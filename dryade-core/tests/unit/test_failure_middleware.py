"""TDD tests for the composable failure middleware pipeline.

Phase 118.8 Plan 01: Tests for FailurePipeline, RecoveryStrategy ABC,
FailureContext, hook types, and get_failure_pipeline singleton.
"""

import pytest

from core.orchestrator.failure_middleware import (
    FailureContext,
    FailurePipeline,
    RecoveryResult,
    RecoveryStrategy,
    get_failure_pipeline,
)
from core.orchestrator.models import (
    ErrorCategory,
    ErrorClassification,
    ErrorSeverity,
    FailureAction,
    OrchestrationObservation,
    ToolError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_observation(**overrides) -> OrchestrationObservation:
    """Create a minimal OrchestrationObservation for testing."""
    defaults = {
        "agent_name": "test-agent",
        "task": "test task",
        "result": "some result",
        "success": False,
        "error": "something went wrong",
    }
    defaults.update(overrides)
    return OrchestrationObservation(**defaults)

def _make_tool_error(**overrides) -> ToolError:
    """Create a minimal ToolError for testing."""
    defaults = {
        "tool_name": "test_tool",
        "server_name": "test_server",
        "error_type": "RuntimeError",
        "message": "test error",
    }
    defaults.update(overrides)
    return ToolError(**defaults)

def _make_classification(**overrides) -> ErrorClassification:
    """Create a minimal ErrorClassification for testing."""
    defaults = {
        "category": ErrorCategory.TRANSIENT,
        "severity": ErrorSeverity.RETRIABLE,
        "suggested_action": FailureAction.RETRY,
        "confidence": 1.0,
        "reason": "test",
    }
    defaults.update(overrides)
    return ErrorClassification(**defaults)

def _make_context(**overrides) -> FailureContext:
    """Create a FailureContext with sensible defaults."""
    defaults = {
        "observation": _make_observation(),
        "error_classification": None,
        "failure_action": None,
        "failure_depth": 0,
        "tool_error": None,
        "metadata": {},
    }
    defaults.update(overrides)
    return FailureContext(**defaults)

class ConcreteRecoveryStrategy(RecoveryStrategy):
    """A concrete recovery strategy for testing."""

    @property
    def name(self) -> str:
        return "test-strategy"

    def can_handle(self, ctx: FailureContext) -> bool:
        return ctx.failure_depth < 3

    async def execute(self, ctx: FailureContext) -> RecoveryResult:
        return RecoveryResult(success=True, output="recovered", metadata={"strategy": self.name})

class NeverHandlesStrategy(RecoveryStrategy):
    """A strategy that never matches."""

    @property
    def name(self) -> str:
        return "never-handles"

    def can_handle(self, ctx: FailureContext) -> bool:
        return False

    async def execute(self, ctx: FailureContext) -> RecoveryResult:
        return RecoveryResult(success=False, error="should not be called")

# ---------------------------------------------------------------------------
# FailureContext tests
# ---------------------------------------------------------------------------

class TestFailureContext:
    """Test FailureContext dataclass creation."""

    def test_creation_with_all_fields(self):
        obs = _make_observation()
        classification = _make_classification()
        tool_error = _make_tool_error()

        ctx = FailureContext(
            observation=obs,
            error_classification=classification,
            failure_action=FailureAction.RETRY,
            failure_depth=2,
            tool_error=tool_error,
            metadata={"key": "value"},
        )

        assert ctx.observation is obs
        assert ctx.error_classification is classification
        assert ctx.failure_action == FailureAction.RETRY
        assert ctx.failure_depth == 2
        assert ctx.tool_error is tool_error
        assert ctx.metadata == {"key": "value"}
        assert ctx.short_circuit is False
        assert ctx.recovery_strategy is None

    def test_creation_minimal(self):
        obs = _make_observation()
        ctx = FailureContext(
            observation=obs,
            error_classification=None,
            failure_action=None,
            failure_depth=0,
            tool_error=None,
            metadata={},
        )
        assert ctx.observation is obs
        assert ctx.short_circuit is False

    def test_short_circuit_default_false(self):
        ctx = _make_context()
        assert ctx.short_circuit is False

    def test_recovery_strategy_default_none(self):
        ctx = _make_context()
        assert ctx.recovery_strategy is None

# ---------------------------------------------------------------------------
# RecoveryResult tests
# ---------------------------------------------------------------------------

class TestRecoveryResult:
    """Test RecoveryResult dataclass."""

    def test_success_result(self):
        result = RecoveryResult(success=True, output="data")
        assert result.success is True
        assert result.output == "data"
        assert result.error is None
        assert result.metadata == {}

    def test_failure_result(self):
        result = RecoveryResult(success=False, error="failed")
        assert result.success is False
        assert result.error == "failed"

    def test_metadata_default_factory(self):
        r1 = RecoveryResult(success=True)
        r2 = RecoveryResult(success=True)
        assert r1.metadata is not r2.metadata  # separate dict instances

# ---------------------------------------------------------------------------
# RecoveryStrategy ABC tests
# ---------------------------------------------------------------------------

class TestRecoveryStrategyABC:
    """Test RecoveryStrategy abstract base class."""

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            RecoveryStrategy()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        strategy = ConcreteRecoveryStrategy()
        assert strategy.name == "test-strategy"

    def test_can_handle(self):
        strategy = ConcreteRecoveryStrategy()
        ctx = _make_context(failure_depth=1)
        assert strategy.can_handle(ctx) is True

        ctx_deep = _make_context(failure_depth=5)
        assert strategy.can_handle(ctx_deep) is False

    @pytest.mark.asyncio
    async def test_execute(self):
        strategy = ConcreteRecoveryStrategy()
        ctx = _make_context()
        result = await strategy.execute(ctx)
        assert result.success is True
        assert result.output == "recovered"
        assert result.metadata == {"strategy": "test-strategy"}

# ---------------------------------------------------------------------------
# FailurePipeline - PreFailure hooks
# ---------------------------------------------------------------------------

class TestPreFailureHooks:
    """Test FailurePipeline.run_pre_failure behavior."""

    @pytest.mark.asyncio
    async def test_hooks_execute_in_priority_order(self):
        pipeline = FailurePipeline()
        call_order = []

        async def hook_a(ctx):
            call_order.append("a")
            return None

        async def hook_b(ctx):
            call_order.append("b")
            return None

        async def hook_c(ctx):
            call_order.append("c")
            return None

        pipeline.add_pre_failure(hook_b, priority=200)
        pipeline.add_pre_failure(hook_a, priority=50)
        pipeline.add_pre_failure(hook_c, priority=100)

        ctx = _make_context()
        await pipeline.run_pre_failure(ctx)

        assert call_order == ["a", "c", "b"]

    @pytest.mark.asyncio
    async def test_short_circuit_stops_pipeline(self):
        pipeline = FailurePipeline()
        call_order = []

        async def hook_short_circuit(ctx):
            call_order.append("short_circuit")
            ctx.short_circuit = True
            ctx.failure_action = FailureAction.ABORT
            return ctx

        async def hook_should_not_run(ctx):
            call_order.append("should_not_run")
            return None

        pipeline.add_pre_failure(hook_short_circuit, priority=50)
        pipeline.add_pre_failure(hook_should_not_run, priority=100)

        ctx = _make_context()
        result = await pipeline.run_pre_failure(ctx)

        assert call_order == ["short_circuit"]
        assert result.short_circuit is True
        assert result.failure_action == FailureAction.ABORT

    @pytest.mark.asyncio
    async def test_hook_errors_are_caught_not_propagated(self):
        pipeline = FailurePipeline()
        call_order = []

        async def failing_hook(ctx):
            call_order.append("failing")
            raise RuntimeError("hook error")

        async def succeeding_hook(ctx):
            call_order.append("succeeding")
            return None

        pipeline.add_pre_failure(failing_hook, priority=50)
        pipeline.add_pre_failure(succeeding_hook, priority=100)

        ctx = _make_context()
        result = await pipeline.run_pre_failure(ctx)

        assert call_order == ["failing", "succeeding"]
        assert result is ctx  # original context returned

    @pytest.mark.asyncio
    async def test_hook_returning_none_doesnt_replace_context(self):
        pipeline = FailurePipeline()

        async def noop_hook(ctx):
            return None

        pipeline.add_pre_failure(noop_hook)

        ctx = _make_context()
        result = await pipeline.run_pre_failure(ctx)
        assert result is ctx

    @pytest.mark.asyncio
    async def test_hook_returning_context_replaces_it(self):
        pipeline = FailurePipeline()

        async def replacing_hook(ctx):
            new_ctx = _make_context(failure_depth=99)
            return new_ctx

        pipeline.add_pre_failure(replacing_hook)

        ctx = _make_context(failure_depth=0)
        result = await pipeline.run_pre_failure(ctx)
        assert result.failure_depth == 99
        assert result is not ctx

# ---------------------------------------------------------------------------
# FailurePipeline - PostFailure hooks
# ---------------------------------------------------------------------------

class TestPostFailureHooks:
    """Test FailurePipeline.run_post_failure behavior."""

    @pytest.mark.asyncio
    async def test_hooks_execute_in_priority_order(self):
        pipeline = FailurePipeline()
        call_order = []

        async def hook_a(ctx):
            call_order.append("a")
            return None

        async def hook_b(ctx):
            call_order.append("b")
            return None

        pipeline.add_post_failure(hook_b, priority=200)
        pipeline.add_post_failure(hook_a, priority=50)

        ctx = _make_context()
        await pipeline.run_post_failure(ctx)

        assert call_order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_short_circuit_stops_remaining_hooks(self):
        pipeline = FailurePipeline()
        call_order = []

        async def hook_short(ctx):
            call_order.append("short")
            ctx.short_circuit = True
            return ctx

        async def hook_after(ctx):
            call_order.append("after")
            return None

        pipeline.add_post_failure(hook_short, priority=50)
        pipeline.add_post_failure(hook_after, priority=100)

        ctx = _make_context()
        result = await pipeline.run_post_failure(ctx)

        assert call_order == ["short"]
        assert result.short_circuit is True

    @pytest.mark.asyncio
    async def test_can_override_failure_action(self):
        pipeline = FailurePipeline()

        async def upgrade_hook(ctx):
            ctx.failure_action = FailureAction.ESCALATE
            return ctx

        pipeline.add_post_failure(upgrade_hook)

        ctx = _make_context(failure_action=FailureAction.RETRY)
        result = await pipeline.run_post_failure(ctx)

        assert result.failure_action == FailureAction.ESCALATE

# ---------------------------------------------------------------------------
# FailurePipeline - OnRecovery hooks
# ---------------------------------------------------------------------------

class TestOnRecoveryHooks:
    """Test FailurePipeline.run_on_recovery behavior."""

    @pytest.mark.asyncio
    async def test_all_hooks_called_even_if_one_fails(self):
        pipeline = FailurePipeline()
        call_order = []

        async def failing_hook(ctx, result):
            call_order.append("failing")
            raise RuntimeError("boom")

        async def succeeding_hook(ctx, result):
            call_order.append("succeeding")

        pipeline.add_on_recovery(failing_hook)
        pipeline.add_on_recovery(succeeding_hook)

        ctx = _make_context()
        recovery_result = RecoveryResult(success=True)

        await pipeline.run_on_recovery(ctx, recovery_result)

        assert call_order == ["failing", "succeeding"]

# ---------------------------------------------------------------------------
# FailurePipeline - Recovery strategy
# ---------------------------------------------------------------------------

class TestRecoveryStrategyLookup:
    """Test FailurePipeline.find_recovery_strategy behavior."""

    @pytest.mark.asyncio
    async def test_returns_first_can_handle_match(self):
        pipeline = FailurePipeline()
        pipeline.register_recovery_strategy(NeverHandlesStrategy())
        pipeline.register_recovery_strategy(ConcreteRecoveryStrategy())

        ctx = _make_context(failure_depth=1)
        strategy = await pipeline.find_recovery_strategy(ctx)

        assert strategy is not None
        assert strategy.name == "test-strategy"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self):
        pipeline = FailurePipeline()
        pipeline.register_recovery_strategy(NeverHandlesStrategy())

        ctx = _make_context()
        strategy = await pipeline.find_recovery_strategy(ctx)
        assert strategy is None

    @pytest.mark.asyncio
    async def test_strategies_checked_in_registration_order(self):
        pipeline = FailurePipeline()

        class FirstStrategy(RecoveryStrategy):
            @property
            def name(self):
                return "first"

            def can_handle(self, ctx):
                return True

            async def execute(self, ctx):
                return RecoveryResult(success=True)

        class SecondStrategy(RecoveryStrategy):
            @property
            def name(self):
                return "second"

            def can_handle(self, ctx):
                return True

            async def execute(self, ctx):
                return RecoveryResult(success=True)

        pipeline.register_recovery_strategy(FirstStrategy())
        pipeline.register_recovery_strategy(SecondStrategy())

        ctx = _make_context()
        strategy = await pipeline.find_recovery_strategy(ctx)

        assert strategy is not None
        assert strategy.name == "first"

