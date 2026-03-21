"""Post-orchestration reflection engine for self-assessment.

Phase 115.3: Rule-based reflection that runs AFTER orchestrate() returns.
Assesses orchestration quality, detects failure patterns, and optionally
writes observations to memory blocks for future reference.

This is rule-based only (no LLM calls). LLM-based reflection is deferred
to a future phase.
"""

import logging
from enum import Enum

from pydantic import BaseModel, Field

from core.orchestrator.models import OrchestrationObservation, OrchestrationResult

logger = logging.getLogger(__name__)

__all__ = [
    "ReflectionMode",
    "ReflectionResult",
    "ReflectionEngine",
]

class ReflectionMode(str, Enum):
    """When to trigger post-orchestration reflection."""

    OFF = "off"
    ON_FAILURE = "on_failure"
    ALWAYS = "always"

class ReflectionResult(BaseModel):
    """Result of a reflection pass over an orchestration outcome."""

    triggered: bool = False
    trigger_reason: str = ""
    quality_assessment: str = ""  # Brief quality note
    memory_updates: list[dict] = Field(
        default_factory=list
    )  # {"label": ..., "action": ..., "content": ...}
    capability_suggestions: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)  # success_rate, routing_accuracy, etc.

class ReflectionEngine:
    """Rule-based post-orchestration reflection engine.

    Runs AFTER orchestrate() returns, not inside the ReAct loop.
    Triggers on failure conditions (on_failure mode) without LLM calls.
    """

    def __init__(self, mode: ReflectionMode = ReflectionMode.ON_FAILURE):
        self.mode = mode
        self._in_reflection = False  # Prevent re-entry

    def should_reflect(
        self,
        result: OrchestrationResult,
        observations: list[OrchestrationObservation],
    ) -> bool:
        """Rule-based trigger detection. No LLM call.

        Returns True if reflection should run based on mode and result state.
        """
        if self.mode == ReflectionMode.OFF:
            return False

        if self._in_reflection:
            return False  # Prevent recursion

        if self.mode == ReflectionMode.ALWAYS:
            return True

        # ON_FAILURE mode: check for failure indicators
        if not result.success:
            return True

        if result.needs_escalation:
            return True

        if any(not obs.success for obs in observations):
            return True

        return False

    async def reflect(
        self,
        result: OrchestrationResult,
        observations: list[OrchestrationObservation],
        goal: str,
        conversation_id: str,
    ) -> ReflectionResult:
        """Run rule-based reflection on orchestration outcome.

        This is rule-based only (no LLM call). Analyzes the result and
        observations to produce quality metrics and suggestions.

        Args:
            result: The orchestration result to reflect on.
            observations: All observations from the orchestration.
            goal: The original user goal.
            conversation_id: For scoping memory block writes.

        Returns:
            ReflectionResult with metrics, suggestions, and optional memory updates.
        """
        self._in_reflection = True
        try:
            return await self._do_reflect(result, observations, goal, conversation_id)
        finally:
            self._in_reflection = False

    async def _do_reflect(
        self,
        result: OrchestrationResult,
        observations: list[OrchestrationObservation],
        goal: str,
        conversation_id: str,
    ) -> ReflectionResult:
        """Internal reflection logic."""
        # Build quality metrics
        success_count = sum(1 for obs in observations if obs.success)
        failure_count = sum(1 for obs in observations if not obs.success)
        total_count = len(observations)
        success_rate = success_count / total_count if total_count > 0 else 0.0

        metrics = {
            "success_count": success_count,
            "failure_count": failure_count,
            "total_observations": total_count,
            "success_rate": round(success_rate, 3),
            "result_success": result.success,
            "needed_escalation": result.needs_escalation,
        }

        # Determine trigger reason
        trigger_reason = ""
        if not result.success:
            trigger_reason = "orchestration_failed"
        elif result.needs_escalation:
            trigger_reason = "escalation_needed"
        elif failure_count > 0:
            trigger_reason = f"observation_failures ({failure_count}/{total_count})"
        elif self.mode == ReflectionMode.ALWAYS:
            trigger_reason = "always_mode"

        # Build quality assessment
        if not result.success and result.needs_escalation:
            quality = f"Orchestration failed and escalated. {failure_count}/{total_count} observations failed."
        elif not result.success:
            quality = f"Orchestration failed. {failure_count}/{total_count} observations failed."
        elif failure_count > 0:
            quality = f"Orchestration succeeded with {failure_count} failed observation(s) out of {total_count}."
        else:
            quality = f"Orchestration succeeded cleanly. {success_count} observation(s) all passed."

        # Suggest memory updates for failures
        memory_updates: list[dict] = []
        capability_suggestions: list[str] = []

        for obs in observations:
            if not obs.success and obs.error:
                # Suggest a memory note about the failure
                memory_updates.append(
                    {
                        "label": "system_notes",
                        "action": "append",
                        "content": f"Observation failure: agent={obs.agent_name}, task={obs.task[:80]}, error={obs.error[:120]}",
                    }
                )

                # Suggest capability improvements
                if "not found" in (obs.error or "").lower():
                    capability_suggestions.append(
                        f"Agent '{obs.agent_name}' not found -- consider creating it"
                    )
                elif "timed out" in (obs.error or "").lower():
                    capability_suggestions.append(
                        f"Agent '{obs.agent_name}' timed out -- consider increasing timeout"
                    )

        # Optionally write to memory blocks (only if system_notes block exists)
        if memory_updates and conversation_id:
            try:
                from core.orchestrator.memory_tools import get_memory_block_store

                store = get_memory_block_store()
                blocks = store.get_blocks(conversation_id)
                has_system_notes = any(b.label == "system_notes" for b in blocks)

                if has_system_notes:
                    from core.orchestrator.memory_tools import execute_memory_insert

                    for update in memory_updates[:3]:  # Limit to 3 updates per reflection
                        try:
                            execute_memory_insert(
                                agent_id=conversation_id,
                                label=update["label"],
                                new_str=update["content"],
                            )
                        except Exception as e:
                            logger.warning(f"[REFLECTION] Failed to write memory update: {e}")
            except Exception as e:
                logger.warning(f"[REFLECTION] Memory block access failed: {e}")

        reflection_result = ReflectionResult(
            triggered=True,
            trigger_reason=trigger_reason,
            quality_assessment=quality,
            memory_updates=memory_updates,
            capability_suggestions=capability_suggestions,
            metrics=metrics,
        )

        logger.info(
            f"[REFLECTION] Completed: reason={trigger_reason}, "
            f"success_rate={success_rate:.1%}, "
            f"memory_updates={len(memory_updates)}, "
            f"suggestions={len(capability_suggestions)}"
        )

        return reflection_result
