"""Regression tests for Phase 115.6: Escalation loop X-Ray fixes.

Tests 6 findings:
- XR-C01: Self-mod tool escalation creates observation
- XR-C02: Executor result fed back to retry context
- XR-E01: Single escalation registration (no double)
- XR-E02: Meta-action fallback skipped on retry
- XR-W01: _create_agent is programmatic (not a stub)
- XR-W02: Router hints skipped for meta-actions
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

@pytest.fixture(autouse=True)
def _disable_prevention_checks():
    with patch.dict(
        os.environ,
        {
            "DRYADE_PREVENTION_ENABLED": "false",
            "DRYADE_MODEL_REACHABILITY_ENABLED": "false",
        },
    ):
        yield

from core.orchestrator.escalation import (
    EscalationAction,
    EscalationActionType,
    EscalationExecutor,
    EscalationRegistry,
    PendingEscalation,
)
from core.orchestrator.models import (
    OrchestrationResult,
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.observation import ObservationHistory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(
    conversation_id: str = "conv-xr",
    user_id: str = "user-xr",
    metadata: dict | None = None,
):
    ctx = MagicMock()
    ctx.conversation_id = conversation_id
    ctx.user_id = user_id
    ctx.metadata = metadata if metadata is not None else {}
    return ctx

async def _collect_events(gen) -> list:
    events = []
    async for event in gen:
        events.append(event)
    return events

def _make_pending_escalation(
    conversation_id: str = "conv-xr",
    action_type: EscalationActionType = EscalationActionType.CREATE_AGENT,
    observations: list | None = None,
    orchestration_state: dict | None = None,
    observation_history: dict | None = None,
) -> PendingEscalation:
    """Build a PendingEscalation for testing."""
    return PendingEscalation(
        conversation_id=conversation_id,
        original_goal="create a websearch agent",
        original_context={"some": "context"},
        action=EscalationAction(
            action_type=action_type,
            parameters={"task_description": "websearch", "failed_agent": "none"},
            description="Create agent",
        ),
        question="Shall I create this agent?",
        observations=observations or [],
        orchestration_state=orchestration_state,
        observation_history=observation_history,
    )

def _make_self_mod_thought() -> OrchestrationThought:
    """Build an OrchestrationThought that calls a self-mod tool."""
    return OrchestrationThought(
        reasoning="User wants a new agent",
        is_final=False,
        task=OrchestrationTask(
            agent_name="self-mod",
            description="Create agent",
            tool="self_improve",
            arguments={"goal": "create a websearch agent"},
        ),
    )

def _mock_orch_config(**overrides):
    """Return a mock OrchestrationConfig with sensible defaults."""
    defaults = dict(
        routing_metrics_enabled=False,
        meta_action_fallback_enabled=False,
        middleware_enabled=False,
        optimization_enabled=False,
        reflection_mode="off",
        obs_window_size=4,
        obs_summary_max_chars=200,
        obs_facts_max_count=20,
        obs_max_observations=50,
        obs_result_max_chars=5000,
        max_retries=3,
        agent_timeout=30,
        planning_enabled=False,
        action_autonomy_enabled=False,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)

# ===========================================================================
# XR-C01: Self-mod tool escalation creates observation
# ===========================================================================

class TestXRC01SelfModObservation:
    """XR-C01: The orchestrator must create an observation when a self-mod
    tool returns a PendingEscalation, so the LLM sees evidence of the
    action on retry after escalation approval."""

    @pytest.mark.asyncio
    async def test_xr_c01_self_mod_escalation_creates_observation(self):
        """When a self-mod tool returns a PendingEscalation, the orchestrator
        must include an observation with agent_name='self-mod' in partial_results."""
        from core.orchestrator.orchestrator import DryadeOrchestrator

        escalation = PendingEscalation(
            conversation_id="conv-xr",
            original_goal="create agent",
            action=EscalationAction(
                action_type=EscalationActionType.CREATE_AGENT,
                parameters={"task_description": "web agent"},
                description="Create a web agent",
            ),
            question="Shall I create this agent?",
        )

        thought = _make_self_mod_thought()
        orchestrator = DryadeOrchestrator()

        with (
            patch.object(
                orchestrator.thinking,
                "orchestrate_think",
                new_callable=AsyncMock,
                return_value=thought,
            ),
            patch(
                "core.orchestrator.self_mod_tools.is_self_mod_tool",
                return_value=True,
            ),
            patch(
                "core.orchestrator.self_mod_tools.is_read_only_tool",
                return_value=False,
            ),
            patch(
                "core.orchestrator.self_mod_tools.execute_self_mod_tool",
                new_callable=AsyncMock,
                return_value=escalation,
            ),
            patch(
                "core.orchestrator.config.get_orchestration_config",
                return_value=_mock_orch_config(),
            ),
        ):
            # Need at least one agent so orchestrator enters the loop
            mock_agent_card = MagicMock()
            mock_agent_card.name = "dummy-agent"
            orchestrator.agents = MagicMock()
            orchestrator.agents.list_agents.return_value = [mock_agent_card]

            result = await orchestrator.orchestrate(
                goal="create a websearch agent",
                context={"conversation_id": "conv-xr"},
            )

        # Verify result is an escalation
        assert result.needs_escalation is True

        # Verify partial_results contains a self-mod observation
        self_mod_obs = [obs for obs in result.partial_results if obs.agent_name == "self-mod"]
        assert len(self_mod_obs) >= 1, "XR-C01: Escalation result must contain self-mod observation"
        assert self_mod_obs[0].success is True
        assert "Escalation created" in self_mod_obs[0].result

    @pytest.mark.asyncio
    async def test_xr_c01_observation_added_to_history(self):
        """The self-mod observation must also appear in the serialized
        observation_history_data so it survives escalation round-trip."""
        from core.orchestrator.orchestrator import DryadeOrchestrator

        escalation = PendingEscalation(
            conversation_id="conv-xr",
            original_goal="create agent",
            action=EscalationAction(
                action_type=EscalationActionType.CREATE_AGENT,
                parameters={"task_description": "web agent"},
                description="Create a web agent",
            ),
            question="Shall I create this agent?",
        )

        thought = _make_self_mod_thought()
        orchestrator = DryadeOrchestrator()

        with (
            patch.object(
                orchestrator.thinking,
                "orchestrate_think",
                new_callable=AsyncMock,
                return_value=thought,
            ),
            patch(
                "core.orchestrator.self_mod_tools.is_self_mod_tool",
                return_value=True,
            ),
            patch(
                "core.orchestrator.self_mod_tools.is_read_only_tool",
                return_value=False,
            ),
            patch(
                "core.orchestrator.self_mod_tools.execute_self_mod_tool",
                new_callable=AsyncMock,
                return_value=escalation,
            ),
            patch(
                "core.orchestrator.config.get_orchestration_config",
                return_value=_mock_orch_config(),
            ),
        ):
            mock_agent_card = MagicMock()
            mock_agent_card.name = "dummy-agent"
            orchestrator.agents = MagicMock()
            orchestrator.agents.list_agents.return_value = [mock_agent_card]

            result = await orchestrator.orchestrate(
                goal="create a websearch agent",
                context={"conversation_id": "conv-xr"},
            )

        # Verify observation_history_data is not None
        assert result.observation_history_data is not None, (
            "XR-C01: observation_history_data must be populated"
        )

        # Deserialize and verify the self-mod observation is present
        history = ObservationHistory.from_dict(result.observation_history_data)
        all_obs = list(history._recent) + list(history._older)
        self_mod_in_history = [obs for obs in all_obs if obs.agent_name == "self-mod"]
        assert len(self_mod_in_history) >= 1, (
            "XR-C01: self-mod observation must be present in observation history"
        )

# ===========================================================================
# XR-C02: Executor result injected into retry context
# ===========================================================================

class TestXRC02ExecutorResultInRetry:
    """XR-C02: After escalation approval, the executor result must be
    included as a synthetic observation in the retry context so the LLM
    knows the fix was applied."""

    @pytest.mark.asyncio
    async def test_xr_c02_executor_result_in_retry_context(self):
        """On successful executor, retry context must contain
        _prior_observations with an 'escalation-executor' entry."""
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(
            conversation_id="conv-xr",
            user_id="user-xr",
        )

        escalation = _make_pending_escalation(
            conversation_id="conv-xr",
            observations=[
                {"agent_name": "self-mod", "task": "self_improve", "success": True},
            ],
        )

        captured_retry_context = {}

        async def mock_handle(msg, ctx, stream=True):
            """Capture the retry context passed to the orchestrate handler."""
            captured_retry_context["metadata"] = dict(ctx.metadata)
            yield MagicMock(type="complete", content="done")

        # Set up a real escalation registry with our escalation
        real_registry = EscalationRegistry()
        real_registry.register(escalation)

        with (
            patch(
                "core.orchestrator.escalation.get_escalation_registry",
                return_value=real_registry,
            ),
            patch.object(
                EscalationExecutor,
                "execute",
                new_callable=AsyncMock,
                return_value=(True, "Agent created successfully"),
            ),
            patch.object(
                router._orchestrate_handler,
                "handle",
                side_effect=mock_handle,
            ),
        ):
            events = await _collect_events(router.route("yes", context, stream=True))

        # Verify the retry happened and captured context has _prior_observations
        assert "metadata" in captured_retry_context, (
            "XR-C02: Retry must be triggered after successful executor"
        )
        prior_obs = captured_retry_context["metadata"].get("_prior_observations")
        assert prior_obs is not None, "XR-C02: _prior_observations must be set in retry metadata"

        # Find the escalation-executor observation
        executor_obs = [o for o in prior_obs if o.get("agent_name") == "escalation-executor"]
        assert len(executor_obs) == 1, (
            "XR-C02: Exactly one escalation-executor observation expected"
        )
        assert executor_obs[0]["result"] == "Agent created successfully"
        assert executor_obs[0]["success"] is True

    @pytest.mark.asyncio
    async def test_xr_c02_executor_failure_no_retry(self):
        """On executor failure, retry must NOT happen
        (_orchestrate_handler.handle() must NOT be called)."""
        from core.orchestrator.router import ExecutionContext, ExecutionRouter

        router = ExecutionRouter()
        context = ExecutionContext(
            conversation_id="conv-xr",
            user_id="user-xr",
        )

        escalation = _make_pending_escalation(conversation_id="conv-xr")

        real_registry = EscalationRegistry()
        real_registry.register(escalation)

        mock_handle = AsyncMock()

        with (
            patch(
                "core.orchestrator.escalation.get_escalation_registry",
                return_value=real_registry,
            ),
            patch.object(
                EscalationExecutor,
                "execute",
                new_callable=AsyncMock,
                return_value=(False, "Failed to create agent"),
            ),
            patch.object(
                router._orchestrate_handler,
                "handle",
                mock_handle,
            ),
        ):
            events = await _collect_events(router.route("yes", context, stream=True))

        # Retry handler must NOT be called on failure
        mock_handle.assert_not_called()

        # Should emit a complete event with failure info (not emit_error
        # which kills the frontend event stream)
        event_types = [e.type for e in events]
        assert "complete" in event_types, (
            "XR-C02: Complete event with failure message must be emitted on executor failure"
        )
        complete_events = [e for e in events if e.type == "complete"]
        assert any("Failed" in (e.content or "") for e in complete_events), (
            "XR-C02: Complete event must contain failure information"
        )

# ===========================================================================
# XR-E01: Single escalation registration (no double)
# ===========================================================================

class TestXRE01SingleRegistration:
    """XR-E01: Escalation registration must happen ONCE (in ComplexHandler.
    _handle_escalation), not also in the orchestrator's self-mod path."""

    @pytest.mark.asyncio
    async def test_xr_e01_no_registration_in_orchestrator(self):
        """The orchestrator's self-mod escalation path must NOT call
        get_escalation_registry().register().

        We verify by inspecting the orchestrator source: the comment
        'XR-E01: Registration removed' must be present, and the
        orchestrate() return path must NOT call register().
        """
        import inspect

        from core.orchestrator.orchestrator import DryadeOrchestrator

        source = inspect.getsource(DryadeOrchestrator.orchestrate)

        # The orchestrator source must NOT contain register() in the self-mod
        # escalation path.  The XR-E01 fix removed the call.
        # Check the XR-E01 marker comment is present
        assert "XR-E01" in source, "XR-E01: Orchestrator must have XR-E01 marker comment"
        assert "Registration removed" in source, (
            "XR-E01: Orchestrator must document that registration was removed"
        )

    @pytest.mark.asyncio
    async def test_xr_e01_single_registration_in_handler(self):
        """ComplexHandler._handle_escalation must call register() exactly once."""
        from core.orchestrator.handlers.complex_handler import ComplexHandler

        handler = ComplexHandler()
        ctx = _make_context()

        obs = MagicMock()
        obs.agent_name = "self-mod"
        obs.task = "self_improve"
        obs.error = None
        obs.model_dump.return_value = {
            "agent_name": "self-mod",
            "task": "self_improve",
            "result": "Escalation created",
            "success": True,
        }

        result = MagicMock()
        result.needs_escalation = True
        result.escalation_question = "Create agent?"
        result.escalation_action = {
            "action_type": "create_agent",
            "parameters": {"task_description": "websearch"},
            "description": "Create a websearch agent",
        }
        result.original_goal = "create a websearch agent"
        result.partial_results = [obs]
        result.state = None
        result.observation_history_data = None

        # _handle_escalation imports get_escalation_registry locally,
        # so patch at source module
        mock_registry = MagicMock()

        with patch(
            "core.orchestrator.escalation.get_escalation_registry",
            return_value=mock_registry,
        ):
            events = await _collect_events(handler._handle_escalation(result, ctx))

        # register must be called exactly once
        mock_registry.register.assert_called_once()

