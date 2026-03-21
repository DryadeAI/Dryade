"""Chaos tests: streaming interruption injection scenarios.

Verifies the orchestrator handles partial/truncated results,
connection resets during execution, and empty results without
crashing.
"""

import pytest

from core.orchestrator.models import FailureAction
from tests.chaos.conftest import StubAgent, make_orchestrator

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_partial_result_from_streaming():
    """Agent returns truncated JSON (incomplete brackets) -> does not crash."""
    truncated_json = '{"data": [1, 2, 3'  # Unclosed bracket
    agent = StubAgent(
        name="stream-agent",
        result=truncated_json,
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="stream-agent",
    )

    result = await orch.orchestrate(goal="test partial streaming result")

    # System should not crash; soft failure detector may catch truncation
    assert result is not None

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_connection_reset_during_execution():
    """ConnectionResetError -> classified and handled gracefully."""
    agent = StubAgent(
        name="reset-agent",
        raise_on_execute=ConnectionResetError("Connection reset by peer"),
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="reset-agent",
    )

    result = await orch.orchestrate(goal="test connection reset during streaming")

    assert result is not None
    assert result.success is False or result.needs_escalation is True

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_incomplete_result_with_soft_failure_detection(monkeypatch):
    """Empty string result with soft failure detection enabled -> completes."""
    monkeypatch.setenv("DRYADE_SOFT_FAILURE_DETECTION_ENABLED", "true")

    agent = StubAgent(
        name="empty-stream-agent",
        result="",  # Empty result -- soft failure detector catches this
    )
    orch = make_orchestrator(
        agents=[agent],
        failure_action=FailureAction.ESCALATE,
        agent_name="empty-stream-agent",
    )

    result = await orch.orchestrate(goal="test incomplete result with soft failure")

    # System should complete without crash
    assert result is not None
