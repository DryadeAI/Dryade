"""Routing metrics tracker for the self-modification pipeline.

Phase 115.1: Collects routing decision metrics (hint fired, tool called,
fallback activated, user approval, latency) for data-driven optimization.

Dual-store pattern: in-memory list for fast reads + database persistence
for durability. Follows the CostTracker pattern from plugins/cost_tracker.

Metrics collection is best-effort -- failures never break orchestration.
"""

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingMetricRecord",
    "RoutingMetricsTracker",
    "get_routing_metrics_tracker",
    "record_routing_metric",
]

@dataclass
class RoutingMetricRecord:
    """Single routing decision metric record."""

    timestamp: datetime
    message_hash: str
    hint_fired: bool
    hint_type: str | None = None
    llm_tool_called: str | None = None
    fallback_activated: bool = False
    user_approved: bool | None = None
    latency_ms: int = 0
    # Phase 115.5: Optimization pipeline extensions
    tool_arguments_hash: str | None = None
    success_outcome: bool | None = None
    model_tier: str | None = None

@dataclass
class RoutingMetricsTracker:
    """Thread-safe routing metrics tracker with in-memory + database dual-store.

    Records are appended to an in-memory list for fast summary queries
    and persisted to database for durability across restarts.
    """

    records: list[RoutingMetricRecord] = field(default_factory=list)

    def record(
        self,
        message: str,
        hint_fired: bool,
        hint_type: str | None = None,
        llm_tool_called: str | None = None,
        fallback_activated: bool = False,
        user_approved: bool | None = None,
        latency_ms: int = 0,
        tool_arguments_hash: str | None = None,
        success_outcome: bool | None = None,
        model_tier: str | None = None,
    ) -> RoutingMetricRecord:
        """Record a routing decision metric.

        Args:
            message: The user message (hashed with sha256[:16] for privacy).
            hint_fired: Whether a routing hint fired for this message.
            hint_type: Type of hint that fired (e.g. 'meta_action', 'tool_match').
            llm_tool_called: Name of the self-mod tool the LLM called, if any.
            fallback_activated: Whether the guardrail fallback was activated.
            user_approved: Whether the user approved the escalation (None if pending).
            latency_ms: Routing decision latency in milliseconds.
            tool_arguments_hash: sha256[:16] of serialized tool arguments for dedup.
            success_outcome: Whether the tool call ultimately succeeded.
            model_tier: Which model tier was active during routing.

        Returns:
            The created RoutingMetricRecord.
        """
        msg_hash = hashlib.sha256(message.encode()).hexdigest()[:16]
        rec = RoutingMetricRecord(
            timestamp=datetime.now(UTC),
            message_hash=msg_hash,
            hint_fired=hint_fired,
            hint_type=hint_type,
            llm_tool_called=llm_tool_called,
            fallback_activated=fallback_activated,
            user_approved=user_approved,
            latency_ms=latency_ms,
            tool_arguments_hash=tool_arguments_hash,
            success_outcome=success_outcome,
            model_tier=model_tier,
        )
        self.records.append(rec)
        self._persist_to_db(rec)
        return rec

    def _persist_to_db(self, rec: RoutingMetricRecord) -> None:
        """Persist a metric record to database.

        Best-effort: failures are logged but never raised.
        Metrics must never break orchestration.
        """
        try:
            from core.database.models import RoutingMetric
            from core.database.session import get_session

            with get_session() as session:
                db_rec = RoutingMetric(
                    timestamp=rec.timestamp,
                    message_hash=rec.message_hash,
                    hint_fired=rec.hint_fired,
                    hint_type=rec.hint_type,
                    llm_tool_called=rec.llm_tool_called,
                    fallback_activated=rec.fallback_activated,
                    user_approved=rec.user_approved,
                    latency_ms=rec.latency_ms,
                    tool_arguments_hash=rec.tool_arguments_hash,
                    success_outcome=rec.success_outcome,
                    model_tier_used=rec.model_tier,
                )
                session.add(db_rec)
                session.commit()
        except Exception:
            # Best-effort persistence -- never break orchestration
            logger.debug("[ROUTING-METRICS] Failed to persist metric to DB", exc_info=True)

    def get_summary(self) -> dict:
        """Return summary statistics from in-memory records.

        Returns:
            Dict with total, hint_fired_count, fallback_count,
            tool_call_counts, avg_latency_ms.
        """
        total = len(self.records)
        if total == 0:
            return {
                "total": 0,
                "hint_fired_count": 0,
                "fallback_count": 0,
                "tool_call_counts": {},
                "avg_latency_ms": 0,
            }

        hint_fired_count = sum(1 for r in self.records if r.hint_fired)
        fallback_count = sum(1 for r in self.records if r.fallback_activated)

        tool_counts: dict[str, int] = {}
        for r in self.records:
            if r.llm_tool_called:
                tool_counts[r.llm_tool_called] = tool_counts.get(r.llm_tool_called, 0) + 1

        total_latency = sum(r.latency_ms for r in self.records)
        avg_latency = total_latency // total if total > 0 else 0

        return {
            "total": total,
            "hint_fired_count": hint_fired_count,
            "fallback_count": fallback_count,
            "tool_call_counts": tool_counts,
            "avg_latency_ms": avg_latency,
        }

# Global instance (thread-safe singleton)
_tracker: RoutingMetricsTracker | None = None
_lock = threading.Lock()

def get_routing_metrics_tracker() -> RoutingMetricsTracker:
    """Get or create the global routing metrics tracker.

    Thread-safe via double-checked locking.
    """
    global _tracker
    if _tracker is None:
        with _lock:
            if _tracker is None:
                _tracker = RoutingMetricsTracker()
    return _tracker

def record_routing_metric(**kwargs) -> None:
    """Convenience function to record a routing metric.

    Delegates to the global tracker's record() method.
    All arguments are passed through.
    """
    tracker = get_routing_metrics_tracker()
    tracker.record(**kwargs)
