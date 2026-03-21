"""
Integration tests for Zitadel SSO endpoints.

These tests require Zitadel to be running and configured.
They are skipped by default when ZITADEL_ENABLED is not set.

To run these tests:
1. Start Zitadel: cd docker/zitadel && docker compose up -d
2. Configure Dryade: Set DRYADE_ZITADEL_* variables
3. Run: pytest tests/integration/test_zitadel_sso.py -v
"""

import os

import pytest

# Skip all tests in this module if Zitadel not configured
pytestmark = pytest.mark.skipif(
    os.getenv("DRYADE_ZITADEL_ENABLED", "").lower() != "true",
    reason="Zitadel not configured (DRYADE_ZITADEL_ENABLED != true)",
)

@pytest.fixture
def client():
    """Create test client with app."""
    from core.api.app import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    return TestClient(app)

class TestSSOProviders:
    """Tests for /auth/sso/providers endpoint."""

    def test_sso_providers_returns_list(self, client):
        """SSO providers endpoint should return provider list."""
        response = client.get("/api/v1/auth/sso/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) > 0

    def test_sso_providers_includes_google(self, client):
        """SSO providers should include Google."""
        response = client.get("/api/v1/auth/sso/providers")

        data = response.json()
        provider_ids = [p["id"] for p in data["providers"]]
        assert "google" in provider_ids

class TestSSOLogin:
    """Tests for /auth/sso/login/{provider} endpoint."""

    def test_sso_login_returns_url(self, client):
        """SSO login should return Zitadel login URL."""
        response = client.get("/api/v1/auth/sso/login/google")

        assert response.status_code == 200
        data = response.json()
        assert "login_url" in data
        assert "oauth" in data["login_url"].lower() or "authorize" in data["login_url"].lower()

    def test_sso_login_invalid_provider(self, client):
        """SSO login should reject invalid provider."""
        response = client.get("/api/v1/auth/sso/login/invalid-provider")

        assert response.status_code == 400
        assert "Invalid provider" in response.json()["detail"]

class TestSSOStatus:
    """Tests for /auth/sso/status endpoint."""

    def test_sso_status_returns_enabled(self, client):
        """SSO status should show enabled when configured."""
        response = client.get("/api/v1/auth/sso/status")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert data["enabled"] is True

class TestSSOCallback:
    """Tests for /auth/sso/callback endpoint."""

    def test_sso_callback_requires_auth(self, client):
        """SSO callback should require authentication."""
        response = client.post("/api/v1/auth/sso/callback")

        # Should fail without valid Zitadel token
        assert response.status_code in [401, 403]

@pytest.mark.skip(reason="Requires actual Zitadel user flow")
class TestEndToEndSSOFlow:
    """End-to-end SSO flow tests (manual/interactive)."""

    def test_complete_sso_flow(self, client):
        """
        Complete SSO flow test.

        This test requires manual interaction:
        1. Get login URL
        2. Authenticate with provider
        3. Handle callback
        4. Verify tokens
        """
        # Step 1: Get login URL
        response = client.get("/api/v1/auth/sso/login/google")
        assert response.status_code == 200
        # login_url would be used for manual navigation in step 2
        _ = response.json()["login_url"]

        # Step 2: Manual - user navigates to login_url and authenticates
        # This cannot be automated without browser automation

        # Step 3: Callback would be called by Zitadel
        # Step 4: Verify tokens returned

        pytest.skip("Requires manual authentication")
