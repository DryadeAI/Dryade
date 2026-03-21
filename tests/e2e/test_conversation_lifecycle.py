"""E2E tests for conversation CRUD lifecycle.

Tests the full conversation lifecycle through the real FastAPI API:
create, list, get, update, delete, bulk delete, delete all,
and chat message persistence.
"""

from unittest.mock import patch

import pytest

from core.extensions.events import ChatEvent

pytestmark = pytest.mark.e2e

def _async_gen_route_request():
    """Build an async-generator mock for route_request.

    The real route_request is an async generator that yields ChatEvent objects.
    The autouse mock_route_request fixture returns a plain dict which cannot be
    iterated with ``async for``, so tests that hit POST /api/chat need this
    replacement.
    """

    async def _fake_route(message, **kwargs):
        yield ChatEvent(
            type="complete",
            content=f"Mock response to: {message[:50]}",
            metadata={"mode": "chat"},
        )

    return _fake_route

@pytest.fixture(autouse=True)
def _patch_route_request_as_generator(mock_route_request):
    """Override the autouse mock_route_request with an async-generator version.

    The parent conftest patches route_request as an AsyncMock returning a dict,
    but the chat endpoint iterates it with ``async for``.  Re-patch here so
    both CRUD and chat endpoints work.
    """
    with patch(
        "core.api.routes.chat.route_request",
        new=_async_gen_route_request(),
    ):
        yield

class TestConversationLifecycle:
    """Full CRUD lifecycle tests for the conversation API."""

    # ------------------------------------------------------------------
    # 1. Create
    # ------------------------------------------------------------------

    def test_create_conversation(self, e2e_client):
        """POST /api/chat/conversations returns 201 with id, title, mode."""
        resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "My first conversation", "mode": "chat"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["title"] == "My first conversation"
        assert body["mode"] == "chat"
        assert body["status"] == "active"
        assert body["message_count"] == 0

    # ------------------------------------------------------------------
    # 2. List after create
    # ------------------------------------------------------------------

    def test_list_conversations_after_create(self, e2e_client):
        """Creating 2 conversations then listing returns both."""
        r1 = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Conv A", "mode": "chat"},
        )
        r2 = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Conv B", "mode": "chat"},
        )
        assert r1.status_code == 201
        assert r2.status_code == 201

        id_a = r1.json()["id"]
        id_b = r2.json()["id"]

        resp = e2e_client.get("/api/chat/conversations")
        assert resp.status_code == 200
        body = resp.json()
        returned_ids = {c["id"] for c in body["conversations"]}
        assert id_a in returned_ids
        assert id_b in returned_ids

    # ------------------------------------------------------------------
    # 3. Chat adds messages
    # ------------------------------------------------------------------

    def test_chat_adds_messages_to_conversation(self, e2e_client):
        """POST /api/chat stores user + assistant messages in history."""
        # Create a conversation
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Chat test", "mode": "chat"},
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["id"]

        # Send a chat message
        chat_resp = e2e_client.post(
            "/api/chat",
            json={"message": "Hello world", "conversation_id": conv_id},
        )
        assert chat_resp.status_code == 200

        # Retrieve history
        hist_resp = e2e_client.get(f"/api/chat/history/{conv_id}")
        assert hist_resp.status_code == 200
        messages = hist_resp.json()["messages"]

        roles = [m["role"] for m in messages]
        assert "user" in roles
        assert "assistant" in roles
        # The user message content should match what we sent
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert any("Hello world" in m["content"] for m in user_msgs)

    # ------------------------------------------------------------------
    # 4. Multi-turn chat
    # ------------------------------------------------------------------

    def test_multi_turn_chat(self, e2e_client):
        """Sending 3 messages to the same conversation stores all 3 user messages."""
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Multi-turn", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        for text in ["First message", "Second message", "Third message"]:
            resp = e2e_client.post(
                "/api/chat",
                json={"message": text, "conversation_id": conv_id},
            )
            assert resp.status_code == 200

        hist_resp = e2e_client.get(f"/api/chat/history/{conv_id}")
        assert hist_resp.status_code == 200
        messages = hist_resp.json()["messages"]

        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 3
        user_contents = [m["content"] for m in user_msgs]
        assert "First message" in user_contents
        assert "Second message" in user_contents
        assert "Third message" in user_contents

    # ------------------------------------------------------------------
    # 5. Update title
    # ------------------------------------------------------------------

    def test_update_conversation_title(self, e2e_client):
        """PATCH /api/chat/conversations/{id} updates the title."""
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Old title", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        patch_resp = e2e_client.patch(
            f"/api/chat/conversations/{conv_id}",
            json={"title": "New title"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "New title"

        # Verify via GET
        get_resp = e2e_client.get(f"/api/chat/conversations/{conv_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "New title"

    # ------------------------------------------------------------------
    # 6. Delete single conversation
    # ------------------------------------------------------------------

    def test_delete_conversation(self, e2e_client):
        """DELETE /api/chat/conversations/{id} returns 204 and removes it from list."""
        create_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "To be deleted", "mode": "chat"},
        )
        conv_id = create_resp.json()["id"]

        del_resp = e2e_client.delete(f"/api/chat/conversations/{conv_id}")
        assert del_resp.status_code == 204

        # Verify gone from list
        list_resp = e2e_client.get("/api/chat/conversations")
        returned_ids = {c["id"] for c in list_resp.json()["conversations"]}
        assert conv_id not in returned_ids

    # ------------------------------------------------------------------
    # 7. Bulk delete
    # ------------------------------------------------------------------

    def test_bulk_delete_conversations(self, e2e_client):
        """Bulk delete 2 of 3 conversations; the remaining 1 survives."""
        ids = []
        for i in range(3):
            resp = e2e_client.post(
                "/api/chat/conversations",
                json={"title": f"Bulk {i}", "mode": "chat"},
            )
            assert resp.status_code == 201
            ids.append(resp.json()["id"])

        # Bulk delete the first two
        bulk_resp = e2e_client.request(
            "DELETE",
            "/api/chat/conversations/bulk",
            json={"conversation_ids": ids[:2]},
        )
        assert bulk_resp.status_code == 200
        body = bulk_resp.json()
        assert body["deleted_count"] == 2

        # Verify only the third remains (among those we created)
        list_resp = e2e_client.get("/api/chat/conversations")
        returned_ids = {c["id"] for c in list_resp.json()["conversations"]}
        assert ids[0] not in returned_ids
        assert ids[1] not in returned_ids
        assert ids[2] in returned_ids

    # ------------------------------------------------------------------
    # 8. Delete all
    # ------------------------------------------------------------------

    def test_delete_all_conversations(self, e2e_client):
        """DELETE /api/chat/conversations/all removes every conversation for the user."""
        for i in range(3):
            resp = e2e_client.post(
                "/api/chat/conversations",
                json={"title": f"All {i}", "mode": "chat"},
            )
            assert resp.status_code == 201

        del_resp = e2e_client.delete("/api/chat/conversations/all")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted_count"] >= 3

        list_resp = e2e_client.get("/api/chat/conversations")
        assert list_resp.json()["total"] == 0
        assert list_resp.json()["conversations"] == []
