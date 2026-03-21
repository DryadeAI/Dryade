"""Orchestration state checkpoint/rollback system.

Provides in-memory snapshots before risky operations (tool execution,
context modifications) and persistent checkpointing via PostgreSQL for
cross-restart recovery.  Enables ROLLBACK action in the graduated
escalation ladder and time-travel debugging via checkpoint inspection.

Classes:
    CheckpointState  -- Immutable snapshot of orchestration state.
    CheckpointManager -- In-memory checkpoint ring buffer per execution.
    PersistentCheckpointBackend -- PostgreSQL persistence for cross-restart recovery.

Plan: 118.5-01
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

__all__ = ["CheckpointState", "CheckpointManager", "PersistentCheckpointBackend"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CheckpointState
# ---------------------------------------------------------------------------

@dataclass
class CheckpointState:
    """Immutable snapshot of orchestration state at a point in time.

    All data is stored as JSON-safe primitives (dicts, lists, strings)
    rather than live Pydantic/dataclass objects.  This enables cheap
    serialization for both in-memory ring buffer storage and database
    persistence without deep-copy overhead.

    Fields:
        checkpoint_id: Unique identifier (uuid4 hex string).
        execution_id: Execution context this checkpoint belongs to.
        created_at: UTC timestamp of checkpoint creation.
        label: Optional human-readable label (e.g. "before tool call").
        state_data: OrchestrationState.model_dump(mode="json") snapshot.
        observation_history_data: ObservationHistory.to_dict() snapshot.
        observations_data: List of OrchestrationObservation.model_dump(mode="json").
        failure_depth: Current failure escalation depth counter.
        tracker_data: ExecutionTracker._history entries as list of [tool, args_hash],
                      or None if no tracker was provided.
    """

    checkpoint_id: str
    execution_id: str
    created_at: datetime
    label: str
    state_data: dict[str, Any]
    observation_history_data: dict[str, Any]
    observations_data: list[dict[str, Any]]
    failure_depth: int
    tracker_data: list[tuple[str, str]] | None

    @classmethod
    def create(
        cls,
        execution_id: str,
        state: Any,  # OrchestrationState (Pydantic)
        observation_history: Any,  # ObservationHistory
        observations: list[Any],  # list[OrchestrationObservation]
        failure_depth: int,
        execution_tracker: Any | None = None,  # ExecutionTracker
        label: str = "",
    ) -> CheckpointState:
        """Create a CheckpointState from live orchestration objects.

        This is the primary factory method.  It serializes all state
        eagerly so the checkpoint is decoupled from the live objects.
        """
        # Serialize OrchestrationState
        state_data = state.model_dump(mode="json")

        # Serialize ObservationHistory
        observation_history_data = observation_history.to_dict()

        # Serialize observations list
        observations_data = [obs.model_dump(mode="json") for obs in observations]

        # Serialize ExecutionTracker (extract _history deque entries)
        tracker_data: list[tuple[str, str]] | None = None
        if execution_tracker is not None:
            tracker_data = list(execution_tracker._history)

        return cls(
            checkpoint_id=str(uuid4()),
            execution_id=execution_id,
            created_at=datetime.now(UTC),
            label=label,
            state_data=state_data,
            observation_history_data=observation_history_data,
            observations_data=observations_data,
            failure_depth=failure_depth,
            tracker_data=tracker_data,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary.

        Suitable for JSON encoding, database storage, or wire transfer.
        """
        return {
            "checkpoint_id": self.checkpoint_id,
            "execution_id": self.execution_id,
            "created_at": self.created_at.isoformat(),
            "label": self.label,
            "state_data": self.state_data,
            "observation_history_data": self.observation_history_data,
            "observations_data": self.observations_data,
            "failure_depth": self.failure_depth,
            "tracker_data": self.tracker_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointState:
        """Restore a CheckpointState from a serialized dictionary.

        Inverse of ``to_dict()``.
        """
        created_at_raw = data["created_at"]
        if isinstance(created_at_raw, str):
            created_at = datetime.fromisoformat(created_at_raw)
        else:
            created_at = created_at_raw

        tracker_data_raw = data.get("tracker_data")
        tracker_data: list[tuple[str, str]] | None = None
        if tracker_data_raw is not None:
            tracker_data = [tuple(entry) for entry in tracker_data_raw]

        return cls(
            checkpoint_id=data["checkpoint_id"],
            execution_id=data["execution_id"],
            created_at=created_at,
            label=data.get("label", ""),
            state_data=data["state_data"],
            observation_history_data=data["observation_history_data"],
            observations_data=data["observations_data"],
            failure_depth=data["failure_depth"],
            tracker_data=tracker_data,
        )

# ---------------------------------------------------------------------------
# CheckpointManager (in-memory ring buffer)
# ---------------------------------------------------------------------------

class CheckpointManager:
    """In-memory checkpoint ring buffer per execution.

    Maintains a bounded deque of CheckpointState snapshots per execution_id.
    When the deque exceeds ``max_snapshots``, the oldest checkpoint is
    automatically evicted (FIFO ring buffer).

    Thread safety: NOT thread-safe.  The orchestrator executes in a single
    asyncio event loop, so concurrent access is not a concern.
    """

    def __init__(self, max_snapshots: int = 20) -> None:
        self._max_snapshots = max_snapshots
        self._store: dict[str, deque[CheckpointState]] = {}

    def create(
        self,
        execution_id: str,
        state: Any,
        observation_history: Any,
        observations: list[Any],
        failure_depth: int,
        execution_tracker: Any | None = None,
        label: str = "",
    ) -> str:
        """Create a checkpoint and append to the ring buffer.

        Returns the checkpoint_id string.
        """
        cp = CheckpointState.create(
            execution_id=execution_id,
            state=state,
            observation_history=observation_history,
            observations=observations,
            failure_depth=failure_depth,
            execution_tracker=execution_tracker,
            label=label,
        )

        if execution_id not in self._store:
            self._store[execution_id] = deque(maxlen=self._max_snapshots)
        self._store[execution_id].append(cp)

        logger.debug(
            "[CHECKPOINT] Created %s for execution %s (label=%r, total=%d)",
            cp.checkpoint_id,
            execution_id,
            label,
            len(self._store[execution_id]),
        )
        return cp.checkpoint_id

    def restore_latest(self, execution_id: str) -> CheckpointState:
        """Return the most recent checkpoint for an execution.

        Raises:
            ValueError: If no checkpoints exist for this execution.
        """
        buf = self._store.get(execution_id)
        if not buf:
            raise ValueError(f"No checkpoints found for execution '{execution_id}'")
        return buf[-1]

    def restore(self, execution_id: str, checkpoint_id: str) -> CheckpointState:
        """Return a specific checkpoint by ID.

        Raises:
            ValueError: If the checkpoint is not found.
        """
        buf = self._store.get(execution_id)
        if not buf:
            raise ValueError(f"No checkpoints found for execution '{execution_id}'")
        for cp in buf:
            if cp.checkpoint_id == checkpoint_id:
                return cp
        raise ValueError(f"Checkpoint '{checkpoint_id}' not found for execution '{execution_id}'")

    def list_checkpoints(self, execution_id: str) -> list[tuple[str, datetime, str]]:
        """List all checkpoints for an execution in chronological order.

        Returns list of (checkpoint_id, created_at, label) tuples.
        """
        buf = self._store.get(execution_id)
        if not buf:
            return []
        return [(cp.checkpoint_id, cp.created_at, cp.label) for cp in buf]

    def clear(self, execution_id: str) -> None:
        """Remove all checkpoints for an execution."""
        self._store.pop(execution_id, None)

    def has_checkpoints(self, execution_id: str) -> bool:
        """Return True if any checkpoints exist for this execution."""
        buf = self._store.get(execution_id)
        return bool(buf)

# ---------------------------------------------------------------------------
# PersistentCheckpointBackend (PostgreSQL)
# ---------------------------------------------------------------------------

class PersistentCheckpointBackend:
    """PostgreSQL-backed persistent checkpoint storage for cross-restart recovery.

    Uses SQLAlchemy ORM via the shared database engine.
    """

    def __init__(self) -> None:
        pass

    @staticmethod
    def _model():
        from core.database.models import OrchestrationCheckpoint

        return OrchestrationCheckpoint

    @staticmethod
    def _get_session():
        from core.database.session import get_session

        return get_session()

    def save(self, checkpoint: CheckpointState) -> None:
        """Save a checkpoint (upsert)."""
        OrchestrationCheckpoint = self._model()
        state_json = json.dumps(checkpoint.to_dict())

        with self._get_session() as session:
            existing = (
                session.query(OrchestrationCheckpoint)
                .filter_by(checkpoint_id=checkpoint.checkpoint_id)
                .first()
            )
            if existing:
                existing.execution_id = checkpoint.execution_id
                existing.created_at = checkpoint.created_at.isoformat()
                existing.label = checkpoint.label
                existing.state_json = state_json
            else:
                record = OrchestrationCheckpoint(
                    checkpoint_id=checkpoint.checkpoint_id,
                    execution_id=checkpoint.execution_id,
                    created_at=checkpoint.created_at.isoformat(),
                    label=checkpoint.label,
                    state_json=state_json,
                )
                session.add(record)

    def load(self, checkpoint_id: str) -> CheckpointState:
        """Load a checkpoint by ID.

        Raises:
            ValueError: If not found.
        """
        OrchestrationCheckpoint = self._model()

        with self._get_session() as session:
            row = (
                session.query(OrchestrationCheckpoint)
                .filter_by(checkpoint_id=checkpoint_id)
                .first()
            )

            if row is None:
                raise ValueError(f"Checkpoint '{checkpoint_id}' not found in database")

            data = json.loads(row.state_json)
            return CheckpointState.from_dict(data)

    def list_by_execution(self, execution_id: str) -> list[tuple[str, datetime, str]]:
        """List checkpoints for an execution, ordered by created_at.

        Returns list of (checkpoint_id, created_at, label) tuples.
        """
        OrchestrationCheckpoint = self._model()

        with self._get_session() as session:
            rows = (
                session.query(OrchestrationCheckpoint)
                .filter_by(execution_id=execution_id)
                .order_by(OrchestrationCheckpoint.created_at.asc())
                .all()
            )

            return [
                (row.checkpoint_id, datetime.fromisoformat(row.created_at), row.label or "")
                for row in rows
            ]

    def cleanup(self, max_age_hours: int = 24) -> int:
        """Delete checkpoints older than max_age_hours.

        When max_age_hours=0, deletes ALL checkpoints (useful for testing).

        Returns the number of deleted rows.
        """
        OrchestrationCheckpoint = self._model()

        with self._get_session() as session:
            if max_age_hours == 0:
                deleted = session.query(OrchestrationCheckpoint).delete(synchronize_session="fetch")
                return deleted

            cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
            deleted = (
                session.query(OrchestrationCheckpoint)
                .filter(OrchestrationCheckpoint.created_at < cutoff)
                .delete(synchronize_session="fetch")
            )
            return deleted
