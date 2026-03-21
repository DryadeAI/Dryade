"""Integration tests for soft failure detection wiring in orchestrator.

Verifies that SoftFailureDetector is correctly wired into _execute_single
and that detected soft failures flip is_success=False, trigger the existing
retry/classification machinery, and respect the feature flag.

Plan: 118.4-02
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.orchestrator.config import get_orchestration_config
from core.orchestrator.models import OrchestrationObservation, OrchestrationTask
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.soft_failure_detector import ExecutionTracker, SoftFailureDetector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator():
    """Minimal DryadeOrchestrator with a mock agent."""
    o = DryadeOrchestrator.__new__(DryadeOrchestrator)
    o.agents = {}
    o._soft_failure_detector = None
    o._circuit_breaker = None
    return o

@pytest.fixture
def mock_agent_ok():
    """Agent that returns a successful result with real content."""
    result = SimpleNamespace(
        result="Here are the search results for your query about Python web frameworks.",
        status="ok",
        error=None,
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    return agent

@pytest.fixture
def mock_agent_empty():
    """Agent that returns a successful status but None result."""
    result = SimpleNamespace(
        result=None,
        status="ok",
        error=None,
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    return agent

@pytest.fixture
def mock_agent_truncated():
    """Agent that returns truncated JSON (unclosed brackets, >50 chars)."""
    # Unclosed JSON padded to >50 chars to trigger truncation check
    truncated_json = '{"results": [{"id": 1, "name": "item_one"}, {"id": 2, "name": "item_tw'
    result = SimpleNamespace(
        result=truncated_json,
        status="ok",
        error=None,
    )
    agent = AsyncMock()
    agent.execute_with_context = AsyncMock(return_value=result)
    return agent

def _default_config(**overrides):
    """Create a default config with optional overrides."""
    cfg = get_orchestration_config()
    for k, v in overrides.items():
        object.__setattr__(cfg, k, v)
    return cfg

def _make_task(tool="search_web", args=None):
    """Create a simple OrchestrationTask."""
    return OrchestrationTask(
        agent_name="test_agent",
        description="Search for Python web frameworks and return a summary",
        tool=tool,
        arguments=args or {"query": "python web frameworks"},
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSoftFailureIntegration:
    """Integration tests for soft failure detection wiring in orchestrator."""

    @pytest.mark.asyncio
    async def test_execute_single_empty_result_detected(self, orchestrator, mock_agent_empty):
        """Empty (None) result on successful status triggers soft failure."""
        orchestrator.agents["test_agent"] = mock_agent_empty
        task = _make_task()

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-001",
                context={},
            )

        assert isinstance(obs, OrchestrationObservation)
        assert obs.success is False
        assert "empty_result" in (obs.error or "")

    @pytest.mark.asyncio
    async def test_execute_single_valid_result_passes(self, orchestrator, mock_agent_ok):
        """Valid non-empty result passes soft failure detection unscathed."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task()

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-002",
                context={},
            )

        assert isinstance(obs, OrchestrationObservation)
        assert obs.success is True
        assert obs.error is None

    @pytest.mark.asyncio
    async def test_execute_single_soft_failure_disabled(self, orchestrator, mock_agent_empty):
        """When feature flag is False, soft failure detection is skipped."""
        orchestrator.agents["test_agent"] = mock_agent_empty
        task = _make_task()

        cfg = _default_config(soft_failure_detection_enabled=False)
        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=cfg,
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-003",
                context={},
            )

        # With detection disabled, None result on "ok" status = success
        assert obs.success is True
        assert obs.error is None

    @pytest.mark.asyncio
    async def test_execution_tracker_records_calls(self, orchestrator, mock_agent_ok):
        """ExecutionTracker accumulates records across multiple _execute_single calls."""
        orchestrator.agents["test_agent"] = mock_agent_ok
        task = _make_task(tool="search_web", args={"query": "python"})
        tracker = ExecutionTracker()

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            for _ in range(3):
                await orchestrator._execute_single(
                    task,
                    execution_id="test-004",
                    context={},
                    execution_tracker=tracker,
                )

        # Tracker should have 3 records of the same tool+args
        assert tracker.count("search_web", {"query": "python"}) == 3

    @pytest.mark.asyncio
    async def test_loop_detection_triggers_on_repeated_calls(self, orchestrator):
        """Loop detection fires when same tool+args executed 3+ times with empty-ish results."""
        # Agent returns non-empty result (so empty_result doesn't fire first),
        # but the loop detector should still trigger on the 3rd identical call
        result = SimpleNamespace(
            result="Some valid-looking result content that is long enough to pass all checks.",
            status="ok",
            error=None,
        )
        agent = AsyncMock()
        agent.execute_with_context = AsyncMock(return_value=result)
        orchestrator.agents["test_agent"] = agent

        task = _make_task(tool="search_web", args={"query": "same_query"})

        # Pre-load tracker with 2 identical calls (simulating prior executions)
        tracker = ExecutionTracker()
        tracker.record("search_web", {"query": "same_query"})
        tracker.record("search_web", {"query": "same_query"})

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            # 3rd call should trigger loop detection (record happens before detect)
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-005",
                context={},
                execution_tracker=tracker,
            )

        assert obs.success is False
        assert "loop_detected" in (obs.error or "")

    @pytest.mark.asyncio
    async def test_truncation_detected_in_pipeline(self, orchestrator, mock_agent_truncated):
        """Truncated JSON result is caught by soft failure detection."""
        orchestrator.agents["test_agent"] = mock_agent_truncated
        task = _make_task()

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-006",
                context={},
            )

        assert obs.success is False
        assert "truncation" in (obs.error or "")

    @pytest.mark.asyncio
    async def test_soft_failure_detector_property(self):
        """soft_failure_detector lazy property creates SoftFailureDetector."""
        o = DryadeOrchestrator.__new__(DryadeOrchestrator)
        o._soft_failure_detector = None

        detector = o.soft_failure_detector
        assert isinstance(detector, SoftFailureDetector)

        # Same instance on second access (cached)
        detector2 = o.soft_failure_detector
        assert detector is detector2

    @pytest.mark.asyncio
    async def test_tracker_records_failures_too(self, orchestrator):
        """Tracker records tool calls even when agent execution fails (is_success=False)."""
        # Agent returns failure status
        result = SimpleNamespace(
            result=None,
            status="error",
            error="connection refused",
        )
        agent = AsyncMock()
        agent.execute_with_context = AsyncMock(return_value=result)
        orchestrator.agents["test_agent"] = agent

        task = _make_task(tool="failing_tool", args={"key": "val"})
        tracker = ExecutionTracker()

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-007",
                context={},
                execution_tracker=tracker,
            )

        # Even though execution failed, the tracker should have recorded the call
        assert tracker.count("failing_tool", {"key": "val"}) == 1
        # The result itself should be a failure (from the agent, not soft failure)
        assert obs.success is False

    @pytest.mark.asyncio
    async def test_feature_flag_env_override(self, monkeypatch):
        """DRYADE_SOFT_FAILURE_DETECTION_ENABLED=false disables detection via env."""
        monkeypatch.setenv("DRYADE_SOFT_FAILURE_DETECTION_ENABLED", "false")
        cfg = get_orchestration_config()
        assert cfg.soft_failure_detection_enabled is False

    @pytest.mark.asyncio
    async def test_size_anomaly_detected_in_pipeline(self, orchestrator):
        """Very small suspicious result triggers size_anomaly soft failure."""
        # Result is "hi" -- 2 chars, not in valid_short_responses
        result = SimpleNamespace(
            result="hi",
            status="ok",
            error=None,
        )
        agent = AsyncMock()
        agent.execute_with_context = AsyncMock(return_value=result)
        orchestrator.agents["test_agent"] = agent

        task = _make_task()

        with patch(
            "core.orchestrator.orchestrator.get_orchestration_config",
            return_value=_default_config(),
        ):
            obs = await orchestrator._execute_single(
                task,
                execution_id="test-008",
                context={},
            )

        assert obs.success is False
        assert "size_anomaly" in (obs.error or "")
