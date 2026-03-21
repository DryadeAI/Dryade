"""LLM-as-judge output validation for tool/agent results.

Evaluates tool output quality across 4 dimensions (intent, grounding,
completeness, tool_appropriateness) using a secondary LLM call.
Returns a structured JudgeVerdict with per-dimension scores and
overall pass/fail.

This is a semantic quality check that complements the deterministic
heuristics in SoftFailureDetector (Phase 118.4).  Heuristics catch
structurally broken output (empty, truncated, looping); the judge
catches output that looks valid but is factually wrong, hallucinated,
or incomplete.

Plan: 118.6-01
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "JudgeDimension",
    "DimensionScore",
    "JudgeVerdict",
    "OutputJudge",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JudgeDimension Enum
# ---------------------------------------------------------------------------

class JudgeDimension(str, Enum):
    """Quality dimensions evaluated by the LLM judge."""

    INTENT = "intent"
    GROUNDING = "grounding"
    COMPLETENESS = "completeness"
    TOOL_APPROPRIATENESS = "tool_appropriateness"

# ---------------------------------------------------------------------------
# DimensionScore
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """Score for a single quality dimension.

    Attributes:
        dimension: Which quality dimension was scored.
        score: 0.0 to 1.0 rating.
        reasoning: LLM's explanation for the score.
    """

    dimension: JudgeDimension
    score: float
    reasoning: str

# ---------------------------------------------------------------------------
# JudgeVerdict
# ---------------------------------------------------------------------------

@dataclass
class JudgeVerdict:
    """Overall judge verdict with per-dimension scores.

    Attributes:
        passed: Whether the output met the score threshold.
        overall_score: Weighted average of dimension scores.
        scores: Per-dimension scoring results.
        reason: Human-readable summary of the verdict.
        dimensions_evaluated: Number of dimensions that were assessed.
    """

    passed: bool
    overall_score: float
    scores: list[DimensionScore]
    reason: str
    dimensions_evaluated: int

    def get_score(self, dim: JudgeDimension) -> float | None:
        """Return the score for a specific dimension, or None if not evaluated."""
        for ds in self.scores:
            if ds.dimension == dim:
                return ds.score
        return None

# ---------------------------------------------------------------------------
# OutputJudge
# ---------------------------------------------------------------------------

class OutputJudge:
    """Evaluates tool output quality using an LLM-as-judge pattern.

    Calls ThinkingProvider.judge_think() to get per-dimension scores,
    then assembles a JudgeVerdict.  Fails open (returns None) on any
    error -- the judge is an enhancement, not a gate.

    Args:
        thinking_provider: ThinkingProvider instance with judge_think().
        score_threshold: Minimum overall_score for passed=True (default 0.6).
    """

    def __init__(
        self,
        thinking_provider: Any,
        score_threshold: float = 0.6,
    ) -> None:
        self._thinking = thinking_provider
        self._threshold = score_threshold

    async def evaluate(
        self,
        tool_output: Any,
        task_description: str,
        tool_name: str | None = None,
        task_context: dict | None = None,
    ) -> JudgeVerdict | None:
        """Evaluate tool output quality via LLM judge.

        Returns None if:
          - tool_output is None or empty string (heuristics handle these)
          - LLM call fails (fail-open)
          - Response cannot be parsed

        Args:
            tool_output: The tool's result to evaluate.
            task_description: What the task was supposed to accomplish.
            tool_name: Name of the tool that produced the output.
            task_context: Additional context for grounding evaluation.

        Returns:
            JudgeVerdict or None.
        """
        # Skip empty outputs -- SoftFailureDetector already handles these
        if tool_output is None:
            return None
        if isinstance(tool_output, str) and not tool_output.strip():
            return None

        # Serialize context if it's a dict
        context_str = ""
        if task_context is not None:
            context_str = (
                json.dumps(task_context) if isinstance(task_context, dict) else str(task_context)
            )

        try:
            llm_response = await self._thinking.judge_think(
                tool_output=str(tool_output) if not isinstance(tool_output, str) else tool_output,
                task_description=task_description,
                tool_name=tool_name or "",
                task_context=context_str,
            )
            return self._parse_verdict(llm_response)
        except Exception as e:
            logger.warning("[OUTPUT_JUDGE] Judge evaluation failed (fail-open): %s", e)
            return None

    def _parse_verdict(self, data: dict) -> JudgeVerdict:
        """Parse LLM response dict into JudgeVerdict.

        Args:
            data: Dict with "scores" list and "overall_summary".

        Returns:
            JudgeVerdict with computed pass/fail.
        """
        raw_scores = data.get("scores", [])
        dimension_scores: list[DimensionScore] = []

        for entry in raw_scores:
            dim_str = entry.get("dimension", "")
            try:
                dim = JudgeDimension(dim_str)
            except ValueError:
                logger.warning("[OUTPUT_JUDGE] Unknown dimension '%s', skipping", dim_str)
                continue
            score = float(entry.get("score", 0.0))
            reasoning = entry.get("reasoning", "")
            dimension_scores.append(
                DimensionScore(
                    dimension=dim,
                    score=max(0.0, min(1.0, score)),  # Clamp to [0, 1]
                    reasoning=reasoning,
                )
            )

        # Compute overall score as simple average
        if dimension_scores:
            overall = sum(ds.score for ds in dimension_scores) / len(dimension_scores)
        else:
            overall = 0.0

        passed = overall >= self._threshold
        summary = data.get("overall_summary", "No summary provided")

        return JudgeVerdict(
            passed=passed,
            overall_score=round(overall, 4),
            scores=dimension_scores,
            reason=summary,
            dimensions_evaluated=len(dimension_scores),
        )
