# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.

"""Signed plugin allowlist verification with Ed25519 + ML-DSA-65 dual signatures.

Security model:
- Plugin Manager (PM) pushes a signed allowlist containing allowed plugin names.
- Core verifies the Ed25519 signature against a TOFU-pinned public key.
- For v3 allowlists, core ALSO verifies the ML-DSA-65 (FIPS 204) signature.
- Only plugins named in a verified allowlist may load.
- No allowlist file = no plugins.
- Invalid signature = no plugins (silent -- no security details leaked).

TOFU (Trust-on-First-Use):
- On first push, the PM public key is pinned to ~/.dryade/pm-pubkey.pem.
- For v3, the ML-DSA public key is also pinned to ~/.dryade/pm-pubkey-pq.bin.
- All subsequent signatures are verified against these pinned keys.
- Key change requires manual operator reset (delete pinned key file).

Allowlist JSON format (v3):
    {
        "version": 3,
        "timestamp": "2026-03-10T00:00:00Z",
        "expires_at": "2026-03-17T00:00:00Z",
        "plugins": ["audio", "conversation", "debugger"],
        "max_users": 1,
        "tier": "starter",
        "custom_plugin_slots": 3,
        "public_key": "<hex Ed25519 public key>",
        "public_key_pq": "<hex ML-DSA-65 public key>",
        "plugin_hashes": {"audio": "sha3-256:<hex>"},
        "signature_pq": "<hex ML-DSA-65 signature>",
        "signature": "<hex Ed25519 signature>"
    }

Version 2 format is still supported (Ed25519-only, no expiry, no ML-DSA).
Version 1 format is still supported (no max_users, tier, or custom_plugin_slots).

Dual-verification flow (v3):
1. Check expires_at (reject if expired past 5-minute grace)
2. Extract and validate all required fields
3. TOFU pin both Ed25519 and ML-DSA keys
4. Verify ML-DSA-65 over payload excluding BOTH signatures
5. Verify Ed25519 over payload excluding only "signature" (includes signature_pq)
6. Both must pass -- fail-closed

The signature covers canonical JSON:
    json.dumps(payload, sort_keys=True, separators=(',', ':'))
"""

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)

# Grace period for expiry checks (allowlist is still valid for this duration
# after expires_at, to account for clock skew between PM and core).
_EXPIRY_GRACE_MINUTES = 5

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierMetadata:
    """Tier metadata extracted from v2+ allowlist."""

    max_users: int = 0  # 0 = unlimited
    tier: str = "unknown"
    custom_plugin_slots: int = 0  # 0 = unlimited

@dataclass(frozen=True)
class AllowlistResult:
    """Result of allowlist verification."""

    plugins: frozenset[str]
    tier_metadata: TierMetadata | None = None
    plugin_hashes: dict[str, str] | None = None  # {plugin_name: "sha256:<hex>"}

# ---------------------------------------------------------------------------
# Module-level tier metadata cache
# ---------------------------------------------------------------------------

_cached_tier_metadata: TierMetadata | None = None
_tier_cache_lock = threading.Lock()

# Plugin hashes cache -- populated as side-effect of get_allowed_plugins()
_cached_plugin_hashes: dict[str, str] | None = None