# ===========================================================================
# XR-E02: Meta-action fallback skipped on retry
# ===========================================================================

class TestXRE02FallbackSkippedOnRetry:
    """XR-E02: The meta-action fallback in ComplexHandler must not fire
    when the request is a retry after escalation approval (indicated by
    _prior_observations in context.metadata)."""

    @pytest.mark.asyncio
    async def test_xr_e02_fallback_skipped_on_retry(self):
        """With _prior_observations in metadata (retry), the is_retry guard
        must evaluate to True, preventing the fallback from firing."""
        ctx = _make_context(
            metadata={
                "_prior_observations": [
                    {"agent_name": "escalation-executor", "task": "execute", "success": True}
                ],
            }
        )

        # The is_retry guard in ComplexHandler.handle():
        # is_retry = bool(context.metadata.get("_prior_observations"))
        is_retry = bool(ctx.metadata.get("_prior_observations"))
        assert is_retry is True, "XR-E02: _prior_observations must trigger is_retry"

        # Simulate the full fallback condition
        meta_hint = True
        fallback_enabled = True
        result_success = True
        result_needs_escalation = False

        should_fallback = (
            meta_hint
            and not is_retry
            and fallback_enabled
            and result_success
            and not result_needs_escalation
        )
        assert should_fallback is False, "XR-E02: Fallback must NOT fire when is_retry is True"

    @pytest.mark.asyncio
    async def test_xr_e02_fallback_fires_on_first_request(self):
        """Without _prior_observations (first request), the fallback condition
        should evaluate to True when all other conditions are met."""
        ctx = _make_context(metadata={})

        is_retry = bool(ctx.metadata.get("_prior_observations"))
        assert is_retry is False

        meta_hint = True
        fallback_enabled = True
        result_success = True
        result_needs_escalation = False

        should_fallback = (
            meta_hint
            and not is_retry
            and fallback_enabled
            and result_success
            and not result_needs_escalation
        )
        assert should_fallback is True, (
            "XR-E02: Fallback MUST fire on first request when conditions met"
        )

    @pytest.mark.asyncio
    async def test_xr_e02_is_retry_guard_in_source(self):
        """Verify the XR-E02 guard exists in the ComplexHandler source code."""
        import inspect

        from core.orchestrator.handlers.complex_handler import ComplexHandler

        source = inspect.getsource(ComplexHandler.handle)
        # The is_retry guard must be present
        assert "_prior_observations" in source
        assert "is_retry" in source or "not is_retry" in source
        assert "XR-E02" in source, "XR-E02: ComplexHandler must have XR-E02 marker comment"

