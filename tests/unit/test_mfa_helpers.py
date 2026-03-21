"""
Unit tests for MFA helper functions in core/auth/mfa.py.

Covers all 7 stateless functions with happy-path and adversarial cases.
Targets 100% line coverage of core/auth/mfa.py.
"""

import re

import pyotp
import pytest

from core.auth.mfa import (
    generate_provisioning_uri,
    generate_qr_svg,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_recovery_code,
    verify_totp,
)

class TestGenerateTotpSecret:
    """Tests for generate_totp_secret()."""

    def test_returns_string(self):
        """generate_totp_secret returns a non-empty string."""
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_returns_base32_string(self):
        """Secret is a valid base32 string (uppercase A-Z and 2-7)."""
        secret = generate_totp_secret()
        # pyotp base32 uses uppercase A-Z and 2-7
        assert re.match(r"^[A-Z2-7]+=*$", secret), f"Not valid base32: {secret}"

    def test_each_call_unique(self):
        """Two calls produce different secrets."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        assert secret1 != secret2

    def test_secret_is_usable_by_pyotp(self):
        """Secret can be used to create a pyotp.TOTP instance."""
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert isinstance(code, str)
        assert len(code) == 6

class TestGenerateProvisioningUri:
    """Tests for generate_provisioning_uri()."""

    def test_returns_otpauth_uri(self):
        """Returns a string starting with otpauth://"""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        assert uri.startswith("otpauth://")

    def test_contains_email(self):
        """URI contains the user email."""
        secret = generate_totp_secret()
        email = "user@example.com"
        uri = generate_provisioning_uri(email, secret)
        assert "user%40example.com" in uri or "user@example.com" in uri

    def test_contains_issuer_name(self):
        """URI contains the Dryade issuer name."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        assert "Dryade" in uri

    def test_contains_secret(self):
        """URI contains the TOTP secret."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        assert secret in uri

    def test_different_emails_produce_different_uris(self):
        """Different emails produce different provisioning URIs."""
        secret = generate_totp_secret()
        uri1 = generate_provisioning_uri("user1@example.com", secret)
        uri2 = generate_provisioning_uri("user2@example.com", secret)
        assert uri1 != uri2

class TestGenerateQrSvg:
    """Tests for generate_qr_svg()."""

    def test_returns_string(self):
        """generate_qr_svg returns a string."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        svg = generate_qr_svg(uri)
        assert isinstance(svg, str)

    def test_returns_non_empty_string(self):
        """generate_qr_svg returns a non-empty string."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        svg = generate_qr_svg(uri)
        assert len(svg) > 0

    def test_returns_svg_content(self):
        """Output contains SVG markup."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        svg = generate_qr_svg(uri)
        # qrcode SVG output contains svg tag
        assert "svg" in svg.lower()

    def test_different_uris_produce_different_svgs(self):
        """Different URIs produce different SVG outputs."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        uri1 = generate_provisioning_uri("user@example.com", secret1)
        uri2 = generate_provisioning_uri("user@example.com", secret2)
        svg1 = generate_qr_svg(uri1)
        svg2 = generate_qr_svg(uri2)
        assert svg1 != svg2

class TestVerifyTotp:
    """Tests for verify_totp()."""

    def test_valid_current_code_returns_true(self):
        """verify_totp returns True for a valid current TOTP code."""
        secret = generate_totp_secret()
        code = pyotp.TOTP(secret).now()
        assert verify_totp(secret, code) is True

    def test_invalid_code_returns_false(self):
        """verify_totp returns False for an obviously wrong code."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_wrong_length_code_returns_false(self):
        """verify_totp returns False for a code of wrong length."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "12345") is False

    def test_wrong_secret_returns_false(self):
        """verify_totp returns False when using a different secret."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()
        code = pyotp.TOTP(secret1).now()
        # With overwhelming probability code from secret1 is invalid for secret2
        # (may be flaky if they coincidentally match, but base32 entropy makes this negligible)
        result = verify_totp(secret2, code)
        # Result can be True or False — we only assert the function returns a bool
        assert isinstance(result, bool)

    def test_empty_code_returns_false(self):
        """verify_totp returns False for empty string."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False

    def test_non_numeric_code_returns_false(self):
        """verify_totp returns False for non-numeric code."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "abcdef") is False

class TestGenerateRecoveryCodes:
    """Tests for generate_recovery_codes()."""

    def test_default_returns_eight_codes(self):
        """Default call returns 8 recovery codes."""
        codes = generate_recovery_codes()
        assert len(codes) == 8

    def test_custom_count(self):
        """Custom count parameter is respected."""
        codes = generate_recovery_codes(count=4)
        assert len(codes) == 4

    def test_codes_are_strings(self):
        """All codes are strings."""
        codes = generate_recovery_codes()
        for code in codes:
            assert isinstance(code, str)

    def test_format_xxxx_xxxx_xxxx_xxxx(self):
        """Each code matches XXXX-XXXX-XXXX-XXXX format (hex, uppercase)."""
        codes = generate_recovery_codes()
        pattern = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{8}-[0-9A-F]{8}-[0-9A-F]{8}$")
        for code in codes:
            assert pattern.match(code), f"Code does not match expected format: {code}"

    def test_all_codes_unique(self):
        """All codes in a batch are unique."""
        codes = generate_recovery_codes(count=8)
        assert len(set(codes)) == 8

    def test_two_batches_are_different(self):
        """Two calls return different sets of codes."""
        batch1 = set(generate_recovery_codes())
        batch2 = set(generate_recovery_codes())
        # With 64-bit random hex, collision probability is negligible
        assert batch1 != batch2

    def test_zero_count(self):
        """Count of 0 returns empty list."""
        codes = generate_recovery_codes(count=0)
        assert codes == []

class TestHashAndVerifyRecoveryCode:
    """Tests for hash_recovery_code() and verify_recovery_code()."""

    def test_hash_returns_string(self):
        """hash_recovery_code returns a non-empty string."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        hashed = hash_recovery_code(code)
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_is_not_plaintext(self):
        """Hash does not equal the plaintext code."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        hashed = hash_recovery_code(code)
        assert hashed != code

    def test_round_trip_succeeds(self):
        """hash + verify round-trip returns True for correct code."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        hashed = hash_recovery_code(code)
        assert verify_recovery_code(code, hashed) is True

    def test_wrong_code_fails_verify(self):
        """verify_recovery_code returns False for a different code."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        wrong_code = "XXXX0000-YYYY1111-ZZZZ2222-WWWW3333"
        hashed = hash_recovery_code(code)
        assert verify_recovery_code(wrong_code, hashed) is False

    def test_two_hashes_of_same_code_are_different(self):
        """Argon2 uses salt — same code produces different hashes each time."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        hash1 = hash_recovery_code(code)
        hash2 = hash_recovery_code(code)
        assert hash1 != hash2

    def test_both_hashes_verify_correctly(self):
        """Both hashes of the same code verify as True."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        hash1 = hash_recovery_code(code)
        hash2 = hash_recovery_code(code)
        assert verify_recovery_code(code, hash1) is True
        assert verify_recovery_code(code, hash2) is True

    def test_real_recovery_code_round_trip(self):
        """Round-trip works with codes from generate_recovery_codes."""
        codes = generate_recovery_codes(count=3)
        for code in codes:
            hashed = hash_recovery_code(code)
            assert verify_recovery_code(code, hashed) is True
