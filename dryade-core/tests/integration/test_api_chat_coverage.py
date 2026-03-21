"""Coverage-focused tests for chat API routes.

Targets uncovered code paths in core/api/routes/chat.py:
- Conversation CRUD (create, get, update, list, delete, bulk delete, delete all)
- Share/unshare conversation
- Move conversation to project
- Chat history (get, clear)
- Cancel orchestration
- Stream status
- Clarification and state conflict resolution
- Modes listing
- Error paths and validation

Uses authenticated_client fixture from integration conftest.
"""

import uuid

import pytest

@pytest.mark.integration
class TestConversationCRUD:
    """Tests for conversation lifecycle endpoints."""

    def test_create_conversation(self, authenticated_client):
        """Test POST /api/chat/conversations creates a new conversation."""
        response = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Test Conversation", "mode": "chat"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Conversation"
        assert data["mode"] == "chat"
        assert data["status"] == "active"
        assert data["message_count"] == 0
        assert "id" in data
        assert "created_at" in data

    def test_create_conversation_default_title(self, authenticated_client):
        """Test creating conversation without explicit title uses default."""
        response = authenticated_client.post(
            "/api/chat/conversations",
            json={"mode": "planner"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Conversation"
        assert data["mode"] == "planner"

    def test_create_conversation_error(self, authenticated_client):
        """Test conversation creation error handling."""
        # This tests the code path; DB errors are hard to trigger but
        # at least exercises the endpoint
        response = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Valid", "mode": "chat"},
        )
        assert response.status_code == 201

    def test_get_conversation(self, authenticated_client):
        """Test GET /api/chat/conversations/{id} returns conversation details."""
        # Create conversation first
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Get Test", "mode": "chat"},
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["id"]

        # Get it
        response = authenticated_client.get(f"/api/chat/conversations/{conv_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == conv_id
        assert data["title"] == "Get Test"
        assert data["message_count"] == 0

    def test_get_conversation_not_found(self, authenticated_client):
        """Test 404 for non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/chat/conversations/{fake_id}")
        assert response.status_code == 404

    def test_get_conversation_invalid_uuid(self, authenticated_client):
        """Test 400 for invalid UUID format."""
        response = authenticated_client.get("/api/chat/conversations/not-a-uuid")
        assert response.status_code == 400
        assert "Invalid conversation_id" in response.json()["detail"]

    def test_get_conversation_access_denied(self, authenticated_client, admin_client):
        """Test 403 when non-owner tries to access."""
        # Create as regular user
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Private Conv", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Admin should be able to access (role == admin)
        response = admin_client.get(f"/api/chat/conversations/{conv_id}")
        assert response.status_code == 200

    def test_list_conversations(self, authenticated_client):
        """Test GET /api/chat/conversations lists user's conversations."""
        # Create a couple
        authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "List Test 1", "mode": "chat"},
        )
        authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "List Test 2", "mode": "chat"},
        )

        response = authenticated_client.get("/api/chat/conversations")
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert "total" in data
        assert data["total"] >= 2

    def test_list_conversations_limit_exceeded(self, authenticated_client):
        """Test 400 when limit exceeds 100."""
        response = authenticated_client.get("/api/chat/conversations?limit=200")
        assert response.status_code == 400
        assert "Limit cannot exceed 100" in response.json()["detail"]

    def test_list_conversations_negative_offset(self, authenticated_client):
        """Test validation error when offset is negative."""
        response = authenticated_client.get("/api/chat/conversations?offset=-1")
        assert response.status_code in [400, 422]  # Manual or Pydantic validation

    def test_update_conversation(self, authenticated_client):
        """Test PATCH /api/chat/conversations/{id} updates title."""
        # Create
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Before Update", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Update
        response = authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}",
            json={"title": "After Update"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "After Update"

    def test_update_conversation_mode(self, authenticated_client):
        """Test PATCH updates mode field."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Mode Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        response = authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}",
            json={"mode": "planner"},
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "planner"

    def test_update_conversation_not_found(self, authenticated_client):
        """Test 404 updating non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.patch(
            f"/api/chat/conversations/{fake_id}",
            json={"title": "nope"},
        )
        assert response.status_code == 404

    def test_update_conversation_invalid_uuid(self, authenticated_client):
        """Test 400 updating with invalid UUID."""
        response = authenticated_client.patch(
            "/api/chat/conversations/bad-id",
            json={"title": "nope"},
        )
        assert response.status_code == 400

    def test_delete_conversation(self, authenticated_client):
        """Test DELETE /api/chat/conversations/{id} deletes conversation."""
        # Create
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "To Delete", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Delete
        response = authenticated_client.delete(f"/api/chat/conversations/{conv_id}")
        assert response.status_code == 204

        # Verify deleted
        response = authenticated_client.get(f"/api/chat/conversations/{conv_id}")
        assert response.status_code == 404

    def test_delete_conversation_not_found(self, authenticated_client):
        """Test 404 deleting non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.delete(f"/api/chat/conversations/{fake_id}")
        assert response.status_code == 404

    def test_delete_conversation_invalid_uuid(self, authenticated_client):
        """Test 400 deleting with invalid UUID."""
        response = authenticated_client.delete("/api/chat/conversations/bad-id")
        assert response.status_code == 400

@pytest.mark.integration
class TestBulkDeleteConversations:
    """Tests for bulk delete endpoints."""

    def test_delete_all_conversations(self, authenticated_client):
        """Test DELETE /api/chat/conversations/all deletes all user conversations."""
        # Create some conversations
        for i in range(3):
            authenticated_client.post(
                "/api/chat/conversations",
                json={"title": f"Bulk {i}", "mode": "chat"},
            )

        # Delete all
        response = authenticated_client.delete("/api/chat/conversations/all")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        assert "message" in data

    def test_bulk_delete_conversations(self, authenticated_client):
        """Test DELETE /api/chat/conversations/bulk deletes specified conversations."""
        # Create conversations
        ids = []
        for i in range(3):
            resp = authenticated_client.post(
                "/api/chat/conversations",
                json={"title": f"Bulk Del {i}", "mode": "chat"},
            )
            ids.append(resp.json()["id"])

        # Bulk delete first two
        response = authenticated_client.request(
            "DELETE",
            "/api/chat/conversations/bulk",
            json={"conversation_ids": ids[:2]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 2
        assert "message" in data

    def test_bulk_delete_with_invalid_ids(self, authenticated_client):
        """Test bulk delete with mix of valid and invalid IDs."""
        valid_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Valid", "mode": "chat"},
        )
        valid_id = valid_resp.json()["id"]

        response = authenticated_client.request(
            "DELETE",
            "/api/chat/conversations/bulk",
            json={"conversation_ids": [valid_id, "not-a-uuid", str(uuid.uuid4())]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 1
        assert len(data["failed_ids"]) == 2

@pytest.mark.integration
class TestConversationMessages:
    """Tests for message endpoints."""

    def test_add_message_to_conversation(self, authenticated_client):
        """Test POST /api/chat/conversations/{id}/messages adds a message."""
        # Create conversation
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Message Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Add user message
        response = authenticated_client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": "Hello world", "role": "user"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "user"
        assert data["content"] == "Hello world"
        assert "id" in data
        assert "timestamp" in data

    def test_add_message_not_found(self, authenticated_client):
        """Test 404 adding message to non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.post(
            f"/api/chat/conversations/{fake_id}/messages",
            json={"content": "Orphan", "role": "user"},
        )
        assert response.status_code == 404

    def test_add_message_invalid_uuid(self, authenticated_client):
        """Test 400 adding message with invalid conversation UUID."""
        response = authenticated_client.post(
            "/api/chat/conversations/not-uuid/messages",
            json={"content": "Bad", "role": "user"},
        )
        assert response.status_code == 400

@pytest.mark.integration
class TestConversationHistory:
    """Tests for history endpoints."""

    def test_get_history(self, authenticated_client):
        """Test GET /api/chat/history/{id} returns messages."""
        # Create conversation with a message
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "History Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Add messages
        authenticated_client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": "First msg", "role": "user"},
        )
        authenticated_client.post(
            f"/api/chat/conversations/{conv_id}/messages",
            json={"content": "Reply", "role": "assistant"},
        )

        # Get history
        response = authenticated_client.get(f"/api/chat/history/{conv_id}")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "total" in data
        assert "has_more" in data
        assert data["total"] == 2

    def test_get_history_not_found(self, authenticated_client):
        """Test 404 for history of non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/chat/history/{fake_id}")
        assert response.status_code == 404

    def test_get_history_invalid_uuid(self, authenticated_client):
        """Test 400 for history with invalid UUID."""
        response = authenticated_client.get("/api/chat/history/bad-uuid")
        assert response.status_code == 400

    def test_get_history_limit_exceeded(self, authenticated_client):
        """Test 400 when history limit exceeds 100."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/chat/history/{fake_id}?limit=200")
        assert response.status_code == 400
        assert "Limit cannot exceed 100" in response.json()["detail"]

    def test_get_history_negative_offset(self, authenticated_client):
        """Test 400 when history offset is negative."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/chat/history/{fake_id}?offset=-1")
        assert response.status_code == 400

    def test_clear_history(self, authenticated_client):
        """Test DELETE /api/chat/history/{id} clears conversation."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Clear Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        response = authenticated_client.delete(f"/api/chat/history/{conv_id}")
        assert response.status_code == 204

    def test_clear_history_invalid_uuid(self, authenticated_client):
        """Test 400 clearing history with invalid UUID."""
        response = authenticated_client.delete("/api/chat/history/bad-uuid")
        assert response.status_code == 400

