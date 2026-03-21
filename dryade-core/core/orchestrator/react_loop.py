"""ReAct loop execution for DryadeOrchestrator.

Extracted from DryadeOrchestrator.orchestrate() for maintainability.
Pure structural refactor -- zero behavioral changes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

import core.orchestrator.orchestrator as _orch_module
from core.orchestrator.models import (
    FailureAction,
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationResult,
    OrchestrationState,
    OrchestrationThought,
)
from core.orchestrator.observation import ObservationHistory

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.orchestrator.orchestrator import DryadeOrchestrator

logger = logging.getLogger(__name__)

class ReActLoop:
    """Executes the Reason-Act-Observe loop.

    Handles: state initialization, thinking provider calls, agent dispatching,
    streaming, observation history, failure depth tracking, cost emission,
    plan detection, checkpoint management, final answer synthesis.
    """

    def __init__(self, orchestrator: DryadeOrchestrator) -> None:
        """Accept reference to parent orchestrator for shared state access."""
        self._orch = orchestrator

    async def run(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        mode: OrchestrationMode = OrchestrationMode.ADAPTIVE,
        agent_filter: list[str] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_agent_event: Callable[[str, dict], None] | None = None,
        on_token: Callable[[str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> OrchestrationResult:
        """Execute the ReAct loop. Moved from DryadeOrchestrator.orchestrate()."""
        execution_id = str(uuid.uuid4())
        context = context or {}
        observations: list[OrchestrationObservation] = []
        failure_depth = 0  # Track consecutive failures for graduated escalation

        # Restore OrchestrationState if available from escalation retry
        prior_state_dict = (context or {}).pop("_prior_state", None)
        if prior_state_dict:
            # Pydantic handles ISO 8601 string -> datetime coercion automatically
            state = OrchestrationState(**prior_state_dict)
            logger.info(
                f"[ORCHESTRATOR] Restored state: actions_taken={state.actions_taken}, "
                f"mode={state.mode.value}"
            )
        else:
            state = OrchestrationState(
                mode=mode,
                memory_enabled=context.get("memory_enabled", True),
                reasoning_visibility=context.get("reasoning_visibility", "summary"),
            )

        # Restore ObservationHistory if available from escalation retry
        prior_history_dict = (context or {}).pop("_prior_observation_history", None)
        if prior_history_dict:
            observation_history = ObservationHistory.from_dict(prior_history_dict)
            logger.info("[ORCHESTRATOR] Restored observation history from escalation")
        else:
            observation_history = ObservationHistory()

        # Phase 118.4: Soft failure detection tracker (per-orchestrate() call)
        from core.orchestrator.soft_failure_detector import ExecutionTracker

        execution_tracker = ExecutionTracker()

        # Seed with prior observations from escalation retry
        prior_obs = (context or {}).pop("_prior_observations", None)
        if prior_obs:
            for obs_dict in prior_obs:
                try:
                    obs = OrchestrationObservation(**obs_dict)
                    observations.append(obs)
                    if not prior_history_dict:
                        # Only re-add to history if we didn't restore full history
                        observation_history.add(obs)
                except Exception:
                    logger.warning(
                        "[ORCHESTRATOR] Skipped invalid prior observation: "
                        f"{obs_dict.get('task', 'unknown')}"
                    )
            logger.info(
                f"[ORCHESTRATOR] Seeded {len(prior_obs)} prior observations from escalation"
            )

        # Get available agents (skills are handled via bash tool, not orchestrated)
        all_agents = self._orch.agents.list_agents()

        if agent_filter:
            available_agents = [a for a in all_agents if a.name in agent_filter]
        else:
            available_agents = all_agents

        if not available_agents:
            return OrchestrationResult(
                success=False,
                reason="No agents available for orchestration",
                state=state,
            )

        logger.info(
            f"[ORCHESTRATOR] Starting orchestration: goal='{goal[:50]}...', "
            f"mode={mode.value}, agents={len(available_agents)}"
        )

        # --- Middleware hooks (Phase 115.4) ---
        _orch_config_mw = _orch_module.get_orchestration_config()
        middleware = None
        if _orch_config_mw.middleware_enabled:
            from core.orchestrator.middleware import get_middleware_chain

            middleware = get_middleware_chain()

        # --- Continuous optimization loop (Phase 115.5) ---
        if _orch_config_mw.optimization_enabled:
            try:
                from core.orchestrator.continuous_loop import get_continuous_loop

                _opt_loop = get_continuous_loop()
                if not _opt_loop.is_running:
                    _opt_loop.start()
                    logger.info("[OPTIMIZATION] Continuous optimization loop started")
            except Exception:
                logger.debug("[OPTIMIZATION] Failed to start optimization loop", exc_info=True)

        # --- Prevention layer: pre-orchestration checks (Phase 118.9) ---
        _cfg_prev = _orch_module.get_orchestration_config()

        # 1. Model reachability check (all orchestrate() calls are COMPLEX tier)
        if _cfg_prev.prevention_enabled and _cfg_prev.model_reachability_enabled:
            try:
                from core.orchestrator.prevention import PreventionVerdict, get_prevention_pipeline

                model_result = await get_prevention_pipeline().check_model_reachability()
                if model_result and model_result.verdict == PreventionVerdict.FAIL:
                    logger.warning(
                        "[ORCHESTRATOR] Model reachability check failed: %s",
                        model_result.reason,
                    )
                    return OrchestrationResult(
                        success=False,
                        reason=f"Model endpoint unreachable: {model_result.reason}",
                        state=state,
                        needs_escalation=True,
                        escalation_question=(
                            "The LLM model endpoint is not responding. "
                            "Please check your model server (vLLM/OpenAI) is running."
                        ),
                    )
            except Exception as e:
                logger.warning("[ORCHESTRATOR] Model reachability check error (fail-open): %s", e)

        # 2. Prompt optimization hints from failure history
        if (
            _cfg_prev.prevention_enabled
            and _cfg_prev.failure_learning_enabled
            and _cfg_prev.prompt_optimization_enabled
        ):
            try:
                from core.orchestrator.prevention import get_prevention_pipeline

                prevention_hints = get_prevention_pipeline().get_prompt_hints()
                if prevention_hints:
                    context["_prevention_hints"] = prevention_hints
                    logger.debug(
                        "[ORCHESTRATOR] Injected %d prevention hints into context",
                        len(prevention_hints),
                    )
            except Exception as e:
                logger.warning("[ORCHESTRATOR] Prompt optimization hints error (fail-open): %s", e)

        # Wrap orchestration loop with error boundary for graceful failure handling
        async with _orch_module.OrchestrationErrorBoundary(logger, execution_id) as boundary:
            while True:
                # Check leash constraints
                if self._orch._leash_exceeded(state, observations):
                    logger.warning(
                        f"[ORCHESTRATOR] Leash exceeded after {state.actions_taken} actions"
                    )
                    # Build escalation question with resource limit context
                    leash_details = []
                    if self._orch.leash.max_actions:
                        leash_details.append(f"max actions: {self._orch.leash.max_actions}")
                    if self._orch.leash.max_duration_seconds:
                        leash_details.append(
                            f"max duration: {self._orch.leash.max_duration_seconds}s"
                        )
                    limits_str = ", ".join(leash_details) if leash_details else "resource limits"

                    leash_result = OrchestrationResult(
                        success=False,
                        needs_escalation=True,
                        escalation_question=(
                            f"I've reached the resource limit ({limits_str}) after "
                            f"{state.actions_taken} actions. Here's what I've accomplished so far. "
                            "Would you like me to continue with an extended limit, "
                            "or would you prefer to take a different approach?"
                        ),
                        partial_results=observations,
                        original_goal=goal,
                        state=state,
                        observation_history_data=observation_history.to_dict(),
                    )
                    await self._orch._maybe_reflect(leash_result, observations, goal, context)
                    return leash_result

                # Check for user-initiated cancellation
                if cancel_event and cancel_event.is_set():
                    logger.info(
                        f"[ORCHESTRATOR] Cancellation detected after {state.actions_taken} actions"
                    )
                    _orch_module._emit_event(
                        on_agent_event,
                        "cancel_ack",
                        {
                            "partial_results_count": len(observations),
                            "current_step": state.actions_taken,
                            "reason": "User requested cancellation",
                        },
                    )
                    return OrchestrationResult(
                        success=False,
                        reason="Cancelled by user",
                        partial_results=observations,
                        state=state,
                        cancelled=True,
                    )

                # Phase 115.4: Pre-routing middleware
                if middleware:
                    from core.orchestrator.middleware import RoutingContext

                    routing_ctx = RoutingContext(
                        goal=goal,
                        model_tier="unknown",  # ThinkingProvider handles detection
                        meta_action_hint=(context or {}).get("_meta_action_hint", False),
                        router_hints=(context or {}).get("_router_hints"),
                        available_agents=available_agents,
                        selected_tools=None,
                    )
                    routing_ctx = await middleware.run_pre_routing(routing_ctx)

                # LLM decides next action
                # Always use full tool schemas for accurate agent selection
                thought = await self._orch.thinking.orchestrate_think(
                    goal=goal,
                    observations=observations,
                    available_agents=available_agents,
                    context=context,
                    observation_history=observation_history,
                    lightweight=False,
                )

                # Emit reasoning in real-time if callback provided
                # Prefer reasoning_summary (concise) over full reasoning (verbose)
                thinking_text = thought.reasoning_summary or thought.reasoning
                if on_thinking and thinking_text:
                    on_thinking(thinking_text)

                state.actions_taken += 1

                # Phase 115.4: Post-routing middleware
                if middleware:
                    await middleware.run_post_routing(routing_ctx, thought)

                # --- Self-mod tool dispatch (Phase 115.1, expanded 115.2) ---
                # If the LLM called a self-mod tool, dispatch it directly instead
                # of going through agent execution (self-mod tools are orchestrator-internal).
                if thought.task and thought.task.tool:
                    from core.orchestrator.self_mod_tools import (
                        execute_self_mod_tool,
                        is_read_only_tool,
                        is_self_mod_tool,
                    )

                    if is_self_mod_tool(thought.task.tool):
                        logger.info(
                            f"[ORCHESTRATOR] Self-mod tool called: {thought.task.tool}, "
                            f"args={thought.task.arguments}"
                        )
                        conversation_id = (context or {}).get("conversation_id", "")

                        # Phase 115.3: Per-action autonomy check
                        _orch_config = _orch_module.get_orchestration_config()
                        if _orch_config.action_autonomy_enabled:
                            from core.orchestrator.action_autonomy import (
                                AutonomyLevel,
                                get_action_autonomy,
                            )

                            autonomy = get_action_autonomy()
                            level = autonomy.check_autonomy(thought.task.tool)
                            logger.info(
                                f"[ORCHESTRATOR] Autonomy check: tool={thought.task.tool}, "
                                f"level={level.value}"
                            )
                            # CONFIRM level: log the action for audit trail (tool still executes)
                            if level == AutonomyLevel.CONFIRM:
                                logger.info(
                                    f"[ORCHESTRATOR] [AUDIT] CONFIRM-level self-mod: "
                                    f"tool={thought.task.tool}, args={thought.task.arguments}"
                                )
                            # Note: AUTO and APPROVE levels are handled by existing paths:
                            # - AUTO: read-only tools already execute directly
                            # - APPROVE: escalation tools already go through PendingEscalation
                            # The ActionAutonomy check here is for logging and future gating.

                        if is_read_only_tool(thought.task.tool):
                            # Read-only tools return results directly as observations
                            # (no escalation needed). Continue the ReAct loop.
                            try:
                                result = await execute_self_mod_tool(
                                    tool_name=thought.task.tool,
                                    arguments=thought.task.arguments,
                                    conversation_id=conversation_id,
                                    original_goal=goal,
                                    context=context,
                                )
                                obs = OrchestrationObservation(
                                    agent_name="self-mod",
                                    task=thought.task.tool,
                                    result=str(result.get("results", [])),
                                    success=True,
                                )
                                observations.append(obs)
                                observation_history.add(obs)
                                logger.info(
                                    f"[ORCHESTRATOR] Read-only self-mod tool '{thought.task.tool}' "
                                    f"returned {len(result.get('results', []))} results"
                                )
                                continue  # Continue ReAct loop with observation
                            except Exception as e:
                                logger.warning(
                                    f"[ORCHESTRATOR] Read-only self-mod tool failed: {e}"
                                )
                                # Fall through to normal task execution on error
                        else:
                            # Escalation path: tool creates a PendingEscalation
                            try:
                                escalation = await execute_self_mod_tool(
                                    tool_name=thought.task.tool,
                                    arguments=thought.task.arguments,
                                    conversation_id=conversation_id,
                                    original_goal=goal,
                                    context=context,
                                )
                                # XR-E01: Registration removed -- now happens ONLY
                                # in ComplexHandler._handle_escalation() which has
                                # full context (observations, state, observation_history).

                                # Record routing metric
                                _cfg = _orch_module.get_orchestration_config()
                                if _cfg.routing_metrics_enabled:
                                    from core.orchestrator.routing_metrics import (
                                        record_routing_metric,
                                    )

                                    record_routing_metric(
                                        message=goal,
                                        hint_fired=True,
                                        hint_type="meta_action",
                                        llm_tool_called=thought.task.tool,
                                        fallback_activated=False,
                                    )

                                # XR-C01: Create observation for the self-mod tool
                                # call so the LLM sees evidence of this action on
                                # retry after escalation approval.
                                obs = OrchestrationObservation(
                                    agent_name="self-mod",
                                    task=thought.task.tool,
                                    result=f"Escalation created: {escalation.action.description}. Awaiting user approval.",
                                    success=True,
                                )
                                observations.append(obs)
                                observation_history.add(obs)

                                return OrchestrationResult(
                                    success=False,
                                    needs_escalation=True,
                                    escalation_question=escalation.question,
                                    escalation_action={
                                        "action_type": escalation.action.action_type.value,
                                        "parameters": escalation.action.parameters,
                                        "description": escalation.action.description,
                                    },
                                    partial_results=observations,
                                    original_goal=goal,
                                    state=state,
                                    observation_history_data=observation_history.to_dict(),
                                )
                            except Exception as e:
                                logger.error(f"[ORCHESTRATOR] Self-mod tool execution failed: {e}")
                                # Fall through to normal task execution on error

                if thought.is_final:
                    if on_token:
                        # Stream the final answer token-by-token
                        logger.info("[ORCHESTRATOR] Streaming final answer via on_token callback")
                        (
                            streamed_content,
                            streamed_reasoning,
                            est_tokens,
                        ) = await self._orch.thinking._stream_final_answer(
                            goal=goal,
                            observations=observations,
                            observation_history=observation_history,
                            context=context,
                            on_token=on_token,
                            on_thinking=on_thinking,
                            cancel_event=cancel_event,
                        )
                        # Emit cost for the streaming call (prompt estimated from
                        # goal + observations length, completion from returned estimate)
                        if self._orch.thinking._on_cost_event:
                            from core.extensions.events import emit_cost_update

                            prompt_est = max(1, (len(goal) + len(str(observations))) // 4)
                            cost_event = emit_cost_update(
                                prompt_tokens=prompt_est,
                                completion_tokens=est_tokens,
                            )
                            try:
                                self._orch.thinking._on_cost_event(cost_event)
                            except Exception:
                                pass
                        final_output = streamed_content
                        if not final_output and streamed_reasoning:
                            # vLLM models put everything in reasoning_content.
                            # Use the accumulated reasoning from the stream
                            # (clean LLM output) instead of thought.answer
                            # (which contains orchestration JSON preamble).
                            final_output = streamed_reasoning
                            on_token(final_output)
                            logger.info(
                                "[ORCHESTRATOR] Content stream empty, "
                                "falling back to streamed reasoning "
                                "(%d chars)",
                                len(streamed_reasoning),
                            )
                        elif not final_output and thought.answer:
                            # Last resort: use thought.answer (orchestrate_think output).
                            # This path only triggers if BOTH content and reasoning
                            # streams were empty.
                            final_output = thought.answer
                            on_token(final_output)
                            logger.info(
                                "[ORCHESTRATOR] Content and reasoning streams empty, "
                                "falling back to thought.answer"
                            )

                        stream_result = OrchestrationResult(
                            success=True,
                            output=final_output,
                            reasoning=thought.reasoning,
                            reasoning_summary=thought.reasoning_summary,
                            partial_results=observations,
                            state=state,
                            streamed=True,
                        )
                        await self._orch._maybe_reflect(stream_result, observations, goal, context)
                        return stream_result
                    else:
                        # Non-streaming path (unchanged)
                        logger.info(
                            f"[ORCHESTRATOR] Goal achieved: {thought.answer[:100] if thought.answer else 'No answer'}..."
                        )
                        final_result = OrchestrationResult(
                            success=True,
                            output=thought.answer,
                            reasoning=thought.reasoning,
                            reasoning_summary=thought.reasoning_summary,
                            partial_results=observations,
                            state=state,
                        )
                        await self._orch._maybe_reflect(final_result, observations, goal, context)
                        return final_result

                # Execute based on orchestration decision
                if thought.parallel_tasks:
                    # Emit all starts before parallel execution
                    for t in thought.parallel_tasks:
                        _orch_module._emit_event(
                            on_agent_event,
                            "agent_start",
                            {
                                "agent": t.agent_name,
                                "task": t.description,
                            },
                        )
                    results = await self._orch._execute_parallel(
                        thought.parallel_tasks,
                        execution_id,
                        context,
                        available_agents,
                        execution_tracker=execution_tracker,
                        state=state,
                        observation_history=observation_history,
                        observations=observations,
                    )
                    # Emit all completes after parallel execution
                    for r in results:
                        _orch_module._emit_event(
                            on_agent_event,
                            "agent_complete",
                            {
                                "agent": r.agent_name,
                                "result": str(r.result)[:500] if r.result else "",
                                "success": r.success,
                                "duration_ms": r.duration_ms,
                                "error": r.error,
                            },
                        )
                elif thought.task:
                    _orch_module._emit_event(
                        on_agent_event,
                        "agent_start",
                        {
                            "agent": thought.task.agent_name,
                            "task": thought.task.description,
                        },
                    )
                    result = await self._orch._execute_with_retry(
                        thought.task,
                        execution_id,
                        context,
                        available_agents,
                        failure_depth=failure_depth,
                        execution_tracker=execution_tracker,
                        state=state,
                        observation_history=observation_history,
                        observations=observations,
                    )
                    _orch_module._emit_event(
                        on_agent_event,
                        "agent_complete",
                        {
                            "agent": result.agent_name,
                            "result": str(result.result)[:500] if result.result else "",
                            "success": result.success,
                            "duration_ms": result.duration_ms,
                            "error": result.error,
                        },
                    )
                    results = [result]
                else:
                    # LLM returned no task -- check if it has a clarification/answer
                    if thought.answer:
                        # LLM wants to respond to user (clarification, greeting, etc.)
                        logger.info(
                            "[ORCHESTRATOR] No task but has answer, treating as final response"
                            + (" (clarification)" if thought.needs_clarification else "")
                        )

                        # Register pending clarification so we can merge the user's
                        # answer with the original goal on the next turn
                        if thought.needs_clarification:
                            from core.orchestrator.clarification import (
                                PendingClarification,
                                get_clarification_registry,
                            )

                            conversation_id = (context or {}).get("conversation_id", "")
                            if conversation_id:
                                get_clarification_registry().register(
                                    PendingClarification(
                                        conversation_id=conversation_id,
                                        original_goal=goal,
                                        original_context=context or {},
                                        clarification_question=thought.answer or "",
                                    )
                                )

                        return OrchestrationResult(
                            success=True,
                            output=thought.answer,
                            partial_results=observations,
                            state=state,
                        )

                    # Genuine no-action bug -- create error observation with failure_thought
                    logger.warning(
                        "[ORCHESTRATOR] Thought has no task and no answer, marking as error"
                    )
                    obs = OrchestrationObservation(
                        agent_name="orchestrator",
                        task="decide_action",
                        result=None,
                        success=False,
                        error="No action specified in thought",
                    )

                    obs.failure_thought = OrchestrationThought(
                        reasoning=thought.reasoning or "No task specified",
                        is_final=False,
                        failure_action=FailureAction.ESCALATE,
                        escalation_question="I wasn't sure how to proceed with your request. Could you rephrase or provide more details?",
                    )
                    results = [obs]

                # Attach LLM reasoning to observations so it can be emitted to frontend
                for r in results:
                    r.reasoning = thought.reasoning
                    r.reasoning_summary = thought.reasoning_summary

                # Handle failures with intelligent fallback
                for result in results:
                    if not result.success:
                        failure_depth += 1
                        handled = await self._orch._handle_failure(
                            result,
                            context,
                            available_agents,
                            state,
                            failure_depth=failure_depth,
                            observation_history=observation_history,
                            execution_tracker=execution_tracker,
                            observations=observations,
                        )
                        if handled.needs_escalation:
                            # Return for escalation (per user decision: inline in chat)
                            return OrchestrationResult(
                                success=False,
                                partial_results=observations + [result],
                                state=state,
                                needs_escalation=True,
                                escalation_question=handled.escalation_question,
                                escalation_action=handled.escalation_action,
                                original_goal=goal,  # Store for retry after fix
                                observation_history_data=observation_history.to_dict(),
                            )

                        # Detect ROLLBACK result and restore state (Phase 118.5)
                        if handled.reason and handled.reason.startswith("ROLLBACK:"):
                            checkpoint_data = handled.observation_history_data
                            if checkpoint_data:
                                from core.orchestrator.checkpoint import CheckpointState

                                restored = CheckpointState.from_dict(checkpoint_data)
                                # Restore observation state and failure depth -- but NOT execution_id.
                                # IMPORTANT: Keep the current execution_id unchanged so that the
                                # checkpoint ring buffer (keyed by execution_id) remains consistent.
                                observations = [
                                    OrchestrationObservation(**od)
                                    for od in restored.observations_data
                                ]
                                observation_history = ObservationHistory.from_dict(
                                    restored.observation_history_data
                                )
                                failure_depth = restored.failure_depth
                                # Restore execution tracker
                                if restored.tracker_data is not None:
                                    from core.orchestrator.soft_failure_detector import (
                                        ExecutionTracker as _ET,
                                    )

                                    execution_tracker = _ET()
                                    for tool, args_hash in restored.tracker_data:
                                        execution_tracker._history.append((tool, args_hash))
                                # Restore OrchestrationState fields EXCEPT execution_id
                                restored_state = OrchestrationState(**restored.state_data)
                                state.actions_taken = restored_state.actions_taken
                                state.mode = restored_state.mode
                                # Do NOT overwrite state.execution_id -- it must match execution_id local var
                                logger.info(
                                    f"[ORCHESTRATOR] State restored from checkpoint: "
                                    f"observations={len(observations)}, failure_depth={failure_depth}, "
                                    f"actions_taken={state.actions_taken}"
                                )
                            continue  # Re-enter the orchestration loop with restored state

                # Record observations
                observations.extend(results)
                for obs in results:
                    observation_history.add(obs)

                # Reset failure depth on any success
                if any(r.success for r in results):
                    failure_depth = 0

                # Proactive 85% context overflow detection
                cfg = _orch_module.get_orchestration_config()
                if observation_history.context_size_chars() > 0.85 * cfg.max_context_chars:
                    logger.info(
                        f"[ORCHESTRATOR] Proactive context overflow: "
                        f"{observation_history.context_size_chars()} chars > "
                        f"{int(0.85 * cfg.max_context_chars)} (85% of {cfg.max_context_chars}). "
                        f"Compressing history."
                    )
                    observation_history.compress_aggressive(target_reduction=0.5)

        # Error boundary caught an exception - return graceful fallback
        if boundary.error:
            return boundary.get_fallback_result()

        # This line should never be reached since loop only exits via return
        # But add explicit return to satisfy type checker
        return OrchestrationResult(
            success=False,
            reason="Orchestration ended unexpectedly",
        )
