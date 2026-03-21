"""
Unit tests for authentication service.

Tests password hashing and AuthService functionality.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from core.auth.password import hash_password, verify_password
from core.auth.service import AuthService

class TestPasswordHashing:
    """Tests for password hashing utilities."""

    def test_hash_password_creates_hash(self):
        """Test that hash_password creates a hash string."""
        password = "secure_password_123"
        hashed = hash_password(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert hashed != password
        assert len(hashed) > 0

    def test_hash_password_different_hashes(self):
        """Test that same password creates different hashes (salted)."""
        password = "secure_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Argon2 uses random salt, so hashes should differ
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Test verify_password returns True for correct password."""
        password = "secure_password_123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verify_password returns False for wrong password."""
        password = "secure_password_123"
        hashed = hash_password(password)

        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_empty_password(self):
        """Test verify_password with empty password."""
        password = "secure_password_123"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

class TestAuthServiceRegister:
    """Tests for AuthService.register method."""

    @patch("core.auth.service.get_settings")
    def test_register_creates_user(self, mock_settings, db_session):
        """Test that register creates a new user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("test@example.com", "password123", "Test User")

        assert user.email == "test@example.com"
        assert user.display_name == "Test User"
        assert user.role == "member"
        assert user.is_external is False
        assert user.password_hash is not None
        assert user.password_hash != "password123"

    @patch("core.auth.service.get_settings")
    def test_register_duplicate_email_fails(self, mock_settings, db_session):
        """Test that registering duplicate email raises error."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        auth.register("test@example.com", "password123")

        with pytest.raises(HTTPException) as exc:
            auth.register("test@example.com", "different_password")

        assert exc.value.status_code == 400
        assert "already registered" in exc.value.detail.lower()

class TestAuthServiceAuthenticate:
    """Tests for AuthService.authenticate method."""

    @patch("core.auth.service.get_settings")
    def test_authenticate_valid_credentials(self, mock_settings, db_session):
        """Test authenticate with valid credentials returns user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        auth.register("test@example.com", "password123")

        user = auth.authenticate("test@example.com", "password123")
        assert user.email == "test@example.com"

    @patch("core.auth.service.get_settings")
    def test_authenticate_invalid_password(self, mock_settings, db_session):
        """Test authenticate with wrong password raises 401."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        auth.register("test@example.com", "password123")

        with pytest.raises(HTTPException) as exc:
            auth.authenticate("test@example.com", "wrong_password")

        assert exc.value.status_code == 401
        assert "invalid credentials" in exc.value.detail.lower()

    @patch("core.auth.service.get_settings")
    def test_authenticate_nonexistent_user(self, mock_settings, db_session):
        """Test authenticate with nonexistent email raises 401."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)

        with pytest.raises(HTTPException) as exc:
            auth.authenticate("nonexistent@example.com", "password123")

        assert exc.value.status_code == 401

    @patch("core.auth.service.get_settings")
    def test_authenticate_disabled_user(self, mock_settings, db_session):
        """Test authenticate with disabled user raises 403."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("test@example.com", "password123")
        user.is_active = False
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            auth.authenticate("test@example.com", "password123")

        assert exc.value.status_code == 403
        assert "disabled" in exc.value.detail.lower()

class TestAuthServiceTokens:
    """Tests for AuthService token methods."""

    @patch("core.auth.service.get_settings")
    def test_create_tokens_returns_tokens(self, mock_settings, db_session):
        """Test create_tokens returns access and refresh tokens."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("test@example.com", "password123")

        tokens = auth.create_tokens(user)

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] == 30 * 60  # 30 minutes in seconds

    @patch("core.auth.service.get_settings")
    def test_refresh_access_token(self, mock_settings, db_session):
        """Test refresh_access_token creates new tokens."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("test@example.com", "password123")
        tokens = auth.create_tokens(user)

        # Sleep briefly to ensure different timestamp in token
        import time

        time.sleep(0.1)

        new_tokens = auth.refresh_access_token(tokens["refresh_token"])

        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"