# Current allowlist data cache -- raw dict stored after successful verification
# Used by AllowlistWatchdog expiry timer to check expires_at without re-reading file
_current_allowlist_data: dict | None = None

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_allowlist_path() -> Path:
    """Return path to the signed allowlist file.

    Checks ``DRYADE_ALLOWLIST_PATH`` environment variable first. Falls back
    to ``~/.dryade/allowed-plugins.json`` if the env var is unset or empty.

    The env var is read directly (not via Settings) to avoid circular imports
    -- ``allowlist.py`` imports nothing from ``core``.
    """
    env_path = os.getenv("DRYADE_ALLOWLIST_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".dryade" / "allowed-plugins.json"

def _tofu_dir() -> Path:
    """Return directory for TOFU-pinned keys.

    Checks ``DRYADE_TOFU_KEY_DIR`` env var first (for Docker/containerized
    deployments where home may be read-only). Falls back to ``~/.dryade/``.
    """
    env_dir = os.environ.get("DRYADE_TOFU_KEY_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".dryade"

def get_tofu_key_path() -> Path:
    """Return path to the TOFU-pinned PM Ed25519 public key.

    Location: $DRYADE_TOFU_KEY_DIR/pm-pubkey.pem or ~/.dryade/pm-pubkey.pem
    """
    return _tofu_dir() / "pm-pubkey.pem"

def get_tofu_pq_key_path() -> Path:
    """Return path to the TOFU-pinned PM ML-DSA-65 public key.

    Location: $DRYADE_TOFU_KEY_DIR/pm-pubkey-pq.bin or ~/.dryade/pm-pubkey-pq.bin
    Stored as raw bytes (1952 bytes for ML-DSA-65).
    """
    return _tofu_dir() / "pm-pubkey-pq.bin"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_allowed_plugins() -> frozenset[str] | None:
    """Read and verify the signed plugin allowlist.

    Returns:
        frozenset of allowed plugin names if valid, None otherwise.
        None means: no plugins should load.

    Side effect:
        Caches tier metadata from v2+ allowlists (accessible via get_tier_metadata()).
        Caches plugin hashes if present (accessible via get_plugin_hashes()).

    Failure modes (all return None):
        - File missing: logs helpful setup message
        - Invalid JSON: silent
        - Invalid signature: silent
        - TOFU key mismatch: logs vague warning
        - Expired allowlist (v3): silent
    """
    global _cached_tier_metadata, _cached_plugin_hashes
    path = get_allowlist_path()

    if not path.exists():
        logger.info("No plugin allowlist found. See docs.dryade.ai/plugins for setup.")
        with _tier_cache_lock:
            _cached_tier_metadata = None
            _cached_plugin_hashes = None
        _set_current_allowlist_data(None)
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        with _tier_cache_lock:
            _cached_tier_metadata = None
            _cached_plugin_hashes = None
        _set_current_allowlist_data(None)
        return None

    result = verify_and_load_allowlist(data)
    if result is None:
        with _tier_cache_lock:
            _cached_tier_metadata = None
            _cached_plugin_hashes = None
        _set_current_allowlist_data(None)
        return None

    with _tier_cache_lock:
        _cached_tier_metadata = result.tier_metadata
        _cached_plugin_hashes = result.plugin_hashes
    _set_current_allowlist_data(data)
    return result.plugins

def get_tier_metadata() -> TierMetadata | None:
    """Return cached tier metadata from the last verified allowlist.

    Returns None if no v2+ allowlist has been loaded yet.
    Metadata is populated as a side-effect of get_allowed_plugins().
    """
    with _tier_cache_lock:
        return _cached_tier_metadata

def get_plugin_hashes() -> dict[str, str] | None:
    """Return cached plugin hashes from the last verified allowlist.

    Returns:
        Dict mapping plugin name to "sha256:<hex>" digest, or None if
        the allowlist has no plugin_hashes field (dev workflow or old allowlists).
        None is also returned if no allowlist has been loaded yet.
    """
    with _tier_cache_lock:
        return _cached_plugin_hashes

def get_current_allowlist_data() -> dict | None:
    """Return the raw allowlist dict from the last successful verification.

    Used by AllowlistWatchdog to check expiry without re-reading the file.
    Returns None if no allowlist has been verified yet.
    """
    with _tier_cache_lock:
        return _current_allowlist_data

def _set_current_allowlist_data(data: dict | None) -> None:
    """Cache the raw allowlist dict after successful verification."""
    global _current_allowlist_data
    with _tier_cache_lock:
        _current_allowlist_data = data

def verify_and_load_allowlist(data: dict) -> AllowlistResult | None:
    """Verify a parsed allowlist dict and return allowed plugin names with metadata.

    For v3 allowlists:
        1. Check expires_at (reject if expired past grace period)
        2. Extract and validate all required fields (public_key_pq, signature_pq)
        3. TOFU pin both Ed25519 and ML-DSA keys
        4. Verify ML-DSA-65 over payload excluding BOTH signatures
        5. Verify Ed25519 over payload excluding only "signature"
        6. Both must pass -- fail-closed

    For v2 allowlists:
        Ed25519-only verification (backward compat during transition)

    Args:
        data: Parsed allowlist dict.

    Returns:
        AllowlistResult with plugins and optional tier_metadata if valid,
        None otherwise.
    """
    try:
        public_key_hex = data["public_key"]
        signature_hex = data["signature"]
        version = data["version"]
        _ = data["plugins"]
    except (KeyError, TypeError):
        return None

    # Reject unsupported versions
    if not isinstance(version, int) or version < 1:
        return None

    # --- v3 path: dual Ed25519 + ML-DSA-65 verification ---
    if version >= 3:
        return _verify_v3(data, public_key_hex, signature_hex, version)

    # --- v2/v1 path: Ed25519-only (backward compat) ---
    return _verify_v2(data, public_key_hex, signature_hex, version)

def write_allowlist_file(data: dict) -> bool:
    """Write allowlist data to the allowlist file path atomically.

    Uses temp-file + os.rename to prevent partial reads by concurrent
    readers.  Creates parent directories if they don't exist.

    Args:
        data: Allowlist dict to write as JSON.

    Returns:
        True if written successfully, False otherwise.
    """
    path = get_allowlist_path()
    tmp_path: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(path.parent), suffix=".tmp", delete=False
        ) as tmp:
            json.dump(data, tmp, indent=2, sort_keys=True)
            tmp_path = tmp.name
        os.rename(tmp_path, str(path))
        return True
    except Exception:
        logger.exception("Failed to write allowlist file")
        # Clean up temp file if rename failed
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False

def reset_tofu_key() -> bool:
    """Delete the TOFU-pinned Ed25519 public key (operator manual reset).

    After reset, the next allowlist push will pin a new key.

    Returns:
        True if key was deleted, False if no key existed.
    """
    path = get_tofu_key_path()
    if not path.exists():
        return False
    try:
        path.unlink()
        logger.info("PM public key reset (TOFU key deleted)")
        return True
    except OSError:
        logger.exception("Failed to delete TOFU key")
        return False

def reset_tofu_pq_key() -> bool:
    """Delete the TOFU-pinned ML-DSA-65 public key (operator manual reset).

    After reset, the next v3 allowlist push will pin a new PQ key.

    Returns:
        True if key was deleted, False if no key existed.
    """
    path = get_tofu_pq_key_path()
    if not path.exists():
        return False
    try:
        path.unlink()
        logger.info("PM ML-DSA public key reset (TOFU PQ key deleted)")
        return True
    except OSError:
        logger.exception("Failed to delete TOFU PQ key")
        return False

def is_allowlist_expired(data: dict) -> bool:
    """Check if a v3 allowlist has expired (past grace period).

    Args:
        data: Parsed allowlist dict with optional ``expires_at`` field.

    Returns:
        True if allowlist is expired (past grace period), False otherwise.
        Returns False for v2 allowlists (no expiry field).
    """
    expires_at_str = data.get("expires_at")
    if not expires_at_str:
        return False
    return _check_expiry(expires_at_str)

# ---------------------------------------------------------------------------
# Internal helpers -- v3 dual-signature verification
# ---------------------------------------------------------------------------

def _verify_v3(
    data: dict,
    public_key_hex: str,
    signature_hex: str,
    version: int,
) -> AllowlistResult | None:
    """Verify a v3 allowlist with dual Ed25519 + ML-DSA-65 signatures.

    Fail-closed: returns None on ANY failure.
    """
    # Step 1: Check expiry
    expires_at_str = data.get("expires_at")
    if not expires_at_str or _check_expiry(expires_at_str):
        return None

    # Step 2: Extract required v3 fields
    public_key_pq_hex = data.get("public_key_pq")
    signature_pq_hex = data.get("signature_pq")

    if not public_key_pq_hex or not signature_pq_hex:
        return None

    # Step 3: TOFU pin Ed25519 key
    public_key = _get_or_pin_public_key(public_key_hex)
    if public_key is None:
        return None

    # Step 3b: TOFU pin ML-DSA key
    mldsa_public_key = _get_or_pin_mldsa_key(public_key_pq_hex)
    if mldsa_public_key is None:
        return None

    # Step 4: Verify ML-DSA-65 (over payload excluding BOTH signatures)
    pq_payload = {
        k: v for k, v in data.items() if k not in ("signature", "signature_pq")
    }
    if not _verify_mldsa_signature(pq_payload, signature_pq_hex, mldsa_public_key):
        return None

    # Step 5: Verify Ed25519 (over payload excluding only "signature" -- includes signature_pq)
    ed_payload = {k: v for k, v in data.items() if k != "signature"}
    if not _verify_signature(ed_payload, signature_hex, public_key):
        return None

    # Step 6: Extract plugins and metadata
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        return None

    tier_metadata = TierMetadata(
        max_users=data.get("max_users", 0),
        tier=data.get("tier", "unknown"),
        custom_plugin_slots=data.get("custom_plugin_slots", 0),
    )

    plugin_hashes = data.get("plugin_hashes")
    if not isinstance(plugin_hashes, dict):
        plugin_hashes = None

    return AllowlistResult(
        plugins=frozenset(plugins),
        tier_metadata=tier_metadata,
        plugin_hashes=plugin_hashes,
    )

def _verify_v2(
    data: dict,
    public_key_hex: str,
    signature_hex: str,
    version: int,
) -> AllowlistResult | None:
    """Verify a v2/v1 allowlist with Ed25519-only signature (backward compat)."""
    # TOFU key pinning
    public_key = _get_or_pin_public_key(public_key_hex)
    if public_key is None:
        return None

    # Build payload (everything except "signature" -- Ed25519 signs over signature_pq if present)
    payload = {k: v for k, v in data.items() if k != "signature"}

    # Verify signature
    if not _verify_signature(payload, signature_hex, public_key):
        return None

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        return None

    # Extract v2 tier metadata
    tier_metadata = None
    if isinstance(version, int) and version >= 2:
        tier_metadata = TierMetadata(
            max_users=data.get("max_users", 0),
            tier=data.get("tier", "unknown"),
            custom_plugin_slots=data.get("custom_plugin_slots", 0),
        )

    # Extract plugin_hashes (optional field -- absent in dev workflow)
    plugin_hashes = data.get("plugin_hashes")  # None if field not present
    if not isinstance(plugin_hashes, dict):
        plugin_hashes = None

    return AllowlistResult(
        plugins=frozenset(plugins),
        tier_metadata=tier_metadata,
        plugin_hashes=plugin_hashes,
    )

# ---------------------------------------------------------------------------
# Internal helpers -- expiry
# ---------------------------------------------------------------------------

def _check_expiry(expires_at_str: str) -> bool:
    """Return True if the allowlist has expired (past grace period).

    Parses ISO 8601 timestamp and compares to UTC now minus grace period.
    """
    try:
        # Parse ISO 8601 -- handle both "Z" suffix and "+00:00"
        expires_at_str_clean = expires_at_str.replace("Z", "+00:00")
        expires_at = datetime.fromisoformat(expires_at_str_clean)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        grace = timedelta(minutes=_EXPIRY_GRACE_MINUTES)

        return now > (expires_at + grace)
    except (ValueError, TypeError):
        # Invalid timestamp format -- fail-closed
        return True

# ---------------------------------------------------------------------------
# Internal helpers -- Ed25519 TOFU + verification
# ---------------------------------------------------------------------------

def _get_or_pin_public_key(public_key_hex: str) -> Ed25519PublicKey | None:
    """TOFU: pin on first use, verify against pinned on subsequent uses.

    Args:
        public_key_hex: Hex-encoded 32-byte raw Ed25519 public key.

    Returns:
        The Ed25519PublicKey to use for verification, or None on key mismatch.
    """
    try:
        incoming_bytes = bytes.fromhex(public_key_hex)
        incoming_key = Ed25519PublicKey.from_public_bytes(incoming_bytes)
    except (ValueError, Exception):
        return None

    tofu_path = get_tofu_key_path()

    if tofu_path.exists():
        # Verify against pinned key
        try:
            pinned_key = serialization.load_pem_public_key(tofu_path.read_bytes())
            if not isinstance(pinned_key, Ed25519PublicKey):
                return None

            pinned_raw = pinned_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            if pinned_raw != incoming_bytes:
                logger.warning("Allowlist key mismatch")
                return None
            return pinned_key
        except Exception:
            return None
    else:
        # First use -- pin the key
        try:
            tofu_path.parent.mkdir(parents=True, exist_ok=True)
            pem = incoming_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            # Atomic write: temp file + rename
            tmp_fd, tmp_name = tempfile.mkstemp(
                dir=str(tofu_path.parent), suffix=".tmp"
            )
            try:
                os.write(tmp_fd, pem)
                os.close(tmp_fd)
                os.rename(tmp_name, str(tofu_path))
            except Exception:
                os.close(tmp_fd) if not os.get_inheritable(tmp_fd) else None
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            tofu_path.chmod(0o644)
            logger.info("PM public key pinned (TOFU)")
            return incoming_key
        except OSError:
            logger.exception("Failed to pin TOFU key")
            return None

def _verify_signature(
    payload: dict,
    signature_hex: str,
    public_key: Ed25519PublicKey,
) -> bool:
    """Verify Ed25519 signature over canonical JSON of payload.

    Canonical JSON: json.dumps(payload, sort_keys=True, separators=(',', ':'))

    Args:
        payload: Dict to verify (everything except "signature" key).
        signature_hex: Hex-encoded Ed25519 signature.
        public_key: Ed25519 public key to verify against.

    Returns:
        True if signature is valid, False otherwise (silent fail).
    """
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, canonical)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False

