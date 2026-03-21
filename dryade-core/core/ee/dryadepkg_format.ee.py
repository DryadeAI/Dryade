# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
# Vendored from plugins/pipeline/dryadepkg_format.py — keep in sync.
"""dryadepkg_format.py — .dryadepkg v2/v3 format library.

Builds and reads ZIP-based .dryadepkg containers with:
  - Plaintext MANIFEST.json (metadata + format version)
  - Ed25519 author signature (manifest.sig)
  - Ed25519 marketplace counter-signature (manifest.sig.market)
  - ML-DSA-65 author PQ signature (manifest.sig.pq) [v3]
  - ML-DSA-65 marketplace PQ counter-signature (manifest.sig.market.pq) [v3]
  - AES-256-GCM encrypted payload (payload.enc)
  - SHA-3-256 integrity hash of plaintext payload (payload.hash) [v3, SHA-256 in v2]
  - Magic identifier file (dryade-pkg)

Format version: 3.0 (backward compatible with 2.0)
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import zipfile
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ── Constants ─────────────────────────────────────────────────────────────────

MAGIC_CONTENT = b"DRYADE_PKG_V1"
FORMAT_VERSION_V2 = "2.0"
FORMAT_VERSION_V3 = "3.0"
FORMAT_VERSION = FORMAT_VERSION_V3  # Default for new packages
NONCE_SIZE = 12  # AES-GCM 96-bit nonce

logger = logging.getLogger(__name__)

# ── Exceptions ────────────────────────────────────────────────────────────────

class IntegrityError(Exception):
    """Raised when the decrypted payload's hash does not match payload.hash."""

# ── Public API ────────────────────────────────────────────────────────────────

def build_dryadepkg(
    payload_bytes: bytes,
    manifest_dict: dict[str, Any],
    author_private_key: Ed25519PrivateKey,
    encryption_key: bytes,
    marketplace_private_key: Ed25519PrivateKey | None = None,
    author_pq_secret_key: bytes | None = None,
    marketplace_pq_secret_key: bytes | None = None,
) -> bytes:
    """Build a .dryadepkg v2 or v3 ZIP container.

    If author_pq_secret_key is provided, builds v3 with ML-DSA-65 PQ
    dual-signatures and SHA-3-256 payload hash. Otherwise builds v2.

    Args:
        payload_bytes: Raw plugin payload (typically a tar.gz archive).
        manifest_dict: Plugin metadata dict. Will be merged with format_version and created_at.
        author_private_key: Ed25519 private key for author signature.
        encryption_key: 32-byte AES-256 key for payload encryption.
        marketplace_private_key: Optional Ed25519 key for marketplace counter-signature.
        author_pq_secret_key: Optional ML-DSA-65 secret key for author PQ signature (enables v3).
        marketplace_pq_secret_key: Optional ML-DSA-65 secret key for marketplace PQ counter-signature.

    Returns:
        ZIP archive bytes (.dryadepkg file content).
    """
    is_v3 = author_pq_secret_key is not None
    version = FORMAT_VERSION_V3 if is_v3 else FORMAT_VERSION_V2

    # 1. Build MANIFEST.json — merge caller dict with required format fields
    manifest = {
        **manifest_dict,
        "format_version": version,
        "created_at": datetime.now(UTC).isoformat(),
    }
    manifest_bytes = _canonical_json(manifest)

    # 2. Compute payload hash
    if is_v3:
        # SHA-3-256 with prefix for v3
        payload_hash = f"sha3-256:{hashlib.sha3_256(payload_bytes).hexdigest()}"
    else:
        # SHA-256 (no prefix) for v2 backward compat
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    # 3. Encrypt payload with AES-256-GCM
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(encryption_key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, payload_bytes, None)
    payload_enc = nonce + ciphertext_and_tag

    # 4. Sign MANIFEST.json with Ed25519 author key
    author_sig = author_private_key.sign(manifest_bytes)

    # 5. Ed25519 marketplace counter-signature (if provided)
    market_sig = b""
    if marketplace_private_key is not None:
        market_sig = marketplace_private_key.sign(manifest_bytes)

    # 6. ML-DSA-65 PQ signatures (v3 only)
    author_pq_sig = b""
    market_pq_sig = b""
    if is_v3:
        from core.ee.crypto.pq import sign_mldsa65

        author_pq_sig = sign_mldsa65(manifest_bytes, author_pq_secret_key)
        if marketplace_pq_secret_key is not None:
            market_pq_sig = sign_mldsa65(manifest_bytes, marketplace_pq_secret_key)

    # 7. Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", manifest_bytes)
        zf.writestr("manifest.sig", author_sig)
        zf.writestr("manifest.sig.market", market_sig)
        zf.writestr("payload.enc", payload_enc)
        zf.writestr("payload.hash", payload_hash.encode("utf-8"))
        zf.writestr("dryade-pkg", MAGIC_CONTENT)
        # v3: PQ signature files
        if is_v3:
            zf.writestr("manifest.sig.pq", author_pq_sig)
            if market_pq_sig:
                zf.writestr("manifest.sig.market.pq", market_pq_sig)

    return buf.getvalue()

def read_dryadepkg_manifest(pkg_bytes: bytes) -> dict[str, Any]:
    """Extract and parse MANIFEST.json from a .dryadepkg package.

    Does NOT decrypt or validate the payload — just reads metadata.

    Args:
        pkg_bytes: Raw .dryadepkg file bytes.

    Returns:
        Parsed MANIFEST.json dict.

    Raises:
        KeyError: If MANIFEST.json is missing from the archive.
        ValueError: If format_version field is absent.
    """
    with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as zf:
        manifest_bytes = zf.read("MANIFEST.json")

    manifest = json.loads(manifest_bytes.decode("utf-8"))

    if "format_version" not in manifest:
        raise ValueError("MANIFEST.json is missing required 'format_version' field")

    return manifest