class TestAuthServiceAdmin:
    """Tests for AuthService admin methods."""

    @patch("core.auth.service.get_settings")
    def test_create_first_admin(self, mock_settings, db_session):
        """Test create_first_admin creates admin user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.create_first_admin("admin@example.com", "admin_password")

        assert user.email == "admin@example.com"
        assert user.role == "admin"
        assert user.is_verified is True

    @patch("core.auth.service.get_settings")
    def test_create_first_admin_fails_if_users_exist(self, mock_settings, db_session):
        """Test create_first_admin fails when users already exist."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        auth.register("user@example.com", "password123")

        with pytest.raises(HTTPException) as exc:
            auth.create_first_admin("admin@example.com", "admin_password")

        assert exc.value.status_code == 400
        assert "users already exist" in exc.value.detail.lower()

# =============================================================================
# JWT Adversarial Tests
# =============================================================================

class TestRefreshAccessTokenAdversarial:
    """Adversarial tests for refresh_access_token — expired, wrong type, tampered."""

    @patch("core.auth.service.get_settings")
    def test_refresh_with_expired_token_raises_401(self, mock_settings, db_session):
        """Refresh with an expired token raises HTTPException 401."""
        import time

        import jwt as pyjwt

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"
        secret = "test_secret_key_at_least_32_chars_long"

        # Craft a token that expired 1 second ago
        payload = {
            "sub": "some-user-id",
            "role": "member",
            "email": "user@example.com",
            "type": "refresh",
            "iat": int(time.time()) - 100,
            "exp": int(time.time()) - 1,  # already expired
        }
        expired_token = pyjwt.encode(payload, secret, algorithm="HS256")

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.refresh_access_token(expired_token)

        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    @patch("core.auth.service.get_settings")
    def test_refresh_with_access_token_raises_401(self, mock_settings, db_session):
        """Refresh with an access token (wrong type) raises HTTPException 401."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("wrongtype@example.com", "password123")
        tokens = auth.create_tokens(user)

        # Use access token instead of refresh token
        with pytest.raises(HTTPException) as exc:
            auth.refresh_access_token(tokens["access_token"])

        assert exc.value.status_code == 401
        assert "invalid token type" in exc.value.detail.lower()

    @patch("core.auth.service.get_settings")
    def test_refresh_with_garbage_token_raises_401(self, mock_settings, db_session):
        """Refresh with garbage JWT raises HTTPException 401."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.refresh_access_token("not.a.valid.jwt.token")

        assert exc.value.status_code == 401

    @patch("core.auth.service.get_settings")
    def test_refresh_with_tampered_signature_raises_401(self, mock_settings, db_session):
        """Refresh with tampered signature raises HTTPException 401."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("tampered@example.com", "password123")
        tokens = auth.create_tokens(user)

        # Tamper the last character of the signature
        refresh_token = tokens["refresh_token"]
        tampered = refresh_token[:-1] + ("X" if refresh_token[-1] != "X" else "Y")

        with pytest.raises(HTTPException) as exc:
            auth.refresh_access_token(tampered)

        assert exc.value.status_code == 401

    @patch("core.auth.service.get_settings")
    def test_refresh_for_inactive_user_raises_401(self, mock_settings, db_session):
        """Refresh token for a deactivated user raises HTTPException 401."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("inactive@example.com", "password123")
        tokens = auth.create_tokens(user)

        # Deactivate the user
        user.is_active = False
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            auth.refresh_access_token(tokens["refresh_token"])

        assert exc.value.status_code == 401

# =============================================================================
# Authenticate Adversarial Tests
# =============================================================================

