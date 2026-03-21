"""Unit tests for autonomous planner (Plan-and-Execute) and scheduler.

Tests cover:
- PlanStep: initialization, repr
- Plan: properties (current_step, remaining, is_complete, advance), to_dict
- PlanAndExecuteAutonomy: achieve_goal flow, leash checking, replanning, complexity estimation
- ProactiveScheduler: schedule_heartbeat, schedule_cron, schedule_oneshot, job management
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.autonomous.models import ExecutionResult
from core.autonomous.planner import (
    Plan,
    PlanAndExecuteAutonomy,
    PlanStep,
)

# ---------------------------------------------------------------------------
# PlanStep
# ---------------------------------------------------------------------------

class TestPlanStep:
    def test_basic_creation(self):
        step = PlanStep(step_id=1, description="Analyze code")
        assert step.step_id == 1
        assert step.description == "Analyze code"
        assert step.skill_hint is None
        assert step.inputs_hint == {}
        assert step.depends_on == []

    def test_with_all_fields(self):
        step = PlanStep(
            step_id=2,
            description="Deploy app",
            skill_hint="deploy",
            inputs_hint={"env": "staging"},
            depends_on=[1],
        )
        assert step.skill_hint == "deploy"
        assert step.inputs_hint == {"env": "staging"}
        assert step.depends_on == [1]

    def test_repr(self):
        step = PlanStep(step_id=1, description="A" * 100)
        r = repr(step)
        assert "PlanStep(1:" in r
        assert "..." in r  # Truncated

# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

class TestPlan:
    def _make_plan(self, n_steps: int = 3) -> Plan:
        steps = [PlanStep(step_id=i, description=f"Step {i}") for i in range(1, n_steps + 1)]
        return Plan(goal="test goal", steps=steps)

    def test_current_step(self):
        plan = self._make_plan(3)
        assert plan.current_step.step_id == 1

    def test_current_step_none_when_complete(self):
        plan = self._make_plan(1)
        plan.advance()
        assert plan.current_step is None

    def test_remaining_steps(self):
        plan = self._make_plan(3)
        assert len(plan.remaining_steps) == 3
        plan.advance()
        assert len(plan.remaining_steps) == 2

    def test_is_complete(self):
        plan = self._make_plan(2)
        assert not plan.is_complete
        plan.advance()
        plan.advance()
        assert plan.is_complete

    def test_advance(self):
        plan = self._make_plan(2)
        assert plan.current_step_index == 0
        plan.advance()
        assert plan.current_step_index == 1

    def test_to_dict(self):
        plan = self._make_plan(2)
        d = plan.to_dict()
        assert d["goal"] == "test goal"
        assert len(d["steps"]) == 2
        assert d["current_step_index"] == 0
        assert d["steps"][0]["step_id"] == 1

# ---------------------------------------------------------------------------
# PlanAndExecuteAutonomy
# ---------------------------------------------------------------------------

class MockPlanningProvider:
    def __init__(self, plan: Plan, should_replan: bool = False, replan_result: Plan | None = None):
        self._plan = plan
        self._should_replan = should_replan
        self._replan_result = replan_result

    async def create_plan(self, goal, available_skills, context):
        return self._plan

    async def should_replan(self, plan, step_result, context):
        return self._should_replan

    async def replan(self, original_goal, completed_steps, failed_step, available_skills, context):
        return self._replan_result or self._plan

class MockStepExecutor:
    def __init__(self, results: list[ExecutionResult] | None = None):
        self._results = results or []
        self._call_count = 0

    async def execute_step(self, step, skills, context):
        if self._call_count < len(self._results):
            result = self._results[self._call_count]
            self._call_count += 1
            return result
        return ExecutionResult(success=True, output="default result")

class TestPlanAndExecuteAutonomy:
    def _make_simple_plan(self) -> Plan:
        steps = [
            PlanStep(step_id=1, description="Step 1"),
            PlanStep(step_id=2, description="Step 2"),
        ]
        return Plan(goal="test goal", steps=steps)

    @pytest.mark.asyncio
    async def test_achieve_goal_success(self):
        plan = self._make_simple_plan()
        planner = MockPlanningProvider(plan)
        executor = MockStepExecutor(
            [
                ExecutionResult(success=True, output="result 1"),
                ExecutionResult(success=True, output="result 2"),
            ]
        )

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=executor,
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert result.success
        assert len(result.completed_steps) == 2

    @pytest.mark.asyncio
    async def test_achieve_goal_planning_failure(self):
        planner = MagicMock()
        planner.create_plan = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        executor = MockStepExecutor()

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=executor,
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert not result.success
        assert result.failed_step == "planning"

    @pytest.mark.asyncio
    async def test_achieve_goal_step_failure_no_replan(self):
        plan = Plan(goal="test", steps=[PlanStep(step_id=1, description="fail step")])
        planner = MockPlanningProvider(plan, should_replan=False)
        executor = MockStepExecutor(
            [
                ExecutionResult(success=False, reason="skill not found"),
            ]
        )

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=executor,
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert not result.success
        assert result.failed_step == "fail step"

    @pytest.mark.asyncio
    async def test_achieve_goal_step_failure_with_replan(self):
        plan = Plan(goal="test", steps=[PlanStep(step_id=1, description="will fail")])
        retry_plan = Plan(goal="test", steps=[PlanStep(step_id=2, description="retry step")])

        planner = MockPlanningProvider(plan, should_replan=True, replan_result=retry_plan)
        executor = MockStepExecutor(
            [
                ExecutionResult(success=False, reason="first attempt failed"),
                ExecutionResult(success=True, output="retry worked"),
            ]
        )

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=executor,
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert result.success

    @pytest.mark.asyncio
    async def test_achieve_goal_max_replans_exceeded(self):
        plan = Plan(goal="test", steps=[PlanStep(step_id=1, description="always fails")])
        planner = MockPlanningProvider(plan, should_replan=True)
        executor = MockStepExecutor(
            [
                ExecutionResult(success=False, reason="fail 1"),
                ExecutionResult(success=False, reason="fail 2"),
                ExecutionResult(success=False, reason="fail 3"),
                ExecutionResult(success=False, reason="fail 4"),
            ]
        )

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=executor,
            max_replans=2,
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert not result.success

    @pytest.mark.asyncio
    async def test_achieve_goal_leash_exceeded(self):
        """When leash is exceeded before step execution, abort."""
        from core.autonomous.leash import LeashConfig

        # 3 steps, leash at max_actions=1
        # Check is `state.actions_taken > max_actions` (strict >)
        # After step 1: actions_taken=1, check: 1 > 1 = False -> OK
        # After step 2: actions_taken=2, check: 2 > 1 = True -> exceeded at step 3
        steps = [PlanStep(step_id=i, description=f"Step {i}") for i in range(1, 4)]
        plan = Plan(goal="test", steps=steps)
        planner = MockPlanningProvider(plan)
        executor = MockStepExecutor(
            [
                ExecutionResult(success=True, output="r1"),
                ExecutionResult(success=True, output="r2"),
                ExecutionResult(success=True, output="r3"),
            ]
        )

        leash = LeashConfig(max_actions=1)
        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=executor,
            leash=leash,
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert not result.success
        assert len(result.completed_steps) == 2

    @pytest.mark.asyncio
    async def test_achieve_goal_step_exception_handled(self):
        plan = Plan(goal="test", steps=[PlanStep(step_id=1, description="throws")])
        planner = MockPlanningProvider(plan, should_replan=False)

        class FailingExecutor:
            async def execute_step(self, step, skills, context):
                raise RuntimeError("unexpected error")

        autonomy = PlanAndExecuteAutonomy(
            planning_provider=planner,
            step_executor=FailingExecutor(),
        )
        result = await autonomy.achieve_goal("do stuff", skills=[])
        assert not result.success

class TestPlanAndExecuteComplexity:
    def test_simple_goal_low_complexity(self):
        score = PlanAndExecuteAutonomy.estimate_complexity("list all users")
        assert score <= 3

    def test_complex_goal_high_complexity(self):
        score = PlanAndExecuteAutonomy.estimate_complexity(
            "first set up the database, and then configure the server, finally deploy to production"
        )
        assert score >= 4

    def test_should_use_planning_simple(self):
        autonomy = PlanAndExecuteAutonomy(
            planning_provider=MagicMock(),
            step_executor=MagicMock(),
        )
        assert not autonomy.should_use_planning("list users")

    def test_should_use_planning_complex(self):
        autonomy = PlanAndExecuteAutonomy(
            planning_provider=MagicMock(),
            step_executor=MagicMock(),
        )
        assert autonomy.should_use_planning(
            "first configure CI, and then set up monitoring, after that deploy"
        )

    def test_get_audit_trail(self):
        autonomy = PlanAndExecuteAutonomy(
            planning_provider=MagicMock(),
            step_executor=MagicMock(),
        )
        trail = autonomy.get_audit_trail()
        assert isinstance(trail, list)

# ---------------------------------------------------------------------------
# ProactiveScheduler
# ---------------------------------------------------------------------------

class TestProactiveScheduler:
    def _make_scheduler(self):
        from core.autonomous.scheduler import ProactiveScheduler

        scheduler = ProactiveScheduler(session_id="test_session")
        return scheduler

    @pytest.mark.asyncio
    async def test_schedule_heartbeat(self):
        scheduler = self._make_scheduler()
        scheduler.start()
        try:
            job_id = scheduler.schedule_heartbeat("health_check", interval_minutes=60)
            assert job_id.startswith("heartbeat_health_check_")
            jobs = scheduler.list_jobs()
            assert len(jobs) == 1
            assert jobs[0]["skill_name"] == "health_check"
            assert jobs[0]["trigger_type"] == "heartbeat"
        finally:
            scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_cron(self):
        scheduler = self._make_scheduler()
        scheduler.start()
        try:
            job_id = scheduler.schedule_cron("daily_report", "0 7 * * *")
            assert job_id.startswith("cron_daily_report_")
            job = scheduler.get_job(job_id)
            assert job is not None
            assert job["schedule"] == "0 7 * * *"
        finally:
            scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_oneshot(self):
        scheduler = self._make_scheduler()
        scheduler.start()
        try:
            run_at = datetime.now(UTC) + timedelta(hours=1)
            job_id = scheduler.schedule_oneshot("reminder", run_at, context={"msg": "hi"})
            assert job_id.startswith("oneshot_reminder_")
            job = scheduler.get_job(job_id)
            assert job is not None
            assert job["context"]["msg"] == "hi"
        finally:
            scheduler.stop()

    @pytest.mark.asyncio
    async def test_remove_job(self):
        scheduler = self._make_scheduler()
        scheduler.start()
        try:
            job_id = scheduler.schedule_heartbeat("check", interval_minutes=30)
            assert scheduler.remove_job(job_id) is True
            assert len(scheduler.list_jobs()) == 0
        finally:
            scheduler.stop()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_job(self):
        scheduler = self._make_scheduler()
        scheduler.start()
        try:
            assert scheduler.remove_job("nonexistent") is False
        finally:
            scheduler.stop()

    @pytest.mark.asyncio
    async def test_pause_and_resume_job(self):
        scheduler = self._make_scheduler()
        scheduler.start()
        try:
            job_id = scheduler.schedule_heartbeat("check", interval_minutes=30)
            assert scheduler.pause_job(job_id) is True
            job = scheduler.get_job(job_id)
            assert job["enabled"] is False

            assert scheduler.resume_job(job_id) is True
            job = scheduler.get_job(job_id)
            assert job["enabled"] is True
        finally:
            scheduler.stop()

    def test_get_job_nonexistent(self):
        scheduler = self._make_scheduler()
        assert scheduler.get_job("nope") is None

    @pytest.mark.asyncio
    async def test_is_running(self):
        scheduler = self._make_scheduler()
        assert not scheduler.is_running
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()
        assert not scheduler.is_running

    def test_set_executor(self):
        scheduler = self._make_scheduler()
        callback = AsyncMock()
        scheduler.set_executor(callback)
        assert scheduler._executor_callback is callback

    def test_list_jobs_empty(self):
        scheduler = self._make_scheduler()
        assert scheduler.list_jobs() == []

class TestSchedulerSingleton:
    def test_get_and_reset(self):
        from core.autonomous.scheduler import (
            get_proactive_scheduler,
            reset_proactive_scheduler,
        )

        s1 = get_proactive_scheduler()
        s2 = get_proactive_scheduler()
        assert s1 is s2

        reset_proactive_scheduler()
        s3 = get_proactive_scheduler()
        assert s3 is not s1
        reset_proactive_scheduler()
