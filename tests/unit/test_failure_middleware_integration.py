"""Integration tests for failure middleware pipeline wired into orchestrator.

Phase 118.8 Plan 02: Tests verify the full FailurePipeline through the
orchestrator's _handle_failure and _execute_with_retry methods.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.adapters.registry import AgentRegistry
from core.orchestrator.failure_classifier import (
    FailureClassifier,
    clear_external_rule_sources,
    register_rule_source,
)
from core.orchestrator.failure_middleware import (
    FailureContext,
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
    OrchestrationState,
    OrchestrationTask,
    OrchestrationThought,
    ToolError,
)
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.thinking import OrchestrationThinkingProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StubAgent(UniversalAgent):
    """Minimal agent for testing."""

    def __init__(
        self,
        name: str = "test-agent",
        description: str = "A test agent",
        result: str = "done",
        status: str = "ok",
        caps: AgentCapabilities | None = None,
        raise_on_execute: Exception | None = None,
    ):
        self._name = name
        self._description = description
        self._result = result
        self._status = status
        self._caps = caps or AgentCapabilities()
        self._raise_on_execute = raise_on_execute

    def get_card(self) -> AgentCard:
        return AgentCard(
            name=self._name,
            description=self._description,
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

    async def execute(self, task, context=None):
        if self._raise_on_execute:
            raise self._raise_on_execute
        return AgentResult(result=self._result, status=self._status)

    def get_tools(self):
        return []

    def capabilities(self) -> AgentCapabilities:
        return self._caps

def _make_registry(*agents: UniversalAgent) -> AgentRegistry:
    """Build a registry pre-loaded with the given agents."""
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg

def _make_thinking(
    *,
    failure_response: OrchestrationThought | None = None,
) -> OrchestrationThinkingProvider:
    """Return a mock-backed thinking provider."""
    tp = MagicMock(spec=OrchestrationThinkingProvider)
    tp._on_cost_event = None

    orchestrate_response = OrchestrationThought(
        reasoning="Immediate answer",
        is_final=True,
        answer="The answer is 42",
    )
    tp.orchestrate_think = AsyncMock(return_value=orchestrate_response)

    if failure_response is None:
        failure_response = OrchestrationThought(
            reasoning="Escalating due to failure",
            is_final=False,
            failure_action=FailureAction.ESCALATE,
            escalation_question="How should I proceed?",
        )
    tp.failure_think = AsyncMock(return_value=failure_response)

    return tp

def _make_observation(**overrides) -> OrchestrationObservation:
    """Create a minimal OrchestrationObservation for testing."""
    defaults = {
        "agent_name": "test-agent",
        "task": "test task",
        "result": None,
        "success": False,
        "error": "something went wrong",
    }
    defaults.update(overrides)
    return OrchestrationObservation(**defaults)

def _make_orchestrator(
    *,
    agents: list[UniversalAgent] | None = None,
    failure_response: OrchestrationThought | None = None,
) -> DryadeOrchestrator:
    """Create a DryadeOrchestrator with failure_middleware_enabled=True."""
    if agents is None:
        agents = [StubAgent(name="test-agent")]
    reg = _make_registry(*agents)
    tp = _make_thinking(failure_response=failure_response)
    orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)
    return orch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_pipeline():
    """Clean up the global singleton pipeline and external rule sources."""
    import core.orchestrator.failure_middleware as fm

    # Reset singleton for each test
    with fm._failure_pipeline_lock:
        fm._failure_pipeline = None
    yield
    # Cleanup after test
    with fm._failure_pipeline_lock:
        if fm._failure_pipeline is not None:
            fm._failure_pipeline.clear()
        fm._failure_pipeline = None
    clear_external_rule_sources()

@pytest.fixture
def enabled_config():
    """Patch config so failure_middleware_enabled=True."""
    return patch.dict(os.environ, {"DRYADE_FAILURE_MIDDLEWARE_ENABLED": "true"})

@pytest.fixture
def disabled_config():
    """Patch config so failure_middleware_enabled=False (default)."""
    return patch.dict(os.environ, {"DRYADE_FAILURE_MIDDLEWARE_ENABLED": "false"})

# ---------------------------------------------------------------------------
# Test 1: PreFailure hook can override action
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPreFailureHookCanOverrideAction:
    """Register a PreFailure hook that changes RETRY to SKIP."""

    @pytest.mark.asyncio
    async def test_pre_failure_hook_can_override_action(self, enabled_config):
        with enabled_config:
            hook_called = False

            async def override_retry_to_skip(ctx: FailureContext) -> FailureContext:
                nonlocal hook_called
                hook_called = True
                if ctx.failure_action == FailureAction.RETRY:
                    ctx.failure_action = FailureAction.SKIP
                return ctx

            pipeline = get_failure_pipeline()
            pipeline.add_pre_failure(override_retry_to_skip, priority=10)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation(agent_name="test-agent")
            obs.failure_thought = OrchestrationThought(
                reasoning="Should retry",
                is_final=False,
                failure_action=FailureAction.RETRY,
            )

            state = OrchestrationState()
            result = await orch._handle_failure(obs, {}, [], state)

            assert hook_called
            # SKIP on non-critical => success=True (continue orchestration)
            assert result.success is True

# ---------------------------------------------------------------------------
# Test 2: PreFailure short-circuit skips graduated escalation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPreFailureShortCircuit:
    """PreFailure hook with short_circuit=True bypasses graduated escalation."""

    @pytest.mark.asyncio
    async def test_pre_failure_short_circuit_skips_graduated_escalation(self, enabled_config):
        with enabled_config:

            async def short_circuit_abort(ctx: FailureContext) -> FailureContext:
                ctx.short_circuit = True
                ctx.failure_action = FailureAction.ABORT
                return ctx

            pipeline = get_failure_pipeline()
            pipeline.add_pre_failure(short_circuit_abort, priority=10)

            orch = _make_orchestrator()
            obs = _make_observation()
            # Even at depth 6, graduated escalation would normally override to ABORT
            # but the short-circuit should bypass it and use the hook's decision
            obs.failure_thought = OrchestrationThought(
                reasoning="Should retry",
                is_final=False,
                failure_action=FailureAction.RETRY,  # Would be overridden by depth>=6
            )

            state = OrchestrationState()
            # Use depth >= 6 where graduated escalation would force ABORT anyway
            # The key test: at depth < 6, short-circuit prevents graduated escalation
            # from changing the action
            result = await orch._handle_failure(
                obs,
                {},
                [],
                state,
                failure_depth=6,
            )

            # ABORT handler returns abort result
            assert result.success is False
            assert (
                "aborted" in (result.reason or "").lower()
                or "aborted" in (result.output or "").lower()
            )

# ---------------------------------------------------------------------------
# Test 3: PostFailure hook can upgrade action
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPostFailureHookCanUpgradeAction:
    """PostFailure hook changes SKIP to ESCALATE."""

    @pytest.mark.asyncio
    async def test_post_failure_hook_can_upgrade_action(self, enabled_config):
        with enabled_config:

            async def upgrade_skip_to_escalate(ctx: FailureContext) -> FailureContext:
                if ctx.failure_action == FailureAction.SKIP:
                    ctx.failure_action = FailureAction.ESCALATE
                return ctx

            pipeline = get_failure_pipeline()
            pipeline.add_post_failure(upgrade_skip_to_escalate, priority=10)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Want to skip",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            result = await orch._handle_failure(obs, {}, [], state)

            # PostFailure changed SKIP -> ESCALATE, so needs_escalation
            assert result.success is False
            assert result.needs_escalation is True

# ---------------------------------------------------------------------------
# Test 4: PostFailure recovery strategy executes
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPostFailureRecoveryStrategyExecutes:
    """PostFailure hook sets a custom RecoveryStrategy that succeeds."""

    @pytest.mark.asyncio
    async def test_post_failure_recovery_strategy_executes(self, enabled_config):
        with enabled_config:

            class CustomStrategy(RecoveryStrategy):
                @property
                def name(self) -> str:
                    return "custom-strategy"

                def can_handle(self, ctx: FailureContext) -> bool:
                    return True

                async def execute(self, ctx: FailureContext) -> RecoveryResult:
                    return RecoveryResult(
                        success=True,
                        output="recovered by custom strategy",
                    )

            async def set_strategy(ctx: FailureContext) -> FailureContext:
                ctx.recovery_strategy = CustomStrategy()
                return ctx

            pipeline = get_failure_pipeline()
            pipeline.add_post_failure(set_strategy, priority=10)

            orch = _make_orchestrator()
            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Retry",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            result = await orch._handle_failure(obs, {}, [], state)

            # Strategy succeeded => returns OrchestrationResult success
            assert result.success is True
            assert result.output == "recovered by custom strategy"

# ---------------------------------------------------------------------------
# Test 5: PostFailure recovery strategy failure falls through
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPostFailureRecoveryStrategyFailure:
    """Recovery strategy returns success=False, falls through to standard handler."""

    @pytest.mark.asyncio
    async def test_post_failure_recovery_strategy_failure_falls_through(self, enabled_config):
        with enabled_config:

            class FailingStrategy(RecoveryStrategy):
                @property
                def name(self) -> str:
                    return "failing-strategy"

                def can_handle(self, ctx: FailureContext) -> bool:
                    return True

                async def execute(self, ctx: FailureContext) -> RecoveryResult:
                    return RecoveryResult(
                        success=False,
                        error="strategy failed to recover",
                    )

            async def set_failing_strategy(ctx: FailureContext) -> FailureContext:
                ctx.recovery_strategy = FailingStrategy()
                return ctx

            pipeline = get_failure_pipeline()
            pipeline.add_post_failure(set_failing_strategy, priority=10)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Skip it",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            result = await orch._handle_failure(obs, {}, [], state)

            # Strategy failed => falls through to standard SKIP handler
            # Non-critical + SKIP => success=True
            assert result.success is True

# ---------------------------------------------------------------------------
# Test 6: OnRecovery hook called after retry success
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOnRecoveryHookCalledAfterRetry:
    """OnRecovery hook fires after successful retry in _execute_with_retry."""

    @pytest.mark.asyncio
    async def test_on_recovery_hook_called_after_retry_success(self, enabled_config):
        with enabled_config:
            hook_called = False
            hook_result_success = None

            async def track_recovery(ctx: FailureContext, result: RecoveryResult) -> None:
                nonlocal hook_called, hook_result_success
                hook_called = True
                hook_result_success = result.success

            pipeline = get_failure_pipeline()
            pipeline.add_on_recovery(track_recovery)

            # Agent that fails once then succeeds
            call_count = 0

            agent = StubAgent(name="flaky-agent")
            reg = _make_registry(agent)
            tp = _make_thinking(
                failure_response=OrchestrationThought(
                    reasoning="Transient, retry",
                    is_final=False,
                    failure_action=FailureAction.RETRY,
                ),
            )
            orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

            async def flaky_execute(
                task, execution_id, context, timeout=None, execution_tracker=None
            ):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return OrchestrationObservation(
                        agent_name="flaky-agent",
                        task="flaky work",
                        result=None,
                        success=False,
                        error="transient error",
                    )
                return OrchestrationObservation(
                    agent_name="flaky-agent",
                    task="flaky work",
                    result="success on retry",
                    success=True,
                )

            orch._execute_single = flaky_execute

            task = OrchestrationTask(agent_name="flaky-agent", description="flaky work")
            result = await orch._execute_with_retry(task, "exec-1", {}, reg.list_agents())

            assert result.success is True
            assert hook_called
            assert hook_result_success is True

# ---------------------------------------------------------------------------
# Test 7: PreFailure hook error does not break orchestration
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPreFailureHookErrorFailOpen:
    """PreFailure hook raises RuntimeError -- orchestration continues."""

    @pytest.mark.asyncio
    async def test_pre_failure_hook_error_does_not_break_orchestration(self, enabled_config):
        with enabled_config:

            async def broken_hook(ctx: FailureContext) -> FailureContext:
                raise RuntimeError("hook crashed")

            pipeline = get_failure_pipeline()
            pipeline.add_pre_failure(broken_hook, priority=10)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Skip it",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            # Should complete normally despite hook error
            result = await orch._handle_failure(obs, {}, [], state)
            assert result.success is True  # SKIP non-critical => continue

# ---------------------------------------------------------------------------
# Test 7b: PostFailure hook error does not break orchestration
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPostFailureHookErrorFailOpen:
    """PostFailure hook raises RuntimeError -- orchestration continues."""

    @pytest.mark.asyncio
    async def test_post_failure_hook_error_does_not_break_orchestration(self, enabled_config):
        with enabled_config:

            async def broken_post_hook(ctx: FailureContext) -> FailureContext:
                raise RuntimeError("post-hook crashed")

            pipeline = get_failure_pipeline()
            pipeline.add_post_failure(broken_post_hook, priority=10)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Skip it",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            result = await orch._handle_failure(obs, {}, [], state)
            assert result.success is True  # SKIP non-critical => continue

# ---------------------------------------------------------------------------
# Test 7c: OnRecovery hook error does not break orchestration
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOnRecoveryHookErrorFailOpen:
    """OnRecovery hook raises RuntimeError -- _execute_with_retry still returns success."""

    @pytest.mark.asyncio
    async def test_on_recovery_hook_error_does_not_break_orchestration(self, enabled_config):
        with enabled_config:

            async def broken_recovery_hook(ctx: FailureContext, result: RecoveryResult) -> None:
                raise RuntimeError("recovery hook crashed")

            pipeline = get_failure_pipeline()
            pipeline.add_on_recovery(broken_recovery_hook)

            # Agent that fails once then succeeds (triggers OnRecovery)
            call_count = 0

            agent = StubAgent(name="flaky-agent")
            reg = _make_registry(agent)
            tp = _make_thinking(
                failure_response=OrchestrationThought(
                    reasoning="Retry",
                    is_final=False,
                    failure_action=FailureAction.RETRY,
                ),
            )
            orch = DryadeOrchestrator(thinking_provider=tp, agent_registry=reg)

            async def flaky_execute(
                task, execution_id, context, timeout=None, execution_tracker=None
            ):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return OrchestrationObservation(
                        agent_name="flaky-agent",
                        task="work",
                        result=None,
                        success=False,
                        error="transient",
                    )
                return OrchestrationObservation(
                    agent_name="flaky-agent",
                    task="work",
                    result="ok",
                    success=True,
                )

            orch._execute_single = flaky_execute

            task = OrchestrationTask(agent_name="flaky-agent", description="work")
            result = await orch._execute_with_retry(task, "exec-1", {}, reg.list_agents())

            # Must still succeed despite broken hook
            assert result.success is True

# ---------------------------------------------------------------------------
# Test 8: Disabled flag bypasses all middleware
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDisabledFlagBypassesMiddleware:
    """With failure_middleware_enabled=False, no hooks are called."""

    @pytest.mark.asyncio
    async def test_disabled_flag_bypasses_all_middleware(self, disabled_config):
        with disabled_config:
            hook_called = False

            async def should_not_run(ctx: FailureContext) -> FailureContext:
                nonlocal hook_called
                hook_called = True
                ctx.failure_action = FailureAction.ABORT
                return ctx

            pipeline = get_failure_pipeline()
            pipeline.add_pre_failure(should_not_run, priority=10)
            pipeline.add_post_failure(should_not_run, priority=10)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Skip",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            result = await orch._handle_failure(obs, {}, [], state)

            # Hook would have changed to ABORT, but flag is off => SKIP behavior
            assert not hook_called
            assert result.success is True  # SKIP non-critical

# ---------------------------------------------------------------------------
# Test 9: Multiple hooks execute in priority order
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMultipleHooksPriorityOrder:
    """3 PreFailure hooks with different priorities run in correct order."""

    @pytest.mark.asyncio
    async def test_multiple_hooks_execute_in_priority_order(self, enabled_config):
        with enabled_config:
            call_order = []

            async def hook_a(ctx: FailureContext) -> None:
                call_order.append("a")

            async def hook_b(ctx: FailureContext) -> None:
                call_order.append("b")

            async def hook_c(ctx: FailureContext) -> None:
                call_order.append("c")

            pipeline = get_failure_pipeline()
            # Register out of order: b(200), a(50), c(100)
            pipeline.add_pre_failure(hook_b, priority=200)
            pipeline.add_pre_failure(hook_a, priority=50)
            pipeline.add_pre_failure(hook_c, priority=100)

            agent = StubAgent(name="test-agent", caps=AgentCapabilities(is_critical=False))
            orch = _make_orchestrator(agents=[agent])

            obs = _make_observation()
            obs.failure_thought = OrchestrationThought(
                reasoning="Skip",
                is_final=False,
                failure_action=FailureAction.SKIP,
            )

            state = OrchestrationState()
            await orch._handle_failure(obs, {}, [], state)

            # Note: built-in logging_pre_failure at priority=0 runs first,
            # but it doesn't add to call_order. Our hooks: a(50), c(100), b(200)
            assert call_order == ["a", "c", "b"]

# ---------------------------------------------------------------------------
# Test 10: External classifier rule integrates with pipeline
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExternalClassifierRuleIntegration:
    """External rule source via register_rule_source() is called during classification."""

    @pytest.mark.asyncio
    async def test_external_classifier_rule_integrates_with_pipeline(self):
        rule_called = False

        def custom_rule(tool_error: ToolError):
            nonlocal rule_called
            rule_called = True
            if "custom_error_pattern" in (tool_error.message or ""):
                return ErrorClassification(
                    category=ErrorCategory.PERMANENT,
                    severity=ErrorSeverity.FATAL,
                    suggested_action=FailureAction.ABORT,
                    confidence=0.95,
                    reason="Custom rule matched",
                )
            return None

        register_rule_source(custom_rule)

        try:
            # Create a ToolError that matches the custom rule
            # Use error_type that does NOT match any built-in exception group
            # so external rules at Priority 2.5 get a chance to run
            tool_error = ToolError(
                tool_name="test-tool",
                server_name="test-server",
                error_type="CustomPluginError",
                message="custom_error_pattern in request",
            )
            classification = FailureClassifier.classify(tool_error)

            assert rule_called
            assert classification.category == ErrorCategory.PERMANENT
            assert classification.suggested_action == FailureAction.ABORT
        finally:
            clear_external_rule_sources()
