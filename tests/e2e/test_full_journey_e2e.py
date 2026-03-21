"""E2E test for the complete user journey.

Tests the end-to-end flow:
  1. Register a new user account
  2. Login with registered credentials
  3. List available plugins
  4. Create a conversation
  5. Add a message to the conversation
  6. List conversations and verify the new one appears
  7. Check system metrics (latency and queue)
  8. Delete the conversation

This covers the core user journey: signup -> configure -> chat -> verify.

Auth notes: these tests use two modes:
  - Integration test app (TestClient with overridden auth dependency)
  - Registration/login tests exercise the auth service directly
"""

import uuid
from unittest.mock import patch

import pytest

from core.extensions.events import ChatEvent

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_email() -> str:
    """Generate a unique email address to avoid test collisions."""
    return f"journey-{uuid.uuid4().hex[:12]}@example.com"

try:
    import argon2  # noqa: F401

    _HAS_ARGON2 = True
except ImportError:
    _HAS_ARGON2 = False

_skip_no_argon2 = pytest.mark.skipif(
    not _HAS_ARGON2,
    reason="argon2-cffi not installed — auth service cannot hash passwords",
)

def _async_gen_for_message():
    """Create an async-generator mock for route_request (chat endpoint)."""

    async def _fake_route(message, **kwargs):
        yield ChatEvent(
            type="complete",
            content=f"Journey mock response to: {message[:50]}",
            metadata={"mode": "chat"},
        )

    return _fake_route

# ---------------------------------------------------------------------------
# Full journey test
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestFullUserJourney:
    """End-to-end user journey: signup -> configure -> chat -> verify."""

    @_skip_no_argon2
    def test_register_and_login(self, integration_test_app):
        """Step 1-2: Register a new user, then login with the same credentials."""
        from fastapi.testclient import TestClient

        email = _unique_email()
        password = "JourneyTest123!"

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            # Step 1: Register
            reg_resp = client.post(
                "/api/auth/register",
                json={"email": email, "password": password, "display_name": "Journey User"},
            )
            assert reg_resp.status_code == 200, f"Register failed: {reg_resp.text}"
            tokens = reg_resp.json()
            assert "access_token" in tokens
            assert "refresh_token" in tokens

            # Step 2: Login
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
            login_tokens = login_resp.json()
            assert "access_token" in login_tokens

    def test_list_plugins(self, e2e_client):
        """Step 3: List available plugins after login."""
        resp = e2e_client.get("/api/plugins")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "plugins" in body
        assert "count" in body
        # count may be 0 in test environment — that's OK
        assert body["count"] >= 0

    def test_create_conversation(self, e2e_client):
        """Step 4: Create a new conversation."""
        resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Journey Test Conversation", "mode": "chat"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "id" in body
        assert body["title"] == "Journey Test Conversation"
        assert body["mode"] == "chat"
        assert body["status"] == "active"
        assert body["message_count"] == 0

    def test_create_then_list_conversations(self, e2e_client):
        """Step 4-6: Create a conversation and verify it appears in list."""
        # Create
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "List Verify Conversation", "mode": "chat"},
        )
        assert create_resp.status_code == 201, create_resp.text
        conv_id = create_resp.json()["id"]

        # List
        list_resp = e2e_client.get("/api/chat/conversations")
        assert list_resp.status_code == 200, list_resp.text
        conversations = list_resp.json()

        # The new conversation must appear
        conv_ids = [c["id"] for c in conversations.get("conversations", conversations)]
        assert conv_id in conv_ids, (
            f"Newly created conversation {conv_id} not found in list: {conv_ids}"
        )

    def test_add_message_to_conversation(self, e2e_client):
        """Step 5: Add a message to a conversation."""
        # First create a conversation
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Message Test Conversation", "mode": "chat"},
        )
        assert create_resp.status_code == 201, create_resp.text
        conv_id = create_resp.json()["id"]

        with patch(
            "core.api.routes.chat.route_request",
            new=_async_gen_for_message(),
        ):
            msg_resp = e2e_client.post(
                f"/api/chat/conversations/{conv_id}/messages",
                json={"content": "Hello, this is a journey test message!", "role": "user"},
            )
        # May return 201 (created) or stream response code
        assert msg_resp.status_code in (200, 201), (
            f"Add message failed: {msg_resp.status_code}: {msg_resp.text}"
        )

    def test_get_conversation_by_id(self, e2e_client):
        """Create a conversation, then retrieve it by ID."""
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Get By ID Conversation", "mode": "chat"},
        )
        assert create_resp.status_code == 201, create_resp.text
        conv_id = create_resp.json()["id"]

        get_resp = e2e_client.get(f"/api/chat/conversations/{conv_id}")
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["id"] == conv_id

    def test_delete_conversation(self, e2e_client):
        """Create then delete a conversation."""
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Delete Me Conversation", "mode": "chat"},
        )
        assert create_resp.status_code == 201, create_resp.text
        conv_id = create_resp.json()["id"]

        del_resp = e2e_client.delete(f"/api/chat/conversations/{conv_id}")
        assert del_resp.status_code in (200, 204), del_resp.text

        # Verify it's gone
        get_resp = e2e_client.get(f"/api/chat/conversations/{conv_id}")
        assert get_resp.status_code in (404, 410), (
            f"Deleted conversation still accessible: {get_resp.status_code}: {get_resp.text}"
        )

    def test_system_metrics_accessible(self, e2e_client):
        """Step 7: System metrics endpoint returns latency and queue stats."""
        latency_resp = e2e_client.get("/api/metrics/latency")
        assert latency_resp.status_code == 200, latency_resp.text
        latency_body = latency_resp.json()
        assert "avg_ms" in latency_body
        assert "total_requests" in latency_body

        queue_resp = e2e_client.get("/api/metrics/queue")
        assert queue_resp.status_code == 200, queue_resp.text
        queue_body = queue_resp.json()
        assert "active" in queue_body
        assert "queued" in queue_body

    def test_health_check_accessible(self, e2e_client):
        """Health endpoint returns 200 throughout the journey."""
        resp = e2e_client.get("/health")
        assert resp.status_code == 200, resp.text

# ---------------------------------------------------------------------------
# Journey invariants
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestJourneyInvariants:
    """Invariants that must hold throughout any user journey."""

    def test_health_check_never_fails(self, e2e_client):
        """Health endpoint is always accessible."""
        for _ in range(3):
            resp = e2e_client.get("/health")
            assert resp.status_code == 200

    def test_api_docs_accessible(self, e2e_client):
        """OpenAPI docs endpoint is accessible."""
        resp = e2e_client.get("/docs")
        assert resp.status_code == 200

    def test_providers_list_accessible(self, e2e_client):
        """Provider list is always accessible (no auth required for list)."""
        resp = e2e_client.get("/api/providers")
        assert resp.status_code == 200, resp.text
        providers = resp.json()
        assert isinstance(providers, list)
        assert len(providers) > 0, "Expected at least one provider in the registry"

    def test_models_config_accessible(self, e2e_client):
        """Model config endpoint is accessible."""
        resp = e2e_client.get("/api/models/config")
        assert resp.status_code == 200, resp.text