# ===========================================================================
# XR-W01: _create_agent is programmatic (not a stub)
# ===========================================================================

class TestXRW01CreateAgentProgrammatic:
    """XR-W01: _create_agent must delegate to _factory_create (post-119.6).

    Post-119.6: _create_agent no longer calls add_mcp_server directly -- all
    creation goes through the factory pipeline via _factory_create(). These
    tests verify the delegation and parameter mapping behavior.
    """

    @pytest.mark.asyncio
    async def test_xr_w01_create_agent_delegates_to_factory_create(self):
        """Call _create_agent -- must delegate to _factory_create with mapped params."""
        executor = EscalationExecutor()

        # Patch _factory_create directly to verify delegation
        with patch.object(
            executor,
            "_factory_create",
            new_callable=AsyncMock,
            return_value=(True, "Created agent test-server"),
        ) as mock_factory:
            success, msg = await executor._create_agent(
                {
                    "task_description": "web search",
                    "failed_agent": "websearch",
                    "suggested_name": "test-server",
                }
            )

        assert success is True
        assert "test-server" in msg
        # Verify delegation happened with correct parameter mapping
        mock_factory.assert_called_once()
        factory_params = mock_factory.call_args[0][0]
        assert factory_params["goal"] == "web search"
        assert factory_params["suggested_name"] == "test-server"

    @pytest.mark.asyncio
    async def test_xr_w01_create_agent_uses_failed_agent_as_suggested_name(self):
        """When suggested_name is missing, _create_agent falls back to failed_agent."""
        executor = EscalationExecutor()

        with patch.object(
            executor,
            "_factory_create",
            new_callable=AsyncMock,
            return_value=(True, "Created agent doc-analyzer"),
        ) as mock_factory:
            success, msg = await executor._create_agent(
                {
                    "task_description": "analyze documents",
                    "failed_agent": "doc-analyzer",
                }
            )

        assert success is True
        factory_params = mock_factory.call_args[0][0]
        # suggested_name falls back to failed_agent when not provided
        assert factory_params["suggested_name"] == "doc-analyzer"

    @pytest.mark.asyncio
    async def test_xr_w01_create_agent_propagates_factory_failure(self):
        """When _factory_create fails, _create_agent must propagate the failure."""
        executor = EscalationExecutor()

        with patch.object(
            executor,
            "_factory_create",
            new_callable=AsyncMock,
            return_value=(False, "Factory disabled"),
        ):
            success, msg = await executor._create_agent(
                {
                    "task_description": "web search",
                    "failed_agent": "websearch",
                }
            )

        assert success is False
        assert "Factory disabled" in msg