# ---------------------------------------------------------------------------
# FailurePipeline - clear()
# ---------------------------------------------------------------------------

class TestPipelineClear:
    """Test FailurePipeline.clear removes all hooks and strategies."""

    @pytest.mark.asyncio
    async def test_clear_removes_everything(self):
        pipeline = FailurePipeline()

        async def pre_hook(ctx):
            return None

        async def post_hook(ctx):
            return None

        async def recovery_hook(ctx, result):
            pass

        pipeline.add_pre_failure(pre_hook)
        pipeline.add_post_failure(post_hook)
        pipeline.add_on_recovery(recovery_hook)
        pipeline.register_recovery_strategy(ConcreteRecoveryStrategy())

        pipeline.clear()

        # Verify all lists are empty
        assert len(pipeline._pre_failure) == 0
        assert len(pipeline._post_failure) == 0
        assert len(pipeline._on_recovery) == 0
        assert len(pipeline._recovery_strategies) == 0

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestGetFailurePipeline:
    """Test get_failure_pipeline singleton."""

    def test_returns_singleton(self):
        # Reset singleton state for test isolation
        import core.orchestrator.failure_middleware as mod

        mod._failure_pipeline = None

        p1 = get_failure_pipeline()
        p2 = get_failure_pipeline()
        assert p1 is p2

        # Cleanup
        mod._failure_pipeline = None

# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    """Test that lower priority numbers execute first."""

    @pytest.mark.asyncio
    async def test_lower_priority_executes_first(self):
        pipeline = FailurePipeline()
        call_order = []

        async def hook_p500(ctx):
            call_order.append(500)
            return None

        async def hook_p1(ctx):
            call_order.append(1)
            return None

        async def hook_p100(ctx):
            call_order.append(100)
            return None

        pipeline.add_pre_failure(hook_p500, priority=500)
        pipeline.add_pre_failure(hook_p1, priority=1)
        pipeline.add_pre_failure(hook_p100, priority=100)

        await pipeline.run_pre_failure(_make_context())
        assert call_order == [1, 100, 500]

    @pytest.mark.asyncio
    async def test_same_priority_preserves_insertion_order(self):
        pipeline = FailurePipeline()
        call_order = []

        async def hook_first(ctx):
            call_order.append("first")
            return None

        async def hook_second(ctx):
            call_order.append("second")
            return None

        pipeline.add_pre_failure(hook_first, priority=100)
        pipeline.add_pre_failure(hook_second, priority=100)

        await pipeline.run_pre_failure(_make_context())
        assert call_order == ["first", "second"]

# ---------------------------------------------------------------------------
# Concrete RecoveryStrategy integration
# ---------------------------------------------------------------------------