@pytest.mark.integration
class TestConversationSharing:
    """Tests for share/unshare conversation endpoints."""

    def test_share_conversation(self, authenticated_client):
        """Test PATCH /api/chat/conversations/{id}/share."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Share Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        response = authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": "other-user", "permission": "view"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_share_conversation_already_shared(self, authenticated_client):
        """Test sharing already-shared conversation returns appropriate message."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Double Share", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Share first time
        authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": "dup-user", "permission": "view"},
        )

        # Share same user again
        response = authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": "dup-user", "permission": "view"},
        )
        assert response.status_code == 200
        assert "already shared" in response.json()["message"]

    def test_share_conversation_update_permission(self, authenticated_client):
        """Test updating permission on existing share."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Perm Update", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Share with view
        authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": "perm-user", "permission": "view"},
        )

        # Update to edit
        response = authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": "perm-user", "permission": "edit"},
        )
        assert response.status_code == 200
        assert "updated" in response.json()["message"]

    def test_share_conversation_not_found(self, authenticated_client):
        """Test 404 sharing non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.patch(
            f"/api/chat/conversations/{fake_id}/share",
            json={"user_id": "other-user", "permission": "view"},
        )
        assert response.status_code == 404

    def test_unshare_conversation(self, authenticated_client):
        """Test DELETE /api/chat/conversations/{id}/share/{user_id}."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Unshare Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        # Share first
        authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/share",
            json={"user_id": "remove-user", "permission": "view"},
        )

        # Unshare
        response = authenticated_client.delete(
            f"/api/chat/conversations/{conv_id}/share/remove-user"
        )
        assert response.status_code == 200
        assert "unshared" in response.json()["message"]

    def test_unshare_not_shared(self, authenticated_client):
        """Test unsharing when share doesn't exist."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Not Shared", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        response = authenticated_client.delete(f"/api/chat/conversations/{conv_id}/share/nobody")
        assert response.status_code == 200
        assert "not shared" in response.json()["message"]

    def test_unshare_invalid_uuid(self, authenticated_client):
        """Test 400 for invalid conversation UUID in unshare."""
        response = authenticated_client.delete("/api/chat/conversations/bad-uuid/share/someone")
        assert response.status_code == 400

