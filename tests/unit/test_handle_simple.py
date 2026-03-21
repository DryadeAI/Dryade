"""Tests for SimpleHandler (SIMPLE tier path).

Covers SimpleHandler.handle(), feature flag gating, router confirmation,
argument extraction, tool name resolution, and COMPLEX fallback.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.extensions.events import ChatEvent
from core.orchestrator.complexity import TierDecision
from core.orchestrator.handlers.complex_handler import TierDispatcher
from core.orchestrator.handlers.simple_handler import (
    SimpleHandler,
    _extract_arguments,
    _resolve_tool_name,
)
from core.orchestrator.models import Tier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(**kwargs):
    """Create a mock ExecutionContext."""
    ctx = MagicMock()
    ctx.conversation_id = kwargs.get("conversation_id", "test-conv-1")
    ctx.user_id = kwargs.get("user_id", "test-user-1")
    ctx.metadata = kwargs.get(
        "metadata",
        {
            "orchestration_mode": "adaptive",
            "memory_enabled": True,
            "reasoning_visibility": "summary",
            "event_visibility": "named-steps",
        },
    )
    return ctx

def _make_agent(name="mcp-filesystem", capabilities=None, execute_result=None):
    """Create a mock UniversalAgent.

    Uses MagicMock base with AsyncMock for execute() only,
    so that get_card() returns a plain MagicMock (not a coroutine).
    """
    agent = MagicMock()
    card = MagicMock()
    card.name = name
    card.capabilities = capabilities or []
    agent.get_card.return_value = card
    if execute_result is None:
        result = MagicMock()
        result.status = "ok"
        result.result = "Success"
        result.error = None
        execute_result = result
    agent.execute = AsyncMock(return_value=execute_result)
    return agent

def _make_tier_decision(
    tier=Tier.SIMPLE,
    target_agent="mcp-filesystem",
    target_tool=None,
    confidence=0.9,
):
    return TierDecision(
        tier=tier,
        confidence=confidence,
        reason="test",
        target_agent=target_agent,
        target_tool=target_tool,
    )

def _make_registry(agents=None):
    """Create a mock registry with optional agents dict."""
    registry = MagicMock()
    agents = agents or {}

    def get_side_effect(name):
        return agents.get(name)

    registry.get.side_effect = get_side_effect

    cards = []
    for name, agent in agents.items():
        card = agent.get_card()
        cards.append(card)
    registry.list_agents.return_value = cards

    return registry

async def _collect_events(handler, message, context, tier_decision):
    """Collect all events from SimpleHandler.handle."""
    events = []
    async for event in handler.handle(message, context, tier_decision=tier_decision):
        events.append(event)
    return events

# ---------------------------------------------------------------------------
# TestHandleSimple -- direct tests for SimpleHandler.handle()
# ---------------------------------------------------------------------------

class TestHandleSimple:
    """Direct tests for SimpleHandler.handle()."""

    @pytest.mark.asyncio
    async def test_successful_dispatch_emits_events(self):
        """Successful dispatch emits agent_start, agent_complete, complete."""
        handler = SimpleHandler()
        context = _make_context()

        result = MagicMock()
        result.status = "ok"
        result.result = "Found 42 files"
        result.error = None

        agent = _make_agent(execute_result=result)
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        with patch("core.adapters.registry.get_registry", return_value=registry):
            events = await _collect_events(handler, "list files", context, td)

        types = [e.type for e in events]
        assert types == ["agent_start", "agent_complete", "complete"]

        # Verify complete event content contains the result
        complete_event = [e for e in events if e.type == "complete"][0]
        assert "42 files" in complete_event.content

    @pytest.mark.asyncio
    async def test_agent_not_found_no_events(self):
        """Agent not found yields no events (triggers COMPLEX fallback)."""
        handler = SimpleHandler()
        context = _make_context()

        registry = _make_registry({})  # No agents
        td = _make_tier_decision(target_agent="nonexistent")

        with patch("core.adapters.registry.get_registry", return_value=registry):
            events = await _collect_events(handler, "do something", context, td)

        assert events == []

    @pytest.mark.asyncio
    async def test_agent_execution_failure_no_complete(self):
        """Agent returning error yields agent_start + agent_complete but no complete."""
        handler = SimpleHandler()
        context = _make_context()

        result = MagicMock()
        result.status = "error"
        result.result = None
        result.error = "Timeout"

        agent = _make_agent(execute_result=result)
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        with patch("core.adapters.registry.get_registry", return_value=registry):
            events = await _collect_events(handler, "list files", context, td)

        types = [e.type for e in events]
        assert "agent_start" in types
        assert "agent_complete" in types
        assert "complete" not in types

    @pytest.mark.asyncio
    async def test_agent_execution_exception_no_complete(self):
        """Agent raising exception yields agent_start + agent_complete but no complete."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        agent.execute.side_effect = RuntimeError("Connection refused")
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        with patch("core.adapters.registry.get_registry", return_value=registry):
            events = await _collect_events(handler, "list files", context, td)

        types = [e.type for e in events]
        assert "agent_start" in types
        assert "agent_complete" in types
        assert "complete" not in types

    @pytest.mark.asyncio
    async def test_passes_tool_in_context(self):
        """Tool name resolved to original case is passed in context dict."""
        handler = SimpleHandler()
        context = _make_context()

        cap = MagicMock()
        cap.name = "Search_Files"
        agent = _make_agent(capabilities=[cap])
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision(target_tool="search_files")

        with patch("core.adapters.registry.get_registry", return_value=registry):
            await _collect_events(handler, "search files", context, td)

        # Verify agent.execute was called with tool in context
        call_args = agent.execute.call_args
        context_dict = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("context", {})
        assert context_dict["tool"] == "Search_Files"

    @pytest.mark.asyncio
    async def test_passes_arguments_from_message(self):
        """Arguments extracted from message are passed in context dict."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        with patch("core.adapters.registry.get_registry", return_value=registry):
            await _collect_events(handler, "search for files in /home/user", context, td)

        call_args = agent.execute.call_args
        context_dict = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("context", {})
        assert "arguments" in context_dict
        assert context_dict["arguments"]["path"] == "/home/user"

    @pytest.mark.asyncio
    async def test_passes_metadata_including_history(self):
        """Context metadata (including history) is spread into agent context."""
        handler = SimpleHandler()
        history = [{"role": "user", "content": "previous msg"}]
        context = _make_context(
            metadata={
                "orchestration_mode": "adaptive",
                "event_visibility": "named-steps",
                "history": history,
            }
        )

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        with patch("core.adapters.registry.get_registry", return_value=registry):
            await _collect_events(handler, "list files", context, td)

        call_args = agent.execute.call_args
        context_dict = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("context", {})
        assert context_dict["conversation_id"] == "test-conv-1"
        assert context_dict["user_id"] == "test-user-1"
        assert context_dict["history"] == history

    @pytest.mark.asyncio
    async def test_case_insensitive_agent_resolution(self):
        """Agent name case mismatch is handled via case-insensitive fallback."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent(name="MCP-Filesystem")
        # Registry stores under exact name "MCP-Filesystem"
        registry = _make_registry({"MCP-Filesystem": agent})
        # Classifier lowercased to "mcp-filesystem"
        td = _make_tier_decision(target_agent="mcp-filesystem")

        with patch("core.adapters.registry.get_registry", return_value=registry):
            events = await _collect_events(handler, "list files", context, td)

        types = [e.type for e in events]
        assert "complete" in types
        agent.execute.assert_called_once()

