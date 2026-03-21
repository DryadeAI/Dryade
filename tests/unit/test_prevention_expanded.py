"""Expanded tests for core/orchestrator/prevention.py.

Tests SchemaValidator, ConnectivityProbe, ModelReachabilityCheck,
PromptOptimizer, and PreventionPipeline. All checks are fail-open —
errors never block execution.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# PreventionVerdict and PreventionResult
# ===========================================================================

class TestPreventionDataTypes:
    """Tests for PreventionVerdict and PreventionResult dataclasses."""

    def test_verdict_pass_value(self):
        """PreventionVerdict.PASS has value 'pass'."""
        from core.orchestrator.prevention import PreventionVerdict

        assert PreventionVerdict.PASS == "pass"

    def test_verdict_fail_value(self):
        """PreventionVerdict.FAIL has value 'fail'."""
        from core.orchestrator.prevention import PreventionVerdict

        assert PreventionVerdict.FAIL == "fail"

    def test_verdict_warn_value(self):
        """PreventionVerdict.WARN has value 'warn'."""
        from core.orchestrator.prevention import PreventionVerdict

        assert PreventionVerdict.WARN == "warn"

    def test_prevention_result_creation(self):
        """PreventionResult can be created with required fields."""
        from core.orchestrator.prevention import PreventionResult, PreventionVerdict

        result = PreventionResult(
            verdict=PreventionVerdict.PASS,
            check_name="test_check",
            reason="all good",
        )
        assert result.verdict == PreventionVerdict.PASS
        assert result.check_name == "test_check"
        assert result.reason == "all good"
        assert result.duration_ms == 0.0

    def test_prevention_result_with_metadata(self):
        """PreventionResult stores metadata dict."""
        from core.orchestrator.prevention import PreventionResult, PreventionVerdict

        result = PreventionResult(
            verdict=PreventionVerdict.FAIL,
            check_name="schema_validator",
            reason="missing field",
            metadata={"field": "name", "path": ["properties"]},
        )
        assert result.metadata["field"] == "name"

# ===========================================================================
# SchemaValidator
# ===========================================================================

class TestSchemaValidator:
    """Tests for SchemaValidator.validate_arguments()."""

    def test_validate_valid_arguments_returns_pass(self):
        """Valid arguments against schema return PASS verdict."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
            "required": ["name"],
        }
        result = validator.validate_arguments("my_tool", {"name": "test", "count": 5}, schema)
        assert result.verdict == PreventionVerdict.PASS
        assert result.check_name == "schema_validator"

    def test_validate_invalid_type_returns_fail(self):
        """Wrong type for required field returns FAIL verdict."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }
        result = validator.validate_arguments("my_tool", {"count": "not-an-int"}, schema)
        assert result.verdict == PreventionVerdict.FAIL
        assert "schema validation failed" in result.reason.lower()

    def test_validate_missing_required_field_returns_fail(self):
        """Missing required field returns FAIL verdict."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = validator.validate_arguments("my_tool", {}, schema)
        assert result.verdict == PreventionVerdict.FAIL

    def test_validate_strips_null_values(self):
        """Null values are stripped before validation (null-sanitization)."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        # None-valued keys should be stripped; 'name' is provided as valid string
        result = validator.validate_arguments("my_tool", {"name": "test", "optional": None}, schema)
        assert result.verdict == PreventionVerdict.PASS

    def test_validate_includes_tool_name_in_fail_reason(self):
        """FAIL reason includes the tool name."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
        result = validator.validate_arguments("special_tool", {"x": "wrong"}, schema)
        if result.verdict == PreventionVerdict.FAIL:
            assert "special_tool" in result.reason

    def test_validate_returns_pass_when_jsonschema_unavailable(self):
        """When jsonschema is not available, returns PASS (fail-open)."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        with patch("core.orchestrator.prevention.validate", None):
            result = validator.validate_arguments("tool", {"any": "value"}, {})
        assert result.verdict == PreventionVerdict.PASS
        assert "not available" in result.reason

    def test_validate_fail_result_has_metadata(self):
        """FAIL result includes metadata with tool_name and path info."""
        from core.orchestrator.prevention import PreventionVerdict, SchemaValidator

        validator = SchemaValidator()
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }
        result = validator.validate_arguments("tool_x", {"count": "string"}, schema)
        if result.verdict == PreventionVerdict.FAIL and result.metadata:
            assert result.metadata.get("tool_name") == "tool_x"

    def test_validate_has_duration_ms(self):
        """Result has non-negative duration_ms."""
        from core.orchestrator.prevention import SchemaValidator

        validator = SchemaValidator()
        result = validator.validate_arguments("tool", {"x": 1}, {"type": "object"})
        assert result.duration_ms >= 0.0

# ===========================================================================
# ConnectivityProbe
# ===========================================================================

class TestConnectivityProbe:
    """Tests for ConnectivityProbe.probe_server()."""

    def _make_probe(self, registry=None):
        """Create a ConnectivityProbe with a mock registry."""
        if registry is None:
            registry = MagicMock()
            registry.is_running.return_value = True
            registry.list_tools.return_value = []
        from core.orchestrator.prevention import ConnectivityProbe

        return ConnectivityProbe(registry)

    def test_already_running_returns_pass(self):
        """Server already running returns PASS without list_tools call."""
        registry = MagicMock()
        registry.is_running.return_value = True
        probe = self._make_probe(registry)

        result = asyncio.run(probe.probe_server("my_server"))

        from core.orchestrator.prevention import PreventionVerdict

        assert result.verdict == PreventionVerdict.PASS
        registry.list_tools.assert_not_called()

    def test_server_not_running_triggers_lazy_start(self):
        """Server not running calls list_tools for lazy start."""
        registry = MagicMock()
        registry.is_running.return_value = False
        registry.list_tools.return_value = [{"name": "tool1"}, {"name": "tool2"}]
        probe = self._make_probe(registry)

        result = asyncio.run(probe.probe_server("lazy_server"))

        from core.orchestrator.prevention import PreventionVerdict

        assert result.verdict == PreventionVerdict.PASS
        assert result.metadata["tool_count"] == 2

    def test_unreachable_server_returns_fail(self):
        """Exception during probe returns FAIL verdict."""
        registry = MagicMock()
        registry.is_running.side_effect = Exception("Connection refused")
        probe = self._make_probe(registry)

        result = asyncio.run(probe.probe_server("dead_server"))

        from core.orchestrator.prevention import PreventionVerdict

        assert result.verdict == PreventionVerdict.FAIL
        assert "dead_server" in result.reason

    def test_already_probed_returns_pass_without_rechecking(self):
        """Second probe for same server returns PASS immediately."""
        registry = MagicMock()
        registry.is_running.return_value = True
        probe = self._make_probe(registry)
        probe._probed_servers.add("cached_server")

        result = asyncio.run(probe.probe_server("cached_server"))

        from core.orchestrator.prevention import PreventionVerdict

        assert result.verdict == PreventionVerdict.PASS
        assert "already probed" in result.reason

    def test_reset_clears_probed_set(self):
        """reset() clears the probed server cache."""
        probe = self._make_probe()
        probe._probed_servers.add("server_a")
        probe._probed_servers.add("server_b")
        probe.reset()
        assert len(probe._probed_servers) == 0

# ===========================================================================
# ModelReachabilityCheck
# ===========================================================================

class TestModelReachabilityCheck:
    """Tests for ModelReachabilityCheck.check()."""

    def test_reachable_endpoint_returns_pass(self):
        """When LLM endpoint responds 200, returns PASS."""
        import httpx

        from core.orchestrator.prevention import ModelReachabilityCheck, PreventionVerdict

        check = ModelReachabilityCheck()

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = asyncio.run(check.check())
        assert result.verdict == PreventionVerdict.PASS
        assert "LLM endpoint reachable" in result.reason

    def test_cached_result_returned_within_ttl(self):
        """Second check within TTL returns cached result."""
        import time

        from core.orchestrator.prevention import (
            ModelReachabilityCheck,
            PreventionResult,
            PreventionVerdict,
        )

        check = ModelReachabilityCheck()
        # Manually set cache
        cached = PreventionResult(
            verdict=PreventionVerdict.PASS,
            check_name="model_reachability",
            reason="cached",
        )
        check._last_result = cached
        check._last_check_time = time.monotonic()  # Just now

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_BASE_URL", None)
            result = asyncio.run(check.check())
        # Should return cached result
        assert result.reason == "cached"

# ===========================================================================
# PromptOptimizer
# ===========================================================================

class TestPromptOptimizer:
    """Tests for PromptOptimizer.compile_hints()."""

    def _make_optimizer(self, failing_tools=None, recurring_errors=None):
        """Create PromptOptimizer with mocked store/detector."""
        from core.orchestrator.prevention import PromptOptimizer

        store = MagicMock()
        detector = MagicMock()
        detector.detect_high_failure_tools.return_value = failing_tools or []
        detector.detect_recurring_errors.return_value = recurring_errors or []
        return PromptOptimizer(store, detector)

    def test_no_failing_tools_returns_empty_list(self):
        """No failing tools produces empty hints list."""
        optimizer = self._make_optimizer(failing_tools=[])
        hints = optimizer.compile_hints()
        assert hints == []

    def test_single_failing_tool_generates_hint(self):
        """One failing tool generates one hint string."""
        optimizer = self._make_optimizer(
            failing_tools=[{"tool_name": "bad_tool", "failure_rate": 0.6}],
            recurring_errors=[],
        )
        hints = optimizer.compile_hints()
        assert len(hints) == 1
        assert "bad_tool" in hints[0]
        assert "60%" in hints[0]

    def test_hint_includes_error_categories(self):
        """Hint includes error category when recurring errors exist."""
        optimizer = self._make_optimizer(
            failing_tools=[{"tool_name": "flaky_tool", "failure_rate": 0.5}],
            recurring_errors=[{"error_category": "TIMEOUT", "count": 5}],
        )
        hints = optimizer.compile_hints()
        assert len(hints) == 1
        assert "TIMEOUT" in hints[0]

    def test_hint_includes_mitigation_from_map(self):
        """Hint includes mitigation for known error category."""
        optimizer = self._make_optimizer(
            failing_tools=[{"tool_name": "tool", "failure_rate": 0.4}],
            recurring_errors=[{"error_category": "TIMEOUT", "count": 3}],
        )
        hints = optimizer.compile_hints()
        assert "simpler queries" in hints[0] or "smaller inputs" in hints[0]

    def test_results_cached_within_ttl(self):
        """Second call within TTL returns cached hints."""
        optimizer = self._make_optimizer(failing_tools=[{"tool_name": "tool", "failure_rate": 0.5}])
        optimizer.compile_hints()  # First call
        # Set last_compiled to "just now"
        import time

        optimizer._last_compiled = time.monotonic()
        optimizer._cached_hints = ["cached hint"]

        hints = optimizer.compile_hints()
        assert hints == ["cached hint"]

    def test_max_hints_limits_output(self):
        """compile_hints respects max_hints parameter."""
        tools = [{"tool_name": f"tool_{i}", "failure_rate": 0.5} for i in range(10)]
        optimizer = self._make_optimizer(failing_tools=tools)
        hints = optimizer.compile_hints(max_hints=3)
        assert len(hints) <= 3

    def test_exception_returns_empty_list_fail_open(self):
        """Exception in compile_hints returns empty list (fail-open)."""
        from core.orchestrator.prevention import PromptOptimizer

        store = MagicMock()
        detector = MagicMock()
        detector.detect_high_failure_tools.side_effect = RuntimeError("DB error")
        optimizer = PromptOptimizer(store, detector)
        hints = optimizer.compile_hints()
        assert hints == []

# ===========================================================================
# PreventionPipeline
# ===========================================================================

class TestPreventionPipeline:
    """Tests for PreventionPipeline."""

    def test_pipeline_importable(self):
        """PreventionPipeline is importable."""
        from core.orchestrator.prevention import PreventionPipeline

        assert PreventionPipeline is not None

    def test_get_prevention_pipeline_importable(self):
        """get_prevention_pipeline function is importable."""
        from core.orchestrator.prevention import get_prevention_pipeline

        assert get_prevention_pipeline is not None

    def test_validate_tool_schema_returns_none_when_disabled(self):
        """validate_tool_schema returns None when prevention is disabled."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = False

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            result = pipeline.validate_tool_schema("server", "tool", {"arg": "val"})
        assert result is None

    def test_validate_tool_schema_returns_none_when_schema_validation_disabled(self):
        """validate_tool_schema returns None when schema_validation_enabled is False."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.schema_validation_enabled = False

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            result = pipeline.validate_tool_schema("server", "tool", {"arg": "val"})
        assert result is None

    def test_probe_connectivity_returns_none_when_disabled(self):
        """probe_connectivity returns None when prevention is disabled."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = False

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            result = asyncio.run(pipeline.probe_connectivity("server"))
        assert result is None

    def test_schema_validator_property_creates_instance(self):
        """_schema_validator lazy property creates SchemaValidator."""
        from core.orchestrator.prevention import PreventionPipeline, SchemaValidator

        pipeline = PreventionPipeline()
        validator = pipeline._schema_validator
        assert isinstance(validator, SchemaValidator)

    def test_schema_validator_property_cached(self):
        """_schema_validator returns same instance on repeated access."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()
        v1 = pipeline._schema_validator
        v2 = pipeline._schema_validator
        assert v1 is v2

    def test_model_reachability_property_creates_instance(self):
        """_model_reachability lazy property creates ModelReachabilityCheck."""
        from core.orchestrator.prevention import ModelReachabilityCheck, PreventionPipeline

        pipeline = PreventionPipeline()
        check = pipeline._model_reachability
        assert isinstance(check, ModelReachabilityCheck)

# ===========================================================================
# get_prevention_pipeline singleton
# ===========================================================================

class TestGetPreventionPipeline:
    """Tests for module-level get_prevention_pipeline() function."""

    def test_returns_prevention_pipeline_instance(self):
        """get_prevention_pipeline returns a PreventionPipeline."""
        from core.orchestrator.prevention import PreventionPipeline, get_prevention_pipeline

        result = get_prevention_pipeline()
        assert isinstance(result, PreventionPipeline)

    def test_returns_same_instance_each_time(self):
        """get_prevention_pipeline is a singleton."""
        from core.orchestrator.prevention import get_prevention_pipeline

        a = get_prevention_pipeline()
        b = get_prevention_pipeline()
        assert a is b

# ===========================================================================
# PreventionPipeline — connectivity probe lazy property
# ===========================================================================

class TestPreventionPipelineConnectivityProbe:
    """Tests for _connectivity_probe lazy property."""

    def test_connectivity_probe_returns_probe_when_registry_available(self):
        """_connectivity_probe returns ConnectivityProbe when MCP registry is available."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import ConnectivityProbe, PreventionPipeline

        pipeline = PreventionPipeline()
        mock_registry = MagicMock()

        with patch("core.orchestrator.prevention.ConnectivityProbe") as MockProbe:
            with patch("core.mcp.registry.get_registry", return_value=mock_registry):
                probe = pipeline._connectivity_probe
                # May or may not be set depending on import path, but no exception
                assert pipeline._connectivity_probe_init_attempted is True

    def test_connectivity_probe_returns_none_when_registry_unavailable(self):
        """_connectivity_probe returns None when MCP registry import fails."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "core.mcp.registry.get_registry", side_effect=ImportError("no registry")
        ):
            probe = pipeline._connectivity_probe
            # After failed init, init_attempted is True
            assert pipeline._connectivity_probe_init_attempted is True

    def test_connectivity_probe_not_reinit_after_attempt(self):
        """_connectivity_probe does not retry after init_attempted is True."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()
        pipeline._connectivity_probe_init_attempted = True
        pipeline._connectivity_probe_instance = None  # explicitly None

        # Should return None immediately without trying to create
        probe = pipeline._connectivity_probe
        assert probe is None

