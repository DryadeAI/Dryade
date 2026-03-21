"""Tests for post-orchestration reflection engine (Phase 115.3).

Covers:
- ReflectionMode trigger logic (OFF, ON_FAILURE, ALWAYS)
- Failure detection from OrchestrationResult and OrchestrationObservation
- Recursion prevention via _in_reflection flag
- ReflectionResult metrics and quality assessment
- Memory update suggestions for failures
"""

import pytest

from core.orchestrator.models import OrchestrationObservation, OrchestrationResult
from core.orchestrator.reflection import (
    ReflectionEngine,
    ReflectionMode,
    ReflectionResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(success: bool = True, needs_escalation: bool = False) -> OrchestrationResult:
    """Create a minimal OrchestrationResult for testing."""
    return OrchestrationResult(
        success=success,
        needs_escalation=needs_escalation,
        output="test output" if success else None,
    )

def _make_obs(success: bool = True, error: str | None = None) -> OrchestrationObservation:
    """Create a minimal OrchestrationObservation for testing."""
    return OrchestrationObservation(
        agent_name="test-agent",
        task="test task",
        result="ok" if success else None,
        success=success,
        error=error,
    )

# ---------------------------------------------------------------------------
# should_reflect tests
# ---------------------------------------------------------------------------

def test_should_reflect_off_mode():
    """ReflectionMode.OFF always returns False."""
    engine = ReflectionEngine(ReflectionMode.OFF)
    result = _make_result(success=False)
    observations = [_make_obs(success=False, error="big failure")]
    assert engine.should_reflect(result, observations) is False

def test_should_reflect_always_mode():
    """ReflectionMode.ALWAYS returns True (unless _in_reflection)."""
    engine = ReflectionEngine(ReflectionMode.ALWAYS)
    result = _make_result(success=True)
    observations = [_make_obs(success=True)]
    assert engine.should_reflect(result, observations) is True

def test_should_reflect_on_failure_success():
    """Successful result with all-success observations -> False."""
    engine = ReflectionEngine(ReflectionMode.ON_FAILURE)
    result = _make_result(success=True)
    observations = [_make_obs(success=True), _make_obs(success=True)]
    assert engine.should_reflect(result, observations) is False

def test_should_reflect_on_failure_failed_result():
    """Failed result -> True."""
    engine = ReflectionEngine(ReflectionMode.ON_FAILURE)
    result = _make_result(success=False)
    observations = [_make_obs(success=True)]
    assert engine.should_reflect(result, observations) is True

def test_should_reflect_on_failure_failed_observation():
    """Success result but one failed observation -> True."""
    engine = ReflectionEngine(ReflectionMode.ON_FAILURE)
    result = _make_result(success=True)
    observations = [_make_obs(success=True), _make_obs(success=False, error="timeout")]
    assert engine.should_reflect(result, observations) is True

def test_should_reflect_on_failure_escalation():
    """Result with needs_escalation -> True."""
    engine = ReflectionEngine(ReflectionMode.ON_FAILURE)
    result = _make_result(success=True, needs_escalation=True)
    observations = [_make_obs(success=True)]
    assert engine.should_reflect(result, observations) is True

def test_reflect_no_recursion():
    """Set _in_reflection=True, verify should_reflect returns False."""
    engine = ReflectionEngine(ReflectionMode.ALWAYS)
    engine._in_reflection = True
    result = _make_result(success=False)
    observations = [_make_obs(success=False)]
    assert engine.should_reflect(result, observations) is False

# ---------------------------------------------------------------------------
# reflect() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reflect_returns_result():
    """Call reflect() with a failed result, verify ReflectionResult has expected fields."""
    engine = ReflectionEngine(ReflectionMode.ON_FAILURE)
    result = _make_result(success=False)
    observations = [
        _make_obs(success=True),
        _make_obs(success=False, error="Agent 'foo' not found"),
    ]

    reflection = await engine.reflect(
        result=result,
        observations=observations,
        goal="test goal",
        conversation_id="",  # No memory writes without conversation_id
    )

    assert isinstance(reflection, ReflectionResult)
    assert reflection.triggered is True
    assert reflection.trigger_reason == "orchestration_failed"
    assert "failed" in reflection.quality_assessment.lower()
    # Should have a memory update suggestion for the failed observation
    assert len(reflection.memory_updates) >= 1
    # Should suggest creating the missing agent
    assert any("not found" in s.lower() for s in reflection.capability_suggestions)

@pytest.mark.asyncio
async def test_reflect_metrics():
    """After reflect(), verify metrics dict contains expected keys."""
    engine = ReflectionEngine(ReflectionMode.ALWAYS)
    result = _make_result(success=True)
    observations = [
        _make_obs(success=True),
        _make_obs(success=True),
        _make_obs(success=False, error="timeout"),
    ]

    reflection = await engine.reflect(
        result=result,
        observations=observations,
        goal="test goal",
        conversation_id="",
    )

    assert "success_count" in reflection.metrics
    assert "failure_count" in reflection.metrics
    assert "total_observations" in reflection.metrics
    assert "success_rate" in reflection.metrics
    assert reflection.metrics["success_count"] == 2
    assert reflection.metrics["failure_count"] == 1
    assert reflection.metrics["total_observations"] == 3
    assert reflection.metrics["success_rate"] == pytest.approx(0.667, abs=0.01)
    assert reflection.metrics["result_success"] is True

@pytest.mark.asyncio
async def test_reflect_resets_in_reflection_flag():
    """Verify _in_reflection is reset to False after reflect() completes."""
    engine = ReflectionEngine(ReflectionMode.ALWAYS)
    result = _make_result(success=True)
    observations = [_make_obs(success=True)]

    assert engine._in_reflection is False
    await engine.reflect(result=result, observations=observations, goal="test", conversation_id="")
    assert engine._in_reflection is False
