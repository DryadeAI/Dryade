"""End-to-end tests for conversation sharing (share / unshare CRUD).

Tests the PATCH /api/chat/conversations/{id}/share and
DELETE /api/chat/conversations/{id}/share/{user_id} endpoints,
verifying ownership checks, permission levels, and idempotency.
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.e2e

# User IDs that match the e2e conftest fixtures
OWNER_ID = "test-user-e2e"
SECOND_USER_ID = "test-user-e2e-2"

def _create_conversation(client, title: str = "Sharing test") -> str:
    """Helper: create a conversation and return its ID."""
    resp = client.post(
        "/api/chat/conversations",
        json={"title": title, "mode": "chat"},
    )
    assert resp.status_code == 201, f"Failed to create conversation: {resp.text}"
    return resp.json()["id"]

class TestConversationSharing:
    """E2E tests for conversation sharing endpoints."""

    # ------------------------------------------------------------------
    # 1. Basic share
    # ------------------------------------------------------------------
    def test_share_conversation_with_user(self, e2e_client):
        """Owner shares a conversation with a second user and receives a
        success message."""
        conv_id = _create_conversation(e2e_client)

        resp = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": SECOND_USER_ID, "permission": "view"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert "shared" in body["message"].lower() or "success" in body["message"].lower()

    # ------------------------------------------------------------------
    # 2. Share creates a record (verified via re-share returning
    #    "already shared" message)
    # ------------------------------------------------------------------
    def test_shared_user_record_exists(self, e2e_client):
        """After sharing, sharing again with the same permission returns an
        'already shared' acknowledgement, proving the record was persisted."""
        conv_id = _create_conversation(e2e_client)

        # First share
        resp1 = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": SECOND_USER_ID, "permission": "view"},
        )
        assert resp1.status_code == 200

        # Second share (same user, same permission) - should be idempotent
        resp2 = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": SECOND_USER_ID, "permission": "view"},
        )
        assert resp2.status_code == 200
        body = resp2.json()
        assert "already" in body["message"].lower()

    # ------------------------------------------------------------------
    # 3. Unshare
    # ------------------------------------------------------------------
    def test_unshare_conversation(self, e2e_client):
        """Owner shares, then unshares, and receives appropriate messages."""
        conv_id = _create_conversation(e2e_client)

        # Share first
        share_resp = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": SECOND_USER_ID, "permission": "view"},
        )
        assert share_resp.status_code == 200

        # Unshare
        unshare_resp = e2e_client.delete(
            f"/api/chat/conversations/{conv_id}/share/{SECOND_USER_ID}",
        )
        assert unshare_resp.status_code == 200
        body = unshare_resp.json()
        assert "unshared" in body["message"].lower() or "success" in body["message"].lower()

    # ------------------------------------------------------------------
    # 4. Non-owner cannot share
    # ------------------------------------------------------------------
    def test_non_owner_cannot_share(self, integration_test_app):
        """A user who does not own the conversation gets 403 when trying
        to share it.

        Strategy: create the conversation as the owner, then switch the
        app's auth override to the second user and attempt the share.
        We use explicit override switching on a single TestClient to
        avoid the shared dependency_overrides issue between fixtures.
        """
        from core.auth.dependencies import get_current_user

        # Step 1: authenticate as owner and create a conversation
        def _owner_override():
            return {"sub": OWNER_ID, "email": "e2e@example.com", "role": "user"}

        integration_test_app.dependency_overrides[get_current_user] = _owner_override

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            conv_id = _create_conversation(client)

            # Step 2: switch to second user identity
            def _second_user_override():
                return {"sub": SECOND_USER_ID, "email": "e2e2@example.com", "role": "user"}

            integration_test_app.dependency_overrides[get_current_user] = _second_user_override

            resp = client.patch(
                f"/api/chat/conversations/{conv_id}/share",
                json={"user_id": "some-other-user", "permission": "view"},
            )

            assert resp.status_code == 403
            assert "owner" in resp.json()["detail"].lower()

        integration_test_app.dependency_overrides.clear()

    # ------------------------------------------------------------------
    # 5. Share with different permissions (update)
    # ------------------------------------------------------------------
    def test_share_with_different_permissions(self, e2e_client):
        """Sharing the same user twice with a different permission level
        updates the existing record and returns an 'updated' message."""
        conv_id = _create_conversation(e2e_client)

        # Share with "view"
        resp_view = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": SECOND_USER_ID, "permission": "view"},
        )
        assert resp_view.status_code == 200

        # Re-share with "edit" - should update permission
        resp_edit = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": SECOND_USER_ID, "permission": "edit"},
        )
        assert resp_edit.status_code == 200
        body = resp_edit.json()
        assert "updated" in body["message"].lower()
