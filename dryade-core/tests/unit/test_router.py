"""Unit tests for ExecutionRouter module.

Updated for Phase 85 simplified 2-path architecture:
- 2 modes: PLANNER, ORCHESTRATE
- Handlers: PlannerHandler, OrchestrateHandler
- No classifier, no ChatHandler

Tests cover:
- Router initialization (2 handlers, no classifier)
- Route delegation (orchestrate and planner modes)
- Exception handling in route()
- Escalation handling (approval/rejection flow)
- route_request() convenience function: default mode, overrides, legacy mapping
- Frontend "chat" -> ORCHESTRATE contract
- Metadata passing
- History fetch present
- ExecutionMode enum values
- Lightweight system prompt token cost regression (<3K tokens)
"""

from unittest.mock import MagicMock, patch

import pytest

# Pre-load the router module. The core.orchestrator.__init__ imports
# DryadeOrchestrator which pulls in sentence_transformers (not installed
# in unit-test environment). We catch the error so that the submodules
# that loaded successfully (router, handlers, models) stay in sys.modules
# and are importable for all tests.
try:
    import core.orchestrator.router  # noqa: F401
except (ImportError, ModuleNotFoundError):
    pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def collect_events(gen):
    """Collect all events from an async generator."""
    events = []
    async for event in gen:
        events.append(event)
    return events

# ---------------------------------------------------------------------------
# TestExecutionRouter
# ---------------------------------------------------------------------------

class TestExecutionRouter:
    """Tests for ExecutionRouter initialization and routing."""

    def test_router_init_creates_two_handlers(self):
        """Instantiate ExecutionRouter and verify it has exactly 2 handlers.

        Plan test (a): Verify _planner_handler (PlannerHandler) and
        _orchestrate_handler (TierDispatcher). Verify it does NOT have
        _chat_handler or classifier.
        """
        from core.orchestrator.router import ExecutionRouter

        router = ExecutionRouter()

        # Check handler types by class name
        assert type(router._planner_handler).__name__ == "PlannerHandler"
        assert type(router._orchestrate_handler).__name__ == "TierDispatcher"
        # Verify they have handle methods (the handler interface)
        assert hasattr(router._planner_handler, "handle")
        assert hasattr(router._orchestrate_handler, "handle")
        # No chat handler or classifier
        assert not hasattr(router, "_chat_handler")
        assert not hasattr(router, "classifier")

    @pytest.mark.asyncio
    async def test_route_delegates_to_orchestrate_for_default(self):
        """Plan test (b): ORCHESTRATE mode delegates to _orchestrate_handler."""
        from core.extensions.events import emit_complete
        from core.orchestrator.router import ExecutionContext, ExecutionMode, ExecutionRouter

        router = ExecutionRouter()

        # Mock orchestrate handler
        async def mock_handle(*args, **kwargs):
            yield emit_complete("orchestrate response")

        router._orchestrate_handler.handle = mock_handle

        ctx = ExecutionContext(conversation_id="conv-1", mode=ExecutionMode.ORCHESTRATE)
        events = await collect_events(router.route("hello", ctx))

        assert len(events) == 1
        assert events[0].type == "complete"
        assert events[0].content == "orchestrate response"

    @pytest.mark.asyncio
    async def test_route_delegates_to_planner(self):
        """Plan test (c): PLANNER mode delegates to _planner_handler."""
        from core.extensions.events import emit_complete
        from core.orchestrator.router import ExecutionContext, ExecutionMode, ExecutionRouter

        router = ExecutionRouter()

        # Mock planner handler
        async def mock_handle(*args, **kwargs):
            yield emit_complete("planner response")

        router._planner_handler.handle = mock_handle

        ctx = ExecutionContext(conversation_id="conv-1", mode=ExecutionMode.PLANNER)
        events = await collect_events(router.route("run plan", ctx))

        assert len(events) == 1
        assert events[0].type == "complete"
        assert events[0].content == "planner response"

    @pytest.mark.asyncio
    async def test_route_handles_exception(self):
        """Plan test (d): Exception in handler yields emit_error event."""
        from core.orchestrator.router import ExecutionContext, ExecutionMode, ExecutionRouter

        router = ExecutionRouter()

        # Mock handler that raises
        async def failing_handle(*args, **kwargs):
            raise RuntimeError("boom")
            yield  # make it a generator  # noqa: E501

        router._orchestrate_handler.handle = failing_handle

        ctx = ExecutionContext(conversation_id="conv-1", mode=ExecutionMode.ORCHESTRATE)
        events = await collect_events(router.route("test", ctx))

        assert len(events) == 1
        assert events[0].type == "error"
        assert "RuntimeError" in events[0].content

    @pytest.mark.asyncio
    async def test_escalation_handling_preserved(self):
        """Plan test (e): Escalation response yields events and skips handler.

        When _handle_escalation_response returns events, those are yielded
        and the mode handler is NOT called.
        """
        from core.extensions.events import emit_complete
        from core.orchestrator.router import ExecutionContext, ExecutionMode, ExecutionRouter

        router = ExecutionRouter()

        # Track whether orchestrate handler is called
        handler_called = False

        async def mock_handle(*args, **kwargs):
            nonlocal handler_called
            handler_called = True
            yield emit_complete("should not appear")

        router._orchestrate_handler.handle = mock_handle

        # Mock _handle_escalation_response to return events
        async def mock_escalation_events():
            yield emit_complete("escalation handled")

        async def mock_handle_escalation(message, context):
            return mock_escalation_events()

        router._handle_escalation_response = mock_handle_escalation

        ctx = ExecutionContext(conversation_id="conv-1", mode=ExecutionMode.ORCHESTRATE)
        events = await collect_events(router.route("yes", ctx))

        assert len(events) == 1
        assert events[0].content == "escalation handled"
        assert not handler_called

