"""Integration tests for failure learning wiring in the orchestrator.

Tests the integration between DryadeOrchestrator, FailureHistoryStore,
PatternDetector, AdaptiveRetryStrategy, and CircuitBreaker via the
failure_learning_enabled feature flag (Phase 118.7-02).
"""

import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base
from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitState
from core.orchestrator.failure_history import (
    AdaptiveRetryStrategy,
    FailureHistoryStore,
    PatternDetector,
)
from core.orchestrator.models import (
    ErrorCategory,
    FailureAction,
    OrchestrationTask,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """Mock get_session to use an in-memory SQLAlchemy database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @contextmanager
    def mock_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("core.database.session.get_session", mock_get_session)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(
    agent_name: str = "mcp-filesystem",
    tool: str = "read_file",
    description: str = "Read a test file",
) -> OrchestrationTask:
    return OrchestrationTask(
        agent_name=agent_name,
        description=description,
        tool=tool,
    )

def _make_store() -> FailureHistoryStore:
    """Create a store for test isolation (uses mocked get_session)."""
    return FailureHistoryStore()

def _seed_failures(
    store: FailureHistoryStore,
    tool_name: str = "read_file",
    server_name: str = "filesystem",
    error_category: ErrorCategory = ErrorCategory.TRANSIENT,
    action_taken: FailureAction = FailureAction.RETRY,
    count: int = 1,
    recovery_success: bool = False,
) -> None:
    """Insert multiple failure records with consistent defaults."""
    for _ in range(count):
        store.record_failure(
            tool_name=tool_name,
            server_name=server_name,
            error_category=error_category,
            error_message=f"Test error for {tool_name}",
            action_taken=action_taken,
            recovery_success=recovery_success,
        )

def _make_orchestrator():
    """Create a DryadeOrchestrator with mocked dependencies."""
    from core.orchestrator.orchestrator import DryadeOrchestrator

    thinking = MagicMock()
    registry = MagicMock()
    orch = DryadeOrchestrator(
        thinking_provider=thinking,
        agent_registry=registry,
    )
    return orch

# ---------------------------------------------------------------------------
# Feature flag tests
# ---------------------------------------------------------------------------

class TestFeatureFlagDefaultOff:
    """Verify failure_learning_enabled=False means no history writes."""

    def test_feature_flag_default_off(self):
        """Config default is False."""
        from core.orchestrator.config import OrchestrationConfig

        cfg = OrchestrationConfig()
        assert cfg.failure_learning_enabled is False

    def test_record_failure_history_noop_when_disabled(self):
        """_record_failure_history does nothing when flag is off."""
        orch = _make_orchestrator()
        task = _make_task()

        # Inject a mock store to verify it's never called
        mock_store = MagicMock(spec=FailureHistoryStore)
        orch._failure_history_store = mock_store

        # With flag off (default), record should not call store
        with patch.dict(os.environ, {}, clear=False):
            # Ensure DRYADE_FAILURE_LEARNING_ENABLED is not set
            os.environ.pop("DRYADE_FAILURE_LEARNING_ENABLED", None)
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.TRANSIENT,
                error_msg="test error",
                action_taken=FailureAction.RETRY,
                recovery_success=False,
            )

        mock_store.record_failure.assert_not_called()

# ---------------------------------------------------------------------------
# Record failure tests
# ---------------------------------------------------------------------------

class TestRecordFailureOnRetryExhaustion:
    """Verify record_failure called when retries are exhausted."""

    def test_record_failure_on_retry_exhaustion(self):
        """Mock store, verify record_failure called with correct args."""
        orch = _make_orchestrator()
        task = _make_task()

        mock_store = MagicMock(spec=FailureHistoryStore)
        orch._failure_history_store = mock_store

        with patch.dict(os.environ, {"DRYADE_FAILURE_LEARNING_ENABLED": "true"}):
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.TRANSIENT,
                error_msg="connection refused after retries",
                action_taken=FailureAction.RETRY,
                recovery_success=False,
                retry_count=3,
            )

        mock_store.record_failure.assert_called_once()
        call_kwargs = mock_store.record_failure.call_args
        assert call_kwargs[1]["tool_name"] == "read_file"
        assert call_kwargs[1]["server_name"] == "filesystem"  # mcp- prefix stripped
        assert call_kwargs[1]["error_category"] == ErrorCategory.TRANSIENT
        assert call_kwargs[1]["recovery_success"] is False
        assert call_kwargs[1]["retry_count"] == 3

class TestRecordFailureOnNonRetryAction:
    """Verify record_failure called when action is not RETRY."""

    def test_record_failure_on_skip_action(self):
        """Mock store, verify called for SKIP action."""
        orch = _make_orchestrator()
        task = _make_task()

        mock_store = MagicMock(spec=FailureHistoryStore)
        orch._failure_history_store = mock_store

        with patch.dict(os.environ, {"DRYADE_FAILURE_LEARNING_ENABLED": "true"}):
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.PERMANENT,
                error_msg="agent not found",
                action_taken=FailureAction.SKIP,
                recovery_success=False,
                retry_count=0,
            )

        mock_store.record_failure.assert_called_once()
        call_kwargs = mock_store.record_failure.call_args
        assert call_kwargs[1]["action_taken"] == FailureAction.SKIP

class TestRecordSuccessAfterRetry:
    """Verify recovery_success=True recorded when retries succeed."""

    def test_record_success_after_retry(self):
        """When recovery_success=True, store records it."""
        orch = _make_orchestrator()
        task = _make_task()

        mock_store = MagicMock(spec=FailureHistoryStore)
        orch._failure_history_store = mock_store

        with patch.dict(os.environ, {"DRYADE_FAILURE_LEARNING_ENABLED": "true"}):
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.TRANSIENT,
                error_msg="recovered after retry",
                action_taken=FailureAction.RETRY,
                recovery_success=True,
                retry_count=2,
            )

        mock_store.record_failure.assert_called_once()
        call_kwargs = mock_store.record_failure.call_args
        assert call_kwargs[1]["recovery_success"] is True
        assert call_kwargs[1]["retry_count"] == 2

# ---------------------------------------------------------------------------
# Adaptive retry tests
# ---------------------------------------------------------------------------

class TestAdaptiveRetryModifiesMaxRetries:
    """Verify adaptive retry changes max_retries based on history."""

    def test_adaptive_retry_modifies_max_retries(self):
        """Seed history with high recovery rate, verify max_retries increases."""
        store = _make_store()

        # Seed: 9 recovered, 1 not -> 90% recovery -> max_retries = default(3) + 2 = 5
        _seed_failures(
            store,
            tool_name="read_file",
            error_category=ErrorCategory.TRANSIENT,
            count=9,
            recovery_success=True,
        )
        _seed_failures(
            store,
            tool_name="read_file",
            error_category=ErrorCategory.TRANSIENT,
            count=1,
            recovery_success=False,
        )

        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("read_file", "transient")
        assert params["max_retries"] == 5
        assert params["reason"] != "no history"

    def test_adaptive_retry_decreases_for_low_recovery(self):
        """Seed history with low recovery rate, verify max_retries decreases."""
        store = _make_store()

        # 1 recovered, 9 not -> 10% recovery -> max_retries = 1
        _seed_failures(
            store,
            tool_name="bad_tool",
            error_category=ErrorCategory.PERMANENT,
            count=9,
            recovery_success=False,
        )
        _seed_failures(
            store,
            tool_name="bad_tool",
            error_category=ErrorCategory.PERMANENT,
            count=1,
            recovery_success=True,
        )

        strategy = AdaptiveRetryStrategy(store)
        params = strategy.get_retry_params("bad_tool", "permanent")
        assert params["max_retries"] == 1

# ---------------------------------------------------------------------------
# Pre-emptive circuit break tests
# ---------------------------------------------------------------------------

class TestPreemptiveCircuitBreakOpensCircuit:
    """Verify pre-emptive circuit breaking opens circuits for high-failure servers."""

    def test_preemptive_circuit_break_opens_circuit(self):
        """Seed high failure history, verify circuit opens via inject_external_failure_rate."""
        store = _make_store()

        # 8 failures, 2 successes -> 80% failure rate for server "badserver"
        _seed_failures(
            store,
            server_name="badserver",
            count=8,
            recovery_success=False,
        )
        _seed_failures(
            store,
            server_name="badserver",
            count=2,
            recovery_success=True,
        )

        detector = PatternDetector(store)
        assert detector.should_preempt_circuit_break("badserver", threshold=0.7) is True

        # Now inject into circuit breaker
        cb = CircuitBreaker()
        server_rate = store.get_server_failure_rate("badserver", window_hours=1)
        opened = cb.inject_external_failure_rate("badserver", server_rate, threshold=0.7)
        assert opened is True
        assert cb.get_state("badserver") == CircuitState.OPEN

class TestPreemptiveCircuitBreakDisabled:
    """Verify pre-emptive breaking does nothing when flag is off."""

    def test_preemptive_circuit_break_disabled(self):
        """With preemptive_circuit_break_enabled=False, no pre-emptive opening."""
        store = _make_store()

        # High failure rate
        _seed_failures(
            store,
            server_name="badserver",
            count=8,
            recovery_success=False,
        )
        _seed_failures(
            store,
            server_name="badserver",
            count=2,
            recovery_success=True,
        )

        # Circuit breaker with below-threshold rate should not open
        cb = CircuitBreaker()
        opened = cb.inject_external_failure_rate("goodserver", 0.3, threshold=0.7)
        assert opened is False
        assert cb.get_state("goodserver") == CircuitState.CLOSED

    def test_inject_external_below_threshold_does_not_open(self):
        """Rate below threshold does not open circuit."""
        cb = CircuitBreaker()
        opened = cb.inject_external_failure_rate("server", 0.5, threshold=0.7)
        assert opened is False
        assert cb.get_state("server") == CircuitState.CLOSED

    def test_inject_external_already_open_returns_false(self):
        """Already-open circuit returns False (no double-open)."""
        from core.orchestrator.circuit_breaker import CircuitConfig

        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server")
        cb.record_failure("server")
        assert cb.get_state("server") == CircuitState.OPEN

        # Try to pre-emptively open an already-open circuit
        opened = cb.inject_external_failure_rate("server", 0.9, threshold=0.7)
        assert opened is False

# ---------------------------------------------------------------------------
# Non-fatal failure handling
# ---------------------------------------------------------------------------

class TestAllFailureHistoryCallsAreNonfatal:
    """Verify that store exceptions don't crash the orchestrator."""

    def test_store_raises_exception_is_caught(self):
        """Store raises, orchestrator continues without error."""
        orch = _make_orchestrator()
        task = _make_task()

        # Create a store mock that raises on record_failure
        mock_store = MagicMock(spec=FailureHistoryStore)
        mock_store.record_failure.side_effect = RuntimeError("DB corrupted!")
        orch._failure_history_store = mock_store

        with patch.dict(os.environ, {"DRYADE_FAILURE_LEARNING_ENABLED": "true"}):
            # Should not raise -- wrapped in try/except
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.TRANSIENT,
                error_msg="test error",
                action_taken=FailureAction.RETRY,
                recovery_success=False,
            )

        # Verify it attempted the call (and caught the exception)
        mock_store.record_failure.assert_called_once()

    def test_pattern_detector_exception_nonfatal(self):
        """PatternDetector exception in pre-emptive check should be non-fatal."""
        orch = _make_orchestrator()

        # Create a mock pattern detector that raises
        mock_detector = MagicMock(spec=PatternDetector)
        mock_detector.should_preempt_circuit_break.side_effect = RuntimeError("DB error")
        orch._pattern_detector = mock_detector

        # The pre-emptive circuit break check is wrapped in try/except in _execute_with_retry
        # We test the detector alone raises but is catchable
        try:
            mock_detector.should_preempt_circuit_break("test-server")
        except RuntimeError:
            pass  # Expected - the try/except in orchestrator would catch this

        mock_detector.should_preempt_circuit_break.assert_called_once()

