"""Tests for core/api/routes/chat.py -- Conversation and Chat routes.

Tests route handlers directly (no TestClient), mocking DB sessions and auth.
Auth is provided via the standard user dict pattern matching get_current_user output.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER = {"sub": "test-user-001", "email": "test@example.com", "role": "user"}
_TEST_ADMIN = {"sub": "admin-001", "email": "admin@example.com", "role": "admin"}

def _make_conversation(
    conv_id=None,
    user_id="test-user-001",
    title="Test Conversation",
    mode="chat",
    status="active",
):
    c = MagicMock()
    c.id = conv_id or str(uuid.uuid4())
    c.user_id = user_id
    c.title = title
    c.mode = mode
    c.status = status
    c.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
    c.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
    return c

def _make_db_session():
    """Return a mock SQLAlchemy Session."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.filter_by.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.count.return_value = 0
    query_mock.all.return_value = []
    query_mock.first.return_value = None
    query_mock.options.return_value = query_mock
    query_mock.delete.return_value = 0
    db.query.return_value = query_mock
    return db

# ===========================================================================
# list_modes
# ===========================================================================
class TestListModes:
    """Tests for GET /modes."""

    @pytest.mark.asyncio
    async def test_returns_expected_modes(self):
        """Should return chat and planner modes."""
        from core.api.routes.chat import list_modes

        result = await list_modes()

        assert "modes" in result
        names = [m["name"] for m in result["modes"]]
        assert "chat" in names
        assert "planner" in names

    @pytest.mark.asyncio
    async def test_chat_is_default(self):
        """Chat mode should be marked as default."""
        from core.api.routes.chat import list_modes

        result = await list_modes()

        chat_mode = next(m for m in result["modes"] if m["name"] == "chat")
        assert chat_mode["default"] is True

