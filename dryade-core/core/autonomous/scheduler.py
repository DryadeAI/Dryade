"""Proactive scheduler for skill execution.

MoltBot's key innovation: Proactive behavior - agents initiate actions.
This scheduler enables:
- Heartbeat: Periodic skill execution (every N minutes)
- Cron: Time-based scheduling (daily at 7am)
- One-shot: Delayed single execution

All scheduled executions flow through autonomous executor with audit.
"""

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any
from uuid import uuid4

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.autonomous.audit import AuditLogger
from core.utils.time import utcnow

logger = logging.getLogger(__name__)

# Type alias for executor callback
ExecutorCallback = Callable[
    [str, dict[str, Any], str],  # skill_name, context, trigger_type
    Coroutine[Any, Any, Any],  # returns coroutine
]

class ScheduledJob:
    """Metadata for a scheduled job."""

    def __init__(
        self,
        job_id: str,
        skill_name: str,
        trigger_type: str,
        schedule: str,
        context: dict[str, Any],
        enabled: bool = True,
    ):
        """Initialize scheduled job metadata.

        Args:
            job_id: Unique job identifier
            skill_name: Name of skill to execute
            trigger_type: Type of trigger (heartbeat, cron, oneshot)
            schedule: Schedule description (interval or cron expression)
            context: Execution context passed to skill
            enabled: Whether job is enabled
        """
        self.job_id = job_id
        self.skill_name = skill_name
        self.trigger_type = trigger_type  # "heartbeat", "cron", "oneshot"
        self.schedule = schedule  # interval or cron expression
        self.context = context
        self.enabled = enabled
        self.created_at = utcnow()
        self.last_run: datetime | None = None
        self.run_count = 0
        self.last_error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "job_id": self.job_id,
            "skill_name": self.skill_name,
            "trigger_type": self.trigger_type,
            "schedule": self.schedule,
            "context": self.context,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "last_error": self.last_error,
        }

