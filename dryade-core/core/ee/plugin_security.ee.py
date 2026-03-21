# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Plugin Security Enforcement (Enterprise Edition).

Contains all security-critical plugin enforcement code:
- Allowlist loading and validation (gate at discovery time)
- Plugin code hash computation and verification (SHA-256 / SHA-3-256)
- Encrypted package hash computation and verification
- Plugin encryption key derivation (HKDF-SHA256)
- UI bundle signature verification
- EnterprisePluginProtocol base class
- Encrypted bridge and plugin detection helpers

Community users without this module get zero plugins loaded (correct
behavior — community users don't have PM pushing allowlists).
"""

import hashlib
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# Module-level allowlist cache
# =============================================================================

_allowed_plugins: frozenset[str] | None = None
_allowlist_loaded: bool = False
_allowlist_cache_lock = threading.Lock()

def _load_allowlist() -> frozenset[str] | None:
    """Load and cache the signed allowlist.

    Returns:
        frozenset of allowed plugin names, or None if no valid allowlist.
    """
    global _allowed_plugins, _allowlist_loaded
    if not _allowlist_loaded:
        with _allowlist_cache_lock:
            if not _allowlist_loaded:
                from core.ee.allowlist_ee import get_allowed_plugins

                _allowed_plugins = get_allowed_plugins()
                _allowlist_loaded = True
    return _allowed_plugins

def reload_allowlist() -> frozenset[str] | None:
    """Force reload the allowlist (for hot-reload).

    Clears the cache and re-reads from disk.

    Returns:
        frozenset of allowed plugin names, or None if no valid allowlist.
    """
    global _allowed_plugins, _allowlist_loaded
    with _allowlist_cache_lock:
        _allowlist_loaded = False
    return _load_allowlist()

def validate_before_load(plugin_name: str) -> tuple[bool, str]:
    """Validate plugin can be loaded by checking the signed allowlist.

    Args:
        plugin_name: Name of the plugin to validate

    Returns:
        (allowed, reason) tuple
    """
    allowed = _load_allowlist()
    if allowed is None:
        return False, "no valid allowlist"
    if plugin_name not in allowed:
        return False, "not in allowlist"
    return True, "allowed"

# =============================================================================
# Plugin Hash Computation
# =============================================================================

def _compute_plugin_hash(plugin_dir: Path) -> str:
    """Compute a SHA-256 hash of all Python source files in a plugin directory.

    Algorithm matches the Rust implementation in scanner.rs:
    1. Collect all *.py files recursively, excluding __pycache__/ dirs and *.pyc files.
    2. Sort file paths lexicographically (relative to plugin_dir).
    3. For each file: sha256(relative_path_str + ":" + file_content_bytes).
    4. Concatenate all "relative_path:hex_hash" strings in sorted order separated by newlines.
    5. Final sha256 of concatenated string.
    6. Return hex-encoded digest prefixed with "sha256:".

    Args:
        plugin_dir: Path to the plugin directory.

    Returns:
        Hash string in format "sha256:<hex_digest>".
    """
    py_files: list[Path] = []

    def collect_py(directory: Path) -> None:
        for entry in directory.iterdir():
            if entry.is_dir():
                if entry.name != "__pycache__":
                    collect_py(entry)
            elif entry.suffix == ".py":
                py_files.append(entry)

    collect_py(plugin_dir)
    py_files.sort()  # Sort absolute paths lexicographically

    parts: list[str] = []
    for abs_path in py_files:
        rel_path = abs_path.relative_to(plugin_dir)
        # Use forward slashes for cross-platform consistency (matches Rust)
        rel_str = str(rel_path).replace("\\", "/")

        content = abs_path.read_bytes()
        file_hasher = hashlib.sha256()
        file_hasher.update(rel_str.encode("utf-8"))
        file_hasher.update(b":")
        file_hasher.update(content)
        file_hash = file_hasher.hexdigest()

        parts.append(f"{rel_str}:{file_hash}")

    combined = "\n".join(parts)
    final_hasher = hashlib.sha256()
    final_hasher.update(combined.encode("utf-8"))
    return f"sha256:{final_hasher.hexdigest()}"

def _compute_plugin_hash_sha3(plugin_dir: Path) -> str:
    """Compute a SHA-3-256 hash of all Python source files in a plugin directory.

    Same algorithm as _compute_plugin_hash but using SHA-3-256 instead of SHA-256.
    Used for v3 allowlists with post-quantum hardened hashing.

    Args:
        plugin_dir: Path to the plugin directory.

    Returns:
        Hash string in format "sha3-256:<hex_digest>".
    """
    py_files: list[Path] = []

    def collect_py(directory: Path) -> None:
        for entry in directory.iterdir():
            if entry.is_dir():
                if entry.name != "__pycache__":
                    collect_py(entry)
            elif entry.suffix == ".py":
                py_files.append(entry)

    collect_py(plugin_dir)
    py_files.sort()

    parts: list[str] = []
    for abs_path in py_files:
        rel_path = abs_path.relative_to(plugin_dir)
        rel_str = str(rel_path).replace("\\", "/")

        content = abs_path.read_bytes()
        file_hasher = hashlib.sha3_256()
        file_hasher.update(rel_str.encode("utf-8"))
        file_hasher.update(b":")
        file_hasher.update(content)
        file_hash = file_hasher.hexdigest()

        parts.append(f"{rel_str}:{file_hash}")

    combined = "\n".join(parts)
    final_hasher = hashlib.sha3_256()
    final_hasher.update(combined.encode("utf-8"))
    return f"sha3-256:{final_hasher.hexdigest()}"

# =============================================================================
# Encrypted Package Hash Computation
# =============================================================================

def _compute_dryadepkg_hash(dryadepkg_path: Path) -> str:
    """Compute SHA-256 hash of a .dryadepkg file for allowlist verification.

    For encrypted marketplace plugins, the hash artifact is the .dryadepkg
    package file itself (not its decrypted contents, since they never touch disk).
    The hash is prefixed "sha256:" to match the plaintext plugin hash format.

    Args:
        dryadepkg_path: Path to the .dryadepkg file.

    Returns:
        Hash string in format "sha256:<hex_digest>".
    """
    content = dryadepkg_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"

def _compute_dryadepkg_hash_sha3(dryadepkg_path: Path) -> str:
    """Compute SHA-3-256 hash of a .dryadepkg file for v3 allowlist verification.

    Args:
        dryadepkg_path: Path to the .dryadepkg file.

    Returns:
        Hash string in format "sha3-256:<hex_digest>".
    """
    content = dryadepkg_path.read_bytes()
    return f"sha3-256:{hashlib.sha3_256(content).hexdigest()}"

# =============================================================================
# Encryption Key Derivation
# =============================================================================

def _derive_plugin_key(master_secret: bytes, plugin_name: str) -> bytes:
    """Derive a 32-byte AES-256 encryption key for a specific plugin.

    Uses HKDF-SHA256 with the plugin name as salt and "dryadepkg-v2" as info.
    This matches the key derivation used during CI packaging.

    Args:
        master_secret: Raw bytes of DRYADE_ENCRYPTION_SECRET.
        plugin_name: Plugin name used as HKDF salt for key isolation.

    Returns:
        32-byte derived encryption key.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=plugin_name.encode("utf-8"),
        info=b"dryadepkg-v2",
    )
    return hkdf.derive(master_secret)

