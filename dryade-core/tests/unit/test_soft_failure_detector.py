"""Tests for SoftFailureDetector - heuristic soft failure detection.

Covers all 5 deterministic heuristic checks:
  1. Empty/null result detection
  2. Loop detection (via ExecutionTracker)
  3. Truncation marker detection
  4. Result size anomaly detection
  5. Keyword relevance scoring

Plan: 118.4-01
"""

import pytest

from core.orchestrator.soft_failure_detector import (
    ExecutionTracker,
    SoftFailureDetector,
    SoftFailureResult,
)

@pytest.fixture
def detector():
    """Fresh SoftFailureDetector for each test."""
    return SoftFailureDetector()

@pytest.fixture
def tracker():
    """Fresh ExecutionTracker for each test."""
    return ExecutionTracker()

# ---- SoftFailureResult dataclass ----

class TestSoftFailureResult:
    """Verify SoftFailureResult fields."""

    def test_fields(self):
        r = SoftFailureResult(
            is_soft_failure=True,
            reason="test reason",
            check_name="empty_result",
            confidence=1.0,
        )
        assert r.is_soft_failure is True
        assert r.reason == "test reason"
        assert r.check_name == "empty_result"
        assert r.confidence == 1.0

# ---- Check 1: Empty/Null Result Detection ----