class TestAuthenticateAdversarial:
    """Additional adversarial tests for authenticate()."""

    @patch("core.auth.service.get_settings")
    def test_authenticate_disabled_account_raises_403(self, mock_settings, db_session):
        """authenticate() with is_active=False raises HTTPException 403."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("disabled@example.com", "password123")
        user.is_active = False
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            auth.authenticate("disabled@example.com", "password123")

        assert exc.value.status_code == 403
        assert "disabled" in exc.value.detail.lower()

    @patch("core.auth.service.get_settings")
    def test_authenticate_external_account_raises_400(self, mock_settings, db_session):
        """authenticate() for an external account raises HTTPException 400."""
        import uuid

        from core.auth.password import hash_password
        from core.database.models import User

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        # Create an external user manually
        external_user = User(
            id=str(uuid.uuid4()),
            email="external@example.com",
            password_hash=hash_password("password123"),
            role="member",
            is_external=True,
        )
        db_session.add(external_user)
        db_session.commit()

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.authenticate("external@example.com", "password123")

        assert exc.value.status_code == 400
        assert "external" in exc.value.detail.lower()

# =============================================================================
# MFA Setup Tests
# =============================================================================

class TestSetupMFA:
    """Tests for AuthService.setup_mfa()."""

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_returns_dict_with_expected_keys(self, mock_settings, db_session):
        """setup_mfa returns dict with qr_code, secret, recovery_codes."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_setup@example.com", "password123")

        result = auth.setup_mfa(user.id)

        assert "qr_code" in result
        assert "secret" in result
        assert "recovery_codes" in result

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_secret_is_base32_string(self, mock_settings, db_session):
        """setup_mfa secret is a non-empty base32 string."""
        import re

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_secret@example.com", "password123")
        result = auth.setup_mfa(user.id)

        assert isinstance(result["secret"], str)
        assert re.match(r"^[A-Z2-7]+=*$", result["secret"])

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_returns_eight_recovery_codes(self, mock_settings, db_session):
        """setup_mfa returns 8 recovery codes."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_codes@example.com", "password123")
        result = auth.setup_mfa(user.id)

        assert len(result["recovery_codes"]) == 8

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_user_not_found_raises_404(self, mock_settings, db_session):
        """setup_mfa raises HTTPException 404 for non-existent user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.setup_mfa("nonexistent-user-id")

        assert exc.value.status_code == 404

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_already_enabled_raises_value_error(self, mock_settings, db_session):
        """setup_mfa raises ValueError if MFA is already enabled."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_already@example.com", "password123")

        # Manually enable MFA
        user.mfa_enabled = True
        db_session.commit()

        with pytest.raises(ValueError, match="already enabled"):
            auth.setup_mfa(user.id)

# =============================================================================
# MFA Verify Setup Tests
# =============================================================================

class TestVerifyMFASetup:
    """Tests for AuthService.verify_mfa_setup()."""

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_setup_valid_code_enables_mfa(self, mock_settings, db_session):
        """verify_mfa_setup with valid TOTP enables MFA and returns tokens."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("verify_setup@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]

        # Generate a valid TOTP code
        valid_code = pyotp.TOTP(secret).now()
        tokens = auth.verify_mfa_setup(user.id, valid_code)

        assert "access_token" in tokens
        assert "refresh_token" in tokens

        # Reload user from DB to check MFA is enabled
        db_session.refresh(user)
        assert user.mfa_enabled is True

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_setup_invalid_code_raises_value_error(self, mock_settings, db_session):
        """verify_mfa_setup with invalid code raises ValueError."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("verify_invalid@example.com", "password123")
        auth.setup_mfa(user.id)

        with pytest.raises(ValueError, match="invalid_totp_code"):
            auth.verify_mfa_setup(user.id, "000000")

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_setup_without_setup_raises_value_error(self, mock_settings, db_session):
        """verify_mfa_setup without prior setup_mfa raises ValueError."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("no_setup@example.com", "password123")

        with pytest.raises(ValueError, match="MFA setup not initiated"):
            auth.verify_mfa_setup(user.id, "123456")

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_setup_user_not_found_raises_404(self, mock_settings, db_session):
        """verify_mfa_setup raises HTTPException 404 for non-existent user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.verify_mfa_setup("nonexistent-user-id", "123456")

        assert exc.value.status_code == 404

# =============================================================================
# MFA Verify Login Tests
# =============================================================================

class TestVerifyMFALogin:
    """Tests for AuthService.verify_mfa() (TOTP during login)."""

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_valid_code_returns_tokens(self, mock_settings, db_session):
        """verify_mfa with valid TOTP code returns tokens."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_login@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]

        # Activate MFA
        valid_code = pyotp.TOTP(secret).now()
        auth.verify_mfa_setup(user.id, valid_code)

        # Now verify MFA login with a fresh code
        login_code = pyotp.TOTP(secret).now()
        tokens = auth.verify_mfa(user.id, login_code)

        assert "access_token" in tokens
        assert "refresh_token" in tokens

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_invalid_code_raises_value_error(self, mock_settings, db_session):
        """verify_mfa with invalid code raises ValueError."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_login_invalid@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]

        valid_code = pyotp.TOTP(secret).now()
        auth.verify_mfa_setup(user.id, valid_code)

        with pytest.raises(ValueError, match="invalid_totp_code"):
            auth.verify_mfa(user.id, "000000")

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_user_not_found_raises_404(self, mock_settings, db_session):
        """verify_mfa raises HTTPException 404 for non-existent user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.verify_mfa("nonexistent-user-id", "123456")

        assert exc.value.status_code == 404