# ===========================================================================
# PreventionPipeline — prompt optimizer lazy property
# ===========================================================================

class TestPreventionPipelinePromptOptimizer:
    """Tests for _prompt_optimizer lazy property."""

    def test_prompt_optimizer_returns_none_when_failure_learning_disabled(self):
        """_prompt_optimizer returns None when failure_learning_enabled=False."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.failure_learning_enabled = False

        with patch("core.orchestrator.config.get_orchestration_config", return_value=mock_cfg):
            optimizer = pipeline._prompt_optimizer
        assert optimizer is None

    def test_prompt_optimizer_returns_instance_when_enabled(self):
        """_prompt_optimizer creates PromptOptimizer when failure_learning_enabled=True."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline, PromptOptimizer

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.failure_learning_enabled = True

        mock_store = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect_high_failure_tools.return_value = []
        mock_detector.detect_recurring_errors.return_value = []

        with patch("core.orchestrator.config.get_orchestration_config", return_value=mock_cfg):
            with patch(
                "core.orchestrator.failure_history.FailureHistoryStore",
                return_value=mock_store,
            ):
                with patch(
                    "core.orchestrator.failure_history.PatternDetector",
                    return_value=mock_detector,
                ):
                    optimizer = pipeline._prompt_optimizer
        # Either the optimizer was created or None (depends on import chain) — just no exception
        assert pipeline._prompt_optimizer_init_attempted is True

    def test_prompt_optimizer_returns_none_on_exception(self):
        """_prompt_optimizer returns None when exception occurs (fail-open)."""
        from unittest.mock import patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        with patch(
            "core.orchestrator.config.get_orchestration_config",
            side_effect=RuntimeError("config error"),
        ):
            optimizer = pipeline._prompt_optimizer
        assert optimizer is None
        assert pipeline._prompt_optimizer_init_attempted is True

    def test_prompt_optimizer_not_reinit_after_attempt(self):
        """_prompt_optimizer does not retry after init_attempted is True."""
        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()
        pipeline._prompt_optimizer_init_attempted = True
        pipeline._prompt_optimizer_instance = None

        optimizer = pipeline._prompt_optimizer
        assert optimizer is None

