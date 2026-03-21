"""TDD tests for core.orchestrator.checkpoint module.

Tests CheckpointState, CheckpointManager (in-memory ring buffer),
and PersistentCheckpointBackend (PostgreSQL-backed, tested with PostgreSQL test database).

Plan: 118.5-01
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base
from core.orchestrator.checkpoint import (
    CheckpointManager,
    CheckpointState,
    PersistentCheckpointBackend,
)
from core.orchestrator.models import (
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationState,
)
from core.orchestrator.observation import ObservationHistory
from core.orchestrator.soft_failure_detector import ExecutionTracker

# ---------------------------------------------------------------------------
# Database session patch for PersistentCheckpointBackend tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_get_session(monkeypatch):
    """Patch get_session to use a PostgreSQL test database for every test."""
    engine = create_engine(
        os.environ.get(
            "DRYADE_TEST_DATABASE_URL",
            "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
        ),
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def _mock_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("core.database.session.get_session", _mock_get_session)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_state(execution_id: str | None = None) -> OrchestrationState:
    """Create a minimal OrchestrationState for testing."""
    state = OrchestrationState(mode=OrchestrationMode.ADAPTIVE, actions_taken=5)
    if execution_id:
        state.execution_id = uuid.UUID(execution_id)
    return state

def _make_observation(agent: str = "test-agent", success: bool = True) -> OrchestrationObservation:
    """Create a minimal OrchestrationObservation for testing."""
    return OrchestrationObservation(
        agent_name=agent,
        task=f"test task for {agent}",
        result=f"result from {agent}",
        success=success,
        duration_ms=100,
    )

def _make_observation_history() -> ObservationHistory:
    """Create an ObservationHistory with a few entries."""
    history = ObservationHistory()
    history.add(_make_observation("agent-a"))
    history.add(_make_observation("agent-b"))
    return history

def _make_tracker() -> ExecutionTracker:
    """Create an ExecutionTracker with a few entries."""
    tracker = ExecutionTracker()
    tracker.record("tool-1", {"query": "test"})
    tracker.record("tool-2", {"file": "readme.md"})
    return tracker

# ---------------------------------------------------------------------------
# CheckpointState tests
# ---------------------------------------------------------------------------

class TestCheckpointState:
    """Tests for CheckpointState creation and serialization."""

    def test_checkpoint_state_from_orchestration_state(self):
        """Creates CheckpointState from OrchestrationState + ObservationHistory + observations + failure_depth."""
        state = _make_state()
        history = _make_observation_history()
        observations = [_make_observation("obs-1"), _make_observation("obs-2", success=False)]
        tracker = _make_tracker()

        cp = CheckpointState.create(
            execution_id=str(state.execution_id),
            state=state,
            observation_history=history,
            observations=observations,
            failure_depth=3,
            execution_tracker=tracker,
            label="before tool call",
        )

        assert cp.execution_id == str(state.execution_id)
        assert cp.failure_depth == 3
        assert cp.label == "before tool call"
        assert len(cp.observations_data) == 2
        assert cp.state_data is not None
        assert cp.observation_history_data is not None
        assert cp.tracker_data is not None

    def test_checkpoint_state_serialization(self):
        """to_dict() produces JSON-safe dict, from_dict() round-trips correctly."""
        state = _make_state()
        history = _make_observation_history()
        observations = [_make_observation()]
        tracker = _make_tracker()

        cp = CheckpointState.create(
            execution_id=str(state.execution_id),
            state=state,
            observation_history=history,
            observations=observations,
            failure_depth=2,
            execution_tracker=tracker,
        )

        d = cp.to_dict()
        # Verify JSON-safe
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

        # Round-trip
        cp2 = CheckpointState.from_dict(d)
        assert cp2.checkpoint_id == cp.checkpoint_id
        assert cp2.execution_id == cp.execution_id
        assert cp2.failure_depth == cp.failure_depth
        assert cp2.state_data == cp.state_data
        assert cp2.observations_data == cp.observations_data
        assert cp2.observation_history_data == cp.observation_history_data
        assert cp2.tracker_data == cp.tracker_data

    def test_checkpoint_state_has_metadata(self):
        """checkpoint_id is auto UUID, created_at is auto datetime, label is optional."""
        state = _make_state()
        history = _make_observation_history()

        cp = CheckpointState.create(
            execution_id=str(state.execution_id),
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
        )

        # Auto UUID
        uuid.UUID(cp.checkpoint_id)  # Should not raise
        # Auto datetime
        assert isinstance(cp.created_at, datetime)
        assert cp.created_at.tzinfo is not None or cp.created_at.year > 2020
        # Label defaults to ""
        assert cp.label == ""

# ---------------------------------------------------------------------------
# CheckpointManager in-memory tests
# ---------------------------------------------------------------------------

class TestCheckpointManager:
    """Tests for in-memory checkpoint management."""

    def _create_checkpoint(self, mgr: CheckpointManager, exec_id: str, label: str = "") -> str:
        """Helper to create a checkpoint with minimal state."""
        state = _make_state(exec_id)
        history = _make_observation_history()
        observations = [_make_observation()]
        return mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=observations,
            failure_depth=1,
            label=label,
        )

    def test_create_checkpoint(self):
        """Creates checkpoint, returns checkpoint_id string."""
        mgr = CheckpointManager(max_snapshots=5)
        exec_id = str(uuid.uuid4())
        cp_id = self._create_checkpoint(mgr, exec_id, label="test")
        assert isinstance(cp_id, str)
        uuid.UUID(cp_id)  # Valid UUID

    def test_restore_latest(self):
        """Creates 2 checkpoints, restore_latest() returns the most recent."""
        mgr = CheckpointManager(max_snapshots=5)
        exec_id = str(uuid.uuid4())
        _id1 = self._create_checkpoint(mgr, exec_id, label="first")
        _id2 = self._create_checkpoint(mgr, exec_id, label="second")

        latest = mgr.restore_latest(exec_id)
        assert latest.checkpoint_id == _id2
        assert latest.label == "second"

    def test_restore_by_id(self):
        """Creates multiple checkpoints, restore(checkpoint_id) returns the exact one."""
        mgr = CheckpointManager(max_snapshots=10)
        exec_id = str(uuid.uuid4())
        id1 = self._create_checkpoint(mgr, exec_id, label="first")
        _id2 = self._create_checkpoint(mgr, exec_id, label="second")
        id3 = self._create_checkpoint(mgr, exec_id, label="third")

        cp1 = mgr.restore(exec_id, id1)
        assert cp1.label == "first"

        cp3 = mgr.restore(exec_id, id3)
        assert cp3.label == "third"

    def test_restore_empty_raises(self):
        """restore_latest() when no checkpoints raises ValueError."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="No checkpoints"):
            mgr.restore_latest(exec_id)

    def test_ring_buffer_eviction(self):
        """Create max_snapshots + 5 checkpoints; verify only max_snapshots retained."""
        max_snaps = 5
        mgr = CheckpointManager(max_snapshots=max_snaps)
        exec_id = str(uuid.uuid4())

        all_ids = []
        for i in range(max_snaps + 5):
            cp_id = self._create_checkpoint(mgr, exec_id, label=f"cp-{i}")
            all_ids.append(cp_id)

        # Only max_snaps should remain
        listing = mgr.list_checkpoints(exec_id)
        assert len(listing) == max_snaps

        # Oldest 5 should be evicted
        for evicted_id in all_ids[:5]:
            with pytest.raises(ValueError):
                mgr.restore(exec_id, evicted_id)

        # Newest max_snaps should still be there
        for kept_id in all_ids[5:]:
            cp = mgr.restore(exec_id, kept_id)
            assert cp.checkpoint_id == kept_id

    def test_list_checkpoints(self):
        """list_checkpoints returns (id, created_at, label) tuples in chronological order."""
        mgr = CheckpointManager(max_snapshots=10)
        exec_id = str(uuid.uuid4())

        self._create_checkpoint(mgr, exec_id, label="alpha")
        self._create_checkpoint(mgr, exec_id, label="beta")
        self._create_checkpoint(mgr, exec_id, label="gamma")

        listing = mgr.list_checkpoints(exec_id)
        assert len(listing) == 3
        assert listing[0][2] == "alpha"
        assert listing[1][2] == "beta"
        assert listing[2][2] == "gamma"

        # Each entry is (str, datetime, str)
        for cp_id, created_at, label in listing:
            assert isinstance(cp_id, str)
            assert isinstance(created_at, datetime)
            assert isinstance(label, str)

    def test_clear(self):
        """clear(execution_id) removes all checkpoints for that execution."""
        mgr = CheckpointManager(max_snapshots=10)
        exec_id = str(uuid.uuid4())

        self._create_checkpoint(mgr, exec_id, label="test")
        assert mgr.has_checkpoints(exec_id) is True

        mgr.clear(exec_id)
        assert mgr.has_checkpoints(exec_id) is False

        with pytest.raises(ValueError):
            mgr.restore_latest(exec_id)