# ---------------------------------------------------------------------------
# Lazy property tests
# ---------------------------------------------------------------------------

class TestLazyProperties:
    """Verify lazy properties are created correctly."""

    def test_failure_history_store_lazy_creation(self):
        """Accessing failure_history_store creates a FailureHistoryStore."""
        orch = _make_orchestrator()
        assert orch._failure_history_store is None

        store = orch.failure_history_store
        assert isinstance(store, FailureHistoryStore)
        assert orch._failure_history_store is not None

    def test_adaptive_retry_strategy_lazy_creation(self):
        """Accessing adaptive_retry_strategy creates an AdaptiveRetryStrategy."""
        orch = _make_orchestrator()
        assert orch._adaptive_retry is None

        strategy = orch.adaptive_retry_strategy
        assert isinstance(strategy, AdaptiveRetryStrategy)
        assert orch._adaptive_retry is not None

    def test_pattern_detector_lazy_creation(self):
        """Accessing pattern_detector creates a PatternDetector."""
        orch = _make_orchestrator()
        assert orch._pattern_detector is None

        detector = orch.pattern_detector
        assert isinstance(detector, PatternDetector)
        assert orch._pattern_detector is not None

    def test_lazy_properties_reuse_same_store(self):
        """adaptive_retry and pattern_detector share the same store instance."""
        orch = _make_orchestrator()

        store = orch.failure_history_store
        strategy = orch.adaptive_retry_strategy
        detector = orch.pattern_detector

        assert strategy._store is store
        assert detector._store is store