class TestEmptyResultDetection:
    """Empty, null, whitespace, and sentinel string results are soft failures."""

    def test_empty_result_none(self, detector):
        result = detector.detect(None, "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_empty_string(self, detector):
        result = detector.detect("", "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_whitespace(self, detector):
        result = detector.detect("   \n  ", "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_null_string(self, detector):
        result = detector.detect("null", "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_none_string(self, detector):
        result = detector.detect("None", "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_undefined_string(self, detector):
        """Case-insensitive 'undefined' is also empty."""
        result = detector.detect("UNDEFINED", "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_empty_list(self, detector):
        result = detector.detect([], "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_empty_result_empty_dict(self, detector):
        result = detector.detect({}, "any task")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "empty_result"

    def test_valid_short_ack(self, detector):
        """'ok' is a valid acknowledgment, not a failure."""
        result = detector.detect("ok", "do something")
        assert result is None

    def test_valid_result(self, detector):
        """Meaningful result content is not a failure."""
        result = detector.detect("File created at /tmp/test.txt", "create file")
        assert result is None

# ---- Check 2: Loop Detection ----

class TestLoopDetection:
    """Loop detection via ExecutionTracker."""

    def test_loop_detected(self, detector, tracker):
        """3 identical calls triggers loop detection."""
        for _ in range(3):
            tracker.record("read_file", {"path": "/tmp/foo.txt"})
        result = detector.detect(
            "some result",
            "read file",
            tool_name="read_file",
            tracker=tracker,
            arguments={"path": "/tmp/foo.txt"},
        )
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "loop_detected"
        assert "read_file" in result.reason

    def test_no_loop_different_args(self, detector, tracker):
        """Different args each time should not trigger loop."""
        for i in range(3):
            tracker.record("read_file", {"path": f"/tmp/foo_{i}.txt"})
        result = detector.detect(
            "some result",
            "read file",
            tool_name="read_file",
            tracker=tracker,
            arguments={"path": "/tmp/foo_0.txt"},
        )
        # Only 1 occurrence of this specific args hash, not 3
        assert result is None

    def test_no_loop_below_threshold(self, detector, tracker):
        """2 identical calls is below the default threshold of 3."""
        for _ in range(2):
            tracker.record("read_file", {"path": "/tmp/foo.txt"})
        result = detector.detect(
            "some result",
            "read file",
            tool_name="read_file",
            tracker=tracker,
            arguments={"path": "/tmp/foo.txt"},
        )
        assert result is None

    def test_loop_no_tracker(self, detector):
        """Without a tracker, loop check is skipped."""
        result = detector.detect(
            "some result",
            "read file",
            tool_name="read_file",
        )
        assert result is None

    def test_tracker_rolling_window(self, tracker):
        """Deque maxlen=20 evicts oldest entries."""
        for i in range(25):
            tracker.record("tool", {"i": i})
        # The first 5 entries should have been evicted
        # Only entries 5-24 remain (20 entries)
        assert not tracker.is_looping("tool", {"i": 0})

    def test_tracker_reset(self, tracker):
        """Reset clears all recorded entries."""
        for _ in range(5):
            tracker.record("tool", {"x": 1})
        tracker.reset()
        assert not tracker.is_looping("tool", {"x": 1})

# ---- Check 3: Truncation Marker Detection ----

class TestTruncationDetection:
    """Truncated results detected by bracket imbalance and cut-off markers."""

    def test_truncation_unclosed_json(self, detector):
        """Unclosed JSON object (more { than })."""
        # Must be > 50 chars to pass minimum length check
        unclosed = '{"key": "value", "nested": {"inner": "data", "extra": "pad"'
        assert len(unclosed) > 50
        result = detector.detect(unclosed, "get data")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "truncation"

    def test_truncation_unclosed_array(self, detector):
        """Unclosed JSON array (more [ than ])."""
        unclosed = "[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16"
        result = detector.detect(unclosed, "list items")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "truncation"

    def test_truncation_valid_json(self, detector):
        """Balanced JSON is not truncated."""
        valid = '{"key": "value", "nested": {"inner": "data"}}'
        result = detector.detect(valid, "get data")
        assert result is None

    def test_truncation_cutoff_word(self, detector):
        """Result cut off mid-word (ending with a letter, not punctuation)."""
        # Pad to > 50 chars to pass minimum length check
        cutoff = "The server returned a response that was partially incomplet"
        assert len(cutoff) > 50
        result = detector.detect(cutoff, "check server")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "truncation"

    def test_truncation_short_string_exempt(self, detector):
        """Short strings (< 50 chars) are exempt from truncation check.

        Use 'hello' (5 chars) which is >= 5 so it won't trigger size_anomaly
        but < 50 so truncation check is skipped.
        """
        result = detector.detect("hello", "greet")
        assert result is None

    def test_truncation_orchestrator_suffix_ignored(self, detector):
        """Orchestrator's own truncation suffix should NOT trigger this check."""
        data = "x" * 60 + "... [truncated from 5000 chars]"
        result = detector.detect(data, "get data")
        assert result is None

    def test_truncation_explicit_marker(self, detector):
        """Explicit ...[truncated marker (not the orchestrator's format)."""
        data = "x" * 60 + "...[truncated"
        result = detector.detect(data, "get data")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "truncation"

    def test_truncation_normal_ending(self, detector):
        """Result ending with punctuation is not truncated."""
        normal = "The server returned a response that was successful."
        assert len(normal) > 50
        result = detector.detect(normal, "check server")
        assert result is None

# ---- Check 4: Result Size Anomaly ----

class TestSizeAnomalyDetection:
    """Suspiciously small results flagged as anomalies."""

    def test_size_anomaly_single_char(self, detector):
        """Single character that isn't a known valid short response."""
        result = detector.detect("x", "read file contents")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "size_anomaly"

    def test_size_anomaly_valid_short_true(self, detector):
        """'true' is a known valid short response."""
        result = detector.detect("true", "check status")
        assert result is None

    def test_size_anomaly_ok(self, detector):
        """'ok' is a known valid short response."""
        result = detector.detect("ok", "confirm action")
        assert result is None

    def test_size_anomaly_number(self, detector):
        """'0' is a known valid short response."""
        result = detector.detect("0", "get count")
        assert result is None

    def test_size_anomaly_false(self, detector):
        """'false' is a known valid short response."""
        result = detector.detect("false", "check enabled")
        assert result is None

    def test_size_anomaly_yes(self, detector):
        """'yes' is a known valid short response."""
        result = detector.detect("yes", "confirm")
        assert result is None

    def test_size_anomaly_no(self, detector):
        """'no' is a known valid short response."""
        result = detector.detect("no", "deny")
        assert result is None

    def test_size_anomaly_done(self, detector):
        """'done' is a known valid short response."""
        result = detector.detect("done", "execute task")
        assert result is None

# ---- Check 5: Keyword Relevance Scoring ----

class TestRelevanceScoring:
    """Low keyword overlap between task and result flags irrelevant results."""

    def test_relevance_low_overlap(self, detector):
        """Result with 0% keyword overlap on a long result (>100 chars)."""
        result_value = (
            "The weather is sunny and warm today with clear skies "
            "forecast for the weekend and the temperature is rising steadily."
        )
        assert len(result_value) > 100
        result = detector.detect(result_value, "read database migration SQL schema")
        assert result is not None
        assert result.is_soft_failure is True
        assert result.check_name == "low_relevance"

    def test_relevance_good_overlap(self, detector):
        """Result with good keyword overlap is not flagged."""
        result = detector.detect(
            "Migration SQL applied to schema successfully",
            "apply database migration SQL schema",
        )
        assert result is None

    def test_relevance_short_exempt(self, detector):
        """Short results (< 100 chars) are exempt from relevance check."""
        result = detector.detect("done", "complex database operation")
        assert result is None

    def test_relevance_few_keywords(self, detector):
        """Fewer than 2 task keywords after filtering skips the check."""
        result = detector.detect("anything", "do it")
        assert result is None

# ---- Integration / ordering tests ----

class TestDetectOrdering:
    """Verify first-match-wins ordering and all-pass behavior."""

    def test_detect_returns_first_match(self, detector):
        """None result triggers empty_result check first (not later checks)."""
        result = detector.detect(None, "task")
        assert result is not None
        assert result.check_name == "empty_result"

    def test_detect_all_pass(self, detector):
        """Valid meaningful result passes all checks."""
        result = detector.detect("Valid meaningful result content here", "get content")
        assert result is None

    def test_detect_non_string_valid(self, detector):
        """Non-empty list/dict results pass all checks."""
        assert detector.detect([1, 2, 3], "list items") is None
        assert detector.detect({"key": "value"}, "get data") is None

    def test_detect_integer_result(self, detector):
        """Integer results should not crash and pass through."""
        assert detector.detect(42, "get count") is None
        assert detector.detect(0, "get count") is None