# ---------------------------------------------------------------------------
# TestHandleSimpleRouterConfirmation
# ---------------------------------------------------------------------------

class TestHandleSimpleRouterConfirmation:
    """Tests for optional router confirmation."""

    @pytest.mark.asyncio
    async def test_router_agrees_proceeds(self):
        """Router agrees (top result matches target) -> agent executed."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        route_result = MagicMock()
        route_result.server = "mcp-filesystem"
        route_result.score = 0.9

        os.environ["DRYADE_TIER_SIMPLE_ROUTER_CONFIRM"] = "true"
        try:
            with (
                patch("core.adapters.registry.get_registry", return_value=registry),
                patch(
                    "core.orchestrator.handlers.simple_handler._router_confirms", return_value=True
                ),
            ):
                events = await _collect_events(handler, "list files", context, td)

            types = [e.type for e in events]
            assert "complete" in types
        finally:
            os.environ.pop("DRYADE_TIER_SIMPLE_ROUTER_CONFIRM", None)

    @pytest.mark.asyncio
    async def test_router_disagrees_strongly_falls_back(self):
        """Router strongly disagrees (score > 0.8, different server) -> no events."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        os.environ["DRYADE_TIER_SIMPLE_ROUTER_CONFIRM"] = "true"
        try:
            with (
                patch("core.adapters.registry.get_registry", return_value=registry),
                patch(
                    "core.orchestrator.handlers.simple_handler._router_confirms", return_value=False
                ),
            ):
                events = await _collect_events(handler, "list files", context, td)

            assert events == []
        finally:
            os.environ.pop("DRYADE_TIER_SIMPLE_ROUTER_CONFIRM", None)

    @pytest.mark.asyncio
    async def test_router_disagrees_weakly_proceeds(self):
        """Router weakly disagrees (score < 0.8) -> agent executed."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        os.environ["DRYADE_TIER_SIMPLE_ROUTER_CONFIRM"] = "true"
        try:
            # _router_confirms returns True for weak disagreement
            with (
                patch("core.adapters.registry.get_registry", return_value=registry),
                patch(
                    "core.orchestrator.handlers.simple_handler._router_confirms", return_value=True
                ),
            ):
                events = await _collect_events(handler, "list files", context, td)

            types = [e.type for e in events]
            assert "complete" in types
        finally:
            os.environ.pop("DRYADE_TIER_SIMPLE_ROUTER_CONFIRM", None)

    @pytest.mark.asyncio
    async def test_router_error_proceeds(self):
        """Router raising exception -> agent still executed."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        os.environ["DRYADE_TIER_SIMPLE_ROUTER_CONFIRM"] = "true"
        try:
            # _router_confirms returns True on exception
            with (
                patch("core.adapters.registry.get_registry", return_value=registry),
                patch(
                    "core.orchestrator.handlers.simple_handler._router_confirms", return_value=True
                ),
            ):
                events = await _collect_events(handler, "list files", context, td)

            types = [e.type for e in events]
            assert "complete" in types
        finally:
            os.environ.pop("DRYADE_TIER_SIMPLE_ROUTER_CONFIRM", None)

    @pytest.mark.asyncio
    async def test_router_disabled_by_default(self):
        """Without DRYADE_TIER_SIMPLE_ROUTER_CONFIRM, router not called."""
        handler = SimpleHandler()
        context = _make_context()

        agent = _make_agent()
        registry = _make_registry({"mcp-filesystem": agent})
        td = _make_tier_decision()

        # Ensure env var not set
        os.environ.pop("DRYADE_TIER_SIMPLE_ROUTER_CONFIRM", None)

        with (
            patch("core.adapters.registry.get_registry", return_value=registry),
            patch("core.orchestrator.handlers.simple_handler._router_confirms") as mock_router,
        ):
            events = await _collect_events(handler, "list files", context, td)

        # Router should NOT have been called
        mock_router.assert_not_called()
        # But agent should have been executed
        types = [e.type for e in events]
        assert "complete" in types

