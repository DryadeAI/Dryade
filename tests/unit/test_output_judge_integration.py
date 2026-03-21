"""Integration tests for LLM-as-judge wiring in orchestrator.

Verifies that OutputJudge is correctly wired into _execute_single
with proper feature gating (off by default), fail-open semantics,
and interaction with heuristic soft failure detection.

Plan: 118.6-02
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.config import get_orchestration_config
from core.orchestrator.models import OrchestrationTask
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.output_judge import DimensionScore, JudgeDimension, JudgeVerdict, OutputJudge

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator():
    """Minimal DryadeOrchestrator with mock defaults."""
    o = DryadeOrchestrator.__new__(DryadeOrchestrator)
    o.agents = {}
    o._soft_failure_detector = None
    o._output_judge = None
    o._circuit_breaker = None
    o._checkpoint_manager = None
    o._persistent_backend = None
    o.thinking = MagicMock()
    return o

@pytest.fixture
def mock_agent_ok():
    """Agent that returns a successful result with real content."""
    result = SimpleNamespace(
        result="Here are the search results for your query about Python web frameworks.",
        status="ok",
        error=None,
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    return agent

@pytest.fixture
def mock_agent_error():
    """Agent that returns a failure."""
    result = SimpleNamespace(
        result=None,
        status="error",
        error="Connection refused",
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    return agent

@pytest.fixture
def mock_agent_empty():
    """Agent that returns a successful status but None result."""
    result = SimpleNamespace(
        result=None,
        status="ok",
        error=None,
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    return agent

def _default_config(**overrides):
    """Create a default config with optional overrides."""
    cfg = get_orchestration_config()
    for k, v in overrides.items():
        object.__setattr__(cfg, k, v)
    return cfg

def _make_task(tool="search_web", args=None):
    """Create a simple OrchestrationTask."""
    return OrchestrationTask(
        agent_name="test_agent",
        description="Search for Python web frameworks and return a summary",
        tool=tool,
        arguments=args or {"query": "python web frameworks"},
    )

def _make_passing_verdict(score=0.85):
    """Create a passing JudgeVerdict."""
    dims = list(JudgeDimension)
    scores = [DimensionScore(dimension=d, score=score, reasoning="good") for d in dims]
    return JudgeVerdict(
        passed=True,
        overall_score=score,
        scores=scores,
        reason="Output looks good",
        dimensions_evaluated=4,
    )

def _make_failing_verdict(score=0.3):
    """Create a failing JudgeVerdict."""
    dims = list(JudgeDimension)
    scores = [DimensionScore(dimension=d, score=score, reasoning="bad") for d in dims]
    return JudgeVerdict(
        passed=False,
        overall_score=score,
        scores=scores,
        reason="Hallucinated entities",
        dimensions_evaluated=4,
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJudgeIntegration:
    """Integration tests for OutputJudge wiring in orchestrator."""

    @pytest.mark.asyncio
    async def test_judge_disabled_by_default(self, orchestrator, mock_agent_ok):
        """When judge_enabled=False (default), _execute_single does NOT call judge."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task()

        # Use default config -- judge_enabled=False
        cfg = _default_config()
        assert cfg.judge_enabled is False

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(return_value=_make_passing_verdict())
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-001",
                context={},
            )

        assert obs.success is True
        mock_judge.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_judge_enabled_calls_evaluate(self, orchestrator, mock_agent_ok):
        """When judge_enabled=True, judge.evaluate() is called with tool output and task description."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task()

        cfg = _default_config(judge_enabled=True)

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(return_value=_make_passing_verdict())
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-002",
                context={},
            )

        assert obs.success is True
        mock_judge.evaluate.assert_called_once()
        call_kwargs = mock_judge.evaluate.call_args
        assert (
            call_kwargs.kwargs["tool_output"]
            == "Here are the search results for your query about Python web frameworks."
        )
        assert call_kwargs.kwargs["task_description"] == task.description
        assert call_kwargs.kwargs["tool_name"] == "search_web"

    @pytest.mark.asyncio
    async def test_judge_verdict_fail_converts_to_soft_failure(self, orchestrator, mock_agent_ok):
        """When judge verdict fails (low score), result is converted to soft failure."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task()

        cfg = _default_config(judge_enabled=True)

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(return_value=_make_failing_verdict(score=0.3))
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-003",
                context={},
            )

        assert obs.success is False
        assert "Judge verdict failed" in (obs.error or "")
        assert "0.30" in (obs.error or "")
        assert "Hallucinated entities" in (obs.error or "")

    @pytest.mark.asyncio
    async def test_judge_verdict_pass_keeps_success(self, orchestrator, mock_agent_ok):
        """When judge verdict passes (high score), observation remains success=True."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task()

        cfg = _default_config(judge_enabled=True)

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(return_value=_make_passing_verdict(score=0.85))
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-004",
                context={},
            )

        assert obs.success is True
        assert obs.error is None

    @pytest.mark.asyncio
    async def test_judge_exception_is_fail_open(self, orchestrator, mock_agent_ok):
        """When judge.evaluate() raises RuntimeError, execution continues as success (fail-open)."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task()

        cfg = _default_config(judge_enabled=True)

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-005",
                context={},
            )

        assert obs.success is True
        assert obs.error is None

    @pytest.mark.asyncio
    async def test_judge_skipped_when_heuristic_fails(self, orchestrator, mock_agent_empty):
        """When heuristics already set is_success=False (empty result), judge is NOT called."""
        orchestrator.agents["test_agent"] = mock_agent_empty
        task = _make_task()

        # Enable both soft failure detection and judge
        cfg = _default_config(judge_enabled=True, soft_failure_detection_enabled=True)

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(return_value=_make_passing_verdict())
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-006",
                context={},
            )

        # Heuristic caught the empty result first
        assert obs.success is False
        assert "empty_result" in (obs.error or "")
        # Judge should NOT have been called because is_success was already False
        mock_judge.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_judge_not_called_on_tool_failure(self, orchestrator, mock_agent_error):
        """When agent execution returns error, judge is NOT called (is_success already False)."""
        orchestrator.agents["test_agent"] = mock_agent_error
        task = _make_task()

        cfg = _default_config(judge_enabled=True)

        mock_judge = MagicMock()
        mock_judge.evaluate = AsyncMock(return_value=_make_passing_verdict())
        orchestrator._output_judge = mock_judge

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-jdg-007",
                context={},
            )

        assert obs.success is False
        mock_judge.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_judge_score_threshold_from_config(self, monkeypatch):
        """DRYADE_JUDGE_SCORE_THRESHOLD=0.8 propagates to output_judge.score_threshold."""
        monkeypatch.setenv("DRYADE_JUDGE_SCORE_THRESHOLD", "0.8")

        o = DryadeOrchestrator.__new__(DryadeOrchestrator)
        o._output_judge = None
        o.thinking = MagicMock()

        judge = o.output_judge
        assert isinstance(judge, OutputJudge)
        assert judge._threshold == 0.8
