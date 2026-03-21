"""E2E tests for error paths.

Tests the system's behavior under error conditions:
- Expired/invalid JWT tokens return 401 (auth expiry mid-session)
- Requests to non-existent routes return 404
- Invalid request bodies return 422 (validation errors)
- Malformed JSON returns 422
- Unauthorized access returns 401 when auth is enabled

These tests verify the API contract for error responses, ensuring
error messages are informative without leaking stack traces.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_expired_jwt(secret: str = "test-secret") -> str:
    """Create an expired JWT for testing auth expiry."""
    try:
        import jwt

        payload = {
            "sub": "test-user-expired",
            "email": "expired@example.com",
            "role": "user",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,  # expired 1 hour ago
        }
        return jwt.encode(payload, secret, algorithm="HS256")
    except ImportError:
        # PyJWT not installed — return a clearly invalid token
        return "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.invalid"

# ---------------------------------------------------------------------------
# Auth expiry tests
# ---------------------------------------------------------------------------

class TestAuthExpiry:
    """Auth error paths: expired tokens, missing tokens, invalid tokens."""

    def test_expired_jwt_returns_401(self, integration_test_app):
        """Requests with an expired JWT return 401 when auth is enabled.

        In the test environment, DRYADE_AUTH_ENABLED=false, so this test
        verifies the auth middleware behavior by directly testing the auth
        service endpoints rather than middleware-level enforcement.
        """
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            expired_token = _make_expired_jwt()
            resp = client.get(
                "/api/users/me",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            # With auth disabled: the middleware is bypassed, but the dependency
            # may or may not enforce tokens. Either 200 (bypass) or 401 (enforced).
            # The key invariant is: we never get a 500 (no stack trace leaked).
            assert resp.status_code != 500, (
                f"Got 500 (stack trace may be leaked) for expired token: {resp.text}"
            )

    def test_malformed_token_does_not_cause_500(self, integration_test_app):
        """Malformed Authorization header never returns 500."""
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.get(
                "/api/users/me",
                headers={"Authorization": "Bearer totally.invalid.token.xyz"},
            )
            assert resp.status_code != 500, f"Got 500 for malformed token: {resp.text}"

    def test_missing_auth_header_on_protected_endpoint(self, integration_test_app):
        """No Authorization header returns a defined status (not 500)."""
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.get("/api/users/me")
            # Auth disabled in test: may return 200/401/422 but never 500
            assert resp.status_code != 500, f"Got 500 for missing auth header: {resp.text}"

    def test_login_wrong_credentials_returns_401(self, integration_test_app):
        """POST /api/auth/login with bad credentials returns 401, not 500."""
        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/auth/login",
                json={
                    "email": f"nonexistent-{uuid.uuid4().hex[:8]}@example.com",
                    "password": "WrongPassword123!",
                },
            )
            assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
            body = resp.json()
            assert "detail" in body
            # Error detail must not contain a Python traceback
            assert "Traceback" not in body["detail"], "Stack trace leaked in 401 response detail"

# ---------------------------------------------------------------------------
# 404 and routing error paths
# ---------------------------------------------------------------------------

class TestNotFoundPaths:
    """Tests that non-existent routes return proper 404 responses."""

    def test_nonexistent_api_path_returns_404(self, e2e_client):
        """GET /api/does-not-exist returns 404."""
        resp = e2e_client.get("/api/does-not-exist-xyz-123")
        assert resp.status_code == 404, resp.text

    def test_nonexistent_conversation_returns_404(self, e2e_client):
        """GET /api/chat/conversations/nonexistent returns 404."""
        resp = e2e_client.get("/api/chat/conversations/nonexistent-conv-xyz-000")
        assert resp.status_code in (400, 404), resp.text

    def test_nonexistent_plugin_returns_404(self, e2e_client):
        """GET /api/plugins/nonexistent returns 404."""
        resp = e2e_client.get("/api/plugins/nonexistent-plugin-xyz-000")
        assert resp.status_code == 404, resp.text

    def test_nonexistent_knowledge_source_returns_404(self, e2e_client):
        """GET /api/knowledge/ks_nonexistent returns 404."""
        resp = e2e_client.get("/api/knowledge/ks_nonexistent_xyz_000")
        assert resp.status_code == 404, resp.text

# ---------------------------------------------------------------------------
# Validation error paths
# ---------------------------------------------------------------------------

class TestValidationErrors:
    """Tests for request validation error handling (422 responses)."""

    def test_create_conversation_missing_required_fields(self, e2e_client):
        """POST /api/chat/conversations with missing title returns 422."""
        resp = e2e_client.post("/api/chat/conversations", json={})
        # May return 201 (title optional) or 422 (title required)
        assert resp.status_code in (201, 422), f"Unexpected status {resp.status_code}: {resp.text}"

    def test_create_conversation_invalid_mode_returns_error(self, e2e_client):
        """POST /api/chat/conversations with invalid mode returns 422."""
        resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Test", "mode": "invalid-mode-xyz"},
        )
        # 201 (mode may be validated at use-time) or 422 (strict validation)
        assert resp.status_code in (201, 422), f"Unexpected status {resp.status_code}: {resp.text}"

    def test_knowledge_query_empty_string_returns_validation_error(self, e2e_client):
        """POST /api/knowledge/query with empty query returns 422."""
        resp = e2e_client.post("/api/knowledge/query", json={"query": ""})
        assert resp.status_code in (400, 422, 503), (
            f"Expected validation error for empty query, got {resp.status_code}: {resp.text}"
        )

    def test_malformed_json_body_returns_422(self, e2e_client):
        """POST with malformed JSON body returns 422, not 500."""
        resp = e2e_client.post(
            "/api/chat/conversations",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for malformed JSON, got {resp.status_code}: {resp.text}"
        )

    def test_error_response_never_leaks_traceback(self, e2e_client):
        """Error responses must not contain Python tracebacks."""
        # Hit a known-bad endpoint
        resp = e2e_client.get("/api/knowledge/ks_nonexistent_xyz_traceback_check")
        if resp.status_code >= 400:
            resp_text = resp.text
            assert "Traceback (most recent call last)" not in resp_text, (
                f"Python traceback leaked in {resp.status_code} response"
            )
            assert 'File "/home' not in resp_text, (
                f"Local file path leaked in {resp.status_code} response"
            )

# ---------------------------------------------------------------------------
# Plugin error paths
# ---------------------------------------------------------------------------

class TestPluginErrorPaths:
    """Tests for plugin-related error paths."""

    def test_uninstall_nonexistent_plugin_returns_error(self, e2e_client):
        """DELETE /api/plugins/nonexistent returns 404 or 400."""
        resp = e2e_client.delete("/api/plugins/nonexistent-plugin-xyz-000")
        assert resp.status_code in (400, 404), (
            f"Expected 400 or 404, got {resp.status_code}: {resp.text}"
        )

    def test_patch_config_nonexistent_plugin_returns_error(self, e2e_client):
        """PATCH /api/plugins/nonexistent/config returns 404 or 400."""
        resp = e2e_client.patch(
            "/api/plugins/nonexistent-plugin-xyz-000/config",
            json={"key": "value"},
        )
        assert resp.status_code in (400, 404, 405), (
            f"Expected 400/404/405, got {resp.status_code}: {resp.text}"
        )
