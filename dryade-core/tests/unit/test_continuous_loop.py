"""Tests for core.orchestrator.continuous_loop -- Phase 115.5.

Covers feature flag dependency chain, tick skip logic, optimization
execution, scheduler lifecycle, and singleton.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from core.orchestrator.continuous_loop import (
    ContinuousOptimizationLoop,
    get_continuous_loop,
)
from core.orchestrator.optimization_pipeline import OptimizationResult

# ---- Helpers ----------------------------------------------------------------

def _make_config(**overrides):
    """Build a mock OrchestrationConfig with all flags enabled by default."""
    from types import SimpleNamespace

    defaults = {
        "optimization_enabled": True,
        "routing_metrics_enabled": True,
        "few_shot_enabled": True,
        "middleware_enabled": True,
        "prompt_versioning_enabled": True,
        "optimization_interval_minutes": 60,
        "optimization_min_metrics": 50,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)

def _make_loop(**kwargs) -> ContinuousOptimizationLoop:
    """Create a fresh ContinuousOptimizationLoop for testing."""
    defaults = {
        "interval_minutes": 60,
        "min_new_metrics": 50,
    }
    defaults.update(kwargs)
    return ContinuousOptimizationLoop(**defaults)

# ---- Feature flag checks ----------------------------------------------------
# get_orchestration_config is imported locally inside _check_feature_flags()
# from core.orchestrator.config, so we patch at the source module.

class TestCheckFeatureFlags:
    @patch("core.orchestrator.config.get_orchestration_config")
    def test_all_enabled(self, mock_cfg):
        mock_cfg.return_value = _make_config()
        loop = _make_loop()
        assert loop._check_feature_flags() is True

    @patch("core.orchestrator.config.get_orchestration_config")
    def test_optimization_disabled(self, mock_cfg):
        mock_cfg.return_value = _make_config(optimization_enabled=False)
        loop = _make_loop()
        assert loop._check_feature_flags() is False

    @patch("core.orchestrator.config.get_orchestration_config")
    def test_metrics_disabled(self, mock_cfg):
        mock_cfg.return_value = _make_config(routing_metrics_enabled=False)
        loop = _make_loop()
        assert loop._check_feature_flags() is False

    @patch("core.orchestrator.config.get_orchestration_config")
    def test_few_shot_disabled(self, mock_cfg):
        mock_cfg.return_value = _make_config(few_shot_enabled=False)
        loop = _make_loop()
        assert loop._check_feature_flags() is False

    @patch("core.orchestrator.config.get_orchestration_config")
    def test_middleware_disabled(self, mock_cfg):
        mock_cfg.return_value = _make_config(middleware_enabled=False)
        loop = _make_loop()
        assert loop._check_feature_flags() is False

# ---- Tick execution ----------------------------------------------------------

class TestTick:
    @patch("core.orchestrator.config.get_orchestration_config")
    def test_skips_when_flags_disabled(self, mock_cfg):
        mock_cfg.return_value = _make_config(optimization_enabled=False)
        loop = _make_loop()

        # Use asyncio.run() instead of get_event_loop().run_until_complete() to
        # avoid RuntimeError when prior async tests close the thread event loop.
        result = asyncio.run(loop.tick())
        assert result["status"] == "skipped"
        assert result["reason"] == "feature_flags_disabled"

    @patch("core.orchestrator.config.get_orchestration_config")
    def test_skips_insufficient_metrics(self, mock_cfg):
        mock_cfg.return_value = _make_config()
        loop = _make_loop(min_new_metrics=50)
        loop._last_optimization_run = datetime.now(UTC) - timedelta(hours=2)

        # Mock DB calls to return low metric count
        loop._count_metrics_since = lambda since: 10
        loop._get_last_run_from_db = lambda: None

        # Use asyncio.run() instead of get_event_loop().run_until_complete() to
        # avoid RuntimeError when prior async tests close the thread event loop.
        result = asyncio.run(loop.tick())
        assert result["status"] == "skipped"
        assert result["reason"] == "insufficient_metrics"
        assert result["metrics_found"] == 10
        assert result["min_required"] == 50

    @patch("core.orchestrator.config.get_orchestration_config")
    @patch("core.orchestrator.optimization_pipeline.get_routing_optimizer")
    def test_runs_optimization(self, mock_get_optimizer, mock_cfg):
        mock_cfg.return_value = _make_config()

        # Mock optimizer
        mock_optimizer = MagicMock()
        mock_optimizer.optimize.return_value = OptimizationResult(
            examples_added=3,
            examples_rejected=1,
            total_metrics_analyzed=100,
        )
        mock_get_optimizer.return_value = mock_optimizer

        loop = _make_loop(min_new_metrics=10)
        loop._last_optimization_run = datetime.now(UTC) - timedelta(hours=2)
        loop._count_metrics_since = lambda since: 100
        loop._get_last_run_from_db = lambda: None
        loop._persist_cycle_start = lambda *a: None
        loop._persist_cycle_end = lambda *a, **kw: None

        # Use asyncio.run() instead of get_event_loop().run_until_complete() to
        # avoid RuntimeError when prior async tests close the thread event loop.
        result = asyncio.run(loop.tick())
        assert result["status"] == "completed"
        assert result["examples_added"] == 3
        assert result["total_analyzed"] == 100
        mock_optimizer.optimize.assert_called_once()

# ---- Scheduler lifecycle -----------------------------------------------------
# The apscheduler imports are local inside start(), so we patch at source.

class TestStart:
    @patch("apscheduler.schedulers.asyncio.AsyncIOScheduler")
    def test_creates_scheduler(self, mock_scheduler_cls):
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler

        loop = _make_loop()
        loop.start()

        assert loop.is_running is True
        mock_scheduler.start.assert_called_once()

    @patch("apscheduler.schedulers.asyncio.AsyncIOScheduler")
    def test_stop(self, mock_scheduler_cls):
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler

        loop = _make_loop()
        loop.start()
        assert loop.is_running is True

        loop.stop()
        assert loop.is_running is False
        mock_scheduler.shutdown.assert_called_once()

# ---- Singleton ---------------------------------------------------------------

class TestSingleton:
    @patch("core.orchestrator.config.get_orchestration_config")
    def test_reads_config(self, mock_cfg):
        mock_cfg.return_value = _make_config(
            optimization_interval_minutes=30,
            optimization_min_metrics=25,
        )
        import core.orchestrator.continuous_loop as mod

        mod._loop = None
        loop = get_continuous_loop()
        assert loop._interval_minutes == 30
        assert loop._min_new_metrics == 25
        # Cleanup
        mod._loop = None