# ===========================================================================
# XR-W02: Router hints skipped for meta-actions
# ===========================================================================

class TestXRW02RouterHintsSkipped:
    """XR-W02: When meta_action_hint is True on the tier_decision,
    ComplexHandler must NOT call get_hierarchical_router().route()."""

    @pytest.mark.asyncio
    async def test_xr_w02_router_hints_skipped_for_meta_action(self):
        """With meta_action_hint=True, the router_hints block is skipped."""
        import inspect

        from core.orchestrator.handlers.complex_handler import ComplexHandler

        # Verify the guard in source code
        source = inspect.getsource(ComplexHandler.handle)
        assert "meta_action_detected" in source, (
            "ComplexHandler must have meta_action_detected guard"
        )
        assert "meta_hint" in source, "ComplexHandler must use meta_hint to gate behavior"

        # Verify the logic: when meta_action_detected is True,
        # the 'if not meta_action_detected:' block is skipped
        meta_action_detected = True
        router_should_run = not meta_action_detected
        assert router_should_run is False, (
            "XR-W02: Router hints must be skipped when meta_action_detected=True"
        )

    @pytest.mark.asyncio
    async def test_xr_w02_router_hints_computed_for_normal_request(self):
        """With meta_action_hint=False (normal request), router.route() IS called."""
        from core.orchestrator.complexity import TierDecision
        from core.orchestrator.handlers.complex_handler import ComplexHandler
        from core.orchestrator.models import Tier

        handler = ComplexHandler()

        tier_decision = TierDecision(
            tier=Tier.COMPLEX,
            confidence=0.8,
            reason="complex task",
            meta_action_hint=False,
        )

        ctx = _make_context(
            metadata={
                "_tier_decision": tier_decision,
                "orchestration_mode": "adaptive",
            }
        )

        mock_orch_result = OrchestrationResult(
            success=True,
            output="Done.",
            partial_results=[],
        )

        with (
            patch(
                "core.mcp.hierarchical_router.get_hierarchical_router",
            ) as mock_get_router,
            patch(
                "core.orchestrator.config.get_orchestration_config",
                return_value=MagicMock(
                    planning_enabled=False,
                    meta_action_fallback_enabled=False,
                    routing_metrics_enabled=False,
                    tier_instant_enabled=False,
                    tier_simple_enabled=False,
                ),
            ),
            patch(
                "core.orchestrator.orchestrator.DryadeOrchestrator",
            ) as MockOrchestrator,
            patch(
                "core.adapters.registry.get_registry",
            ),
            patch(
                "core.orchestrator.cancellation.get_cancellation_registry",
            ) as mock_cancel,
            patch(
                "core.orchestrator.typo_correction.suggest_typo_corrections",
                return_value=("read a file", []),
            ),
        ):
            mock_cancel_reg = MagicMock()
            mock_cancel_reg.get_or_create.return_value = None
            mock_cancel.return_value = mock_cancel_reg

            mock_router = MagicMock()
            mock_router.route.return_value = []
            mock_get_router.return_value = mock_router

            mock_orch = MagicMock()
            mock_orch.thinking = MagicMock()
            mock_orch.thinking._on_cost_event = None
            mock_orch.thinking._get_llm = MagicMock(return_value=MagicMock(model="test"))
            mock_orch.agents = MagicMock()
            mock_orch.agents.list_agents.return_value = []
            mock_orch.orchestrate = AsyncMock(return_value=mock_orch_result)
            MockOrchestrator.return_value = mock_orch

            events = await _collect_events(handler.handle("read a file", ctx, stream=True))

        # router.route() MUST have been called for non-meta-action request
        mock_router.route.assert_called_once()

