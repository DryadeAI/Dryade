"""Tests for scheduler and planner coverage gaps.

Covers:
- core.autonomous.scheduler (ProactiveScheduler, ScheduledJob)
- core.autonomous.planner (PlanStep, Plan, PlanAndExecuteAutonomy)
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.utils.time import utcnow

# ---------------------------------------------------------------------------
# ScheduledJob tests
# ---------------------------------------------------------------------------

class TestScheduledJob:
    """Tests for ScheduledJob metadata class."""

    def test_creation_defaults(self):
        """ScheduledJob initializes with correct defaults."""
        from core.autonomous.scheduler import ScheduledJob

        job = ScheduledJob(
            job_id="test-1",
            skill_name="health-check",
            trigger_type="heartbeat",
            schedule="every 5 minutes",
            context={"server": "prod"},
        )
        assert job.job_id == "test-1"
        assert job.skill_name == "health-check"
        assert job.trigger_type == "heartbeat"
        assert job.schedule == "every 5 minutes"
        assert job.context == {"server": "prod"}
        assert job.enabled is True
        assert job.last_run is None
        assert job.run_count == 0
        assert job.last_error is None
        assert isinstance(job.created_at, datetime)

    def test_to_dict(self):
        """ScheduledJob.to_dict returns correct dictionary."""
        from core.autonomous.scheduler import ScheduledJob

        job = ScheduledJob(
            job_id="job-1",
            skill_name="sync",
            trigger_type="cron",
            schedule="0 7 * * *",
            context={},
        )
        d = job.to_dict()
        assert d["job_id"] == "job-1"
        assert d["skill_name"] == "sync"
        assert d["trigger_type"] == "cron"
        assert d["schedule"] == "0 7 * * *"
        assert d["enabled"] is True
        assert d["last_run"] is None
        assert d["run_count"] == 0
        assert d["last_error"] is None
        assert "created_at" in d

    def test_to_dict_with_last_run(self):
        """ScheduledJob.to_dict serializes last_run datetime."""
        from core.autonomous.scheduler import ScheduledJob

        job = ScheduledJob(
            job_id="job-2",
            skill_name="sync",
            trigger_type="heartbeat",
            schedule="every 10 minutes",
            context={},
        )
        now = utcnow()
        job.last_run = now
        job.run_count = 3
        job.last_error = "timeout"
        d = job.to_dict()
        assert d["last_run"] == now.isoformat()
        assert d["run_count"] == 3
        assert d["last_error"] == "timeout"

    def test_disabled_creation(self):
        """ScheduledJob can be created disabled."""
        from core.autonomous.scheduler import ScheduledJob

        job = ScheduledJob(
            job_id="job-3",
            skill_name="noop",
            trigger_type="oneshot",
            schedule="2025-01-01T00:00:00",
            context={},
            enabled=False,
        )
        assert job.enabled is False

# ---------------------------------------------------------------------------
# ProactiveScheduler tests
# ---------------------------------------------------------------------------

class TestProactiveScheduler:
    """Tests for ProactiveScheduler."""

    def test_creation_defaults(self):
        """ProactiveScheduler initializes with no callback."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        assert sched._executor_callback is None
        assert sched._started is False
        assert sched.is_running is False
        assert sched._jobs == {}

    def test_set_executor(self):
        """set_executor stores the callback."""
        from core.autonomous.scheduler import ProactiveScheduler

        cb = AsyncMock()
        sched = ProactiveScheduler()
        sched.set_executor(cb)
        assert sched._executor_callback is cb

    def test_start_stop(self):
        """Start and stop toggle _started flag."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "start"):
            sched.start()
        assert sched.is_running is True
        # Starting again is a no-op
        with patch.object(sched._scheduler, "start") as mock_start:
            sched.start()
            mock_start.assert_not_called()

        with patch.object(sched._scheduler, "shutdown"):
            sched.stop()
        assert sched.is_running is False
        # Stopping again is a no-op
        with patch.object(sched._scheduler, "shutdown") as mock_shutdown:
            sched.stop()
            mock_shutdown.assert_not_called()

    def test_schedule_heartbeat(self):
        """schedule_heartbeat creates a job and returns a job_id."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat(
                skill_name="health-check",
                interval_minutes=5,
                context={"server": "prod"},
            )
        assert job_id.startswith("heartbeat_health-check_")
        assert job_id in sched._jobs
        job = sched._jobs[job_id]
        assert job.trigger_type == "heartbeat"
        assert job.skill_name == "health-check"

    def test_schedule_cron(self):
        """schedule_cron creates a cron-triggered job."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_cron(
                skill_name="daily-briefing",
                cron_expression="0 7 * * *",
                context={"user": "john"},
            )
        assert job_id.startswith("cron_daily-briefing_")
        assert sched._jobs[job_id].trigger_type == "cron"
        assert sched._jobs[job_id].schedule == "0 7 * * *"

    def test_schedule_oneshot(self):
        """schedule_oneshot creates a one-time job."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        run_at = utcnow() + timedelta(hours=1)
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_oneshot(
                skill_name="reminder",
                run_at=run_at,
                context={"msg": "test"},
            )
        assert job_id.startswith("oneshot_reminder_")
        assert sched._jobs[job_id].trigger_type == "oneshot"

    def test_list_jobs(self):
        """list_jobs returns all job metadata dicts."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            sched.schedule_heartbeat("a", 10)
            sched.schedule_cron("b", "0 * * * *")
        jobs = sched.list_jobs()
        assert len(jobs) == 2
        assert all(isinstance(j, dict) for j in jobs)

    def test_get_job(self):
        """get_job returns metadata for existing job."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat("c", 15)
        result = sched.get_job(job_id)
        assert result is not None
        assert result["job_id"] == job_id

    def test_get_job_not_found(self):
        """get_job returns None for unknown job."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        assert sched.get_job("nonexistent") is None

    def test_remove_job(self):
        """remove_job deletes from scheduler and internal dict."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat("d", 5)
        with patch.object(sched._scheduler, "remove_job"):
            result = sched.remove_job(job_id)
        assert result is True
        assert job_id not in sched._jobs

    def test_remove_job_not_found(self):
        """remove_job returns False if job not found."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "remove_job", side_effect=Exception("not found")):
            result = sched.remove_job("nonexistent")
        assert result is False

    def test_pause_resume_job(self):
        """pause_job and resume_job toggle enabled flag."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat("e", 5)
        with patch.object(sched._scheduler, "pause_job"):
            assert sched.pause_job(job_id) is True
        assert sched._jobs[job_id].enabled is False
        with patch.object(sched._scheduler, "resume_job"):
            assert sched.resume_job(job_id) is True
        assert sched._jobs[job_id].enabled is True

    def test_pause_job_not_found(self):
        """pause_job returns False for unknown job."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "pause_job", side_effect=Exception):
            assert sched.pause_job("nope") is False

    def test_resume_job_not_found(self):
        """resume_job returns False for unknown job."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "resume_job", side_effect=Exception):
            assert sched.resume_job("nope") is False

    @pytest.mark.asyncio
    async def test_execute_scheduled_success(self):
        """_execute_scheduled updates metadata on success."""
        from core.autonomous.scheduler import ProactiveScheduler

        callback = AsyncMock()
        sched = ProactiveScheduler(executor_callback=callback)
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat("f", 5)
        await sched._execute_scheduled(
            skill_name="f", context={}, trigger_type="heartbeat", job_id=job_id
        )
        callback.assert_awaited_once_with("f", {}, "heartbeat")
        assert sched._jobs[job_id].run_count == 1
        assert sched._jobs[job_id].last_run is not None
        assert sched._jobs[job_id].last_error is None

    @pytest.mark.asyncio
    async def test_execute_scheduled_failure(self):
        """_execute_scheduled records error on failure."""
        from core.autonomous.scheduler import ProactiveScheduler

        callback = AsyncMock(side_effect=RuntimeError("boom"))
        sched = ProactiveScheduler(executor_callback=callback)
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat("g", 5)
        await sched._execute_scheduled(
            skill_name="g", context={}, trigger_type="heartbeat", job_id=job_id
        )
        assert sched._jobs[job_id].last_error == "boom"

    @pytest.mark.asyncio
    async def test_execute_scheduled_no_callback(self):
        """_execute_scheduled warns when no callback set."""
        from core.autonomous.scheduler import ProactiveScheduler

        sched = ProactiveScheduler()
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_heartbeat("h", 5)
        # Should not raise
        await sched._execute_scheduled(
            skill_name="h", context={}, trigger_type="heartbeat", job_id=job_id
        )

    @pytest.mark.asyncio
    async def test_execute_scheduled_oneshot_removes_job(self):
        """_execute_scheduled removes oneshot jobs after execution."""
        from core.autonomous.scheduler import ProactiveScheduler

        callback = AsyncMock()
        sched = ProactiveScheduler(executor_callback=callback)
        run_at = utcnow() + timedelta(hours=1)
        with patch.object(sched._scheduler, "add_job"):
            job_id = sched.schedule_oneshot("oneshot-test", run_at)
        with patch.object(sched._scheduler, "remove_job"):
            await sched._execute_scheduled(
                skill_name="oneshot-test", context={}, trigger_type="oneshot", job_id=job_id
            )
        assert job_id not in sched._jobs