# ---------------------------------------------------------------------------
# Internal helpers -- ML-DSA-65 TOFU + verification
# ---------------------------------------------------------------------------

def _get_or_pin_mldsa_key(public_key_pq_hex: str) -> bytes | None:
    """TOFU: pin ML-DSA-65 public key on first use, verify on subsequent uses.

    The ML-DSA public key is stored as raw bytes in ~/.dryade/pm-pubkey-pq.bin.

    Args:
        public_key_pq_hex: Hex-encoded ML-DSA-65 public key (1952 bytes).

    Returns:
        The raw ML-DSA-65 public key bytes, or None on key mismatch / error.
    """
    try:
        incoming_bytes = bytes.fromhex(public_key_pq_hex)
    except ValueError:
        return None

    # ML-DSA-65 public key is 1952 bytes
    if len(incoming_bytes) != 1952:
        return None

    tofu_path = get_tofu_pq_key_path()

    if tofu_path.exists():
        # Verify against pinned key
        try:
            pinned_bytes = tofu_path.read_bytes()
            if pinned_bytes != incoming_bytes:
                logger.warning("Allowlist ML-DSA key mismatch")
                return None
            return pinned_bytes
        except Exception:
            return None
    else:
        # First use -- pin the key (atomic write)
        try:
            tofu_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_name = tempfile.mkstemp(
                dir=str(tofu_path.parent), suffix=".tmp"
            )
            try:
                os.write(tmp_fd, incoming_bytes)
                os.close(tmp_fd)
                os.rename(tmp_name, str(tofu_path))
            except Exception:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            tofu_path.chmod(0o644)
            logger.info("PM ML-DSA public key pinned (TOFU)")
            return incoming_bytes
        except OSError:
            logger.exception("Failed to pin TOFU PQ key")
            return None

def _verify_mldsa_signature(
    payload: dict,
    signature_pq_hex: str,
    public_key: bytes,
) -> bool:
    """Verify ML-DSA-65 signature over canonical JSON of payload.

    Uses the same canonical JSON format as Ed25519.

    Args:
        payload: Dict to verify (everything except "signature" and "signature_pq").
        signature_pq_hex: Hex-encoded ML-DSA-65 signature (3309 bytes).
        public_key: Raw ML-DSA-65 public key bytes (1952 bytes).

    Returns:
        True if signature is valid, False otherwise (silent fail).
    """
    try:
        from core.ee.crypto.pq import verify_mldsa65

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        signature = bytes.fromhex(signature_pq_hex)
        return verify_mldsa65(canonical, signature, public_key)
    except (ValueError, Exception):
        return False
