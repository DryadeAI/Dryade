"""Unit tests for DryadeOrchestrator.

Covers:
- Initialization with default and custom configs
- Mode dispatch (orchestrate method with different modes)
- ReAct loop: single-iteration, multi-iteration, max-iterations exceeded
- Error handling: LLM failures, tool failures, error boundary
- Cancellation support
- Parallel execution
- Capability validation
- Failure handling: skip, escalate, alternative agent
- Streaming callbacks (on_thinking, on_agent_event)
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.adapters.registry import AgentRegistry
from core.autonomous.leash import LEASH_STANDARD, LeashConfig
from core.orchestrator.models import (
    FailureAction,
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.orchestrator import (
    DryadeOrchestrator,
    OrchestrationErrorBoundary,
    _emit_event,
)
from core.orchestrator.thinking import OrchestrationThinkingProvider

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

class StubAgent(UniversalAgent):
    """Minimal agent for testing."""

    def __init__(
        self,
        name: str = "test-agent",
        description: str = "A test agent",
        result: str = "done",
        status: str = "ok",
        caps: AgentCapabilities | None = None,
        raise_on_execute: Exception | None = None,
    ):
        self._name = name
        self._description = description
        self._result = result
        self._status = status
        self._caps = caps or AgentCapabilities()
        self._raise_on_execute = raise_on_execute

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description=self._description,
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task, context=None):
        if self._raise_on_execute:
            raise self._raise_on_execute
        return AgentResult(result=self._result, status=self._status)

    def get_tools(self):
        return []

    def capabilities(self) -> AgentCapabilities:
        return self._caps

def _make_registry(*agents: UniversalAgent) -> AgentRegistry:
    """Build a registry pre-loaded with the given agents."""
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg

def _make_thinking(
    *,
    orchestrate_response: OrchestrationThought | None = None,
    failure_response: OrchestrationThought | None = None,
) -> OrchestrationThinkingProvider:
    """Return a mock-backed thinking provider."""
    tp = MagicMock(spec=OrchestrationThinkingProvider)
    tp._on_cost_event = None

    if orchestrate_response is None:
        orchestrate_response = OrchestrationThought(
            reasoning="Immediate answer",
            is_final=True,
            answer="The answer is 42",
        )
    tp.orchestrate_think = AsyncMock(return_value=orchestrate_response)

    if failure_response is None:
        failure_response = OrchestrationThought(
            reasoning="Escalating due to failure",
            is_final=False,
            failure_action=FailureAction.ESCALATE,
            escalation_question="How should I proceed?",
        )
    tp.failure_think = AsyncMock(return_value=failure_response)

    return tp

@pytest.fixture(autouse=True)
def _disable_prevention_checks():
    """Disable prevention-layer network probes for all orchestrator tests."""
    with patch.dict(
        os.environ,
        {
            "DRYADE_PREVENTION_ENABLED": "false",
            "DRYADE_MODEL_REACHABILITY_ENABLED": "false",
        },
    ):
        yield

# ---------------------------------------------------------------------------
# TestOrchestratorInitialization
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorInitialization:
    """Verify constructor wiring and defaults."""

    def test_default_init(self):
        """Orchestrator can be constructed with defaults (lazy providers)."""
        orch = DryadeOrchestrator()
        assert orch.thinking is not None
        assert orch.agents is not None
        assert orch.leash is not None

    def test_custom_thinking_provider(self):
        """Custom thinking provider is stored."""
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp)
        assert orch.thinking is tp

    def test_custom_registry(self):
        """Custom agent registry is stored when non-empty.

        Note: Empty AgentRegistry is falsy (due to __len__==0), so
        the ``or get_registry()`` fallback kicks in. Pre-populate
        the registry to test the custom path.
        """
        reg = _make_registry(StubAgent(name="sentinel"))
        orch = DryadeOrchestrator(agent_registry=reg)
        assert orch.agents is reg

    def test_custom_leash(self):
        """Custom leash config is stored."""
        leash = LeashConfig(max_actions=5)
        orch = DryadeOrchestrator(leash=leash)
        assert orch.leash is leash
        assert orch.leash.max_actions == 5

    def test_default_leash_is_standard(self):
        """Default leash is LEASH_STANDARD."""
        orch = DryadeOrchestrator()
        assert orch.leash is LEASH_STANDARD

# ---------------------------------------------------------------------------
# TestOrchestratorModeDispatch
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorModeDispatch:
    """The orchestrate method accepts different modes correctly."""

    async def test_sequential_mode(self):
        """SEQUENTIAL mode passes through to orchestrate_think."""
        tp = _make_thinking()
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("test goal", mode=OrchestrationMode.SEQUENTIAL)
        assert result.success is True
        assert result.output == "The answer is 42"
        tp.orchestrate_think.assert_awaited()

    async def test_parallel_mode(self):
        """PARALLEL mode also reaches orchestrate_think."""
        tp = _make_thinking()
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("test goal", mode=OrchestrationMode.PARALLEL)
        assert result.success is True

    async def test_hierarchical_mode(self):
        """HIERARCHICAL mode also reaches orchestrate_think."""
        tp = _make_thinking()
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("test goal", mode=OrchestrationMode.HIERARCHICAL)
        assert result.success is True

    async def test_adaptive_mode_default(self):
        """ADAPTIVE mode is the default."""
        tp = _make_thinking()
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("test goal")
        assert result.success is True
        call_args = tp.orchestrate_think.call_args
        # Mode is stored in state, not passed directly to thinking provider
        # Check the state stored in result instead
        assert result.state is not None
        assert result.state.mode == OrchestrationMode.ADAPTIVE

# ---------------------------------------------------------------------------
# TestOrchestratorReActLoop
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorReActLoop:
    """Test the ReAct (Reason-Act) loop iterations."""

    async def test_single_iteration_final_answer(self):
        """LLM returns is_final=True on first call, loop exits immediately."""
        tp = _make_thinking(
            orchestrate_response=OrchestrationThought(
                reasoning="Goal already clear",
                is_final=True,
                answer="Direct answer",
            ),
        )
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("simple question")
        assert result.success is True
        assert result.output == "Direct answer"
        assert result.state.actions_taken == 1

    async def test_multi_iteration_tool_then_answer(self):
        """LLM calls a tool on step 1, then returns final answer on step 2."""
        call_count = 0

        async def fake_orchestrate_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Need to call test-agent",
                    is_final=False,
                    task=OrchestrationTask(
                        agent_name="test-agent",
                        description="do the thing",
                    ),
                )
            return OrchestrationThought(
                reasoning="Got the result, done",
                is_final=True,
                answer="Combined result",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_orchestrate_think)

        agent = StubAgent(name="test-agent", result="tool output")
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("complex goal")
        assert result.success is True
        assert result.output == "Combined result"
        assert result.state.actions_taken == 2
        assert len(result.partial_results) == 1  # one agent execution

    async def test_max_iterations_leash_exceeded(self):
        """When leash max_actions exceeded, loop exits with escalation."""
        tp = _make_thinking(
            orchestrate_response=OrchestrationThought(
                reasoning="Keep going",
                is_final=False,
                task=OrchestrationTask(agent_name="test-agent", description="work"),
            ),
        )
        agent = StubAgent(name="test-agent")
        reg = _make_registry(agent)
        leash = LeashConfig(max_actions=2)
        orch = DryadeOrchestrator(
            thinking_provider=tp,
            agent_registry=reg,
            leash=leash,
        )

        result = await orch.orchestrate("infinite loop goal")
        assert result.success is False
        assert result.needs_escalation is True
        assert "resource limit" in result.escalation_question

    async def test_no_action_specified_triggers_escalation(self):
        """Thought with no task and not final creates an error observation.

        The resulting observation has no failure_thought attached (since it
        didn't go through _execute_with_retry), so _handle_failure defaults
        to escalation.  This is the correct graceful-degradation behavior.
        """
        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(
            return_value=OrchestrationThought(
                reasoning="I'm confused",
                is_final=False,
                task=None,
                parallel_tasks=None,
            )
        )

        agent = StubAgent(name="test-agent")
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("confusing goal")
        # The no-action observation triggers default escalation
        assert result.success is False
        assert result.needs_escalation is True

# ---------------------------------------------------------------------------
# TestOrchestratorErrorHandling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorErrorHandling:
    """Error handling: LLM failures, tool failures, error boundary."""

    async def test_no_agents_available(self):
        """Orchestrate with no agents returns failure."""
        tp = _make_thinking()
        reg = AgentRegistry()  # empty

        # Mock get_registry to prevent fallback to global singleton.
        # Empty AgentRegistry is falsy (len==0), so `agent_registry or get_registry()`
        # in the constructor would silently replace it with the global singleton.
        with patch("core.orchestrator.orchestrator.get_registry", return_value=reg):
            orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)
            result = await orch.orchestrate("any goal")

        assert result.success is False
        assert "no agents" in (result.reason or "").lower()

    async def test_no_agents_after_filter(self):
        """agent_filter that matches nothing returns failure."""
        tp = _make_thinking()
        reg = _make_registry(StubAgent(name="real-agent"))
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate(
            "goal",
            agent_filter=["nonexistent-agent"],
        )
        assert result.success is False
        assert "no agents" in (result.reason or "").lower()

    async def test_agent_not_found_during_execution(self):
        """Task referencing a non-existent agent produces error and escalation.

        When agent is not found, _execute_with_retry returns early without
        calling failure_think (no failure_thought attached). The default
        _handle_failure path then escalates.
        """
        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(
            return_value=OrchestrationThought(
                reasoning="Use ghost agent",
                is_final=False,
                task=OrchestrationTask(
                    agent_name="ghost-agent",
                    description="something",
                ),
            )
        )

        agent = StubAgent(name="real-agent")
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        # Mock _handle_capability_gap to prevent real LLM calls via factory
        with patch.object(
            orch, "_handle_capability_gap", new_callable=AsyncMock, return_value=None
        ):
            result = await orch.orchestrate("use ghost agent")
        # Agent not found => escalation (default when failure_thought missing)
        assert result.success is False
        assert result.needs_escalation is True

    async def test_agent_execute_raises_exception(self):
        """Agent raising during execute produces failure observation."""
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Call failing agent",
                    is_final=False,
                    task=OrchestrationTask(
                        agent_name="exploding-agent",
                        description="boom",
                    ),
                )
            return OrchestrationThought(
                reasoning="Done anyway",
                is_final=True,
                answer="handled",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)
        tp.failure_think = AsyncMock(
            return_value=OrchestrationThought(
                reasoning="Skip the failure",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )
        )

        agent = StubAgent(
            name="exploding-agent",
            raise_on_execute=RuntimeError("kaboom"),
        )
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("run exploding agent")
        assert result.success is True
        assert result.output == "handled"

    async def test_agent_timeout(self):
        """Agent that takes too long triggers timeout error."""
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Call slow agent",
                    is_final=False,
                    task=OrchestrationTask(
                        agent_name="slow-agent",
                        description="slow task",
                    ),
                )
            return OrchestrationThought(
                reasoning="Done",
                is_final=True,
                answer="timed out handled",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)
        tp.failure_think = AsyncMock(
            return_value=OrchestrationThought(
                reasoning="Skip timed out",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )
        )

        # Agent that sleeps forever
        agent = StubAgent(name="slow-agent")
        original_execute = agent.execute

        async def slow_execute(task, context=None):
            await asyncio.sleep(999)
            return await original_execute(task, context)

        agent.execute = slow_execute

        # Set 1-second timeout via capabilities
        agent._caps = AgentCapabilities(timeout_seconds=1)

        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("slow goal")
        assert result.success is True

# ---------------------------------------------------------------------------
# TestOrchestrationErrorBoundary
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestrationErrorBoundary:
    """Test the error boundary context manager."""

    async def test_no_error(self):
        """No exception => error is None."""
        async with OrchestrationErrorBoundary(None, "exec-1") as boundary:
            pass
        assert boundary.error is None

    async def test_catches_exception(self):
        """Exception is caught and stored."""
        async with OrchestrationErrorBoundary(None, "exec-2") as boundary:
            raise ValueError("test error")
        assert boundary.error is not None
        assert "test error" in str(boundary.error)

    async def test_fallback_result(self):
        """Fallback result contains escalation info."""
        async with OrchestrationErrorBoundary(None, "exec-3") as boundary:
            raise RuntimeError("catastrophic")
        result = boundary.get_fallback_result()
        assert result.success is False
        assert result.needs_escalation is True
        assert "catastrophic" in (result.escalation_question or "")
        assert "RuntimeError" in (result.reason or "")

    async def test_error_boundary_integration_in_orchestrate(self):
        """Catastrophic error in thinking provider is caught by error boundary."""
        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=RuntimeError("LLM exploded"))

        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("trigger error boundary")
        assert result.success is False
        assert result.needs_escalation is True

# ---------------------------------------------------------------------------
# TestOrchestratorCancellation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorCancellation:
    """Cancellation via cancel_event."""

    async def test_cancel_before_first_iteration(self):
        """Pre-set cancel event stops orchestration immediately."""
        tp = _make_thinking()
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        cancel = asyncio.Event()
        cancel.set()  # Already cancelled

        result = await orch.orchestrate("goal", cancel_event=cancel)
        assert result.success is False
        assert result.cancelled is True
        assert "cancel" in (result.reason or "").lower()

    async def test_cancel_after_first_iteration(self):
        """Cancel event set during execution stops before next iteration."""
        cancel = asyncio.Event()
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                cancel.set()  # Trigger cancellation after first action
                return OrchestrationThought(
                    reasoning="First step",
                    is_final=False,
                    task=OrchestrationTask(
                        agent_name="test-agent",
                        description="step 1",
                    ),
                )
            return OrchestrationThought(
                reasoning="Should not reach here",
                is_final=True,
                answer="should not appear",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)

        agent = StubAgent(name="test-agent")
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("cancellable goal", cancel_event=cancel)
        assert result.cancelled is True
        assert len(result.partial_results) >= 1

# ---------------------------------------------------------------------------
# TestOrchestratorParallelExecution
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorParallelExecution:
    """Parallel task execution via parallel_tasks."""

    async def test_parallel_tasks_execute_concurrently(self):
        """Multiple tasks are dispatched via asyncio.gather."""
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Run two in parallel",
                    is_final=False,
                    parallel_tasks=[
                        OrchestrationTask(agent_name="agent-a", description="task A"),
                        OrchestrationTask(agent_name="agent-b", description="task B"),
                    ],
                )
            return OrchestrationThought(
                reasoning="Both done",
                is_final=True,
                answer="parallel complete",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)

        agent_a = StubAgent(name="agent-a", result="result-a")
        agent_b = StubAgent(name="agent-b", result="result-b")
        reg = _make_registry(agent_a, agent_b)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("parallel goal")
        assert result.success is True
        assert result.output == "parallel complete"
        assert len(result.partial_results) == 2

# ---------------------------------------------------------------------------
# TestCapabilityValidation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCapabilityValidation:
    """Test _validate_capabilities method."""

    def test_no_required_capabilities(self):
        """No required capabilities => always valid."""
        agent = StubAgent()
        orch = DryadeOrchestrator()
        task = OrchestrationTask(
            agent_name="test-agent",
            description="something",
            required_capabilities=[],
        )
        valid, error = orch._validate_capabilities(agent, task)
        assert valid is True
        assert error is None

    def test_missing_streaming_capability(self):
        """Agent missing streaming when required => invalid."""
        agent = StubAgent(caps=AgentCapabilities(supports_streaming=False))
        orch = DryadeOrchestrator()
        task = OrchestrationTask(
            agent_name="test-agent",
            description="stream something",
            required_capabilities=["streaming"],
        )
        valid, error = orch._validate_capabilities(agent, task)
        assert valid is False
        assert "streaming" in (error or "")

    def test_multiple_missing_capabilities(self):
        """Multiple missing capabilities are all listed."""
        agent = StubAgent(
            caps=AgentCapabilities(
                supports_streaming=False,
                supports_memory=False,
            )
        )
        orch = DryadeOrchestrator()
        task = OrchestrationTask(
            agent_name="test-agent",
            description="complex task",
            required_capabilities=["streaming", "memory"],
        )
        valid, error = orch._validate_capabilities(agent, task)
        assert valid is False
        assert "streaming" in (error or "")
        assert "memory" in (error or "")

    def test_all_capabilities_present(self):
        """Agent with all required capabilities => valid."""
        agent = StubAgent(
            caps=AgentCapabilities(
                supports_streaming=True,
                supports_memory=True,
                supports_delegation=True,
            )
        )
        orch = DryadeOrchestrator()
        task = OrchestrationTask(
            agent_name="test-agent",
            description="full-featured task",
            required_capabilities=["streaming", "memory", "delegation"],
        )
        valid, error = orch._validate_capabilities(agent, task)
        assert valid is True
        assert error is None

# ---------------------------------------------------------------------------
# TestOrchestratorFailureHandling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorFailureHandling:
    """Test _handle_failure method with different failure actions."""

    async def test_skip_non_critical_task(self):
        """SKIP on non-critical task returns success to continue loop."""
        agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="optional work",
            result=None,
            success=False,
            error="Something failed",
        )
        # Attach failure thought with SKIP
        obs.failure_thought = OrchestrationThought(
            reasoning="Not critical, skip",
            is_final=False,
            failure_action=FailureAction.SKIP,
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()
        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        assert result.success is True  # Continue orchestration

    async def test_skip_critical_task_escalates(self):
        """SKIP on critical task escalates instead."""
        agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=True))
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="critical work",
            result=None,
            success=False,
            error="Something failed",
        )
        obs.failure_thought = OrchestrationThought(
            reasoning="Want to skip",
            is_final=False,
            failure_action=FailureAction.SKIP,
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()
        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        assert result.success is False
        assert result.needs_escalation is True

    @patch("core.orchestrator.orchestrator.DryadeOrchestrator._execute_single")
    async def test_alternative_agent_success(self, mock_execute_single):
        """ALTERNATIVE action tries a different agent and succeeds."""
        mock_execute_single.return_value = OrchestrationObservation(
            agent_name="backup-agent",
            task="the work",
            result="backup result",
            success=True,
        )

        agent = StubAgent(name="test-agent")
        backup = StubAgent(name="backup-agent")
        reg = _make_registry(agent, backup)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="the work",
            result=None,
            success=False,
            error="Original failed",
        )
        obs.failure_thought = OrchestrationThought(
            reasoning="Try backup",
            is_final=False,
            failure_action=FailureAction.ALTERNATIVE,
            alternative_agent="backup-agent",
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()
        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        assert result.success is True
        assert result.alternative_agent_used == "backup-agent"

    @patch("core.orchestrator.orchestrator.DryadeOrchestrator._execute_single")
    async def test_alternative_agent_fails_escalates(self, mock_execute_single):
        """ALTERNATIVE action where backup also fails => escalation."""
        mock_execute_single.return_value = OrchestrationObservation(
            agent_name="backup-agent",
            task="the work",
            result=None,
            success=False,
            error="Backup also failed",
        )

        agent = StubAgent(name="test-agent")
        backup = StubAgent(name="backup-agent")
        reg = _make_registry(agent, backup)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="the work",
            result=None,
            success=False,
            error="Original failed",
        )
        obs.failure_thought = OrchestrationThought(
            reasoning="Try backup",
            is_final=False,
            failure_action=FailureAction.ALTERNATIVE,
            alternative_agent="backup-agent",
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()
        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        assert result.success is False
        assert result.needs_escalation is True

    async def test_escalate_action(self):
        """ESCALATE action returns needs_escalation result."""
        agent = StubAgent(name="test-agent")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="failing task",
            result=None,
            success=False,
            error="Permission denied",
        )
        obs.failure_thought = OrchestrationThought(
            reasoning="Need user help",
            is_final=False,
            failure_action=FailureAction.ESCALATE,
            escalation_question="Can you fix permissions?",
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()

        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        assert result.success is False
        assert result.needs_escalation is True
        assert "permissions" in (result.escalation_question or "").lower()

    async def test_missingfailure_thought_defaults_escalation(self):
        """If failure_thought is missing, _handle_failure defaults to escalation."""
        agent = StubAgent(name="test-agent")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="test-agent",
            task="broken",
            result=None,
            success=False,
            error="some error",
        )
        # Deliberately do NOT set failure_thought

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()

        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        assert result.success is False
        assert result.needs_escalation is True

    async def test_same_agent_alternative_escalates(self):
        """When failure_think suggests the same agent as alternative, escalation occurs (RC4)."""
        agent = StubAgent(name="mcp-capella")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        obs = OrchestrationObservation(
            agent_name="mcp-capella",
            task="open model",
            result=None,
            success=False,
            error="Tool not found",
        )
        # Attach a failure thought that suggests the SAME agent as alternative
        obs.failure_thought = OrchestrationThought(
            reasoning="Try mcp-capella again",
            is_final=False,
            failure_action=FailureAction.ALTERNATIVE,
            alternative_agent="mcp-capella",  # Same as failed agent!
        )

        from core.orchestrator.models import OrchestrationState

        state = OrchestrationState()

        result = await orch._handle_failure(obs, {}, reg.list_agents(), state)
        # Should escalate, not try the same agent
        assert result.success is False
        assert result.needs_escalation is True
        assert "mcp-capella" in result.escalation_question

# ---------------------------------------------------------------------------
# TestOrchestratorCallbacks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorCallbacks:
    """Test on_thinking and on_agent_event callbacks."""

    async def test_on_thinking_callback_called(self):
        """on_thinking is called with reasoning text."""
        thinking_events = []

        tp = _make_thinking(
            orchestrate_response=OrchestrationThought(
                reasoning="Deep reasoning here",
                reasoning_summary="Summary here",
                is_final=True,
                answer="done",
            ),
        )
        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate(
            "goal",
            on_thinking=lambda text: thinking_events.append(text),
        )
        assert result.success is True
        # on_thinking should have been called with reasoning_summary (preferred)
        assert len(thinking_events) >= 1
        assert "Summary here" in thinking_events[0]

    async def test_on_agent_event_callback_for_single_task(self):
        """on_agent_event emits agent_start and agent_complete for single task."""
        events = []
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Call agent",
                    is_final=False,
                    task=OrchestrationTask(
                        agent_name="test-agent",
                        description="task 1",
                    ),
                )
            return OrchestrationThought(
                reasoning="Done",
                is_final=True,
                answer="result",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)

        agent = StubAgent(name="test-agent")
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate(
            "goal",
            on_agent_event=lambda etype, data: events.append((etype, data)),
        )
        assert result.success is True
        event_types = [e[0] for e in events]
        assert "agent_start" in event_types
        assert "agent_complete" in event_types

    async def test_on_agent_event_for_parallel_tasks(self):
        """on_agent_event emits start/complete for each parallel task."""
        events = []
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Parallel",
                    is_final=False,
                    parallel_tasks=[
                        OrchestrationTask(agent_name="a1", description="t1"),
                        OrchestrationTask(agent_name="a2", description="t2"),
                    ],
                )
            return OrchestrationThought(
                reasoning="Done",
                is_final=True,
                answer="parallel done",
            )

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)

        a1 = StubAgent(name="a1")
        a2 = StubAgent(name="a2")
        reg = _make_registry(a1, a2)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate(
            "goal",
            on_agent_event=lambda etype, data: events.append((etype, data)),
        )
        assert result.success is True
        starts = [e for e in events if e[0] == "agent_start"]
        completes = [e for e in events if e[0] == "agent_complete"]
        assert len(starts) == 2
        assert len(completes) == 2

# ---------------------------------------------------------------------------
# TestEmitEvent helper
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmitEvent:
    """Test the _emit_event helper function."""

    def test_emit_event_calls_callback(self):
        """Callback is invoked with event type and data."""
        cb = MagicMock()
        _emit_event(cb, "test_event", {"key": "val"})
        cb.assert_called_once_with("test_event", {"key": "val"})

    def test_emit_event_none_callback(self):
        """None callback is safely ignored."""
        _emit_event(None, "test_event", {"key": "val"})  # should not raise

# ---------------------------------------------------------------------------
# TestLeashExceeded
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLeashExceeded:
    """Test _leash_exceeded private method."""

    def test_not_exceeded_at_start(self):
        """Fresh state does not exceed leash."""
        from core.orchestrator.models import OrchestrationState

        orch = DryadeOrchestrator()
        state = OrchestrationState()
        assert orch._leash_exceeded(state, []) is False

    def test_actions_exceeded(self):
        """Actions at or above max_actions triggers exceeded."""
        from core.orchestrator.models import OrchestrationState

        leash = LeashConfig(max_actions=3)
        orch = DryadeOrchestrator(leash=leash)
        state = OrchestrationState(actions_taken=3)
        assert orch._leash_exceeded(state, []) is True

    def test_actions_below_limit(self):
        """Actions below limit does not exceed."""
        from core.orchestrator.models import OrchestrationState

        leash = LeashConfig(max_actions=10)
        orch = DryadeOrchestrator(leash=leash)
        state = OrchestrationState(actions_taken=5)
        assert orch._leash_exceeded(state, []) is False

# ---------------------------------------------------------------------------
# TestOrchestratorRetryLogic
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorRetryLogic:
    """Test _execute_with_retry behavior."""

    async def test_success_on_first_attempt(self):
        """Successful first execution returns immediately without retry."""
        agent = StubAgent(name="good-agent", result="success")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        task = OrchestrationTask(agent_name="good-agent", description="easy task")
        result = await orch._execute_with_retry(task, "exec-1", {}, reg.list_agents())
        assert result.success is True
        assert result.retry_count == 0

    async def test_agent_not_found_returns_error(self):
        """Task for nonexistent agent returns error observation."""
        reg = _make_registry(StubAgent(name="other-agent"))
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        task = OrchestrationTask(agent_name="missing-agent", description="task")
        result = await orch._execute_with_retry(task, "exec-2", {}, reg.list_agents())
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    async def test_capability_validation_failure(self):
        """Task requiring capability agent lacks returns error."""
        agent = StubAgent(
            name="limited-agent",
            caps=AgentCapabilities(supports_streaming=False),
        )
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        task = OrchestrationTask(
            agent_name="limited-agent",
            description="needs streaming",
            required_capabilities=["streaming"],
        )
        result = await orch._execute_with_retry(task, "exec-3", {}, reg.list_agents())
        assert result.success is False
        assert "streaming" in (result.error or "").lower()

    async def test_llm_says_no_retry(self):
        """When failure_think says ESCALATE (not RETRY), no retry occurs."""
        agent = StubAgent(name="fail-agent", status="error")
        agent._result = None

        # Override execute to return error status
        async def fail_execute(task, context=None):
            return AgentResult(result=None, status="error", error="config error")

        agent.execute = fail_execute
        reg = _make_registry(agent)
        tp = _make_thinking(
            failure_response=OrchestrationThought(
                reasoning="Config error, no retry",
                is_final=False,
                failure_action=FailureAction.ESCALATE,
                escalation_question="Fix your config",
            ),
        )
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        task = OrchestrationTask(agent_name="fail-agent", description="failing task")
        result = await orch._execute_with_retry(task, "exec-4", {}, reg.list_agents())
        assert result.success is False
        assert result.retry_count == 0
        # failure_think should have been called exactly once
        tp.failure_think.assert_awaited_once()

# ---------------------------------------------------------------------------
# TestOrchestratorEscalationInLoop
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorEscalationInLoop:
    """Test that escalation results from _handle_failure propagate to orchestrate()."""

    async def test_escalation_returns_from_orchestrate(self):
        """When _handle_failure returns needs_escalation, orchestrate() returns it."""
        call_count = 0

        async def fake_think(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationThought(
                    reasoning="Use failing agent",
                    is_final=False,
                    task=OrchestrationTask(
                        agent_name="fail-agent",
                        description="doomed task",
                        is_critical=True,
                    ),
                )
            # Should not reach here
            return OrchestrationThought(reasoning="x", is_final=True, answer="x")

        tp = _make_thinking()
        tp.orchestrate_think = AsyncMock(side_effect=fake_think)
        tp.failure_think = AsyncMock(
            return_value=OrchestrationThought(
                reasoning="Must escalate",
                is_final=False,
                failure_action=FailureAction.ESCALATE,
                escalation_question="Help needed",
            )
        )

        agent = StubAgent(
            name="fail-agent",
            raise_on_execute=RuntimeError("permanent failure"),
            caps=AgentCapabilities(max_retries=0),
        )
        reg = _make_registry(agent)
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("goal needing escalation")

        assert result.success is False
        assert result.needs_escalation is True
        assert result.original_goal == "goal needing escalation"

# ---------------------------------------------------------------------------
# TestOrchestratorStreaming (Phase 88-02)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrchestratorStreaming:
    """Test on_token streaming path in orchestrate()."""

    async def test_orchestrate_streams_final_answer_when_on_token_provided(self):
        """When on_token is provided and is_final, _stream_final_answer is used."""
        tp = _make_thinking(
            orchestrate_response=OrchestrationThought(
                reasoning="Direct answer",
                is_final=True,
                answer="Pre-computed answer",
            ),
        )
        # Mock _stream_final_answer to return streamed content
        tp._stream_final_answer = AsyncMock(return_value=("Streamed content here", "", 10))

        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        token_cb = MagicMock()
        result = await orch.orchestrate(
            "test goal",
            on_token=token_cb,
        )

        # _stream_final_answer should have been called
        tp._stream_final_answer.assert_awaited_once()
        # Result should reflect streamed content
        assert result.success is True
        assert result.output == "Streamed content here"
        assert result.streamed is True

    async def test_orchestrate_does_not_stream_when_no_on_token(self):
        """Without on_token, _stream_final_answer is NOT called; uses pre-computed answer."""
        tp = _make_thinking(
            orchestrate_response=OrchestrationThought(
                reasoning="Direct answer",
                is_final=True,
                answer="Pre-computed answer",
            ),
        )
        tp._stream_final_answer = AsyncMock(return_value=("Should not appear", "", 10))

        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        result = await orch.orchestrate("test goal")

        # _stream_final_answer should NOT have been called
        tp._stream_final_answer.assert_not_awaited()
        # Result uses pre-computed answer
        assert result.success is True
        assert result.output == "Pre-computed answer"
        assert result.streamed is False

    async def test_orchestrate_fallback_uses_streamed_reasoning(self):
        """When content stream is empty but reasoning stream has data,
        the orchestrator falls back to streamed_reasoning (not thought.answer)."""
        tp = _make_thinking(
            orchestrate_response=OrchestrationThought(
                reasoning="LLM reasoning preamble",
                is_final=True,
                answer="We need to respond. The user says hello.",
            ),
        )
        # _stream_final_answer returns empty content but non-empty reasoning
        tp._stream_final_answer = AsyncMock(return_value=("", "The answer is 42.", 5))

        reg = _make_registry(StubAgent())
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        token_cb = MagicMock()
        result = await orch.orchestrate(
            "test goal",
            on_token=token_cb,
        )

        # Should use streamed reasoning, NOT thought.answer
        assert result.success is True
        assert result.output == "The answer is 42."
        # on_token was called with the reasoning fallback
        token_cb.assert_called_with("The answer is 42.")
        assert result.streamed is True

# ---------------------------------------------------------------------------
# TestCircuitBreakerIntegration (Phase 118.2)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCircuitBreakerIntegration:
    """Test CircuitBreaker integration in _execute_with_retry."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_open_server(self):
        """When circuit is OPEN for an MCP server, _execute_with_retry returns SKIP observation."""
        agent = StubAgent(name="mcp-filesystem", result="done")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        # Force circuit open by recording enough failures (default threshold is 5)
        cb = orch.circuit_breaker
        for _ in range(cb._config.failure_threshold):
            cb.record_failure("filesystem")

        task = OrchestrationTask(agent_name="mcp-filesystem", description="list files")
        # Disable the connectivity probe: it runs before the circuit breaker check
        # and would fail on "server not registered" before the circuit state is checked.
        # The circuit breaker behavior is what this test verifies, not probe behavior.
        with patch("core.orchestrator.orchestrator.get_orchestration_config") as mock_get_cfg:
            real_cfg = mock_get_cfg.return_value
            real_cfg.prevention_enabled = False
            real_cfg.circuit_breaker_enabled = True
            real_cfg.pre_emptive_circuit_breaking_enabled = False
            real_cfg.failure_metrics_enabled = False
            real_cfg.obs_result_max_chars = 5000
            real_cfg.agent_timeout = 30
            real_cfg.max_retries = 3
            real_cfg.action_autonomy_enabled = False
            real_cfg.soft_failure_detection_enabled = False
            real_cfg.routing_metrics_enabled = False
            result = await orch._execute_with_retry(task, "exec-cb-1", {}, reg.list_agents())

        assert result.success is False
        assert "circuit is open" in (result.error or "").lower()
        assert result.failure_thought is not None
        assert result.failure_thought.failure_action == FailureAction.SKIP

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_success_on_success(self):
        """Successful _execute_single triggers circuit_breaker.record_success."""
        agent = StubAgent(name="mcp-git", result="ok")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        # Add a failure first, then a success should clear it via record_success
        orch.circuit_breaker.record_failure("git")
        stats_before = orch.circuit_breaker._get_stats("git")
        assert stats_before.failure_count == 1

        task = OrchestrationTask(agent_name="mcp-git", description="git status")
        with patch("core.orchestrator.orchestrator.get_orchestration_config") as mock_get_cfg:
            real_cfg = mock_get_cfg.return_value
            real_cfg.prevention_enabled = False
            real_cfg.circuit_breaker_enabled = True
            real_cfg.pre_emptive_circuit_breaking_enabled = False
            real_cfg.failure_metrics_enabled = False
            real_cfg.obs_result_max_chars = 5000
            real_cfg.agent_timeout = 30
            real_cfg.max_retries = 3
            real_cfg.action_autonomy_enabled = False
            real_cfg.soft_failure_detection_enabled = False
            real_cfg.routing_metrics_enabled = False
            result = await orch._execute_with_retry(task, "exec-cb-2", {}, reg.list_agents())

        assert result.success is True
        # record_success in CLOSED state resets failure count to 0
        stats_after = orch.circuit_breaker._get_stats("git")
        assert stats_after.failure_count == 0
        assert stats_after.state.value == "closed"

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_failure_on_failure(self):
        """Failed _execute_single triggers circuit_breaker.record_failure."""
        agent = StubAgent(name="mcp-docker", raise_on_execute=RuntimeError("connection refused"))
        reg = _make_registry(agent)
        tp = _make_thinking(
            failure_response=OrchestrationThought(
                reasoning="Server error, escalate",
                is_final=False,
                failure_action=FailureAction.ESCALATE,
                escalation_question="Docker unavailable",
            ),
        )
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        task = OrchestrationTask(agent_name="mcp-docker", description="list containers")
        with patch("core.orchestrator.orchestrator.get_orchestration_config") as mock_get_cfg:
            real_cfg = mock_get_cfg.return_value
            real_cfg.prevention_enabled = False
            real_cfg.circuit_breaker_enabled = True
            real_cfg.pre_emptive_circuit_breaking_enabled = False
            real_cfg.failure_metrics_enabled = False
            real_cfg.obs_result_max_chars = 5000
            real_cfg.agent_timeout = 30
            real_cfg.max_retries = 1  # fail fast
            real_cfg.action_autonomy_enabled = False
            real_cfg.soft_failure_detection_enabled = False
            real_cfg.routing_metrics_enabled = False
            result = await orch._execute_with_retry(task, "exec-cb-3", {}, reg.list_agents())

        assert result.success is False
        # Circuit breaker should have recorded at least one failure for "docker" server
        stats = orch.circuit_breaker._get_stats("docker")
        assert len(stats.failure_timestamps) >= 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_non_mcp_agents(self):
        """Non-MCP agents (no 'mcp-' prefix) don't interact with circuit breaker."""
        agent = StubAgent(name="test-agent", result="done")
        reg = _make_registry(agent)
        tp = _make_thinking()
        orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

        task = OrchestrationTask(agent_name="test-agent", description="do stuff")
        with patch("core.orchestrator.orchestrator.get_orchestration_config") as mock_get_cfg:
            real_cfg = mock_get_cfg.return_value
            real_cfg.prevention_enabled = False
            real_cfg.circuit_breaker_enabled = True
            real_cfg.pre_emptive_circuit_breaking_enabled = False
            real_cfg.failure_metrics_enabled = False
            real_cfg.obs_result_max_chars = 5000
            real_cfg.agent_timeout = 30
            real_cfg.max_retries = 3
            real_cfg.action_autonomy_enabled = False
            real_cfg.soft_failure_detection_enabled = False
            real_cfg.routing_metrics_enabled = False
            result = await orch._execute_with_retry(task, "exec-cb-4", {}, reg.list_agents())

        assert result.success is True
        # Circuit breaker should NOT have any servers tracked
        assert orch.circuit_breaker.get_all_states() == {}
