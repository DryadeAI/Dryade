"""A2A Task Store.

In-memory store for A2A tasks with TTL-based expiry and thread safety.
Used by the A2A server executor to persist task results for later retrieval
via tasks/get and tasks/cancel.
"""

import threading
import time
from typing import Any


class A2ATaskStore:
    """Thread-safe in-memory task store with TTL expiry.

    Tasks are stored as dicts and automatically cleaned up when
    their TTL expires. All operations are protected by a threading.Lock.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize the task store.

        Args:
            ttl_seconds: Time-to-live for stored tasks in seconds (default 1 hour).
        """
        self._tasks: dict[str, dict[str, Any]] = {}
        self._timestamps: dict[str, float] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def store(self, task_id: str, task_dict: dict[str, Any]) -> None:
        """Store a task.

        Args:
            task_id: Unique task identifier.
            task_dict: Task data dict (A2A task format).
        """
        with self._lock:
            self._cleanup()
            self._tasks[task_id] = task_dict
            self._timestamps[task_id] = time.monotonic()

    def get(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a task by ID.

        Returns None if the task does not exist or has expired.
        """
        with self._lock:
            self._cleanup()
            return self._tasks.get(task_id)

    def update_status(
        self, task_id: str, state: str, message: dict[str, Any] | None = None
    ) -> bool:
        """Update the status of a stored task.

        Args:
            task_id: Task identifier.
            state: New A2A task state.
            message: Optional A2A message dict.

        Returns:
            True if the task was found and updated, False otherwise.
        """
        with self._lock:
            self._cleanup()
            task = self._tasks.get(task_id)
            if task is None:
                return False
            task["status"] = {"state": state}
            if message is not None:
                task["status"]["message"] = message
            return True

    def cancel(self, task_id: str) -> bool:
        """Cancel a task by setting its state to 'canceled'.

        Returns:
            True if the task was found and canceled, False otherwise.
        """
        return self.update_status(task_id, "canceled")

    def _cleanup(self) -> None:
        """Remove expired tasks. Must be called under lock."""
        now = time.monotonic()
        expired = [tid for tid, ts in self._timestamps.items() if (now - ts) >= self._ttl]
        for tid in expired:
            self._tasks.pop(tid, None)
            self._timestamps.pop(tid, None)

    def __len__(self) -> int:
        """Return number of non-expired tasks."""
        with self._lock:
            self._cleanup()
            return len(self._tasks)

# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_store: A2ATaskStore | None = None
_store_lock = threading.Lock()

def get_task_store() -> A2ATaskStore:
    """Get or create the global task store singleton.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = A2ATaskStore()
    return _store
