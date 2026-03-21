"""Stream Registry - Track active streaming conversations for reconnection.

Singleton registry that tracks which conversations have active streams,
accumulating content so that reconnecting clients can recover partial state.
"""

import threading
import time
from dataclasses import dataclass, field

@dataclass
class ActiveStream:
    """State for a single active streaming conversation."""

    conversation_id: str
    started_at: float
    accumulated_content: str = ""
    accumulated_thinking: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    mode: str = "chat"

class StreamRegistry:
    """Thread-safe registry of active streaming conversations."""

    def __init__(self):
        self._streams: dict[str, ActiveStream] = {}
        self._lock = threading.Lock()

    def register(self, conversation_id: str, mode: str = "chat") -> ActiveStream:
        """Register a new active stream. Overwrites any existing entry."""
        stream = ActiveStream(
            conversation_id=conversation_id,
            started_at=time.time(),
            mode=mode,
        )
        with self._lock:
            self._streams[conversation_id] = stream
        return stream

    def get(self, conversation_id: str) -> ActiveStream | None:
        """Get active stream state, or None if not streaming."""
        with self._lock:
            return self._streams.get(conversation_id)

    def is_active(self, conversation_id: str) -> bool:
        """Check if a conversation has an active stream."""
        with self._lock:
            return conversation_id in self._streams

    def complete(self, conversation_id: str) -> ActiveStream | None:
        """Remove and return a completed stream. Returns None if not found."""
        with self._lock:
            return self._streams.pop(conversation_id, None)

# Module-level singleton
_registry: StreamRegistry | None = None
_registry_lock = threading.Lock()

def get_stream_registry() -> StreamRegistry:
    """Get or create the global StreamRegistry singleton."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = StreamRegistry()
    return _registry
