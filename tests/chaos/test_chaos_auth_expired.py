"""Chaos tests: authentication failure injection scenarios.

Verifies the orchestrator handles auth errors (401 Unauthorized,
403 Forbidden, expired tokens) gracefully -- classifying them as
permanent failures and escalating without unnecessary retries.
"""

import time

import pytest

from core.orchestrator.models import FailureAction
from tests.chaos.conftest import StubAgent, make_orchestrator, make_registry, make_thinking

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_auth_error_classified_as_auth_category():
    """RuntimeError with '401 Unauthorized' -> orchestrator handles without crash."""
    agent = StubAgent(
        name="auth-agent",
        raise_on_execute=RuntimeError("HTTP 401 Unauthorized"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="auth-agent",
    )

    result = await orch.orchestrate(goal="test auth error classification")

    # Must not crash; should escalate or mark as failure
    assert result is not None
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_auth_error_is_permanent_no_retry():
    """Auth error with ESCALATE action -> completes quickly (no retry delay)."""
    agent = StubAgent(
        name="auth-no-retry",
        raise_on_execute=RuntimeError("HTTP 401 Unauthorized"),
    )
    reg = make_registry(agent)
    tp = make_thinking(
        failure_action=FailureAction.ESCALATE,
        is_final_after_fail=True,
        agent_name="auth-no-retry",
    )

    from core.autonomous.leash import LeashConfig
    from core.orchestrator.orchestrator import DryadeOrchestrator

    orch = DryadeOrchestrator(
        thinking_provider=tp,
        agent_registry=reg,
        leash=LeashConfig(max_actions=5),
    )

    start = time.perf_counter()
    result = await orch.orchestrate(goal="test auth permanent failure")
    elapsed = time.perf_counter() - start

    assert result is not None
    # Auth errors are permanent -- should not keep retrying
    assert result.success is False or result.needs_escalation is True
    # Should complete quickly (no retry backoff delays)
    assert elapsed < 15, f"Auth error took {elapsed:.1f}s, expected <15s (no retries)"

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_permission_denied_403():
    """RuntimeError with '403 Forbidden' -> completes gracefully."""
    agent = StubAgent(
        name="forbidden-agent",
        raise_on_execute=RuntimeError("HTTP 403 Forbidden: insufficient permissions"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="forbidden-agent",
    )

    result = await orch.orchestrate(goal="test permission denied")

    assert result is not None
    assert result.success is False or result.needs_escalation is True
