"""Regression tests for Phase 114.2: Reasoning leak, router filter, clarification, agent creation.

Tests cover:
- BUG-R1: Router fail-open (never return all agents)
- BUG-R2: Reasoning leak in _stream_final_answer (merge_thinking=False)
- BUG-R3: Clarification short-circuit (escalation priority in router)
- BUG-R4: Agent creation meta-action (complexity estimator + system prompt)
"""

import inspect
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework
from core.orchestrator.complexity import (
    META_ACTION_PATTERNS,
    ComplexityEstimator,
    PlanningMode,
)
from core.orchestrator.models import Tier
from core.orchestrator.thinking.provider import (
    GENERAL_PURPOSE_AGENTS,
    MAX_FALLBACK_AGENTS,
    OrchestrationThinkingProvider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(
    name: str, framework: str = "mcp", capabilities: list[str] | None = None
) -> AgentCard:
    """Create an AgentCard with minimal required fields."""
    caps = [AgentCapability(name=c) for c in (capabilities or [])]
    return AgentCard(
        name=name,
        description=f"{name} agent",
        version="1.0",
        framework=AgentFramework(framework),
        capabilities=caps,
    )

def _make_provider() -> OrchestrationThinkingProvider:
    """Create a ThinkingProvider without calling __init__ (no LLM needed)."""
    p = OrchestrationThinkingProvider.__new__(OrchestrationThinkingProvider)
    p._explicit_llm = None
    p._cached_llm = None
    p._on_cost_event = None
    p._last_available_agents = []
    p._cached_tools_key = None
    p._cached_tools = None
    return p

# ---------------------------------------------------------------------------
# BUG-R1: Router fail-open (never return all agents)
# ---------------------------------------------------------------------------

class TestRouterFailOpen:
    """BUG-R1: Router must never return ALL agents on no-match."""

    def test_router_never_returns_all_agents_on_no_match(self):
        """When router_hints is None, result must NOT be the full agent list."""
        provider = _make_provider()
        general = [_make_agent(name) for name in GENERAL_PURPOSE_AGENTS]
        other_mcp = [_make_agent(f"mcp-special-{i}") for i in range(20)]
        non_mcp = [_make_agent("crew-agent", framework="crewai")]
        all_agents = non_mcp + general + other_mcp

        result = provider._filter_agents_by_router(all_agents, router_hints=None)

        # Result must be smaller than the full list
        assert len(result) < len(all_agents), (
            f"Filter returned {len(result)} agents, same as total {len(all_agents)}"
        )
        # All non-MCP agents should be included
        result_names = {a.name for a in result}
        assert "crew-agent" in result_names

    def test_router_filter_uses_general_purpose_agents(self):
        """Fallback prefers general-purpose agents (filesystem, memory, git) over others."""
        provider = _make_provider()
        general = [_make_agent(name) for name in GENERAL_PURPOSE_AGENTS]
        other_mcp = [_make_agent(f"mcp-other-{i}") for i in range(10)]
        all_agents = general + other_mcp

        # router_hints that match no agents
        result = provider._filter_agents_by_router(
            all_agents,
            router_hints=[{"server": "nonexistent-server"}],
        )

        result_names = {a.name for a in result}
        # General-purpose agents MUST be in the result
        for gp in GENERAL_PURPOSE_AGENTS:
            assert gp in result_names, f"General-purpose agent {gp} missing from fallback"

    def test_router_filter_max_fallback_agents(self):
        """When no general-purpose agents exist, fallback caps at MAX_FALLBACK_AGENTS."""
        provider = _make_provider()
        # Create 20 MCP agents, none of which are general-purpose
        mcp_agents = [_make_agent(f"mcp-niche-{i}") for i in range(20)]

        result = provider._filter_agents_by_router(mcp_agents, router_hints=None)

        assert len(result) <= MAX_FALLBACK_AGENTS, (
            f"Fallback returned {len(result)} MCP agents, max is {MAX_FALLBACK_AGENTS}"
        )

    def test_router_filter_normal_matching_unchanged(self):
        """Normal router matching still works: matched MCP included, unmatched excluded."""
        provider = _make_provider()
        target = _make_agent("mcp-target")
        other = _make_agent("mcp-other")
        non_mcp = _make_agent("crew-agent", framework="crewai")
        all_agents = [non_mcp, target, other]

        result = provider._filter_agents_by_router(
            all_agents,
            router_hints=[{"server": "mcp-target"}],
        )

        result_names = {a.name for a in result}
        assert "mcp-target" in result_names
        assert "crew-agent" in result_names
        assert "mcp-other" not in result_names

    def test_router_filter_empty_hints_bounded_result(self):
        """Empty hints list (not None) also produces bounded result."""
        provider = _make_provider()
        mcp_agents = [_make_agent(f"mcp-bulk-{i}") for i in range(30)]

        result = provider._filter_agents_by_router(mcp_agents, router_hints=[])

        # Empty list is falsy, should trigger bounded fallback
        assert len(result) <= MAX_FALLBACK_AGENTS, (
            f"Empty hints returned {len(result)} agents, expected <= {MAX_FALLBACK_AGENTS}"
        )

# ---------------------------------------------------------------------------
# BUG-R2: Reasoning leak in _stream_final_answer (merge_thinking=False)
# ---------------------------------------------------------------------------

class TestReasoningLeak:
    """BUG-R2: Reasoning content must not leak into user chat bubble."""

    @pytest.mark.asyncio
    async def test_stream_final_answer_merge_thinking_false(self):
        """_stream_final_answer must call _stream_llm with merge_thinking=False."""
        provider = _make_provider()
        provider._stream_llm = AsyncMock(return_value=("answer text", "reasoning text", 100))

        # Create minimal observation_history mock
        obs_history = MagicMock()
        obs_history.format_for_llm.return_value = ""

        await provider._stream_final_answer(
            goal="test",
            observations=[],
            observation_history=obs_history,
        )

        # Verify merge_thinking=False was passed
        call_kwargs = provider._stream_llm.call_args
        assert call_kwargs.kwargs.get("merge_thinking") is False

    @pytest.mark.asyncio
    async def test_stream_final_answer_reasoning_fallback(self):
        """When content is empty but reasoning exists, reasoning becomes content."""
        provider = _make_provider()
        # Model returns all in reasoning, no content
        provider._stream_llm = AsyncMock(return_value=("", "actual answer in reasoning", 100))

        obs_history = MagicMock()
        obs_history.format_for_llm.return_value = ""

        on_token = MagicMock()

        content, reasoning, tokens = await provider._stream_final_answer(
            goal="test",
            observations=[],
            observation_history=obs_history,
            on_token=on_token,
        )

        assert content == "actual answer in reasoning"
        # Verify on_token was called with the fallback content
        on_token.assert_called_once_with("actual answer in reasoning")

    @pytest.mark.asyncio
    async def test_stream_final_answer_normal_content_no_fallback(self):
        """When content is present, reasoning is NOT substituted."""
        provider = _make_provider()
        provider._stream_llm = AsyncMock(return_value=("normal content", "internal reasoning", 100))

        obs_history = MagicMock()
        obs_history.format_for_llm.return_value = ""

        content, reasoning, tokens = await provider._stream_final_answer(
            goal="test",
            observations=[],
            observation_history=obs_history,
        )

        assert content == "normal content"
        assert reasoning == "internal reasoning"

    def test_answer_field_sanitization_strips_json_reasoning(self):
        """Answer field sanitization extracts clean answer from JSON-like content."""
        import json

        # Simulate the sanitization path in orchestrate_think's except block
        # Content looks like a JSON response that failed the main parser
        json_content = json.dumps(
            {
                "reasoning": "I analyzed the tools available",
                "is_final": True,
                "answer": "Here is the clean answer",
            }
        )

        # The sanitization logic from provider.py (lines ~1060-1079)
        sanitized = json_content[:2000]
        if json_content.lstrip().startswith('{"reasoning"') or '"is_final"' in json_content[:500]:
            try:
                partial = json.loads(json_content)
                if isinstance(partial, dict) and partial.get("answer"):
                    sanitized = partial["answer"]
            except (json.JSONDecodeError, TypeError):
                sanitized = "I encountered an issue processing the request. Please try rephrasing."

        assert sanitized == "Here is the clean answer"
        # Must NOT contain the JSON structure
        assert '"reasoning"' not in sanitized
        assert '"is_final"' not in sanitized

# ---------------------------------------------------------------------------
# BUG-R3: Clarification short-circuit (escalation priority in router)
# ---------------------------------------------------------------------------

class TestClarificationEscalationPriority:
    """BUG-R3: Escalation must be checked BEFORE normal message routing."""

    def test_router_route_checks_escalation_first(self):
        """In router.py route(), escalation check comes before handler dispatch."""
        from core.orchestrator.router import ExecutionRouter

        source = inspect.getsource(ExecutionRouter.route)

        # Find position of escalation check and handler dispatch
        escalation_pos = source.find("_handle_escalation_response")
        handler_pos = source.find("handler.handle")

        assert escalation_pos != -1, "Escalation check not found in route()"
        assert handler_pos != -1, "Handler dispatch not found in route()"
        assert escalation_pos < handler_pos, (
            "Escalation check must come BEFORE handler dispatch, "
            f"but escalation_pos={escalation_pos} >= handler_pos={handler_pos}"
        )

    @pytest.mark.asyncio
    async def test_escalation_response_intercepts_normal_routing(self):
        """When escalation is pending and message is approval, normal routing is skipped."""
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        ctx = ExecutionContext(conversation_id="test-conv-123", mode="orchestrate")

        # Mock _handle_escalation_response to return an async generator
        async def fake_escalation():
            yield MagicMock(type="complete", content="Escalation handled")

        router._handle_escalation_response = AsyncMock(return_value=fake_escalation())

        # Mock the orchestrate handler to track if it was called
        router._orchestrate_handler.handle = AsyncMock()

        events = []
        async for event in router.route("yes", ctx, stream=True):
            events.append(event)

        # Escalation should have been handled
        assert len(events) == 1
        # Orchestrate handler should NOT have been called
        router._orchestrate_handler.handle.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_escalation_proceeds_to_handler(self):
        """When no escalation is pending, normal handler dispatch proceeds."""
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        ctx = ExecutionContext(conversation_id="test-conv-456", mode="orchestrate")

        # No pending escalation
        router._handle_escalation_response = AsyncMock(return_value=None)

        # Mock handler to return a simple event
        async def fake_handle(msg, ctx, stream):
            yield MagicMock(type="complete", content="Normal response")

        router._orchestrate_handler.handle = fake_handle

        events = []
        async for event in router.route("hello", ctx, stream=True):
            events.append(event)

        assert len(events) == 1
        assert events[0].content == "Normal response"

    def test_escalation_registry_get_pending_returns_none_for_unknown(self):
        """EscalationRegistry returns None for unknown conversation IDs."""
        from core.orchestrator.escalation import get_escalation_registry

        registry = get_escalation_registry()
        result = registry.get_pending("nonexistent-conversation-id")
        assert result is None

# ---------------------------------------------------------------------------
# BUG-R4: Agent creation meta-action (complexity estimator + system prompt)
# ---------------------------------------------------------------------------

class TestMetaActionPatterns:
    """BUG-R4: Meta-action patterns for agent/tool creation requests."""

    @pytest.mark.parametrize(
        "message",
        [
            "create a websearch agent",
            "add a Brave Search tool",
            "set up a Slack integration",
            "configure a new MCP server",
            "install the Docker plugin",
            "enable the monitoring capability",
            "remove the old agent",
            "delete the test plugin",
            "disable the debug tool",
        ],
    )
    def test_meta_action_pattern_create_agent(self, message):
        """META_ACTION_PATTERNS match creation/removal requests."""
        match = any(re.search(p, message.lower()) for p in META_ACTION_PATTERNS)
        assert match, f"Expected meta-action match for: {message!r}"

    @pytest.mark.parametrize(
        "message",
        [
            "search for files",
            "list my agents",
            "what agents are available",
            "how do I use the filesystem agent",
            "tell me about MCP servers",
            "what tools do you have",
            "help me with my project",
        ],
    )
    def test_meta_action_does_not_match_normal_queries(self, message):
        """Normal queries must NOT trigger meta-action patterns."""
        match = any(re.search(p, message.lower()) for p in META_ACTION_PATTERNS)
        assert not match, f"Unexpected meta-action match for: {message!r}"

    def test_meta_action_overrides_simple_classification(self):
        """Meta-action takes priority over agent name match for SIMPLE classification."""
        estimator = ComplexityEstimator()
        # Agent named "websearch" exists -- without meta-action check,
        # "create a websearch agent" would match agent name and route SIMPLE
        agents = [
            _make_agent("websearch"),
            _make_agent("mcp-filesystem"),
        ]

        result = estimator.classify("create a websearch agent", agents)

        assert result.tier == Tier.COMPLEX, (
            f"Expected COMPLEX tier, got {result.tier} with reason: {result.reason}"
        )
        assert result.sub_mode == PlanningMode.REACT
        assert "meta-action" in result.reason.lower() or "Meta-action" in result.reason

    def test_meta_action_classify_returns_complex_react(self):
        """classify() returns COMPLEX/REACT for agent creation messages."""
        estimator = ComplexityEstimator()
        agents = [_make_agent("mcp-filesystem")]

        result = estimator.classify("create a websearch agent", agents)

        assert result.tier == Tier.COMPLEX
        assert result.sub_mode == PlanningMode.REACT
        assert result.confidence == 0.90

    def test_system_prompt_has_meta_action_guidance(self):
        """ORCHESTRATE_SYSTEM_PROMPT contains Rule 7 and Meta-Actions section.

        Updated for Phase 167: prompt rewrite replaced the old 'CREATE, CONFIGURE, SET UP, or ADD'
        text and 'TOOL LIST' section with a more concise tool-first framing. The key invariants
        are: (1) Meta-Actions section exists, (2) Rule 7 references system management tools and
        the `create` tool, (3) language-agnostic framing is present.
        """
        from core.orchestrator.thinking.prompts import ORCHESTRATE_SYSTEM_PROMPT

        # Rule 7 for agent creation (Phase 167 rewrite: tool-first framing)
        assert "system management tools" in ORCHESTRATE_SYSTEM_PROMPT
        assert "`factory_create`" in ORCHESTRATE_SYSTEM_PROMPT

        # Meta-Actions section still exists
        assert "Meta-Actions" in ORCHESTRATE_SYSTEM_PROMPT
        # Language-agnostic framing
        assert "language" in ORCHESTRATE_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# BUG-R4 gap closure: Programmatic meta-action interception in ComplexHandler
# ---------------------------------------------------------------------------

class TestMetaActionInterception:
    """Phase 115.1: meta-action hint triggers fallback when LLM doesn't use self-mod tools."""

    @pytest.mark.asyncio
    async def test_meta_action_hint_with_fallback(self):
        """When meta_action_hint is active and LLM doesn't use self-mod tools, fallback fires."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.orchestrator.complexity import PlanningMode, TierDecision
        from core.orchestrator.handlers.complex_handler import ComplexHandler
        from core.orchestrator.models import Tier

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-1"
        context.user_id = "test-user"
        context.metadata = {
            "_tier_decision": TierDecision(
                tier=Tier.COMPLEX,
                confidence=0.90,
                reason="Meta-action: system infrastructure request",
                sub_mode=PlanningMode.REACT,
                meta_action_hint=True,
            ),
        }

        # Mock orchestrator to return success WITHOUT using self-mod tools
        mock_instance = AsyncMock()
        mock_instance.orchestrate = AsyncMock(
            return_value=MagicMock(
                success=True,
                needs_escalation=False,
                output="I can help with that.",
                partial_results=[],  # No observations -- LLM didn't use self-mod tools
                reasoning=None,
                reasoning_summary=None,
                streamed=False,
            )
        )
        mock_instance.thinking = MagicMock()
        mock_instance.thinking._on_cost_event = None
        mock_instance.thinking._get_llm = MagicMock(return_value=MagicMock(model="test"))
        mock_instance.agents = MagicMock()
        mock_instance.agents.list_agents = MagicMock(return_value=[])

        with patch("core.orchestrator.orchestrator.DryadeOrchestrator", return_value=mock_instance):
            with patch("core.adapters.registry.get_registry") as mock_reg:
                mock_reg.return_value = MagicMock()
                mock_reg.return_value.list_agents.return_value = []
                with patch(
                    "core.orchestrator.cancellation.get_cancellation_registry"
                ) as mock_cancel:
                    mock_cancel.return_value = MagicMock()
                    mock_cancel.return_value.get_or_create.return_value = None

                    events = []
                    async for event in handler.handle(
                        "create a websearch agent", context, stream=True
                    ):
                        events.append(event)

        # Fallback must fire: escalation + complete events
        event_types = [e.type for e in events]
        assert "escalation" in event_types, (
            f"Expected escalation event from fallback, got: {event_types}"
        )
        assert "complete" in event_types, (
            f"Expected complete event from fallback, got: {event_types}"
        )

        # Escalation must have auto_fix
        esc_event = next(e for e in events if e.type == "escalation")
        assert esc_event.metadata["has_auto_fix"] is True

    @pytest.mark.asyncio
    async def test_meta_action_registers_pending_escalation(self):
        """Meta-action fallback must register a PendingEscalation with CREATE_AGENT."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.orchestrator.complexity import PlanningMode, TierDecision
        from core.orchestrator.escalation import get_escalation_registry
        from core.orchestrator.handlers.complex_handler import ComplexHandler
        from core.orchestrator.models import Tier

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-meta"
        context.user_id = "test-user"
        context.metadata = {
            "_tier_decision": TierDecision(
                tier=Tier.COMPLEX,
                confidence=0.90,
                reason="Meta-action: system infrastructure request",
                sub_mode=PlanningMode.REACT,
                meta_action_hint=True,
            ),
        }

        # Clear registry before test
        registry = get_escalation_registry()
        registry.clear("test-conv-meta")

        # Mock orchestrator to return success without self-mod tools
        mock_instance = AsyncMock()
        mock_instance.orchestrate = AsyncMock(
            return_value=MagicMock(
                success=True,
                needs_escalation=False,
                output="I can help.",
                partial_results=[],
                reasoning=None,
                reasoning_summary=None,
                streamed=False,
            )
        )
        mock_instance.thinking = MagicMock()
        mock_instance.thinking._on_cost_event = None
        mock_instance.thinking._get_llm = MagicMock(return_value=MagicMock(model="test"))
        mock_instance.agents = MagicMock()
        mock_instance.agents.list_agents = MagicMock(return_value=[])

        with patch("core.orchestrator.orchestrator.DryadeOrchestrator", return_value=mock_instance):
            with patch("core.adapters.registry.get_registry") as mock_reg:
                mock_reg.return_value = MagicMock()
                mock_reg.return_value.list_agents.return_value = []
                with patch(
                    "core.orchestrator.cancellation.get_cancellation_registry"
                ) as mock_cancel:
                    mock_cancel.return_value = MagicMock()
                    mock_cancel.return_value.get_or_create.return_value = None

                    events = []
                    async for event in handler.handle(
                        "add a Brave Search tool", context, stream=True
                    ):
                        events.append(event)

        # Verify escalation was registered via fallback
        pending = registry.get_pending("test-conv-meta")
        assert pending is not None, "PendingEscalation not registered"
        assert pending.action.action_type.value == "factory_create"
        assert "Brave Search tool" in pending.original_goal

        # Cleanup
        registry.clear("test-conv-meta")

    @pytest.mark.asyncio
    async def test_non_meta_action_complex_not_intercepted(self):
        """COMPLEX tier requests WITHOUT meta_action_hint must NOT be intercepted."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.orchestrator.complexity import PlanningMode, TierDecision
        from core.orchestrator.handlers.complex_handler import ComplexHandler
        from core.orchestrator.models import Tier

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-normal"
        context.user_id = "test-user"
        context.metadata = {
            "_tier_decision": TierDecision(
                tier=Tier.COMPLEX,
                confidence=0.75,
                reason="Short goal with no multi-step signals",
                sub_mode=PlanningMode.REACT,
                meta_action_hint=False,  # NOT a meta-action
            ),
            "orchestration_mode": "adaptive",
            "memory_enabled": True,
            "reasoning_visibility": "summary",
        }

        # DryadeOrchestrator is imported locally inside handle(), so we
        # patch at its source module rather than at the handler module.
        mock_instance = AsyncMock()
        mock_instance.orchestrate = AsyncMock(
            return_value=MagicMock(
                success=True,
                needs_escalation=False,
                output="Done",
                partial_results=[],
                reasoning=None,
                reasoning_summary=None,
                streamed=False,
            )
        )
        mock_instance.thinking = MagicMock()
        mock_instance.thinking._on_cost_event = None
        mock_instance.thinking._get_llm = MagicMock(return_value=MagicMock(model="test"))
        mock_instance.agents = MagicMock()
        mock_instance.agents.list_agents = MagicMock(return_value=[])

        with patch(
            "core.orchestrator.orchestrator.DryadeOrchestrator", return_value=mock_instance
        ) as MockOrch:
            with patch("core.adapters.registry.get_registry") as mock_reg:
                mock_reg.return_value = MagicMock()
                mock_reg.return_value.list_agents.return_value = []

                with patch(
                    "core.orchestrator.cancellation.get_cancellation_registry"
                ) as mock_cancel:
                    mock_cancel.return_value = MagicMock()
                    mock_cancel.return_value.get_or_create.return_value = None

                    events = []
                    async for event in handler.handle(
                        "analyze this document", context, stream=True
                    ):
                        events.append(event)

                    # DryadeOrchestrator.orchestrate() MUST have been called
                    mock_instance.orchestrate.assert_called_once()

    @pytest.mark.asyncio
    async def test_meta_action_escalation_contains_original_message(self):
        """Escalation task_description must contain the user's original request."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.orchestrator.complexity import PlanningMode, TierDecision
        from core.orchestrator.escalation import get_escalation_registry
        from core.orchestrator.handlers.complex_handler import ComplexHandler
        from core.orchestrator.models import Tier

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-desc"
        context.user_id = "test-user"
        context.metadata = {
            "_tier_decision": TierDecision(
                tier=Tier.COMPLEX,
                confidence=0.90,
                reason="Meta-action: system infrastructure request",
                sub_mode=PlanningMode.REACT,
                meta_action_hint=True,
            ),
        }

        registry = get_escalation_registry()
        registry.clear("test-conv-desc")

        # Mock orchestrator to return success without self-mod tools
        mock_instance = AsyncMock()
        mock_instance.orchestrate = AsyncMock(
            return_value=MagicMock(
                success=True,
                needs_escalation=False,
                output="Done.",
                partial_results=[],
                reasoning=None,
                reasoning_summary=None,
                streamed=False,
            )
        )
        mock_instance.thinking = MagicMock()
        mock_instance.thinking._on_cost_event = None
        mock_instance.thinking._get_llm = MagicMock(return_value=MagicMock(model="test"))
        mock_instance.agents = MagicMock()
        mock_instance.agents.list_agents = MagicMock(return_value=[])

        with patch("core.orchestrator.orchestrator.DryadeOrchestrator", return_value=mock_instance):
            with patch("core.adapters.registry.get_registry") as mock_reg:
                mock_reg.return_value = MagicMock()
                mock_reg.return_value.list_agents.return_value = []
                with patch(
                    "core.orchestrator.cancellation.get_cancellation_registry"
                ) as mock_cancel:
                    mock_cancel.return_value = MagicMock()
                    mock_cancel.return_value.get_or_create.return_value = None

                    events = []
                    async for event in handler.handle(
                        "configure a new MCP server for GitHub", context, stream=True
                    ):
                        events.append(event)

        pending = registry.get_pending("test-conv-desc")
        assert pending is not None
        assert pending.action.parameters["goal"] == "configure a new MCP server for GitHub"

        registry.clear("test-conv-desc")