def _get_plugin_encryption_key(plugin_name: str) -> bytes | None:
    """Get the per-plugin encryption key from the environment.

    Reads DRYADE_ENCRYPTION_SECRET (hex-encoded master secret) and derives
    a plugin-specific key via HKDF. Returns None if env var is not set,
    which disables encrypted plugin loading gracefully.

    Args:
        plugin_name: Plugin name for per-plugin key derivation.

    Returns:
        32-byte derived key, or None if DRYADE_ENCRYPTION_SECRET is not set.
    """
    master_hex = os.environ.get("DRYADE_ENCRYPTION_SECRET")
    if not master_hex:
        return None
    try:
        master_secret = bytes.fromhex(master_hex)
    except ValueError:
        logger.warning("DRYADE_ENCRYPTION_SECRET is not valid hex — encrypted plugins disabled")
        return None
    return _derive_plugin_key(master_secret, plugin_name)

# =============================================================================
# Hash Verification
# =============================================================================

def verify_plugin_hash(plugin_name: str, plugin_dir: Path) -> bool:
    """Verify a plugin's on-disk code matches the hash in the signed allowlist.

    Supports both SHA-3-256 (v3 allowlists) and SHA-256 (v2 backward compat).
    Unknown hash prefixes are rejected (fail-closed).

    Args:
        plugin_name: Name of the plugin (used as key in plugin_hashes dict).
        plugin_dir: Path to the plugin directory on disk.

    Returns:
        True if hash matches or if no hashes in allowlist (backward compat).
        False if hash mismatch, unknown prefix, or plugin not in hashes dict.
    """
    from core.ee.allowlist_ee import get_plugin_hashes

    hashes = get_plugin_hashes()
    if hashes is None:
        # No plugin_hashes in allowlist — dev workflow or old allowlist format
        return True

    expected = hashes.get(plugin_name)
    if expected is None:
        logger.warning(
            "Plugin '%s' not found in allowlist plugin_hashes — skipping",
            plugin_name,
        )
        return False

    # Detect hash algorithm from prefix and compute accordingly
    if expected.startswith("sha3-256:"):
        actual = _compute_plugin_hash_sha3(plugin_dir)
        expected_hex = expected.removeprefix("sha3-256:")
        actual_hex = actual.removeprefix("sha3-256:")
    elif expected.startswith("sha256:"):
        actual = _compute_plugin_hash(plugin_dir)
        expected_hex = expected.removeprefix("sha256:")
        actual_hex = actual.removeprefix("sha256:")
    else:
        # Unknown hash prefix — fail-closed
        logger.warning(
            "Plugin '%s' has unknown hash prefix in allowlist — skipping (hash: %s...)",
            plugin_name,
            expected[:20],
        )
        return False

    if expected_hex != actual_hex:
        logger.warning(
            "Plugin '%s' code hash mismatch — skipping (expected: %s..., got: %s...)",
            plugin_name,
            expected_hex[:16],
            actual_hex[:16],
        )
        return False

    return True