def verify_dryadepkg(
    pkg_bytes: bytes,
    author_public_key: Ed25519PublicKey,
    marketplace_public_key: Ed25519PublicKey | None = None,
    author_pq_public_key: bytes | None = None,
    marketplace_pq_public_key: bytes | None = None,
) -> tuple[bool, bool, bool, bool]:
    """Verify signatures in a .dryadepkg package (v2 or v3).

    For v3 packages, verifies both Ed25519 and ML-DSA-65 PQ signatures.
    For v2 packages, Ed25519 only (PQ fields return False).

    Args:
        pkg_bytes: Raw .dryadepkg file bytes.
        author_public_key: Ed25519 public key to verify author signature.
        marketplace_public_key: Optional Ed25519 public key to verify counter-signature.
        author_pq_public_key: Optional ML-DSA-65 public key for author PQ verification.
        marketplace_pq_public_key: Optional ML-DSA-65 public key for marketplace PQ verification.

    Returns:
        (author_valid, market_valid, author_pq_valid, market_pq_valid) tuple.
    """
    with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as zf:
        manifest_bytes = zf.read("MANIFEST.json")
        author_sig = zf.read("manifest.sig")
        market_sig = zf.read("manifest.sig.market")
        names = zf.namelist()

        # Read PQ signatures if present
        author_pq_sig = zf.read("manifest.sig.pq") if "manifest.sig.pq" in names else b""
        market_pq_sig = (
            zf.read("manifest.sig.market.pq") if "manifest.sig.market.pq" in names else b""
        )

    # Detect format version
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    version = manifest.get("format_version", "2.0")

    # Verify Ed25519 author signature
    author_valid = _verify_ed25519(author_public_key, author_sig, manifest_bytes)

    # Verify Ed25519 marketplace counter-signature
    market_valid = False
    if marketplace_public_key is not None and market_sig:
        market_valid = _verify_ed25519(marketplace_public_key, market_sig, manifest_bytes)

    # PQ verification
    author_pq_valid = False
    market_pq_valid = False

    if version == FORMAT_VERSION_V3:
        # v3: verify PQ signatures if keys provided
        if author_pq_public_key is not None and author_pq_sig:
            from core.ee.crypto.pq import verify_mldsa65

            author_pq_valid = verify_mldsa65(manifest_bytes, author_pq_sig, author_pq_public_key)

        if marketplace_pq_public_key is not None and market_pq_sig:
            from core.ee.crypto.pq import verify_mldsa65

            market_pq_valid = verify_mldsa65(
                manifest_bytes, market_pq_sig, marketplace_pq_public_key
            )
    # v2: PQ fields remain False (no PQ signatures in v2 format)

    return author_valid, market_valid, author_pq_valid, market_pq_valid

def decrypt_dryadepkg_payload(pkg_bytes: bytes, encryption_key: bytes) -> bytes:
    """Decrypt the payload from a .dryadepkg package and verify integrity.

    Supports both v2 (SHA-256) and v3 (SHA-3-256 with prefix) payload hashes.

    Args:
        pkg_bytes: Raw .dryadepkg file bytes.
        encryption_key: 32-byte AES-256 key used during build.

    Returns:
        Decrypted plaintext payload bytes.

    Raises:
        ValueError: If decryption fails (wrong key or corrupted ciphertext).
        IntegrityError: If hash of decrypted payload doesn't match payload.hash.
    """
    with zipfile.ZipFile(io.BytesIO(pkg_bytes)) as zf:
        payload_enc = zf.read("payload.enc")
        stored_hash = zf.read("payload.hash").decode("utf-8")

    # Split nonce from ciphertext+tag
    nonce = payload_enc[:NONCE_SIZE]
    ciphertext_and_tag = payload_enc[NONCE_SIZE:]

    # Decrypt — AESGCM.decrypt raises InvalidTag on bad key/data
    aesgcm = AESGCM(encryption_key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}") from e

    # Integrity check — detect hash algorithm from prefix
    if stored_hash.startswith("sha3-256:"):
        # v3: SHA-3-256
        expected_hex = stored_hash.removeprefix("sha3-256:")
        computed_hex = hashlib.sha3_256(plaintext).hexdigest()
    elif stored_hash.startswith("sha256:"):
        # Explicit SHA-256 prefix
        expected_hex = stored_hash.removeprefix("sha256:")
        computed_hex = hashlib.sha256(plaintext).hexdigest()
    else:
        # v2 legacy: bare hex string assumed SHA-256
        expected_hex = stored_hash
        computed_hex = hashlib.sha256(plaintext).hexdigest()

    if computed_hex != expected_hex:
        raise IntegrityError(
            f"Payload integrity check failed: "
            f"computed={computed_hex}, stored={stored_hash}"
        )

    return plaintext

# ── Internal helpers ──────────────────────────────────────────────────────────

def _canonical_json(data: dict[str, Any]) -> bytes:
    """Produce canonical JSON bytes (sorted keys, no extra whitespace, UTF-8)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

def _verify_ed25519(
    public_key: Ed25519PublicKey,
    signature: bytes,
    message: bytes,
) -> bool:
    """Verify an Ed25519 signature. Returns True if valid, False otherwise."""
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
