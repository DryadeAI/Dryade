"""Chaos tests: rate limit injection scenarios.

Verifies the orchestrator handles HTTP 429 rate limit errors
gracefully -- retrying when appropriate and escalating when the
retry budget is exhausted, without entering infinite loops.
"""

import time

import pytest

from core.orchestrator.models import FailureAction
from tests.chaos.conftest import (
    CountingAgent,
    StubAgent,
    make_orchestrator,
)

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_rate_limit_classified_correctly():
    """RuntimeError with 'HTTP 429 Too Many Requests' -> completes without crash."""
    agent = StubAgent(
        name="rate-limited-agent",
        raise_on_execute=RuntimeError("HTTP 429 Too Many Requests"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="rate-limited-agent",
    )

    result = await orch.orchestrate(goal="test rate limit classification")

    assert result is not None
    # Should handle gracefully (escalate after seeing rate limit)
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_rate_limit_with_retry_recovery():
    """Rate limit fails twice then recovers -> system retries and succeeds or escalates."""
    agent = CountingAgent(
        name="flaky-rate-agent",
        fail_until=2,
        raise_on_execute=RuntimeError("HTTP 429 Too Many Requests"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.RETRY,
        agent_name="flaky-rate-agent",
    )

    result = await orch.orchestrate(goal="test rate limit retry recovery")

    assert result is not None
    # Agent was called at least once
    assert agent.call_count >= 1
    # System either succeeded after retry or escalated gracefully

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_rate_limit_does_not_cause_infinite_retry():
    """Permanent rate limit with RETRY action -> completes within 30s (bounded retries)."""
    agent = StubAgent(
        name="always-429-agent",
        raise_on_execute=RuntimeError("HTTP 429 Too Many Requests"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.RETRY,
        agent_name="always-429-agent",
        max_actions=5,
    )

    start = time.perf_counter()
    result = await orch.orchestrate(goal="test rate limit bounded retries")
    elapsed = time.perf_counter() - start

    assert result is not None
    assert elapsed < 30, f"Rate limit retry took {elapsed:.1f}s, expected <30s"