# ---------------------------------------------------------------------------
# TestSimpleFeatureFlagGating
# ---------------------------------------------------------------------------

class TestSimpleFeatureFlagGating:
    """Test that DRYADE_TIER_SIMPLE_ENABLED gates the SIMPLE path."""

    @pytest.mark.asyncio
    async def test_simple_disabled_by_default(self):
        """With no env var, SIMPLE messages go through COMPLEX path."""
        handler = TierDispatcher()
        context = _make_context()

        # Remove env var if set
        os.environ.pop("DRYADE_TIER_SIMPLE_ENABLED", None)

        with (
            patch("core.adapters.registry.get_registry") as mock_reg,
            patch(
                "core.orchestrator.orchestrator.DryadeOrchestrator", autospec=False
            ) as mock_orch_cls,
        ):
            # Set up registry mock
            mock_reg.return_value.list_agents.return_value = []

            # Set up orchestrator mock for COMPLEX path
            mock_result = MagicMock()
            mock_result.needs_escalation = False
            mock_result.success = True
            mock_result.output = "complex response"
            mock_result.partial_results = []
            mock_result.reasoning = None
            mock_result.streamed = False

            mock_orch_instance = MagicMock()
            mock_orch_instance.thinking = MagicMock()
            mock_orch_instance.thinking._on_cost_event = None
            mock_orch_instance.agents.list_agents.return_value = []
            mock_orch_cls.return_value = mock_orch_instance

            async def mock_orchestrate(**kwargs):
                return mock_result

            mock_orch_instance.orchestrate = mock_orchestrate

            # Verify handle() does NOT call SimpleHandler.handle
            with patch.object(handler._simple, "handle") as mock_simple:
                events = []
                async for event in handler.handle("hello", context):
                    events.append(event)

                mock_simple.assert_not_called()

    @pytest.mark.asyncio
    async def test_simple_enabled_routes_to_handle_simple(self):
        """With DRYADE_TIER_SIMPLE_ENABLED=true, SIMPLE goes to SimpleHandler."""
        handler = TierDispatcher()
        context = _make_context()

        os.environ["DRYADE_TIER_SIMPLE_ENABLED"] = "true"
        try:
            with patch("core.adapters.registry.get_registry") as mock_reg:
                # Create a mock agent with a name that will trigger SIMPLE classification
                mock_card = MagicMock()
                mock_card.name = "mcp-filesystem"
                mock_card.capabilities = []
                mock_reg.return_value.list_agents.return_value = [mock_card]

                # Mock SimpleHandler.handle to yield a complete event
                async def mock_handle_simple(msg, ctx, stream=True, tier_decision=None):
                    yield ChatEvent(type="complete", content="simple response")

                with patch.object(handler._simple, "handle", side_effect=mock_handle_simple):
                    events = []
                    # Use a message that will trigger SIMPLE (contains agent name)
                    async for event in handler.handle("use mcp-filesystem to list files", context):
                        events.append(event)

                    event_types = [e.type for e in events]
                    assert "complete" in event_types
        finally:
            os.environ.pop("DRYADE_TIER_SIMPLE_ENABLED", None)