def verify_dryadepkg_hash(plugin_name: str, dryadepkg_path: Path) -> bool:
    """Verify an encrypted .dryadepkg file's hash against the signed allowlist.

    Supports both SHA-3-256 (v3 allowlists) and SHA-256 (v2 backward compat).
    Unknown hash prefixes are rejected (fail-closed).

    Args:
        plugin_name: Name of the plugin (used as key in plugin_hashes dict).
        dryadepkg_path: Path to the .dryadepkg file on disk.

    Returns:
        True if hash matches or if no hashes in allowlist (backward compat).
        False if hash mismatch, unknown prefix, or plugin not in hashes dict.
    """
    from core.ee.allowlist_ee import get_plugin_hashes

    hashes = get_plugin_hashes()
    if hashes is None:
        # No plugin_hashes in allowlist — dev workflow or old allowlist format
        return True

    expected = hashes.get(plugin_name)
    if expected is None:
        logger.warning(
            "Encrypted plugin '%s' not found in allowlist plugin_hashes — skipping",
            plugin_name,
        )
        return False

    # Detect hash algorithm from prefix and compute accordingly
    if expected.startswith("sha3-256:"):
        actual = _compute_dryadepkg_hash_sha3(dryadepkg_path)
        expected_hex = expected.removeprefix("sha3-256:")
        actual_hex = actual.removeprefix("sha3-256:")
    elif expected.startswith("sha256:"):
        actual = _compute_dryadepkg_hash(dryadepkg_path)
        expected_hex = expected.removeprefix("sha256:")
        actual_hex = actual.removeprefix("sha256:")
    else:
        logger.warning(
            "Encrypted plugin '%s' has unknown hash prefix — skipping (hash: %s...)",
            plugin_name,
            expected[:20],
        )
        return False

    if expected_hex != actual_hex:
        logger.warning(
            "Encrypted plugin '%s' package hash mismatch — skipping (expected: %s..., got: %s...)",
            plugin_name,
            expected_hex[:16],
            actual_hex[:16],
        )
        return False

    return True

# =============================================================================
# UI Bundle Verification
# =============================================================================

