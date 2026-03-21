"""Metrics API endpoints for latency and queue stats."""

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query

from core.api.middleware.request_metrics import get_recent_requests
from core.extensions.request_queue import get_request_queue
from core.observability.metrics import REQUEST_LATENCY

router = APIRouter()

def _aggregate_histogram() -> dict[str, Any]:
    """Aggregate REQUEST_LATENCY histogram across all labels."""
    samples = REQUEST_LATENCY.collect()[0].samples
    bucket_counts = defaultdict(float)
    total_count = 0.0
    total_sum = 0.0

    for sample in samples:
        name = sample.name
        labels = sample.labels
        value = float(sample.value)

        if name.endswith("_bucket"):
            bucket_counts[labels["le"]] += value
        elif name.endswith("_count"):
            total_count += value
        elif name.endswith("_sum"):
            total_sum += value

    return {
        "buckets": bucket_counts,
        "count": total_count,
        "sum": total_sum,
    }

def _percentile(bucket_counts: dict[str, float], count: float, p: float) -> float:
    """Estimate percentile from aggregated histogram buckets (seconds)."""
    if count <= 0:
        return 0.0

    target = count * p
    cumulative = 0.0

    for le in sorted(bucket_counts.keys(), key=lambda x: float("inf") if x == "+Inf" else float(x)):
        cumulative += bucket_counts[le]
        if cumulative >= target:
            return float("inf") if le == "+Inf" else float(le)
    return 0.0

@router.get("/latency")
async def get_latency():
    """Return aggregate latency stats from Prometheus histogram."""
    hist = _aggregate_histogram()
    count = hist["count"]
    total_sum = hist["sum"]
    buckets = hist["buckets"]

    avg_ms = (total_sum / count) * 1000 if count else 0.0
    p50 = _percentile(buckets, count, 0.5) * 1000
    p95 = _percentile(buckets, count, 0.95) * 1000
    p99 = _percentile(buckets, count, 0.99) * 1000

    return {
        "avg_ms": avg_ms,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "total_requests": int(count),
        "cache_hit_rate": 0,
    }

@router.get("/latency/recent")
async def get_latency_recent(limit: int | None = Query(None, ge=1, le=200)):
    """Return recent request entries (newest first)."""
    return get_recent_requests(limit)

@router.get("/latency/by-mode")
async def get_latency_by_mode():
    """Return simple aggregation by mode (uses recorded recent entries)."""
    recent = get_recent_requests()
    by_mode: dict[str, dict[str, float]] = {}
    for entry in recent:
        mode = entry.get("mode", "unknown") or "unknown"
        stats = by_mode.setdefault(mode, {"request_count": 0, "total_latency": 0.0, "successes": 0})
        stats["request_count"] += 1
        stats["total_latency"] += entry.get("latency_ms", 0.0)
        if entry.get("status") == "success":
            stats["successes"] += 1

    results = []
    for mode, stats in by_mode.items():
        count = stats["request_count"]
        avg_latency = stats["total_latency"] / count if count else 0.0
        success_rate = (stats["successes"] / count * 100) if count else 0.0
        results.append(
            {
                "mode": mode,
                "request_count": count,
                "avg_latency_ms": avg_latency,
                "success_rate": success_rate,
                "total_tokens": 0,
            }
        )
    return results

@router.get("/queue")
async def get_queue_status():
    """Expose queue stats from the request queue."""
    queue = get_request_queue()
    stats = await queue.get_stats()

    # Determine status based on queue depth
    if stats.queued_requests == 0 and stats.active_requests < stats.max_concurrent * 0.8:
        status = "healthy"
    elif stats.queued_requests < stats.max_queue_size * 0.5:
        status = "busy"
    else:
        status = "overloaded"

    return {
        "active": stats.active_requests,
        "queued": stats.queued_requests,
        "rejected_total": stats.total_rejected,
        "max_concurrent": stats.max_concurrent,
        "max_queue_size": stats.max_queue_size,
        "average_wait_ms": round(stats.avg_wait_ms, 2),
        "status": status,
    }