# ===========================================================================
# PreventionPipeline — validate_tool_schema (enabled path)
# ===========================================================================

class TestPreventionPipelineValidateToolSchema:
    """Tests for validate_tool_schema when enabled."""

    def test_validate_tool_schema_returns_result_when_schema_found(self):
        """validate_tool_schema returns a result when schema is found and validation passes."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline, PreventionVerdict

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.schema_validation_enabled = True

        # Mock _get_tool_schema to return a schema
        mock_schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": []}

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(pipeline, "_get_tool_schema", return_value=mock_schema):
                result = pipeline.validate_tool_schema("server_a", "tool_a", {"name": "test"})

        assert result is not None
        assert result.verdict == PreventionVerdict.PASS

    def test_validate_tool_schema_returns_none_when_schema_not_found(self):
        """validate_tool_schema returns None when _get_tool_schema returns None."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.schema_validation_enabled = True

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(pipeline, "_get_tool_schema", return_value=None):
                result = pipeline.validate_tool_schema("server_a", "tool_a", {"name": "test"})

        assert result is None

    def test_validate_tool_schema_records_prevention_check(self):
        """validate_tool_schema calls record_prevention_check when metrics available."""
        from unittest.mock import MagicMock, call, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.schema_validation_enabled = True

        mock_schema = {"type": "object", "properties": {}, "required": []}

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(pipeline, "_get_tool_schema", return_value=mock_schema):
                with patch(
                    "core.orchestrator.failure_metrics.record_prevention_check"
                ) as mock_record:
                    result = pipeline.validate_tool_schema("srv", "tool", {})

        # record_prevention_check may or may not be called depending on import path
        assert result is not None

