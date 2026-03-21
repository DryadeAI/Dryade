"""Unit tests for PlanningOrchestrator (DAG-based planning layer).

Tests cover:
- Plan generation and execution flow
- Wave-by-wave parallel execution
- Cancellation handling
- Single-step plan shortcut
- Failed critical steps and replanning
- Max replans exceeded
- Synthesis for multi-step plans
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator.context import OrchestrationContext
from core.orchestrator.models import (
    ExecutionPlan,
    OrchestrationResult,
    PlanStep,
    StepStatus,
)
from core.orchestrator.planning import PlanningOrchestrator

def _make_plan(steps: list[PlanStep], waves: list[list[str]] | None = None) -> ExecutionPlan:
    """Helper to create an ExecutionPlan with given steps and waves."""
    plan = ExecutionPlan(
        id="plan-1",
        goal="test goal",
        steps=steps,
        execution_order=waves or [[s.id for s in steps]],
    )
    return plan

def _make_step(
    step_id: str,
    agent: str = "agent1",
    is_critical: bool = True,
    depends_on: list[str] | None = None,
) -> PlanStep:
    return PlanStep(
        id=step_id,
        agent_name=agent,
        task=f"Do {step_id}",
        is_critical=is_critical,
        depends_on=depends_on or [],
    )

class TestPlanningOrchestratorNoAgents:
    @pytest.mark.asyncio
    async def test_returns_failure_when_no_agents(self):
        mock_thinking = MagicMock()
        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = []

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        assert not result.success
        assert "No agents" in result.reason

class TestPlanningOrchestratorSingleStep:
    @pytest.mark.asyncio
    async def test_single_step_returns_result_directly(self):
        """Single completed step -> no synthesis, return result directly."""
        step = _make_step("s1")
        plan = _make_plan([step], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(
            return_value=OrchestrationResult(success=True, output="step1 done")
        )

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        assert result.success
        assert result.output == "step1 done"
        # synthesize_think should NOT be called for single step
        mock_thinking.synthesize_think.assert_not_called()

class TestPlanningOrchestratorMultiStep:
    @pytest.mark.asyncio
    async def test_multi_step_synthesizes_results(self):
        """Multiple steps -> call synthesize_think."""
        s1 = _make_step("s1")
        s2 = _make_step("s2")
        plan = _make_plan([s1, s2], [["s1", "s2"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)
        mock_thinking.synthesize_think = AsyncMock(return_value="synthesized answer")

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(
            return_value=OrchestrationResult(success=True, output="done")
        )

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="multi step test", context=ctx)
        assert result.success
        assert result.output == "synthesized answer"
        mock_thinking.synthesize_think.assert_called_once()

class TestPlanningOrchestratorCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_at_wave_start(self):
        s1 = _make_step("s1")
        plan = _make_plan([s1], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        cancel = asyncio.Event()
        cancel.set()  # Pre-cancelled

        result = await planner.orchestrate(goal="test", context=ctx, cancel_event=cancel)
        assert not result.success
        assert result.cancelled

class TestPlanningOrchestratorCriticalFailure:
    @pytest.mark.asyncio
    async def test_critical_failure_triggers_replan(self):
        """Critical step fails -> replan is attempted."""
        s1 = _make_step("s1", is_critical=True)
        plan = _make_plan([s1], [["s1"]])

        # New plan after replan has a single successful step
        s2 = _make_step("s2")
        new_plan = _make_plan([s2], [["s2"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)
        mock_thinking.replan_think = AsyncMock(return_value=new_plan)
        mock_thinking.synthesize_think = AsyncMock(return_value="done")

        call_count = 0

        async def mock_orchestrate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrchestrationResult(success=False, reason="step failed")
            return OrchestrationResult(success=True, output="retry worked")

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(side_effect=mock_orchestrate)

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        # Replan was called
        mock_thinking.replan_think.assert_called_once()

    @pytest.mark.asyncio
    async def test_replan_failure_returns_error(self):
        """If replan_think returns None, abort."""
        s1 = _make_step("s1", is_critical=True)
        plan = _make_plan([s1], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)
        mock_thinking.replan_think = AsyncMock(return_value=None)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(
            return_value=OrchestrationResult(success=False, reason="failed")
        )

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        assert not result.success
        assert "replanning failed" in result.reason

    @pytest.mark.asyncio
    async def test_max_replans_exceeded(self):
        """After MAX_REPLANS failures, abort."""
        s1 = _make_step("s1", is_critical=True)
        plan = _make_plan([s1], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(
            return_value=OrchestrationResult(success=False, reason="always fail")
        )

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        # Set MAX_REPLANS to 0 so first critical failure immediately exceeds limit
        planner.MAX_REPLANS = 0
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        assert not result.success
        assert "replans" in result.reason.lower()

class TestPlanningOrchestratorStepExecution:
    @pytest.mark.asyncio
    async def test_exception_in_step_marks_failed(self):
        """Step that raises exception is marked as FAILED."""
        s1 = _make_step("s1", is_critical=False)
        plan = _make_plan([s1], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(side_effect=RuntimeError("boom"))

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        # Non-critical failure -> plan completes but no successful steps
        assert result.success
        assert result.output == "No steps completed successfully."

    @pytest.mark.asyncio
    async def test_plan_events_emitted(self):
        """on_plan_event callback receives plan_preview and progress events."""
        s1 = _make_step("s1")
        plan = _make_plan([s1], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]
        mock_base.orchestrate = AsyncMock(
            return_value=OrchestrationResult(success=True, output="done")
        )

        events = []

        def on_plan_event(event_type, data):
            events.append((event_type, data))

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        await planner.orchestrate(goal="test", context=ctx, on_plan_event=on_plan_event)

        event_types = [e[0] for e in events]
        assert "plan_preview" in event_types
        assert "progress" in event_types

    @pytest.mark.asyncio
    async def test_skips_already_completed_steps(self):
        """Steps already in COMPLETED status are skipped."""
        s1 = _make_step("s1")
        s1.status = StepStatus.COMPLETED  # Pre-completed
        plan = _make_plan([s1], [["s1"]])

        mock_thinking = MagicMock()
        mock_thinking.plan_think = AsyncMock(return_value=plan)

        mock_base = MagicMock()
        mock_base.agents.list_agents.return_value = [MagicMock()]

        planner = PlanningOrchestrator(
            thinking_provider=mock_thinking,
            base_orchestrator=mock_base,
        )
        ctx = OrchestrationContext()
        result = await planner.orchestrate(goal="test", context=ctx)
        # No orchestrate call since step was already completed
        mock_base.orchestrate.assert_not_called()
        assert result.success
        # Step was pre-completed with result=None -> single step path returns ""
        assert result.output == ""

class TestPlanningOrchestratorLazyBase:
    def test_lazy_base_property(self):
        """Base orchestrator is created lazily when accessed."""
        planner = PlanningOrchestrator(thinking_provider=MagicMock())
        assert planner._base is None
        # We can't easily test the lazy creation without importing DryadeOrchestrator
        # but we can verify the logic path exists
