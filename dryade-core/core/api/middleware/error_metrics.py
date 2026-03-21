"""Error Metrics Middleware.

Tracks error rates by type, endpoint, and status code for observability.
Provides in-memory error counting and basic monitoring foundation.
Future: Can be extended to integrate with Sentry, Prometheus, etc.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import ClassVar

from core.logs import get_logger
from core.utils.time import utcnow

logger = get_logger(__name__)

@dataclass
class ErrorMetrics:
    """Tracks error occurrences and rates."""

    # Error counts by type
    by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Error counts by endpoint
    by_endpoint: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Error counts by status code
    by_status: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # Recent errors (last 100)
    recent_errors: list[dict] = field(default_factory=list)

    # Timestamps for rate calculation
    window_start: datetime = field(default_factory=datetime.utcnow)
    window_errors: int = 0

    # Thread safety
    _lock: Lock = field(default_factory=Lock)

    # Singleton instance
    _instance: ClassVar["ErrorMetrics | None"] = None

    @classmethod
    def get_instance(cls) -> "ErrorMetrics":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

def record_error(
    error_type: str,
    endpoint: str,
    *,
    status_code: int = 500,
    error_message: str | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Record an error occurrence for metrics.

    Args:
        error_type: Exception type name (e.g., "ValueError", "MCPTransportError")
        endpoint: API endpoint path (e.g., "/api/chat")
        status_code: HTTP status code
        error_message: Optional error message (truncated for storage)
        request_id: Optional request ID for correlation
        user_id: Optional user ID for analysis
    """
    metrics = ErrorMetrics.get_instance()

    with metrics._lock:
        # Increment counters
        metrics.by_type[error_type] += 1
        metrics.by_endpoint[endpoint] += 1
        metrics.by_status[status_code] += 1
        metrics.window_errors += 1

        # Track recent errors (keep last 100)
        error_entry = {
            "timestamp": utcnow().isoformat(),
            "type": error_type,
            "endpoint": endpoint,
            "status": status_code,
            "message": (error_message or "")[:200],  # Truncate
            "request_id": request_id,
            "user_id": user_id,
        }
        metrics.recent_errors.append(error_entry)
        if len(metrics.recent_errors) > 100:
            metrics.recent_errors.pop(0)

        # Log structured error metric
        logger.debug(
            "Error recorded",
            error_type=error_type,
            endpoint=endpoint,
            status_code=status_code,
        )

def get_error_stats() -> dict:
    """Get current error statistics.

    Returns:
        Dict with error counts by type, endpoint, status, and rates
    """
    metrics = ErrorMetrics.get_instance()

    with metrics._lock:
        # Calculate error rate (errors per minute in current window)
        window_duration = (utcnow() - metrics.window_start).total_seconds()
        if window_duration > 0:
            error_rate = (metrics.window_errors / window_duration) * 60
        else:
            error_rate = 0

        # Reset window if > 5 minutes
        if window_duration > 300:
            metrics.window_start = utcnow()
            metrics.window_errors = 0

        return {
            "by_type": dict(metrics.by_type),
            "by_endpoint": dict(metrics.by_endpoint),
            "by_status": dict(metrics.by_status),
            "total_errors": sum(metrics.by_type.values()),
            "error_rate_per_minute": round(error_rate, 2),
            "recent_count": len(metrics.recent_errors),
        }

def get_recent_errors(limit: int = 20) -> list[dict]:
    """Get most recent errors.

    Args:
        limit: Maximum number of errors to return

    Returns:
        List of recent error entries
    """
    metrics = ErrorMetrics.get_instance()
    with metrics._lock:
        return list(reversed(metrics.recent_errors[-limit:]))

def clear_metrics() -> None:
    """Clear all error metrics (for testing)."""
    metrics = ErrorMetrics.get_instance()
    with metrics._lock:
        metrics.by_type.clear()
        metrics.by_endpoint.clear()
        metrics.by_status.clear()
        metrics.recent_errors.clear()
        metrics.window_start = utcnow()
        metrics.window_errors = 0

# Backward compatibility aliases
def get_error_summary() -> dict[str, int]:
    """Get current error counts by endpoint and error type.

    Returns:
        Dictionary mapping "endpoint:error_type" to count
    """
    stats = get_error_stats()
    # Combine endpoint:type format for backward compatibility
    result: dict[str, int] = {}
    for endpoint, count in stats["by_endpoint"].items():
        for error_type, type_count in stats["by_type"].items():
            key = f"{endpoint}:{error_type}"
            result[key] = min(count, type_count)
    return result

def get_error_count(endpoint: str, error_type: str) -> int:
    """Get error count for a specific endpoint and error type.

    Args:
        endpoint: API endpoint
        error_type: Error type

    Returns:
        Count of errors
    """
    stats = get_error_stats()
    endpoint_count = stats["by_endpoint"].get(endpoint, 0)
    type_count = stats["by_type"].get(error_type, 0)
    return min(endpoint_count, type_count)

def reset_error_counts() -> None:
    """Reset all error counts to zero.

    Useful for testing or after exporting metrics to external system.
    """
    clear_metrics()
    logger.info("Error counts reset", extra={"operation": "reset_error_counts"})

__all__ = [
    "ErrorMetrics",
    "record_error",
    "get_error_stats",
    "get_recent_errors",
    "clear_metrics",
    # Backward compatibility
    "get_error_summary",
    "get_error_count",
    "reset_error_counts",
]
