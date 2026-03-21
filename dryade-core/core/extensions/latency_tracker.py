"""Latency Tracking Extension.

Tracks request latency, time-to-first-token, and component timing.
Target: ~120 LOC
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from core.utils.time import utcnow

logger = logging.getLogger(__name__)

@dataclass
class LatencyRecord:
    """Single latency measurement."""

    timestamp: str
    conversation_id: str | None
    mode: str  # chat, crew, flow, planner
    total_ms: float
    ttft_ms: float | None  # Time to first token
    cache_lookup_ms: float | None
    llm_call_ms: float | None
    cache_hit: bool

@dataclass
class LatencyTracker:
    """Track request latency metrics."""

    records: list[LatencyRecord] = field(default_factory=list)
    max_records: int = 10000  # Rolling window
    slow_threshold_ms: float = 5000.0  # Log warning for requests > 5s

    def record(
        self,
        conversation_id: str | None,
        mode: str,
        total_ms: float,
        ttft_ms: float | None = None,
        cache_lookup_ms: float | None = None,
        llm_call_ms: float | None = None,
        cache_hit: bool = False,
    ):
        """Record a latency measurement."""
        record = LatencyRecord(
            timestamp=utcnow().isoformat(),
            conversation_id=conversation_id,
            mode=mode,
            total_ms=total_ms,
            ttft_ms=ttft_ms,
            cache_lookup_ms=cache_lookup_ms,
            llm_call_ms=llm_call_ms,
            cache_hit=cache_hit,
        )
        self.records.append(record)

        # Rolling window
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records :]

        # Log slow requests
        if total_ms > self.slow_threshold_ms:
            logger.warning(
                f"Slow request: {total_ms:.2f}ms (mode={mode}, cache_hit={cache_hit})",
                extra={"conversation_id": conversation_id, "total_ms": total_ms},
            )

    def get_stats(self, mode: str | None = None, last_n: int = 1000) -> dict[str, Any]:
        """Get latency statistics."""
        records = self.records[-last_n:]
        if mode:
            records = [r for r in records if r.mode == mode]

        if not records:
            return {"count": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0}

        totals = sorted([r.total_ms for r in records])
        ttfts = sorted([r.ttft_ms for r in records if r.ttft_ms is not None])

        def percentile(data: list[float], p: float) -> float:
            if not data:
                return 0
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]

        cache_hits = sum(1 for r in records if r.cache_hit)

        return {
            "count": len(records),
            "cache_hit_rate": cache_hits / len(records) if records else 0,
            "total_latency": {
                "avg_ms": sum(totals) / len(totals),
                "p50_ms": percentile(totals, 50),
                "p95_ms": percentile(totals, 95),
                "p99_ms": percentile(totals, 99),
                "min_ms": min(totals),
                "max_ms": max(totals),
            },
            "ttft": {
                "avg_ms": sum(ttfts) / len(ttfts) if ttfts else 0,
                "p50_ms": percentile(ttfts, 50),
                "p95_ms": percentile(ttfts, 95),
            }
            if ttfts
            else None,
        }

# Global instance
_tracker: LatencyTracker | None = None
_lock = threading.Lock()

def get_latency_tracker() -> LatencyTracker:
    """Get or create global latency tracker."""
    global _tracker
    with _lock:
        if _tracker is None:
            _tracker = LatencyTracker()
    return _tracker

def record_latency(**kwargs):
    """Convenience function to record latency."""
    get_latency_tracker().record(**kwargs)

def get_latency_stats(**kwargs) -> dict[str, Any]:
    """Convenience function to get latency stats."""
    return get_latency_tracker().get_stats(**kwargs)
