"""Chaos tests: multi-failure cascading scenarios.

Verifies the orchestrator handles sequences of different failure
types, graduated escalation through multiple depths, and simultaneous
failures across multiple agents without crashing or hanging.
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.adapters.protocol import AgentResult
from core.orchestrator.models import (
    FailureAction,
    OrchestrationTask,
    OrchestrationThought,
)
from tests.chaos.conftest import (
    StubAgent,
    make_orchestrator,
    make_registry,
    make_thinking,
)

# ---------------------------------------------------------------------------
# Helper: agent that changes failure mode mid-test
# ---------------------------------------------------------------------------

class ShiftingFailureAgent(StubAgent):
    """Agent that changes failure type based on call count.

    Calls 1-2: raises timeout_error
    Calls 3+:  raises crash_error
    """

    def __init__(
        self,
        name: str = "shifting-agent",
        timeout_error: Exception | None = None,
        crash_error: Exception | None = None,
    ):
        super().__init__(name=name)
        self.call_count = 0
        self._timeout_error = timeout_error or TimeoutError("tool timed out")
        self._crash_error = crash_error or ConnectionError("server crashed")

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        self.call_count += 1
        if self.call_count <= 2:
            raise self._timeout_error
        raise self._crash_error

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_timeout_then_crash_cascade():
    """Agent times out (calls 1-2) then crashes (call 3+) -> handled gracefully."""
    agent = ShiftingFailureAgent(name="cascade-agent")
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.RETRY,
        agent_name="cascade-agent",
        max_actions=5,
    )

    result = await orch.orchestrate(goal="test timeout then crash cascade")

    assert result is not None
    # System should handle the changing failure mode without crashing
    assert agent.call_count >= 1

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_graduated_escalation_depth_progression():
    """Agent always fails, thinking progresses: RETRY -> RETRY -> CONTEXT_REDUCE -> ESCALATE."""
    agent = StubAgent(
        name="escalation-agent",
        raise_on_execute=RuntimeError("persistent error"),
    )
    reg = make_registry(agent)

    tp = make_thinking(failure_action=FailureAction.RETRY, agent_name="escalation-agent")

    # Build side_effect list for graduated escalation
    retry_thought = OrchestrationThought(
        reasoning="Retry the operation",
        is_final=False,
        failure_action=FailureAction.RETRY,
        task=OrchestrationTask(
            agent_name="escalation-agent",
            description="retry task",
        ),
    )
    context_reduce_thought = OrchestrationThought(
        reasoning="Context too large, reducing",
        is_final=False,
        failure_action=FailureAction.CONTEXT_REDUCE,
        task=OrchestrationTask(
            agent_name="escalation-agent",
            description="retry with reduced context",
        ),
    )
    escalate_thought = OrchestrationThought(
        reasoning="All retries exhausted, escalating to user",
        is_final=True,
        failure_action=FailureAction.ESCALATE,
        escalation_question="Cannot complete task after multiple attempts",
        answer="Task failed after graduated escalation",
    )

    tp.failure_think = AsyncMock(
        side_effect=[retry_thought, retry_thought, context_reduce_thought, escalate_thought]
    )

    from core.autonomous.leash import LeashConfig
    from core.orchestrator.orchestrator import DryadeOrchestrator

    orch = DryadeOrchestrator(
        thinking_provider=tp,
        agent_registry=reg,
        leash=LeashConfig(max_actions=10),
    )

    result = await orch.orchestrate(goal="test graduated escalation")

    assert result is not None
    # Should eventually terminate (not loop forever)
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_multiple_agents_different_failures():
    """Two agents with different failure types -> system handles both."""
    timeout_agent = StubAgent(
        name="timeout-multi-agent",
        raise_on_execute=TimeoutError("tool timed out"),
    )
    auth_agent = StubAgent(
        name="auth-multi-agent",
        raise_on_execute=RuntimeError("HTTP 401 Unauthorized"),
    )

    reg = make_registry(timeout_agent, auth_agent)
    tp = make_thinking(failure_action=FailureAction.ESCALATE, agent_name="timeout-multi-agent")

    # First call dispatches to timeout_agent, second call dispatches to auth_agent
    call_count = 0
    dispatch_to_timeout = OrchestrationThought(
        reasoning="Try the timeout agent first",
        is_final=False,
        task=OrchestrationTask(
            agent_name="timeout-multi-agent",
            description="first attempt",
        ),
    )
    dispatch_to_auth = OrchestrationThought(
        reasoning="Try the auth agent",
        is_final=False,
        task=OrchestrationTask(
            agent_name="auth-multi-agent",
            description="second attempt",
        ),
    )
    # After both fail, escalate
    escalate = OrchestrationThought(
        reasoning="Both agents failed",
        is_final=True,
        failure_action=FailureAction.ESCALATE,
        escalation_question="Both agents failed with different errors",
        answer="Multiple agent failure cascade",
    )

    tp.orchestrate_think = AsyncMock(side_effect=[dispatch_to_timeout, dispatch_to_auth, escalate])
    tp.failure_think = AsyncMock(
        return_value=OrchestrationThought(
            reasoning="Failure encountered, trying next",
            is_final=False,
            failure_action=FailureAction.ESCALATE,
            escalation_question="Agent failed",
        )
    )

    from core.autonomous.leash import LeashConfig
    from core.orchestrator.orchestrator import DryadeOrchestrator

    orch = DryadeOrchestrator(
        thinking_provider=tp,
        agent_registry=reg,
        leash=LeashConfig(max_actions=10),
    )

    result = await orch.orchestrate(goal="test multiple agents different failures")

    assert result is not None
    # System handled different failure types from different agents

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_all_agents_fail_graceful_abort():
    """Three agents all with fatal errors -> eventually returns result, does NOT hang."""
    agents = [
        StubAgent(name=f"fatal-agent-{i}", raise_on_execute=RuntimeError("fatal error"))
        for i in range(3)
    ]
    orch = make_orchestrator(
        agents=agents,
        failure_action=FailureAction.ESCALATE,
        agent_name="fatal-agent-0",
        max_actions=5,
    )

    result = await orch.orchestrate(goal="test all agents fail abort")

    assert result is not None
    # Should return a failure/escalation result, not hang
    assert result.success is False or result.needs_escalation is True
