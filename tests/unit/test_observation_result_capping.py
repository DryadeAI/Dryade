"""Tests for observation result size capping in _execute_single.

Validates that large tool outputs are truncated to obs_result_max_chars
before being stored in OrchestrationObservation.result, preventing
unbounded memory growth from 1MB+ tool outputs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.config import get_orchestration_config

def _cap_result(result_value, max_chars):
    """Replicate the capping logic from _execute_single for unit testing."""
    if result_value is not None:
        result_str = str(result_value) if not isinstance(result_value, str) else result_value
        if len(result_str) > max_chars:
            result_value = result_str[:max_chars] + f"... [truncated from {len(result_str)} chars]"
    return result_value

class TestResultCapping:
    """Tests for observation result size capping logic."""

    def test_small_result_not_capped(self):
        """Small results (under obs_result_max_chars) pass through unchanged."""
        config = get_orchestration_config()
        small_result = "x" * 100
        capped = _cap_result(small_result, config.obs_result_max_chars)
        assert capped == small_result
        assert "truncated" not in capped

    def test_large_string_result_capped(self):
        """String results exceeding obs_result_max_chars are truncated with a suffix."""
        config = get_orchestration_config()
        large_result = "x" * 100_000
        capped = _cap_result(large_result, config.obs_result_max_chars)

        assert len(capped) < len(large_result)
        assert capped.startswith("x" * 100)
        assert "... [truncated from 100000 chars]" in capped
        # The capped portion should be exactly max_chars + suffix
        expected = "x" * config.obs_result_max_chars + "... [truncated from 100000 chars]"
        assert capped == expected

    def test_large_dict_result_capped(self):
        """Dict results that exceed obs_result_max_chars when str()'d are converted and capped."""
        config = get_orchestration_config()
        # Create a dict whose str() representation exceeds max_chars
        large_dict = {"data": "y" * 100_000}
        capped = _cap_result(large_dict, config.obs_result_max_chars)

        assert isinstance(capped, str)
        assert "truncated" in capped
        # Verify it starts with the dict's string representation
        assert capped.startswith("{'data': '")

    def test_none_result_not_capped(self):
        """None results pass through without error or modification."""
        config = get_orchestration_config()
        capped = _cap_result(None, config.obs_result_max_chars)
        assert capped is None

    def test_custom_max_chars_via_env(self, monkeypatch):
        """obs_result_max_chars can be overridden via DRYADE_OBS_RESULT_MAX_CHARS env var."""
        monkeypatch.setenv("DRYADE_OBS_RESULT_MAX_CHARS", "1024")
        config = get_orchestration_config()
        assert config.obs_result_max_chars == 1024

        # Verify capping uses the custom value
        result = "z" * 2000
        capped = _cap_result(result, config.obs_result_max_chars)
        assert "truncated" in capped
        assert capped.startswith("z" * 1024)

    @pytest.mark.asyncio
    async def test_execute_single_caps_result(self):
        """Integration test: _execute_single caps large results in OrchestrationObservation."""
        from types import SimpleNamespace

        from core.orchestrator.models import OrchestrationObservation, OrchestrationTask
        from core.orchestrator.orchestrator import DryadeOrchestrator

        # Create a mock agent result using SimpleNamespace to avoid MagicMock
        # attribute propagation issues (MagicMock creates child mocks for any
        # attribute access, which breaks hasattr-based field extraction)
        large_result_value = "A" * 100_000
        mock_result = SimpleNamespace(
            result=large_result_value,
            status="ok",
            error=None,
        )

        mock_agent = AsyncMock()
        mock_agent.execute_with_context = AsyncMock(return_value=mock_result)
        mock_agent.execute = AsyncMock(return_value=mock_result)

        task = OrchestrationTask(
            agent_name="test_agent",
            description="test task",
        )

        # Create orchestrator with minimal setup.
        # __new__ skips __init__, so all lazy-init attrs must be set manually
        # to avoid AttributeError in property getters (e.g. _soft_failure_detector).
        orchestrator = DryadeOrchestrator.__new__(DryadeOrchestrator)
        orchestrator.agents = {"test_agent": mock_agent}
        orchestrator.logger = MagicMock()
        # Lazy-initialized sentinel values (set by __init__, used by property getters)
        orchestrator._soft_failure_detector = None
        orchestrator._circuit_breaker = None
        orchestrator._output_judge = None
        orchestrator._checkpoint_manager = None
        orchestrator._persistent_backend = None
        orchestrator._failure_history_store = None
        orchestrator._adaptive_retry = None
        orchestrator._pattern_detector = None
        orchestrator._failure_pipeline = None

        # Disable soft failure detection via env var so the synthetic result
        # (100K "A" chars) isn't flagged for zero keyword overlap with "test task".
        # Also disable middleware and vllm validation to reduce test surface.
        # OrchestrationConfig fields use validation_alias (DRYADE_* env vars).
        # patch.dict restores the original env var values after the with-block.
        with patch.dict(
            "os.environ",
            {
                "DRYADE_SOFT_FAILURE_DETECTION_ENABLED": "false",
                "DRYADE_MIDDLEWARE_ENABLED": "false",
                "DRYADE_VLLM_VALIDATOR_ENABLED": "false",
                "DRYADE_CHECKPOINT_ENABLED": "false",
            },
        ):
            obs = await orchestrator._execute_single(task, execution_id="test-exec-123", context={})

        assert isinstance(obs, OrchestrationObservation)
        assert obs.success is True
        # The result should be capped
        assert len(str(obs.result)) < 100_000
        assert "truncated from 100000 chars" in str(obs.result)
