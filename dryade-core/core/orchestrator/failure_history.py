"""Cross-session failure history persistence and adaptive retry intelligence.

Records every tool failure with rich metadata, detects recurring patterns
deterministically, and computes adaptive retry parameters from historical
success rates.  This is the data foundation for failure-learning integration
wired by Plan 118.7-02.

SQLAlchemy ORM-backed, uses the shared PostgreSQL database engine.

Classes:
    FailureHistoryStore  -- SQLAlchemy ORM persistence for failure records.
    PatternDetector      -- Deterministic pattern detection over failure history.
    AdaptiveRetryStrategy -- Per-tool-per-error adaptive retry computation.

Plan: 118.7-01 (raw), 120-04 (ORM conversion)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func

from core.orchestrator.models import ErrorCategory, FailureAction

__all__ = ["FailureHistoryStore", "PatternDetector", "AdaptiveRetryStrategy"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FailureHistoryStore
# ---------------------------------------------------------------------------

class FailureHistoryStore:
    """SQLAlchemy ORM-backed persistent storage for tool failure history.

    Records every tool failure with rich metadata (tool name, server name,
    error category, action taken, recovery outcome, duration, retries, model).
    Provides efficient queries for failure rates, error stats, top failing
    tools, and server-level aggregation.

    Uses the shared PostgreSQL database engine via ``get_session()``.
    """

    def __init__(self) -> None:
        pass

    def _get_session(self):
        """Return a session context manager."""
        from core.database.session import get_session

        return get_session()

    @staticmethod
    def _model():
        """Return the FailureHistoryRecord model class (lazy import)."""
        from core.database.models import FailureHistoryRecord

        return FailureHistoryRecord

    def record_failure(
        self,
        tool_name: str,
        server_name: str,
        error_category: ErrorCategory,
        error_message: str,
        action_taken: FailureAction,
        recovery_success: bool,
        duration_ms: int = 0,
        retry_count: int = 0,
        model_used: str = "",
        timestamp_offset_hours: float = 0.0,
    ) -> None:
        """Record a single failure event.

        Args:
            tool_name: Name of the tool that failed (e.g. "read_file").
            server_name: MCP server name (e.g. "filesystem") or "internal".
            error_category: ErrorCategory enum value.
            error_message: Error message (truncated to 500 chars).
            action_taken: FailureAction enum value.
            recovery_success: Whether recovery succeeded.
            duration_ms: Time from first attempt to resolution in ms.
            retry_count: Number of retries before resolution.
            model_used: LLM model name if available.
            timestamp_offset_hours: Offset from now for testing (negative = past).
        """
        FailureHistoryRecord = self._model()

        # Truncate error message to 500 chars
        if len(error_message) > 500:
            error_message = error_message[:500]

        ts = datetime.now(UTC) + timedelta(hours=timestamp_offset_hours)
        timestamp = ts.isoformat()

        with self._get_session() as session:
            record = FailureHistoryRecord(
                timestamp=timestamp,
                tool_name=tool_name,
                server_name=server_name,
                error_category=error_category.value,
                error_message=error_message,
                action_taken=action_taken.value,
                recovery_success=1 if recovery_success else 0,
                duration_ms=duration_ms,
                retry_count=retry_count,
                model_used=model_used,
            )
            session.add(record)

    def get_failure_rate(self, tool_name: str, window_hours: int = 24) -> tuple[int, int, float]:
        """Get failure rate for a tool within a rolling window.

        Returns:
            (total_failures, total_successes, failure_rate) where failure_rate
            is failures / (failures + successes), or 0.0 if no data.
        """
        FailureHistoryRecord = self._model()
        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()

        with self._get_session() as session:
            rows = (
                session.query(
                    FailureHistoryRecord.recovery_success,
                    func.count(),
                )
                .filter(
                    FailureHistoryRecord.tool_name == tool_name,
                    FailureHistoryRecord.timestamp > cutoff,
                )
                .group_by(FailureHistoryRecord.recovery_success)
                .all()
            )

        failures = 0
        successes = 0
        for recovery_success, count in rows:
            if recovery_success == 0:
                failures = count
            else:
                successes = count

        total = failures + successes
        rate = failures / total if total > 0 else 0.0
        return (failures, successes, rate)

    def get_tool_error_stats(
        self, tool_name: str, error_category: str, window_hours: int = 24
    ) -> dict:
        """Get stats for a specific tool+error category combination.

        Returns:
            {"total": int, "recovered": int, "recovery_rate": float,
             "avg_retries": float, "avg_duration_ms": float}
        """
        FailureHistoryRecord = self._model()
        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()

        with self._get_session() as session:
            row = (
                session.query(
                    func.count(),
                    func.sum(
                        case(
                            (FailureHistoryRecord.recovery_success == 1, 1),
                            else_=0,
                        )
                    ),
                    func.avg(FailureHistoryRecord.retry_count),
                    func.avg(FailureHistoryRecord.duration_ms),
                )
                .filter(
                    FailureHistoryRecord.tool_name == tool_name,
                    FailureHistoryRecord.error_category == error_category,
                    FailureHistoryRecord.timestamp > cutoff,
                )
                .first()
            )

        total = row[0] or 0
        recovered = row[1] or 0
        avg_retries = row[2] or 0.0
        avg_duration = row[3] or 0.0
        recovery_rate = recovered / total if total > 0 else 0.0

        return {
            "total": total,
            "recovered": recovered,
            "recovery_rate": recovery_rate,
            "avg_retries": avg_retries,
            "avg_duration_ms": avg_duration,
        }

    def get_top_failing_tools(self, window_hours: int = 24, limit: int = 10) -> list[dict]:
        """Get top failing tools sorted by failure rate.

        Only includes tools with >= 3 total records to filter noise.

        Returns:
            [{"tool_name": str, "failure_count": int, "total_count": int,
              "failure_rate": float}] sorted by failure_rate desc.
        """
        FailureHistoryRecord = self._model()
        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()

        with self._get_session() as session:
            fail_count = func.sum(
                case(
                    (FailureHistoryRecord.recovery_success == 0, 1),
                    else_=0,
                )
            ).label("fail_count")
            total_count = func.count().label("total_count")

            rows = (
                session.query(
                    FailureHistoryRecord.tool_name,
                    fail_count,
                    total_count,
                )
                .filter(FailureHistoryRecord.timestamp > cutoff)
                .group_by(FailureHistoryRecord.tool_name)
                .having(total_count >= 3)
                .all()
            )

        # Sort by failure rate in Python (avoids dialect-specific cast issues)
        results = [
            {
                "tool_name": row[0],
                "failure_count": row[1],
                "total_count": row[2],
                "failure_rate": row[1] / row[2] if row[2] > 0 else 0.0,
            }
            for row in rows
        ]
        results.sort(key=lambda r: r["failure_rate"], reverse=True)
        return results[:limit]

    def get_server_failure_rate(self, server_name: str, window_hours: int = 24) -> float:
        """Get failure rate for a server (0.0-1.0).

        Used for pre-emptive circuit breaking decisions.
        """
        FailureHistoryRecord = self._model()
        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()

        with self._get_session() as session:
            rows = (
                session.query(
                    FailureHistoryRecord.recovery_success,
                    func.count(),
                )
                .filter(
                    FailureHistoryRecord.server_name == server_name,
                    FailureHistoryRecord.timestamp > cutoff,
                )
                .group_by(FailureHistoryRecord.recovery_success)
                .all()
            )

        failures = 0
        successes = 0
        for recovery_success, count in rows:
            if recovery_success == 0:
                failures = count
            else:
                successes = count

        total = failures + successes
        return failures / total if total > 0 else 0.0

    def purge_old_records(self, retention_days: int = 30) -> int:
        """Delete records older than retention_days.

        Returns the number of rows deleted.
        """
        FailureHistoryRecord = self._model()
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()

        with self._get_session() as session:
            deleted = (
                session.query(FailureHistoryRecord)
                .filter(FailureHistoryRecord.timestamp < cutoff)
                .delete(synchronize_session="fetch")
            )

        return deleted

    def count_records(self) -> int:
        """Return total record count for diagnostics."""
        FailureHistoryRecord = self._model()

        with self._get_session() as session:
            count = session.query(func.count(FailureHistoryRecord.id)).scalar()

        return count or 0

# ---------------------------------------------------------------------------
# PatternDetector
# ---------------------------------------------------------------------------

class PatternDetector:
    """Deterministic pattern detection over failure history.

    Wraps FailureHistoryStore queries to identify:
    - Tools with high failure rates (above configurable threshold)
    - Recurring error categories per tool
    - Servers that should be pre-emptively circuit-broken
    - Failure trend direction (improving / stable / degrading)
    """

    def __init__(self, store: FailureHistoryStore) -> None:
        self._store = store

    def detect_high_failure_tools(
        self, threshold: float = 0.5, window_hours: int = 24
    ) -> list[dict]:
        """Return tools with failure_rate >= threshold.

        Wraps ``store.get_top_failing_tools()`` and applies threshold filter.

        Returns:
            List of {"tool_name", "failure_rate", "failure_count", "total_count"}.
        """
        top = self._store.get_top_failing_tools(window_hours=window_hours)
        return [t for t in top if t["failure_rate"] >= threshold]

    def detect_recurring_errors(self, tool_name: str, window_hours: int = 24) -> list[dict]:
        """Detect recurring error categories for a tool.

        Groups failure_history by error_category for the given tool,
        returns categories with >= 2 occurrences sorted by count desc.

        Returns:
            [{"error_category": str, "count": int, "pct_of_total": float}]
        """
        from core.database.models import FailureHistoryRecord

        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()

        with self._store._get_session() as session:
            rows = (
                session.query(
                    FailureHistoryRecord.error_category,
                    func.count().label("cnt"),
                )
                .filter(
                    FailureHistoryRecord.tool_name == tool_name,
                    FailureHistoryRecord.timestamp > cutoff,
                )
                .group_by(FailureHistoryRecord.error_category)
                .having(func.count() >= 2)
                .order_by(func.count().desc())
                .all()
            )

        total = sum(row[1] for row in rows)
        return [
            {
                "error_category": row[0],
                "count": row[1],
                "pct_of_total": row[1] / total if total > 0 else 0.0,
            }
            for row in rows
        ]

    def should_preempt_circuit_break(
        self, server_name: str, threshold: float = 0.7, window_hours: int = 1
    ) -> bool:
        """Check if a server should be pre-emptively circuit-broken.

        Returns True if the server's failure rate exceeds the threshold
        over the given (typically short) window.
        """
        rate = self._store.get_server_failure_rate(server_name, window_hours=window_hours)
        return rate >= threshold

    def get_failure_trend(self, tool_name: str, window_hours: int = 24) -> str:
        """Determine failure trend direction for a tool.

        Splits the window into two halves and compares failure rates.

        Returns:
            "improving" if rate dropped > 10%,
            "degrading" if rate increased > 10%,
            "stable" otherwise.
        """
        from core.database.models import FailureHistoryRecord

        now = datetime.now(UTC)
        window_start = now - timedelta(hours=window_hours)
        midpoint = window_start + timedelta(hours=window_hours / 2)

        window_start_iso = window_start.isoformat()
        midpoint_iso = midpoint.isoformat()
        now_iso = now.isoformat()

        with self._store._get_session() as session:
            # First half: window_start to midpoint
            first_half = (
                session.query(
                    FailureHistoryRecord.recovery_success,
                    func.count(),
                )
                .filter(
                    FailureHistoryRecord.tool_name == tool_name,
                    FailureHistoryRecord.timestamp > window_start_iso,
                    FailureHistoryRecord.timestamp <= midpoint_iso,
                )
                .group_by(FailureHistoryRecord.recovery_success)
                .all()
            )

            # Second half: midpoint to now
            second_half = (
                session.query(
                    FailureHistoryRecord.recovery_success,
                    func.count(),
                )
                .filter(
                    FailureHistoryRecord.tool_name == tool_name,
                    FailureHistoryRecord.timestamp > midpoint_iso,
                    FailureHistoryRecord.timestamp <= now_iso,
                )
                .group_by(FailureHistoryRecord.recovery_success)
                .all()
            )

        def _calc_rate(rows: list[tuple]) -> float:
            failures = 0
            successes = 0
            for recovery_success, count in rows:
                if recovery_success == 0:
                    failures = count
                else:
                    successes = count
            total = failures + successes
            return failures / total if total > 0 else 0.0

        first_rate = _calc_rate(first_half)
        second_rate = _calc_rate(second_half)
        diff = second_rate - first_rate

        if diff < -0.10:
            return "improving"
        elif diff > 0.10:
            return "degrading"
        return "stable"

# ---------------------------------------------------------------------------
# AdaptiveRetryStrategy
# ---------------------------------------------------------------------------

class AdaptiveRetryStrategy:
    """Per-tool-per-error adaptive retry computation.

    Queries historical success rates from FailureHistoryStore and computes
    adaptive max_retries and backoff_base with hard-clamped bounds:
    - max_retries: [1, 10]
    - backoff_base: [1.0, 10.0]
    """

    def __init__(
        self,
        store: FailureHistoryStore,
        default_max_retries: int = 3,
        default_backoff_base: float = 2.0,
    ) -> None:
        self._store = store
        self._default_max_retries = default_max_retries
        self._default_backoff_base = default_backoff_base

    def get_retry_params(self, tool_name: str, error_category: str, window_hours: int = 24) -> dict:
        """Compute adaptive retry parameters for a tool+error combination.

        Returns:
            {"max_retries": int, "backoff_base": float, "reason": str}

        Logic:
            - recovery_rate >= 0.8: more retries (default+2), lower backoff (1.5)
            - recovery_rate >= 0.5: default retries and backoff
            - recovery_rate >= 0.2: fewer retries (default-1), higher backoff (3.0)
            - recovery_rate <  0.2: minimal retries (1), high backoff (5.0)
        """
        stats = self._store.get_tool_error_stats(tool_name, error_category, window_hours)

        if stats["total"] == 0:
            return {
                "max_retries": self._default_max_retries,
                "backoff_base": self._default_backoff_base,
                "reason": "no history",
            }

        rate = stats["recovery_rate"]

        if rate >= 0.8:
            max_retries = min(self._default_max_retries + 2, 10)
            backoff_base = 1.5
            reason = f"high recovery rate ({rate:.2f})"
        elif rate >= 0.5:
            max_retries = self._default_max_retries
            backoff_base = self._default_backoff_base
            reason = f"moderate recovery rate ({rate:.2f})"
        elif rate >= 0.2:
            max_retries = max(self._default_max_retries - 1, 1)
            backoff_base = 3.0
            reason = f"low recovery rate ({rate:.2f})"
        else:
            max_retries = 1
            backoff_base = 5.0
            reason = f"very low recovery rate ({rate:.2f})"

        # Hard clamp
        max_retries = max(1, min(max_retries, 10))
        backoff_base = max(1.0, min(backoff_base, 10.0))

        return {
            "max_retries": max_retries,
            "backoff_base": backoff_base,
            "reason": reason,
        }