def _verify_ui_bundle(plugin_dir: Path, manifest: dict) -> bool:
    """Check that a plugin's UI bundle file exists and matches the declared hash.

    Returns True if the bundle is present and the SHA-256 digest matches
    ``ui_bundle_hash`` in the manifest.  Returns False (fail-closed) in all
    other cases:

    - Bundle file absent
    - ``ui_bundle_hash`` key missing from manifest
    - ``ui_bundle_hash`` is an empty string
    - Digest computed from the on-disk file does not match the declared hash

    The optional ``ui.entry`` key in the manifest overrides the default bundle
    path (``ui/dist/bundle.js``).  Hash values may optionally be prefixed with
    ``sha256-``; the prefix is stripped before comparison.

    This function is intentionally narrow: it only validates the bundle.  The
    ``has_ui`` guard (whether to call this function at all) lives in
    ``discover_plugins()`` — this keeps the two concerns separate and makes
    the helper easy to unit-test in isolation.
    """
    ui_config = manifest.get("ui", {})
    entry = ui_config.get("entry", "ui/dist/bundle.js")
    bundle_path = plugin_dir / entry

    if not bundle_path.exists():
        return False

    expected_hash = manifest.get("ui_bundle_hash")
    if not expected_hash:
        # No hash in manifest — strict fail-closed (Phase 175)
        return False

    content = bundle_path.read_bytes()
    computed = hashlib.sha256(content).hexdigest()
    normalized = expected_hash.replace("sha256-", "")
    return computed == normalized

# =============================================================================
# Enterprise Plugin Protocol
# =============================================================================

_EnterprisePluginProtocol = None

def get_enterprise_plugin_protocol():
    """Get EnterprisePluginProtocol class (lazy to avoid circular import)."""
    global _EnterprisePluginProtocol
    if _EnterprisePluginProtocol is None:
        from core.ee.plugins_ee import PluginProtocol

        class EnterprisePluginProtocol(PluginProtocol):
            """Base class for plugins requiring access control.

            Actual access control is handled by Plugin Manager at the route level
            via the signed allowlist.
            """

            def __init__(self):
                super().__init__()

            def _validate_access(self) -> tuple[bool, str]:
                """Always allowed - access control via signed allowlist."""
                return True, "allowed"

            def invalidate_validation_cache(self) -> None:
                """No-op."""

            def register(self, _registry) -> None:
                """Register plugin."""

        _EnterprisePluginProtocol = EnterprisePluginProtocol
    return _EnterprisePluginProtocol

# =============================================================================
# Encrypted Plugin Helpers (PluginManager EE methods)
# =============================================================================

def is_encrypted_plugin(plugins: dict[str, Any], name: str) -> bool:
    """Return True if the named plugin is an encrypted marketplace plugin.

    Encrypted plugins are loaded from .dryadepkg files and have their routes
    obfuscated through the EncryptedPluginBridge.

    Args:
        plugins: Dict of plugin name -> plugin instance.
        name: Plugin name.

    Returns:
        True if plugin is encrypted, False for custom (plaintext) plugins.
    """
    plugin = plugins.get(name)
    return bool(plugin and getattr(plugin, "_dryadepkg_encrypted", False))

def get_bridge(bridge_ref: list[Any | None]) -> Any:
    """Get or create the EncryptedPluginBridge singleton.

    The bridge key is derived from the JWT secret so that session keys
    are deterministic per server instance.

    Args:
        bridge_ref: Mutable list holding [bridge_instance_or_None].

    Returns:
        EncryptedPluginBridge instance (lazy-initialized on first call).
    """
    if bridge_ref[0] is not None:
        return bridge_ref[0]

    from core.encrypted_bridge import EncryptedPluginBridge

    bridge_key = _derive_bridge_key()
    bridge_ref[0] = EncryptedPluginBridge(bridge_key)
    return bridge_ref[0]

def _derive_bridge_key() -> bytes:
    """Derive the bridge HMAC key from the server JWT secret.

    Returns:
        32-byte bridge key (HMAC-SHA256 of JWT secret with context string).
    """
    import hashlib as _hashlib
    import hmac as _hmac

    try:
        from core.config import get_settings

        jwt_secret = (get_settings().jwt_secret or "default-bridge-key").encode("utf-8")
    except Exception:
        jwt_secret = b"default-bridge-key"
    return _hmac.new(jwt_secret, b"dryade-encrypted-bridge", _hashlib.sha256).digest()
