"""MFA (TOTP) helper functions.

Uses pyotp for TOTP generation/verification and qrcode for QR code SVG output.
Recovery codes use passlib argon2 for hashing (already installed).

All functions are stateless — no DB access. AuthService calls these helpers.
"""

import io
import secrets

import pyotp
import qrcode
import qrcode.image.svg
from passlib.hash import argon2

def generate_totp_secret() -> str:
    """Generate a random base32 TOTP secret."""
    return pyotp.random_base32()

def generate_provisioning_uri(email: str, secret: str) -> str:
    """Generate otpauth:// URI for authenticator app enrollment."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name="Dryade")

def generate_qr_svg(provisioning_uri: str) -> str:
    """Generate QR code as SVG string from provisioning URI."""
    img = qrcode.make(provisioning_uri, image_factory=qrcode.image.svg.SvgImage)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue().decode("utf-8")

def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code with 1-window tolerance for clock drift (90s total)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)

def generate_recovery_codes(count: int = 8) -> list[str]:
    """Generate recovery codes in XXXX-XXXX-XXXX-XXXX format.

    Args:
        count: Number of codes to generate (default 8).

    Returns:
        List of plaintext recovery codes. Show to user once, then discard plaintext.
    """
    return [
        f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-"
        f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        for _ in range(count)
    ]

def hash_recovery_code(code: str) -> str:
    """Hash a recovery code with argon2 for storage. NOT SHA-256 — brute-force resistant."""
    return argon2.hash(code)

def verify_recovery_code(code: str, code_hash: str) -> bool:
    """Verify a recovery code against its argon2 hash."""
    return argon2.verify(code, code_hash)
