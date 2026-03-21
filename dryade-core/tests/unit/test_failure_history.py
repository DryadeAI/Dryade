"""TDD test suite for failure history module.

Tests FailureHistoryStore, PatternDetector, and AdaptiveRetryStrategy.
All tests use a mocked in-memory database for isolation.

Plan: 118.7-01
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base
from core.orchestrator.failure_history import (
    AdaptiveRetryStrategy,
    FailureHistoryStore,
    PatternDetector,
)
from core.orchestrator.models import ErrorCategory, FailureAction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """Mock get_session to use an in-memory SQLAlchemy database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @contextmanager
    def mock_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("core.database.session.get_session", mock_get_session)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store() -> FailureHistoryStore:
    """Create a store for test isolation (uses mocked get_session)."""
    return FailureHistoryStore()

def _seed_failures(
    store: FailureHistoryStore,
    tool_name: str = "read_file",
    server_name: str = "filesystem",
    error_category: ErrorCategory = ErrorCategory.TRANSIENT,
    action_taken: FailureAction = FailureAction.RETRY,
    count: int = 1,
    recovery_success: bool = False,
    duration_ms: int = 100,
    retry_count: int = 1,
    model_used: str = "test-model",
    timestamp_offset_hours: float = 0.0,
) -> None:
    """Insert multiple failure records with consistent defaults."""
    for _ in range(count):
        store.record_failure(
            tool_name=tool_name,
            server_name=server_name,
            error_category=error_category,
            error_message=f"Test error for {tool_name}",
            action_taken=action_taken,
            recovery_success=recovery_success,
            duration_ms=duration_ms,
            retry_count=retry_count,
            model_used=model_used,
            timestamp_offset_hours=timestamp_offset_hours,
        )

# ---------------------------------------------------------------------------
# Task 1: FailureHistoryStore tests
# ---------------------------------------------------------------------------