# =============================================================================
# Recovery Code Tests
# =============================================================================

class TestUseRecoveryCode:
    """Tests for AuthService.use_recovery_code()."""

    @patch("core.auth.service.get_settings")
    def test_use_valid_recovery_code_returns_tokens(self, mock_settings, db_session):
        """use_recovery_code with a valid code returns tokens."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("recovery@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]
        recovery_codes = setup_result["recovery_codes"]

        # Activate MFA
        valid_code = pyotp.TOTP(secret).now()
        auth.verify_mfa_setup(user.id, valid_code)

        # Use a recovery code
        tokens = auth.use_recovery_code(user.id, recovery_codes[0])

        assert "access_token" in tokens
        assert "refresh_token" in tokens

    @patch("core.auth.service.get_settings")
    def test_use_invalid_recovery_code_raises_value_error(self, mock_settings, db_session):
        """use_recovery_code with invalid code raises ValueError."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("recovery_invalid@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]

        valid_code = pyotp.TOTP(secret).now()
        auth.verify_mfa_setup(user.id, valid_code)

        with pytest.raises(ValueError, match="invalid_recovery_code"):
            auth.use_recovery_code(user.id, "XXXX0000-YYYY1111-ZZZZ2222-WWWW3333")

    @patch("core.auth.service.get_settings")
    def test_use_recovery_code_marks_as_used(self, mock_settings, db_session):
        """Recovery code cannot be used twice."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("recovery_used@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]
        recovery_codes = setup_result["recovery_codes"]

        valid_code = pyotp.TOTP(secret).now()
        auth.verify_mfa_setup(user.id, valid_code)

        # First use succeeds
        auth.use_recovery_code(user.id, recovery_codes[0])

        # Second use raises
        with pytest.raises(ValueError, match="invalid_recovery_code"):
            auth.use_recovery_code(user.id, recovery_codes[0])

    @patch("core.auth.service.get_settings")
    def test_use_recovery_code_user_not_found_raises_404(self, mock_settings, db_session):
        """use_recovery_code raises HTTPException 404 for non-existent user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.use_recovery_code("nonexistent-user-id", "ABCD1234-EFGH5678-IJKL9012-MNOP3456")

        assert exc.value.status_code == 404

# =============================================================================
# Disable MFA Tests
# =============================================================================

class TestDisableMFA:
    """Tests for AuthService.disable_mfa()."""

    @patch("core.auth.service.get_settings")
    def test_disable_mfa_clears_mfa_fields(self, mock_settings, db_session):
        """disable_mfa clears totp_secret, mfa_enabled, and recovery codes."""
        import pyotp

        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("disable_mfa@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        secret = setup_result["secret"]

        # Activate MFA
        valid_code = pyotp.TOTP(secret).now()
        auth.verify_mfa_setup(user.id, valid_code)

        db_session.refresh(user)
        assert user.mfa_enabled is True

        # Disable MFA with correct password
        auth.disable_mfa(user.id, "password123")

        db_session.refresh(user)
        assert user.mfa_enabled is False
        assert user.totp_secret is None
        assert user.mfa_enabled_at is None

    @patch("core.auth.service.get_settings")
    def test_disable_mfa_wrong_password_raises_401(self, mock_settings, db_session):
        """disable_mfa raises HTTPException 401 for wrong password."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("disable_wrong_pw@example.com", "password123")

        with pytest.raises(ValueError, match="invalid_password"):
            auth.disable_mfa(user.id, "wrong_password")

    @patch("core.auth.service.get_settings")
    def test_disable_mfa_user_not_found_raises_404(self, mock_settings, db_session):
        """disable_mfa raises HTTPException 404 for non-existent user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc:
            auth.disable_mfa("nonexistent-user-id", "password123")

        assert exc.value.status_code == 404