# ===========================================================================
# list_conversations
# ===========================================================================
class TestListConversations:
    """Tests for GET /conversations."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """No conversations -- should return empty list."""
        db = _make_db_session()
        # For non-admin user, filter is applied
        filtered_q = MagicMock()
        filtered_q.count.return_value = 0
        filtered_q.order_by.return_value.limit.return_value.offset.return_value.all.return_value = []
        db.query.return_value.filter.return_value = filtered_q

        from core.api.routes.chat import list_conversations

        result = await list_conversations(user=_TEST_USER, db=db)

        assert result.total == 0
        assert result.conversations == []

    @pytest.mark.asyncio
    async def test_limit_too_large_raises_400(self):
        """Limit > 100 should raise 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import list_conversations

        with pytest.raises(HTTPException) as exc_info:
            await list_conversations(limit=101, user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_negative_offset_raises_400(self):
        """Negative offset should raise 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import list_conversations

        with pytest.raises(HTTPException) as exc_info:
            await list_conversations(offset=-1, user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_skips_user_filter(self):
        """Admin user skips user_id filter and sees all conversations."""
        db = _make_db_session()
        # Admin path: no .filter() call — query used directly
        q = db.query.return_value
        q.count.return_value = 0
        q.order_by.return_value.limit.return_value.offset.return_value.all.return_value = []

        from core.api.routes.chat import list_conversations

        result = await list_conversations(user=_TEST_ADMIN, db=db)
        assert result.total == 0

# ===========================================================================
# get_conversation
# ===========================================================================
class TestGetConversation:
    """Tests for GET /conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_get_own_conversation(self):
        """User can get their own conversation."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="test-user-001")

        db = _make_db_session()
        # First query: get conversation by id
        conv_q = MagicMock()
        conv_q.filter_by.return_value.first.return_value = conv
        # Second query: count messages
        msg_q = MagicMock()
        msg_q.filter.return_value.count.return_value = 2
        db.query.side_effect = [conv_q, msg_q]

        from core.api.routes.chat import get_conversation

        result = await get_conversation(conversation_id=conv_id, user=_TEST_USER, db=db)

        assert result.id == conv_id

    @pytest.mark.asyncio
    async def test_get_not_found_raises_404(self):
        """Non-existent conversation should raise 404."""
        from fastapi import HTTPException

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.chat import get_conversation

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation(conversation_id=str(uuid.uuid4()), user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_other_users_conversation_raises_403(self):
        """User cannot access another user's conversation."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="other-user")

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.chat import get_conversation

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation(conversation_id=conv_id, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_uuid_raises_400(self):
        """Non-UUID conversation_id should raise 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_conversation

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation(
                conversation_id="not-a-uuid", user=_TEST_USER, db=_make_db_session()
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_can_access_any_conversation(self):
        """Admin can access any conversation regardless of owner."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="other-user")

        db = _make_db_session()
        conv_q = MagicMock()
        conv_q.filter_by.return_value.first.return_value = conv
        msg_q = MagicMock()
        msg_q.filter.return_value.count.return_value = 0
        db.query.side_effect = [conv_q, msg_q]

        from core.api.routes.chat import get_conversation

        result = await get_conversation(conversation_id=conv_id, user=_TEST_ADMIN, db=db)
        assert result.id == conv_id

# ===========================================================================
# create_conversation
# ===========================================================================
class TestCreateConversation:
    """Tests for POST /conversations."""

    @pytest.mark.asyncio
    async def test_create_basic(self):
        """Create a conversation -- should call add and commit."""
        from core.api.routes.chat import CreateConversationRequest, create_conversation

        req = CreateConversationRequest(title="My Chat", mode="chat")
        db = _make_db_session()

        # db.refresh sets attributes on the object passed to it
        def fake_refresh(obj):
            obj.id = str(uuid.uuid4())
            obj.created_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)
            obj.updated_at = datetime(2026, 1, 13, 10, 0, 0, tzinfo=timezone.utc)

        db.refresh.side_effect = fake_refresh

        result = await create_conversation(request=req, user=_TEST_USER, db=db)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result.mode == "chat"

# ===========================================================================
# get_history
# ===========================================================================
class TestGetHistory:
    """Tests for GET /history/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_get_history_not_found(self):
        """Missing conversation returns 404."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.chat import get_history

        with pytest.raises(HTTPException) as exc_info:
            await get_history(conversation_id=conv_id, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_history_invalid_uuid(self):
        """Non-UUID conversation_id raises 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_history

        with pytest.raises(HTTPException) as exc_info:
            await get_history(conversation_id="bad-id", user=_TEST_USER, db=_make_db_session())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_history_limit_exceeded(self):
        """Limit > 100 raises 400."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())

        from core.api.routes.chat import get_history

        with pytest.raises(HTTPException) as exc_info:
            await get_history(
                conversation_id=conv_id, limit=101, user=_TEST_USER, db=_make_db_session()
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_history_access_denied(self):
        """User cannot view other user's history."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.chat import get_history

        with pytest.raises(HTTPException) as exc_info:
            await get_history(conversation_id=conv_id, user=_TEST_USER, db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_history_empty(self):
        """Empty conversation returns 0 messages."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="test-user-001")

        db = _make_db_session()
        # query 1: DBConversation filter_by
        conv_q = MagicMock()
        conv_q.filter_by.return_value.first.return_value = conv
        # query 2: DBMessage count
        count_q = MagicMock()
        count_q.filter.return_value.count.return_value = 0
        # query 3: DBMessage with options
        msg_q = MagicMock()
        msg_q.options.return_value = msg_q
        msg_q.filter.return_value = msg_q
        msg_q.order_by.return_value = msg_q
        msg_q.limit.return_value = msg_q
        msg_q.offset.return_value = msg_q
        msg_q.all.return_value = []
        db.query.side_effect = [conv_q, count_q, msg_q]

        from core.api.routes.chat import get_history

        result = await get_history(conversation_id=conv_id, user=_TEST_USER, db=db)
        assert result.total == 0
        assert result.messages == []

# ===========================================================================
# clear_history (no auth -- just db)
# ===========================================================================
class TestClearHistory:
    """Tests for DELETE /history/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_clear_invalid_uuid(self):
        """Invalid UUID raises 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import clear_history

        with pytest.raises(HTTPException) as exc_info:
            await clear_history(conversation_id="bad", db=_make_db_session())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_clear_missing_conversation_no_op(self):
        """Missing conversation is silently ignored (no error)."""
        conv_id = str(uuid.uuid4())
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.chat import clear_history

        # Should not raise
        await clear_history(conversation_id=conv_id, db=db)

    @pytest.mark.asyncio
    async def test_clear_existing_conversation(self):
        """Existing conversation is deleted."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id)
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.chat import clear_history

        await clear_history(conversation_id=conv_id, db=db)
        db.delete.assert_called_once_with(conv)
        db.commit.assert_called()

# ===========================================================================
# delete_conversation (no user auth -- uses only db)
# ===========================================================================
class TestDeleteConversation:
    """Tests for DELETE /conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """Non-existent conversation returns 404."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.chat import delete_conversation

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation(conversation_id=conv_id, db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_existing(self):
        """Existing conversation is deleted."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id)
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.chat import delete_conversation

        await delete_conversation(conversation_id=conv_id, db=db)
        db.delete.assert_called_once_with(conv)
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(self):
        """Invalid UUID format raises 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import delete_conversation

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation(conversation_id="not-uuid", db=_make_db_session())
        assert exc_info.value.status_code == 400

# ===========================================================================
# update_conversation
# ===========================================================================
class TestUpdateConversation:
    """Tests for PATCH /conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_update_title(self):
        """User can update the title of their own conversation."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="test-user-001", title="Old Title")
        db = _make_db_session()

        conv_q = MagicMock()
        conv_q.filter_by.return_value.first.return_value = conv
        msg_q = MagicMock()
        msg_q.filter.return_value.count.return_value = 0
        db.query.side_effect = [conv_q, msg_q]

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        req = UpdateConversationRequest(title="New Title")
        result = await update_conversation(
            conversation_id=conv_id, request=req, user=_TEST_USER, db=db
        )

        assert conv.title == "New Title"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        """Update on missing conversation raises 404."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation(
                conversation_id=conv_id,
                request=UpdateConversationRequest(title="X"),
                user=_TEST_USER,
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_access_denied(self):
        """User cannot update another user's conversation."""
        from fastapi import HTTPException

        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="other-user")
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation(
                conversation_id=conv_id,
                request=UpdateConversationRequest(title="X"),
                user=_TEST_USER,
                db=db,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_invalid_uuid(self):
        """Non-UUID raises 400."""
        from fastapi import HTTPException

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        with pytest.raises(HTTPException) as exc_info:
            await update_conversation(
                conversation_id="bad-uuid",
                request=UpdateConversationRequest(title="X"),
                user=_TEST_USER,
                db=_make_db_session(),
            )
        assert exc_info.value.status_code == 400

# ===========================================================================
# stream_status and cancel_orchestration
# ===========================================================================
class TestStreamStatus:
    """Tests for GET /{conversation_id}/stream-status."""

    @pytest.mark.asyncio
    async def test_no_active_stream(self):
        """No active stream returns active=False."""
        import sys

        mock_stream_reg_module = MagicMock()
        mock_stream_reg_module.get_stream_registry = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=None))
        )

        with patch.dict(sys.modules, {"core.orchestrator.stream_registry": mock_stream_reg_module}):
            from core.api.routes.chat import get_stream_status

            result = await get_stream_status(conversation_id="conv-123")

        assert result["active"] is False

    @pytest.mark.asyncio
    async def test_active_stream(self):
        """Active stream returns active=True with metadata."""
        import sys

        stream = MagicMock()
        stream.started_at = "2026-01-13T10:00:00Z"
        stream.mode = "chat"
        stream.accumulated_content = "hello"
        stream.accumulated_thinking = None

        mock_stream_reg_module = MagicMock()
        mock_stream_reg_module.get_stream_registry = MagicMock(
            return_value=MagicMock(get=MagicMock(return_value=stream))
        )

        with patch.dict(sys.modules, {"core.orchestrator.stream_registry": mock_stream_reg_module}):
            from core.api.routes.chat import get_stream_status

            result = await get_stream_status(conversation_id="conv-123")

        assert result["active"] is True
        assert result["mode"] == "chat"