# ---------------------------------------------------------------------------
# Singleton helpers tests
# ---------------------------------------------------------------------------

class TestSchedulerSingleton:
    """Tests for singleton functions."""

    def test_get_proactive_scheduler(self):
        """get_proactive_scheduler returns a ProactiveScheduler."""
        from core.autonomous.scheduler import (
            ProactiveScheduler,
            get_proactive_scheduler,
            reset_proactive_scheduler,
        )

        reset_proactive_scheduler()
        sched = get_proactive_scheduler()
        assert isinstance(sched, ProactiveScheduler)
        # Second call returns same instance
        assert get_proactive_scheduler() is sched
        reset_proactive_scheduler()

    def test_reset_proactive_scheduler(self):
        """reset_proactive_scheduler clears singleton."""
        from core.autonomous.scheduler import (
            get_proactive_scheduler,
            reset_proactive_scheduler,
        )

        s1 = get_proactive_scheduler()
        reset_proactive_scheduler()
        s2 = get_proactive_scheduler()
        assert s1 is not s2
        reset_proactive_scheduler()

# ---------------------------------------------------------------------------
# PlanStep / Plan tests (core.autonomous.planner)
# ---------------------------------------------------------------------------

class TestPlanStep:
    """Tests for PlanStep."""

    def test_creation_defaults(self):
        """PlanStep initializes with correct defaults."""
        from core.autonomous.planner import PlanStep

        step = PlanStep(step_id=1, description="Do something")
        assert step.step_id == 1
        assert step.description == "Do something"
        assert step.skill_hint is None
        assert step.inputs_hint == {}
        assert step.depends_on == []

    def test_creation_all_fields(self):
        """PlanStep with all fields."""
        from core.autonomous.planner import PlanStep

        step = PlanStep(
            step_id=2,
            description="Analyze data",
            skill_hint="analyzer",
            inputs_hint={"file": "data.csv"},
            depends_on=[1],
        )
        assert step.skill_hint == "analyzer"
        assert step.inputs_hint == {"file": "data.csv"}
        assert step.depends_on == [1]

    def test_repr(self):
        """PlanStep repr is readable."""
        from core.autonomous.planner import PlanStep

        step = PlanStep(step_id=1, description="Short task")
        assert "PlanStep(1:" in repr(step)