class ProactiveScheduler:
    """Schedule proactive skill executions.

    Supports three scheduling patterns:

    1. Heartbeat (interval):
       - Run skill every N minutes/hours
       - Use for: health checks, monitoring, periodic sync

    2. Cron (time-based):
       - Run skill at specific times
       - Use for: daily briefings, weekly reports, scheduled tasks

    3. One-shot (delayed):
       - Run skill once at future time
       - Use for: reminders, delayed actions

    Example:
        scheduler = ProactiveScheduler(executor_callback=my_executor.execute)
        scheduler.start()

        # Heartbeat: Check server every 4 hours
        scheduler.schedule_heartbeat(
            skill_name="server-health-check",
            interval_minutes=240,
            context={"server": "prod-01"}
        )

        # Cron: Daily briefing at 7am
        scheduler.schedule_cron(
            skill_name="daily-briefing",
            cron_expression="0 7 * * *",
            context={"user": "john"}
        )
    """

    def __init__(
        self,
        executor_callback: ExecutorCallback | None = None,
        session_id: str | None = None,
    ):
        """Initialize proactive scheduler.

        Args:
            executor_callback: Async function to execute skills
            session_id: Session ID for audit logging
        """
        self._executor_callback = executor_callback
        self._jobs: dict[str, ScheduledJob] = {}
        self._audit = AuditLogger(session_id=session_id or str(uuid4()), initiator_id="scheduler")

        # Configure APScheduler — use SQLAlchemyJobStore for persistence with
        # MemoryJobStore fallback if the DB engine is unavailable (e.g. tests).
        jobstores = self._build_jobstores()
        executors = {"default": AsyncIOExecutor()}

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults={
                "coalesce": True,  # Merge missed runs
                "max_instances": 1,  # One instance per job
                "misfire_grace_time": 60,  # 1 minute grace for missed jobs
            },
        )

        self._started = False
        self._lock = threading.Lock()

    @staticmethod
    def _build_jobstores() -> dict:
        """Build jobstore config, preferring SQLAlchemy persistence.

        Falls back to MemoryJobStore if the database engine is unavailable
        (e.g. during unit tests without a running database).
        """
        try:
            from core.database.session import get_engine

            engine = get_engine()
            return {"default": SQLAlchemyJobStore(engine=engine)}
        except Exception:
            logger.info("[Scheduler] SQLAlchemyJobStore unavailable, using MemoryJobStore")
            return {"default": MemoryJobStore()}

    def set_executor(self, executor_callback: ExecutorCallback) -> None:
        """Set or update executor callback.

        Args:
            executor_callback: Async function to execute skills
        """
        self._executor_callback = executor_callback

    def start(self) -> None:
        """Start the scheduler."""
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("[Scheduler] Started proactive scheduler")

    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler.

        Args:
            wait: Wait for running jobs to complete
        """
        if self._started:
            self._scheduler.shutdown(wait=wait)
            self._started = False
            logger.info("[Scheduler] Stopped proactive scheduler")

    def schedule_heartbeat(
        self,
        skill_name: str,
        interval_minutes: int,
        context: dict[str, Any] | None = None,
        start_immediately: bool = False,
    ) -> str:
        """Schedule heartbeat (interval-based) skill execution.

        Args:
            skill_name: Name of skill to execute
            interval_minutes: Minutes between executions
            context: Execution context
            start_immediately: Run immediately on schedule

        Returns:
            Job ID for management
        """
        context = context or {}
        job_id = f"heartbeat_{skill_name}_{uuid4().hex[:8]}"

        # Create trigger
        trigger = IntervalTrigger(minutes=interval_minutes)

        # Add to APScheduler
        self._scheduler.add_job(
            self._execute_scheduled,
            trigger=trigger,
            id=job_id,
            kwargs={
                "skill_name": skill_name,
                "context": context,
                "trigger_type": "heartbeat",
                "job_id": job_id,
            },
            replace_existing=True,
        )

        # Track job metadata
        job = ScheduledJob(
            job_id=job_id,
            skill_name=skill_name,
            trigger_type="heartbeat",
            schedule=f"every {interval_minutes} minutes",
            context=context,
        )
        with self._lock:
            self._jobs[job_id] = job

        logger.info(f"[Scheduler] Scheduled heartbeat: {skill_name} every {interval_minutes}m")

        # Optionally run immediately
        if start_immediately and self._executor_callback:
            asyncio.create_task(
                self._execute_scheduled(
                    skill_name=skill_name,
                    context=context,
                    trigger_type="heartbeat",
                    job_id=job_id,
                )
            )

        return job_id

    def schedule_cron(
        self,
        skill_name: str,
        cron_expression: str,
        context: dict[str, Any] | None = None,
        timezone: str = "UTC",
    ) -> str:
        """Schedule cron-based skill execution.

        Args:
            skill_name: Name of skill to execute
            cron_expression: Standard cron expression (e.g., "0 7 * * *")
            context: Execution context
            timezone: Timezone for cron schedule

        Returns:
            Job ID for management
        """
        context = context or {}
        job_id = f"cron_{skill_name}_{uuid4().hex[:8]}"

        # Create trigger from cron expression
        trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone)

        # Add to APScheduler
        self._scheduler.add_job(
            self._execute_scheduled,
            trigger=trigger,
            id=job_id,
            kwargs={
                "skill_name": skill_name,
                "context": context,
                "trigger_type": "cron",
                "job_id": job_id,
            },
            replace_existing=True,
        )

        # Track job metadata
        job = ScheduledJob(
            job_id=job_id,
            skill_name=skill_name,
            trigger_type="cron",
            schedule=cron_expression,
            context=context,
        )
        with self._lock:
            self._jobs[job_id] = job

        logger.info(f"[Scheduler] Scheduled cron: {skill_name} at '{cron_expression}'")

        return job_id

    def schedule_oneshot(
        self,
        skill_name: str,
        run_at: datetime,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Schedule one-time skill execution.

        Args:
            skill_name: Name of skill to execute
            run_at: When to execute
            context: Execution context

        Returns:
            Job ID for management
        """
        context = context or {}
        job_id = f"oneshot_{skill_name}_{uuid4().hex[:8]}"

        # Create trigger for specific time
        trigger = DateTrigger(run_date=run_at)

        # Add to APScheduler
        self._scheduler.add_job(
            self._execute_scheduled,
            trigger=trigger,
            id=job_id,
            kwargs={
                "skill_name": skill_name,
                "context": context,
                "trigger_type": "oneshot",
                "job_id": job_id,
            },
            replace_existing=True,
        )

        # Track job metadata
        job = ScheduledJob(
            job_id=job_id,
            skill_name=skill_name,
            trigger_type="oneshot",
            schedule=run_at.isoformat(),
            context=context,
        )
        with self._lock:
            self._jobs[job_id] = job

        logger.info(f"[Scheduler] Scheduled oneshot: {skill_name} at {run_at}")

        return job_id

    async def _execute_scheduled(
        self,
        skill_name: str,
        context: dict[str, Any],
        trigger_type: str,
        job_id: str,
    ) -> None:
        """Execute scheduled skill with full audit.

        Internal method called by APScheduler.
        """
        logger.info(f"[Scheduler] Executing {trigger_type} job: {skill_name}")

        # Update job metadata
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].last_run = utcnow()
                self._jobs[job_id].run_count += 1

        # Log proactive trigger
        self._audit._create_entry(
            action_type="skill_exec",
            initiator_type="scheduler",
            skill_name=skill_name,
            inputs=context,
            action_details={"trigger_type": trigger_type, "job_id": job_id},
        )

        # Execute via callback
        if self._executor_callback:
            try:
                await self._executor_callback(skill_name, context, trigger_type)

                with self._lock:
                    if job_id in self._jobs:
                        self._jobs[job_id].last_error = None

            except Exception as e:
                logger.error(f"[Scheduler] Job {job_id} failed: {e}")
                with self._lock:
                    if job_id in self._jobs:
                        self._jobs[job_id].last_error = str(e)

                # Log error
                self._audit._create_entry(
                    action_type="skill_exec",
                    initiator_type="scheduler",
                    skill_name=skill_name,
                    success=False,
                    error=str(e),
                )
        else:
            logger.warning(f"[Scheduler] No executor callback set for job {job_id}")

        # Remove oneshot jobs after execution
        if trigger_type == "oneshot":
            self.remove_job(job_id)

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job.

        Args:
            job_id: Job to remove

        Returns:
            True if removed, False if not found
        """
        try:
            self._scheduler.remove_job(job_id)
            with self._lock:
                if job_id in self._jobs:
                    del self._jobs[job_id]
            logger.info(f"[Scheduler] Removed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"[Scheduler] Failed to remove job {job_id}: {e}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job.

        Args:
            job_id: Job to pause

        Returns:
            True if paused, False if not found
        """
        try:
            self._scheduler.pause_job(job_id)
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id].enabled = False
            return True
        except Exception:
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.

        Args:
            job_id: Job to resume

        Returns:
            True if resumed, False if not found
        """
        try:
            self._scheduler.resume_job(job_id)
            with self._lock:
                if job_id in self._jobs:
                    self._jobs[job_id].enabled = True
            return True
        except Exception:
            return False

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs.

        Returns:
            List of job metadata dicts
        """
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def get_job(self, job_id: str) -> dict | None:
        """Get job metadata.

        Args:
            job_id: Job to get

        Returns:
            Job metadata or None
        """
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def add_job(self, func, trigger, job_id: str, **kwargs) -> None:
        """Add a job to the underlying APScheduler.

        Thin wrapper exposing APScheduler.add_job for LoopService.

        Args:
            func: Callable to execute.
            trigger: APScheduler trigger (CronTrigger, IntervalTrigger, DateTrigger).
            job_id: Unique job identifier.
            **kwargs: Additional APScheduler add_job kwargs.
        """
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            **kwargs,
        )

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._started

# Singleton scheduler instance
_scheduler: ProactiveScheduler | None = None
_scheduler_lock = threading.Lock()

def get_proactive_scheduler() -> ProactiveScheduler:
    """Get or create global proactive scheduler.

    Returns:
        Singleton ProactiveScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = ProactiveScheduler()
    return _scheduler

def reset_proactive_scheduler() -> None:
    """Reset global scheduler (for testing)."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.is_running:
            _scheduler.stop()
        _scheduler = None
