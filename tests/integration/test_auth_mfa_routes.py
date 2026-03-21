"""
Integration tests for MFA API routes.

Tests the /api/auth/mfa/* endpoints using the integration_test_app fixture.
Covers: setup, verify (confirm setup), validate (login TOTP), recovery, disable.

Route prefix is determined by how mfa router is mounted — actual paths are
/api/auth/mfa/setup, /api/auth/mfa/verify, /api/auth/mfa/validate,
/api/auth/mfa/recovery, /api/auth/mfa/disable.
"""

import uuid
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, email=None, password="password123"):
    """Register a new user and return the tokens."""
    if email is None:
        email = f"mfa-test-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/api/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    return email, resp.json()

def _auth_headers(tokens):
    """Build Authorization header dict from token response."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}

def _get_mfa_prefix(integration_test_app):
    """Discover the actual MFA route prefix by inspecting registered routes."""
    for route in integration_test_app.routes:
        if hasattr(route, "path") and "mfa" in route.path and "setup" in route.path:
            # e.g. /api/auth/mfa/setup → prefix is /api/auth/mfa
            return route.path.replace("/setup", "")
    # Default fallback
    return "/api/auth/mfa"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_client_no_override(integration_test_app):
    """Client with real auth processing (no get_current_user override)."""
    from core.auth.dependencies import get_current_user

    integration_test_app.dependency_overrides.pop(get_current_user, None)
    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        yield client
    integration_test_app.dependency_overrides.clear()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestMFASetupRoute:
    """Tests for POST /api/auth/mfa/setup."""

    def test_setup_unauthenticated_returns_401(self, integration_test_app):
        """Unauthenticated request to /setup returns 401."""
        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/setup")

        integration_test_app.dependency_overrides.clear()
        assert resp.status_code == 401

    def test_setup_authenticated_returns_setup_data(self, integration_test_app):
        """Authenticated user gets MFA setup data with qr_code, secret, recovery_codes."""
        from core.auth.dependencies import get_current_user

        # Register a user to get a real DB user ID
        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-setup-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        # Decode token to get user sub
        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]

        # Override get_current_user to return this real user
        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/setup")

        integration_test_app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert "qr_code" in data
        assert "secret" in data
        assert "recovery_codes" in data
        assert len(data["recovery_codes"]) == 8

    def test_setup_twice_returns_400(self, integration_test_app):
        """Calling /setup when MFA is already enabled returns 400."""
        from core.auth.dependencies import get_current_user

        # Register user
        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-setup-dup-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            # First setup
            setup_resp = client.post("/api/auth/mfa/setup")
            assert setup_resp.status_code == 200
            secret = setup_resp.json()["secret"]

            # Confirm setup to actually enable MFA
            valid_code = pyotp.TOTP(secret).now()
            client.post("/api/auth/mfa/verify", json={"code": valid_code})

            # Try to setup again — MFA already enabled
            dup_resp = client.post("/api/auth/mfa/setup")

        integration_test_app.dependency_overrides.clear()

        assert dup_resp.status_code == 400

@pytest.mark.integration
class TestMFAVerifySetupRoute:
    """Tests for POST /api/auth/mfa/verify (confirm MFA setup)."""

    def _setup_mfa_for_user(self, integration_test_app, user_sub, email):
        """Helper: run /setup for the given user and return the secret."""
        from core.auth.dependencies import get_current_user

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/setup")

        integration_test_app.dependency_overrides.clear()
        assert resp.status_code == 200
        return resp.json()["secret"]

    def test_verify_valid_code_enables_mfa(self, integration_test_app):
        """POST /verify with a valid TOTP code enables MFA and returns tokens."""
        from core.auth.dependencies import get_current_user

        # Register user
        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-verify-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]
        secret = self._setup_mfa_for_user(integration_test_app, user_sub, email)

        # Verify with valid code
        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            valid_code = pyotp.TOTP(secret).now()
            resp = client.post("/api/auth/mfa/verify", json={"code": valid_code})

        integration_test_app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_verify_invalid_code_returns_400(self, integration_test_app):
        """POST /verify with invalid TOTP code returns 400."""
        from core.auth.dependencies import get_current_user

        # Register user
        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-verify-bad-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]
        self._setup_mfa_for_user(integration_test_app, user_sub, email)

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/verify", json={"code": "000000"})

        integration_test_app.dependency_overrides.clear()

        assert resp.status_code == 400

@pytest.mark.integration
class TestMFAValidateRoute:
    """Tests for POST /api/auth/mfa/validate (TOTP during login)."""

    def _register_and_enable_mfa(self, integration_test_app):
        """Register user, enable MFA, return (user_id, email, secret)."""
        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-validate-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            setup_resp = client.post("/api/auth/mfa/setup")
            assert setup_resp.status_code == 200
            secret = setup_resp.json()["secret"]
            valid_code = pyotp.TOTP(secret).now()
            verify_resp = client.post("/api/auth/mfa/verify", json={"code": valid_code})
            assert verify_resp.status_code == 200

        integration_test_app.dependency_overrides.clear()
        return user_sub, email, secret

    def test_validate_valid_code_returns_tokens(self, integration_test_app):
        """POST /validate with valid TOTP returns full tokens."""
        user_sub, email, secret = self._register_and_enable_mfa(integration_test_app)

        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            valid_code = pyotp.TOTP(secret).now()
            resp = client.post(
                "/api/auth/mfa/validate",
                json={"user_id": user_sub, "code": valid_code},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_validate_invalid_code_returns_401(self, integration_test_app):
        """POST /validate with invalid code returns 401."""
        user_sub, email, secret = self._register_and_enable_mfa(integration_test_app)

        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/auth/mfa/validate",
                json={"user_id": user_sub, "code": "000000"},
            )

        assert resp.status_code == 401

    def test_validate_nonexistent_user_returns_404(self, integration_test_app):
        """POST /validate for non-existent user_id returns 404."""
        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/auth/mfa/validate",
                json={"user_id": "nonexistent-user-id", "code": "123456"},
            )

        assert resp.status_code in (401, 404)

@pytest.mark.integration
class TestMFARecoveryRoute:
    """Tests for POST /api/auth/mfa/recovery."""

    def _register_and_enable_mfa(self, integration_test_app):
        """Register user, enable MFA, return (user_id, email, secret, recovery_codes)."""
        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-recovery-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            setup_resp = client.post("/api/auth/mfa/setup")
            assert setup_resp.status_code == 200
            secret = setup_resp.json()["secret"]
            recovery_codes = setup_resp.json()["recovery_codes"]
            valid_code = pyotp.TOTP(secret).now()
            verify_resp = client.post("/api/auth/mfa/verify", json={"code": valid_code})
            assert verify_resp.status_code == 200

        integration_test_app.dependency_overrides.clear()
        return user_sub, email, secret, recovery_codes

    def test_recovery_valid_code_returns_tokens(self, integration_test_app):
        """POST /recovery with valid recovery code returns tokens."""
        user_sub, email, secret, recovery_codes = self._register_and_enable_mfa(
            integration_test_app
        )

        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/auth/mfa/recovery",
                json={"user_id": user_sub, "recovery_code": recovery_codes[0]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_recovery_invalid_code_returns_401(self, integration_test_app):
        """POST /recovery with invalid code returns 401."""
        user_sub, email, secret, recovery_codes = self._register_and_enable_mfa(
            integration_test_app
        )

        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/auth/mfa/recovery",
                json={
                    "user_id": user_sub,
                    "recovery_code": "XXXX0000-YYYY1111-ZZZZ2222-WWWW3333",
                },
            )

        assert resp.status_code == 401

    def test_recovery_used_code_returns_401(self, integration_test_app):
        """POST /recovery with already-used recovery code returns 401."""
        user_sub, email, secret, recovery_codes = self._register_and_enable_mfa(
            integration_test_app
        )

        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            # Use code once
            first_resp = client.post(
                "/api/auth/mfa/recovery",
                json={"user_id": user_sub, "recovery_code": recovery_codes[1]},
            )
            assert first_resp.status_code == 200

            # Try to use same code again
            second_resp = client.post(
                "/api/auth/mfa/recovery",
                json={"user_id": user_sub, "recovery_code": recovery_codes[1]},
            )

        assert second_resp.status_code == 401

@pytest.mark.integration
class TestMFADisableRoute:
    """Tests for POST /api/auth/mfa/disable."""

    def _register_and_enable_mfa(self, integration_test_app):
        """Register user, enable MFA, return (user_id, email)."""
        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            email = f"mfa-disable-{uuid.uuid4().hex[:8]}@example.com"
            reg_resp = client.post(
                "/api/auth/register", json={"email": email, "password": "password123"}
            )
        assert reg_resp.status_code == 200

        import jwt as pyjwt

        from core.config import get_settings

        tokens = reg_resp.json()
        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )
        user_sub = payload["sub"]

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            setup_resp = client.post("/api/auth/mfa/setup")
            assert setup_resp.status_code == 200
            secret = setup_resp.json()["secret"]
            valid_code = pyotp.TOTP(secret).now()
            verify_resp = client.post("/api/auth/mfa/verify", json={"code": valid_code})
            assert verify_resp.status_code == 200

        integration_test_app.dependency_overrides.clear()
        return user_sub, email

    def test_disable_mfa_authenticated_correct_password(self, integration_test_app):
        """POST /disable with correct password disables MFA."""
        user_sub, email = self._register_and_enable_mfa(integration_test_app)

        from core.auth.dependencies import get_current_user

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/disable", json={"password": "password123"})

        integration_test_app.dependency_overrides.clear()

        assert resp.status_code == 200

    def test_disable_mfa_wrong_password_returns_400(self, integration_test_app):
        """POST /disable with wrong password returns 400 (ValueError -> 400)."""
        user_sub, email = self._register_and_enable_mfa(integration_test_app)

        from core.auth.dependencies import get_current_user

        def override_user():
            return {"sub": user_sub, "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/disable", json={"password": "wrong_password"})

        integration_test_app.dependency_overrides.clear()

        assert resp.status_code == 400

    def test_disable_mfa_unauthenticated_returns_401(self, integration_test_app):
        """POST /disable without auth header returns 401."""
        from core.auth.dependencies import get_current_user

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post("/api/auth/mfa/disable", json={"password": "password123"})

        assert resp.status_code == 401