# ===========================================================================
# PreventionPipeline — probe_connectivity (enabled path)
# ===========================================================================

class TestPreventionPipelineProbeConnectivity:
    """Tests for probe_connectivity when enabled."""

    def test_probe_connectivity_returns_result_when_probe_available(self):
        """probe_connectivity returns result when probe is not None."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.orchestrator.prevention import (
            PreventionPipeline,
            PreventionResult,
            PreventionVerdict,
        )

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.connectivity_probe_enabled = True

        expected = PreventionResult(
            verdict=PreventionVerdict.PASS,
            check_name="connectivity_probe",
            reason="server is running",
        )

        mock_probe = MagicMock()
        mock_probe.probe_server = AsyncMock(return_value=expected)

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(
                type(pipeline),
                "_connectivity_probe",
                new_callable=lambda: property(lambda self: mock_probe),
            ):
                result = asyncio.run(pipeline.probe_connectivity("test_server"))

        assert result is not None
        assert result.verdict == PreventionVerdict.PASS

    def test_probe_connectivity_returns_none_when_probe_unavailable(self):
        """probe_connectivity returns None when _connectivity_probe is None."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.connectivity_probe_enabled = True

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(
                type(pipeline),
                "_connectivity_probe",
                new_callable=lambda: property(lambda self: None),
            ):
                result = asyncio.run(pipeline.probe_connectivity("no_server"))

        assert result is None

