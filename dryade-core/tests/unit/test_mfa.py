"""Unit tests for MFA (TOTP) authentication.

Tests cover:
- MFA helper functions (mfa.py)
- AuthService MFA methods
- MFA API routes
- Grace period middleware
- Recovery code consumption
- Refresh token bypass prevention
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.auth.mfa import (
    generate_provisioning_uri,
    generate_qr_svg,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_recovery_code,
    verify_totp,
)
from core.auth.service import AuthService
from core.database.models import MFARecoveryCode, User

# =============================================================================
# MFA Helper Function Tests
# =============================================================================

class TestMFAHelpers:
    """Tests for pure TOTP helper functions in core/auth/mfa.py."""

    def test_generate_totp_secret_is_base32(self):
        """Secret is a non-empty base32 string."""
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) >= 16  # pyotp default is 32 chars base32

    def test_generate_totp_secret_unique(self):
        """Each generated secret is unique."""
        s1 = generate_totp_secret()
        s2 = generate_totp_secret()
        assert s1 != s2

    def test_generate_provisioning_uri_format(self):
        """URI starts with otpauth:// and contains issuer=Dryade."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        assert uri.startswith("otpauth://totp/")
        assert "Dryade" in uri
        assert "user%40example.com" in uri or "user@example.com" in uri

    def test_generate_qr_svg_is_valid_svg(self):
        """QR code output is a valid SVG string."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri("user@example.com", secret)
        svg = generate_qr_svg(uri)
        assert isinstance(svg, str)
        assert "<svg" in svg.lower() or "<?xml" in svg.lower()

    def test_verify_totp_valid_code(self):
        """Valid current TOTP code is accepted."""
        secret = generate_totp_secret()
        current_code = pyotp.TOTP(secret).now()
        assert verify_totp(secret, current_code) is True

    def test_verify_totp_invalid_code(self):
        """Invalid TOTP code is rejected."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_verify_totp_wrong_length(self):
        """Code with wrong number of digits is rejected."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "12345") is False  # 5 digits
        assert verify_totp(secret, "1234567") is False  # 7 digits

    def test_verify_totp_empty_code(self):
        """Empty TOTP code is rejected."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False

    def test_generate_recovery_codes_count(self):
        """Generates exactly the requested number of recovery codes."""
        codes = generate_recovery_codes(8)
        assert len(codes) == 8

    def test_generate_recovery_codes_custom_count(self):
        """Custom count is respected."""
        codes = generate_recovery_codes(4)
        assert len(codes) == 4

    def test_generate_recovery_codes_format(self):
        """Codes are in XXXX-XXXX-XXXX-XXXX format."""
        codes = generate_recovery_codes(8)
        for code in codes:
            parts = code.split("-")
            assert len(parts) == 4, f"Code {code!r} does not have 4 parts"
            for part in parts:
                assert len(part) == 8, f"Part {part!r} is not 8 chars"
                assert all(c in "0123456789ABCDEF" for c in part), f"Part {part!r} not hex"

    def test_generate_recovery_codes_uniqueness(self):
        """All codes in a batch are unique."""
        codes = generate_recovery_codes(8)
        assert len(set(codes)) == 8

    def test_hash_and_verify_recovery_code(self):
        """Hashed recovery code verifies correctly."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        code_hash = hash_recovery_code(code)
        assert isinstance(code_hash, str)
        assert len(code_hash) > 0
        assert verify_recovery_code(code, code_hash) is True

    def test_recovery_code_wrong_code_fails(self):
        """Wrong recovery code does not verify against a hash."""
        code = "ABCD1234-EFGH5678-IJKL9012-MNOP3456"
        code_hash = hash_recovery_code(code)
        assert verify_recovery_code("WRONG-RECOVERY-CODE-VALUE", code_hash) is False

    def test_hash_different_codes_produce_different_hashes(self):
        """Different codes produce different argon2 hashes."""
        code1 = "AAAA1111-BBBB2222-CCCC3333-DDDD4444"
        code2 = "EEEE5555-FFFF6666-GGGG7777-HHHH8888"
        hash1 = hash_recovery_code(code1)
        hash2 = hash_recovery_code(code2)
        assert hash1 != hash2

# =============================================================================
# AuthService MFA Method Tests
# =============================================================================

class TestAuthServiceMFA:
    """Tests for MFA methods on AuthService."""

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_returns_qr_and_codes(self, mock_settings, db_session):
        """setup_mfa returns qr_code, secret, and 8 recovery_codes."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        # Create a user
        auth = AuthService(db_session)
        user = auth.register("mfa@example.com", "password123", "MFA User")

        # Setup MFA
        result = auth.setup_mfa(user.id)

        assert "qr_code" in result
        assert "secret" in result
        assert "recovery_codes" in result
        assert "<svg" in result["qr_code"].lower() or "<?xml" in result["qr_code"].lower()
        assert len(result["secret"]) >= 16
        assert len(result["recovery_codes"]) == 8

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_fails_if_already_enabled(self, mock_settings, db_session):
        """setup_mfa raises ValueError if MFA already active."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa2@example.com", "password123")
        user.mfa_enabled = True
        db_session.commit()

        with pytest.raises(ValueError, match="already enabled"):
            auth.setup_mfa(user.id)

    @patch("core.auth.service.get_settings")
    def test_setup_mfa_user_not_found(self, mock_settings, db_session):
        """setup_mfa raises HTTPException 404 for unknown user."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            auth.setup_mfa("nonexistent-user-id")
        assert exc_info.value.status_code == 404

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_setup_activates_mfa(self, mock_settings, db_session):
        """verify_mfa_setup sets mfa_enabled=True and mfa_enabled_at."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("verify@example.com", "password123")
        auth.setup_mfa(user.id)

        # Reload user to get totp_secret
        db_session.refresh(user)
        valid_code = pyotp.TOTP(user.totp_secret).now()

        tokens = auth.verify_mfa_setup(user.id, valid_code)

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        db_session.refresh(user)
        assert user.mfa_enabled is True
        assert user.mfa_enabled_at is not None

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_setup_invalid_code(self, mock_settings, db_session):
        """verify_mfa_setup raises ValueError for bad code."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("verify2@example.com", "password123")
        auth.setup_mfa(user.id)

        with pytest.raises(ValueError, match="invalid_totp_code"):
            auth.verify_mfa_setup(user.id, "000000")

    @patch("core.auth.service.get_settings")
    def test_verify_mfa_at_login(self, mock_settings, db_session):
        """verify_mfa returns tokens for valid code during login."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("login_mfa@example.com", "password123")
        auth.setup_mfa(user.id)

        # Activate MFA
        db_session.refresh(user)
        setup_code = pyotp.TOTP(user.totp_secret).now()
        auth.verify_mfa_setup(user.id, setup_code)

        # Re-generate valid code (time may have advanced)
        db_session.refresh(user)
        login_code = pyotp.TOTP(user.totp_secret).now()
        tokens = auth.verify_mfa(user.id, login_code)

        assert "access_token" in tokens
        assert "refresh_token" in tokens

    @patch("core.auth.service.get_settings")
    def test_use_recovery_code_marks_used(self, mock_settings, db_session):
        """Recovery code sets used_at, returns tokens."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("recovery@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        recovery_code = setup_result["recovery_codes"][0]

        # Enable MFA first
        db_session.refresh(user)
        code = pyotp.TOTP(user.totp_secret).now()
        auth.verify_mfa_setup(user.id, code)

        tokens = auth.use_recovery_code(user.id, recovery_code)
        assert "access_token" in tokens

        # Verify the code is marked as used
        used = (
            db_session.query(MFARecoveryCode)
            .filter(
                MFARecoveryCode.user_id == user.id,
                MFARecoveryCode.used_at.isnot(None),
            )
            .count()
        )
        assert used == 1

    @patch("core.auth.service.get_settings")
    def test_use_recovery_code_replay_fails(self, mock_settings, db_session):
        """Same recovery code cannot be used twice."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("replay@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        recovery_code = setup_result["recovery_codes"][0]

        # Enable MFA first
        db_session.refresh(user)
        code = pyotp.TOTP(user.totp_secret).now()
        auth.verify_mfa_setup(user.id, code)

        # First use — should succeed
        auth.use_recovery_code(user.id, recovery_code)

        # Second use — should fail
        with pytest.raises(ValueError, match="invalid_recovery_code"):
            auth.use_recovery_code(user.id, recovery_code)

    @patch("core.auth.service.get_settings")
    def test_disable_mfa_requires_password(self, mock_settings, db_session):
        """disable_mfa raises ValueError for wrong password."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("disable@example.com", "password123")

        with pytest.raises(ValueError, match="invalid_password"):
            auth.disable_mfa(user.id, "wrong_password")

    @patch("core.auth.service.get_settings")
    def test_disable_mfa_clears_totp_and_codes(self, mock_settings, db_session):
        """After disable, totp_secret is None, recovery codes deleted."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("disable2@example.com", "password123")
        auth.setup_mfa(user.id)

        # Enable MFA
        db_session.refresh(user)
        code = pyotp.TOTP(user.totp_secret).now()
        auth.verify_mfa_setup(user.id, code)

        # Disable MFA
        auth.disable_mfa(user.id, "password123")

        db_session.refresh(user)
        assert user.totp_secret is None
        assert user.mfa_enabled is False
        assert user.mfa_enabled_at is None

        code_count = (
            db_session.query(MFARecoveryCode).filter(MFARecoveryCode.user_id == user.id).count()
        )
        assert code_count == 0

    @patch("core.auth.service.get_settings")
    def test_authenticate_with_mfa_returns_challenge(self, mock_settings, db_session):
        """authenticate_with_mfa_check returns mfa_required for MFA users."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("mfa_challenge@example.com", "password123")
        auth.setup_mfa(user.id)

        # Activate MFA
        db_session.refresh(user)
        code = pyotp.TOTP(user.totp_secret).now()
        auth.verify_mfa_setup(user.id, code)

        # Login should return MFA challenge
        result = auth.authenticate_with_mfa_check("mfa_challenge@example.com", "password123")
        assert isinstance(result, dict)
        assert result.get("mfa_required") is True
        assert "mfa_user_id" in result

    @patch("core.auth.service.get_settings")
    def test_authenticate_without_mfa_returns_user(self, mock_settings, db_session):
        """authenticate_with_mfa_check returns User for non-MFA users."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        auth.register("no_mfa@example.com", "password123")

        result = auth.authenticate_with_mfa_check("no_mfa@example.com", "password123")
        # Should return a User object (no mfa_required key)
        assert hasattr(result, "email"), "Expected User object"
        assert result.email == "no_mfa@example.com"

    @patch("core.auth.service.get_settings")
    def test_refresh_token_blocked_if_pre_mfa(self, mock_settings, db_session):
        """Refresh token issued before MFA enabled is rejected."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("refresh_mfa@example.com", "password123")

        # Get refresh token before MFA
        tokens_before = auth.create_tokens(user)

        # Enable MFA with a future timestamp (ensure it's after token iat)
        # Token iat is in seconds (integer from JWT), so set mfa_enabled_at
        # to 2 seconds after the token was issued
        user.mfa_enabled = True
        user.mfa_enabled_at = datetime.now(UTC) + timedelta(seconds=2)
        db_session.commit()

        # Old refresh token should be rejected
        with pytest.raises(HTTPException) as exc_info:
            auth.refresh_access_token(tokens_before["refresh_token"])
        assert exc_info.value.status_code == 401
        assert "before MFA" in exc_info.value.detail

    @patch("core.auth.service.get_settings")
    def test_regenerate_recovery_codes_replaces_old(self, mock_settings, db_session):
        """regenerate_recovery_codes deletes old codes and creates 8 new ones."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("regen@example.com", "password123")
        setup_result = auth.setup_mfa(user.id)
        old_codes = setup_result["recovery_codes"]

        # Enable MFA
        db_session.refresh(user)
        code = pyotp.TOTP(user.totp_secret).now()
        auth.verify_mfa_setup(user.id, code)

        new_codes = auth.regenerate_recovery_codes(user.id)

        assert len(new_codes) == 8
        # New codes should be different from old ones
        assert set(new_codes) != set(old_codes)

    @patch("core.auth.service.get_settings")
    def test_regenerate_codes_fails_if_mfa_not_enabled(self, mock_settings, db_session):
        """regenerate_recovery_codes raises ValueError if MFA is not enabled."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        auth = AuthService(db_session)
        user = auth.register("noregen@example.com", "password123")

        with pytest.raises(ValueError, match="not enabled"):
            auth.regenerate_recovery_codes(user.id)