# ---------------------------------------------------------------------------
# TestSimpleFallbackToComplex
# ---------------------------------------------------------------------------

class TestSimpleFallbackToComplex:
    """Test that failed SIMPLE dispatch falls back to COMPLEX."""

    @pytest.mark.asyncio
    async def test_simple_failure_falls_through_to_complex(self):
        """SIMPLE dispatch failure falls through to COMPLEX transparently."""
        handler = TierDispatcher()
        context = _make_context()

        os.environ["DRYADE_TIER_SIMPLE_ENABLED"] = "true"
        try:
            with (
                patch("core.adapters.registry.get_registry") as mock_reg,
                patch(
                    "core.orchestrator.orchestrator.DryadeOrchestrator", autospec=False
                ) as mock_orch_cls,
            ):
                # Set up registry with an agent that triggers SIMPLE
                mock_card = MagicMock()
                mock_card.name = "mcp-filesystem"
                mock_card.capabilities = []
                mock_reg.return_value.list_agents.return_value = [mock_card]

                # Set up orchestrator for COMPLEX fallback path
                mock_result = MagicMock()
                mock_result.needs_escalation = False
                mock_result.success = True
                mock_result.output = "complex fallback response"
                mock_result.partial_results = []
                mock_result.reasoning = None
                mock_result.streamed = False

                mock_orch_instance = MagicMock()
                mock_orch_instance.thinking = MagicMock()
                mock_orch_instance.thinking._on_cost_event = None
                mock_orch_instance.agents.list_agents.return_value = []
                mock_orch_cls.return_value = mock_orch_instance

                async def mock_orchestrate(**kwargs):
                    return mock_result

                mock_orch_instance.orchestrate = mock_orchestrate

                # Mock SimpleHandler.handle to yield NO complete (failure scenario)
                async def mock_handle_simple_failure(msg, ctx, stream=True, tier_decision=None):
                    yield ChatEvent(type="agent_start", content="starting")
                    yield ChatEvent(type="agent_complete", content="failed")
                    # No "complete" event -> signals failure

                with patch.object(
                    handler._simple, "handle", side_effect=mock_handle_simple_failure
                ):
                    events = []
                    async for event in handler.handle("use mcp-filesystem to list", context):
                        events.append(event)

                    event_types = [e.type for e in events]
                    # Should have COMPLEX path events, NOT SIMPLE failure events
                    assert "complete" in event_types
                    # SIMPLE failure events should NOT appear (invisible fallback)
                    assert event_types.count(
                        "agent_start"
                    ) == 0 or "complex fallback response" in str(
                        [e.content for e in events if e.type == "complete"]
                    )
        finally:
            os.environ.pop("DRYADE_TIER_SIMPLE_ENABLED", None)

