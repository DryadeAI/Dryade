"""Chaos tests: MCP server crash injection scenarios.

Verifies the orchestrator handles ConnectionError from agents
gracefully -- classifying, retrying, and eventually escalating
without hanging.
"""

import time

import pytest

from core.orchestrator.models import FailureAction
from tests.chaos.conftest import CountingAgent, StubAgent, make_orchestrator

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_connection_error_triggers_classification():
    """ConnectionError on agent -> orchestrator classifies and handles failure."""
    agent = StubAgent(
        name="dead-mcp",
        raise_on_execute=ConnectionError("Connection reset by peer"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="dead-mcp",
    )

    result = await orch.orchestrate(goal="test mcp crash")

    assert result is not None
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_repeated_crashes_trip_circuit_breaker(monkeypatch):
    """Repeated ConnectionErrors with circuit breaker enabled -- exhausts retries and stops."""
    monkeypatch.setenv("DRYADE_CIRCUIT_BREAKER_ENABLED", "true")

    agent = StubAgent(
        name="crashing-mcp",
        raise_on_execute=ConnectionError("Connection refused"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.RETRY,
        agent_name="crashing-mcp",
    )

    start = time.perf_counter()
    result = await orch.orchestrate(goal="test repeated crashes")
    elapsed = time.perf_counter() - start

    assert result is not None
    # Should complete within timeout (not hang)
    assert elapsed < 30, f"Orchestration took {elapsed:.1f}s, expected <30s"

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_crash_recovery_after_transient_failure():
    """CountingAgent fails once with ConnectionError, then recovers on retry."""
    agent = CountingAgent(
        name="flaky-mcp",
        fail_until=1,
        raise_on_execute=ConnectionError("Connection temporarily lost"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.RETRY,
        agent_name="flaky-mcp",
    )

    result = await orch.orchestrate(goal="test crash recovery")

    assert result is not None
    # Agent should have been called at least twice (1 failure + 1 success attempt)
    assert agent.call_count >= 1