# ---------------------------------------------------------------------------
# CheckpointState restoration fidelity tests
# ---------------------------------------------------------------------------

class TestRestoreFidelity:
    """Tests that restored CheckpointState preserves all data."""

    def test_restore_observations(self):
        """Restored state has same observation list (deep equality via model_dump)."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        obs1 = _make_observation("agent-x", success=True)
        obs2 = _make_observation("agent-y", success=False)
        history = _make_observation_history()

        mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[obs1, obs2],
            failure_depth=0,
        )

        cp = mgr.restore_latest(exec_id)
        assert len(cp.observations_data) == 2
        assert cp.observations_data[0] == obs1.model_dump(mode="json")
        assert cp.observations_data[1] == obs2.model_dump(mode="json")

    def test_restore_observation_history(self):
        """Restored ObservationHistory has same to_dict() output as original."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        history = _make_observation_history()
        original_dict = history.to_dict()

        mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
        )

        cp = mgr.restore_latest(exec_id)
        assert cp.observation_history_data == original_dict

    def test_restore_failure_depth(self):
        """Restored failure_depth matches original."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        history = _make_observation_history()

        mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=7,
        )

        cp = mgr.restore_latest(exec_id)
        assert cp.failure_depth == 7

    def test_restore_execution_tracker(self):
        """Restored ExecutionTracker has same recent entries."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        history = _make_observation_history()
        tracker = _make_tracker()

        mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
            execution_tracker=tracker,
        )

        cp = mgr.restore_latest(exec_id)
        assert cp.tracker_data is not None
        assert len(cp.tracker_data) == 2  # 2 recorded entries
        assert cp.tracker_data[0][0] == "tool-1"
        assert cp.tracker_data[1][0] == "tool-2"

    def test_restore_orchestration_state(self):
        """Restored OrchestrationState has same actions_taken, mode, execution_id."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        state.actions_taken = 42
        history = _make_observation_history()

        mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
        )

        cp = mgr.restore_latest(exec_id)
        assert cp.state_data["actions_taken"] == 42
        assert cp.state_data["mode"] == "adaptive"
        assert cp.state_data["execution_id"] == exec_id

# ---------------------------------------------------------------------------
# PersistentCheckpointBackend tests
# ---------------------------------------------------------------------------

class TestPersistentCheckpointBackend:
    """Tests for persistent checkpoint storage (uses patched in-memory SQLite)."""

    def test_persistent_save_and_load(self):
        """Save checkpoint, load it back, verify fidelity."""
        backend = PersistentCheckpointBackend()

        state = _make_state()
        history = _make_observation_history()
        observations = [_make_observation()]
        tracker = _make_tracker()

        cp = CheckpointState.create(
            execution_id=str(state.execution_id),
            state=state,
            observation_history=history,
            observations=observations,
            failure_depth=5,
            execution_tracker=tracker,
            label="persistent test",
        )

        backend.save(cp)
        loaded = backend.load(cp.checkpoint_id)

        assert loaded.checkpoint_id == cp.checkpoint_id
        assert loaded.execution_id == cp.execution_id
        assert loaded.failure_depth == cp.failure_depth
        assert loaded.label == cp.label
        assert loaded.state_data == cp.state_data
        assert loaded.observations_data == cp.observations_data
        assert loaded.observation_history_data == cp.observation_history_data
        assert loaded.tracker_data == cp.tracker_data

    def test_persistent_list_by_execution(self):
        """Save 3 for exec A, 2 for exec B; list(A) returns 3."""
        backend = PersistentCheckpointBackend()

        exec_a = str(uuid.uuid4())
        exec_b = str(uuid.uuid4())

        state_a = _make_state(exec_a)
        state_b = _make_state(exec_b)
        history = _make_observation_history()

        for i in range(3):
            cp = CheckpointState.create(
                execution_id=exec_a,
                state=state_a,
                observation_history=history,
                observations=[],
                failure_depth=0,
                label=f"a-{i}",
            )
            backend.save(cp)

        for i in range(2):
            cp = CheckpointState.create(
                execution_id=exec_b,
                state=state_b,
                observation_history=history,
                observations=[],
                failure_depth=0,
                label=f"b-{i}",
            )
            backend.save(cp)

        listing_a = backend.list_by_execution(exec_a)
        listing_b = backend.list_by_execution(exec_b)

        assert len(listing_a) == 3
        assert len(listing_b) == 2

    def test_persistent_cleanup_old(self):
        """cleanup(max_age_hours=0) removes all checkpoints."""
        backend = PersistentCheckpointBackend()

        state = _make_state()
        history = _make_observation_history()

        cp = CheckpointState.create(
            execution_id=str(state.execution_id),
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
        )
        backend.save(cp)

        deleted = backend.cleanup(max_age_hours=0)
        assert deleted >= 1

        with pytest.raises(ValueError):
            backend.load(cp.checkpoint_id)

    def test_persistent_table_creation(self):
        """Backend can be created and used immediately (tables from patched session)."""
        backend = PersistentCheckpointBackend()

        # Should be able to list (empty) without error
        listing = backend.list_by_execution("nonexistent")
        assert listing == []

# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests for checkpoint module."""

    def test_checkpoint_with_empty_observations(self):
        """Checkpoint with empty observations list works."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        history = _make_observation_history()

        cp_id = mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
        )

        cp = mgr.restore_latest(exec_id)
        assert cp.observations_data == []
        assert cp.checkpoint_id == cp_id

    def test_checkpoint_with_no_tracker(self):
        """Checkpoint with execution_tracker=None works."""
        mgr = CheckpointManager()
        exec_id = str(uuid.uuid4())
        state = _make_state(exec_id)
        history = _make_observation_history()

        mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=history,
            observations=[],
            failure_depth=0,
            execution_tracker=None,
        )

        cp = mgr.restore_latest(exec_id)
        assert cp.tracker_data is None
