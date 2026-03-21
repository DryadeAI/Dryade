"""Cancellation support for orchestration.

Provides per-conversation cancel events so users can gracefully stop
a running orchestration via REST endpoint. The orchestrator loop checks
the event at the top of each iteration and returns partial results.
"""

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

__all__ = ["CancellationRegistry", "get_cancellation_registry"]

class CancellationRegistry:
    """Per-conversation asyncio.Event tracking for graceful cancellation.

    Each active orchestration gets an asyncio.Event keyed by conversation_id.
    The REST endpoint calls request_cancel() to set the event, and the
    orchestrator loop checks it at the top of each iteration.

    Example:
        registry = get_cancellation_registry()
        event = registry.get_or_create("conv-123")
        # Pass event to orchestrator...
        # Later, from REST endpoint:
        registry.request_cancel("conv-123")
        # Orchestrator detects event.is_set() and stops gracefully
    """

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._lock = threading.Lock()

    def get_or_create(self, conversation_id: str) -> asyncio.Event:
        """Get or create a cancel event for a conversation.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            asyncio.Event that can be checked/set for cancellation.
        """
        with self._lock:
            if conversation_id not in self._events:
                self._events[conversation_id] = asyncio.Event()
            return self._events[conversation_id]

    def request_cancel(self, conversation_id: str) -> bool:
        """Request cancellation of an active orchestration.

        Args:
            conversation_id: Conversation to cancel.

        Returns:
            True if an active event was found and set, False otherwise.
        """
        with self._lock:
            event = self._events.get(conversation_id)
        if event is None:
            return False
        event.set()
        logger.info(f"[CANCEL] Cancellation requested for conversation {conversation_id}")
        return True

    def clear(self, conversation_id: str) -> None:
        """Remove the cancel event after orchestration completes.

        Args:
            conversation_id: Conversation to clean up.
        """
        with self._lock:
            self._events.pop(conversation_id, None)

    def is_cancelled(self, conversation_id: str) -> bool:
        """Check if cancellation has been requested.

        Args:
            conversation_id: Conversation to check.

        Returns:
            True if the event exists and is set, False otherwise.
        """
        with self._lock:
            event = self._events.get(conversation_id)
        if event is None:
            return False
        return event.is_set()

# Module-level singleton (double-checked locking)
_registry: CancellationRegistry | None = None
_registry_lock = threading.Lock()

def get_cancellation_registry() -> CancellationRegistry:
    """Get the global CancellationRegistry singleton.

    Uses double-checked locking to ensure thread-safe singleton creation.

    Returns:
        The singleton CancellationRegistry instance.
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CancellationRegistry()
    return _registry
