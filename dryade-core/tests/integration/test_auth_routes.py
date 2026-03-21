"""
Integration tests for authentication API routes.

Tests the /api/auth and /api/users endpoints.
Uses integration_test_app fixture which initializes the real in-memory DB
via init_db() so auth routes can interact with the users table directly.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from core.auth.dependencies import get_current_user

@pytest.fixture
def auth_client(integration_test_app):
    """Provide a test client WITHOUT auth bypass for testing auth endpoints.

    Auth routes (register, login, setup) are public and don't need auth override.
    This client uses the real DB created by integration_test_app.
    """
    # Clear any existing overrides so auth middleware processes requests naturally
    integration_test_app.dependency_overrides.pop(get_current_user, None)

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        yield client

    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def unique_email():
    """Generate a unique email for test isolation."""
    return f"test-{uuid.uuid4().hex[:8]}@example.com"

@pytest.mark.integration
class TestAuthRegister:
    """Tests for POST /api/auth/register."""

    def test_register_success(self, auth_client, unique_email):
        """Test successful user registration."""
        response = auth_client.post(
            "/api/auth/register",
            json={
                "email": unique_email,
                "password": "password123",
                "display_name": "New User",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, auth_client):
        """Test registration with duplicate email fails."""
        email = f"dup-{uuid.uuid4().hex[:8]}@example.com"

        # First registration
        auth_client.post("/api/auth/register", json={"email": email, "password": "password123"})

        # Second registration with same email
        response = auth_client.post(
            "/api/auth/register",
            json={"email": email, "password": "different123"},
        )

        assert response.status_code == 400

    def test_register_invalid_email(self, auth_client):
        """Test registration with invalid email format fails."""
        response = auth_client.post(
            "/api/auth/register", json={"email": "not-an-email", "password": "password123"}
        )

        assert response.status_code == 422  # Validation error

@pytest.mark.integration
class TestAuthLogin:
    """Tests for POST /api/auth/login."""

    def test_login_success(self, auth_client):
        """Test successful login."""
        email = f"login-{uuid.uuid4().hex[:8]}@example.com"

        # Register first
        auth_client.post("/api/auth/register", json={"email": email, "password": "password123"})

        # Login
        response = auth_client.post(
            "/api/auth/login", json={"email": email, "password": "password123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_wrong_password(self, auth_client):
        """Test login with wrong password fails."""
        email = f"wrongpw-{uuid.uuid4().hex[:8]}@example.com"

        # Register first
        auth_client.post("/api/auth/register", json={"email": email, "password": "password123"})

        # Login with wrong password
        response = auth_client.post(
            "/api/auth/login", json={"email": email, "password": "wrong_password"}
        )

        assert response.status_code == 401

    def test_login_nonexistent_user(self, auth_client):
        """Test login with nonexistent email fails."""
        response = auth_client.post(
            "/api/auth/login", json={"email": "nonexistent@example.com", "password": "password123"}
        )

        assert response.status_code == 401

@pytest.mark.integration
class TestAuthRefresh:
    """Tests for POST /api/auth/refresh."""

    def test_refresh_token_success(self, auth_client):
        """Test successful token refresh."""
        email = f"refresh-{uuid.uuid4().hex[:8]}@example.com"

        # Register and get tokens
        register_response = auth_client.post(
            "/api/auth/register", json={"email": email, "password": "password123"}
        )
        tokens = register_response.json()

        # Refresh
        response = auth_client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        assert response.status_code == 200
        new_tokens = response.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["token_type"] == "bearer"

    def test_refresh_invalid_token(self, auth_client):
        """Test refresh with invalid token fails."""
        response = auth_client.post("/api/auth/refresh", json={"refresh_token": "invalid_token"})

        assert response.status_code == 401

@pytest.mark.integration
class TestAuthSetup:
    """Tests for POST /api/auth/setup."""

    def test_setup_fails_when_users_exist(self, auth_client):
        """Test setup fails when users already exist.

        Note: We test the 'fail' case because setup only works when
        zero users exist, and other tests may have registered users.
        """
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"

        # Create a user first
        auth_client.post("/api/auth/register", json={"email": email, "password": "password123"})

        # Try to setup admin -- should fail because users exist
        response = auth_client.post(
            "/api/auth/setup", json={"email": "admin@example.com", "password": "admin_password123"}
        )

        assert response.status_code == 400

@pytest.mark.integration
class TestUserProfile:
    """Tests for /api/users/me endpoints."""

    def test_get_profile_authenticated(self, auth_client, integration_test_app):
        """Test getting profile when authenticated."""
        email = f"profile-{uuid.uuid4().hex[:8]}@example.com"

        # Register user in the DB
        register_response = auth_client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "password123",
                "display_name": "Profile User",
            },
        )
        tokens = register_response.json()

        # Decode the token to get the user ID (sub claim)
        import jwt as pyjwt

        from core.config import get_settings

        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )

        # Override get_current_user to return the registered user's info
        def override_user():
            return {"sub": payload["sub"], "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            response = client.get("/api/users/me")

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == email
        assert data["display_name"] == "Profile User"

    def test_get_profile_unauthenticated(self, auth_client):
        """Test getting profile without token fails."""
        response = auth_client.get("/api/users/me")

        # Should fail due to missing auth
        assert response.status_code == 401

    def test_update_profile(self, auth_client, integration_test_app):
        """Test updating user profile."""
        email = f"update-{uuid.uuid4().hex[:8]}@example.com"

        # Register user in the DB
        register_response = auth_client.post(
            "/api/auth/register", json={"email": email, "password": "password123"}
        )
        tokens = register_response.json()

        # Decode the token to get the user ID (sub claim)
        import jwt as pyjwt

        from core.config import get_settings

        payload = pyjwt.decode(
            tokens["access_token"], get_settings().jwt_secret, algorithms=["HS256"]
        )

        # Override get_current_user to return the registered user's info
        def override_user():
            return {"sub": payload["sub"], "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_user

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            response = client.patch(
                "/api/users/me",
                json={"display_name": "Updated Name", "preferences": {"theme": "dark"}},
            )

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["preferences"]["theme"] == "dark"

@pytest.mark.integration
class TestUserList:
    """Tests for GET /api/users (admin only)."""

    def test_list_users_as_admin(self, auth_client, integration_test_app):
        """Test listing users as admin."""
        # Register a user first (to make sure DB has at least one)
        email = f"admin-list-{uuid.uuid4().hex[:8]}@example.com"
        auth_client.post("/api/auth/register", json={"email": email, "password": "password123"})

        # Override get_current_user to simulate admin access
        def admin_override():
            return {"sub": "admin-user", "email": "admin@example.com", "role": "admin"}

        integration_test_app.dependency_overrides[get_current_user] = admin_override

        with TestClient(integration_test_app, raise_server_exceptions=False) as admin_client:
            # List users
            response = admin_client.get("/api/users")

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_users_as_member_forbidden(self, auth_client, integration_test_app):
        """Test listing users as regular member fails."""
        email = f"member-{uuid.uuid4().hex[:8]}@example.com"

        # Register regular user in the DB
        auth_client.post("/api/auth/register", json={"email": email, "password": "password123"})

        # Override get_current_user to return a member (non-admin) user
        def override_member():
            return {"sub": "member-user", "email": email, "role": "member"}

        integration_test_app.dependency_overrides[get_current_user] = override_member

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            response = client.get("/api/users")

        integration_test_app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 403
