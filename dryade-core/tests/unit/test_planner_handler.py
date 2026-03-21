"""Unit tests for PlannerHandler.

Covers:
- Intent classification (NEW_PLAN, MODIFY_PLAN, CONVERSATION)
- Pre-plan clarification check
- Conversational follow-up handling
- Active plan cache
- Plan generation from user message
- Plan validation (valid, invalid, empty)
- Crash guard error handling (modify_plan, generate_plan)
- Dead code removal verification
- DB persistence and cache-miss reload
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.extensions.events import ChatEvent
from core.orchestrator.handlers.planner_handler import (
    PlannerHandler,
    PlannerIntent,
    classify_planner_intent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    conversation_id: str = "conv-1",
    user_id: str = "user-1",
    metadata: dict | None = None,
):
    """Create a mock ExecutionContext."""
    ctx = MagicMock()
    ctx.conversation_id = conversation_id
    ctx.user_id = user_id
    ctx.metadata = metadata if metadata is not None else {}
    return ctx

def _make_plan(
    name: str = "Test Plan",
    description: str = "A test plan",
    nodes: list | None = None,
    reasoning: str = "test reasoning",
    confidence: float = 0.85,
):
    """Create a mock plan object."""
    plan = MagicMock()
    plan.name = name
    plan.description = description
    if nodes is None:
        node = MagicMock()
        node.id = "step-1"
        node.agent = "test-agent"
        node.task = "do something"
        node.depends_on = []
        nodes = [node]
    plan.nodes = nodes
    plan.reasoning = reasoning
    plan.confidence = confidence
    return plan

async def _collect_events(gen) -> list[ChatEvent]:
    """Collect all events from an async generator."""
    events = []
    async for event in gen:
        events.append(event)
    return events

# ---------------------------------------------------------------------------
# Tests: Handle method (full planner pipeline)
# ---------------------------------------------------------------------------

class TestPlannerHandlerHandle:
    """Tests for PlannerHandler.handle (the full planner pipeline).

    handle() emits plan_data in the complete event metadata for the frontend
    to render PlanCard. Crash guards around modify_plan/generate_plan ensure
    exceptions yield error events instead of crashing the async generator.
    """

    @pytest.mark.asyncio
    async def test_handle_new_plan_emits_plan_data(self):
        """Test successful NEW_PLAN emits token + complete with plan_data in exports."""
        handler = PlannerHandler()
        ctx = _make_context()
        plan = _make_plan()

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("build a thing", ctx))

        event_types = [e.type for e in events]
        assert "token" in event_types
        assert "complete" in event_types

        # Complete event should have plan_data in exports
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("mode") == "planner"
        assert exports.get("intent") == "new_plan"
        plan_data = exports.get("plan_data")
        assert plan_data is not None
        assert plan_data["name"] == "Test Plan"
        assert plan_data["confidence"] == 0.85
        assert plan_data["status"] == "draft"
        assert plan_data["ai_generated"] is True
        assert len(plan_data["nodes"]) == 1
        assert plan_data["nodes"][0]["agent"] == "test-agent"

    @pytest.mark.asyncio
    async def test_handle_modify_plan_emits_plan_data(self):
        """Test MODIFY_PLAN intent emits plan_data with modify_plan intent."""
        handler = PlannerHandler()
        ctx = _make_context(conversation_id="conv-modify")

        original_plan = _make_plan(name="Original Plan")
        handler._active_plans["conv-modify"] = original_plan

        modified_plan = _make_plan(name="Modified Plan")

        mock_planner = MagicMock()
        mock_planner.modify_plan = AsyncMock(return_value=modified_plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("Change step 1 to use agent X", ctx))

        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("intent") == "modify_plan"
        assert exports["plan_data"]["name"] == "Modified Plan"

    @pytest.mark.asyncio
    async def test_handle_invalid_plan(self):
        """Test plan validation failure yields error event."""
        handler = PlannerHandler()
        ctx = _make_context()
        plan = _make_plan()

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(False, ["missing steps", "bad node"]))

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("build a thing", ctx))

        error_events = [e for e in events if e.type == "error"]
        assert len(error_events) == 1
        assert "missing steps" in error_events[0].content
        assert error_events[0].metadata["code"] == "PLAN_VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_handle_no_stream(self):
        """Test handle with stream=False skips token events for plan summary."""
        handler = PlannerHandler()
        ctx = _make_context()
        plan = _make_plan()

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("build", ctx, stream=False))

        # "Analyzing request..." token should NOT appear when stream=False
        analyzing_tokens = [
            e for e in events if e.type == "token" and "Analyzing" in (e.content or "")
        ]
        assert len(analyzing_tokens) == 0

        # Complete event should still be emitted with plan_data
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("plan_data") is not None

    @pytest.mark.asyncio
    async def test_handle_caches_active_plan(self):
        """Test that handle() caches the generated plan for future modify/conversation."""
        handler = PlannerHandler()
        ctx = _make_context(conversation_id="conv-cache")
        plan = _make_plan(name="Cached Plan")

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        # Simulate plan being an ExecutionPlan type (patch at source module for deferred import)
        with (
            patch("core.orchestrator.planner.get_planner", return_value=mock_planner),
            patch("core.orchestrator.models.ExecutionPlan", type(plan)),
        ):
            await _collect_events(handler.handle("build something", ctx))

        # Plan should be cached for this conversation
        assert "conv-cache" in handler._active_plans

    @pytest.mark.asyncio
    async def test_handle_plan_data_edges_from_depends_on(self):
        """Test that plan_data edges are correctly derived from node depends_on."""
        handler = PlannerHandler()
        ctx = _make_context()

        node1 = MagicMock()
        node1.id = "step-1"
        node1.agent = "agent-a"
        node1.task = "first task"
        node1.depends_on = []

        node2 = MagicMock()
        node2.id = "step-2"
        node2.agent = "agent-b"
        node2.task = "second task"
        node2.depends_on = ["step-1"]

        plan = _make_plan(nodes=[node1, node2])

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("build", ctx))

        complete_events = [e for e in events if e.type == "complete"]
        exports = complete_events[0].metadata.get("exports", {})
        plan_data = exports["plan_data"]

        assert len(plan_data["nodes"]) == 2
        assert len(plan_data["edges"]) == 1
        assert plan_data["edges"][0] == {"source": "step-1", "target": "step-2"}

# ---------------------------------------------------------------------------
# Tests: Crash Guard Error Handling
# ---------------------------------------------------------------------------

class TestCrashGuards:
    """Tests for crash guards around modify_plan and generate_plan."""

    @pytest.mark.asyncio
    async def test_handle_modify_plan_error_yields_error_event(self):
        """modify_plan raising RuntimeError yields emit_error with PLAN_MODIFY_ERROR."""
        handler = PlannerHandler()
        ctx = _make_context(conversation_id="conv-err-modify")

        original_plan = _make_plan(name="Original")
        handler._active_plans["conv-err-modify"] = original_plan

        mock_planner = MagicMock()
        mock_planner.modify_plan = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("Change step 1 to use agent X", ctx))

        error_events = [e for e in events if e.type == "error"]
        assert len(error_events) == 1
        assert "PLAN_MODIFY_ERROR" == error_events[0].metadata["code"]
        assert "LLM timeout" in error_events[0].content

    @pytest.mark.asyncio
    async def test_handle_generate_plan_error_yields_error_event(self):
        """generate_plan raising RuntimeError yields emit_error with PLAN_GENERATE_ERROR."""
        handler = PlannerHandler()
        ctx = _make_context(metadata={"history": []})

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(side_effect=RuntimeError("connection refused"))
        mock_planner.get_available_capabilities = MagicMock(return_value=[])

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            events = await _collect_events(handler.handle("build a deployment pipeline", ctx))

        error_events = [e for e in events if e.type == "error"]
        assert len(error_events) == 1
        assert "PLAN_GENERATE_ERROR" == error_events[0].metadata["code"]
        assert "connection refused" in error_events[0].content

    def test_dead_methods_removed(self):
        """Verify dead methods are no longer on PlannerHandler."""
        dead_methods = [
            "_execute_flow",
            "_request_approval",
            "_save_plan",
            "_update_plan_status",
            "_update_execution_result",
            "_topological_sort",
        ]
        for method_name in dead_methods:
            assert not hasattr(PlannerHandler, method_name), (
                f"Dead method {method_name} should have been removed from PlannerHandler"
            )

# ---------------------------------------------------------------------------
# Tests: Intent Classification
# ---------------------------------------------------------------------------

class TestClassifyPlannerIntent:
    """Tests for classify_planner_intent function."""

    def test_no_active_plan_returns_new_plan(self):
        """Without an active plan, all messages return NEW_PLAN."""
        assert classify_planner_intent("anything", False) == PlannerIntent.NEW_PLAN
        assert classify_planner_intent("change step 3", False) == PlannerIntent.NEW_PLAN
        assert classify_planner_intent("what does step 2 do?", False) == PlannerIntent.NEW_PLAN

    def test_explicit_new_plan_keywords(self):
        """With active plan, explicit new plan keywords return NEW_PLAN."""
        assert (
            classify_planner_intent("Create a new plan for deployment", True)
            == PlannerIntent.NEW_PLAN
        )
        assert classify_planner_intent("Start over", True) == PlannerIntent.NEW_PLAN
        assert classify_planner_intent("Plan something different", True) == PlannerIntent.NEW_PLAN
        assert classify_planner_intent("Generate a plan for CI/CD", True) == PlannerIntent.NEW_PLAN

    def test_modify_keywords(self):
        """With active plan, modification keywords return MODIFY_PLAN."""
        assert (
            classify_planner_intent("Change step 3 to use agent X", True)
            == PlannerIntent.MODIFY_PLAN
        )
        assert (
            classify_planner_intent("Add a step for error handling", True)
            == PlannerIntent.MODIFY_PLAN
        )
        assert classify_planner_intent("Remove the last step", True) == PlannerIntent.MODIFY_PLAN
        assert (
            classify_planner_intent("Use agent Y instead of agent X", True)
            == PlannerIntent.MODIFY_PLAN
        )

    def test_conversation_keywords(self):
        """With active plan, questions return CONVERSATION."""
        assert classify_planner_intent("What does step 2 do?", True) == PlannerIntent.CONVERSATION
        assert classify_planner_intent("Explain the reasoning", True) == PlannerIntent.CONVERSATION
        assert (
            classify_planner_intent("How long will this take?", True) == PlannerIntent.CONVERSATION
        )
        assert (
            classify_planner_intent("Why did you choose that agent?", True)
            == PlannerIntent.CONVERSATION
        )

    def test_default_with_active_plan(self):
        """With active plan, ambiguous messages default to MODIFY_PLAN."""
        assert classify_planner_intent("Something else entirely", True) == PlannerIntent.MODIFY_PLAN

# ---------------------------------------------------------------------------
# Tests: Active Plan Cache
# ---------------------------------------------------------------------------

class TestActivePlansCache:
    """Tests for PlannerHandler active plans cache."""

    def test_handler_has_active_plans_cache(self):
        handler = PlannerHandler()
        assert hasattr(handler, "_active_plans")
        assert isinstance(handler._active_plans, dict)
        assert len(handler._active_plans) == 0

# ---------------------------------------------------------------------------
# Tests: Pre-Plan Clarification Check
# ---------------------------------------------------------------------------

class TestCheckNeedsClarification:
    """Tests for PlannerHandler._check_needs_clarification."""

    @pytest.mark.asyncio
    async def test_returns_none_no_capabilities(self):
        """Returns None when no capabilities are available."""
        handler = PlannerHandler()
        ctx = _make_context()

        mock_planner = MagicMock()
        mock_planner.get_available_capabilities = MagicMock(return_value=[])

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            result = await handler._check_needs_clarification("build something", ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_questions_when_unclear(self):
        """Returns clarification questions when LLM says request is unclear."""
        handler = PlannerHandler()
        ctx = _make_context(metadata={"history": []})

        mock_planner = MagicMock()
        mock_planner.get_available_capabilities = MagicMock(
            return_value=[{"agent": "test-agent", "description": "A test agent"}]
        )
        mock_planner.llm.call = MagicMock(
            return_value='{"clear": false, "questions": "What format do you want?"}'
        )

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            result = await handler._check_needs_clarification("do something", ctx)

        assert result == "What format do you want?"

    @pytest.mark.asyncio
    async def test_returns_none_when_clear(self):
        """Returns None when LLM says request is clear enough."""
        handler = PlannerHandler()
        ctx = _make_context(metadata={"history": []})

        mock_planner = MagicMock()
        mock_planner.get_available_capabilities = MagicMock(
            return_value=[{"agent": "test-agent", "description": "A test agent"}]
        )
        mock_planner.llm.call = MagicMock(return_value='{"clear": true}')

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            result = await handler._check_needs_clarification("analyze file.txt", ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_parse_error(self):
        """Returns None (fail open) when LLM returns unparseable response."""
        handler = PlannerHandler()
        ctx = _make_context(metadata={"history": []})

        mock_planner = MagicMock()
        mock_planner.get_available_capabilities = MagicMock(
            return_value=[{"agent": "test-agent", "description": "A test agent"}]
        )
        mock_planner.llm.call = MagicMock(return_value="not json at all")

        with patch("core.orchestrator.planner.get_planner", return_value=mock_planner):
            result = await handler._check_needs_clarification("build something", ctx)

        assert result is None

# ---------------------------------------------------------------------------
# Tests: Conversation Intent Handling
# ---------------------------------------------------------------------------

class TestConversationIntentHandling:
    """Tests for CONVERSATION intent in PlannerHandler.handle."""

    @pytest.mark.asyncio
    async def test_conversation_yields_chat_response(self):
        """CONVERSATION intent yields chat response, not a plan."""
        handler = PlannerHandler()
        ctx = _make_context(conversation_id="conv-chat")
        plan = _make_plan()

        # Set active plan for this conversation
        handler._active_plans["conv-chat"] = plan

        with (
            patch("core.orchestrator.planner.get_planner", return_value=MagicMock()),
            patch.object(
                handler,
                "_chat_about_plan",
                new_callable=AsyncMock,
                return_value="Step 2 uses the analyzer agent.",
            ),
        ):
            events = await _collect_events(handler.handle("What does step 2 do?", ctx))

        # Should have token + complete events
        event_types = [e.type for e in events]
        assert "token" in event_types
        assert "complete" in event_types

        # Complete event should have conversation intent
        complete_events = [e for e in events if e.type == "complete"]
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("intent") == "conversation"

        # Content should be the chat response
        assert "analyzer agent" in complete_events[0].content

# ---------------------------------------------------------------------------
# Tests: DB Persistence and Cache-Miss Reload
# ---------------------------------------------------------------------------

class TestDBPersistence:
    """Tests for DB-backed plan persistence and cache-miss reload."""

    @pytest.mark.asyncio
    async def test_load_plan_from_db_on_cache_miss(self):
        """When _active_plans cache misses, handler loads from DB and caches."""
        handler = PlannerHandler()
        ctx = _make_context(conversation_id="conv-db-load")

        # Create a mock DB plan
        mock_db_plan = MagicMock()
        mock_db_plan.id = 42
        mock_db_plan.name = "DB Plan"
        mock_db_plan.description = "Plan from database"
        mock_db_plan.nodes = [
            {"id": "step1", "agent": "research", "task": "test", "depends_on": []}
        ]
        mock_db_plan.reasoning = "DB reasoning"
        mock_db_plan.confidence = 0.9

        # Mock the DB query chain
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_db_plan

        mock_session = MagicMock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("core.database.session.get_session", return_value=mock_session):
            plan = handler._load_plan_from_db("conv-db-load")

        assert plan is not None
        assert plan.name == "DB Plan"
        assert plan.description == "Plan from database"
        assert len(plan.nodes) == 1
        assert plan.nodes[0].id == "step1"
        assert plan.nodes[0].agent == "research"
        assert plan._db_id == 42

    @pytest.mark.asyncio
    async def test_save_plan_to_db_on_generation(self):
        """After plan generation, _save_plan_to_db is called."""
        handler = PlannerHandler()
        ctx = _make_context(metadata={"user_id": "user-1"})
        plan = _make_plan()

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with (
            patch("core.orchestrator.planner.get_planner", return_value=mock_planner),
            patch("core.orchestrator.models.ExecutionPlan", type(plan)),
            patch.object(handler, "_save_plan_to_db") as mock_save,
            patch.object(handler, "_load_plan_from_db", return_value=None),
        ):
            events = await _collect_events(handler.handle("build something", ctx))

        # _save_plan_to_db should have been called
        mock_save.assert_called_once_with(plan, "conv-1", "user-1")

        # Should still have complete event with plan_data
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("plan_data") is not None

    @pytest.mark.asyncio
    async def test_load_plan_from_db_returns_none_gracefully(self):
        """When DB query returns None, active_plan stays None and NEW_PLAN path runs."""
        handler = PlannerHandler()
        ctx = _make_context(conversation_id="conv-no-db")
        plan = _make_plan()

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with (
            patch("core.orchestrator.planner.get_planner", return_value=mock_planner),
            patch.object(handler, "_load_plan_from_db", return_value=None),
        ):
            events = await _collect_events(handler.handle("build a deployment pipeline", ctx))

        # Should follow NEW_PLAN path (no active plan)
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("intent") == "new_plan"

    @pytest.mark.asyncio
    async def test_save_plan_to_db_error_does_not_crash(self):
        """If DB session raises inside _save_plan_to_db, handler continues normally."""
        handler = PlannerHandler()
        ctx = _make_context(metadata={"user_id": "user-1"})
        plan = _make_plan()

        mock_planner = MagicMock()
        mock_planner.generate_plan = AsyncMock(return_value=plan)
        mock_planner.validate_plan = AsyncMock(return_value=(True, []))

        with (
            patch("core.orchestrator.planner.get_planner", return_value=mock_planner),
            patch("core.orchestrator.models.ExecutionPlan", type(plan)),
            patch(
                "core.database.session.get_session",
                side_effect=RuntimeError("DB down"),
            ),
            patch.object(handler, "_load_plan_from_db", return_value=None),
        ):
            events = await _collect_events(handler.handle("build something", ctx))

        # Plan should still be in _active_plans cache
        assert "conv-1" in handler._active_plans

        # emit_complete should still be yielded
        complete_events = [e for e in events if e.type == "complete"]
        assert len(complete_events) == 1
        exports = complete_events[0].metadata.get("exports", {})
        assert exports.get("plan_data") is not None
