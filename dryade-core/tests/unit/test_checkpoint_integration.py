"""Integration tests for checkpoint/rollback orchestrator wiring.

Verifies:
- Checkpoint creation before tool execution
- ROLLBACK handler restores state from checkpoint
- Graduated escalation triggers ROLLBACK at depth 3
- Feature flag disables checkpoint creation
- Persistent backend integration

Plan: 118.5-02
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.checkpoint import CheckpointManager, CheckpointState
from core.orchestrator.config import OrchestrationConfig, get_orchestration_config
from core.orchestrator.models import (
    FailureAction,
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationState,
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.observation import ObservationHistory
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.soft_failure_detector import ExecutionTracker

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _default_config(**overrides) -> OrchestrationConfig:
    """Create a default config with optional overrides."""
    cfg = get_orchestration_config()
    for k, v in overrides.items():
        object.__setattr__(cfg, k, v)
    return cfg

def _make_task(agent="test-agent", tool="search_web", args=None) -> OrchestrationTask:
    """Create a simple OrchestrationTask."""
    return OrchestrationTask(
        agent_name=agent,
        description="Search for Python web frameworks",
        tool=tool,
        arguments=args or {"query": "python"},
    )

def _make_state() -> OrchestrationState:
    """Create a minimal OrchestrationState."""
    return OrchestrationState(mode=OrchestrationMode.ADAPTIVE, actions_taken=2)

def _make_observation(agent="test-agent", success=True) -> OrchestrationObservation:
    """Create a minimal OrchestrationObservation."""
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

@pytest.fixture
def orchestrator():
    """Minimal DryadeOrchestrator with a mock agent."""
    o = DryadeOrchestrator.__new__(DryadeOrchestrator)
    o.agents = MagicMock()
    o._soft_failure_detector = None
    o._circuit_breaker = None
    o._checkpoint_manager = None
    o._persistent_backend = None
    return o

@pytest.fixture
def mock_agent_ok():
    """Agent that returns a successful result with real content."""
    result = SimpleNamespace(
        result="Here are the search results for Python web frameworks.",
        status="ok",
        error=None,
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    caps = SimpleNamespace(
        max_retries=1,
        timeout_seconds=30,
        is_critical=True,
        supports_streaming=False,
        supports_memory=False,
        supports_resources=False,
        supports_prompts=False,
        supports_knowledge=False,
        supports_delegation=False,
        supports_callbacks=False,
        supports_sessions=False,
        supports_artifacts=False,
        supports_async_tasks=False,
        supports_push=False,
    )
    agent.capabilities = MagicMock(return_value=caps)
    return agent

@pytest.fixture
def mock_agent_failing():
    """Agent that always returns a failure."""
    result = SimpleNamespace(
        result=None,
        status="error",
        error="Connection refused",
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    caps = SimpleNamespace(
        max_retries=0,
        timeout_seconds=30,
        is_critical=True,
        supports_streaming=False,
        supports_memory=False,
        supports_resources=False,
        supports_prompts=False,
        supports_knowledge=False,
        supports_delegation=False,
        supports_callbacks=False,
        supports_sessions=False,
        supports_artifacts=False,
        supports_async_tasks=False,
        supports_push=False,
    )
    agent.capabilities = MagicMock(return_value=caps)
    return agent

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckpointCreation:
    """Tests for checkpoint creation in _execute_with_retry."""

    @pytest.mark.asyncio
    async def test_checkpoint_created_before_execution(self, orchestrator, mock_agent_ok):
        """Checkpoint is created before retry loop when feature flag enabled."""
        orchestrator.agents.get = MagicMock(return_value=mock_agent_ok)
        task = _make_task()
        state = _make_state()
        obs_history = _make_observation_history()
        observations = [_make_observation()]

        # Use a real CheckpointManager to verify creation
        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        orchestrator._checkpoint_manager = checkpoint_mgr
        exec_id = str(state.execution_id)

        cfg = _default_config(checkpoint_enabled=True, circuit_breaker_enabled=False)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._execute_with_retry(
                task,
                exec_id,
                {},
                [],
                failure_depth=0,
                execution_tracker=ExecutionTracker(),
                state=state,
                observation_history=obs_history,
                observations=observations,
            )

        # Checkpoint should have been created
        assert checkpoint_mgr.has_checkpoints(exec_id)
        listing = checkpoint_mgr.list_checkpoints(exec_id)
        assert len(listing) == 1
        assert listing[0][2].startswith("before:test-agent:")

        # Execution should succeed
        assert result.success is True

    @pytest.mark.asyncio
    async def test_checkpoint_not_created_when_disabled(self, orchestrator, mock_agent_ok):
        """No checkpoint created when checkpoint_enabled=False."""
        orchestrator.agents.get = MagicMock(return_value=mock_agent_ok)
        task = _make_task()
        state = _make_state()
        obs_history = _make_observation_history()

        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        orchestrator._checkpoint_manager = checkpoint_mgr
        exec_id = str(state.execution_id)

        cfg = _default_config(checkpoint_enabled=False, circuit_breaker_enabled=False)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            await orchestrator._execute_with_retry(
                task,
                exec_id,
                {},
                [],
                state=state,
                observation_history=obs_history,
                observations=[],
            )

        # No checkpoint should exist
        assert not checkpoint_mgr.has_checkpoints(exec_id)

    @pytest.mark.asyncio
    async def test_checkpoint_not_created_when_state_is_none(self, orchestrator, mock_agent_ok):
        """No checkpoint created when state is not provided (backwards compat)."""
        orchestrator.agents.get = MagicMock(return_value=mock_agent_ok)
        task = _make_task()

        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        orchestrator._checkpoint_manager = checkpoint_mgr

        cfg = _default_config(checkpoint_enabled=True, circuit_breaker_enabled=False)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._execute_with_retry(
                task,
                "exec-001",
                {},
                [],
                # state=None, observation_history=None by default
            )

        # No checkpoint (state is None), but execution still succeeds
        assert not checkpoint_mgr.has_checkpoints("exec-001")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_checkpoint_creation_failure_non_fatal(self, orchestrator, mock_agent_ok):
        """Checkpoint creation failure does not block execution."""
        orchestrator.agents.get = MagicMock(return_value=mock_agent_ok)
        task = _make_task()
        state = _make_state()
        obs_history = _make_observation_history()

        # Use a checkpoint manager that raises on create
        broken_mgr = CheckpointManager()
        broken_mgr.create = MagicMock(side_effect=RuntimeError("disk full"))
        orchestrator._checkpoint_manager = broken_mgr

        cfg = _default_config(checkpoint_enabled=True, circuit_breaker_enabled=False)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._execute_with_retry(
                task,
                "exec-002",
                {},
                [],
                state=state,
                observation_history=obs_history,
                observations=[],
            )

        # Execution should still succeed despite checkpoint failure
        assert result.success is True

class TestPersistentCheckpoint:
    """Tests for persistent checkpoint backend integration."""

    @pytest.mark.asyncio
    async def test_persistent_checkpoint_saved_when_enabled(
        self, orchestrator, mock_agent_ok, tmp_path
    ):
        """Persistent backend save() is called when both flags are enabled."""
        orchestrator.agents.get = MagicMock(return_value=mock_agent_ok)
        task = _make_task()
        state = _make_state()
        obs_history = _make_observation_history()

        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        orchestrator._checkpoint_manager = checkpoint_mgr

        # Mock the persistent backend
        mock_persistent = MagicMock()
        orchestrator._persistent_backend = mock_persistent
        exec_id = str(state.execution_id)

        cfg = _default_config(
            checkpoint_enabled=True,
            persistent_checkpoint_enabled=True,
            circuit_breaker_enabled=False,
        )
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            await orchestrator._execute_with_retry(
                task,
                exec_id,
                {},
                [],
                state=state,
                observation_history=obs_history,
                observations=[],
            )

        # Persistent backend should have been called with the checkpoint
        mock_persistent.save.assert_called_once()
        saved_cp = mock_persistent.save.call_args[0][0]
        assert isinstance(saved_cp, CheckpointState)
        assert saved_cp.execution_id == exec_id

class TestRollbackHandler:
    """Tests for ROLLBACK handler in _handle_failure."""

    @pytest.mark.asyncio
    async def test_rollback_restores_state(self, orchestrator):
        """ROLLBACK handler returns OrchestrationResult with checkpoint data."""
        state = _make_state()
        exec_id = str(state.execution_id)

        # Create a real checkpoint to restore from
        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        obs_history = _make_observation_history()
        observations = [_make_observation("agent-a"), _make_observation("agent-b")]

        checkpoint_mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=obs_history,
            observations=observations,
            failure_depth=0,
            label="test-checkpoint",
        )
        orchestrator._checkpoint_manager = checkpoint_mgr

        # Create a failure observation with ROLLBACK action
        failed_obs = _make_observation("test-agent", success=False)
        failed_obs.error = "Something went wrong"
        failed_obs.failure_thought = OrchestrationThought(
            reasoning="Rollback test",
            is_final=False,
            failure_action=FailureAction.ROLLBACK,
        )

        mock_agent = MagicMock()
        mock_caps = SimpleNamespace(is_critical=True, max_retries=1)
        mock_agent.capabilities.return_value = mock_caps
        orchestrator.agents.get = MagicMock(return_value=mock_agent)

        cfg = _default_config(checkpoint_enabled=True)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._handle_failure(
                failed_obs,
                {},
                [],
                state,
                failure_depth=3,
                observation_history=obs_history,
            )

        # Should return a successful result with ROLLBACK: prefix
        assert result.success is True
        assert result.reason is not None
        assert result.reason.startswith("ROLLBACK:")
        assert result.observation_history_data is not None
        # Verify the checkpoint data is valid
        restored = CheckpointState.from_dict(result.observation_history_data)
        assert restored.failure_depth == 0
        assert len(restored.observations_data) == 2

    @pytest.mark.asyncio
    async def test_rollback_falls_back_to_alternative_when_no_checkpoints(self, orchestrator):
        """ROLLBACK with no checkpoints falls back to ALTERNATIVE."""
        state = _make_state()

        # Empty checkpoint manager (no checkpoints)
        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        orchestrator._checkpoint_manager = checkpoint_mgr

        failed_obs = _make_observation("test-agent", success=False)
        failed_obs.error = "Something went wrong"
        failed_obs.failure_thought = OrchestrationThought(
            reasoning="Rollback test",
            is_final=False,
            failure_action=FailureAction.ROLLBACK,
            alternative_agent=None,  # No alternative available
        )

        mock_agent = MagicMock()
        mock_caps = SimpleNamespace(is_critical=True, max_retries=1)
        mock_agent.capabilities.return_value = mock_caps
        orchestrator.agents.get = MagicMock(return_value=mock_agent)

        cfg = _default_config(checkpoint_enabled=True)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._handle_failure(
                failed_obs,
                {},
                [],
                state,
                failure_depth=3,
                observation_history=_make_observation_history(),
            )

        # Should escalate because ALTERNATIVE has no agent specified
        assert result.needs_escalation is True

    @pytest.mark.asyncio
    async def test_rollback_observation_history_fidelity(self, orchestrator):
        """Checkpoint data preserves observation history accurately."""
        state = _make_state()
        exec_id = str(state.execution_id)

        # Build specific observation history
        obs_history = ObservationHistory()
        obs1 = _make_observation("agent-x")
        obs2 = _make_observation("agent-y")
        obs3 = _make_observation("agent-z", success=False)
        obs_history.add(obs1)
        obs_history.add(obs2)
        obs_history.add(obs3)
        original_dict = obs_history.to_dict()

        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        checkpoint_mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=obs_history,
            observations=[obs1, obs2],
            failure_depth=1,
            label="fidelity-test",
        )
        orchestrator._checkpoint_manager = checkpoint_mgr

        # Trigger ROLLBACK
        failed_obs = _make_observation("test-agent", success=False)
        failed_obs.error = "err"
        failed_obs.failure_thought = OrchestrationThought(
            reasoning="fidelity",
            is_final=False,
            failure_action=FailureAction.ROLLBACK,
        )
        mock_agent = MagicMock()
        mock_agent.capabilities.return_value = SimpleNamespace(is_critical=True, max_retries=1)
        orchestrator.agents.get = MagicMock(return_value=mock_agent)

        cfg = _default_config(checkpoint_enabled=True)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._handle_failure(
                failed_obs,
                {},
                [],
                state,
                failure_depth=3,
                observation_history=obs_history,
            )

        # Verify fidelity
        restored = CheckpointState.from_dict(result.observation_history_data)
        assert restored.observation_history_data == original_dict
        assert restored.failure_depth == 1

    @pytest.mark.asyncio
    async def test_rollback_failure_depth_restored(self, orchestrator):
        """Rollback restores failure_depth from checkpoint (not current depth)."""
        state = _make_state()
        exec_id = str(state.execution_id)

        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        obs_history = _make_observation_history()

        # Checkpoint with failure_depth=0
        checkpoint_mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=obs_history,
            observations=[],
            failure_depth=0,  # Checkpoint at depth 0
        )
        orchestrator._checkpoint_manager = checkpoint_mgr

        failed_obs = _make_observation("test-agent", success=False)
        failed_obs.error = "err"
        failed_obs.failure_thought = OrchestrationThought(
            reasoning="depth test",
            is_final=False,
            failure_action=FailureAction.RETRY,  # Graduated escalation at depth 3 overrides to ROLLBACK
        )
        mock_agent = MagicMock()
        mock_agent.capabilities.return_value = SimpleNamespace(is_critical=True, max_retries=1)
        orchestrator.agents.get = MagicMock(return_value=mock_agent)

        cfg = _default_config(checkpoint_enabled=True)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._handle_failure(
                failed_obs,
                {},
                [],
                state,
                failure_depth=3,  # Triggers ROLLBACK via graduated escalation
                observation_history=obs_history,
            )

        # Verify ROLLBACK was chosen
        assert result.success is True
        assert result.reason is not None
        assert result.reason.startswith("ROLLBACK:")

        restored = CheckpointState.from_dict(result.observation_history_data)
        assert restored.failure_depth == 0  # Should be 0, not 3

class TestGraduatedEscalation:
    """Tests for graduated escalation ROLLBACK at depth 3."""

    @pytest.mark.asyncio
    async def test_graduated_escalation_rollback_at_depth_3(self, orchestrator):
        """At depth 3 with checkpoints available, ROLLBACK is chosen over ALTERNATIVE."""
        state = _make_state()
        exec_id = str(state.execution_id)

        # Create checkpoints so ROLLBACK is viable
        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        obs_history = _make_observation_history()
        checkpoint_mgr.create(
            execution_id=exec_id,
            state=state,
            observation_history=obs_history,
            observations=[],
            failure_depth=0,
        )
        orchestrator._checkpoint_manager = checkpoint_mgr

        # Create failure with RETRY action (graduated escalation will override)
        failed_obs = _make_observation("test-agent", success=False)
        failed_obs.error = "repeated semantic failure"
        failed_obs.failure_thought = OrchestrationThought(
            reasoning="Retry please",
            is_final=False,
            failure_action=FailureAction.RETRY,  # Will be overridden to ROLLBACK
        )

        mock_agent = MagicMock()
        mock_agent.capabilities.return_value = SimpleNamespace(is_critical=True, max_retries=1)
        orchestrator.agents.get = MagicMock(return_value=mock_agent)

        cfg = _default_config(checkpoint_enabled=True)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._handle_failure(
                failed_obs,
                {},
                [],
                state,
                failure_depth=3,  # Triggers graduated escalation
                observation_history=obs_history,
            )

        # Should be ROLLBACK (not ALTERNATIVE)
        assert result.success is True
        assert result.reason is not None
        assert result.reason.startswith("ROLLBACK:")

    @pytest.mark.asyncio
    async def test_graduated_escalation_skips_rollback_without_checkpoints(self, orchestrator):
        """At depth 3 without checkpoints, ALTERNATIVE is chosen instead of ROLLBACK."""
        state = _make_state()

        # Empty checkpoint manager
        checkpoint_mgr = CheckpointManager(max_snapshots=5)
        orchestrator._checkpoint_manager = checkpoint_mgr

        failed_obs = _make_observation("test-agent", success=False)
        failed_obs.error = "repeated failure"
        failed_obs.failure_thought = OrchestrationThought(
            reasoning="Retry please",
            is_final=False,
            failure_action=FailureAction.RETRY,
            alternative_agent="alt-agent",  # Provide alternative for test
        )

        mock_agent = MagicMock()
        mock_agent.capabilities.return_value = SimpleNamespace(is_critical=True, max_retries=1)
        orchestrator.agents.get = MagicMock(return_value=mock_agent)

        # Set up alt-agent execution
        alt_result = SimpleNamespace(result="alt success", status="ok", error=None)
        alt_agent = AsyncMock()
        alt_agent.execute_with_context = AsyncMock(return_value=alt_result)

        def get_agent(name):
            if name == "alt-agent":
                return alt_agent
            return mock_agent

        orchestrator.agents.get = MagicMock(side_effect=get_agent)

        cfg = _default_config(
            checkpoint_enabled=True,
            circuit_breaker_enabled=False,
            soft_failure_detection_enabled=False,
        )
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            result = await orchestrator._handle_failure(
                failed_obs,
                {},
                [],
                state,
                failure_depth=3,
                observation_history=_make_observation_history(),
            )

        # Should succeed via ALTERNATIVE (not ROLLBACK)
        assert result.success is True
        assert result.alternative_agent_used == "alt-agent"

class TestCheckpointLazyProperties:
    """Tests for lazy property creation."""

    def test_checkpoint_manager_property(self):
        """checkpoint_manager lazy property creates CheckpointManager."""
        o = DryadeOrchestrator.__new__(DryadeOrchestrator)
        o._checkpoint_manager = None

        mgr = o.checkpoint_manager
        assert isinstance(mgr, CheckpointManager)

        # Same instance on second access (cached)
        mgr2 = o.checkpoint_manager
        assert mgr is mgr2

    def test_feature_flag_env_override(self, monkeypatch):
        """DRYADE_CHECKPOINT_ENABLED=false disables checkpoint via env."""
        monkeypatch.setenv("DRYADE_CHECKPOINT_ENABLED", "false")
        cfg = get_orchestration_config()
        assert cfg.checkpoint_enabled is False

    def test_feature_flag_persistent_env_override(self, monkeypatch):
        """DRYADE_PERSISTENT_CHECKPOINT_ENABLED=true enables persistent via env."""
        monkeypatch.setenv("DRYADE_PERSISTENT_CHECKPOINT_ENABLED", "true")
        cfg = get_orchestration_config()
        assert cfg.persistent_checkpoint_enabled is True