class TestPlan:
    """Tests for Plan."""

    def test_creation(self):
        """Plan initializes correctly."""
        from core.autonomous.planner import Plan, PlanStep

        steps = [
            PlanStep(step_id=1, description="Step 1"),
            PlanStep(step_id=2, description="Step 2", depends_on=[1]),
        ]
        plan = Plan(goal="Test goal", steps=steps)
        assert plan.goal == "Test goal"
        assert len(plan.steps) == 2
        assert plan.current_step_index == 0

    def test_current_step(self):
        """current_step returns the step at current index."""
        from core.autonomous.planner import Plan, PlanStep

        steps = [PlanStep(step_id=1, description="A"), PlanStep(step_id=2, description="B")]
        plan = Plan(goal="g", steps=steps)
        assert plan.current_step.step_id == 1

    def test_current_step_exhausted(self):
        """current_step returns None when all steps done."""
        from core.autonomous.planner import Plan, PlanStep

        plan = Plan(goal="g", steps=[PlanStep(step_id=1, description="A")])
        plan.current_step_index = 1
        assert plan.current_step is None

    def test_remaining_steps(self):
        """remaining_steps returns unexecuted steps."""
        from core.autonomous.planner import Plan, PlanStep

        steps = [PlanStep(step_id=i, description=f"S{i}") for i in range(3)]
        plan = Plan(goal="g", steps=steps)
        plan.advance()
        assert len(plan.remaining_steps) == 2

    def test_is_complete(self):
        """is_complete returns True when all steps executed."""
        from core.autonomous.planner import Plan, PlanStep

        plan = Plan(goal="g", steps=[PlanStep(step_id=1, description="A")])
        assert not plan.is_complete
        plan.advance()
        assert plan.is_complete

    def test_advance(self):
        """advance increments current_step_index."""
        from core.autonomous.planner import Plan, PlanStep

        plan = Plan(goal="g", steps=[PlanStep(step_id=1, description="A")])
        assert plan.current_step_index == 0
        plan.advance()
        assert plan.current_step_index == 1

    def test_to_dict(self):
        """to_dict returns serializable representation."""
        from core.autonomous.planner import Plan, PlanStep

        steps = [
            PlanStep(step_id=1, description="S1", skill_hint="a", depends_on=[]),
        ]
        plan = Plan(goal="g", steps=steps)
        d = plan.to_dict()
        assert d["goal"] == "g"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["step_id"] == 1
        assert d["current_step_index"] == 0