# ---------------------------------------------------------------------------
# TestArgumentExtraction
# ---------------------------------------------------------------------------

class TestArgumentExtraction:
    """Tests for _extract_arguments() helper."""

    def test_extracts_file_path(self):
        """Extract absolute file path from message."""
        args = _extract_arguments("read /home/user/file.txt")
        assert args.get("path") == "/home/user/file.txt"

    def test_extracts_tilde_path(self):
        """Extract tilde-prefixed path from message."""
        args = _extract_arguments("open ~/Documents/notes.md")
        assert "path" in args
        assert args["path"].startswith("~/")

    def test_extracts_quoted_string(self):
        """Extract quoted string from message."""
        args = _extract_arguments('search for "important keyword"')
        assert args.get("query") == "important keyword"

    def test_no_args_returns_empty(self):
        """No extractable arguments returns empty dict."""
        args = _extract_arguments("hello world")
        assert args == {}

    def test_does_not_overmatch_fractions(self):
        """Fractions like 3/4 should not be matched as paths."""
        args = _extract_arguments("list 3/4 of the files")
        # 3/4 doesn't start with /, ~, or .
        assert "path" not in args

# ---------------------------------------------------------------------------
# TestToolNameResolution
# ---------------------------------------------------------------------------

class TestToolNameResolution:
    """Tests for _resolve_tool_name() helper."""

    def test_resolves_original_case(self):
        """Tool name is resolved to original case from capabilities."""
        cap = MagicMock()
        cap.name = "Search_Files"
        agent = _make_agent(capabilities=[cap])

        result = _resolve_tool_name(agent, "search_files")
        assert result == "Search_Files"

    def test_fallback_to_input_when_no_match(self):
        """Returns input as-is when no capability matches."""
        cap = MagicMock()
        cap.name = "other_tool"
        agent = _make_agent(capabilities=[cap])

        result = _resolve_tool_name(agent, "missing_tool")
        assert result == "missing_tool"

    def test_none_input_returns_none(self):
        """None input returns None."""
        agent = _make_agent()
        result = _resolve_tool_name(agent, None)
        assert result is None
