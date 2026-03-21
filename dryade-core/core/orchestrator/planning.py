"""PlanningOrchestrator -- DAG-based planning layer.

Wraps DryadeOrchestrator to decompose complex goals into multi-step
execution plans.  Each step delegates to the existing ReAct loop.

Design reference: 81-03 Section 3.1 (PlanningOrchestrator).

Key principles:
- PlanningOrchestrator WRAPS DryadeOrchestrator (no replacement)
- Each step is executed by the base orchestrator
- Wave execution runs parallel steps via asyncio.gather()
- Failed critical steps trigger replanning up to MAX_REPLANS times
- Single-step plans return the step result directly (no synthesis overhead)
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from core.orchestrator.context import OrchestrationContext
from core.orchestrator.models import (
    ExecutionPlan,
    OrchestrationResult,
    PlanStep,
    StepStatus,
)
from core.orchestrator.thinking import OrchestrationThinkingProvider

logger = logging.getLogger(__name__)

__all__ = ["PlanningOrchestrator"]

class PlanningOrchestrator:
    """DAG-based planning orchestrator wrapping DryadeOrchestrator.

    Decomposes complex goals into execution plans (DAGs), runs them
    wave-by-wave with parallel execution within each wave, and
    synthesizes results into a final answer.

    The base DryadeOrchestrator handles actual step execution via
    its battle-tested ReAct loop.

    Usage:
        planner = PlanningOrchestrator()
        context = OrchestrationContext(initial_state={...})
        result = await planner.orchestrate(
            goal="Analyze repo and create summary",
            context=context,
        )
    """

    MAX_REPLANS = 3

    def __init__(
        self,
        thinking_provider: OrchestrationThinkingProvider | None = None,
        base_orchestrator: Any | None = None,
    ) -> None:
        """Initialize PlanningOrchestrator.

        Args:
            thinking_provider: LLM reasoning provider.  Shared with
                base orchestrator for consistency.
            base_orchestrator: DryadeOrchestrator instance.  Created
                lazily if not provided to avoid circular imports.
        """
        self.thinking = thinking_provider or OrchestrationThinkingProvider()
        self._base = base_orchestrator

    @property
    def base(self) -> Any:
        """Lazy-initialize the base DryadeOrchestrator to avoid circular imports."""
        if self._base is None:
            from core.orchestrator.orchestrator import DryadeOrchestrator

            self._base = DryadeOrchestrator(thinking_provider=self.thinking)
        return self._base

    async def orchestrate(
        self,
        goal: str,
        context: OrchestrationContext,
        on_thinking: Callable[[str], None] | None = None,
        on_agent_event: Callable[[str, dict], None] | None = None,
        on_plan_event: Callable[[str, dict], None] | None = None,
        cancel_event: asyncio.Event | None = None,
        on_token: Callable[[str], None] | None = None,
        plan: ExecutionPlan | None = None,
    ) -> OrchestrationResult:
        """Execute a goal via DAG-based planning.

        1. Generate execution plan from goal
        2. Execute plan wave-by-wave with parallel steps
        3. Handle failures with replanning
        4. Synthesize final answer from step results

        Args:
            goal: Natural language goal.
            context: OrchestrationContext for state management.
            on_thinking: Callback for reasoning events.
            on_agent_event: Callback for agent lifecycle events.
            on_plan_event: Callback for plan-level events
                (plan_preview, progress).
            cancel_event: asyncio.Event for cancellation.
            on_token: Optional callback for token-level streaming during
                synthesis.  Forwarded to synthesize_think().

        Returns:
            OrchestrationResult with success/failure and output.
        """
        # 1. Get available agents from base orchestrator's registry
        available_agents = self.base.agents.list_agents()
        if not available_agents:
            return OrchestrationResult(
                success=False,
                reason="No agents available for planning",
            )

        # 2. Use pre-built plan or generate new one
        if plan is not None:
            logger.info("[PLANNING] Using pre-built plan (from FlowPlanner)")
            # Ensure execution order is computed
            if not plan.execution_order:
                plan.compute_execution_order()
        else:
            # Generate plan via LLM (original behavior)
            plan = await self.thinking.plan_think(
                goal=goal,
                available_agents=available_agents,
                context=context.to_dict(),
            )
        context.set_plan(plan)

        # 4. Emit plan preview
        if on_plan_event:
            on_plan_event("plan_preview", plan.to_preview_dict())

        # 5. Start execution
        plan.status = "executing"
        step_index = 0
        total_steps = len(plan.steps)
        replan_count = 0

        logger.info(
            f"[PLANNING] Executing plan: {total_steps} steps, "
            f"{len(plan.execution_order)} waves for goal: '{goal[:80]}...'"
        )

        # 6. Wave-by-wave execution
        for wave_idx, wave in enumerate(plan.execution_order):
            # Check cancellation at the top of each wave
            if cancel_event and cancel_event.is_set():
                plan.status = "cancelled"
                return OrchestrationResult(
                    success=False,
                    reason="Cancelled by user during planning execution",
                    cancelled=True,
                )

            logger.info(
                f"[PLANNING] Wave {wave_idx + 1}/{len(plan.execution_order)}: "
                f"{len(wave)} steps [{', '.join(wave)}]"
            )

            # Build coroutines for this wave
            wave_tasks: list[asyncio.Task] = []
            wave_steps: list[PlanStep] = []
            for step_id in wave:
                step = plan.get_step(step_id)
                # Skip already completed steps (from replanning)
                if step.status == StepStatus.COMPLETED:
                    continue

                step.status = StepStatus.RUNNING
                step_index += 1

                # Emit progress
                if on_plan_event:
                    on_plan_event(
                        "progress",
                        {
                            "step_id": step.id,
                            "step_name": step.task[:50],
                            "step_index": step_index,
                            "total_steps": total_steps,
                            "status": "running",
                        },
                    )

                wave_steps.append(step)
                coro = self._execute_step(
                    step=step,
                    context=context,
                    on_thinking=on_thinking,
                    on_agent_event=on_agent_event,
                )
                wave_tasks.append(asyncio.ensure_future(coro))

            if not wave_tasks:
                continue

            # Execute wave in parallel
            results = await asyncio.gather(*wave_tasks, return_exceptions=True)

            # Process results
            failed_critical_steps: list[PlanStep] = []

            for step, result in zip(wave_steps, results, strict=True):
                if isinstance(result, Exception):
                    step.status = StepStatus.FAILED
                    step.error = f"{type(result).__name__}: {str(result)}"
                    logger.error(f"[PLANNING] Step {step.id} raised exception: {step.error}")
                    if step.is_critical:
                        failed_critical_steps.append(step)
                elif isinstance(result, OrchestrationResult):
                    if result.success:
                        step.status = StepStatus.COMPLETED
                        step.result = result.output
                        # Store result in context for dependent steps
                        context.set(
                            f"step_result.{step.id}",
                            result.output,
                            scope="orchestration",
                        )
                        logger.info(f"[PLANNING] Step {step.id} completed successfully")
                    else:
                        step.status = StepStatus.FAILED
                        step.error = result.reason or "Unknown failure"
                        logger.warning(f"[PLANNING] Step {step.id} failed: {step.error}")
                        if step.is_critical:
                            failed_critical_steps.append(step)
                else:
                    # Unexpected result type - treat as success with raw output
                    step.status = StepStatus.COMPLETED
                    step.result = str(result)
                    context.set(
                        f"step_result.{step.id}",
                        str(result),
                        scope="orchestration",
                    )

                # Emit progress update
                if on_plan_event:
                    on_plan_event(
                        "progress",
                        {
                            "step_id": step.id,
                            "step_name": step.task[:50],
                            "step_index": step_index,
                            "total_steps": total_steps,
                            "status": step.status.value,
                        },
                    )

            # Handle failed critical steps with replanning
            if failed_critical_steps:
                if replan_count < self.MAX_REPLANS:
                    replan_count += 1
                    logger.info(
                        f"[PLANNING] Attempting replan #{replan_count} "
                        f"({len(failed_critical_steps)} critical failures)"
                    )

                    # Gather completed results for replanning
                    completed_results: dict[str, Any] = {}
                    for s in plan.steps:
                        if s.status == StepStatus.COMPLETED and s.result is not None:
                            completed_results[s.id] = s.result

                    new_plan = await self._replan(
                        plan=plan,
                        failed_steps=failed_critical_steps,
                        completed_results=completed_results,
                        available_agents=available_agents,
                    )

                    if new_plan is not None:
                        plan = new_plan
                        context.set_plan(plan)
                        total_steps = len(plan.steps)
                        # Emit updated plan preview
                        if on_plan_event:
                            on_plan_event("plan_preview", plan.to_preview_dict())
                        # Break out of wave loop to restart with new plan
                        break
                    else:
                        logger.warning("[PLANNING] Replan failed, aborting execution")
                        plan.status = "failed"
                        return OrchestrationResult(
                            success=False,
                            reason=(
                                f"Critical step(s) failed and replanning failed: "
                                f"{', '.join(s.id for s in failed_critical_steps)}"
                            ),
                        )
                else:
                    logger.warning(f"[PLANNING] MAX_REPLANS ({self.MAX_REPLANS}) exceeded")
                    plan.status = "failed"
                    return OrchestrationResult(
                        success=False,
                        reason=(
                            f"Critical step(s) failed after {self.MAX_REPLANS} replans: "
                            f"{', '.join(s.id for s in failed_critical_steps)}"
                        ),
                    )
        else:
            # All waves completed without breaking for replan
            pass

        # 7. If we broke out for replanning, re-execute with new plan
        # (Recursive call -- bounded by MAX_REPLANS checked above)
        if plan.status == "executing" and any(s.status == StepStatus.PENDING for s in plan.steps):
            # There are still pending steps from a replanned plan
            # Re-run the execution with the updated plan
            return await self.orchestrate(
                goal=goal,
                context=context,
                on_thinking=on_thinking,
                on_agent_event=on_agent_event,
                on_plan_event=on_plan_event,
                cancel_event=cancel_event,
                on_token=on_token,
            )

        # 8. Plan completed
        plan.status = "completed"

        # 9. Synthesize final answer
        completed_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED]

        if len(completed_steps) == 1:
            # Single completed step -- return its result directly
            final_answer = str(completed_steps[0].result or "")
        elif completed_steps:
            # Multiple steps -- synthesize via LLM
            step_results = {s.id: str(s.result or "") for s in completed_steps}
            final_answer = await self.thinking.synthesize_think(
                goal=goal,
                step_results=step_results,
                on_token=on_token,
                on_thinking=on_thinking,
                cancel_event=cancel_event,
            )
        else:
            final_answer = "No steps completed successfully."

        logger.info(
            f"[PLANNING] Plan completed: {len(completed_steps)}/{len(plan.steps)} steps succeeded"
        )

        return OrchestrationResult(
            success=True,
            output=final_answer,
            streamed=bool(on_token and len(completed_steps) > 1),
        )

    async def _execute_step(
        self,
        step: PlanStep,
        context: OrchestrationContext,
        on_thinking: Callable[[str], None] | None = None,
        on_agent_event: Callable[[str, dict], None] | None = None,
    ) -> OrchestrationResult:
        """Execute a single plan step via the base orchestrator.

        Builds a step-level context from the orchestration context
        plus dependency results, clears the step scope, and delegates
        to the base DryadeOrchestrator's ReAct loop.

        Args:
            step: PlanStep to execute.
            context: OrchestrationContext for state access.
            on_thinking: Reasoning callback.
            on_agent_event: Agent lifecycle callback.

        Returns:
            OrchestrationResult from the base orchestrator.
        """
        start_time = time.perf_counter()

        # Build step context from orchestration context + dependency results
        step_context = context.to_dict()
        for dep_id in step.depends_on:
            dep_result = context.get(f"step_result.{dep_id}")
            if dep_result is not None:
                step_context[f"dep_{dep_id}"] = dep_result

        # Clear step-scoped state from previous step
        context.clear_step_scope()

        # Determine agent filter
        agent_filter: list[str] | None = None
        if step.agent_name:
            agent_filter = [step.agent_name]

        # Delegate to base orchestrator's ReAct loop
        result = await self.base.orchestrate(
            goal=step.task,
            context=step_context,
            agent_filter=agent_filter,
            on_thinking=on_thinking,
            on_agent_event=on_agent_event,
        )

        # Record actual duration on the step
        step.actual_duration_ms = int((time.perf_counter() - start_time) * 1000)

        return result

    async def _replan(
        self,
        plan: ExecutionPlan,
        failed_steps: list[PlanStep],
        completed_results: dict[str, Any],
        available_agents: list[Any],
    ) -> ExecutionPlan | None:
        """Generate a revised plan after step failures.

        Args:
            plan: The original/current plan.
            failed_steps: Steps that failed.
            completed_results: Results from completed steps.
            available_agents: Available agents.

        Returns:
            New ExecutionPlan or None if replanning failed.
        """
        return await self.thinking.replan_think(
            original_plan=plan,
            failed_steps=failed_steps,
            completed_results=completed_results,
            available_agents=available_agents,
        )