class TestFailureHistoryStore:
    """Tests for FailureHistoryStore CRUD and query operations."""

    def test_uses_in_memory_db(self) -> None:
        """Store can be created for test isolation."""
        store = _make_store()
        assert store.count_records() == 0

    def test_record_and_count(self) -> None:
        """Record 3 failures, count_records returns 3."""
        store = _make_store()
        for i in range(3):
            store.record_failure(
                tool_name=f"tool_{i}",
                server_name="server",
                error_category=ErrorCategory.TRANSIENT,
                error_message="boom",
                action_taken=FailureAction.RETRY,
                recovery_success=False,
            )
        assert store.count_records() == 3

    def test_failure_rate_calculation(self) -> None:
        """Mix of success/failure gives correct rate."""
        store = _make_store()
        # 3 failures
        _seed_failures(store, count=3, recovery_success=False)
        # 2 successes
        _seed_failures(store, count=2, recovery_success=True)

        total_failures, total_successes, rate = store.get_failure_rate("read_file")
        assert total_failures == 3
        assert total_successes == 2
        assert abs(rate - 0.6) < 0.01  # 3 / (3+2) = 0.6

    def test_failure_rate_empty(self) -> None:
        """No data returns (0, 0, 0.0)."""
        store = _make_store()
        total_failures, total_successes, rate = store.get_failure_rate("nonexistent")
        assert total_failures == 0
        assert total_successes == 0
        assert rate == 0.0

    def test_tool_error_stats(self) -> None:
        """Specific tool+error combo stats are correct."""
        store = _make_store()
        # 4 transient failures: 3 recovered, 1 not
        _seed_failures(
            store,
            count=3,
            recovery_success=True,
            duration_ms=200,
            retry_count=2,
        )
        _seed_failures(
            store,
            count=1,
            recovery_success=False,
            duration_ms=400,
            retry_count=3,
        )

        stats = store.get_tool_error_stats("read_file", "transient")
        assert stats["total"] == 4
        assert stats["recovered"] == 3
        assert abs(stats["recovery_rate"] - 0.75) < 0.01
        # avg retries: (2+2+2+3)/4 = 2.25
        assert abs(stats["avg_retries"] - 2.25) < 0.01
        # avg duration: (200+200+200+400)/4 = 250
        assert abs(stats["avg_duration_ms"] - 250.0) < 0.01

    def test_top_failing_tools(self) -> None:
        """Sorting by rate, minimum 3 records filter."""
        store = _make_store()
        # tool_a: 4 failures out of 5 (rate=0.8) -> above minimum
        _seed_failures(store, tool_name="tool_a", count=4, recovery_success=False)
        _seed_failures(store, tool_name="tool_a", count=1, recovery_success=True)
        # tool_b: 1 failure out of 3 (rate=0.333) -> above minimum
        _seed_failures(store, tool_name="tool_b", count=1, recovery_success=False)
        _seed_failures(store, tool_name="tool_b", count=2, recovery_success=True)
        # tool_c: 2 records only -> below minimum (filtered out)
        _seed_failures(store, tool_name="tool_c", count=2, recovery_success=False)

        top = store.get_top_failing_tools()
        # tool_c should be filtered (only 2 records < 3 minimum)
        tool_names = [t["tool_name"] for t in top]
        assert "tool_c" not in tool_names
        # tool_a should be first (highest failure rate)
        assert top[0]["tool_name"] == "tool_a"
        assert abs(top[0]["failure_rate"] - 0.8) < 0.01
        # tool_b should be second
        assert top[1]["tool_name"] == "tool_b"

    def test_server_failure_rate(self) -> None:
        """Server-level aggregation works."""
        store = _make_store()
        _seed_failures(store, server_name="mcp_server_1", count=3, recovery_success=False)
        _seed_failures(store, server_name="mcp_server_1", count=7, recovery_success=True)

        rate = store.get_server_failure_rate("mcp_server_1")
        assert abs(rate - 0.3) < 0.01  # 3 / (3+7) = 0.3

    def test_server_failure_rate_empty(self) -> None:
        """Empty server returns 0.0."""
        store = _make_store()
        assert store.get_server_failure_rate("nonexistent") == 0.0

    def test_purge_old_records(self) -> None:
        """Purge removes old records, keeps recent."""
        store = _make_store()
        # Insert 3 "old" records (35 days ago)
        _seed_failures(
            store,
            count=3,
            timestamp_offset_hours=-35 * 24,
        )
        # Insert 2 "recent" records (now)
        _seed_failures(store, count=2)

        assert store.count_records() == 5
        deleted = store.purge_old_records(retention_days=30)
        assert deleted == 3
        assert store.count_records() == 2

    def test_error_message_truncation(self) -> None:
        """Messages > 500 chars are truncated."""
        store = _make_store()
        long_msg = "x" * 1000
        store.record_failure(
            tool_name="test_tool",
            server_name="server",
            error_category=ErrorCategory.TRANSIENT,
            error_message=long_msg,
            action_taken=FailureAction.RETRY,
            recovery_success=False,
        )
        # Retrieve via ORM session to check stored message length
        from core.database.models import FailureHistoryRecord

        with store._get_session() as session:
            record = session.query(FailureHistoryRecord).first()
            assert record is not None
            assert len(record.error_message) == 500

    def test_failure_rate_respects_window(self) -> None:
        """Records outside the window are excluded."""
        store = _make_store()
        # 2 old failures (48 hours ago)
        _seed_failures(store, count=2, timestamp_offset_hours=-48)
        # 1 recent failure (now)
        _seed_failures(store, count=1, recovery_success=False)

        # 24h window should only see the 1 recent record
        total_failures, total_successes, rate = store.get_failure_rate("read_file", window_hours=24)
        assert total_failures == 1
        assert total_successes == 0
        assert rate == 1.0

# ---------------------------------------------------------------------------
# Task 2: PatternDetector tests
# ---------------------------------------------------------------------------

