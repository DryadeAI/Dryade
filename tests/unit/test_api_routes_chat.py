"""Tests for core/api/routes/chat.py -- Conversation and chat endpoints.

Tests route handler functions directly (async pattern) rather than through
TestClient, to avoid DB session conflicts in unit test environments.

Pattern:
- Call async route handler functions directly
- Mock DB session via SQLite in-memory database (no real PostgreSQL required)
- Mock auth via simple dict
- Mock LLM/orchestration calls
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base, Conversation, Message, ResourceShare

# ---------------------------------------------------------------------------
# Test DB fixture — SQLite in-memory (no PostgreSQL required)
# ---------------------------------------------------------------------------

_ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(_ENGINE)
_SessionLocal = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False)

def _make_session():
    """Create a fresh SQLite in-memory session (shared schema, isolated per test via rollback)."""
    return _SessionLocal()

# ---------------------------------------------------------------------------
# Autouse fixture: patch get_session so route handlers that open their own
# DB sessions (inline `with get_session() as db`) also hit SQLite, not PG.
# Also patches the inline import in core.api.routes.chat.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_get_session(monkeypatch):
    """Replace core.database.session.get_session with SQLite in-memory context manager.

    Also cleans all test tables before each test so count assertions are reliable.
    """
    # Wipe data between tests so count assertions don't see prior-test rows
    with _ENGINE.connect() as conn:
        # Delete in FK-safe order (children before parents)
        from sqlalchemy import text

        conn.execute(text("DELETE FROM tool_results"))
        conn.execute(text("DELETE FROM checkpoints"))
        conn.execute(text("DELETE FROM messages"))
        conn.execute(text("DELETE FROM resource_shares"))
        conn.execute(text("DELETE FROM conversations"))
        conn.commit()

    @contextmanager
    def _sqlite_session():
        session = _SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("core.database.session.get_session", _sqlite_session)
    # Also patch where the route module imports it locally (inline import guard)
    try:
        import core.api.routes.chat as _chat_mod  # noqa: PLC0415

        monkeypatch.setattr(_chat_mod, "get_session", _sqlite_session, raising=False)
    except Exception:
        pass

def _conv_id() -> str:
    return str(uuid.uuid4())

def _user(sub: str = "user-001", role: str = "member") -> dict:
    return {"sub": sub, "role": role, "email": f"{sub}@example.com"}

def _make_conversation(db, user_id: str = "user-001", **kwargs) -> Conversation:
    conv = Conversation(
        id=_conv_id(),
        user_id=user_id,
        title=kwargs.get("title", "Test Conv"),
        mode=kwargs.get("mode", "chat"),
        status=kwargs.get("status", "active"),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv

def _make_message(db, conversation_id: str, role: str = "user", content: str = "hello") -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata_={"timestamp": datetime.now(UTC).isoformat()},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg

# ===========================================================================
# cancel_orchestration endpoint
# ===========================================================================

class TestCancelOrchestration:
    """Tests for POST /{conversation_id}/cancel."""

    @pytest.mark.asyncio
    async def test_cancel_not_active(self):
        """Returns 404 when no active orchestration."""
        from fastapi import HTTPException

        from core.api.routes.chat import cancel_orchestration

        conv_id = _conv_id()
        with patch("core.orchestrator.cancellation.get_cancellation_registry") as mock_reg:
            mock_registry = MagicMock()
            mock_registry.request_cancel.return_value = False
            mock_reg.return_value = mock_registry

            with pytest.raises(HTTPException) as exc:
                await cancel_orchestration(conversation_id=conv_id, current_user=_user())

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_active_orchestration(self):
        """Returns 200 dict when orchestration is cancelled."""
        from core.api.routes.chat import cancel_orchestration

        conv_id = _conv_id()
        with patch("core.orchestrator.cancellation.get_cancellation_registry") as mock_reg:
            mock_registry = MagicMock()
            mock_registry.request_cancel.return_value = True
            mock_reg.return_value = mock_registry

            result = await cancel_orchestration(conversation_id=conv_id, current_user=_user())

        assert result["status"] == "cancelling"
        assert result["conversation_id"] == conv_id

# ===========================================================================
# get_stream_status endpoint
# ===========================================================================

class TestStreamStatus:
    """Tests for GET /{conversation_id}/stream-status."""

    @pytest.mark.asyncio
    async def test_stream_status_no_active_stream(self):
        """Returns active=False when no stream is running."""
        from core.api.routes.chat import get_stream_status

        conv_id = _conv_id()
        with patch("core.orchestrator.stream_registry.get_stream_registry") as mock_reg:
            mock_registry = MagicMock()
            mock_registry.get.return_value = None
            mock_reg.return_value = mock_registry

            result = await get_stream_status(conversation_id=conv_id)

        assert result["active"] is False

    @pytest.mark.asyncio
    async def test_stream_status_active_stream(self):
        """Returns active=True with stream details."""
        from core.api.routes.chat import get_stream_status

        conv_id = _conv_id()
        with patch("core.orchestrator.stream_registry.get_stream_registry") as mock_reg:
            mock_stream = MagicMock()
            mock_stream.started_at = "2026-01-01T00:00:00Z"
            mock_stream.mode = "chat"
            mock_stream.accumulated_content = "partial"
            mock_stream.accumulated_thinking = ""
            mock_registry = MagicMock()
            mock_registry.get.return_value = mock_stream
            mock_reg.return_value = mock_registry

            result = await get_stream_status(conversation_id=conv_id)

        assert result["active"] is True
        assert result["mode"] == "chat"

# ===========================================================================
# get_history endpoint
# ===========================================================================

class TestGetHistory:
    """Tests for GET /history/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_get_history_success(self):
        """Returns messages for user's conversation."""
        from core.api.routes.chat import get_history

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        _make_message(db, conv.id, role="user", content="Hello")
        _make_message(db, conv.id, role="assistant", content="Hi!")

        result = await get_history(
            conversation_id=conv.id,
            limit=100,
            offset=0,
            user=user,
            db=db,
        )
        assert result.total == 2
        assert len(result.messages) == 2
        assert result.has_more is False
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_history

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_history(
                conversation_id=_conv_id(),
                limit=100,
                offset=0,
                user=_user(),
                db=db,
            )
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_invalid_uuid(self):
        """Returns 400 for invalid UUID format."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_history

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_history(
                conversation_id="not-a-uuid",
                limit=100,
                offset=0,
                user=_user(),
                db=db,
            )
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_access_denied(self):
        """Returns 403 when user doesn't own conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_history

        db = _make_session()
        conv = _make_conversation(db, user_id="other-user")

        with pytest.raises(HTTPException) as exc:
            await get_history(
                conversation_id=conv.id,
                limit=100,
                offset=0,
                user=_user(sub="user-A"),
                db=db,
            )
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_admin_access(self):
        """Admin can access any user's conversation."""
        from core.api.routes.chat import get_history

        db = _make_session()
        conv = _make_conversation(db, user_id="other-user")

        result = await get_history(
            conversation_id=conv.id,
            limit=100,
            offset=0,
            user=_user(sub="admin-1", role="admin"),
            db=db,
        )
        assert result.total == 0
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_limit_exceeded(self):
        """Returns 400 when limit > 100."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_history

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_history(
                conversation_id=_conv_id(),
                limit=101,
                offset=0,
                user=_user(),
                db=db,
            )
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_negative_offset(self):
        """Returns 400 for negative offset."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_history

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_history(
                conversation_id=_conv_id(),
                limit=10,
                offset=-1,
                user=_user(),
                db=db,
            )
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_get_history_pagination(self):
        """Pagination returns correct slice."""
        from core.api.routes.chat import get_history

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        for i in range(5):
            _make_message(db, conv.id, content=f"msg {i}")

        result = await get_history(
            conversation_id=conv.id,
            limit=2,
            offset=0,
            user=user,
            db=db,
        )
        assert len(result.messages) == 2
        assert result.total == 5
        assert result.has_more is True
        db.close()

