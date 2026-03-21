"""Chaos tests: context overflow injection scenarios.

Verifies the orchestrator handles oversized results, massive error
messages, and many observations without crashing.

Note: Chaos tests verify resilience (no crash, no hang), not specific
success/failure outcomes. The soft failure detector and other subsystems
may trigger escalation for anomalous data, which is correct behavior.
"""

import pytest

from core.orchestrator.models import FailureAction
from tests.chaos.conftest import StubAgent, make_orchestrator

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_context_overflow_large_result():
    """Agent returning a very large result (100K+ chars) does not crash the orchestrator."""
    large_result = "x" * 150_000  # 150KB result
    agent = StubAgent(
        name="verbose-agent",
        result=large_result,
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="verbose-agent",
    )

    result = await orch.orchestrate(goal="test context overflow with large result")

    # The system should not crash even with oversized context
    assert result is not None
    # Soft failure detector may trigger low_relevance -> escalation, which is fine.
    # Key assertion: no unhandled exception, no hang.

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_massive_error_message_handled_gracefully():
    """Agent raising a RuntimeError with 50K char message does not crash."""
    massive_msg = "E" * 50_000  # 50KB error message
    agent = StubAgent(
        name="error-flood-agent",
        raise_on_execute=RuntimeError(massive_msg),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="error-flood-agent",
    )

    result = await orch.orchestrate(goal="test massive error message")

    assert result is not None
    # Orchestrator should handle gracefully (escalate or error boundary)
    # The massive error message should be truncated or handled, not cause OOM
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_many_observations_dont_crash(monkeypatch):
    """Orchestrator handles many observations in succession without OOM or crash."""
    # Disable soft failure detection so the successful agent results are not
    # flagged as low-relevance (which would break the multi-step loop)
    monkeypatch.setenv("DRYADE_SOFT_FAILURE_DETECTION_ENABLED", "false")

    agent = StubAgent(
        name="chatty-agent",
        result="observation data " * 100,  # ~1.7KB per result
    )
    # Use a higher max_actions to accumulate many observations
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="chatty-agent",
        max_actions=20,
    )

    # Make orchestrate_think dispatch the task for multiple iterations
    # then finally return is_final=True
    call_count = 0
    original_think = orch.thinking.orchestrate_think

    async def multi_step_then_final(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 10:  # After 10 successful observations
            from core.orchestrator.models import OrchestrationThought

            return OrchestrationThought(
                reasoning="Enough observations collected, task complete",
                is_final=True,
                answer="Completed after many observations",
            )
        return await original_think(*args, **kwargs)

    from unittest.mock import AsyncMock

    orch.thinking.orchestrate_think = AsyncMock(side_effect=multi_step_then_final)

    result = await orch.orchestrate(goal="test many observations")

    assert result is not None
    # Should complete after accumulating 10+ observations without crash
    assert result.success is True
