"""Tests for OutputJudge - LLM-as-judge output validation.

Covers:
  - JudgeVerdict model (pass/fail, scoring, helpers)
  - JudgeDimension enum values
  - DimensionScore dataclass
  - OutputJudge evaluate() behavior (empty input, LLM call, fail-open)
  - JUDGE_SYSTEM_PROMPT placeholders
  - Config feature flag defaults

Plan: 118.6-01
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.output_judge import (
    DimensionScore,
    JudgeDimension,
    JudgeVerdict,
    OutputJudge,
)

# ---- JudgeDimension Enum ----

class TestJudgeDimension:
    """Verify all 4 JudgeDimension enum values exist."""

    def test_dimension_enum_values(self):
        assert JudgeDimension.INTENT == "intent"
        assert JudgeDimension.GROUNDING == "grounding"
        assert JudgeDimension.COMPLETENESS == "completeness"
        assert JudgeDimension.TOOL_APPROPRIATENESS == "tool_appropriateness"

    def test_dimension_enum_count(self):
        assert len(JudgeDimension) == 4

# ---- DimensionScore Dataclass ----

class TestDimensionScore:
    """Verify DimensionScore fields."""

    def test_fields(self):
        ds = DimensionScore(
            dimension=JudgeDimension.INTENT,
            score=0.9,
            reasoning="Good intent match",
        )
        assert ds.dimension == JudgeDimension.INTENT
        assert ds.score == 0.9
        assert ds.reasoning == "Good intent match"

# ---- JudgeVerdict Model ----

class TestJudgeVerdict:
    """Verify JudgeVerdict pass/fail logic and helpers."""

    def _make_scores(self, *values: float) -> list[DimensionScore]:
        """Helper to create dimension scores from float values."""
        dims = list(JudgeDimension)
        return [
            DimensionScore(dimension=dims[i], score=v, reasoning=f"score {v}")
            for i, v in enumerate(values)
        ]

    def test_judge_verdict_passed_when_above_threshold(self):
        scores = self._make_scores(0.8, 0.9, 0.7, 0.8)
        verdict = JudgeVerdict(
            passed=True,
            overall_score=0.8,
            scores=scores,
            reason="All good",
            dimensions_evaluated=4,
        )
        assert verdict.passed is True
        assert verdict.overall_score == 0.8

    def test_judge_verdict_failed_when_below_threshold(self):
        scores = self._make_scores(0.3, 0.4, 0.5, 0.4)
        verdict = JudgeVerdict(
            passed=False,
            overall_score=0.4,
            scores=scores,
            reason="Low scores",
            dimensions_evaluated=4,
        )
        assert verdict.passed is False
        assert verdict.overall_score == 0.4

    def test_judge_verdict_get_score(self):
        scores = self._make_scores(0.8, 0.9, 0.7, 0.6)
        verdict = JudgeVerdict(
            passed=True,
            overall_score=0.75,
            scores=scores,
            reason="ok",
            dimensions_evaluated=4,
        )
        assert verdict.get_score(JudgeDimension.INTENT) == 0.8
        assert verdict.get_score(JudgeDimension.GROUNDING) == 0.9
        assert verdict.get_score(JudgeDimension.COMPLETENESS) == 0.7
        assert verdict.get_score(JudgeDimension.TOOL_APPROPRIATENESS) == 0.6

    def test_judge_verdict_get_score_missing_dimension(self):
        # Only 2 dimensions scored
        scores = [
            DimensionScore(dimension=JudgeDimension.INTENT, score=0.8, reasoning="ok"),
            DimensionScore(dimension=JudgeDimension.GROUNDING, score=0.9, reasoning="ok"),
        ]
        verdict = JudgeVerdict(
            passed=True,
            overall_score=0.85,
            scores=scores,
            reason="partial",
            dimensions_evaluated=2,
        )
        assert verdict.get_score(JudgeDimension.COMPLETENESS) is None
        assert verdict.get_score(JudgeDimension.TOOL_APPROPRIATENESS) is None

# ---- OutputJudge evaluate() ----

class TestOutputJudgeEvaluate:
    """Verify OutputJudge.evaluate() behavior."""

    def _make_mock_provider(self, llm_response: dict | None = None, raise_error: bool = False):
        """Create a mock ThinkingProvider with judge_think."""
        provider = MagicMock()
        if raise_error:
            provider.judge_think = AsyncMock(side_effect=Exception("LLM failed"))
        elif llm_response is not None:
            provider.judge_think = AsyncMock(return_value=llm_response)
        else:
            provider.judge_think = AsyncMock(
                return_value={
                    "scores": [
                        {"dimension": "intent", "score": 0.9, "reasoning": "ok"},
                        {"dimension": "grounding", "score": 0.8, "reasoning": "ok"},
                        {"dimension": "completeness", "score": 0.7, "reasoning": "ok"},
                        {"dimension": "tool_appropriateness", "score": 0.8, "reasoning": "ok"},
                    ],
                    "overall_summary": "Good output",
                }
            )
        return provider

    @pytest.mark.asyncio
    async def test_output_judge_returns_none_for_empty_output(self):
        provider = self._make_mock_provider()
        judge = OutputJudge(provider)
        result = await judge.evaluate(None, "some task")
        assert result is None

    @pytest.mark.asyncio
    async def test_output_judge_returns_none_for_empty_string(self):
        provider = self._make_mock_provider()
        judge = OutputJudge(provider)
        result = await judge.evaluate("", "some task")
        assert result is None

    @pytest.mark.asyncio
    async def test_output_judge_evaluate_calls_judge_think(self):
        provider = self._make_mock_provider()
        judge = OutputJudge(provider)
        await judge.evaluate("some output", "search for files", tool_name="search_files")
        provider.judge_think.assert_called_once_with(
            tool_output="some output",
            task_description="search for files",
            tool_name="search_files",
            task_context="",
        )

    @pytest.mark.asyncio
    async def test_output_judge_evaluate_passes_on_high_scores(self):
        llm_response = {
            "scores": [
                {"dimension": "intent", "score": 0.9, "reasoning": "great"},
                {"dimension": "grounding", "score": 0.9, "reasoning": "great"},
                {"dimension": "completeness", "score": 0.9, "reasoning": "great"},
                {"dimension": "tool_appropriateness", "score": 0.9, "reasoning": "great"},
            ],
            "overall_summary": "Excellent output",
        }
        provider = self._make_mock_provider(llm_response)
        judge = OutputJudge(provider, score_threshold=0.6)
        verdict = await judge.evaluate("good output", "do a thing")
        assert verdict is not None
        assert verdict.passed is True
        assert verdict.overall_score == 0.9

    @pytest.mark.asyncio
    async def test_output_judge_evaluate_fails_on_low_scores(self):
        llm_response = {
            "scores": [
                {"dimension": "intent", "score": 0.3, "reasoning": "bad"},
                {"dimension": "grounding", "score": 0.3, "reasoning": "bad"},
                {"dimension": "completeness", "score": 0.3, "reasoning": "bad"},
                {"dimension": "tool_appropriateness", "score": 0.3, "reasoning": "bad"},
            ],
            "overall_summary": "Poor output",
        }
        provider = self._make_mock_provider(llm_response)
        judge = OutputJudge(provider, score_threshold=0.6)
        verdict = await judge.evaluate("bad output", "do a thing")
        assert verdict is not None
        assert verdict.passed is False
        assert verdict.overall_score == pytest.approx(0.3, abs=0.01)

    @pytest.mark.asyncio
    async def test_output_judge_graceful_on_llm_failure(self):
        provider = self._make_mock_provider(raise_error=True)
        judge = OutputJudge(provider)
        result = await judge.evaluate("some output", "some task")
        assert result is None

    @pytest.mark.asyncio
    async def test_output_judge_passes_context(self):
        provider = self._make_mock_provider()
        judge = OutputJudge(provider)
        await judge.evaluate(
            "output",
            "task",
            tool_name="my_tool",
            task_context={"key": "value"},
        )
        provider.judge_think.assert_called_once_with(
            tool_output="output",
            task_description="task",
            tool_name="my_tool",
            task_context='{"key": "value"}',
        )

# ---- JUDGE_SYSTEM_PROMPT ----

class TestJudgePrompt:
    """Verify JUDGE_SYSTEM_PROMPT has all required placeholders."""

    def test_judge_prompt_has_all_placeholders(self):
        from core.orchestrator.thinking.prompts import JUDGE_SYSTEM_PROMPT

        assert "{task_description}" in JUDGE_SYSTEM_PROMPT
        assert "{tool_name}" in JUDGE_SYSTEM_PROMPT
        assert "{task_context}" in JUDGE_SYSTEM_PROMPT
        assert "{tool_output}" in JUDGE_SYSTEM_PROMPT

# ---- Config Feature Flag Defaults ----

class TestConfigJudgeDefaults:
    """Verify judge feature flag defaults in OrchestrationConfig."""

    def test_config_judge_defaults(self):
        from core.orchestrator.config import OrchestrationConfig

        config = OrchestrationConfig()
        assert config.judge_enabled is False
        assert config.judge_score_threshold == 0.6
        assert config.judge_model is None
