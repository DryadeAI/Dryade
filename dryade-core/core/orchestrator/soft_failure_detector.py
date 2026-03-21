"""Heuristic soft failure detection for tool/agent results.

Soft failures are results that succeed at the transport layer but contain
useless, broken, looping, or irrelevant content.  The SoftFailureDetector
runs 5 deterministic checks (no LLM calls, no I/O) in priority order and
returns the first match.

Classes:
    SoftFailureResult  -- Dataclass describing the detected soft failure.
    ExecutionTracker   -- Rolling-window tracker for loop detection.
    SoftFailureDetector -- Stateless detector with 5 heuristic checks.

Plan: 118.4-01
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

__all__ = [
    "SoftFailureResult",
    "ExecutionTracker",
    "SoftFailureDetector",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Strings treated as semantically empty (case-insensitive)
_NULL_SENTINELS = frozenset({"null", "none", "undefined"})

# Valid short responses that should NOT trigger size anomaly
_VALID_SHORT_RESPONSES = frozenset({"ok", "true", "false", "yes", "no", "done", "0", "1"})

# Orchestrator truncation suffix pattern (intentional, not a soft failure)
_RE_ORCHESTRATOR_TRUNCATION = re.compile(r"\.\.\.\s*\[truncated from \d+ chars\]$")

# Explicit truncation markers (NOT the orchestrator's own)
_RE_EXPLICIT_TRUNCATION = re.compile(r"\.\.\.\s*\[truncated")

# Stopwords for keyword relevance scoring
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        "each",
        "every",
        "all",
        "any",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "about",
        "up",
        "down",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "i",
        "me",
        "my",
        "we",
        "us",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "they",
        "them",
        "their",
    }
)

# Regex for splitting text into words (non-alphanumeric separator)
_RE_WORD_SPLIT = re.compile(r"[^a-zA-Z0-9]+")

# Common ending words that legitimately appear at the end of a sentence
_COMMON_ENDING_WORDS = frozenset(
    {
        "ok",
        "yes",
        "no",
        "done",
        "true",
        "false",
        "null",
        "none",
        "success",
        "failed",
        "error",
        "complete",
        "finished",
        "available",
        "enabled",
        "disabled",
        "active",
        "inactive",
        "found",
        "created",
        "updated",
        "deleted",
        "removed",
    }
)

# ---------------------------------------------------------------------------
# SoftFailureResult
# ---------------------------------------------------------------------------

@dataclass
class SoftFailureResult:
    """Describes a detected soft failure.

    Attributes:
        is_soft_failure: Always True when returned from detect().
        reason: Human-readable description of what was detected.
        check_name: Which heuristic triggered (e.g. "empty_result").
        confidence: 0.0-1.0; deterministic checks use 1.0.
    """

    is_soft_failure: bool
    reason: str
    check_name: str
    confidence: float

# ---------------------------------------------------------------------------
# ExecutionTracker
# ---------------------------------------------------------------------------

class ExecutionTracker:
    """Rolling-window tracker for tool call loop detection.

    Maintains a deque of the last 20 (tool_name, args_hash) tuples.
    Used by SoftFailureDetector's loop check to detect repeated identical
    tool invocations.
    """

    _WINDOW_SIZE = 20

    def __init__(self) -> None:
        self._history: deque[tuple[str, str]] = deque(maxlen=self._WINDOW_SIZE)

    @staticmethod
    def _hash_args(arguments: dict) -> str:
        """Deterministic hash of tool arguments for deduplication."""
        raw = json.dumps(arguments, sort_keys=True, default=str).encode()
        return hashlib.md5(raw).hexdigest()[:16]  # noqa: S324

    def record(self, tool_name: str, arguments: dict) -> None:
        """Record a tool invocation in the rolling window."""
        self._history.append((tool_name, self._hash_args(arguments)))

    def is_looping(self, tool_name: str, arguments: dict, threshold: int = 3) -> bool:
        """Return True if (tool_name, args_hash) appears >= threshold times."""
        args_hash = self._hash_args(arguments)
        count = sum(1 for name, h in self._history if name == tool_name and h == args_hash)
        return count >= threshold

    def count(self, tool_name: str, arguments: dict) -> int:
        """Return the number of times (tool_name, args_hash) appears."""
        args_hash = self._hash_args(arguments)
        return sum(1 for name, h in self._history if name == tool_name and h == args_hash)

    def reset(self) -> None:
        """Clear all recorded entries."""
        self._history.clear()

# ---------------------------------------------------------------------------
# SoftFailureDetector
# ---------------------------------------------------------------------------

class SoftFailureDetector:
    """Stateless detector with 5 heuristic checks for soft failures.

    Checks run in order (first match wins):
      1. Empty/null result
      2. Loop detection (requires tracker)
      3. Truncation markers
      4. Size anomaly
      5. Keyword relevance

    All checks are deterministic and complete in under 1ms.
    """

    def detect(
        self,
        result_value: Any,
        task_description: str,
        tool_name: str | None = None,
        tracker: ExecutionTracker | None = None,
        arguments: dict | None = None,
    ) -> SoftFailureResult | None:
        """Run all 5 checks in order. Return first match or None."""
        return (
            self._check_empty_result(result_value)
            or self._check_loop(tool_name, arguments, tracker)
            or self._check_truncation(result_value)
            or self._check_size_anomaly(result_value)
            or self._check_relevance(result_value, task_description)
        )

    # -- Check 1: Empty/Null Result --

    @staticmethod
    def _check_empty_result(result_value: Any) -> SoftFailureResult | None:
        """Detect empty, null, or sentinel-string results."""
        if result_value is None:
            return SoftFailureResult(
                is_soft_failure=True,
                reason="Result is None",
                check_name="empty_result",
                confidence=1.0,
            )

        if isinstance(result_value, str):
            stripped = result_value.strip()
            if not stripped:
                return SoftFailureResult(
                    is_soft_failure=True,
                    reason="Result is empty or whitespace-only string",
                    check_name="empty_result",
                    confidence=1.0,
                )
            if stripped.lower() in _NULL_SENTINELS:
                return SoftFailureResult(
                    is_soft_failure=True,
                    reason=f"Result is sentinel value '{stripped}'",
                    check_name="empty_result",
                    confidence=1.0,
                )
            return None

        if isinstance(result_value, (list, dict)) and len(result_value) == 0:
            type_name = "list" if isinstance(result_value, list) else "dict"
            return SoftFailureResult(
                is_soft_failure=True,
                reason=f"Result is empty {type_name}",
                check_name="empty_result",
                confidence=1.0,
            )

        return None

    # -- Check 2: Loop Detection --

    @staticmethod
    def _check_loop(
        tool_name: str | None,
        arguments: dict | None,
        tracker: ExecutionTracker | None,
    ) -> SoftFailureResult | None:
        """Detect tool call loops via ExecutionTracker."""
        if tracker is None or tool_name is None:
            return None

        args = arguments or {}
        if tracker.is_looping(tool_name, args):
            count = tracker.count(tool_name, args)
            return SoftFailureResult(
                is_soft_failure=True,
                reason=(f"Tool '{tool_name}' called {count} times with identical arguments"),
                check_name="loop_detected",
                confidence=1.0,
            )
        return None

    # -- Check 3: Truncation Marker Detection --

    @staticmethod
    def _check_truncation(result_value: Any) -> SoftFailureResult | None:
        """Detect truncated results via bracket imbalance and markers."""
        if not isinstance(result_value, str) or len(result_value) <= 50:
            return None

        # Skip if this is the orchestrator's own intentional truncation
        if _RE_ORCHESTRATOR_TRUNCATION.search(result_value):
            return None

        # Check for explicit truncation markers (not orchestrator's format)
        if _RE_EXPLICIT_TRUNCATION.search(result_value):
            return SoftFailureResult(
                is_soft_failure=True,
                reason="Result contains explicit truncation marker",
                check_name="truncation",
                confidence=1.0,
            )

        # Check for unclosed JSON brackets
        if result_value.lstrip()[:1] in ("{", "["):
            open_braces = result_value.count("{") - result_value.count("}")
            open_brackets = result_value.count("[") - result_value.count("]")
            if open_braces > 0 or open_brackets > 0:
                return SoftFailureResult(
                    is_soft_failure=True,
                    reason="Result has unbalanced JSON brackets (likely truncated)",
                    check_name="truncation",
                    confidence=1.0,
                )

        # Check for cut-off mid-word: ends with a letter and last word
        # is not a common ending word
        stripped = result_value.rstrip()
        if stripped and stripped[-1].isalpha():
            # Extract last word
            words = stripped.split()
            if words:
                last_word = words[-1].lower().rstrip(".,;:!?\"')")
                if last_word not in _COMMON_ENDING_WORDS:
                    return SoftFailureResult(
                        is_soft_failure=True,
                        reason="Result appears cut off mid-word",
                        check_name="truncation",
                        confidence=0.8,
                    )

        return None

    # -- Check 4: Result Size Anomaly --

    @staticmethod
    def _check_size_anomaly(result_value: Any) -> SoftFailureResult | None:
        """Detect suspiciously small string results."""
        if not isinstance(result_value, str):
            return None

        stripped = result_value.strip().lower()
        if len(stripped) < 5 and stripped not in _VALID_SHORT_RESPONSES:
            return SoftFailureResult(
                is_soft_failure=True,
                reason=f"Result suspiciously small ({len(stripped)} chars)",
                check_name="size_anomaly",
                confidence=1.0,
            )
        return None

    # -- Check 5: Keyword Relevance Scoring --

    @staticmethod
    def _check_relevance(result_value: Any, task_description: str) -> SoftFailureResult | None:
        """Detect results with very low keyword overlap with task."""
        if not isinstance(result_value, str) or len(result_value) < 100:
            return None

        # Extract task keywords
        task_words = {
            w.lower()
            for w in _RE_WORD_SPLIT.split(task_description)
            if len(w) >= 3 and w.lower() not in _STOPWORDS
        }
        if len(task_words) < 2:
            return None

        # Extract result words
        result_words = {
            w.lower()
            for w in _RE_WORD_SPLIT.split(result_value)
            if len(w) >= 3 and w.lower() not in _STOPWORDS
        }

        # Compute overlap ratio
        overlap = len(task_words & result_words)
        ratio = overlap / len(task_words) if task_words else 1.0

        if ratio < 0.1:
            return SoftFailureResult(
                is_soft_failure=True,
                reason=(
                    f"Result has {ratio:.0%} keyword overlap with task "
                    f"({overlap}/{len(task_words)} keywords)"
                ),
                check_name="low_relevance",
                confidence=max(0.1, 1.0 - ratio),
            )
        return None