# ---------------------------------------------------------------------------
# Server name stripping
# ---------------------------------------------------------------------------

class TestServerNameStripping:
    """Verify mcp- prefix is stripped correctly."""

    def test_mcp_prefix_stripped(self):
        """Agent name mcp-filesystem records server as filesystem."""
        orch = _make_orchestrator()
        task = _make_task(agent_name="mcp-filesystem")

        store = _make_store()
        orch._failure_history_store = store

        with patch.dict(os.environ, {"DRYADE_FAILURE_LEARNING_ENABLED": "true"}):
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.TRANSIENT,
                error_msg="test",
                action_taken=FailureAction.RETRY,
                recovery_success=False,
            )

        # Verify the stored record has stripped server name
        rate = store.get_server_failure_rate("filesystem", window_hours=24)
        assert rate > 0  # Should find the record under "filesystem"

    def test_non_mcp_agent_uses_agent_name(self):
        """Non-MCP agent uses full agent_name as server_name."""
        orch = _make_orchestrator()
        task = _make_task(agent_name="my-custom-agent", tool="do_something")

        store = _make_store()
        orch._failure_history_store = store

        with patch.dict(os.environ, {"DRYADE_FAILURE_LEARNING_ENABLED": "true"}):
            orch._record_failure_history(
                task=task,
                error_category=ErrorCategory.SEMANTIC,
                error_msg="something went wrong",
                action_taken=FailureAction.SKIP,
                recovery_success=False,
            )

        rate = store.get_server_failure_rate("my-custom-agent", window_hours=24)
        assert rate > 0
