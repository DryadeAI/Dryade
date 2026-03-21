# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Core self-integrity check at startup.

Computes an aggregate SHA-3-256 hash over all Python source files in the core/
directory. This is INFORMATIONAL only -- it never blocks startup.

Layered defense model:
1. PM verifies its own binary (blocking in production)
2. Core logs its integrity hash (this module -- informational, warns on deviation)
3. Encrypted marketplace plugins are the ultimate gate (no valid ML-KEM keys = useless)

A root attacker CAN modify Python files, but without valid decryption keys,
marketplace plugin content remains inaccessible.
"""

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default paths -- patched in tests
CORE_DIR = Path(__file__).resolve().parent.parent
INTEGRITY_HASH_FILE = Path.home() / ".dryade" / "core-integrity.hash"

def check_core_integrity(core_dir: Path) -> str:
    """Compute aggregate SHA-3-256 over all .py files in core_dir.

    Files are sorted by their relative path for deterministic ordering.
    Non-.py files are ignored.

    Args:
        core_dir: Path to the core directory to hash.

    Returns:
        64-character lowercase hex digest (SHA-3-256).
    """
    hasher = hashlib.sha3_256()

    # Collect all .py files, sorted by relative path for determinism
    py_files = sorted(core_dir.rglob("*.py"), key=lambda p: str(p.relative_to(core_dir)))

    for py_file in py_files:
        try:
            content = py_file.read_bytes()
            hasher.update(content)
        except (OSError, PermissionError) as e:
            logger.warning("Cannot read %s for integrity check: %s", py_file, e)
            # Include the filename in hash so missing files still change the digest
            hasher.update(f"ERROR:{py_file}".encode())

    return hasher.hexdigest()

def log_integrity_at_startup() -> None:
    """Compute and log core integrity hash. Called during FastAPI lifespan.

    - Computes hash of all .py files in the core directory
    - Logs the hash at INFO level
    - Compares against stored hash (if exists) and logs WARNING on deviation
    - Stores hash to ~/.dryade/core-integrity.hash on clean startup

    This function NEVER raises exceptions -- all errors are caught and logged.
    """
    try:
        current_hash = check_core_integrity(CORE_DIR)
        logger.info("Core integrity hash: %s", current_hash)

        # Check for previous hash
        try:
            if INTEGRITY_HASH_FILE.exists():
                stored_hash = INTEGRITY_HASH_FILE.read_text().strip()
                if stored_hash and stored_hash != current_hash:
                    logger.warning(
                        "Core integrity hash has changed since last startup! "
                        "Previous: %s, Current: %s. "
                        "This may indicate core files were modified.",
                        stored_hash,
                        current_hash,
                    )
                elif stored_hash == current_hash:
                    logger.debug("Core integrity hash unchanged from last startup")
        except (OSError, PermissionError) as e:
            logger.debug("Cannot read stored integrity hash: %s", e)

        # Store current hash for next comparison
        try:
            INTEGRITY_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
            INTEGRITY_HASH_FILE.write_text(current_hash + "\n")
        except (OSError, PermissionError) as e:
            logger.debug("Cannot store integrity hash: %s", e)

    except Exception as e:
        # NEVER fail startup -- this is purely informational
        logger.warning("Core integrity check failed (non-fatal): %s", e)
