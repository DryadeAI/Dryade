"""Unit tests for OrchestrateHandler and module-level helpers.

Covers:
- VISIBILITY_DENY dict contents and _should_emit logic
- Local event helpers (_emit_escalation, _emit_reasoning, _emit_resource_suggestion)
- _resolve_agent: exact match, case-insensitive fallback, not found
- _resolve_tool_name: exact match, case-insensitive, None input
- _router_confirms: agreement, strong disagreement, error fallback
- _extract_arguments: file paths, quoted strings, empty
- OrchestrateHandler._handle_escalation: with/without action, observations
- OrchestrateHandler._handle_success: with observations, without, streamed
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.extensions.events import ChatEvent
from core.orchestrator.handlers._utils import (
    VISIBILITY_DENY,
    _emit_escalation,
    _emit_reasoning,
    _emit_resource_suggestion,
    _should_emit,
)
from core.orchestrator.handlers.complex_handler import ComplexHandler
from core.orchestrator.handlers.simple_handler import (
    _extract_arguments,
    _resolve_agent,
    _resolve_tool_name,
    _router_confirms,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    conversation_id: str = "conv-1",
    user_id: str = "user-1",
    metadata: dict | None = None,
):
    ctx = MagicMock()
    ctx.conversation_id = conversation_id
    ctx.user_id = user_id
    ctx.metadata = metadata if metadata is not None else {}
    return ctx

async def _collect_events(gen) -> list[ChatEvent]:
    events = []
    async for event in gen:
        events.append(event)
    return events

# ---------------------------------------------------------------------------
# Tests: VISIBILITY_DENY and _should_emit
# ---------------------------------------------------------------------------

class TestVisibilityDeny:
    """Tests for VISIBILITY_DENY dict and _should_emit function."""

    def test_minimal_allows_essentials(self):
        assert "complete" not in VISIBILITY_DENY["minimal"]
        assert "error" not in VISIBILITY_DENY["minimal"]
        assert "escalation" not in VISIBILITY_DENY["minimal"]
        assert "cancel_ack" not in VISIBILITY_DENY["minimal"]

    def test_minimal_blocks_non_essentials(self):
        assert "token" in VISIBILITY_DENY["minimal"]
        assert "thinking" in VISIBILITY_DENY["minimal"]
        assert "agent_start" in VISIBILITY_DENY["minimal"]

    def test_named_steps_allows_agent_events(self):
        deny = VISIBILITY_DENY["named-steps"]
        assert "agent_start" not in deny
        assert "agent_complete" not in deny
        assert "progress" not in deny
        assert "plan_preview" not in deny
        assert "thinking" not in deny

    def test_full_transparency_is_empty_set(self):
        assert VISIBILITY_DENY["full-transparency"] == set()

    def test_should_emit_full_transparency_allows_all(self):
        assert _should_emit("token", "full-transparency") is True
        assert _should_emit("thinking", "full-transparency") is True
        assert _should_emit("any_random_type", "full-transparency") is True

    def test_should_emit_minimal_blocks_token(self):
        assert _should_emit("token", "minimal") is False

    def test_should_emit_minimal_allows_complete(self):
        assert _should_emit("complete", "minimal") is True

    def test_should_emit_named_steps_allows_thinking(self):
        assert _should_emit("thinking", "named-steps") is True

    def test_should_emit_unknown_visibility_defaults_to_named_steps(self):
        # Unknown visibility level should default to named-steps
        assert _should_emit("agent_start", "unknown_level") is True
        assert (
            _should_emit("token", "unknown_level") is True
        )  # Phase 111: tokens pass at named-steps default

# ---------------------------------------------------------------------------
# Tests: Local Event Helpers
# ---------------------------------------------------------------------------

class TestLocalEventHelpers:
    """Tests for _emit_escalation, _emit_reasoning, _emit_resource_suggestion."""

    def test_emit_escalation_basic(self):
        event = _emit_escalation("How to proceed?")
        assert event.type == "escalation"
        assert event.content == "How to proceed?"
        assert event.metadata["inline"] is True
        assert event.metadata["has_auto_fix"] is False

    def test_emit_escalation_with_context_and_auto_fix(self):
        event = _emit_escalation(
            "Fix config?",
            task_context="reading file",
            has_auto_fix=True,
        )
        assert event.metadata["task_context"] == "reading file"
        assert event.metadata["has_auto_fix"] is True

    def test_emit_reasoning_summary_only(self):
        event = _emit_reasoning("Using agent X for analysis")
        assert event.type == "reasoning"
        assert event.content == "Using agent X for analysis"
        assert event.metadata["expandable"] is False
        assert event.metadata["detailed"] is None

    def test_emit_reasoning_with_detailed(self):
        event = _emit_reasoning("Summary", detailed="Full reasoning here")
        assert event.metadata["expandable"] is True
        assert event.metadata["detailed"] == "Full reasoning here"

    def test_emit_reasoning_custom_visibility(self):
        event = _emit_reasoning("Summary", visibility="hidden")
        assert event.metadata["visibility"] == "hidden"

    def test_emit_resource_suggestion(self):
        resources = [{"uri": "file://a.txt"}, {"uri": "file://b.txt"}]
        event = _emit_resource_suggestion(resources, "mcp-fs")
        assert event.type == "resource_suggestion"
        assert event.metadata["agent_name"] == "mcp-fs"
        assert len(event.metadata["resources"]) == 2
        assert event.metadata["requires_confirmation"] is True
        assert "2 relevant resources" in event.content

# ---------------------------------------------------------------------------
# Tests: _resolve_agent
# ---------------------------------------------------------------------------

class TestResolveAgent:
    """Tests for _resolve_agent helper."""

    def test_exact_match(self):
        registry = MagicMock()
        registry.get.return_value = MagicMock()
        agent, name = _resolve_agent(registry, "filesystem")
        assert agent is not None
        assert name == "filesystem"

    def test_case_insensitive_fallback(self):
        registry = MagicMock()
        registry.get.side_effect = lambda n: None if n == "filesystem" else MagicMock()
        card = MagicMock()
        card.name = "Filesystem"
        registry.list_agents.return_value = [card]
        # Mock: registry.get("Filesystem") returns an agent
        registry.get.side_effect = lambda n: MagicMock() if n == "Filesystem" else None

        agent, name = _resolve_agent(registry, "filesystem")
        assert agent is not None
        assert name == "Filesystem"

    def test_not_found(self):
        registry = MagicMock()
        registry.get.return_value = None
        registry.list_agents.return_value = []
        agent, name = _resolve_agent(registry, "nonexistent")
        assert agent is None
        assert name == "nonexistent"

# ---------------------------------------------------------------------------
# Tests: _resolve_tool_name
# ---------------------------------------------------------------------------

class TestResolveToolName:
    """Tests for _resolve_tool_name helper."""

    def test_none_input(self):
        agent = MagicMock()
        result = _resolve_tool_name(agent, None)
        assert result is None

    def test_exact_case_match(self):
        cap = MagicMock()
        cap.name = "readFile"
        card = MagicMock()
        card.capabilities = [cap]
        agent = MagicMock()
        agent.get_card.return_value = card

        result = _resolve_tool_name(agent, "readfile")
        assert result == "readFile"

    def test_no_match_returns_input(self):
        card = MagicMock()
        card.capabilities = []
        agent = MagicMock()
        agent.get_card.return_value = card

        result = _resolve_tool_name(agent, "unknown_tool")
        assert result == "unknown_tool"

# ---------------------------------------------------------------------------
# Tests: _router_confirms
# ---------------------------------------------------------------------------

class TestRouterConfirms:
    """Tests for _router_confirms helper."""

    def test_agreement(self):
        mock_result = MagicMock()
        mock_result.server = "filesystem"
        mock_result.score = 0.9

        with patch("core.mcp.hierarchical_router.get_hierarchical_router") as mock_get:
            mock_router = MagicMock()
            mock_router.route.return_value = [mock_result]
            mock_get.return_value = mock_router

            assert _router_confirms("read file", "filesystem") is True

    def test_strong_disagreement(self):
        mock_result = MagicMock()
        mock_result.server = "database"
        mock_result.score = 0.85  # > 0.8 threshold

        with patch("core.mcp.hierarchical_router.get_hierarchical_router") as mock_get:
            mock_router = MagicMock()
            mock_router.route.return_value = [mock_result]
            mock_get.return_value = mock_router

            assert _router_confirms("query db", "filesystem") is False

    def test_weak_disagreement_trusts_classifier(self):
        mock_result = MagicMock()
        mock_result.server = "database"
        mock_result.score = 0.5  # < 0.8 threshold

        with patch("core.mcp.hierarchical_router.get_hierarchical_router") as mock_get:
            mock_router = MagicMock()
            mock_router.route.return_value = [mock_result]
            mock_get.return_value = mock_router

            assert _router_confirms("query", "filesystem") is True

    def test_no_results_returns_true(self):
        with patch("core.mcp.hierarchical_router.get_hierarchical_router") as mock_get:
            mock_router = MagicMock()
            mock_router.route.return_value = []
            mock_get.return_value = mock_router

            assert _router_confirms("hello", "filesystem") is True

    def test_error_returns_true(self):
        with patch("core.mcp.hierarchical_router.get_hierarchical_router") as mock_get:
            mock_get.side_effect = RuntimeError("no router")
            assert _router_confirms("hello", "filesystem") is True

# ---------------------------------------------------------------------------
# Tests: _extract_arguments
# ---------------------------------------------------------------------------

class TestExtractArguments:
    """Tests for _extract_arguments helper."""

    def test_file_path_extraction(self):
        args = _extract_arguments("read /home/user/file.txt")
        assert args["path"] == "/home/user/file.txt"

    def test_tilde_path_extraction(self):
        args = _extract_arguments("read ~/Documents/report.pdf")
        assert args["path"] == "~/Documents/report.pdf"

    def test_quoted_string_extraction(self):
        args = _extract_arguments('search for "hello world"')
        assert args["query"] == "hello world"

    def test_both_path_and_query(self):
        args = _extract_arguments('search /tmp/data.csv for "revenue"')
        assert "path" in args
        assert "query" in args

    def test_no_arguments(self):
        args = _extract_arguments("hello how are you")
        assert args == {}

    def test_relative_path(self):
        args = _extract_arguments("read ./local/config.yaml")
        assert args["path"] == "./local/config.yaml"

# ---------------------------------------------------------------------------
# Tests: OrchestrateHandler._handle_escalation
# ---------------------------------------------------------------------------

class TestHandleEscalation:
    """Tests for OrchestrateHandler._handle_escalation."""

    @pytest.mark.asyncio
    async def test_escalation_with_action(self):
        handler = ComplexHandler()
        ctx = _make_context()

        obs = MagicMock()
        obs.agent_name = "mcp-fs"
        obs.task = "read file"
        obs.error = "Access denied"
        obs.model_dump.return_value = {"agent_name": "mcp-fs", "error": "Access denied"}

        result = MagicMock()
        result.needs_escalation = True
        result.escalation_question = "Add path to config?"
        result.escalation_action = {
            "action_type": "update_mcp_config",
            "parameters": {"path": "/home/user"},
            "description": "Add path",
        }
        result.original_goal = "read my file"
        result.partial_results = [obs]
        result.state = None
        result.observation_history_data = None

        with patch("core.orchestrator.escalation.get_escalation_registry") as mock_get_reg:
            mock_registry = MagicMock()
            mock_get_reg.return_value = mock_registry
            events = await _collect_events(handler._handle_escalation(result, ctx))

        event_types = [e.type for e in events]
        assert "agent_start" in event_types
        assert "thinking" in event_types
        assert "escalation" in event_types
        assert "complete" in event_types
        mock_registry.register.assert_called_once()

    @pytest.mark.asyncio
    async def test_escalation_without_action(self):
        handler = ComplexHandler()
        ctx = _make_context()

        result = MagicMock()
        result.needs_escalation = True
        result.escalation_question = "How to proceed?"
        result.escalation_action = None
        result.original_goal = None
        result.partial_results = []

        events = await _collect_events(handler._handle_escalation(result, ctx))

        event_types = [e.type for e in events]
        assert "escalation" in event_types
        assert "complete" in event_types
        escalation_event = next(e for e in events if e.type == "escalation")
        assert escalation_event.metadata["has_auto_fix"] is False

# ---------------------------------------------------------------------------
# Tests: OrchestrateHandler._handle_success
# ---------------------------------------------------------------------------

class TestHandleSuccess:
    """Tests for OrchestrateHandler._handle_success."""

    @pytest.mark.asyncio
    async def test_success_with_observations(self):
        handler = ComplexHandler()

        obs = MagicMock()
        obs.reasoning_summary = "Analyzed data"
        obs.reasoning = "Full reasoning text..."
        obs.agent_name = "analyst"

        result = MagicMock()
        result.success = True
        result.output = "Here is the answer."
        result.partial_results = [obs]
        result.reasoning = None
        result.reasoning_summary = None
        result.streamed = False

        events = await _collect_events(
            handler._handle_success(result, stream=True, reasoning_visibility="summary")
        )

        event_types = [e.type for e in events]
        assert "reasoning" in event_types
        assert "token" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_success_direct_answer_no_observations(self):
        handler = ComplexHandler()

        result = MagicMock()
        result.success = True
        result.output = "Direct answer."
        result.partial_results = []
        result.reasoning = "I decided to answer directly."
        result.reasoning_summary = "Direct reasoning"
        result.streamed = False

        events = await _collect_events(
            handler._handle_success(result, stream=True, reasoning_visibility="summary")
        )

        reasoning_events = [e for e in events if e.type == "reasoning"]
        assert len(reasoning_events) == 1
        assert reasoning_events[0].content == "Direct reasoning"

    @pytest.mark.asyncio
    async def test_success_streamed_skips_token_emission(self):
        handler = ComplexHandler()

        result = MagicMock()
        result.success = True
        result.output = "Streamed answer."
        result.partial_results = []
        result.reasoning = None
        result.reasoning_summary = None
        result.streamed = True  # Already streamed

        events = await _collect_events(
            handler._handle_success(result, stream=True, reasoning_visibility="summary")
        )

        # Should NOT have token events (already streamed)
        token_events = [e for e in events if e.type == "token"]
        assert len(token_events) == 0
        # But should still have complete event
        assert any(e.type == "complete" for e in events)

    @pytest.mark.asyncio
    async def test_success_no_stream_mode(self):
        handler = ComplexHandler()

        result = MagicMock()
        result.success = True
        result.output = "Full response."
        result.partial_results = []
        result.reasoning = None
        result.reasoning_summary = None
        result.streamed = False

        events = await _collect_events(
            handler._handle_success(result, stream=False, reasoning_visibility="summary")
        )

        token_events = [e for e in events if e.type == "token"]
        # In no-stream mode, there's still a single token event with full content
        assert len(token_events) == 1
        assert token_events[0].content == "Full response."

# ---------------------------------------------------------------------------
# Tests: OrchestrateHandler._suggest_mcp_resources_if_available
# ---------------------------------------------------------------------------

class TestSuggestMCPResources:
    """Tests for OrchestrateHandler._suggest_mcp_resources_if_available."""

    @pytest.mark.asyncio
    async def test_no_mcp_agents(self):
        handler = ComplexHandler()
        ctx = _make_context()

        orchestrator = MagicMock()
        card = MagicMock()
        card.framework.value = "custom"  # Not MCP
        orchestrator.agents.list_agents.return_value = [card]

        events = await _collect_events(
            handler._suggest_mcp_resources_if_available(orchestrator, ctx)
        )
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_mcp_agent_with_resources(self):
        handler = ComplexHandler()
        ctx = _make_context()

        orchestrator = MagicMock()
        card = MagicMock()
        card.framework.value = "mcp"
        card.name = "mcp-fs"
        orchestrator.agents.list_agents.return_value = [card]

        mock_agent = MagicMock()
        mock_agent.list_resources = AsyncMock(return_value=[{"uri": "file://a"}])
        orchestrator.agents.get.return_value = mock_agent

        events = await _collect_events(
            handler._suggest_mcp_resources_if_available(orchestrator, ctx)
        )
        assert len(events) == 1
        assert events[0].type == "resource_suggestion"

    @pytest.mark.asyncio
    async def test_mcp_resource_check_failure(self):
        handler = ComplexHandler()
        ctx = _make_context()

        orchestrator = MagicMock()
        orchestrator.agents.list_agents.side_effect = RuntimeError("boom")

        # Should not raise, just returns no events
        events = await _collect_events(
            handler._suggest_mcp_resources_if_available(orchestrator, ctx)
        )
        assert len(events) == 0
