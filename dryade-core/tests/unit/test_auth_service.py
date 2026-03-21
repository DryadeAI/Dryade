"""
Unit tests for authentication service.

Tests password hashing and AuthService functionality.
"""

from unittest.mock import MagicMock, patch

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

class TestCommunityAutoAdmin:
    """Tests for community auto-admin promotion in register()."""

    @patch("core.auth.service.get_allowlist_path")
    @patch("core.auth.service.get_settings")
    def test_community_auto_admin(self, mock_settings, mock_get_path, db_session):
        """First user registered with no allowlist file gets role=admin."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path

        auth = AuthService(db_session)
        user = auth.register("first@example.com", "password123", "First User")

        assert user.role == "admin"

    @patch("core.auth.service.get_allowlist_path")
    @patch("core.auth.service.get_settings")
    def test_register_with_allowlist_member(self, mock_settings, mock_get_path, db_session):
        """First user registered with allowlist file present gets role=member."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path

        auth = AuthService(db_session)
        user = auth.register("first@example.com", "password123", "First User")

        assert user.role == "member"

    @patch("core.auth.service.get_allowlist_path")
    @patch("core.auth.service.get_settings")
    def test_second_register_member(self, mock_settings, mock_get_path, db_session):
        """Second user registered with no allowlist gets role=member."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path

        auth = AuthService(db_session)
        # Create first user
        auth.register("first@example.com", "password123", "First User")
        # Register second user -- should be member even without allowlist
        user = auth.register("second@example.com", "password123", "Second User")

        assert user.role == "member"