class TestConcreteRecoveryStrategy:
    """Test a concrete RecoveryStrategy subclass end-to-end."""

    @pytest.mark.asyncio
    async def test_can_handle_and_execute_work(self):
        strategy = ConcreteRecoveryStrategy()
        ctx = _make_context(failure_depth=1)

        assert strategy.can_handle(ctx) is True
        result = await strategy.execute(ctx)

        assert result.success is True
        assert result.output == "recovered"
        assert result.metadata["strategy"] == "test-strategy"

    @pytest.mark.asyncio
    async def test_can_handle_rejects_deep_failures(self):
        strategy = ConcreteRecoveryStrategy()
        ctx = _make_context(failure_depth=5)

        assert strategy.can_handle(ctx) is False

# ===========================================================================
# Task 2: External rule sources and config flag tests
# ===========================================================================

from core.orchestrator.failure_classifier import (
    FailureClassifier,
    clear_external_rule_sources,
    register_rule_source,
)

class TestExternalRuleSources:
    """Test pluggable external rule sources in FailureClassifier."""

    def setup_method(self):
        """Clean up external rule sources before each test."""
        clear_external_rule_sources()

    def teardown_method(self):
        """Clean up external rule sources after each test."""
        clear_external_rule_sources()

    def test_custom_rule_takes_priority_over_message_patterns(self):
        """External rule at Priority 2.5 should override message pattern match at Priority 3."""

        # "rate limit" matches message pattern -> RATE_LIMIT/RETRY
        # But our custom rule says -> PERMANENT/ABORT
        def custom_rule(error):
            if "rate limit" in error.message_lower:
                return ErrorClassification(
                    category=ErrorCategory.PERMANENT,
                    severity=ErrorSeverity.FATAL,
                    suggested_action=FailureAction.ABORT,
                    confidence=1.0,
                    reason="Custom: rate limit override",
                )
            return None

        register_rule_source(custom_rule)

        error = _make_tool_error(message="rate limit exceeded")
        result = FailureClassifier.classify(error)

        assert result.category == ErrorCategory.PERMANENT
        assert result.suggested_action == FailureAction.ABORT
        assert "Custom" in result.reason

    def test_custom_rule_does_not_override_http_status(self):
        """HTTP status (Priority 1) should still take precedence over external rules."""

        def custom_rule(error):
            return ErrorClassification(
                category=ErrorCategory.PERMANENT,
                severity=ErrorSeverity.FATAL,
                suggested_action=FailureAction.ABORT,
                confidence=1.0,
                reason="Custom override",
            )

        register_rule_source(custom_rule)

        # HTTP 429 = RATE_LIMIT/RETRY at Priority 1
        error = _make_tool_error(http_status=429, message="test")
        result = FailureClassifier.classify(error)

        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.suggested_action == FailureAction.RETRY

    def test_custom_rule_does_not_override_exception_type(self):
        """Exception type (Priority 2) should still take precedence over external rules."""

        def custom_rule(error):
            return ErrorClassification(
                category=ErrorCategory.PERMANENT,
                severity=ErrorSeverity.FATAL,
                suggested_action=FailureAction.ABORT,
                confidence=1.0,
                reason="Custom override",
            )

        register_rule_source(custom_rule)

        # TimeoutError = TRANSIENT/RETRY at Priority 2
        error = _make_tool_error(error_type="TimeoutError", message="test")
        result = FailureClassifier.classify(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.suggested_action == FailureAction.RETRY

    def test_erroring_rule_source_is_caught_pipeline_continues(self):
        """An erroring external rule source should be caught; pipeline should continue."""

        def bad_rule(error):
            raise RuntimeError("rule source crashed")

        def good_rule(error):
            return ErrorClassification(
                category=ErrorCategory.RESOURCE,
                severity=ErrorSeverity.FATAL,
                suggested_action=FailureAction.ABORT,
                confidence=1.0,
                reason="Good rule matched",
            )

        register_rule_source(bad_rule)
        register_rule_source(good_rule)

        error = _make_tool_error(message="no matching built-in pattern")
        result = FailureClassifier.classify(error)

        assert result.category == ErrorCategory.RESOURCE
        assert result.suggested_action == FailureAction.ABORT

    def test_clear_external_rule_sources_removes_all(self):
        """clear_external_rule_sources should remove all registered rules."""

        def custom_rule(error):
            return ErrorClassification(
                category=ErrorCategory.PERMANENT,
                severity=ErrorSeverity.FATAL,
                suggested_action=FailureAction.ABORT,
                confidence=1.0,
                reason="Custom",
            )

        register_rule_source(custom_rule)
        clear_external_rule_sources()

        # After clearing, should fall through to message patterns or default
        error = _make_tool_error(message="no matching pattern at all xyz123")
        result = FailureClassifier.classify(error)

        # Should be SEMANTIC default (no external rules, no message match)
        assert result.category == ErrorCategory.SEMANTIC
        assert result.confidence == 0.0

    def test_classify_chain_order_http_exception_external_message_default(self):
        """Verify the full classification chain order: http > exception > external > message > default."""
        call_order = []

        def tracking_rule(error):
            call_order.append("external")
            return None  # Don't match, let pipeline continue

        register_rule_source(tracking_rule)

        # Error with no HTTP status, no matching exception type -> external rules called
        # Then message patterns -> "connection refused" matches CONNECTION
        error = _make_tool_error(
            error_type="SomeUnknownError",
            message="connection refused",
        )
        result = FailureClassifier.classify(error)

        # External rule was called (didn't match), so fell through to message pattern
        assert "external" in call_order
        assert result.category == ErrorCategory.CONNECTION

        # Now test that with an HTTP status, external rule is NOT called
        call_order.clear()
        error_with_http = _make_tool_error(
            http_status=429,
            error_type="SomeUnknownError",
            message="connection refused",
        )
        result = FailureClassifier.classify(error_with_http)

        # HTTP status wins at Priority 1, external rule never called
        assert "external" not in call_order
        assert result.category == ErrorCategory.RATE_LIMIT

class TestConfigFlag:
    """Test failure_middleware_enabled config flag."""

    def test_failure_middleware_enabled_exists_and_defaults_false(self):
        from core.orchestrator.config import get_orchestration_config

        config = get_orchestration_config()
        assert hasattr(config, "failure_middleware_enabled")
        assert config.failure_middleware_enabled is False

    def test_failure_middleware_enabled_in_mutable_keys(self):
        from core.orchestrator.config import MUTABLE_CONFIG_KEYS

        assert "failure_middleware_enabled" in MUTABLE_CONFIG_KEYS