class TestCancelOrchestration:
    """Tests for POST /{conversation_id}/cancel."""

    @pytest.mark.asyncio
    async def test_cancel_no_active_orchestration(self):
        """No active orchestration returns 404."""
        import sys

        from fastapi import HTTPException

        mock_cancel_module = MagicMock()
        mock_cancel_module.get_cancellation_registry = MagicMock(
            return_value=MagicMock(request_cancel=MagicMock(return_value=False))
        )

        with patch.dict(sys.modules, {"core.orchestrator.cancellation": mock_cancel_module}):
            from core.api.routes.chat import cancel_orchestration

            with pytest.raises(HTTPException) as exc_info:
                await cancel_orchestration(conversation_id="conv-123", current_user=_TEST_USER)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_active_orchestration(self):
        """Active orchestration is cancelled successfully."""
        import sys

        mock_cancel_module = MagicMock()
        mock_cancel_module.get_cancellation_registry = MagicMock(
            return_value=MagicMock(request_cancel=MagicMock(return_value=True))
        )

        with patch.dict(sys.modules, {"core.orchestrator.cancellation": mock_cancel_module}):
            from core.api.routes.chat import cancel_orchestration

            result = await cancel_orchestration(conversation_id="conv-123", current_user=_TEST_USER)

        assert result["status"] == "cancelling"
        assert result["conversation_id"] == "conv-123"

