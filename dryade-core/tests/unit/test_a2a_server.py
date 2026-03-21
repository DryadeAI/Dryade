"""Unit tests for A2A server: protocol models, task store, and executor bridge."""

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.a2a.models import (
    JSONRPC_INVALID_PARAMS,
    JSONRPC_METHOD_NOT_FOUND,
    A2AAgentCard,
    A2AJsonRpcRequest,
    A2AMessage,
    A2APart,
    A2ATask,
    A2ATaskStatus,
    jsonrpc_error,
)
from core.a2a.task_store import A2ATaskStore
from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework, AgentResult

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def mock_agent():
    """Create a mock UniversalAgent."""
    agent = MagicMock()
    agent.get_card.return_value = AgentCard(
        name="test_agent",
        description="A test agent for A2A server tests",
        version="1.0.0",
        framework=AgentFramework.CUSTOM,
        capabilities=[
            AgentCapability(name="echo", description="Echo input back"),
        ],
        skills=["testing"],
    )
    agent.execute = AsyncMock(return_value=AgentResult(result="Test output", status="ok"))
    agent.supports_streaming.return_value = False
    return agent

@pytest.fixture()
def mock_registry(mock_agent):
    """Patch registry to return mock agent."""
    with (
        patch("core.a2a.executor.get_registry") as mock_reg,
        patch("core.a2a.executor.get_agent") as mock_get,
    ):
        registry = MagicMock()
        registry.list_agents.return_value = [mock_agent.get_card()]
        mock_reg.return_value = registry
        mock_get.return_value = mock_agent
        yield {"registry": mock_reg, "get_agent": mock_get, "agent": mock_agent}

@pytest.fixture()
def task_store():
    """Create a fresh task store."""
    return A2ATaskStore(ttl_seconds=60)

# ------------------------------------------------------------------
# Model validation tests
# ------------------------------------------------------------------