# ---------------------------------------------------------------------------
# TestRouteRequest
# ---------------------------------------------------------------------------

class TestRouteRequest:
    """Tests for route_request() convenience function."""

    @pytest.mark.asyncio
    async def test_default_mode_is_orchestrate(self):
        """Plan test (f): No mode_override -> ORCHESTRATE."""
        from core.orchestrator.router import ExecutionMode

        ctx = await self._get_context_from_route_request(mode_override=None)
        assert ctx.mode == ExecutionMode.ORCHESTRATE

    @pytest.mark.asyncio
    async def test_planner_override(self):
        """Plan test (g): mode_override='planner' -> PLANNER."""
        from core.orchestrator.router import ExecutionMode

        ctx = await self._get_context_from_route_request(mode_override="planner")
        assert ctx.mode == ExecutionMode.PLANNER

    @pytest.mark.asyncio
    async def test_flow_maps_to_planner(self):
        """Plan test (h): mode_override='flow' -> PLANNER."""
        from core.orchestrator.router import ExecutionMode

        ctx = await self._get_context_from_route_request(mode_override="flow")
        assert ctx.mode == ExecutionMode.PLANNER

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "mode_str",
        ["chat", "orchestrate", "crew", "autonomous", None],
    )
    async def test_legacy_modes_map_to_orchestrate(self, mode_str):
        """Plan test (i): Legacy mode strings map to ORCHESTRATE."""
        from core.orchestrator.router import ExecutionMode

        ctx = await self._get_context_from_route_request(mode_override=mode_str)
        assert ctx.mode == ExecutionMode.ORCHESTRATE

    @pytest.mark.asyncio
    async def test_frontend_chat_maps_to_orchestrate(self):
        """Plan test (i2): Frontend sends 'chat' -> backend uses ORCHESTRATE.

        This is the critical contract between frontend and backend.
        The frontend ChatMode 'chat' must resolve to ExecutionMode.ORCHESTRATE.
        """
        from core.orchestrator.router import ExecutionMode

        ctx = await self._get_context_from_route_request(mode_override="chat")
        assert ctx.mode == ExecutionMode.ORCHESTRATE

    @pytest.mark.asyncio
    async def test_metadata_passed_correctly(self):
        """Plan test (j): Metadata fields are set in context."""
        ctx = await self._get_context_from_route_request(
            mode_override=None,
            enable_thinking=True,
            user_llm_config={"provider": "anthropic", "model": "claude-3"},
            crew_id="analysis_crew",
            leash_preset="conservative",
        )

        assert ctx.metadata["enable_thinking"] is True
        assert ctx.metadata["user_llm_config"] == {"provider": "anthropic", "model": "claude-3"}
        assert ctx.metadata["crew_id"] == "analysis_crew"
        assert ctx.metadata["leash_preset"] == "conservative"

    def test_history_is_fetched(self):
        """Plan test (k): route_request DOES call get_recent_history.

        Verifies that the route_request function source code references
        get_recent_history. Phase 86.3 re-added history fetching at the
        router level (it was removed in Phase 85 but handlers never
        implemented it, leaving a gap).
        """
        import inspect

        from core.orchestrator.router import route_request

        source = inspect.getsource(route_request)
        assert "get_recent_history" in source, (
            "route_request should reference get_recent_history; "
            "history fetching was re-added in Phase 86.3"
        )

    # ---- helper ----

    async def _get_context_from_route_request(
        self,
        mode_override=None,
        enable_thinking=False,
        user_llm_config=None,
        crew_id=None,
        leash_preset=None,
    ):
        """Call route_request, intercept the ExecutionContext passed to router.route().

        We patch get_router().route to capture the context instead of
        actually executing anything.
        """

        captured_ctx = None

        async def capture_route(message, context, stream=True):
            nonlocal captured_ctx
            captured_ctx = context
            return
            yield  # make it an async generator  # noqa: E501

        with patch("core.orchestrator.router.get_router") as mock_get:
            mock_router = MagicMock()
            mock_router.route = capture_route
            mock_get.return_value = mock_router

            from core.orchestrator.router import route_request

            gen = route_request(
                message="test",
                conversation_id="conv-test",
                user_id="user-1",
                mode_override=mode_override,
                enable_thinking=enable_thinking,
                user_llm_config=user_llm_config,
                crew_id=crew_id,
                leash_preset=leash_preset,
            )
            # Consume the generator
            async for _ in gen:
                pass

        assert captured_ctx is not None, "route_request did not call router.route()"
        return captured_ctx