# ===========================================================================
# submit_clarification
# ===========================================================================
class TestSubmitClarification:
    """Tests for POST /clarify."""

    @pytest.mark.asyncio
    async def test_clarification_found(self):
        """Valid clarification response returns success."""
        import sys

        from core.api.routes.chat import ClarifyRequest
        from core.api.routes.chat import submit_clarification as route_submit

        req = ClarifyRequest(conversation_id="conv-abc", response="Yes, proceed")

        # These are imported inside the route function body, so patch at the source module
        mock_autonomous = MagicMock()
        mock_autonomous.has_pending_autonomous_clarification = MagicMock(return_value=False)
        mock_autonomous.submit_autonomous_clarification = MagicMock(return_value=False)
        mock_extensions = MagicMock()
        mock_extensions.submit_clarification = MagicMock(return_value=True)
        mock_extensions.ClarificationResponse = MagicMock(return_value=MagicMock())

        with (
            patch.dict(
                sys.modules,
                {
                    "core.autonomous.chat_adapter": mock_autonomous,
                    "core.extensions": mock_extensions,
                },
            ),
        ):
            result = await route_submit(req)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_clarification_not_found_raises_404(self):
        """No pending clarification raises 404."""
        import sys

        from fastapi import HTTPException

        from core.api.routes.chat import ClarifyRequest
        from core.api.routes.chat import submit_clarification as route_submit

        req = ClarifyRequest(conversation_id="conv-abc", response="Yes")

        mock_autonomous = MagicMock()
        mock_autonomous.has_pending_autonomous_clarification = MagicMock(return_value=False)
        mock_extensions = MagicMock()
        mock_extensions.submit_clarification = MagicMock(return_value=False)
        mock_extensions.ClarificationResponse = MagicMock(return_value=MagicMock())

        with patch.dict(
            sys.modules,
            {
                "core.autonomous.chat_adapter": mock_autonomous,
                "core.extensions": mock_extensions,
            },
        ):
            with pytest.raises(HTTPException) as exc_info:
                await route_submit(req)
        assert exc_info.value.status_code == 404

