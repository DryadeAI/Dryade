"""Resilience event types for structured failover logging.

Provides structured logging of provider failover events with timestamp,
reason classification, and latency tracking.
"""

import logging
import time
from dataclasses import asdict, dataclass

__all__ = [
    "FailoverEvent",
    "log_failover_event",
]

_failover_logger = logging.getLogger("dryade.provider.failover")

@dataclass
class FailoverEvent:
    """Structured record of a provider failover event.

    Attributes:
        timestamp: Unix timestamp (time.time()) when failover occurred.
        from_provider: Provider key that failed (format: "provider:model").
        to_provider: Provider key being tried next, or None if exhausted.
        reason: Classification of the failure:
            "timeout" - asyncio.TimeoutError
            "rate_limit" - HTTP 429
            "server_error" - HTTP 500/502
            "connection_error" - ConnectionError / network failure
        status_code: HTTP status code if applicable, else None.
        latency_ms: Time spent waiting for the failed provider (ms), or None.
    """

    timestamp: float
    from_provider: str
    to_provider: str | None
    reason: str
    status_code: int | None
    latency_ms: float | None

def log_failover_event(
    from_provider: str,
    exc: Exception,
    to_provider: str | None = None,
    latency_ms: float | None = None,
) -> FailoverEvent:
    """Classify exception and log a structured FailoverEvent.

    Args:
        from_provider: Provider key that failed (format: "provider:model").
        exc: The exception that caused the failover.
        to_provider: Next provider in chain, or None if exhausted.
        latency_ms: Time spent on the failed call (milliseconds).

    Returns:
        FailoverEvent that was logged.
    """
    import asyncio

    # Classify the exception into a reason string and extract status code
    status_code: int | None = None
    reason: str

    if isinstance(exc, asyncio.TimeoutError):
        reason = "timeout"
    else:
        # Try to extract HTTP status code from various exception shapes
        try:
            import httpx

            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
                if status_code == 429:
                    reason = "rate_limit"
                elif status_code in (500, 502):
                    reason = "server_error"
                else:
                    reason = "server_error"
            else:
                reason = "connection_error"
        except ImportError:
            reason = "connection_error"

        if not status_code:
            if isinstance(exc, ConnectionError):
                reason = "connection_error"

    event = FailoverEvent(
        timestamp=time.time(),
        from_provider=from_provider,
        to_provider=to_provider,
        reason=reason,
        status_code=status_code,
        latency_ms=latency_ms,
    )

    _failover_logger.info("provider_failover", extra={"event": asdict(event)})

    return event