# ---------------------------------------------------------------------------
# PlanAndExecuteAutonomy tests
# ---------------------------------------------------------------------------

class TestPlanAndExecuteAutonomy:
    """Tests for PlanAndExecuteAutonomy."""

    def test_estimate_complexity_simple(self):
        """Simple goal gets low complexity."""
        from core.autonomous.planner import PlanAndExecuteAutonomy

        c = PlanAndExecuteAutonomy.estimate_complexity("Check server status")
        assert c >= 1

    def test_estimate_complexity_complex(self):
        """Complex goal with indicators gets higher complexity."""
        from core.autonomous.planner import PlanAndExecuteAutonomy

        c = PlanAndExecuteAutonomy.estimate_complexity(
            "First set up CI, and then configure deploy, after that migrate data"
        )
        assert c >= 4  # "first", "and then", "after that", "set up", "configure", "migrate"

    def test_should_use_planning(self):
        """should_use_planning returns True for complex goals."""
        from core.autonomous.planner import PlanAndExecuteAutonomy

        provider = MagicMock()
        executor = MagicMock()
        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        assert not pae.should_use_planning("Check status")
        assert pae.should_use_planning(
            "First set up CI, and then configure deploy, after that migrate data, finally verify"
        )

    @pytest.mark.asyncio
    async def test_achieve_goal_planning_failure(self):
        """achieve_goal returns failure when planning fails."""
        from core.autonomous.planner import PlanAndExecuteAutonomy

        provider = MagicMock()
        provider.create_plan = AsyncMock(side_effect=RuntimeError("LLM down"))
        executor = MagicMock()
        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        result = await pae.achieve_goal("Do something", skills=[])
        assert result.success is False
        assert result.failed_step == "planning"

    @pytest.mark.asyncio
    async def test_achieve_goal_success(self):
        """achieve_goal completes all steps successfully."""
        from core.autonomous.models import ExecutionResult
        from core.autonomous.planner import Plan, PlanAndExecuteAutonomy, PlanStep

        steps = [PlanStep(step_id=1, description="S1")]
        plan = Plan(goal="g", steps=steps)

        provider = MagicMock()
        provider.create_plan = AsyncMock(return_value=plan)

        step_result = ExecutionResult(success=True, output="done")
        executor = MagicMock()
        executor.execute_step = AsyncMock(return_value=step_result)

        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        result = await pae.achieve_goal("g", skills=[])
        assert result.success is True
        assert len(result.completed_steps) == 1

    @pytest.mark.asyncio
    async def test_achieve_goal_step_failure_replan(self):
        """achieve_goal replans on step failure."""
        from core.autonomous.models import ExecutionResult
        from core.autonomous.planner import Plan, PlanAndExecuteAutonomy, PlanStep

        step1 = PlanStep(step_id=1, description="S1")
        step2 = PlanStep(step_id=1, description="S1-retry")
        plan_v1 = Plan(goal="g", steps=[step1])
        plan_v2 = Plan(goal="g", steps=[step2])

        failure = ExecutionResult(success=False, reason="failed")
        success = ExecutionResult(success=True, output="ok")

        provider = MagicMock()
        provider.create_plan = AsyncMock(return_value=plan_v1)
        provider.should_replan = AsyncMock(return_value=True)
        provider.replan = AsyncMock(return_value=plan_v2)

        executor = MagicMock()
        executor.execute_step = AsyncMock(side_effect=[failure, success])

        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        result = await pae.achieve_goal("g", skills=[])
        assert result.success is True
        provider.should_replan.assert_awaited_once()
        provider.replan.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_achieve_goal_max_replans_exceeded(self):
        """achieve_goal fails when max replans exceeded."""
        from core.autonomous.models import ExecutionResult
        from core.autonomous.planner import Plan, PlanAndExecuteAutonomy, PlanStep

        step = PlanStep(step_id=1, description="S1")

        def make_plan():
            return Plan(goal="g", steps=[PlanStep(step_id=1, description="retry")])

        provider = MagicMock()
        provider.create_plan = AsyncMock(return_value=Plan(goal="g", steps=[step]))
        provider.should_replan = AsyncMock(return_value=True)
        provider.replan = AsyncMock(side_effect=lambda **kw: make_plan())

        failure = ExecutionResult(success=False, reason="always fails")
        executor = MagicMock()
        executor.execute_step = AsyncMock(return_value=failure)

        pae = PlanAndExecuteAutonomy(
            planning_provider=provider, step_executor=executor, max_replans=2
        )
        result = await pae.achieve_goal("g", skills=[])
        assert result.success is False

    @pytest.mark.asyncio
    async def test_achieve_goal_no_replan(self):
        """achieve_goal fails when should_replan returns False."""
        from core.autonomous.models import ExecutionResult
        from core.autonomous.planner import Plan, PlanAndExecuteAutonomy, PlanStep

        step = PlanStep(step_id=1, description="S1")
        plan = Plan(goal="g", steps=[step])

        provider = MagicMock()
        provider.create_plan = AsyncMock(return_value=plan)
        provider.should_replan = AsyncMock(return_value=False)

        failure = ExecutionResult(success=False, reason="failed")
        executor = MagicMock()
        executor.execute_step = AsyncMock(return_value=failure)

        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        result = await pae.achieve_goal("g", skills=[])
        assert result.success is False
        assert result.failed_step == "S1"

    @pytest.mark.asyncio
    async def test_achieve_goal_replan_failure(self):
        """achieve_goal fails when replanning throws exception."""
        from core.autonomous.models import ExecutionResult
        from core.autonomous.planner import Plan, PlanAndExecuteAutonomy, PlanStep

        step = PlanStep(step_id=1, description="S1")
        plan = Plan(goal="g", steps=[step])

        provider = MagicMock()
        provider.create_plan = AsyncMock(return_value=plan)
        provider.should_replan = AsyncMock(side_effect=RuntimeError("LLM error"))

        failure = ExecutionResult(success=False, reason="failed")
        executor = MagicMock()
        executor.execute_step = AsyncMock(return_value=failure)

        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        result = await pae.achieve_goal("g", skills=[])
        assert result.success is False

    @pytest.mark.asyncio
    async def test_achieve_goal_step_exception(self):
        """achieve_goal handles step execution exception."""
        from core.autonomous.planner import Plan, PlanAndExecuteAutonomy, PlanStep

        step = PlanStep(step_id=1, description="S1")
        plan = Plan(goal="g", steps=[step])

        provider = MagicMock()
        provider.create_plan = AsyncMock(return_value=plan)
        provider.should_replan = AsyncMock(return_value=False)

        executor = MagicMock()
        executor.execute_step = AsyncMock(side_effect=RuntimeError("crash"))

        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        result = await pae.achieve_goal("g", skills=[])
        assert result.success is False

    def test_get_audit_trail(self):
        """get_audit_trail returns JSON audit entries."""
        from core.autonomous.planner import PlanAndExecuteAutonomy

        provider = MagicMock()
        executor = MagicMock()
        pae = PlanAndExecuteAutonomy(planning_provider=provider, step_executor=executor)
        trail = pae.get_audit_trail()
        assert isinstance(trail, list)