# ===========================================================================
# get_pending_conflicts
# ===========================================================================
class TestGetPendingConflicts:
    """Tests for GET /pending-conflicts/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_no_conflicts(self):
        """No pending conflicts -- returns empty state."""
        import sys

        mock_extensions = MagicMock()
        mock_extensions.has_pending_clarification = MagicMock(return_value=False)
        mock_state = MagicMock()
        mock_state.get_state_store = MagicMock(
            return_value=MagicMock(get_all_conflicts=MagicMock(return_value=[]))
        )

        with patch.dict(
            sys.modules,
            {
                "core.extensions": mock_extensions,
                "core.extensions.state": mock_state,
            },
        ):
            from core.api.routes.chat import get_pending_conflicts

            result = await get_pending_conflicts(conversation_id="conv-abc")

        assert result["has_pending_clarification"] is False
        assert result["state_conflicts"] == []

    @pytest.mark.asyncio
    async def test_has_pending_clarification(self):
        """Pending clarification is reported."""
        import sys

        mock_extensions = MagicMock()
        mock_extensions.has_pending_clarification = MagicMock(return_value=True)
        mock_state = MagicMock()
        mock_state.get_state_store = MagicMock(
            return_value=MagicMock(get_all_conflicts=MagicMock(return_value=[]))
        )

        with patch.dict(
            sys.modules,
            {
                "core.extensions": mock_extensions,
                "core.extensions.state": mock_state,
            },
        ):
            from core.api.routes.chat import get_pending_conflicts

            result = await get_pending_conflicts(conversation_id="conv-abc")

        assert result["has_pending_clarification"] is True

# ===========================================================================
# bulk_delete_conversations
# ===========================================================================
class TestBulkDeleteConversations:
    """Tests for POST /conversations/bulk-delete."""

    @pytest.mark.asyncio
    async def test_bulk_delete_empty_ids_raises_validation_error(self):
        """Empty conversation_ids list fails Pydantic validation."""
        from pydantic import ValidationError

        from core.api.routes.chat import BulkDeleteRequest

        with pytest.raises(ValidationError):
            BulkDeleteRequest(conversation_ids=[])

    @pytest.mark.asyncio
    async def test_bulk_delete_own_conversations(self):
        """User can bulk-delete their own conversations."""
        conv_id1 = str(uuid.uuid4())
        conv_id2 = str(uuid.uuid4())
        conv1 = _make_conversation(conv_id=conv_id1, user_id="test-user-001")
        conv2 = _make_conversation(conv_id=conv_id2, user_id="test-user-001")

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.side_effect = [conv1, conv2]

        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        req = BulkDeleteRequest(conversation_ids=[conv_id1, conv_id2])
        result = await bulk_delete_conversations(request=req, user=_TEST_USER, db=db)

        assert result.deleted_count == 2
        assert result.failed_ids == []

    @pytest.mark.asyncio
    async def test_bulk_delete_other_user_skips(self):
        """Conversations owned by other users are skipped."""
        conv_id = str(uuid.uuid4())
        conv = _make_conversation(conv_id=conv_id, user_id="other-user")

        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = conv

        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        req = BulkDeleteRequest(conversation_ids=[conv_id])
        result = await bulk_delete_conversations(request=req, user=_TEST_USER, db=db)

        assert result.deleted_count == 0
        assert conv_id in result.failed_ids

    @pytest.mark.asyncio
    async def test_bulk_delete_not_found_in_failed(self):
        """Non-existent conversations appear in failed_ids."""
        conv_id = str(uuid.uuid4())
        db = _make_db_session()
        db.query.return_value.filter_by.return_value.first.return_value = None

        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        req = BulkDeleteRequest(conversation_ids=[conv_id])
        result = await bulk_delete_conversations(request=req, user=_TEST_USER, db=db)

        assert result.deleted_count == 0
        assert conv_id in result.failed_ids
