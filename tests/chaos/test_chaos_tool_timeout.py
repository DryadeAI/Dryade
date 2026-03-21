"""Chaos tests: tool timeout injection scenarios.

Verifies the orchestrator handles asyncio.TimeoutError from agents
gracefully -- escalating, retrying, or aborting without hanging.
"""

import time

import pytest

from core.orchestrator.models import FailureAction
from tests.chaos.conftest import CountingAgent, StubAgent, make_orchestrator

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_timeout_triggers_escalation():
    """TimeoutError on agent -> orchestrator escalates (default failure_action=ESCALATE)."""
    agent = StubAgent(
        name="slow-agent",
        raise_on_execute=TimeoutError("tool timed out"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="slow-agent",
    )

    result = await orch.orchestrate(goal="test timeout escalation")

    # Orchestrator should return a result, not hang
    assert result is not None
    # The agent always fails, so the orchestrator either escalates or marks failure
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_timeout_retry_blocked_with_identical_params():
    """TimeoutError with RETRY -> orchestrator blocks retry (identical params) and escalates.

    BUG-006 fix: The orchestrator detects that retrying a timed-out call with
    identical parameters is futile and forces escalation instead.
    """
    agent = CountingAgent(
        name="flaky-timeout-agent",
        fail_until=2,
        raise_on_execute=TimeoutError("transient timeout"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.RETRY,
        agent_name="flaky-timeout-agent",
    )

    result = await orch.orchestrate(goal="retry after timeout")

    assert result is not None
    # Agent called once; retry blocked because params are identical
    assert agent.call_count >= 1
    # Result should indicate failure/escalation (retry was blocked)
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_timeout_does_not_hang_with_circuit_breaker(monkeypatch):
    """TimeoutError with circuit_breaker_enabled -- completes within 15s."""
    monkeypatch.setenv("DRYADE_CIRCUIT_BREAKER_ENABLED", "true")

    agent = StubAgent(
        name="hanging-agent",
        raise_on_execute=TimeoutError("total hang"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="hanging-agent",
    )

    start = time.perf_counter()
    result = await orch.orchestrate(goal="test circuit breaker timeout")
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 15, f"Orchestration took {elapsed:.1f}s, expected <15s"