# =============================================================================
# MFA Grace Period / Middleware Tests
# =============================================================================

class TestMFAGracePeriod:
    """Tests for MFA enforcement via middleware logic."""

    @pytest.fixture(autouse=True)
    def patch_auth_middleware_settings(self):
        """Patch get_settings in auth middleware to avoid JWT secret validation errors.

        AuthMiddleware.__init__ calls get_settings() at construction time. Tests
        that construct AuthMiddleware without a valid DRYADE_JWT_SECRET env var
        would fail before the test body runs. This fixture provides a safe mock.
        """
        from unittest.mock import MagicMock, patch

        mock_settings = MagicMock()
        mock_settings.auth_enabled = True
        mock_settings.mfa_enforcement_enabled = False
        with patch("core.api.middleware.auth.get_settings", return_value=mock_settings):
            yield

    def test_enforcement_disabled_skips_check(self):
        """When enforcement is off, _check_mfa_enforcement returns None immediately."""
        import asyncio

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)

        # Override settings to have enforcement disabled
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = False

        mock_request = MagicMock()

        result = asyncio.run(middleware._check_mfa_enforcement(mock_request, {"sub": "user-123"}))
        assert result is None

    def test_mfa_routes_exempt_from_enforcement(self):
        """Requests to /api/auth/mfa/* are never blocked."""
        import asyncio

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/auth/mfa/setup"

        result = asyncio.run(middleware._check_mfa_enforcement(mock_request, {"sub": "user-123"}))
        assert result is None

    def test_login_route_exempt_from_enforcement(self):
        """Login route is exempt from MFA grace period enforcement."""
        import asyncio

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/auth/login"

        result = asyncio.run(middleware._check_mfa_enforcement(mock_request, {"sub": "user-123"}))
        assert result is None

    def test_no_sub_skips_enforcement(self):
        """Missing sub in payload skips enforcement check."""
        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/chat/send"

        import asyncio

        result = asyncio.run(middleware._check_mfa_enforcement(mock_request, {}))
        assert result is None

    @patch("core.auth.service.get_settings")
    def test_external_users_exempt_from_mfa(self, mock_settings, db_session):
        """SSO users (is_external=True) skip MFA enforcement."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        # Create external user
        external_user = User(
            id="ext-user-001",
            email="sso@external.com",
            is_external=True,
            is_active=True,
            role="member",
        )
        db_session.add(external_user)
        db_session.commit()

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/chat/send"

        # Patch get_session at the database.session module level (lazy import location)
        with patch("core.database.session.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            import asyncio

            result = asyncio.new_event_loop().run_until_complete(
                middleware._check_mfa_enforcement(mock_request, {"sub": "ext-user-001"})
            )
        assert result is None

    @patch("core.auth.service.get_settings")
    def test_mfa_enabled_user_passes(self, mock_settings, db_session):
        """Users with mfa_enabled=True are not blocked."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        # Create MFA-enabled user
        mfa_user = User(
            id="mfa-user-001",
            email="mfa@enabled.com",
            is_external=False,
            is_active=True,
            mfa_enabled=True,
            role="member",
        )
        db_session.add(mfa_user)
        db_session.commit()

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/chat/send"

        with patch("core.database.session.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            import asyncio

            result = asyncio.new_event_loop().run_until_complete(
                middleware._check_mfa_enforcement(mock_request, {"sub": "mfa-user-001"})
            )
        assert result is None

    @patch("core.auth.service.get_settings")
    def test_grace_deadline_set_on_first_check(self, mock_settings, db_session):
        """First enforcement check sets mfa_grace_deadline = now + 14 days."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        # User without any MFA and without grace deadline
        new_user = User(
            id="new-user-001",
            email="newbie@example.com",
            is_external=False,
            is_active=True,
            mfa_enabled=False,
            mfa_grace_deadline=None,
            role="member",
            password_hash="hashed",
        )
        db_session.add(new_user)
        db_session.commit()

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/chat/send"

        before = datetime.now(UTC)
        with patch("core.database.session.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            import asyncio

            result = asyncio.new_event_loop().run_until_complete(
                middleware._check_mfa_enforcement(mock_request, {"sub": "new-user-001"})
            )

        # First check — deadline set, user not blocked
        assert result is None
        db_session.refresh(new_user)
        assert new_user.mfa_grace_deadline is not None
        # Deadline should be ~14 days from now
        expected_min = before + timedelta(days=13, hours=23)
        expected_max = before + timedelta(days=14, hours=1)
        # Handle timezone-naive datetimes
        deadline = new_user.mfa_grace_deadline
        if deadline.tzinfo is None:
            from datetime import timezone

            deadline = deadline.replace(tzinfo=timezone.utc)
        assert deadline >= expected_min
        assert deadline <= expected_max

    @patch("core.auth.service.get_settings")
    def test_grace_period_expired_returns_403(self, mock_settings, db_session):
        """Users past grace deadline get 403 with mfa_required detail."""
        mock_settings.return_value.jwt_secret = "test_secret_key_at_least_32_chars_long"

        # User with expired grace deadline
        expired_user = User(
            id="expired-user-001",
            email="expired@example.com",
            is_external=False,
            is_active=True,
            mfa_enabled=False,
            mfa_grace_deadline=datetime.now(UTC) - timedelta(days=1),  # Yesterday
            role="member",
            password_hash="hashed",
        )
        db_session.add(expired_user)
        db_session.commit()

        from core.api.middleware.auth import AuthMiddleware

        mock_app = MagicMock()
        middleware = AuthMiddleware(mock_app)
        middleware.settings = MagicMock()
        middleware.settings.mfa_enforcement_enabled = True

        mock_request = MagicMock()
        mock_request.url.path = "/api/chat/send"

        with patch("core.database.session.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=db_session)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            import asyncio

            result = asyncio.new_event_loop().run_until_complete(
                middleware._check_mfa_enforcement(mock_request, {"sub": "expired-user-001"})
            )

        # Should be a 403 response
        assert result is not None
        assert result.status_code == 403

# =============================================================================
# MFA API Route Tests (integration-style with TestClient)
# =============================================================================

class TestMFARoutes:
    """Integration tests for MFA API routes."""

    def test_mfa_routes_imported_correctly(self):
        """MFA router has expected routes."""
        from core.api.routes.mfa import router

        paths = [r.path for r in router.routes]
        assert "/setup" in paths
        assert "/verify" in paths
        assert "/validate" in paths
        assert "/recovery" in paths
        assert "/disable" in paths
        assert "/recovery-codes" in paths

    def test_mfa_setup_requires_auth(self):
        """POST /api/auth/mfa/setup requires authentication."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/auth/mfa/setup")
        # Should fail auth (401) since no token provided
        assert response.status_code in (401, 422)  # 422 if no auth header at all

    def test_mfa_validate_no_auth_required(self):
        """POST /api/auth/mfa/validate does NOT require Authorization header."""
        from core.api.routes.mfa import router

        # /validate should not have get_current_user dependency
        validate_routes = [r for r in router.routes if hasattr(r, "path") and r.path == "/validate"]
        assert len(validate_routes) == 1
        # Verify by checking dependencies don't include get_current_user
        # (it accepts user_id in body instead)
        route = validate_routes[0]
        dep_names = [
            d.dependency.__name__ for d in route.dependencies if hasattr(d.dependency, "__name__")
        ]
        assert "get_current_user" not in dep_names