@pytest.mark.unit
class TestA2AModels:
    """Tests for A2A protocol Pydantic models."""

    def test_a2a_jsonrpc_request_valid(self):
        """A2AJsonRpcRequest validates correct input."""
        req = A2AJsonRpcRequest(jsonrpc="2.0", method="message/send", params={}, id="1")
        assert req.jsonrpc == "2.0"
        assert req.method == "message/send"
        assert req.id == "1"

    def test_a2a_jsonrpc_request_rejects_bad_version(self):
        """A2AJsonRpcRequest rejects non-2.0 jsonrpc."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            A2AJsonRpcRequest(jsonrpc="1.0", method="test", params={}, id="1")

    def test_a2a_jsonrpc_request_integer_id(self):
        """A2AJsonRpcRequest accepts integer id."""
        req = A2AJsonRpcRequest(jsonrpc="2.0", method="test", params={}, id=42)
        assert req.id == 42

    def test_a2a_task_model(self):
        """A2ATask validates correctly."""
        task = A2ATask(
            id="t1",
            contextId="c1",
            status=A2ATaskStatus(state="completed"),
        )
        assert task.kind == "task"
        assert task.artifacts == []

    def test_a2a_message_model(self):
        """A2AMessage validates correctly."""
        msg = A2AMessage(role="user", parts=[A2APart(text="hello")])
        assert msg.role == "user"
        assert msg.parts[0].text == "hello"

    def test_a2a_agent_card_defaults(self):
        """A2AAgentCard has correct defaults."""
        card = A2AAgentCard(name="Test", description="test", url="http://localhost/a2a")
        assert card.protocolVersion == "0.3.0"
        assert card.provider["organization"] == "Dryade"
        assert card.capabilities["streaming"] is True
        assert card.defaultInputModes == ["text"]

# ------------------------------------------------------------------
# JSON-RPC error helper tests
# ------------------------------------------------------------------

@pytest.mark.unit
class TestJsonRpcErrorHelper:
    """Tests for jsonrpc_error helper."""

    def test_jsonrpc_error_shape(self):
        """jsonrpc_error returns correct dict shape."""
        result = jsonrpc_error("1", JSONRPC_METHOD_NOT_FOUND, "Not found")
        assert result == {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Not found"},
            "id": "1",
        }

    def test_jsonrpc_error_none_id(self):
        """jsonrpc_error handles None id (parse errors)."""
        result = jsonrpc_error(None, -32700, "Parse error")
        assert result["id"] is None

    def test_unknown_method_error_code(self):
        """JSONRPC_METHOD_NOT_FOUND is -32601."""
        assert JSONRPC_METHOD_NOT_FOUND == -32601

# ------------------------------------------------------------------
# Agent card generation tests
# ------------------------------------------------------------------

@pytest.mark.unit
class TestAgentCardGeneration:
    """Tests for build_a2a_agent_card."""

    def test_agent_card_generation(self, mock_registry):
        """build_a2a_agent_card returns valid card."""
        from core.a2a.executor import build_a2a_agent_card

        card = build_a2a_agent_card("http://localhost:8000")
        assert card["protocolVersion"] == "0.3.0"
        assert card["url"] == "http://localhost:8000/a2a"
        assert card["provider"]["organization"] == "Dryade"
        assert isinstance(card["skills"], list)

    def test_agent_card_skills_from_registry(self, mock_registry):
        """Agents are mapped to skills in the card."""
        from core.a2a.executor import build_a2a_agent_card

        card = build_a2a_agent_card("http://localhost:8000")
        assert len(card["skills"]) == 1
        assert card["skills"][0]["id"] == "test_agent"
        assert "custom" in card["skills"][0]["tags"]

    def test_agent_card_empty_registry(self):
        """Empty registry produces card with no skills."""
        from core.a2a.executor import build_a2a_agent_card

        with patch("core.a2a.executor.get_registry") as mock_reg:
            registry = MagicMock()
            registry.list_agents.return_value = []
            mock_reg.return_value = registry

            card = build_a2a_agent_card("http://localhost:8000")
            assert card["skills"] == []

# ------------------------------------------------------------------
# Message send tests
# ------------------------------------------------------------------

@pytest.mark.unit
class TestMessageSend:
    """Tests for handle_message_send."""

    @pytest.mark.asyncio
    async def test_message_send_executes_agent(self, mock_registry):
        """handle_message_send dispatches to agent and returns task."""
        from core.a2a.executor import handle_message_send

        result = await handle_message_send(
            {"message": {"role": "user", "parts": [{"text": "hello"}]}}
        )
        assert result["status"]["state"] == "completed"
        assert result["kind"] == "task"
        assert "id" in result
        assert "contextId" in result
        mock_registry["agent"].execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_send_invalid_skill(self, mock_registry):
        """handle_message_send raises ValueError for unknown skill."""
        from core.a2a.executor import handle_message_send

        mock_registry["get_agent"].return_value = None

        with pytest.raises(ValueError, match="Unknown skill"):
            await handle_message_send(
                {
                    "message": {"role": "user", "parts": [{"text": "hello"}]},
                    "metadata": {"skillId": "nonexistent"},
                }
            )

    @pytest.mark.asyncio
    async def test_message_send_no_text(self, mock_registry):
        """handle_message_send raises ValueError for empty message."""
        from core.a2a.executor import handle_message_send

        with pytest.raises(ValueError, match="No message text"):
            await handle_message_send({"message": {"role": "user", "parts": []}})

# ------------------------------------------------------------------
# Tasks get / cancel tests
# ------------------------------------------------------------------

@pytest.mark.unit
class TestTasksGetCancel:
    """Tests for handle_tasks_get and handle_tasks_cancel."""

    @pytest.mark.asyncio
    async def test_tasks_get(self, mock_registry):
        """handle_tasks_get retrieves a stored task."""
        from core.a2a.executor import handle_message_send, handle_tasks_get

        task = await handle_message_send(
            {"message": {"role": "user", "parts": [{"text": "hello"}]}}
        )
        task_id = task["id"]

        retrieved = await handle_tasks_get({"id": task_id})
        assert retrieved["id"] == task_id
        assert retrieved["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_tasks_get_unknown(self):
        """handle_tasks_get raises ValueError for unknown task."""
        from core.a2a.executor import handle_tasks_get

        with pytest.raises(ValueError, match="Task not found"):
            await handle_tasks_get({"id": "nonexistent-task-id"})

    @pytest.mark.asyncio
    async def test_tasks_cancel(self, mock_registry):
        """handle_tasks_cancel marks task as canceled."""
        from core.a2a.executor import handle_message_send, handle_tasks_cancel

        task = await handle_message_send(
            {"message": {"role": "user", "parts": [{"text": "hello"}]}}
        )
        task_id = task["id"]

        canceled = await handle_tasks_cancel({"id": task_id})
        assert canceled["status"]["state"] == "canceled"

# ------------------------------------------------------------------
# Task store tests
# ------------------------------------------------------------------

@pytest.mark.unit
class TestTaskStore:
    """Tests for A2ATaskStore."""

    def test_task_store_ttl(self):
        """Expired tasks return None."""
        store = A2ATaskStore(ttl_seconds=0)
        store.store("t1", {"id": "t1", "status": {"state": "completed"}})
        # TTL=0 means instant expiry on next access
        assert store.get("t1") is None

    def test_task_store_basic_operations(self, task_store):
        """Store, get, update, and cancel work correctly."""
        task_store.store("t1", {"id": "t1", "status": {"state": "working"}})
        assert task_store.get("t1") is not None
        assert task_store.get("t1")["status"]["state"] == "working"

        task_store.update_status("t1", "completed")
        assert task_store.get("t1")["status"]["state"] == "completed"

        assert task_store.cancel("t1") is True
        assert task_store.get("t1")["status"]["state"] == "canceled"

    def test_task_store_unknown_returns_none(self, task_store):
        """Getting unknown task returns None."""
        assert task_store.get("nonexistent") is None

    def test_task_store_cancel_unknown_returns_false(self, task_store):
        """Canceling unknown task returns False."""
        assert task_store.cancel("nonexistent") is False

    def test_task_store_len(self, task_store):
        """__len__ returns correct count."""
        assert len(task_store) == 0
        task_store.store("t1", {"id": "t1"})
        assert len(task_store) == 1

    def test_task_store_thread_safety(self):
        """Concurrent operations don't raise exceptions."""
        store = A2ATaskStore(ttl_seconds=60)
        errors = []

        def worker(thread_id):
            try:
                for i in range(20):
                    tid = f"t-{thread_id}-{i}"
                    store.store(tid, {"id": tid, "status": {"state": "working"}})
                    store.get(tid)
                    store.cancel(tid)
                    len(store)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"