class TestPatternDetector:
    """Tests for PatternDetector pattern detection logic."""

    def test_detect_high_failure_tools(self) -> None:
        """Threshold filtering returns only high-failure tools."""
        store = _make_store()
        # tool_a: 4/5 fail (rate=0.8) -> above 0.5 threshold
        _seed_failures(store, tool_name="tool_a", count=4, recovery_success=False)
        _seed_failures(store, tool_name="tool_a", count=1, recovery_success=True)
        # tool_b: 1/4 fail (rate=0.25) -> below 0.5 threshold
        _seed_failures(store, tool_name="tool_b", count=1, recovery_success=False)
        _seed_failures(store, tool_name="tool_b", count=3, recovery_success=True)

        detector = PatternDetector(store)
        high = detector.detect_high_failure_tools(threshold=0.5)
        tool_names = [t["tool_name"] for t in high]
        assert "tool_a" in tool_names
        assert "tool_b" not in tool_names

    def test_detect_recurring_errors(self) -> None:
        """Multiple error categories grouped and sorted by count."""
        store = _make_store()
        # 5 transient errors
        _seed_failures(
            store,
            tool_name="flaky_tool",
            error_category=ErrorCategory.TRANSIENT,
            count=5,
        )
        # 3 connection errors
        _seed_failures(
            store,
            tool_name="flaky_tool",
            error_category=ErrorCategory.CONNECTION,
            count=3,
        )
        # 1 auth error (below minimum of 2, should be filtered)
        _seed_failures(
            store,
            tool_name="flaky_tool",
            error_category=ErrorCategory.AUTH,
            count=1,
        )

        detector = PatternDetector(store)
        recurring = detector.detect_recurring_errors("flaky_tool")
        categories = [r["error_category"] for r in recurring]
        assert categories[0] == "transient"  # highest count
        assert categories[1] == "connection"
        assert "auth" not in categories  # only 1 occurrence, below threshold

    def test_preempt_circuit_break_true(self) -> None:
        """High failure rate server triggers circuit break."""
        store = _make_store()
        _seed_failures(store, server_name="bad_server", count=8, recovery_success=False)
        _seed_failures(store, server_name="bad_server", count=2, recovery_success=True)

        detector = PatternDetector(store)
        # 80% failure rate > 70% threshold
        assert detector.should_preempt_circuit_break("bad_server", threshold=0.7) is True

    def test_preempt_circuit_break_false(self) -> None:
        """Low failure rate server does not trigger circuit break."""
        store = _make_store()
        _seed_failures(store, server_name="ok_server", count=1, recovery_success=False)
        _seed_failures(store, server_name="ok_server", count=9, recovery_success=True)

        detector = PatternDetector(store)
        # 10% failure rate < 70% threshold
        assert detector.should_preempt_circuit_break("ok_server", threshold=0.7) is False

    def test_failure_trend_improving(self) -> None:
        """More failures in first half = improving trend.

        Window is [now-24h, now], midpoint at now-12h.
        First half data at -18h (falls in [now-24h, now-12h]).
        Second half data at -6h (falls in [now-12h, now]).
        """
        store = _make_store()
        # First half: 18 hours ago -- mostly failures (80%)
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=8,
            recovery_success=False,
            timestamp_offset_hours=-18,
        )
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=2,
            recovery_success=True,
            timestamp_offset_hours=-18,
        )
        # Second half: 6 hours ago -- mostly successes (20% failure)
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=2,
            recovery_success=False,
            timestamp_offset_hours=-6,
        )
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=8,
            recovery_success=True,
            timestamp_offset_hours=-6,
        )

        detector = PatternDetector(store)
        trend = detector.get_failure_trend("trend_tool", window_hours=24)
        assert trend == "improving"

    def test_failure_trend_degrading(self) -> None:
        """More failures in second half = degrading trend.

        First half data at -18h, second half data at -6h.
        """
        store = _make_store()
        # First half: 18 hours ago -- mostly successes (20% failure)
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=2,
            recovery_success=False,
            timestamp_offset_hours=-18,
        )
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=8,
            recovery_success=True,
            timestamp_offset_hours=-18,
        )
        # Second half: 6 hours ago -- mostly failures (80%)
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=8,
            recovery_success=False,
            timestamp_offset_hours=-6,
        )
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=2,
            recovery_success=True,
            timestamp_offset_hours=-6,
        )

        detector = PatternDetector(store)
        trend = detector.get_failure_trend("trend_tool", window_hours=24)
        assert trend == "degrading"

    def test_failure_trend_stable(self) -> None:
        """Similar rates in both halves = stable trend.

        First half data at -18h, second half data at -6h. Both 50% failure.
        """
        store = _make_store()
        # First half: 18 hours ago -- 50% failure
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=5,
            recovery_success=False,
            timestamp_offset_hours=-18,
        )
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=5,
            recovery_success=True,
            timestamp_offset_hours=-18,
        )
        # Second half: 6 hours ago -- 50% failure
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=5,
            recovery_success=False,
            timestamp_offset_hours=-6,
        )
        _seed_failures(
            store,
            tool_name="trend_tool",
            count=5,
            recovery_success=True,
            timestamp_offset_hours=-6,
        )

        detector = PatternDetector(store)
        trend = detector.get_failure_trend("trend_tool", window_hours=24)
        assert trend == "stable"

