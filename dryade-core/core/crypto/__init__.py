"""Cryptographic utilities for Dryade core.

Re-exports credential encryption functions (Fernet-based) that were
originally in core/crypto.py before the crypto package was created.
Also provides access to post-quantum crypto via core.crypto.pq.
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from core.logs import get_logger


@lru_cache
def get_encryption_key() -> bytes:
    """Get or generate encryption key from Settings.

    Uses Settings.encryption_key if set, otherwise falls back to a
    deterministic default key for development. Production validation
    in Settings.validate_production_config() warns if unset.
    """
    from core.config import get_settings

    key = get_settings().encryption_key
    if key:
        # Derive 32-byte key from provided secret
        return base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
    # Development fallback — production warning handled by config validation
    get_logger(__name__).debug(
        "Using default encryption key (set DRYADE_ENCRYPTION_KEY for production)"
    )
    return base64.urlsafe_b64encode(hashlib.sha256(b"dev-key-change-me").digest())

def encrypt_key(plaintext: str) -> str:
    """Encrypt an API key for storage."""
    f = Fernet(get_encryption_key())
    return f.encrypt(plaintext.encode()).decode()

def decrypt_key(ciphertext: str) -> str:
    """Decrypt a stored API key."""
    f = Fernet(get_encryption_key())
    return f.decrypt(ciphertext.encode()).decode()

def get_key_prefix(key: str, length: int = 4) -> str:
    """Extract display prefix from API key (e.g., 'sk-a...')."""
    return key[:length] + "..." if len(key) > length else key