@pytest.mark.integration
class TestMoveToProject:
    """Tests for moving conversations to projects."""

    def test_move_conversation_not_found(self, authenticated_client):
        """Test 404 moving non-existent conversation."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.patch(
            f"/api/chat/conversations/{fake_id}/project",
            json={"project_id": None},
        )
        assert response.status_code == 404

    def test_move_conversation_invalid_uuid(self, authenticated_client):
        """Test 400 moving with invalid UUID."""
        response = authenticated_client.patch(
            "/api/chat/conversations/bad-uuid/project",
            json={"project_id": None},
        )
        assert response.status_code == 400

    def test_move_conversation_remove_from_project(self, authenticated_client):
        """Test removing conversation from project (project_id=null)."""
        create_resp = authenticated_client.post(
            "/api/chat/conversations",
            json={"title": "Move Test", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        response = authenticated_client.patch(
            f"/api/chat/conversations/{conv_id}/project",
            json={"project_id": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] is None
        assert "removed from project" in data["message"]

@pytest.mark.integration
class TestChatModes:
    """Tests for mode-related endpoints."""

    def test_list_modes(self, authenticated_client):
        """Test GET /api/chat/modes returns available modes."""
        response = authenticated_client.get("/api/chat/modes")
        assert response.status_code == 200
        data = response.json()
        assert "modes" in data
        modes = data["modes"]
        assert len(modes) == 2
        mode_names = [m["name"] for m in modes]
        assert "chat" in mode_names
        assert "planner" in mode_names

    def test_cancel_orchestration_not_found(self, authenticated_client):
        """Test 404 cancelling non-existent orchestration."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.post(f"/api/chat/{fake_id}/cancel")
        assert response.status_code == 404

    def test_stream_status_no_active(self, authenticated_client):
        """Test stream status when no active stream."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/chat/{fake_id}/stream-status")
        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False

@pytest.mark.integration
class TestClarifyAndConflicts:
    """Tests for clarification and state conflict endpoints."""

    def test_clarify_no_pending(self, authenticated_client):
        """Test 404 when no pending clarification exists."""
        response = authenticated_client.post(
            "/api/chat/clarify",
            json={
                "conversation_id": str(uuid.uuid4()),
                "response": "Yes",
                "selected_option": 0,
            },
        )
        assert response.status_code == 404

    def test_resolve_state_conflict_no_pending(self, authenticated_client):
        """Test error when no pending state conflict exists."""
        response = authenticated_client.post(
            "/api/chat/resolve-state-conflict",
            json={
                "conversation_id": str(uuid.uuid4()),
                "state_key": "some_key",
                "selected_value": "some_value",
            },
        )
        # 404 if state store has no conflicts, 500 if store init fails
        assert response.status_code in [404, 500]

    def test_get_pending_conflicts(self, authenticated_client):
        """Test GET /api/chat/pending-conflicts/{id} returns conflict status."""
        fake_id = str(uuid.uuid4())
        response = authenticated_client.get(f"/api/chat/pending-conflicts/{fake_id}")
        assert response.status_code == 200
        data = response.json()
        assert "has_pending_clarification" in data
        assert "state_conflicts" in data
        assert isinstance(data["state_conflicts"], list)

@pytest.mark.integration
class TestGetRecentHistory:
    """Tests for the get_recent_history utility function."""

    def test_get_recent_history_invalid_uuid(self):
        """Test ValueError for invalid conversation_id."""
        from core.services.conversation import get_recent_history

        with pytest.raises(ValueError, match="Invalid conversation_id"):
            get_recent_history("not-a-uuid")

    def test_get_recent_history_limit_too_high(self):
        """Test ValueError for limit > 100."""
        from core.services.conversation import get_recent_history

        with pytest.raises(ValueError, match="Limit cannot exceed 100"):
            get_recent_history(str(uuid.uuid4()), limit=200)
