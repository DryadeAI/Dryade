"""COMPLEX tier handler + TierDispatcher.

ComplexHandler: Full orchestrator path (ReAct/PLAN modes) for multi-step
goals requiring agent coordination, planning, and escalation.

TierDispatcher: Top-level dispatcher that classifies tiers and delegates
to InstantHandler, SimpleHandler, or ComplexHandler.  The router
instantiates TierDispatcher instead of the old monolithic OrchestrateHandler.

Phase 89-93: Tiered dispatch architecture (INSTANT/SIMPLE/COMPLEX).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from core.extensions.events import (
    ChatEvent,
    emit_agent_complete,
    emit_agent_start,
    emit_complete,
    emit_error,
    emit_plan_preview,
    emit_progress,
    emit_thinking,
    emit_token,
    emit_tool_result,
    emit_tool_start,
)
from core.orchestrator.complexity import TierDecision
from core.orchestrator.handlers._utils import (
    _emit_escalation,
    _emit_reasoning,
    _emit_resource_suggestion,
    _should_emit,
)
from core.orchestrator.handlers.base import OrchestrateHandlerBase

if TYPE_CHECKING:
    from core.orchestrator.orchestrator import DryadeOrchestrator
    from core.orchestrator.router import ExecutionContext

logger = logging.getLogger("dryade.router.orchestrate.complex")

class ComplexHandler(OrchestrateHandlerBase):
    """Handle COMPLEX tier -- full orchestrator path.

    Uses DryadeOrchestrator to coordinate agents across frameworks
    for complex multi-step tasks.

    Features:
        - Dynamic agent selection and coordination
        - Escalation handling (inline in chat)
        - MCP resource suggestions (confirm before use)
        - Configurable reasoning visibility
        - Partial result streaming
    """

    async def handle(
        self,
        message: str,
        context: "ExecutionContext",
        stream: bool = True,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle COMPLEX tier message -- native Dryade orchestration.

        Args:
            message: User goal/request to accomplish.
            context: Execution context with preferences.
            stream: Whether to stream output token-by-token.

        Yields:
            ChatEvent: Progress, agent, reasoning, escalation, complete, or error events.
        """
        from core.adapters.registry import get_registry
        from core.autonomous.leash import (
            LEASH_CONSERVATIVE,
            LEASH_PERMISSIVE,
            LEASH_STANDARD,
            LeashConfig,
        )
        from core.orchestrator.cancellation import get_cancellation_registry
        from core.orchestrator.complexity import ComplexityEstimator, PlanningMode
        from core.orchestrator.config import get_orchestration_config
        from core.orchestrator.models import OrchestrationMode, Tier
        from core.orchestrator.orchestrator import DryadeOrchestrator
        from core.orchestrator.typo_correction import suggest_typo_corrections

        # Typo detection for common paths (F-002)
        corrected_message, typo_corrections = suggest_typo_corrections(message)
        if typo_corrections:
            logger.info(f"[ORCHESTRATE] Typo corrections applied: {', '.join(typo_corrections)}")
            message = corrected_message

        # Feature flag for planning layer (default: enabled)
        cfg = get_orchestration_config()
        planning_enabled = cfg.planning_enabled

        # Determine orchestration mode from context
        mode_str = context.metadata.get("orchestration_mode", "adaptive")
        try:
            orch_mode = OrchestrationMode(mode_str)
        except ValueError:
            orch_mode = OrchestrationMode.ADAPTIVE

        # Get user preferences per user decisions
        memory_enabled = context.metadata.get("memory_enabled", True)
        reasoning_visibility = context.metadata.get("reasoning_visibility", "summary")
        agent_filter = context.metadata.get("agent_filter")

        logger.info(
            f"[ORCHESTRATE] COMPLEX mode: goal='{message[:50]}...', "
            f"mode={orch_mode.value}, memory={memory_enabled}, filter={agent_filter}"
        )

        # Get agent list from registry
        registry = get_registry()
        agent_cards = registry.list_agents()

        # Retrieve tier_decision from context metadata (set by TierDispatcher)
        tier_decision: TierDecision | None = context.metadata.get("_tier_decision")

        # --- Meta-action hint (Phase 115.1) ---
        # When complexity estimator detected a meta-action pattern, pass the hint
        # to the orchestrator so self-mod tools are injected. LLM decides action.
        meta_action_detected = (
            getattr(tier_decision, "meta_action_hint", False) if tier_decision else False
        )
        meta_hint = meta_action_detected
        if meta_hint:
            context.metadata["_meta_action_hint"] = True
            logger.info(f"[ORCHESTRATE] Meta-action hint active for: '{message[:80]}'")

        # Router hints for COMPLEX tier (ADR-001 Part E, zero LLM cost)
        # Phase 167: Router hints run for ALL requests (including meta-actions).
        # With always-inject, meta-actions are no longer a special case that needs
        # to skip routing -- the LLM will naturally choose self-mod tools if needed.
        router_hints: list[dict[str, str]] | None = None
        try:
            from core.mcp.hierarchical_router import get_hierarchical_router

            router = get_hierarchical_router()
            router_results = router.route(message, top_k=10)
            if router_results:
                router_hints = [
                    {
                        "tool_name": r.tool_name,
                        "server": r.server,
                        "score": f"{r.score:.2f}",
                        "description": r.description or "",
                    }
                    for r in router_results[:10]
                ]
        except Exception:
            logger.debug("[ORCHESTRATE] Router hints unavailable, proceeding without")

        # Leash preset wiring (F-007) -- apply frontend leash_preset to orchestrator
        LEASH_PRESETS: dict[str, LeashConfig] = {
            "conservative": LEASH_CONSERVATIVE,
            "standard": LEASH_STANDARD,
            "permissive": LEASH_PERMISSIVE,
        }
        leash_preset = context.metadata.get("leash_preset", "standard")
        leash = LEASH_PRESETS.get(leash_preset, LEASH_STANDARD)

        orchestrator = DryadeOrchestrator(agent_registry=registry, leash=leash)

        # Use tier_decision.sub_mode for COMPLEX, fall back to estimator if needed
        if planning_enabled:
            if (
                tier_decision is not None
                and tier_decision.tier == Tier.COMPLEX
                and tier_decision.sub_mode is not None
            ):
                decision = type(
                    "PlanningDecision",
                    (),
                    {
                        "mode": tier_decision.sub_mode,
                        "confidence": tier_decision.confidence,
                        "reason": tier_decision.reason,
                    },
                )()
            else:
                # SIMPLE treated as COMPLEX: run estimate() for sub-mode
                estimator = ComplexityEstimator()
                decision = estimator.estimate(message, agent_cards)
            logger.info(
                f"[ORCHESTRATE] Complexity: mode={decision.mode.value}, "
                f"confidence={decision.confidence:.2f}, reason={decision.reason}"
            )
        else:
            decision = None

        # Set up cancellation support
        cancel_registry = get_cancellation_registry()
        cancel_event = cancel_registry.get_or_create(context.conversation_id)

        # Check for MCP resources and suggest if available
        async for event in self._suggest_mcp_resources_if_available(orchestrator, context):
            yield event

        # Queue for real-time event streaming from orchestration callbacks
        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

        # Accumulate token counts across all LLM calls for the final response
        accumulated_prompt_tokens = 0
        accumulated_completion_tokens = 0

        # Wire cost_update events from the ThinkingProvider into the SSE queue
        # AND persist to database for historical cost reporting.
        def _handle_cost_event(event: ChatEvent) -> None:
            nonlocal accumulated_prompt_tokens, accumulated_completion_tokens
            queue.put_nowait(event)
            # Accumulate token counts for the final emit_complete usage field
            meta = event.metadata or {}
            accumulated_prompt_tokens += meta.get("prompt_tokens", 0)
            accumulated_completion_tokens += meta.get("completion_tokens", 0)
            # Persist ThinkingProvider costs to database
            try:
                from core.extensions import record_cost
                from core.providers.cost_context import get_cost_user_id

                # Get model name from the ThinkingProvider's LLM instance
                llm = orchestrator.thinking._get_llm()
                model_name = getattr(llm, "model", None) or "thinking_provider"
                record_cost(
                    model=model_name,
                    input_tokens=meta.get("prompt_tokens", 0),
                    output_tokens=meta.get("completion_tokens", 0),
                    agent="thinking_provider",
                    user_id=get_cost_user_id(),
                    conversation_id=context.conversation_id,
                )
            except Exception:
                pass  # Cost tracking must never break orchestration

        orchestrator.thinking._on_cost_event = _handle_cost_event

        def on_thinking(reasoning: str) -> None:
            """Callback to stream thinking events in real-time."""
            queue.put_nowait(emit_thinking(reasoning))

        def on_agent_event(event_type: str, data: dict) -> None:
            """Callback to stream agent lifecycle events in real-time."""
            if event_type == "agent_start":
                queue.put_nowait(
                    emit_agent_start(
                        data.get("agent", ""),
                        data.get("task", ""),
                    )
                )
                # Emit tool_start so chat.py can pair with tool_result
                queue.put_nowait(
                    emit_tool_start(
                        tool=data.get("agent", "unknown"),
                        args={"task": data.get("task", "")},
                    )
                )
            elif event_type == "agent_complete":
                if data.get("success", True):
                    queue.put_nowait(
                        emit_agent_complete(
                            data.get("agent", ""),
                            data.get("result", "Completed"),
                            data.get("duration_ms", 0),
                        )
                    )
                else:
                    queue.put_nowait(
                        emit_error(
                            f"Agent {data.get('agent', '')} failed: {data.get('error', 'Unknown')}",
                            "AGENT_ERROR",
                        )
                    )
                # Emit tool_result paired with the tool_start from agent_start
                queue.put_nowait(
                    emit_tool_result(
                        tool=data.get("agent", "unknown"),
                        result=data.get("result", data.get("error", "")),
                        duration_ms=data.get("duration_ms", 0),
                        success=data.get("success", True),
                    )
                )

        def on_plan_event(event_type: str, data: dict) -> None:
            """Callback for plan-level events (plan_preview, progress)."""
            if event_type == "plan_preview":
                queue.put_nowait(
                    emit_plan_preview(
                        steps=data.get("steps", []),
                        estimated_duration_s=data.get("total_estimated_seconds"),
                    )
                )
            elif event_type == "progress":
                queue.put_nowait(
                    emit_progress(
                        current_step=data.get("step_index", 0),
                        total_steps=data.get("total_steps", 0),
                        current_agent=data.get("step_name", ""),
                        eta_seconds=None,
                    )
                )

        # Store result/error from the orchestration task
        orch_result = None
        orch_error = None

        # Determine whether to use PlanningOrchestrator or DryadeOrchestrator
        use_planning = (
            (decision is not None and decision.mode == PlanningMode.PLAN)
            if planning_enabled
            else False
        )

        def on_token_cb(token_content: str) -> None:
            """Callback to stream real LLM tokens in real-time."""
            queue.put_nowait(emit_token(token_content))

        async def run_orchestration() -> None:
            nonlocal orch_result, orch_error
            try:
                if meta_hint:
                    queue.put_nowait(
                        emit_thinking("Analyzing request to determine capabilities needed...")
                    )

                if use_planning:
                    # PLAN mode: use PlanningOrchestrator
                    from core.orchestrator.context import OrchestrationContext
                    from core.orchestrator.planning import PlanningOrchestrator

                    orch_context = OrchestrationContext(
                        initial_state={
                            "conversation_id": context.conversation_id,
                            "user_id": context.user_id,
                            "memory_enabled": memory_enabled,
                            "reasoning_visibility": reasoning_visibility,
                            "planning_decision": "plan",
                            "_router_hints": router_hints,
                            **context.metadata,
                        }
                    )
                    planning_orchestrator = PlanningOrchestrator(
                        thinking_provider=orchestrator.thinking,
                        base_orchestrator=orchestrator,
                    )
                    orch_result = await planning_orchestrator.orchestrate(
                        goal=message,
                        context=orch_context,
                        on_thinking=on_thinking,
                        on_agent_event=on_agent_event,
                        on_plan_event=on_plan_event,
                        cancel_event=cancel_event,
                        on_token=on_token_cb,
                    )
                else:
                    # REACT / DEFER / disabled: use DryadeOrchestrator
                    orch_result = await orchestrator.orchestrate(
                        goal=message,
                        context={
                            "conversation_id": context.conversation_id,
                            "user_id": context.user_id,
                            "memory_enabled": memory_enabled,
                            "reasoning_visibility": reasoning_visibility,
                            "planning_decision": decision.mode.value if decision else "disabled",
                            "_router_hints": router_hints,
                            **context.metadata,
                        },
                        mode=orch_mode,
                        agent_filter=agent_filter,
                        on_thinking=on_thinking,
                        on_agent_event=on_agent_event,
                        on_token=on_token_cb,
                        cancel_event=cancel_event,
                    )
            except Exception as e:
                orch_error = e
            finally:
                cancel_registry.clear(context.conversation_id)
                queue.put_nowait(None)  # Sentinel to signal completion

        # Launch orchestration as a background task
        task = asyncio.create_task(run_orchestration())

        # Event visibility level (separate from reasoning_visibility)
        event_visibility = context.metadata.get("event_visibility", "named-steps")

        try:
            # Stream events in real-time as they arrive
            # Apply visibility filter to gate which events reach SSE stream
            while True:
                event = await queue.get()
                if event is None:
                    break
                if _should_emit(event.type, event_visibility) or event.type in (
                    "tool_start",
                    "tool_result",
                ):
                    yield event

            # Ensure task has completed (should already be done)
            await task

            # Handle orchestration error
            if orch_error is not None:
                logger.exception(f"[ORCHESTRATE] Orchestration error: {orch_error}")
                yield emit_error(
                    f"Orchestration error: {type(orch_error).__name__}: {str(orch_error)}",
                    "ORCHESTRATION_ERROR",
                )
                return

            result = orch_result

            # --- Meta-action fallback (Phase 115.1) ---
            # If hint was active but LLM didn't use self-mod tools and didn't escalate,
            # fall back to programmatic escalation (safety net for weak models).
            from core.orchestrator.config import get_orchestration_config

            _cfg = get_orchestration_config()

            # XR-E02: Skip meta-action fallback on escalation retries.
            # On retry after escalation approval, context.metadata contains
            # _prior_observations from the executor.  The same message gets
            # re-classified with meta_hint=True, but the fallback should NOT
            # fire again since the action was already approved and executed.
            is_retry = bool(context.metadata.get("_prior_observations"))

            # Phase 167: Fallback only fires for text-only providers where self-mod
            # tools couldn't be injected. Function-calling providers get always-inject
            # -- if the LLM chose not to call them, trust its judgment.
            self_mod_tools_were_injected = context.metadata.get("_self_mod_tools_injected", False)

            if (
                meta_hint
                and not self_mod_tools_were_injected  # Only fire for text-only providers
                and not is_retry  # XR-E02: don't fire on retries
                and _cfg.meta_action_fallback_enabled
                and result is not None
                and result.success
                and not result.needs_escalation
            ):
                # Check if any observation used a self-mod tool
                from core.orchestrator.self_mod_tools import is_self_mod_tool

                used_self_mod = any(
                    is_self_mod_tool(getattr(obs, "tool_called", None))
                    for obs in (result.partial_results or [])
                )
                if not used_self_mod:
                    logger.info(
                        "[ORCHESTRATE] Meta-action fallback: hint fired but LLM "
                        "didn't use self-mod tools, falling back to programmatic escalation"
                    )
                    if _cfg.routing_metrics_enabled:
                        from core.orchestrator.routing_metrics import record_routing_metric

                        record_routing_metric(
                            message=message,
                            hint_fired=True,
                            hint_type="meta_action",
                            fallback_activated=True,
                        )
                    async for event in self._handle_meta_action(message, context, tier_decision):
                        yield event
                    return

            # Record routing metric for hint-active requests that didn't fallback
            if meta_hint and _cfg.routing_metrics_enabled:
                from core.orchestrator.routing_metrics import record_routing_metric

                record_routing_metric(
                    message=message,
                    hint_fired=True,
                    hint_type="meta_action",
                    llm_tool_called="self_mod" if result and result.needs_escalation else None,
                    fallback_activated=False,
                )

            # Handle escalation (per user decision: inline in chat)
            if result.needs_escalation:
                async for event in self._handle_escalation(result, context):
                    yield event
                return

            if result.success:
                usage = {
                    "prompt_tokens": accumulated_prompt_tokens,
                    "completion_tokens": accumulated_completion_tokens,
                    "total_tokens": accumulated_prompt_tokens + accumulated_completion_tokens,
                }
                async for event in self._handle_success(
                    result,
                    stream,
                    reasoning_visibility,
                    accumulated_usage=usage,
                    orchestration_mode=orch_mode.value,
                ):
                    yield event
            else:
                yield emit_error(
                    f"Orchestration failed: {result.reason}",
                    "ORCHESTRATION_ERROR",
                )

        except Exception as e:
            logger.exception(f"[ORCHESTRATE] Orchestration error: {e}")
            task.cancel()
            yield emit_error(
                f"Orchestration error: {type(e).__name__}: {str(e)}",
                "ORCHESTRATION_ERROR",
            )
        finally:
            # BUG-011: Release LLM httpx clients to prevent connection pool
            # exhaustion after sequential agent invocations.
            try:
                await orchestrator.cleanup()
            except Exception:
                pass

    async def _handle_meta_action(
        self,
        message: str,
        context: "ExecutionContext",
        tier_decision: "TierDecision",
    ) -> AsyncGenerator[ChatEvent, None]:
        """Fallback escalation for meta-action requests when LLM doesn't use self-mod tools.

        When the meta-action hint was active but the LLM did not invoke any
        self-modification tool, this fallback builds a FACTORY_CREATE escalation
        to route the request through the Agent Factory pipeline.

        Post-119.6: Uses FACTORY_CREATE instead of CREATE_AGENT. The factory
        handles name extraction, framework selection, and MCP package resolution
        internally via LLM-driven config generation.

        Args:
            message: Original user message (e.g., "create a websearch agent").
            context: Execution context with conversation_id.
            tier_decision: TierDecision with meta_action_hint=True.

        Yields:
            ChatEvent: escalation + complete events.
        """
        from core.orchestrator.escalation import (
            EscalationAction,
            EscalationActionType,
            PendingEscalation,
            get_escalation_registry,
        )

        logger.info(
            f"[ORCHESTRATE] Meta-action intercepted: '{message[:80]}' "
            f"(confidence={tier_decision.confidence:.2f})"
        )

        # Phase 167: English regex removed. Factory handles name extraction internally
        # via LLM-driven config generation (language-agnostic).
        suggested_name = None

        logger.info("[ORCHESTRATE] Meta-action: delegating to FACTORY_CREATE (language-agnostic)")

        # Build FACTORY_CREATE escalation (factory handles all resolution internally)
        parameters: dict = {
            "goal": message,
            "suggested_name": suggested_name,
            "trigger": "meta_action",
            "conversation_id": context.conversation_id,
        }

        description = f"Agent Factory: {message[:200]}"
        question = f"**Agent Factory** → {message[:200]}\n\n✅ / ❌ ?"

        action = EscalationAction(
            action_type=EscalationActionType.FACTORY_CREATE,
            parameters=parameters,
            description=description,
        )

        escalation = PendingEscalation(
            conversation_id=context.conversation_id,
            original_goal=message,
            original_context=context.metadata,
            action=action,
            question=question,
        )

        get_escalation_registry().register(escalation)
        logger.info(
            f"[ORCHESTRATE] Registered meta-action FACTORY_CREATE escalation for "
            f"conversation {context.conversation_id}"
        )

        yield _emit_escalation(
            question=escalation.question,
            task_context=message,
            has_auto_fix=True,
            auto_fix_description=action.description,
        )
        yield emit_complete(
            response="",
            usage={"meta_action_intercepted": True},
        )

    async def _suggest_mcp_resources_if_available(
        self,
        orchestrator: "DryadeOrchestrator",
        context: "ExecutionContext",
    ) -> AsyncGenerator[ChatEvent, None]:
        """Check MCP agents for resources and emit suggestion if found.

        Per user decision: Suggest but confirm - don't use automatically.
        """
        try:
            agents = orchestrator.agents.list_agents()
            for agent_card in agents:
                if agent_card.framework.value == "mcp":
                    agent = orchestrator.agents.get(agent_card.name)
                    if agent and hasattr(agent, "list_resources"):
                        resources = await agent.list_resources()
                        if resources:
                            yield _emit_resource_suggestion(
                                resources=resources[:5],
                                agent_name=agent_card.name,
                            )
        except Exception as e:
            logger.debug(f"MCP resource check failed: {e}")

    async def _handle_escalation(
        self,
        result,  # OrchestrationResult
        context: "ExecutionContext",
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle escalation scenario.

        Emits context about what was tried before escalating.
        Registers pending escalation for automatic fix if user approves.
        """
        # Emit context about what we tried before escalating
        for obs in result.partial_results:
            yield emit_agent_start(obs.agent_name, obs.task)
            if obs.error:
                yield emit_thinking(f"Task failed: {obs.error}")

        # Register pending escalation for automatic fix if user approves
        if result.escalation_action and result.original_goal:
            from core.orchestrator.escalation import (
                EscalationAction,
                EscalationActionType,
                PendingEscalation,
                get_escalation_registry,
            )

            action = EscalationAction(
                action_type=EscalationActionType(result.escalation_action["action_type"]),
                parameters=result.escalation_action.get("parameters", {}),
                description=result.escalation_action.get("description", ""),
            )

            escalation = PendingEscalation(
                conversation_id=context.conversation_id,
                original_goal=result.original_goal,
                original_context=context.metadata,
                action=action,
                question=result.escalation_question or "How would you like to proceed?",
                observations=[
                    obs.model_dump(mode="json") for obs in (result.partial_results or [])
                ],
                orchestration_state=(
                    result.state.model_dump(mode="json") if result.state else None
                ),
                observation_history=result.observation_history_data,
            )

            get_escalation_registry().register(escalation)
            logger.info(
                f"[ORCHESTRATE] Registered escalation with action: {action.action_type.value}"
            )

        # Extract auto_fix_description from the registered escalation action
        auto_fix_desc = None
        if result.escalation_action:
            auto_fix_desc = result.escalation_action.get("description", None)

        yield _emit_escalation(
            question=result.escalation_question or "How would you like to proceed?",
            task_context=result.partial_results[-1].task if result.partial_results else None,
            has_auto_fix=result.escalation_action is not None,
            auto_fix_description=auto_fix_desc,
        )
        yield emit_complete(
            response=result.escalation_question or "How would you like to proceed?",
            usage={"escalation": True},
        )

    async def _handle_success(
        self,
        result,  # OrchestrationResult
        stream: bool,
        reasoning_visibility: str,
        accumulated_usage: dict[str, int] | None = None,
        orchestration_mode: str | None = None,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle successful orchestration result.

        Agent start/complete events are already streamed in real-time via the queue.
        This emits reasoning detail panels and the final output.
        """
        # Emit reasoning detail events (expandable panels per observation)
        for obs in result.partial_results:
            yield _emit_reasoning(
                summary=obs.reasoning_summary or f"Using {obs.agent_name} for this step",
                detailed=obs.reasoning,
                visibility=reasoning_visibility,
            )

        # Emit top-level reasoning for direct answers (is_final=true, no observations)
        if not result.partial_results and result.reasoning:
            yield _emit_reasoning(
                summary=result.reasoning_summary or "Reasoning",
                detailed=result.reasoning,
                visibility=reasoning_visibility,
            )

        # Emit final result
        # If tokens were already streamed via on_token callback, skip re-emitting
        if not getattr(result, "streamed", False):
            # Legacy path: word-split fake streaming (for non-streamed results)
            if stream:
                output = result.output or "Orchestration complete."
                words = output.split(" ")
                for i, word in enumerate(words):
                    chunk = word if i == len(words) - 1 else word + " "
                    yield emit_token(chunk)
            else:
                yield emit_token(result.output or "Orchestration complete.")

        usage = accumulated_usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        yield emit_complete(
            response=result.output or "Orchestration complete.",
            usage=usage,
            orchestration_mode=orchestration_mode,
        )

class TierDispatcher(OrchestrateHandlerBase):
    """Top-level dispatcher: classifies tier and delegates to handler.

    Contains the tier classification code that was in
    OrchestrateHandler.handle() (INSTANT check, SIMPLE check, COMPLEX fallback).
    The router instantiates TierDispatcher instead of OrchestrateHandler.
    """

    def __init__(self) -> None:
        from core.orchestrator.handlers.instant_handler import InstantHandler
        from core.orchestrator.handlers.simple_handler import SimpleHandler

        self._instant = InstantHandler()
        self._simple = SimpleHandler()
        self._complex = ComplexHandler()

    async def handle(
        self,
        message: str,
        context: "ExecutionContext",
        stream: bool = True,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Classify tier and delegate to appropriate handler.

        Args:
            message: User goal/request.
            context: Execution context with preferences.
            stream: Whether to stream output token-by-token.

        Yields:
            ChatEvent instances from the delegated handler.
        """
        from core.adapters.registry import get_registry
        from core.orchestrator.complexity import ComplexityEstimator
        from core.orchestrator.config import get_orchestration_config
        from core.orchestrator.models import Tier

        logger.info(f"[ORCHESTRATE] ORCHESTRATE mode: goal='{message[:50]}...'")

        # ---------------------------------------------------------------
        # Tier Classification (Phase 90 -- zero-LLM, runs BEFORE orchestrator)
        # ---------------------------------------------------------------
        registry = get_registry()
        agent_cards = registry.list_agents()

        estimator = ComplexityEstimator()
        tier_decision = estimator.classify(message, agent_cards)
        logger.info(
            f"[ORCHESTRATE] Tier: {tier_decision.tier.value}, "
            f"confidence={tier_decision.confidence:.2f}, "
            f"reason={tier_decision.reason}"
        )

        # ---------------------------------------------------------------
        # Knowledge source inventory (Phase 99.3) -- build BEFORE pre-query
        # ---------------------------------------------------------------
        from core.knowledge.sources import _knowledge_registry

        if _knowledge_registry:
            from core.knowledge.sources import list_knowledge_sources

            sources = list_knowledge_sources()
            if sources:
                # Cap at 10 sources, 1 line per source, ~500 chars total
                source_lines = []
                for s in sources[:10]:
                    line = f"- {s.name} ({s.source_type}, {s.chunk_count} chunks)"
                    source_lines.append(line)
                if len(sources) > 10:
                    source_lines.append(f"- ... and {len(sources) - 10} more sources")
                source_summary = "\n".join(source_lines)
                # Cap total chars at 500
                if len(source_summary) > 500:
                    source_summary = source_summary[:497] + "..."
                context.metadata["_knowledge_sources_summary"] = source_summary

        # ---------------------------------------------------------------
        # Knowledge pre-query (Phase 94.1) -- runs ONCE, shared by all tiers
        # ---------------------------------------------------------------
        if _knowledge_registry:
            from core.knowledge.context import get_knowledge_context

            knowledge_context = await get_knowledge_context(message)
        else:
            knowledge_context = None

        if knowledge_context:
            context.metadata["_knowledge_context"] = knowledge_context

        # INSTANT path: bypass orchestrator entirely
        cfg = get_orchestration_config()
        instant_enabled = cfg.tier_instant_enabled

        if instant_enabled and tier_decision.tier == Tier.INSTANT:
            logger.info("[ORCHESTRATE] INSTANT tier: bypassing orchestrator")
            async for event in self._instant.handle(message, context, stream):
                yield event
            return

        # SIMPLE tier: direct agent dispatch (Phase 91)
        simple_enabled = cfg.tier_simple_enabled

        if simple_enabled and tier_decision.tier == Tier.SIMPLE:
            logger.info(f"[ORCHESTRATE] SIMPLE tier: dispatching to {tier_decision.target_agent}")
            simple_events = []
            has_complete = False
            async for event in self._simple.handle(
                message, context, stream, tier_decision=tier_decision
            ):
                simple_events.append(event)
                if event.type == "complete":
                    has_complete = True

            if has_complete:
                for event in simple_events:
                    yield event
                return
            else:
                logger.info("[ORCHESTRATE] SIMPLE tier failed, falling back to COMPLEX")
                # Discard SIMPLE events for invisible fallback

        # ---------------------------------------------------------------
        # COMPLEX path (fallback)
        # ---------------------------------------------------------------
        # Stash tier_decision in metadata so ComplexHandler can access it
        context.metadata["_tier_decision"] = tier_decision

        async for event in self._complex.handle(message, context, stream):
            yield event