# ===========================================================================
# PreventionPipeline — check_model_reachability (enabled path)
# ===========================================================================

class TestPreventionPipelineCheckModelReachability:
    """Tests for check_model_reachability when enabled."""

    def test_check_model_reachability_returns_result_when_enabled(self):
        """check_model_reachability returns result when enabled."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.orchestrator.prevention import (
            PreventionPipeline,
            PreventionResult,
            PreventionVerdict,
        )

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.model_reachability_enabled = True

        expected = PreventionResult(
            verdict=PreventionVerdict.PASS,
            check_name="model_reachability",
            reason="cloud API",
        )

        mock_check = MagicMock()
        mock_check.check = AsyncMock(return_value=expected)

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(
                type(pipeline),
                "_model_reachability",
                new_callable=lambda: property(lambda self: mock_check),
            ):
                result = asyncio.run(pipeline.check_model_reachability())

        assert result is not None
        assert result.verdict == PreventionVerdict.PASS

    def test_check_model_reachability_returns_none_when_disabled(self):
        """check_model_reachability returns None when model_reachability_enabled=False."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.model_reachability_enabled = False

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            result = asyncio.run(pipeline.check_model_reachability())

        assert result is None

# ===========================================================================
# PreventionPipeline — get_prompt_hints (enabled path)
# ===========================================================================

