"""FailoverEngine — async provider failover with circuit breaker integration.

Iterates a list of LLMConfig entries, skipping those whose circuit is open,
and fails over on timeout / rate-limit / server-error / connection errors.
"""

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar

from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitConfig

__all__ = [
    "PROVIDER_CIRCUIT_BREAKER",
    "AllProvidersExhaustedError",
    "execute_with_fallback",
]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Module-level circuit breaker shared across all provider calls.
# Aggressive config: 1 failure opens, 2 successes close, 60s reset.
PROVIDER_CIRCUIT_BREAKER = CircuitBreaker(
    config=CircuitConfig(
        failure_threshold=1,
        success_threshold=2,
        reset_timeout_seconds=60.0,
        sliding_window_seconds=120.0,
    )
)

# Per-provider concurrency limiters (max 10 concurrent calls per provider)
_provider_semaphores: dict[str, asyncio.Semaphore] = {}
_semaphore_lock = asyncio.Lock()

async def _get_semaphore(provider_id: str, max_concurrent: int = 10) -> asyncio.Semaphore:
    """Get or create a semaphore for the given provider key."""
    async with _semaphore_lock:
        if provider_id not in _provider_semaphores:
            _provider_semaphores[provider_id] = asyncio.Semaphore(max_concurrent)
        return _provider_semaphores[provider_id]

class AllProvidersExhaustedError(Exception):
    """Raised when all providers in the chain have failed or have open circuits."""

    pass

async def execute_with_fallback(
    chain: list,
    call_fn: Callable[[Any], Awaitable[T]],
    cancel_event: asyncio.Event | None = None,
    on_failover: Callable[[str, str, str], None] | None = None,
    timeout: float = 15.0,
) -> T:
    """Execute call_fn against each provider in chain until one succeeds.

    Args:
        chain: Ordered list of LLMConfig objects to try.
        call_fn: Async callable that accepts an LLMConfig and returns a result.
        cancel_event: Optional asyncio.Event — if set, stops iteration immediately.
        on_failover: Optional callback(from_provider, to_provider, reason) called
            when failing over (only if next provider exists).
        timeout: Per-provider call timeout in seconds.

    Returns:
        Result from the first successful provider call.

    Raises:
        AllProvidersExhaustedError: When all providers fail or have open circuits.
    """
    from core.providers.resilience.events import log_failover_event

    last_exc: Exception | None = None

    for i, config in enumerate(chain):
        # Check cancellation before each attempt
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Fallback chain cancelled by cancel_event")
            raise AllProvidersExhaustedError("Fallback chain cancelled by caller")

        # Circuit breaker key: "provider:model"
        cb_key = f"{config.provider}:{config.model}"

        # Skip providers with open circuits
        if not PROVIDER_CIRCUIT_BREAKER.can_execute(cb_key):
            logger.debug("Skipping %s — circuit is OPEN", cb_key)
            continue

        # Acquire per-provider semaphore
        semaphore = await _get_semaphore(cb_key)

        start_time = time.monotonic()
        try:
            async with semaphore:
                result = await asyncio.wait_for(call_fn(config), timeout=timeout)

            PROVIDER_CIRCUIT_BREAKER.record_success(cb_key)
            return result

        except asyncio.TimeoutError as exc:
            latency_ms = (time.monotonic() - start_time) * 1000
            PROVIDER_CIRCUIT_BREAKER.record_failure(cb_key)
            last_exc = exc

            next_provider = (
                chain[i + 1].provider + ":" + chain[i + 1].model if i + 1 < len(chain) else None
            )
            event = log_failover_event(
                cb_key, exc, to_provider=next_provider, latency_ms=latency_ms
            )

            if on_failover and next_provider:
                on_failover(cb_key, next_provider, event.reason)

        except Exception as exc:
            latency_ms = (time.monotonic() - start_time) * 1000

            # Check if this is a retryable error
            if _is_retryable(exc):
                PROVIDER_CIRCUIT_BREAKER.record_failure(cb_key)
                last_exc = exc

                next_provider = (
                    chain[i + 1].provider + ":" + chain[i + 1].model if i + 1 < len(chain) else None
                )
                event = log_failover_event(
                    cb_key, exc, to_provider=next_provider, latency_ms=latency_ms
                )

                if on_failover and next_provider:
                    on_failover(cb_key, next_provider, event.reason)
            else:
                # Non-retryable error — propagate immediately
                raise

    raise AllProvidersExhaustedError(
        f"All {len(chain)} providers in fallback chain exhausted. Last error: {last_exc}"
    )

def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception warrants failing over to the next provider."""
    if isinstance(exc, ConnectionError):
        return True

    try:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (429, 500, 502, 503, 504)
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)):
            return True
    except ImportError:
        pass

    # Check for common HTTP client patterns without importing specific libraries
    exc_name = type(exc).__name__.lower()
    if "ratelimit" in exc_name or "timeout" in exc_name or "connection" in exc_name:
        return True

    # Check for status code attribute (many HTTP clients expose this)
    status_code = getattr(exc, "status_code", None)
    if status_code in (429, 500, 502, 503, 504):
        return True

    return False