# ---------------------------------------------------------------------------
# TestExecutionMode
# ---------------------------------------------------------------------------

class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_execution_mode_values(self):
        """Plan test (l): Verify enum values and count."""
        from core.orchestrator.router import ExecutionMode

        assert ExecutionMode.PLANNER.value == "planner"
        assert ExecutionMode.ORCHESTRATE.value == "orchestrate"
        assert len(ExecutionMode) == 2  # No CHAT mode

# ---------------------------------------------------------------------------
# TestLightweightTokenCost
# ---------------------------------------------------------------------------

class TestLightweightTokenCost:
    """Regression test for lightweight system prompt token cost."""

    def test_lightweight_system_prompt_under_3k_tokens(self):
        """Plan test (m): Verify lightweight prompt + trivial message < 3K tokens.

        Builds the full system prompt with a realistic set of 6 agent cards
        in lightweight mode, adds LIGHTWEIGHT_AGENT_ADDENDUM, and a trivial
        user message 'bonjour sabine'. Estimates token count with a word-based
        heuristic (words * 1.3).

        This is a regression test: if the lightweight prompt bloats past 3K
        estimated input tokens, this test will catch it.
        """
        from core.adapters.protocol import AgentCard, AgentFramework
        from core.orchestrator.thinking import (
            LIGHTWEIGHT_AGENT_ADDENDUM,
            ORCHESTRATE_SYSTEM_PROMPT,
            _format_agents_xml,
        )

        # Realistic mock agents (names and descriptions matching real ones)
        mock_agents = [
            AgentCard(
                name="mcp-filesystem",
                description="File system operations: list, read, write, search files",
                version="1.0.0",
                framework=AgentFramework.MCP,
            ),
            AgentCard(
                name="mcp-capella",
                description="Capella MBSE model operations: open, query, modify system models",
                version="1.0.0",
                framework=AgentFramework.MCP,
            ),
            AgentCard(
                name="mcp-grafana",
                description="Grafana dashboard and metrics querying",
                version="1.0.0",
                framework=AgentFramework.MCP,
            ),
            AgentCard(
                name="code-reviewer",
                description="Automated code review with best practices analysis",
                version="1.0.0",
                framework=AgentFramework.CREWAI,
            ),
            AgentCard(
                name="database-analyst",
                description="SQL query generation and database schema analysis",
                version="1.0.0",
                framework=AgentFramework.CREWAI,
            ),
            AgentCard(
                name="document-processor",
                description="Document parsing, summarization, and information extraction",
                version="1.0.0",
                framework=AgentFramework.CREWAI,
            ),
        ]

        # Build lightweight agents XML
        agents_xml = _format_agents_xml(mock_agents, lightweight=True)

        # Build full system prompt
        system_prompt = ORCHESTRATE_SYSTEM_PROMPT.format(
            agents_xml=agents_xml,
            environment_info="test environment",
            knowledge_section="",
            knowledge_sources="",
        )
        system_prompt += LIGHTWEIGHT_AGENT_ADDENDUM

        # User message
        user_message = "bonjour sabine"

        # Total input text
        total_input = system_prompt + "\n" + user_message

        # Estimate tokens: words * 1.3 (handles French/English mix)
        word_count = len(total_input.split())
        estimated_tokens = int(word_count * 1.3)

        assert estimated_tokens < 3000, (
            f"Lightweight prompt estimated at {estimated_tokens} tokens "
            f"({word_count} words * 1.3), exceeds 3K limit. "
            f"System prompt length: {len(system_prompt)} chars, "
            f"agents_xml length: {len(agents_xml)} chars."
        )

# ---------------------------------------------------------------------------
# TestModeMap
# ---------------------------------------------------------------------------

class TestModeMap:
    """Tests for _MODE_MAP legacy mode mapping."""

    def test_mode_map_covers_all_legacy_modes(self):
        """Verify _MODE_MAP has correct entries."""
        from core.orchestrator.router import _MODE_MAP, ExecutionMode

        assert _MODE_MAP["planner"] == ExecutionMode.PLANNER
        assert _MODE_MAP["flow"] == ExecutionMode.PLANNER
        assert _MODE_MAP["chat"] == ExecutionMode.ORCHESTRATE
        assert _MODE_MAP["orchestrate"] == ExecutionMode.ORCHESTRATE
        assert _MODE_MAP["crew"] == ExecutionMode.ORCHESTRATE
        assert _MODE_MAP["autonomous"] == ExecutionMode.ORCHESTRATE

    def test_mode_map_has_six_entries(self):
        """Verify _MODE_MAP has exactly 6 entries."""
        from core.orchestrator.router import _MODE_MAP

        assert len(_MODE_MAP) == 6
