"""End-to-end tests for the authentication flow.

Tests registration, login, token refresh, and error handling through the
real FastAPI auth endpoints. Auth middleware is disabled (DRYADE_AUTH_ENABLED=false)
but the auth *service* (register/login/refresh) is fully exercised.

Note: These tests require ``argon2-cffi`` for password hashing.  When the
library is not installed the auth service returns 500, so we skip
gracefully.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.e2e

try:
    import argon2  # noqa: F401

    _HAS_ARGON2 = True
except ImportError:
    _HAS_ARGON2 = False

_skip_no_argon2 = pytest.mark.skipif(
    not _HAS_ARGON2,
    reason="argon2-cffi not installed – auth service cannot hash passwords",
)

def _unique_email() -> str:
    """Generate a unique email address to avoid cross-test collisions."""
    return f"e2e-{uuid.uuid4().hex[:12]}@test.dryade.ai"

# ---------------------------------------------------------------------------
# 1. Register a brand-new user
# ---------------------------------------------------------------------------

@_skip_no_argon2
def test_register_new_user(integration_test_app):
    """Register a new user and verify the token response shape."""
    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        email = _unique_email()
        resp = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "SecurePass123!",
                "display_name": "E2E Tester",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert isinstance(body["expires_in"], int)
        assert body["expires_in"] > 0

# ---------------------------------------------------------------------------
# 2. Login with a previously registered user
# ---------------------------------------------------------------------------

@_skip_no_argon2
def test_login_registered_user(integration_test_app):
    """Register a user, then login with the same credentials."""
    email = _unique_email()
    password = "LoginPass456!"

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        # Register first
        reg_resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "display_name": "Login User"},
        )
        assert reg_resp.status_code == 200, reg_resp.text

        # Now login
        login_resp = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert login_resp.status_code == 200, login_resp.text
        body = login_resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert isinstance(body["expires_in"], int)
        assert body["expires_in"] > 0

        # Verify login returned its own valid token set
        # Note: tokens may be identical if issued in the same second (same iat claim),
        # so we only verify the login response shape, not uniqueness.
        assert body["access_token"]
        assert body["refresh_token"]

# ---------------------------------------------------------------------------
# 3. Login with wrong password
# ---------------------------------------------------------------------------

@_skip_no_argon2
def test_login_wrong_password(integration_test_app):
    """Attempt login with incorrect password and expect an error."""
    email = _unique_email()
    correct_password = "CorrectHorse99!"
    wrong_password = "TotallyWrong00!"

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        # Register the user
        reg_resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": correct_password},
        )
        assert reg_resp.status_code == 200, reg_resp.text

        # Login with wrong password
        login_resp = client.post(
            "/api/auth/login",
            json={"email": email, "password": wrong_password},
        )
        assert login_resp.status_code in (400, 401)
        error_body = login_resp.json()
        assert "detail" in error_body

# ---------------------------------------------------------------------------
# 4. Refresh token flow
# ---------------------------------------------------------------------------

@_skip_no_argon2
def test_refresh_token(integration_test_app):
    """Register, obtain a refresh token, then exchange it for new tokens."""
    email = _unique_email()

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        # Register to get initial tokens
        reg_resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": "RefreshMe789!"},
        )
        assert reg_resp.status_code == 200, reg_resp.text
        initial_tokens = reg_resp.json()

        # Use the refresh token to obtain new tokens
        refresh_resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": initial_tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 200, refresh_resp.text
        new_tokens = refresh_resp.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"
        assert isinstance(new_tokens["expires_in"], int)

        # Verify refresh returned its own valid token set
        # Note: tokens may be identical if issued in the same second (same iat claim),
        # so we only verify the refresh response shape, not uniqueness.
        assert new_tokens["access_token"]
        assert new_tokens["refresh_token"]

# ---------------------------------------------------------------------------
# 5. Duplicate registration
# ---------------------------------------------------------------------------

@_skip_no_argon2
def test_duplicate_registration_fails(integration_test_app):
    """Registering the same email twice should fail."""
    email = _unique_email()
    payload = {"email": email, "password": "DupeCheck321!", "display_name": "First"}

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        first_resp = client.post("/api/auth/register", json=payload)
        assert first_resp.status_code == 200, first_resp.text

        # Second registration with the same email
        second_resp = client.post("/api/auth/register", json=payload)
        assert second_resp.status_code == 400
        error_body = second_resp.json()
        assert "detail" in error_body
        assert "already" in error_body["detail"].lower()

# ---------------------------------------------------------------------------
# 6. Auth service rejects nonexistent user (wrong credentials)
# ---------------------------------------------------------------------------

@_skip_no_argon2
def test_protected_endpoint_without_auth(integration_test_app):
    """Verify the auth service returns proper errors for nonexistent users.

    Since auth middleware is disabled in the test environment, we cannot
    test middleware-level token enforcement. Instead we verify the auth
    *service* itself correctly rejects invalid credentials by attempting
    to login with a user that was never registered.
    """
    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/api/auth/login",
            json={
                "email": f"nonexistent-{uuid.uuid4().hex[:8]}@example.com",
                "password": "DoesNotMatter1!",
            },
        )
        assert resp.status_code == 401
        error_body = resp.json()
        assert "detail" in error_body
        assert "invalid" in error_body["detail"].lower()

# ---------------------------------------------------------------------------
# 7. Profile access with authenticated client
# ---------------------------------------------------------------------------

def test_profile_access_with_auth(e2e_client, integration_test_app, db_session):
    """Access the /api/users/me endpoint using the authenticated e2e_client.

    The e2e_client has get_current_user overridden to return a synthetic
    user dict. We insert a matching User row into the in-memory DB so the
    profile endpoint can find it.
    """
    from core.database.models import User

    user_id = "test-user-e2e"
    email = "e2e@example.com"

    # Ensure the user row exists in the test database
    existing = db_session.query(User).filter(User.id == user_id).first()
    if not existing:
        user = User(
            id=user_id,
            email=email,
            display_name="E2E Test User",
            role="user",
            is_external=False,
        )
        db_session.add(user)
        db_session.commit()

    resp = e2e_client.get("/api/users/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == user_id
    assert body["email"] == email
    assert body["role"] == "user"
    assert "is_active" in body
    assert "display_name" in body
