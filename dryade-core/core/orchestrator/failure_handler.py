"""Failure handling for DryadeOrchestrator.

Extracted from DryadeOrchestrator._handle_failure() for maintainability.
Pure structural refactor -- zero behavioral changes.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import TYPE_CHECKING, Any

import core.orchestrator.orchestrator as _orch_module
from core.orchestrator.models import (
    ErrorCategory,
    FailureAction,
    OrchestrationObservation,
    OrchestrationResult,
    OrchestrationState,
    OrchestrationTask,
)
from core.orchestrator.observation import ObservationHistory

if TYPE_CHECKING:
    from core.adapters.protocol import AgentCard
    from core.orchestrator.orchestrator import DryadeOrchestrator
    from core.orchestrator.soft_failure_detector import ExecutionTracker

logger = logging.getLogger(__name__)

class FailureHandler:
    """Handles orchestration failures with healing and retry logic.

    Extracted from DryadeOrchestrator._handle_failure().
    """

    def __init__(self, orchestrator: DryadeOrchestrator) -> None:
        """Accept reference to parent orchestrator for shared state access."""
        self._orch = orchestrator

    async def handle(
        self,
        observation: OrchestrationObservation,
        context: dict[str, Any],
        available_agents: list[AgentCard],
        state: OrchestrationState,
        failure_depth: int = 0,
        observation_history: ObservationHistory | None = None,
        execution_tracker: ExecutionTracker | None = None,
        observations: list[OrchestrationObservation] | None = None,
    ) -> OrchestrationResult:
        """Handle task failure with intelligent fallback.

        Per user decision: LLM decides retry/skip/escalate based on criticality.
        Graduated escalation overrides at depth thresholds (3/4/5/6).
        Moved from DryadeOrchestrator._handle_failure().
        """
        _recovery_start = time.perf_counter()

        # Local helper for classifier accuracy tracking (Phase 118.10 gap closure)
        def _emit_accuracy(outcome: str) -> None:
            try:
                from core.orchestrator.failure_metrics import record_classifier_accuracy

                cat = (
                    observation.error_classification.category.value
                    if observation.error_classification
                    else "unknown"
                )
                record_classifier_accuracy(category=cat, outcome=outcome)
            except Exception:
                pass

        agent = self._orch.agents.get(observation.agent_name)
        caps = agent.capabilities() if agent else None
        is_critical = caps.is_critical if caps else True  # Default to critical if unknown
        _max_retries = (
            caps.max_retries if caps else _orch_module.get_orchestration_config().max_retries
        )

        # Use pre-computed thought from _execute_with_retry if available
        # This avoids redundant LLM call since we already consulted LLM during retry loop
        thought = observation.failure_thought
        if thought is None:
            logger.error(
                "[ORCHESTRATOR] BUG: failure_thought not set on observation. "
                "Defaulting to escalation."
            )
            from core.orchestrator.models import OrchestrationThought

            thought = OrchestrationThought(
                reasoning="Failure thought missing - defaulting to escalation",
                is_final=False,
                failure_action=FailureAction.ESCALATE,
                escalation_question=f"Task '{observation.task}' failed: {observation.error}. How should I proceed?",
            )

        # Phase 118.8: PreFailure middleware hooks
        cfg_fm = _orch_module.get_orchestration_config()
        if cfg_fm.failure_middleware_enabled:
            try:
                from core.orchestrator.failure_middleware import FailureContext

                failure_ctx = FailureContext(
                    observation=observation,
                    error_classification=observation.error_classification,
                    failure_action=thought.failure_action,
                    failure_depth=failure_depth,
                    tool_error=None,  # Not always available at this point
                    metadata={},
                )
                failure_ctx = await self._orch.failure_pipeline.run_pre_failure(failure_ctx)
                if failure_ctx.short_circuit:
                    thought.failure_action = failure_ctx.failure_action
                    logger.info(
                        "[ORCHESTRATOR] Failure middleware short-circuited: action=%s",
                        thought.failure_action.value if thought.failure_action else "None",
                    )
                elif failure_ctx.failure_action != thought.failure_action:
                    thought.failure_action = failure_ctx.failure_action
            except Exception as e:
                logger.debug("[ORCHESTRATOR] PreFailure middleware failed (non-fatal): %s", e)

        # Graduated escalation: override LLM decision based on depth
        # Hard classifier overrides (AUTH->ESCALATE, PERMANENT->ABORT, severe RATE_LIMIT)
        # bypass the graduation ladder
        _CLASSIFIER_HARD_CATEGORIES = {
            ErrorCategory.AUTH,
            ErrorCategory.PERMANENT,
            ErrorCategory.RATE_LIMIT,
        }

        classifier_override = False
        if observation.error_classification is not None:
            if observation.error_classification.category in _CLASSIFIER_HARD_CATEGORIES:
                classifier_override = True

        if not classifier_override and failure_depth >= 3:
            original_action = thought.failure_action
            if failure_depth >= 6:
                thought.failure_action = FailureAction.ABORT
            elif failure_depth >= 5:
                thought.failure_action = FailureAction.CONTEXT_REDUCE
            elif failure_depth >= 4:
                thought.failure_action = FailureAction.DECOMPOSE
            elif failure_depth >= 3:
                # Try ROLLBACK first if checkpoints available, then ALTERNATIVE
                cfg_rl = _orch_module.get_orchestration_config()
                if (
                    cfg_rl.checkpoint_enabled
                    and self._orch.checkpoint_manager.has_checkpoints(str(state.execution_id))
                    and thought.failure_action == FailureAction.RETRY
                ):
                    thought.failure_action = FailureAction.ROLLBACK
                elif thought.failure_action == FailureAction.RETRY:
                    thought.failure_action = FailureAction.ALTERNATIVE

            if thought.failure_action != original_action:
                logger.info(
                    f"[ORCHESTRATOR] Graduated escalation: depth={failure_depth}, "
                    f"overrode {original_action.value} -> {thought.failure_action.value}"
                )

        # Phase 118.8: PostFailure middleware hooks
        cfg_fm_post = _orch_module.get_orchestration_config()  # Independent config read
        if cfg_fm_post.failure_middleware_enabled:
            try:
                from core.orchestrator.failure_middleware import FailureContext

                post_failure_ctx = FailureContext(
                    observation=observation,
                    error_classification=observation.error_classification,
                    failure_action=thought.failure_action,
                    failure_depth=failure_depth,
                    tool_error=None,
                    metadata={},
                )
                post_failure_ctx = await self._orch.failure_pipeline.run_post_failure(
                    post_failure_ctx
                )
                if post_failure_ctx.failure_action != thought.failure_action:
                    logger.info(
                        "[ORCHESTRATOR] PostFailure hook overrode action: %s -> %s",
                        thought.failure_action.value,
                        post_failure_ctx.failure_action.value
                        if post_failure_ctx.failure_action
                        else "None",
                    )
                    thought.failure_action = post_failure_ctx.failure_action
                # Check for plugin-provided recovery strategy
                if post_failure_ctx.recovery_strategy is not None:
                    try:
                        strategy_result = await post_failure_ctx.recovery_strategy.execute(
                            post_failure_ctx
                        )
                        # Run OnRecovery hooks
                        await self._orch.failure_pipeline.run_on_recovery(
                            post_failure_ctx, strategy_result
                        )
                        if strategy_result.success:
                            return OrchestrationResult(
                                success=True,
                                output=strategy_result.output,
                                state=state,
                            )
                        # Strategy failed -- fall through to standard handler
                        logger.warning(
                            "[ORCHESTRATOR] Recovery strategy '%s' failed: %s",
                            post_failure_ctx.recovery_strategy.name,
                            strategy_result.error,
                        )
                    except Exception as e:
                        logger.debug(
                            "[ORCHESTRATOR] Recovery strategy execution failed (non-fatal): %s", e
                        )
            except Exception as e:
                logger.debug("[ORCHESTRATOR] PostFailure middleware failed (non-fatal): %s", e)

        if thought.failure_action == FailureAction.SKIP:
            if is_critical:
                # Cannot skip critical tasks - escalate instead
                logger.warning("[ORCHESTRATOR] Cannot skip critical task, escalating")
                try:
                    from core.orchestrator.failure_metrics import record_failure_recovery

                    record_failure_recovery(
                        action="skip",
                        success=False,
                        duration_seconds=time.perf_counter() - _recovery_start,
                        agent_name=observation.agent_name,
                    )
                except Exception:
                    pass
                _emit_accuracy("escalated")
                return OrchestrationResult(
                    success=False,
                    needs_escalation=True,
                    escalation_question=f"Critical task failed: {observation.task}. Error: {observation.error}. How should I proceed?",
                )
            logger.info(f"[ORCHESTRATOR] Skipping non-critical failed task: {observation.task}")
            try:
                from core.orchestrator.failure_metrics import record_failure_recovery

                record_failure_recovery(
                    action="skip",
                    success=True,
                    duration_seconds=time.perf_counter() - _recovery_start,
                    agent_name=observation.agent_name,
                )
            except Exception:
                pass
            _emit_accuracy("resolved")
            return OrchestrationResult(success=True)  # Continue orchestration

        elif thought.failure_action == FailureAction.ESCALATE:
            # Build escalation action from error context inline.
            # The classifier already identified the error category, so we can derive
            # the appropriate fix action without the old string-parsing function.
            escalation_action = None

            # Check if the error is about path restrictions (MCP filesystem)
            error_lower = (observation.error or "").lower()
            if "path outside allowed directories" in error_lower or (
                "access denied" in error_lower and observation.agent_name.startswith("mcp-")
            ):
                import os as _os

                path_match = re.search(r":\s*(/[^\s]+)\s+not in", observation.error or "")
                if path_match:
                    denied_path = path_match.group(1)
                    home = _os.path.expanduser("~")
                    if not denied_path.startswith(home):
                        if home.startswith(denied_path):
                            denied_path = home
                        else:
                            denied_path = None

                    if denied_path:
                        server_name = (
                            observation.agent_name.replace("mcp-", "")
                            if observation.agent_name.startswith("mcp-")
                            else "filesystem"
                        )
                        from core.orchestrator.escalation import (
                            EscalationAction,
                            EscalationActionType,
                        )

                        action = EscalationAction(
                            action_type=EscalationActionType.UPDATE_MCP_CONFIG,
                            parameters={"path": denied_path, "server": server_name},
                            description=f"Add '{denied_path}' to the {server_name} MCP server's allowed directories",
                        )
                        escalation_action = {
                            "action_type": action.action_type.value,
                            "parameters": action.parameters,
                            "description": action.description,
                        }

            # Check for agent-not-found -> attempt factory fast-path, then CREATE_AGENT
            elif any(
                p in error_lower
                for p in [
                    "agent not found",
                    "no suitable agent",
                    "no agent available",
                    "not found in registry",
                ]
            ) or ("agent '" in error_lower and "not found" in error_lower):
                # Try fast-path factory creation first (Phase 119.4)
                gap_result = await self._orch._handle_capability_gap(
                    observation.error or observation.task,
                    context,
                )
                if gap_result:
                    # Fast-path succeeded -- return success with creation message
                    return OrchestrationResult(
                        success=True,
                        output=gap_result,
                    )

                # Fast-path failed or factory disabled -- fall through to standard escalation
                from core.orchestrator.escalation import EscalationActionType

                escalation_action = {
                    "action_type": EscalationActionType.CREATE_AGENT.value,
                    "parameters": {
                        "task_description": observation.error or "",
                        "failed_agent": observation.agent_name,
                    },
                    "description": (
                        "No suitable agent found for this task. "
                        "I can help create a dedicated agent using the self-improve skill."
                    ),
                }

            if escalation_action:
                logger.info(
                    f"[ORCHESTRATOR] Created escalation action: {escalation_action.get('action_type')}"
                )

            try:
                from core.orchestrator.failure_metrics import record_failure_recovery

                record_failure_recovery(
                    action="escalate",
                    success=False,
                    duration_seconds=time.perf_counter() - _recovery_start,
                    agent_name=observation.agent_name,
                )
            except Exception:
                pass
            _emit_accuracy("escalated")
            return OrchestrationResult(
                success=False,
                needs_escalation=True,
                escalation_question=(
                    thought.escalation_question
                    or (escalation_action.get("description") if escalation_action else None)
                    or f"Task failed: {observation.task}. Error: {observation.error}. How should I proceed?"
                ),
                escalation_action=escalation_action,
            )

        elif thought.failure_action == FailureAction.DECOMPOSE:
            logger.info(
                f"[ORCHESTRATOR] DECOMPOSE: breaking task into sub-steps: {observation.task}"
            )
            from core.orchestrator.models import ExecutionPlan, PlanStep, StepStatus

            failed_step = PlanStep(
                id="failed-0",
                agent_name=observation.agent_name,
                task=observation.task,
                status=StepStatus.FAILED,
                error=observation.error,
            )
            synthetic_plan = ExecutionPlan(
                id=str(uuid.uuid4()),
                goal=observation.task,
                steps=[failed_step],
            )
            synthetic_plan.compute_execution_order()

            try:
                sub_plan = await self._orch.thinking.replan_think(
                    original_plan=synthetic_plan,
                    failed_steps=[failed_step],
                    completed_results={},
                    available_agents=available_agents,
                    context=context,
                )
                try:
                    from core.orchestrator.failure_metrics import record_failure_llm_call

                    record_failure_llm_call(call_type="replan_think")
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] DECOMPOSE replan_think failed: {e}")
                sub_plan = None

            if sub_plan and sub_plan.steps:
                logger.info(
                    f"[ORCHESTRATOR] DECOMPOSE: executing {len(sub_plan.steps)} sub-steps "
                    f"in {len(sub_plan.execution_order)} waves"
                )
                sub_observations: list[OrchestrationObservation] = []
                all_succeeded = True
                for wave in sub_plan.execution_order:
                    for step_id in wave:
                        step = sub_plan.get_step(step_id)
                        if step.status == StepStatus.COMPLETED:
                            continue
                        sub_task = OrchestrationTask(
                            agent_name=step.agent_name,
                            description=step.task,
                            is_critical=step.is_critical,
                        )
                        sub_obs = await self._orch._execute_with_retry(
                            sub_task,
                            str(state.execution_id),
                            context,
                            available_agents,
                            execution_tracker=execution_tracker,
                            state=state,
                            observation_history=observation_history,
                            observations=observations,
                        )
                        sub_observations.append(sub_obs)
                        if not sub_obs.success:
                            all_succeeded = False
                            logger.warning(f"[ORCHESTRATOR] DECOMPOSE sub-step failed: {step.task}")
                            break
                    if not all_succeeded:
                        break

                if all_succeeded:
                    combined_result = "\n".join(
                        f"[{obs.agent_name}] {obs.task}: {str(obs.result)[:200]}"
                        for obs in sub_observations
                        if obs.success
                    )
                    try:
                        from core.orchestrator.failure_metrics import record_failure_recovery

                        record_failure_recovery(
                            action="decompose",
                            success=True,
                            duration_seconds=time.perf_counter() - _recovery_start,
                            agent_name=observation.agent_name,
                        )
                    except Exception:
                        pass
                    _emit_accuracy("resolved")
                    return OrchestrationResult(
                        success=True,
                        output=combined_result,
                        partial_results=sub_observations,
                        state=state,
                    )
                else:
                    try:
                        from core.orchestrator.failure_metrics import record_failure_recovery

                        record_failure_recovery(
                            action="decompose",
                            success=False,
                            duration_seconds=time.perf_counter() - _recovery_start,
                            agent_name=observation.agent_name,
                        )
                    except Exception:
                        pass
                    return OrchestrationResult(
                        success=False,
                        needs_escalation=True,
                        partial_results=sub_observations,
                        escalation_question=(
                            f"Task decomposed into {len(sub_plan.steps)} sub-steps but "
                            f"sub-step execution failed. Error: {sub_observations[-1].error if sub_observations else 'unknown'}. "
                            f"How should I proceed?"
                        ),
                    )
            else:
                try:
                    from core.orchestrator.failure_metrics import record_failure_recovery

                    record_failure_recovery(
                        action="decompose",
                        success=False,
                        duration_seconds=time.perf_counter() - _recovery_start,
                        agent_name=observation.agent_name,
                    )
                except Exception:
                    pass
                return OrchestrationResult(
                    success=False,
                    needs_escalation=True,
                    escalation_question=(
                        f"Tried to decompose '{observation.task}' into smaller steps "
                        f"but couldn't generate a valid sub-plan. "
                        f"Error: {observation.error}. How should I proceed?"
                    ),
                )

        elif thought.failure_action == FailureAction.CONTEXT_REDUCE:
            logger.info(
                f"[ORCHESTRATOR] CONTEXT_REDUCE: compressing history and retrying: {observation.task}"
            )
            if observation_history is not None:
                observation_history.compress_aggressive(target_reduction=0.5)
            else:
                logger.warning(
                    "[ORCHESTRATOR] CONTEXT_REDUCE: no observation_history available, skipping compression"
                )

            retry_task = OrchestrationTask(
                agent_name=observation.agent_name,
                description=observation.task,
                is_critical=is_critical,
            )
            retries_after_reduce = 0
            while retries_after_reduce < 2:
                retry_obs = await self._orch._execute_single(
                    retry_task,
                    str(state.execution_id),
                    context,
                    execution_tracker=execution_tracker,
                )
                if retry_obs.success:
                    logger.info(
                        f"[ORCHESTRATOR] CONTEXT_REDUCE retry succeeded on attempt {retries_after_reduce + 1}"
                    )
                    try:
                        from core.orchestrator.failure_metrics import record_failure_recovery

                        record_failure_recovery(
                            action="context_reduce",
                            success=True,
                            duration_seconds=time.perf_counter() - _recovery_start,
                            agent_name=observation.agent_name,
                        )
                    except Exception:
                        pass
                    _emit_accuracy("resolved")
                    return OrchestrationResult(
                        success=True,
                        output=retry_obs.result,
                        partial_results=[retry_obs],
                        state=state,
                    )
                retries_after_reduce += 1

            try:
                from core.orchestrator.failure_metrics import record_failure_recovery

                record_failure_recovery(
                    action="context_reduce",
                    success=False,
                    duration_seconds=time.perf_counter() - _recovery_start,
                    agent_name=observation.agent_name,
                )
            except Exception:
                pass
            return OrchestrationResult(
                success=False,
                needs_escalation=True,
                escalation_question=(
                    f"Reduced context and retried '{observation.task}' twice but still failed. "
                    f"Error: {retry_obs.error}. How should I proceed?"
                ),
            )

        elif thought.failure_action == FailureAction.ABORT:
            logger.warning(
                f"[ORCHESTRATOR] ABORT: all recovery exhausted, depth={failure_depth}: "
                f"{observation.task}, error={observation.error}"
            )
            try:
                from core.orchestrator.failure_metrics import record_failure_recovery

                record_failure_recovery(
                    action="abort",
                    success=False,
                    duration_seconds=time.perf_counter() - _recovery_start,
                    agent_name=observation.agent_name,
                )
            except Exception:
                pass
            _emit_accuracy("failed")
            partial = []
            if observation_history is not None:
                partial = [obs for obs in observation_history.get_all_observations() if obs.success]
            return OrchestrationResult(
                success=False,
                reason=f"Orchestration aborted after {failure_depth} consecutive failures. "
                f"Last error: {observation.error}",
                output=(
                    f"Unable to complete: {observation.task}. "
                    f"All automated recovery strategies exhausted (depth={failure_depth})."
                ),
                partial_results=partial,
                state=state,
                observation_history_data=(
                    observation_history.to_dict() if observation_history is not None else None
                ),
            )

        elif thought.failure_action == FailureAction.ROLLBACK:
            logger.info(
                f"[ORCHESTRATOR] ROLLBACK: restoring state from checkpoint: {observation.task}"
            )
            cfg_rb = _orch_module.get_orchestration_config()
            exec_id_str = str(state.execution_id)
            if not cfg_rb.checkpoint_enabled or not self._orch.checkpoint_manager.has_checkpoints(
                exec_id_str
            ):
                logger.warning(
                    "[ORCHESTRATOR] ROLLBACK: no checkpoints available, falling back to ALTERNATIVE"
                )
                thought.failure_action = FailureAction.ALTERNATIVE
                return await self.handle(
                    observation,
                    context,
                    available_agents,
                    state,
                    failure_depth=failure_depth,
                    observation_history=observation_history,
                    execution_tracker=execution_tracker,
                    observations=observations,
                )

            try:
                checkpoint = self._orch.checkpoint_manager.restore_latest(exec_id_str)
                logger.info(
                    f"[ORCHESTRATOR] ROLLBACK: restored to '{checkpoint.label}' "
                    f"(id={checkpoint.checkpoint_id})"
                )
                try:
                    from core.orchestrator.failure_metrics import record_failure_recovery

                    record_failure_recovery(
                        action="rollback",
                        success=True,
                        duration_seconds=time.perf_counter() - _recovery_start,
                        agent_name=observation.agent_name,
                    )
                except Exception:
                    pass
                _emit_accuracy("resolved")
                # Return a special "rollback" result that orchestrate() will interpret
                # to restore state. Use reason prefix "ROLLBACK:" as the signal.
                return OrchestrationResult(
                    success=True,  # Not a terminal failure -- orchestration continues
                    reason=f"ROLLBACK:{checkpoint.checkpoint_id}",
                    output=None,
                    state=state,
                    observation_history_data=checkpoint.to_dict(),
                )
            except (ValueError, Exception) as e:
                logger.warning(f"[ORCHESTRATOR] ROLLBACK failed: {e}, escalating")
                try:
                    from core.orchestrator.failure_metrics import record_failure_recovery

                    record_failure_recovery(
                        action="rollback",
                        success=False,
                        duration_seconds=time.perf_counter() - _recovery_start,
                        agent_name=observation.agent_name,
                    )
                except Exception:
                    pass
                return OrchestrationResult(
                    success=False,
                    needs_escalation=True,
                    escalation_question=(
                        f"Tried to rollback but failed: {e}. "
                        f"Original error: {observation.error}. How should I proceed?"
                    ),
                )

        elif thought.failure_action == FailureAction.ALTERNATIVE:
            alternative = thought.alternative_agent
            if not alternative:
                logger.warning(
                    "[ORCHESTRATOR] ALTERNATIVE action but no agent specified, escalating"
                )
                return OrchestrationResult(
                    success=False,
                    needs_escalation=True,
                    escalation_question=f"Task failed and no alternative agent available: {observation.task}",
                )

            # Guard: alternative must differ from the failed agent (RC4)
            if alternative == observation.agent_name:
                logger.warning(
                    f"[ORCHESTRATOR] Alternative agent '{alternative}' same as failed agent, escalating"
                )
                return OrchestrationResult(
                    success=False,
                    needs_escalation=True,
                    escalation_question=(
                        f"Agent '{observation.agent_name}' failed: {observation.error}. "
                        "No different alternative agent is available. How should I proceed?"
                    ),
                )

            logger.info(f"[ORCHESTRATOR] Trying alternative agent: {alternative}")

            # Create new task with alternative agent
            alt_task = OrchestrationTask(
                agent_name=alternative,
                description=observation.task,
                is_critical=True,
            )

            # Execute with alternative (single attempt, no retry loop)
            alt_result = await self._orch._execute_single(
                task=alt_task,
                execution_id=str(state.execution_id),
                context=context,
                execution_tracker=execution_tracker,
            )

            if alt_result.success:
                logger.info(f"[ORCHESTRATOR] Alternative agent {alternative} succeeded")
                try:
                    from core.orchestrator.failure_metrics import record_failure_recovery

                    record_failure_recovery(
                        action="alternative",
                        success=True,
                        duration_seconds=time.perf_counter() - _recovery_start,
                        agent_name=observation.agent_name,
                    )
                except Exception:
                    pass
                _emit_accuracy("resolved")
                return OrchestrationResult(
                    success=True,
                    output=alt_result.result,
                    state=state,
                    alternative_agent_used=alternative,
                )
            else:
                # Alternative also failed - escalate
                logger.warning(
                    f"[ORCHESTRATOR] Alternative agent {alternative} also failed: {alt_result.error}"
                )
                try:
                    from core.orchestrator.failure_metrics import record_failure_recovery

                    record_failure_recovery(
                        action="alternative",
                        success=False,
                        duration_seconds=time.perf_counter() - _recovery_start,
                        agent_name=observation.agent_name,
                    )
                except Exception:
                    pass
                return OrchestrationResult(
                    success=False,
                    needs_escalation=True,
                    escalation_question=f"Both {observation.agent_name} and {alternative} failed. Error: {alt_result.error}. How should I proceed?",
                )

        # RETRY is handled in _execute_with_retry, shouldn't reach here
        return OrchestrationResult(success=True)
