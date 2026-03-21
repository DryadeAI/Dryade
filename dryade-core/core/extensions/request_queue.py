"""Request Queue Manager for LLM Concurrency Control.

Limits concurrent LLM requests for production stability.
Fully configurable via environment variables for any hardware.
Target: ~150 LOC
"""

import asyncio
import logging
from dataclasses import dataclass

from core.utils.time import utcnow

logger = logging.getLogger(__name__)

@dataclass
class QueueStats:
    """Queue statistics snapshot."""

    active_requests: int
    queued_requests: int
    max_concurrent: int
    max_queue_size: int
    total_processed: int
    total_rejected: int
    avg_wait_ms: float

class RequestQueue:
    """Manages concurrent LLM request limiting.

    Environment variables:
        DRYADE_MAX_CONCURRENT_LLM: Maximum concurrent LLM requests (default: 8)
        DRYADE_MAX_QUEUE_SIZE: Maximum queued requests (default: 20)
        DRYADE_QUEUE_TIMEOUT_S: Queue wait timeout in seconds (default: 30.0)
    """

    def __init__(
        self,
        max_concurrent: int | None = None,
        max_queue_size: int | None = None,
        queue_timeout_s: float | None = None,
    ):
        """Initialize the request queue with configurable limits.

        Args:
            max_concurrent: Maximum concurrent LLM requests (env: DRYADE_MAX_CONCURRENT_LLM).
            max_queue_size: Maximum queued requests (env: DRYADE_MAX_QUEUE_SIZE).
            queue_timeout_s: Queue wait timeout in seconds (env: DRYADE_QUEUE_TIMEOUT_S).
        """
        # Configurable limits - tune based on your hardware
        from core.config import get_settings

        settings = get_settings()
        self.max_concurrent = max_concurrent or settings.max_concurrent_llm
        self.max_queue_size = max_queue_size or settings.max_queue_size
        self.queue_timeout_s = queue_timeout_s or settings.queue_timeout_s

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active = 0
        self._queued = 0
        self._total_processed = 0
        self._total_rejected = 0
        self._wait_times: list = []  # Rolling window of wait times
        self._lock = asyncio.Lock()

        logger.info(
            f"RequestQueue initialized: max_concurrent={self.max_concurrent}, "
            f"max_queue_size={self.max_queue_size}, timeout={self.queue_timeout_s}s"
        )

    async def acquire(self, timeout: float | None = None) -> bool:
        """Acquire a slot for LLM request.

        Args:
            timeout: Override timeout in seconds (uses default if not provided)

        Returns:
            True if acquired, False if rejected (queue full or timeout)
        """
        timeout = timeout or self.queue_timeout_s

        async with self._lock:
            # Check if queue is full
            if self._queued >= self.max_queue_size:
                self._total_rejected += 1
                logger.warning(
                    f"Request rejected: queue full ({self._queued}/{self.max_queue_size})"
                )
                return False

            self._queued += 1

        # Wait for semaphore with timeout
        start = utcnow()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            wait_ms = (utcnow() - start).total_seconds() * 1000
            async with self._lock:
                self._queued -= 1
                self._active += 1
                self._wait_times.append(wait_ms)
                # Keep rolling window bounded at 1000 entries
                if len(self._wait_times) > 1000:
                    self._wait_times = self._wait_times[-1000:]

            if wait_ms > 100:  # Log if waited more than 100ms
                logger.info(f"Request acquired after {wait_ms:.2f}ms wait")

            return True

        except TimeoutError:
            async with self._lock:
                self._queued -= 1
                self._total_rejected += 1
            logger.warning(f"Request rejected: queue timeout ({timeout}s)")
            return False

    async def release(self) -> None:
        """Release an LLM request slot."""
        async with self._lock:
            self._active -= 1
            self._total_processed += 1
        self._semaphore.release()

    async def get_stats(self) -> QueueStats:
        """Get current queue statistics."""
        async with self._lock:
            avg_wait = sum(self._wait_times) / len(self._wait_times) if self._wait_times else 0.0
            return QueueStats(
                active_requests=self._active,
                queued_requests=self._queued,
                max_concurrent=self.max_concurrent,
                max_queue_size=self.max_queue_size,
                total_processed=self._total_processed,
                total_rejected=self._total_rejected,
                avg_wait_ms=avg_wait,
            )

# Global instance
_queue: RequestQueue | None = None

def get_request_queue() -> RequestQueue:
    """Get or create global request queue."""
    global _queue
    if _queue is None:
        _queue = RequestQueue()
    return _queue

def reset_request_queue() -> None:
    """Reset global request queue (for testing)."""
    global _queue
    _queue = None

async def with_llm_slot(coro):
    """Execute coroutine with LLM slot acquisition.

    Usage:
        result = await with_llm_slot(some_async_llm_call())

    Raises:
        RuntimeError: If queue is full or timeout exceeded
    """
    queue = get_request_queue()
    acquired = await queue.acquire()
    if not acquired:
        raise RuntimeError("LLM request queue full or timeout - please retry in a moment")
    try:
        return await coro
    finally:
        await queue.release()