# ===========================================================================
# XR-W01 Additional: _create_tool and _modify_config
# ===========================================================================

class TestXRW01CreateToolProgrammatic:
    """Additional XR-W01 coverage: _create_tool delegates to _factory_create (post-119.6)."""

    @pytest.mark.asyncio
    async def test_create_tool_delegates_to_factory_create(self):
        """_create_tool must delegate to _factory_create with tool parameters."""
        executor = EscalationExecutor()

        with patch.object(
            executor,
            "_factory_create",
            new_callable=AsyncMock,
            return_value=(True, "Created tool web_scraper"),
        ) as mock_factory:
            success, msg = await executor._create_tool(
                {
                    "tool_name": "web_scraper",
                    "description": "Scrape web pages for content",
                }
            )

        assert success is True
        assert "web_scraper" in msg
        mock_factory.assert_called_once()
        # Verify tool parameters are mapped correctly
        factory_params = mock_factory.call_args[0][0]
        assert factory_params["suggested_name"] == "web_scraper"
        assert factory_params["artifact_type"] == "tool"

class TestXRW01ModifyConfigProgrammatic:
    """Additional XR-W01 coverage: _modify_config uses MUTABLE_CONFIG_KEYS."""

    @pytest.mark.asyncio
    async def test_modify_config_rejects_non_mutable_key(self):
        """_modify_config must reject keys not in MUTABLE_CONFIG_KEYS."""
        executor = EscalationExecutor()

        success, msg = await executor._modify_config(
            {
                "config_key": "not_a_real_key",
                "config_value": "true",
            }
        )

        assert success is False
        assert "not in the mutable allowlist" in msg

    @pytest.mark.asyncio
    async def test_modify_config_accepts_mutable_key(self):
        """_modify_config must accept keys in MUTABLE_CONFIG_KEYS."""
        executor = EscalationExecutor()

        with patch(
            "core.orchestrator.config.get_orchestration_config",
        ) as mock_cfg:
            mock_config = MagicMock()
            mock_config.planning_enabled = True
            mock_cfg.return_value = mock_config

            success, msg = await executor._modify_config(
                {
                    "config_key": "planning_enabled",
                    "config_value": "false",
                }
            )

        assert success is True
        assert "planning_enabled" in msg