# ===========================================================================
# clear_history endpoint
# ===========================================================================

class TestClearHistory:
    """Tests for DELETE /history/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_clear_history_success(self):
        """Returns None (204) for existing conversation."""
        from core.api.routes.chat import clear_history

        db = _make_session()
        conv = _make_conversation(db)

        result = await clear_history(conversation_id=conv.id, db=db)
        assert result is None
        db.close()

    @pytest.mark.asyncio
    async def test_clear_history_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import clear_history

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await clear_history(conversation_id="not-a-uuid", db=db)
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_clear_history_nonexistent(self):
        """No-op for non-existent conversation (204 idempotent)."""
        from core.api.routes.chat import clear_history

        db = _make_session()
        result = await clear_history(conversation_id=_conv_id(), db=db)
        assert result is None
        db.close()

# ===========================================================================
# list_conversations endpoint
# ===========================================================================

class TestListConversations:
    """Tests for GET /conversations."""

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self):
        """Returns empty list when no conversations exist."""
        from core.api.routes.chat import list_conversations

        db = _make_session()
        result = await list_conversations(limit=50, offset=0, user=_user(), db=db)
        assert result.total == 0
        assert result.conversations == []
        db.close()

    @pytest.mark.asyncio
    async def test_list_conversations_returns_own(self):
        """User sees only their own conversations."""
        from core.api.routes.chat import list_conversations

        db = _make_session()
        user = _user()
        _make_conversation(db, user_id=user["sub"], title="Mine")
        _make_conversation(db, user_id="other-user", title="Not Mine")

        result = await list_conversations(limit=50, offset=0, user=user, db=db)
        assert result.total == 1
        assert result.conversations[0].title == "Mine"
        db.close()

    @pytest.mark.asyncio
    async def test_list_conversations_admin_sees_all(self):
        """Admin sees all conversations."""
        from core.api.routes.chat import list_conversations

        db = _make_session()
        _make_conversation(db, user_id="user-A")
        _make_conversation(db, user_id="user-B")

        result = await list_conversations(
            limit=50, offset=0, user=_user(sub="admin-1", role="admin"), db=db
        )
        assert result.total == 2
        db.close()

    @pytest.mark.asyncio
    async def test_list_conversations_limit_exceeded(self):
        """Returns 400 for limit > 100."""
        from fastapi import HTTPException

        from core.api.routes.chat import list_conversations

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await list_conversations(limit=101, offset=0, user=_user(), db=db)
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_list_conversations_negative_offset(self):
        """Returns 400 for negative offset."""
        from fastapi import HTTPException

        from core.api.routes.chat import list_conversations

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await list_conversations(limit=10, offset=-1, user=_user(), db=db)
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_list_conversations_has_message_count(self):
        """Response includes message count."""
        from core.api.routes.chat import list_conversations

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        _make_message(db, conv.id)
        _make_message(db, conv.id)

        result = await list_conversations(limit=50, offset=0, user=user, db=db)
        assert result.conversations[0].message_count == 2
        db.close()

# ===========================================================================
# get_conversation endpoint
# ===========================================================================

class TestGetConversation:
    """Tests for GET /conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_get_conversation_success(self):
        """Returns conversation for owner."""
        from core.api.routes.chat import get_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"], title="My Convo")

        result = await get_conversation(conversation_id=conv.id, user=user, db=db)
        assert result.id == conv.id
        assert result.title == "My Convo"
        db.close()

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_conversation

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_conversation(conversation_id=_conv_id(), user=_user(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_get_conversation_forbidden(self):
        """Returns 403 for another user's conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_conversation

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")

        with pytest.raises(HTTPException) as exc:
            await get_conversation(conversation_id=conv.id, user=_user(sub="user-A"), db=db)
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_get_conversation_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import get_conversation

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await get_conversation(conversation_id="bad-id", user=_user(), db=db)
        assert exc.value.status_code == 400
        db.close()

# ===========================================================================
# create_conversation endpoint
# ===========================================================================

class TestCreateConversation:
    """Tests for POST /conversations."""

    @pytest.mark.asyncio
    async def test_create_conversation_success(self):
        """Creates conversation with provided title."""
        from core.api.routes.chat import CreateConversationRequest, create_conversation

        db = _make_session()
        req = CreateConversationRequest(title="New Convo", mode="chat")

        result = await create_conversation(request=req, user=_user(), db=db)
        assert result.title == "New Convo"
        assert result.mode == "chat"
        assert result.status == "active"
        assert result.message_count == 0
        db.close()

    @pytest.mark.asyncio
    async def test_create_conversation_no_title(self):
        """Creates conversation with default title."""
        from core.api.routes.chat import CreateConversationRequest, create_conversation

        db = _make_session()
        req = CreateConversationRequest(mode="chat")

        result = await create_conversation(request=req, user=_user(), db=db)
        assert result.title == "New Conversation"
        db.close()

    @pytest.mark.asyncio
    async def test_create_conversation_planner_mode(self):
        """Creates conversation in planner mode."""
        from core.api.routes.chat import CreateConversationRequest, create_conversation

        db = _make_session()
        req = CreateConversationRequest(mode="planner")

        result = await create_conversation(request=req, user=_user(), db=db)
        assert result.mode == "planner"
        db.close()

# ===========================================================================
# update_conversation endpoint
# ===========================================================================

class TestUpdateConversation:
    """Tests for PATCH /conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_update_conversation_title(self):
        """Updates conversation title."""
        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"], title="Old Title")
        req = UpdateConversationRequest(title="New Title")

        result = await update_conversation(conversation_id=conv.id, request=req, user=user, db=db)
        assert result.title == "New Title"
        db.close()

    @pytest.mark.asyncio
    async def test_update_conversation_mode(self):
        """Updates conversation mode."""
        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"], mode="chat")
        req = UpdateConversationRequest(mode="planner")

        result = await update_conversation(conversation_id=conv.id, request=req, user=user, db=db)
        assert result.mode == "planner"
        db.close()

    @pytest.mark.asyncio
    async def test_update_conversation_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        db = _make_session()
        req = UpdateConversationRequest(title="x")

        with pytest.raises(HTTPException) as exc:
            await update_conversation(conversation_id=_conv_id(), request=req, user=_user(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_update_conversation_forbidden(self):
        """Returns 403 for another user's conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")
        req = UpdateConversationRequest(title="hack")

        with pytest.raises(HTTPException) as exc:
            await update_conversation(
                conversation_id=conv.id, request=req, user=_user(sub="user-A"), db=db
            )
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_update_conversation_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import UpdateConversationRequest, update_conversation

        db = _make_session()
        req = UpdateConversationRequest(title="x")

        with pytest.raises(HTTPException) as exc:
            await update_conversation(conversation_id="bad-id", request=req, user=_user(), db=db)
        assert exc.value.status_code == 400
        db.close()

# ===========================================================================
# delete_conversation endpoint
# ===========================================================================

class TestDeleteConversation:
    """Tests for DELETE /conversations/{conversation_id}."""

    @pytest.mark.asyncio
    async def test_delete_conversation_success(self):
        """Deletes conversation — returns None (204)."""
        from core.api.routes.chat import delete_conversation

        db = _make_session()
        conv = _make_conversation(db)

        result = await delete_conversation(conversation_id=conv.id, db=db)
        assert result is None

        # Verify deleted
        from sqlalchemy.orm import Session

        assert db.query(Conversation).filter_by(id=conv.id).first() is None
        db.close()

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import delete_conversation

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await delete_conversation(conversation_id=_conv_id(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_delete_conversation_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import delete_conversation

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await delete_conversation(conversation_id="bad-uuid", db=db)
        assert exc.value.status_code == 400
        db.close()

# ===========================================================================
# bulk_delete_conversations endpoint
# ===========================================================================

class TestBulkDeleteConversations:
    """Tests for DELETE /conversations/bulk."""

    @pytest.mark.asyncio
    async def test_bulk_delete_owned_conversations(self):
        """Deletes conversations owned by the user."""
        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        db = _make_session()
        user = _user()
        conv1 = _make_conversation(db, user_id=user["sub"])
        conv2 = _make_conversation(db, user_id=user["sub"])
        req = BulkDeleteRequest(conversation_ids=[conv1.id, conv2.id])

        result = await bulk_delete_conversations(request=req, user=user, db=db)
        assert result.deleted_count == 2
        assert result.failed_ids == []
        db.close()

    @pytest.mark.asyncio
    async def test_bulk_delete_invalid_uuid_skipped(self):
        """Invalid UUIDs are added to failed_ids."""
        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        db = _make_session()
        req = BulkDeleteRequest(conversation_ids=["not-a-uuid"])

        result = await bulk_delete_conversations(request=req, user=_user(), db=db)
        assert result.deleted_count == 0
        assert "not-a-uuid" in result.failed_ids
        db.close()

    @pytest.mark.asyncio
    async def test_bulk_delete_skips_others_conversations(self):
        """Conversations owned by others are skipped."""
        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")
        req = BulkDeleteRequest(conversation_ids=[conv.id])

        result = await bulk_delete_conversations(request=req, user=_user(sub="user-A"), db=db)
        assert result.deleted_count == 0
        assert conv.id in result.failed_ids
        db.close()

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent_added_to_failed(self):
        """Non-existent conversations are added to failed_ids."""
        from core.api.routes.chat import BulkDeleteRequest, bulk_delete_conversations

        db = _make_session()
        fake_id = _conv_id()
        req = BulkDeleteRequest(conversation_ids=[fake_id])

        result = await bulk_delete_conversations(request=req, user=_user(), db=db)
        assert fake_id in result.failed_ids
        db.close()

# ===========================================================================
# delete_all_conversations endpoint
# ===========================================================================

class TestDeleteAllConversations:
    """Tests for DELETE /conversations/all."""

    @pytest.mark.asyncio
    async def test_delete_all_conversations(self):
        """Deletes all conversations for the user."""
        from core.api.routes.chat import delete_all_conversations

        db = _make_session()
        user = _user()
        _make_conversation(db, user_id=user["sub"])
        _make_conversation(db, user_id=user["sub"])

        result = await delete_all_conversations(user=user, db=db)
        assert result.deleted_count == 2
        db.close()

    @pytest.mark.asyncio
    async def test_delete_all_conversations_empty(self):
        """Returns 0 when user has no conversations."""
        from core.api.routes.chat import delete_all_conversations

        db = _make_session()
        result = await delete_all_conversations(user=_user(), db=db)
        assert result.deleted_count == 0
        db.close()

    @pytest.mark.asyncio
    async def test_delete_all_only_own(self):
        """Only deletes current user's conversations."""
        from core.api.routes.chat import delete_all_conversations

        db = _make_session()
        user = _user()
        _make_conversation(db, user_id=user["sub"])
        _make_conversation(db, user_id="other-user")

        result = await delete_all_conversations(user=user, db=db)
        assert result.deleted_count == 1

        # Other user's conversation should still exist
        remaining = db.query(Conversation).filter_by(user_id="other-user").count()
        assert remaining == 1
        db.close()

# ===========================================================================
# add_message_to_conversation endpoint
# ===========================================================================

class TestAddMessage:
    """Tests for POST /conversations/{conversation_id}/messages."""

    @pytest.mark.asyncio
    async def test_add_message_success(self):
        """Adds message to owned conversation."""
        from core.api.routes.chat import AddMessageRequest, add_message_to_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        req = AddMessageRequest(content="Hello world", role="user")

        result = await add_message_to_conversation(
            conversation_id=conv.id, request=req, user=user, db=db
        )
        assert result.content == "Hello world"
        assert result.role == "user"
        db.close()

    @pytest.mark.asyncio
    async def test_add_message_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import AddMessageRequest, add_message_to_conversation

        db = _make_session()
        req = AddMessageRequest(content="Hello", role="user")

        with pytest.raises(HTTPException) as exc:
            await add_message_to_conversation(
                conversation_id=_conv_id(), request=req, user=_user(), db=db
            )
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_add_message_forbidden(self):
        """Returns 403 for another user's conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import AddMessageRequest, add_message_to_conversation

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")
        req = AddMessageRequest(content="Hi", role="user")

        with pytest.raises(HTTPException) as exc:
            await add_message_to_conversation(
                conversation_id=conv.id, request=req, user=_user(sub="user-A"), db=db
            )
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_add_message_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import AddMessageRequest, add_message_to_conversation

        db = _make_session()
        req = AddMessageRequest(content="Hi", role="user")

        with pytest.raises(HTTPException) as exc:
            await add_message_to_conversation(
                conversation_id="bad-uuid", request=req, user=_user(), db=db
            )
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_add_assistant_message(self):
        """Can add assistant messages."""
        from core.api.routes.chat import AddMessageRequest, add_message_to_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        req = AddMessageRequest(content="I am the assistant", role="assistant")

        result = await add_message_to_conversation(
            conversation_id=conv.id, request=req, user=user, db=db
        )
        assert result.role == "assistant"
        db.close()

# ===========================================================================
# share_conversation endpoint
# ===========================================================================

class TestShareConversation:
    """Tests for PATCH /conversations/{conversation_id}/share."""

    @pytest.mark.asyncio
    async def test_share_conversation_success(self):
        """Owner can share conversation."""
        from core.api.routes.chat import ShareConversationRequest, share_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        req = ShareConversationRequest(user_id="user-other", permission="view")

        result = await share_conversation(conversation_id=conv.id, request=req, user=user, db=db)
        assert "message" in result
        db.close()

    @pytest.mark.asyncio
    async def test_share_conversation_not_owner(self):
        """Non-owner cannot share."""
        from fastapi import HTTPException

        from core.api.routes.chat import ShareConversationRequest, share_conversation

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")
        req = ShareConversationRequest(user_id="user-C", permission="view")

        with pytest.raises(HTTPException) as exc:
            await share_conversation(
                conversation_id=conv.id, request=req, user=_user(sub="user-A"), db=db
            )
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_share_conversation_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import ShareConversationRequest, share_conversation

        db = _make_session()
        req = ShareConversationRequest(user_id="user-x", permission="view")

        with pytest.raises(HTTPException) as exc:
            await share_conversation(conversation_id=_conv_id(), request=req, user=_user(), db=db)
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_share_conversation_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import ShareConversationRequest, share_conversation

        db = _make_session()
        req = ShareConversationRequest(user_id="user-x", permission="view")

        with pytest.raises(HTTPException) as exc:
            await share_conversation(conversation_id="bad-uuid", request=req, user=_user(), db=db)
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_share_conversation_update_permission(self):
        """Updates permission if already shared."""
        from core.api.routes.chat import ShareConversationRequest, share_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])

        # Create existing share record
        share = ResourceShare(
            resource_type="conversation",
            resource_id=conv.id,
            user_id="user-other",
            permission="view",
            shared_by=user["sub"],
        )
        db.add(share)
        db.commit()

        # Update to edit permission
        req = ShareConversationRequest(user_id="user-other", permission="edit")
        result = await share_conversation(conversation_id=conv.id, request=req, user=user, db=db)
        assert "message" in result
        db.close()

# ===========================================================================
# unshare_conversation endpoint
# ===========================================================================

class TestUnshareConversation:
    """Tests for DELETE /conversations/{conversation_id}/share/{user_id}."""

    @pytest.mark.asyncio
    async def test_unshare_conversation_success(self):
        """Owner can unshare conversation."""
        from core.api.routes.chat import unshare_conversation

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])

        result = await unshare_conversation(
            conversation_id=conv.id,
            user_id="user-other",
            user=user,
            db=db,
        )
        assert "message" in result
        db.close()

    @pytest.mark.asyncio
    async def test_unshare_conversation_not_owner(self):
        """Non-owner cannot unshare."""
        from fastapi import HTTPException

        from core.api.routes.chat import unshare_conversation

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")

        with pytest.raises(HTTPException) as exc:
            await unshare_conversation(
                conversation_id=conv.id,
                user_id="user-C",
                user=_user(sub="user-A"),
                db=db,
            )
        assert exc.value.status_code == 403
        db.close()

    @pytest.mark.asyncio
    async def test_unshare_conversation_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import unshare_conversation

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await unshare_conversation(
                conversation_id="bad-uuid",
                user_id="user-x",
                user=_user(),
                db=db,
            )
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_unshare_conversation_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import unshare_conversation

        db = _make_session()
        with pytest.raises(HTTPException) as exc:
            await unshare_conversation(
                conversation_id=_conv_id(),
                user_id="user-x",
                user=_user(),
                db=db,
            )
        assert exc.value.status_code == 404
        db.close()

# ===========================================================================
# move_conversation_to_project endpoint
# ===========================================================================

class TestMoveToProject:
    """Tests for PATCH /conversations/{conversation_id}/project."""

    @pytest.mark.asyncio
    async def test_remove_from_project(self):
        """Setting project_id to None removes from project."""
        from core.api.routes.chat import MoveToProjectRequest, move_conversation_to_project

        db = _make_session()
        user = _user()
        conv = _make_conversation(db, user_id=user["sub"])
        req = MoveToProjectRequest(project_id=None)

        result = await move_conversation_to_project(
            conversation_id=conv.id, request=req, user=user, db=db
        )
        assert result.project_id is None
        db.close()

    @pytest.mark.asyncio
    async def test_move_to_project_invalid_uuid(self):
        """Returns 400 for invalid UUID."""
        from fastapi import HTTPException

        from core.api.routes.chat import MoveToProjectRequest, move_conversation_to_project

        db = _make_session()
        req = MoveToProjectRequest(project_id=None)

        with pytest.raises(HTTPException) as exc:
            await move_conversation_to_project(
                conversation_id="bad-uuid", request=req, user=_user(), db=db
            )
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_move_to_project_not_found(self):
        """Returns 404 for non-existent conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import MoveToProjectRequest, move_conversation_to_project

        db = _make_session()
        req = MoveToProjectRequest(project_id=None)

        with pytest.raises(HTTPException) as exc:
            await move_conversation_to_project(
                conversation_id=_conv_id(), request=req, user=_user(), db=db
            )
        assert exc.value.status_code == 404
        db.close()

    @pytest.mark.asyncio
    async def test_move_to_project_forbidden(self):
        """Returns 403 for another user's conversation."""
        from fastapi import HTTPException

        from core.api.routes.chat import MoveToProjectRequest, move_conversation_to_project

        db = _make_session()
        conv = _make_conversation(db, user_id="user-B")
        req = MoveToProjectRequest(project_id=None)

        with pytest.raises(HTTPException) as exc:
            await move_conversation_to_project(
                conversation_id=conv.id, request=req, user=_user(sub="user-A"), db=db
            )
        assert exc.value.status_code == 403
        db.close()

# ===========================================================================
# chat (non-streaming) endpoint
# ===========================================================================

class TestChatEndpoint:
    """Tests for POST / (chat handler)."""

    @pytest.mark.asyncio
    async def test_chat_message_too_large(self):
        """Message with multibyte chars exceeding 10KB (in bytes) returns 400.

        The 10000-char Pydantic limit allows up to 10000 ASCII chars (10KB).
        To test the byte-level check we need a message where bytes > 10240
        but length <= 10000 chars (multibyte unicode characters).
        Each char is 3 bytes, so 3500 * 3 = 10500 bytes > 10240 limit.
        """
        from fastapi import HTTPException

        from core.api.routes.chat import ChatRequest, chat

        db = _make_session()
        # Use 3-byte UTF-8 chars (e.g., '中') — 3500 of them = 10500 bytes > 10240 limit
        multibyte_message = "中" * 3500  # 3500 chars but 10500 bytes
        req = ChatRequest(message=multibyte_message)

        # The 10KB byte check happens before any external calls
        with patch("core.providers.user_config.get_user_llm_config", return_value=None):
            with pytest.raises(HTTPException) as exc:
                await chat(request=req, user=_user(), db=db)
        assert exc.value.status_code == 400
        db.close()

    @pytest.mark.asyncio
    async def test_chat_success(self):
        """Happy path: returns ChatResponse with response text."""
        from core.api.routes.chat import ChatRequest, chat

        db = _make_session()
        req = ChatRequest(message="Hello!")

        async def _fake_route(**kwargs):
            event = MagicMock()
            event.type = "complete"
            event.content = "Hello from assistant"
            event.metadata = {"mode": "chat", "exports": {}}
            yield event

        with patch("core.api.routes.chat.route_request", side_effect=_fake_route):
            with patch("core.providers.user_config.get_user_llm_config", return_value=None):
                with patch("core.extensions.latency_tracker.record_latency"):
                    result = await chat(request=req, user=_user(), db=db)

        assert result.response == "Hello from assistant"
        assert result.mode == "chat"
        db.close()

    @pytest.mark.asyncio
    async def test_chat_service_overloaded(self):
        """RuntimeError with 'queue' raises 503."""
        from fastapi import HTTPException

        from core.api.routes.chat import ChatRequest, chat

        db = _make_session()
        req = ChatRequest(message="Hello!")

        async def _fake_route(**kwargs):
            raise RuntimeError("queue is full and overloaded")
            yield  # make it a generator

        with patch("core.api.routes.chat.route_request", side_effect=_fake_route):
            with patch("core.providers.user_config.get_user_llm_config", return_value=None):
                with pytest.raises(HTTPException) as exc:
                    await chat(request=req, user=_user(), db=db)
        assert exc.value.status_code == 503
        db.close()

    @pytest.mark.asyncio
    async def test_chat_error_event(self):
        """Error event from route_request is included in response."""
        from core.api.routes.chat import ChatRequest, chat

        db = _make_session()
        req = ChatRequest(message="Hello!")

        async def _fake_route(**kwargs):
            event = MagicMock()
            event.type = "error"
            event.content = "LLM unavailable"
            event.metadata = {}
            yield event

        with patch("core.api.routes.chat.route_request", side_effect=_fake_route):
            with patch("core.providers.user_config.get_user_llm_config", return_value=None):
                with patch("core.extensions.latency_tracker.record_latency"):
                    result = await chat(request=req, user=_user(), db=db)

        assert "Error:" in result.response
        db.close()

# ===========================================================================
# Request/Response model validation
# ===========================================================================

class TestChatModels:
    """Tests for Pydantic models in chat module."""

    def test_chat_request_defaults(self):
        """ChatRequest has correct defaults."""
        from core.api.routes.chat import ChatRequest

        req = ChatRequest(message="hello")
        assert req.mode == "chat"
        assert req.enable_thinking is False
        assert req.conversation_id is None

    def test_chat_request_max_length(self):
        """ChatRequest enforces max_length=10000."""
        from pydantic import ValidationError

        from core.api.routes.chat import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 10001)

    def test_chat_request_empty_message(self):
        """ChatRequest allows empty string (no min_length constraint)."""
        from core.api.routes.chat import ChatRequest

        req = ChatRequest(message="")
        assert req.message == ""

    def test_token_usage_defaults(self):
        """TokenUsage has correct defaults."""
        from core.api.routes.chat import TokenUsage

        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_conversation_summary_response(self):
        """ConversationSummary models correctly."""
        from core.api.routes.chat import ConversationSummary

        summary = ConversationSummary(
            id="test-id",
            title="My Convo",
            mode="chat",
            status="active",
            message_count=5,
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        assert summary.id == "test-id"
        assert summary.message_count == 5