# ---------------------------------------------------------------------------
# Task 2: AdaptiveRetryStrategy tests
# ---------------------------------------------------------------------------

class TestAdaptiveRetryStrategy:
    """Tests for AdaptiveRetryStrategy adaptive computation."""

    def test_no_history(self) -> None:
        """No history returns default values."""
        store = _make_store()
        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("unknown_tool", "transient")
        assert params["max_retries"] == 3
        assert params["backoff_base"] == 2.0
        assert params["reason"] == "no history"

    def test_high_recovery(self) -> None:
        """recovery_rate >= 0.8 gives more retries and lower backoff."""
        store = _make_store()
        # 9 successes, 1 failure -> 90% recovery rate
        _seed_failures(
            store,
            tool_name="good_tool",
            error_category=ErrorCategory.TRANSIENT,
            count=9,
            recovery_success=True,
        )
        _seed_failures(
            store,
            tool_name="good_tool",
            error_category=ErrorCategory.TRANSIENT,
            count=1,
            recovery_success=False,
        )

        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("good_tool", "transient")
        assert params["max_retries"] == 5  # default(3) + 2
        assert params["backoff_base"] == 1.5
        assert "high recovery rate" in params["reason"]

    def test_low_recovery(self) -> None:
        """recovery_rate < 0.2 gives fewer retries and higher backoff."""
        store = _make_store()
        # 1 success, 9 failures -> 10% recovery rate
        _seed_failures(
            store,
            tool_name="bad_tool",
            error_category=ErrorCategory.PERMANENT,
            count=9,
            recovery_success=False,
        )
        _seed_failures(
            store,
            tool_name="bad_tool",
            error_category=ErrorCategory.PERMANENT,
            count=1,
            recovery_success=True,
        )

        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("bad_tool", "permanent")
        assert params["max_retries"] == 1
        assert params["backoff_base"] == 5.0
        assert "very low recovery rate" in params["reason"]

    def test_moderate_recovery(self) -> None:
        """recovery_rate between 0.5 and 0.8 returns defaults."""
        store = _make_store()
        # 6 successes, 4 failures -> 60% recovery rate
        _seed_failures(
            store,
            tool_name="ok_tool",
            error_category=ErrorCategory.TRANSIENT,
            count=6,
            recovery_success=True,
        )
        _seed_failures(
            store,
            tool_name="ok_tool",
            error_category=ErrorCategory.TRANSIENT,
            count=4,
            recovery_success=False,
        )

        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("ok_tool", "transient")
        assert params["max_retries"] == 3  # default
        assert params["backoff_base"] == 2.0  # default
        assert "moderate recovery rate" in params["reason"]

    def test_low_but_not_very_low_recovery(self) -> None:
        """recovery_rate between 0.2 and 0.5 gives reduced retries."""
        store = _make_store()
        # 3 successes, 7 failures -> 30% recovery rate
        _seed_failures(
            store,
            tool_name="meh_tool",
            error_category=ErrorCategory.CONNECTION,
            count=3,
            recovery_success=True,
        )
        _seed_failures(
            store,
            tool_name="meh_tool",
            error_category=ErrorCategory.CONNECTION,
            count=7,
            recovery_success=False,
        )

        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("meh_tool", "connection")
        assert params["max_retries"] == 2  # default(3) - 1
        assert params["backoff_base"] == 3.0
        assert "low recovery rate" in params["reason"]

    def test_clamp_bounds(self) -> None:
        """max_retries stays within [1, 10] even with extreme defaults."""
        store = _make_store()
        # High recovery with large default -> should clamp to 10
        _seed_failures(
            store,
            tool_name="tool",
            error_category=ErrorCategory.TRANSIENT,
            count=10,
            recovery_success=True,
        )
        strategy_high = AdaptiveRetryStrategy(store, default_max_retries=9)
        params = strategy_high.get_retry_params("tool", "transient")
        assert params["max_retries"] <= 10
        assert params["max_retries"] >= 1

        # Very low recovery with default of 1 -> should clamp to 1
        store2 = _make_store()
        _seed_failures(
            store2,
            tool_name="tool2",
            error_category=ErrorCategory.PERMANENT,
            count=10,
            recovery_success=False,
        )
        strategy_low = AdaptiveRetryStrategy(store2, default_max_retries=1)
        params2 = strategy_low.get_retry_params("tool2", "permanent")
        assert params2["max_retries"] >= 1
        assert params2["max_retries"] <= 10
