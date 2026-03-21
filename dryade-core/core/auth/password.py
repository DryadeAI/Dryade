"""Password hashing utilities using Argon2.

Argon2 is the winner of the Password Hashing Competition (PHC)
and is recommended for secure password storage due to:
- Memory-hard (resistant to GPU/ASIC attacks)
- Configurable time/memory/parallelism costs
- Side-channel resistant

Target: ~20 LOC
"""

from passlib.context import CryptContext

# Argon2 context with auto-upgrade for deprecated hashes
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using Argon2.

    Args:
        password: Plain text password

    Returns:
        Argon2 hash string
    """
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored Argon2 hash

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)