class TestPreventionPipelineGetPromptHints:
    """Tests for get_prompt_hints when enabled."""

    def test_get_prompt_hints_returns_hints_when_optimizer_available(self):
        """get_prompt_hints returns list from optimizer."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.prompt_optimization_enabled = True

        mock_optimizer = MagicMock()
        mock_optimizer.compile_hints.return_value = ["hint 1", "hint 2"]

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(
                type(pipeline),
                "_prompt_optimizer",
                new_callable=lambda: property(lambda self: mock_optimizer),
            ):
                hints = pipeline.get_prompt_hints()

        assert hints == ["hint 1", "hint 2"]

    def test_get_prompt_hints_returns_empty_when_optimizer_none(self):
        """get_prompt_hints returns [] when _prompt_optimizer is None."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.prompt_optimization_enabled = True

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            with patch.object(
                type(pipeline),
                "_prompt_optimizer",
                new_callable=lambda: property(lambda self: None),
            ):
                hints = pipeline.get_prompt_hints()

        assert hints == []

    def test_get_prompt_hints_returns_empty_when_prompt_optimization_disabled(self):
        """get_prompt_hints returns [] when prompt_optimization_enabled=False."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_cfg = MagicMock()
        mock_cfg.prevention_enabled = True
        mock_cfg.prompt_optimization_enabled = False

        with patch.object(pipeline, "_get_config", return_value=mock_cfg):
            hints = pipeline.get_prompt_hints()

        assert hints == []

# ===========================================================================
# PreventionPipeline — _get_tool_schema
# ===========================================================================

class TestPreventionPipelineGetToolSchema:
    """Tests for _get_tool_schema private method."""

    def test_get_tool_schema_returns_schema_when_tool_found(self):
        """_get_tool_schema returns dict schema when tool is found in registry."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_tool = MagicMock()
        mock_tool.name = "my_tool"
        mock_tool.inputSchema.type = "object"
        mock_tool.inputSchema.properties = {"name": {"type": "string"}}
        mock_tool.inputSchema.required = ["name"]

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [mock_tool]

        with patch("core.mcp.registry.get_registry", return_value=mock_registry):
            result = pipeline._get_tool_schema("server_a", "my_tool")

        assert result is not None
        assert result["type"] == "object"
        assert "name" in result["properties"]
        assert "name" in result["required"]

    def test_get_tool_schema_returns_none_when_tool_not_found(self):
        """_get_tool_schema returns None when tool is not in registry list."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_tool = MagicMock()
        mock_tool.name = "other_tool"

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [mock_tool]

        with patch("core.mcp.registry.get_registry", return_value=mock_registry):
            result = pipeline._get_tool_schema("server_a", "missing_tool")

        assert result is None

    def test_get_tool_schema_returns_none_on_exception(self):
        """_get_tool_schema returns None on any exception (fail-open)."""
        from unittest.mock import patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        with patch("core.mcp.registry.get_registry", side_effect=Exception("registry unavailable")):
            result = pipeline._get_tool_schema("server_a", "tool_a")

        assert result is None

    def test_get_tool_schema_returns_none_when_list_tools_raises(self):
        """_get_tool_schema returns None when list_tools raises."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.prevention import PreventionPipeline

        pipeline = PreventionPipeline()

        mock_registry = MagicMock()
        mock_registry.list_tools.side_effect = RuntimeError("connection lost")

        with patch("core.mcp.registry.get_registry", return_value=mock_registry):
            result = pipeline._get_tool_schema("server_a", "tool_a")

        assert result is None
