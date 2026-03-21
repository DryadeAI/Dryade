# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Post-quantum cryptography module for Dryade core.

Provides ML-DSA-65 (FIPS 204) signature verification and SHA-3/SHAKE256
hashing utilities. Uses liboqs-python for ML-DSA operations and Python's
built-in hashlib for SHA-3.

SECURITY: This module NEVER fails open. If liboqs is not available,
ImportError is raised at module load time -- no silent fallback.
"""

import hashlib
import logging
import os

try:
    import oqs
except ImportError as e:
    raise ImportError(
        "liboqs-python is required for post-quantum crypto. "
        "Install with: pip install liboqs-python==0.14.1 "
        "and ensure liboqs shared library is available (LD_LIBRARY_PATH). "
        f"Original error: {e}"
    ) from e

logger = logging.getLogger(__name__)

# ML-DSA-65 constants (FIPS 204)
MLDSA65_SIG_SIZE = 3309  # bytes
MLDSA65_PK_SIZE = 1952  # bytes
MLDSA65_ALG_NAME = "ML-DSA-65"

def generate_mldsa65_keypair() -> tuple[bytes, bytes]:
    """Generate an ML-DSA-65 keypair.

    Returns:
        (public_key, secret_key) tuple of raw bytes.
        public_key: 1952 bytes, secret_key: 4032 bytes.
    """
    with oqs.Signature(MLDSA65_ALG_NAME) as signer:
        public_key = signer.generate_keypair()
        secret_key = signer.export_secret_key()
    return bytes(public_key), bytes(secret_key)

def sign_mldsa65(message: bytes, secret_key: bytes) -> bytes:
    """Sign a message with ML-DSA-65.

    Args:
        message: The message bytes to sign.
        secret_key: The ML-DSA-65 secret key bytes (4032 bytes).

    Returns:
        ML-DSA-65 signature bytes (3309 bytes).

    Raises:
        ValueError: If signing fails for any reason.
    """
    try:
        with oqs.Signature(MLDSA65_ALG_NAME, secret_key) as signer:
            signature = signer.sign(message)
        return bytes(signature)
    except Exception as e:
        raise ValueError(f"ML-DSA-65 signing failed: {e}") from e

def verify_mldsa65(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Verify an ML-DSA-65 signature.

    Args:
        message: The original signed message bytes.
        signature: The ML-DSA-65 signature bytes (3309 bytes).
        public_key: The ML-DSA-65 public key bytes (1952 bytes).

    Returns:
        True if the signature is valid, False otherwise.
        NEVER raises an exception -- returns False on any error.
    """
    try:
        if message is None or signature is None or public_key is None:
            return False

        if len(signature) != MLDSA65_SIG_SIZE:
            logger.debug(
                "ML-DSA-65 signature size mismatch: got %d, expected %d",
                len(signature),
                MLDSA65_SIG_SIZE,
            )
            return False

        if len(public_key) != MLDSA65_PK_SIZE:
            logger.debug(
                "ML-DSA-65 public key size mismatch: got %d, expected %d",
                len(public_key),
                MLDSA65_PK_SIZE,
            )
            return False

        with oqs.Signature(MLDSA65_ALG_NAME) as verifier:
            return verifier.verify(message, signature, public_key)

    except Exception:
        logger.debug("ML-DSA-65 verification failed with exception", exc_info=True)
        return False

# ML-KEM-1024 constants (FIPS 203)
ML_KEM_1024_CT_SIZE = 1568  # KEM ciphertext size in bytes
NONCE_SIZE = 12  # AES-GCM nonce size in bytes

def generate_mlkem_keypair() -> tuple[bytes, bytes]:
    """Generate an ML-KEM-1024 keypair.

    Returns:
        (public_key, secret_key) tuple of raw bytes.
    """
    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        public_key = kem.generate_keypair()
        secret_key = kem.export_secret_key()
    return bytes(public_key), bytes(secret_key)

def hybrid_encrypt(plaintext: bytes, recipient_public_key: bytes) -> bytes:
    """ML-KEM-1024 + AES-256-GCM hybrid encryption.

    Layout: [KEM_CT (1568 bytes)][nonce (12 bytes)][AES ciphertext + GCM tag (16 bytes)]

    Args:
        plaintext: Data to encrypt (any size).
        recipient_public_key: ML-KEM-1024 public key bytes.

    Returns:
        Encrypted bytes in the hybrid format.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        kem_ciphertext, shared_secret = kem.encap_secret(recipient_public_key)

    # Use first 32 bytes of shared secret as AES-256 key
    aes_key = bytes(shared_secret[:32])
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(aes_key)
    aes_ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    return bytes(kem_ciphertext) + nonce + aes_ciphertext

def hybrid_decrypt(encrypted: bytes, recipient_secret_key: bytes) -> bytes:
    """ML-KEM-1024 + AES-256-GCM hybrid decryption.

    Args:
        encrypted: Bytes produced by hybrid_encrypt().
        recipient_secret_key: ML-KEM-1024 secret key bytes.

    Returns:
        Decrypted plaintext bytes.

    Raises:
        ValueError: If the payload is too short.
        Exception: If decryption fails (tampered data, wrong key).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    min_size = ML_KEM_1024_CT_SIZE + NONCE_SIZE + 1
    if len(encrypted) < min_size:
        raise ValueError(
            f"Hybrid-encrypted payload too short: {len(encrypted)} bytes "
            f"(minimum {min_size})"
        )

    kem_ct = encrypted[:ML_KEM_1024_CT_SIZE]
    nonce = encrypted[ML_KEM_1024_CT_SIZE : ML_KEM_1024_CT_SIZE + NONCE_SIZE]
    aes_ct = encrypted[ML_KEM_1024_CT_SIZE + NONCE_SIZE :]

    with oqs.KeyEncapsulation("ML-KEM-1024", recipient_secret_key) as kem:
        shared_secret = kem.decap_secret(kem_ct)

    aes_key = bytes(shared_secret[:32])
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, aes_ct, None)

def sha3_256_hex(data: bytes) -> str:
    """Compute SHA-3-256 hash and return hex digest.

    Args:
        data: Input bytes to hash.

    Returns:
        64-character lowercase hex string (256-bit digest).
    """
    return hashlib.sha3_256(data).hexdigest()

def shake256_hex(data: bytes, length: int = 32) -> str:
    """Compute SHAKE256 hash with variable output length and return hex digest.

    Args:
        data: Input bytes to hash.
        length: Output length in bytes (default 32 = 256 bits).

    Returns:
        Hex string of length * 2 characters.
    """
    return hashlib.shake_256(data).hexdigest(length)
