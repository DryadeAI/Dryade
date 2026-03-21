"""Chaos tests: model unavailable / LLM endpoint down scenarios.

Verifies the orchestrator handles failures in the thinking provider
(orchestrate_think, failure_think) gracefully via the error boundary.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.models import FailureAction
from core.orchestrator.orchestrator import DryadeOrchestrator
from tests.chaos.conftest import StubAgent, make_orchestrator, make_registry, make_thinking

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_thinking_provider_error_handled():
    """orchestrate_think raises ConnectionError -> error boundary catches it."""
    agent = StubAgent(name="good-agent")
    reg = make_registry(agent)

    tp = make_thinking(agent_name="good-agent")
    # Override orchestrate_think to raise ConnectionError (LLM down)
    tp.orchestrate_think = AsyncMock(side_effect=ConnectionError("LLM endpoint unreachable"))

    from core.autonomous.leash import LeashConfig

    orch = DryadeOrchestrator(
        thinking_provider=tp,
        agent_registry=reg,
        leash=LeashConfig(max_actions=5),
    )

    result = await orch.orchestrate(goal="test thinking provider error")

    # Error boundary should catch the ConnectionError and return a fallback result
    assert result is not None
    assert result.success is False
    # Error boundary sets needs_escalation=True with a user-friendly message
    assert result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_failure_think_error_handled():
    """Agent fails, then failure_think raises ConnectionError -> does not crash."""
    agent = StubAgent(
        name="failing-agent",
        raise_on_execute=RuntimeError("tool error"),
    )
    reg = make_registry(agent)

    tp = make_thinking(agent_name="failing-agent")
    # failure_think raises ConnectionError (LLM down during failure handling)
    tp.failure_think = AsyncMock(side_effect=ConnectionError("LLM down during failure handling"))

    from core.autonomous.leash import LeashConfig

    orch = DryadeOrchestrator(
        thinking_provider=tp,
        agent_registry=reg,
        leash=LeashConfig(max_actions=5),
    )

    result = await orch.orchestrate(goal="test failure think error")

    # Should not crash -- either error boundary catches it or escalation happens
    assert result is not None
    assert result.success is False

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_model_unavailable_with_prevention_enabled(monkeypatch):
    """Prevention layer model reachability check fails -> orchestrator returns early."""
    monkeypatch.setenv("DRYADE_PREVENTION_ENABLED", "true")
    monkeypatch.setenv("DRYADE_MODEL_REACHABILITY_ENABLED", "true")

    agent = StubAgent(name="normal-agent")
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="normal-agent",
    )

    # Import the real PreventionVerdict so we can use it for comparison
    from core.orchestrator.prevention import PreventionVerdict

    # Mock the prevention pipeline at the source module (lazy import target)
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.verdict = PreventionVerdict.FAIL
    mock_result.reason = "Model endpoint unreachable (chaos test)"
    mock_pipeline.check_model_reachability = AsyncMock(return_value=mock_result)

    with patch("core.orchestrator.prevention.get_prevention_pipeline", return_value=mock_pipeline):
        result = await orch.orchestrate(goal="test model reachability check")

    assert result is not None
    # Prevention layer should catch unreachable model and return early
    assert result.success is False
    assert result.needs_escalation is True
    assert (
        "unreachable" in (result.reason or "").lower()
        or "unreachable" in (result.escalation_question or "").lower()
    )
