"""Retry execution logic for DryadeOrchestrator.

Extracted from DryadeOrchestrator._execute_with_retry() for maintainability.
Pure structural refactor -- zero behavioral changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import core.orchestrator.orchestrator as _orch_module
from core.orchestrator.failure_classifier import FailureClassifier
from core.orchestrator.models import (
    ErrorCategory,
    FailureAction,
    OrchestrationObservation,
    OrchestrationTask,
    OrchestrationThought,
)
from core.orchestrator.observation import ObservationHistory

if TYPE_CHECKING:
    from core.adapters.protocol import AgentCard
    from core.orchestrator.models import OrchestrationState
    from core.orchestrator.orchestrator import DryadeOrchestrator
    from core.orchestrator.soft_failure_detector import ExecutionTracker

logger = logging.getLogger(__name__)

class RetryExecutor:
    """Handles task execution with retry logic.

    Extracted from DryadeOrchestrator._execute_with_retry().
    """

    def __init__(self, orchestrator: DryadeOrchestrator) -> None:
        """Accept reference to parent orchestrator for shared state access."""
        self._orch = orchestrator

    async def execute(
        self,
        task: OrchestrationTask,
        execution_id: str,
        context: dict[str, Any],
        available_agents: list[AgentCard],
        failure_depth: int = 0,
        execution_tracker: ExecutionTracker | None = None,
        state: OrchestrationState | None = None,
        observation_history: ObservationHistory | None = None,
        observations: list[OrchestrationObservation] | None = None,
    ) -> OrchestrationObservation:
        """Execute task with intelligent retry logic.

        Per user decision: Default 3 retries, 30s timeout.
        Uses LLM to determine if error is retryable before attempting retry.
        Note: Skills are NOT executed here - they use bash tool (OpenClaw pattern).
        Moved from DryadeOrchestrator._execute_with_retry().
        """
        agent = self._orch.agents.get(task.agent_name)
        if not agent:
            error_msg = f"Agent '{task.agent_name}' not found"
            obs = OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=None,
                success=False,
                error=error_msg,
            )
            # --- Tier 1: Deterministic classification (no LLM cost) ---
            tool_error = self._orch._to_tool_error(task, error_msg)
            _classify_start = time.perf_counter()
            classification = FailureClassifier.classify(tool_error)
            _classify_elapsed = time.perf_counter() - _classify_start
            try:
                from core.orchestrator.failure_metrics import record_failure_classification

                record_failure_classification(
                    tier="deterministic",
                    category=classification.category.value,
                    action=classification.suggested_action.value,
                    duration_seconds=_classify_elapsed,
                )
            except Exception:
                pass
            obs.error_classification = classification

            if classification.category != ErrorCategory.SEMANTIC:
                logger.info(
                    f"[ORCHESTRATOR] Agent-not-found Tier 1: {classification.category.value} -> "
                    f"{classification.suggested_action.value} (confidence={classification.confidence})"
                )
                obs.failure_thought = OrchestrationThought(
                    reasoning=f"Deterministic: {classification.reason}",
                    is_final=False,
                    failure_action=classification.suggested_action,
                )
            else:
                # --- Tier 2: LLM-based classification ---
                try:
                    thought = await self._orch.thinking.failure_think(
                        agent_name=task.agent_name,
                        task_description=task.description,
                        error=error_msg,
                        retry_count=0,
                        max_retries=0,
                        is_critical=True,
                        available_agents=available_agents,
                        failure_depth=failure_depth,
                    )
                    try:
                        from core.orchestrator.failure_metrics import record_failure_llm_call

                        record_failure_llm_call(call_type="failure_think")
                    except Exception:
                        pass
                    obs.failure_thought = thought
                    obs.error_classification = classification  # Still store even for SEMANTIC
                except Exception:
                    logger.warning(
                        "[ORCHESTRATOR] failure_think failed for agent-not-found, will use default"
                    )
            return obs

        # Get retry config from agent capabilities
        caps = agent.capabilities()
        cfg = _orch_module.get_orchestration_config()
        max_retries = caps.max_retries if caps.max_retries else cfg.max_retries
        timeout = caps.timeout_seconds if caps.timeout_seconds else cfg.agent_timeout
        is_critical = caps.is_critical if caps else True

        # Validate capabilities before execution
        valid, error = self._orch._validate_capabilities(agent, task)
        if not valid:
            return OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=None,
                success=False,
                error=error,
            )

        # Extract server name early -- needed by connectivity probe + circuit breaker
        server_name = self._orch._get_server_for_task(task)

        # PREVENTION: Connectivity probe (Phase 118.9)
        if server_name and cfg.prevention_enabled and cfg.connectivity_probe_enabled:
            try:
                from core.orchestrator.prevention import PreventionVerdict, get_prevention_pipeline

                conn_result = await get_prevention_pipeline().probe_connectivity(server_name)
                if conn_result and conn_result.verdict == PreventionVerdict.FAIL:
                    logger.warning(
                        "[ORCHESTRATOR] Connectivity probe failed for '%s': %s",
                        server_name,
                        conn_result.reason,
                    )
                    # Feed into circuit breaker
                    if cfg.circuit_breaker_enabled:
                        self._orch.circuit_breaker.record_failure(server_name)
                    return OrchestrationObservation(
                        agent_name=task.agent_name,
                        task=task.description,
                        result=None,
                        success=False,
                        error=f"MCP server '{server_name}' connectivity check failed: {conn_result.reason}",
                    )
            except Exception as e:
                logger.warning("[ORCHESTRATOR] Connectivity probe error (fail-open): %s", e)

        # PREVENTION: Circuit breaker gate (Phase 118.2)
        if (
            server_name
            and cfg.circuit_breaker_enabled
            and not self._orch.circuit_breaker.can_execute(server_name)
        ):
            circuit_state = self._orch.circuit_breaker.get_state(server_name)
            logger.warning(
                f"[ORCHESTRATOR] Circuit OPEN for MCP server '{server_name}' "
                f"(state={circuit_state.value}), skipping execution"
            )
            return OrchestrationObservation(
                agent_name=task.agent_name,
                task=task.description,
                result=None,
                success=False,
                error=f"MCP server '{server_name}' circuit is open (too many recent failures). "
                f"Will retry automatically after cooldown.",
                failure_thought=OrchestrationThought(
                    reasoning=f"Circuit breaker open for server '{server_name}'. "
                    f"Skipping to avoid cascading failure.",
                    is_final=False,
                    failure_action=FailureAction.SKIP,
                ),
            )

        # Pre-emptive circuit breaking from failure history (Phase 118.7)
        if (
            server_name
            and cfg.failure_learning_enabled
            and cfg.preemptive_circuit_break_enabled
            and cfg.circuit_breaker_enabled
        ):
            try:
                if self._orch.pattern_detector.should_preempt_circuit_break(server_name):
                    server_rate = self._orch.failure_history_store.get_server_failure_rate(
                        server_name, window_hours=1
                    )
                    opened = self._orch.circuit_breaker.inject_external_failure_rate(
                        server_name, server_rate, threshold=0.7
                    )
                    if opened:
                        logger.warning(
                            "[ORCHESTRATOR] Pre-emptive circuit break for server '%s' "
                            "(historical rate=%.2f)",
                            server_name,
                            server_rate,
                        )
                        # Re-check can_execute after pre-emptive open
                        if not self._orch.circuit_breaker.can_execute(server_name):
                            return OrchestrationObservation(
                                agent_name=task.agent_name,
                                task=task.description,
                                result=None,
                                success=False,
                                error=f"MCP server '{server_name}' pre-emptively circuit-broken "
                                f"(historical failure rate {server_rate:.0%}). Will retry after cooldown.",
                                failure_thought=OrchestrationThought(
                                    reasoning=f"Pre-emptive circuit break: server '{server_name}' has "
                                    f"{server_rate:.0%} failure rate over last hour.",
                                    is_final=False,
                                    failure_action=FailureAction.SKIP,
                                ),
                            )
            except Exception as e:
                logger.warning(
                    "[ORCHESTRATOR] Pre-emptive circuit break check failed (non-fatal): %s", e
                )

        retry_count = 0
        last_error = None
        last_failure_thought = None  # Track last LLM decision to avoid redundant call

        # Checkpoint state before execution (Phase 118.5)
        cfg_cp = _orch_module.get_orchestration_config()
        if cfg_cp.checkpoint_enabled and state is not None and observation_history is not None:
            try:
                cp_id = self._orch.checkpoint_manager.create(
                    execution_id=execution_id,
                    state=state,
                    observation_history=observation_history,
                    observations=observations or [],
                    failure_depth=failure_depth,
                    execution_tracker=execution_tracker,
                    label=f"before:{task.agent_name}:{task.tool or task.description[:30]}",
                )
                logger.debug(
                    f"[ORCHESTRATOR] Checkpoint created: {cp_id} (before {task.agent_name})"
                )
                # Persist if persistent backend enabled (uses lazy property -- single connection)
                if cfg_cp.persistent_checkpoint_enabled:
                    self._orch.persistent_checkpoint_backend.save(
                        self._orch.checkpoint_manager.restore(execution_id, cp_id)
                    )
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Checkpoint creation failed (non-fatal): {e}")

        # PREVENTION: Schema validation (Phase 118.9)
        if server_name and cfg.prevention_enabled and cfg.schema_validation_enabled and task.tool:
            try:
                from core.orchestrator.prevention import PreventionVerdict, get_prevention_pipeline

                schema_result = get_prevention_pipeline().validate_tool_schema(
                    server_name=server_name,
                    tool_name=task.tool,
                    arguments=task.arguments or {},
                )
                if schema_result and schema_result.verdict == PreventionVerdict.FAIL:
                    logger.warning(
                        "[ORCHESTRATOR] Schema validation failed for %s/%s: %s",
                        server_name,
                        task.tool,
                        schema_result.reason,
                    )
                    # Record in failure history for future pattern detection
                    self._orch._record_failure_history(
                        task=task,
                        error_category=ErrorCategory.PERMANENT,
                        error_msg=schema_result.reason,
                        action_taken=FailureAction.ESCALATE,
                        recovery_success=False,
                    )
                    return OrchestrationObservation(
                        agent_name=task.agent_name,
                        task=task.description,
                        result=None,
                        success=False,
                        error=f"Schema validation failed: {schema_result.reason}",
                    )
            except Exception as e:
                logger.warning("[ORCHESTRATOR] Schema validation error (fail-open): %s", e)

        while retry_count <= max_retries:
            result = await self._orch._execute_single(
                task, execution_id, context, timeout, execution_tracker=execution_tracker
            )

            if result.success:
                if server_name and cfg.circuit_breaker_enabled:
                    self._orch.circuit_breaker.record_success(server_name)
                # Record recovery success if there were retries (Phase 118.7)
                if retry_count > 0:
                    self._orch._record_failure_history(
                        task=task,
                        error_category=ErrorCategory.TRANSIENT,
                        error_msg=last_error or "recovered after retry",
                        action_taken=FailureAction.RETRY,
                        recovery_success=True,
                        retry_count=retry_count,
                    )
                    # Phase 118.8: OnRecovery middleware hooks
                    if cfg.failure_middleware_enabled:
                        try:
                            from core.orchestrator.failure_middleware import FailureContext
                            from core.orchestrator.failure_middleware import (
                                RecoveryResult as FMRecoveryResult,
                            )

                            recovery_ctx = FailureContext(
                                observation=result,
                                error_classification=None,
                                failure_action=FailureAction.RETRY,
                                failure_depth=0,
                                tool_error=None,
                                metadata={},
                            )
                            recovery_result = FMRecoveryResult(
                                success=True,
                                output=result.result,
                                metadata={"retry_count": retry_count, "agent": task.agent_name},
                            )
                            await self._orch.failure_pipeline.run_on_recovery(
                                recovery_ctx, recovery_result
                            )
                        except Exception:
                            pass  # Strictly non-fatal
                    # Emit retry success metric (Phase 118.10 gap closure)
                    try:
                        from core.orchestrator.failure_metrics import record_failure_recovery

                        record_failure_recovery(
                            action="retry",
                            success=True,
                            duration_seconds=time.perf_counter() - _execute_start,
                            agent_name=task.agent_name,
                        )
                    except Exception:
                        pass
                result.retry_count = retry_count
                return result

            # Record failure for circuit breaker
            if server_name and cfg.circuit_breaker_enabled:
                self._orch.circuit_breaker.record_failure(server_name)

            last_error = result.error

            # --- Tier 1: Deterministic classification (no LLM cost) ---
            tool_error = self._orch._to_tool_error(task, last_error or "Unknown error")
            _classify_start_retry = time.perf_counter()
            classification = FailureClassifier.classify(tool_error)
            _classify_elapsed_retry = time.perf_counter() - _classify_start_retry
            try:
                from core.orchestrator.failure_metrics import record_failure_classification

                record_failure_classification(
                    tier="deterministic",
                    category=classification.category.value,
                    action=classification.suggested_action.value,
                    duration_seconds=_classify_elapsed_retry,
                )
            except Exception:
                pass
            result.error_classification = classification

            # If classifier is confident (not SEMANTIC), skip the LLM call entirely
            if classification.category != ErrorCategory.SEMANTIC:
                logger.info(
                    f"[ORCHESTRATOR] Tier 1 classified: {classification.category.value} -> "
                    f"{classification.suggested_action.value} (confidence={classification.confidence})"
                )
                thought = OrchestrationThought(
                    reasoning=f"Deterministic classification: {classification.reason}",
                    is_final=False,
                    failure_action=classification.suggested_action,
                )
            else:
                # --- Tier 2: LLM-based classification (SEMANTIC errors only) ---
                thought = await self._orch.thinking.failure_think(
                    agent_name=task.agent_name,
                    task_description=task.description,
                    error=last_error or "Unknown error",
                    retry_count=retry_count,
                    max_retries=max_retries,
                    is_critical=is_critical,
                    available_agents=available_agents,
                    failure_depth=failure_depth,
                )
                try:
                    from core.orchestrator.failure_metrics import record_failure_llm_call

                    record_failure_llm_call(call_type="failure_think")
                except Exception:
                    pass
            logger.debug(
                f"[ORCHESTRATOR] failure classification for {task.agent_name}, "
                f"action={thought.failure_action.value}"
            )
            last_failure_thought = thought  # Store for use if retries exhaust

            # Refine adaptive retry for this specific error category (Phase 118.7)
            if cfg.failure_learning_enabled and classification.category != ErrorCategory.SEMANTIC:
                try:
                    refined = self._orch.adaptive_retry_strategy.get_retry_params(
                        tool_name=task.tool or task.agent_name,
                        error_category=classification.category.value,
                    )
                    if refined.get("reason") != "no history":
                        max_retries = refined["max_retries"]
                        logger.debug(
                            "[ORCHESTRATOR] Refined adaptive retry for %s/%s: max_retries=%d",
                            task.tool or task.agent_name,
                            classification.category.value,
                            max_retries,
                        )
                except Exception:
                    pass  # Non-fatal, keep existing max_retries

            # If LLM says don't retry, return immediately with the failure info
            if thought.failure_action != FailureAction.RETRY:
                logger.info(
                    f"[ORCHESTRATOR] LLM decided {thought.failure_action.value} (not retry): "
                    f"agent={task.agent_name}, error={last_error}"
                )
                # Record failure to history (Phase 118.7)
                self._orch._record_failure_history(
                    task=task,
                    error_category=classification.category,
                    error_msg=last_error or "Unknown error",
                    action_taken=thought.failure_action,
                    recovery_success=False,
                    retry_count=retry_count,
                )
                # Return observation with failure action info for _handle_failure
                result.retry_count = retry_count
                # Store the thought decision for later handling
                result.failure_thought = thought
                return result

            # BUG-006: Prevent blind retry on timeout with identical parameters.
            # The retry loop cannot modify task parameters, so retrying a timed-out
            # call is futile and wastes N * timeout seconds.
            if last_error and "timed out" in last_error.lower():
                logger.warning(
                    f"[ORCHESTRATOR] Timeout retry blocked - identical params would be used. "
                    f"Forcing escalation. agent={task.agent_name}, tool={task.tool}"
                )
                result.failure_thought = OrchestrationThought(
                    reasoning=f"Retry blocked: '{task.tool or task.description}' timed out and "
                    f"retry would use identical parameters. Escalating instead.",
                    is_final=False,
                    failure_action=FailureAction.ESCALATE,
                    escalation_question=(
                        f"Tool '{task.tool or task.agent_name}' timed out. "
                        f"Retrying with the same parameters won't help. "
                        f"Would you like me to try a different approach?"
                    ),
                )
                # Record timeout failure to history (Phase 118.7)
                self._orch._record_failure_history(
                    task=task,
                    error_category=ErrorCategory.TRANSIENT,
                    error_msg=last_error or "timeout",
                    action_taken=FailureAction.ESCALATE,
                    recovery_success=False,
                    retry_count=retry_count,
                )
                return result

            retry_count += 1

            if retry_count <= max_retries:
                logger.info(
                    f"[ORCHESTRATOR] LLM approved retry (attempt {retry_count}/{max_retries}): "
                    f"agent={task.agent_name}, error={last_error}"
                )
                # Exponential backoff
                await asyncio.sleep(min(2**retry_count, 10))

        # All retries exhausted - create observation with the last failure thought attached
        # to avoid redundant LLM call in _handle_failure
        # Record retry exhaustion to failure history (Phase 118.7)
        self._orch._record_failure_history(
            task=task,
            error_category=ErrorCategory.TRANSIENT,
            error_msg=last_error or "retries exhausted",
            action_taken=FailureAction.RETRY,
            recovery_success=False,
            retry_count=retry_count - 1,
        )
        observation = OrchestrationObservation(
            agent_name=task.agent_name,
            task=task.description,
            result=None,
            success=False,
            error=f"Failed after {max_retries} retries: {last_error}",
            retry_count=retry_count - 1,
        )
        # CRITICAL: Attach last thought so _handle_failure doesn't call LLM again
        if last_failure_thought:
            observation.failure_thought = last_failure_thought
        return observation
