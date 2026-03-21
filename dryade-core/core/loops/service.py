"""Loop Engine Service — schedule and execute workflows, agents, skills, and tasks.

Orchestrates creation, persistence, dispatch, and lifecycle management of
scheduled loops. All loop state lives in the database; APScheduler handles
the timing and fires callbacks that delegate to the correct executor.
"""

import asyncio
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.database.session import get_session
from core.loops.models import (
    ExecutionStatus,
    LoopExecution,
    ScheduledLoop,
    TargetType,
    TriggerType,
)

logger = logging.getLogger("dryade.loops.service")

# Regex for parsing interval strings like "30m", "4h", "1d"
_INTERVAL_RE = re.compile(r"^(\d+)\s*(s|m|h|d)$", re.IGNORECASE)

_INTERVAL_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}

class LoopService:
    """Core orchestration service for the Loop Engine.

    Manages loop CRUD, APScheduler registration, and universal target dispatch.
    Does NOT import from plugins — plugins extend behavior by hooking into
    the execution lifecycle.
    """

    def __init__(self, scheduler, db_session_factory=None):
        """Initialize LoopService.

        Args:
            scheduler: ProactiveScheduler instance (provides APScheduler access).
            db_session_factory: Optional session factory override (for tests).
        """
        self._scheduler = scheduler
        self._db_session_factory = db_session_factory

    # =========================================================================
    # CRUD
    # =========================================================================

    def create_loop(self, loop_data: dict[str, Any], user_id: str | None = None) -> ScheduledLoop:
        """Create a new scheduled loop in DB and register with APScheduler.

        Args:
            loop_data: Dict with name, target_type, target_id, trigger_type,
                       schedule, timezone, config, enabled.
            user_id: Creator user ID (optional for system-created loops).

        Returns:
            Created ScheduledLoop instance.
        """
        loop = ScheduledLoop(
            id=str(uuid.uuid4()),
            name=loop_data["name"],
            target_type=TargetType(loop_data["target_type"]),
            target_id=loop_data["target_id"],
            trigger_type=TriggerType(loop_data["trigger_type"]),
            schedule=loop_data["schedule"],
            timezone=loop_data.get("timezone", "UTC"),
            enabled=loop_data.get("enabled", True),
            config=loop_data.get("config"),
            created_by=user_id,
        )

        # Validate trigger BEFORE persisting — fail fast on bad schedule format
        should_register = loop.enabled
        if should_register:
            self._build_trigger(loop)

        with get_session() as db:
            db.add(loop)
            db.flush()
            # Expunge so the ORM instance survives after session close
            db.expunge(loop)

        logger.info(
            "[LoopService] Created loop",
            extra={"loop_id": loop.id, "loop_name": loop.name},
        )

        # Register with APScheduler if enabled (trigger already validated)
        if should_register:
            self._register_with_scheduler(loop)

        return loop

    def get_loop(self, loop_id: str) -> ScheduledLoop | None:
        """Get a loop by ID."""
        with get_session() as db:
            loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
            if loop:
                db.expunge(loop)
            return loop

    def list_loops(
        self,
        target_type: str | None = None,
        enabled: bool | None = None,
    ) -> list[ScheduledLoop]:
        """List loops with optional filtering."""
        with get_session() as db:
            query = db.query(ScheduledLoop)
            if target_type is not None:
                query = query.filter(ScheduledLoop.target_type == target_type)
            if enabled is not None:
                query = query.filter(ScheduledLoop.enabled == enabled)
            loops = query.all()
            for loop in loops:
                db.expunge(loop)
            return loops

    def delete_loop(self, loop_id: str) -> bool:
        """Remove loop from DB and APScheduler.

        Returns:
            True if deleted, False if not found.
        """
        with get_session() as db:
            loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
            if not loop:
                return False
            db.delete(loop)

        # Remove from APScheduler (ignore if not registered)
        self._unregister_from_scheduler(loop_id)
        logger.info("[LoopService] Deleted loop", extra={"loop_id": loop_id})
        return True

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def pause_loop(self, loop_id: str) -> ScheduledLoop | None:
        """Pause a loop — set enabled=false and remove from APScheduler."""
        with get_session() as db:
            loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
            if not loop:
                return None
            loop.enabled = False
            db.flush()
            db.expunge(loop)

        self._unregister_from_scheduler(loop_id)
        logger.info("[LoopService] Paused loop", extra={"loop_id": loop_id})
        return loop

    def resume_loop(self, loop_id: str) -> ScheduledLoop | None:
        """Resume a paused loop — set enabled=true and re-register."""
        with get_session() as db:
            loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
            if not loop:
                return None
            loop.enabled = True
            db.flush()
            db.expunge(loop)

        self._register_with_scheduler(loop)
        logger.info("[LoopService] Resumed loop", extra={"loop_id": loop_id})
        return loop

    # =========================================================================
    # Execution
    # =========================================================================

    async def execute_loop(
        self,
        loop: ScheduledLoop,
        trigger_source: str = "schedule",
    ) -> LoopExecution:
        """Execute a loop — universal target dispatch.

        Routes to the correct executor based on target_type:
        - workflow  -> TriggerHandler.trigger() with TriggerSource.SCHEDULE
        - agent     -> Agent lookup + execute
        - skill     -> Skill executor callback
        - orchestrator_task -> DryadeOrchestrator.orchestrate()

        Args:
            loop: ScheduledLoop to execute.
            trigger_source: "schedule", "manual", or "api".

        Returns:
            LoopExecution record with result/error.
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        # Create execution record
        with get_session() as db:
            execution = LoopExecution(
                id=execution_id,
                loop_id=loop.id,
                status=ExecutionStatus.RUNNING,
                started_at=started_at,
                trigger_source=trigger_source,
            )
            db.add(execution)
            db.flush()
            db.expunge(execution)

        logger.info(
            "[LoopService] Executing loop",
            extra={
                "loop_id": loop.id,
                "target_type": loop.target_type.value
                if isinstance(loop.target_type, TargetType)
                else loop.target_type,
                "trigger_source": trigger_source,
                "execution_id": execution_id,
            },
        )

        result = None
        error = None
        start_ns = time.monotonic_ns()

        try:
            result = await self._dispatch(loop)
        except Exception as e:
            error = str(e)
            logger.error(
                "[LoopService] Loop execution failed",
                extra={"loop_id": loop.id, "execution_id": execution_id, "error": error},
            )

        duration_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
        completed_at = datetime.now(UTC)

        # Update execution record and return a fresh, detached instance
        with get_session() as db:
            exec_record = db.query(LoopExecution).filter(LoopExecution.id == execution_id).first()
            if exec_record:
                exec_record.status = ExecutionStatus.FAILED if error else ExecutionStatus.COMPLETED
                exec_record.completed_at = completed_at
                exec_record.duration_ms = duration_ms
                exec_record.result = (
                    result
                    if isinstance(result, (dict, list))
                    else {"output": str(result)}
                    if result
                    else None
                )
                exec_record.error = error
                db.flush()
                db.expunge(exec_record)
                execution = exec_record

        # Update loop last_run_at
        with get_session() as db:
            loop_record = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop.id).first()
            if loop_record:
                loop_record.last_run_at = completed_at

        return execution

    async def trigger_manual(self, loop_id: str) -> LoopExecution | None:
        """Manually trigger a loop execution.

        Args:
            loop_id: Loop to trigger.

        Returns:
            LoopExecution or None if loop not found.
        """
        with get_session() as db:
            loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
            if not loop:
                return None
            # Detach from session for use in async dispatch
            db.expunge(loop)

        return await self.execute_loop(loop, trigger_source="manual")

    # =========================================================================
    # Startup Recovery
    # =========================================================================

    async def startup_recovery(self) -> int:
        """Load all enabled loops from DB and register with APScheduler.

        Called on application startup to restore scheduled jobs after restart.

        Returns:
            Number of loops recovered.
        """
        with get_session() as db:
            loops = db.query(ScheduledLoop).filter(ScheduledLoop.enabled.is_(True)).all()
            # Detach all from session
            for loop in loops:
                db.expunge(loop)

        recovered = 0
        for loop in loops:
            try:
                self._register_with_scheduler(loop)
                recovered += 1
            except Exception as e:
                logger.error(
                    "[LoopService] Failed to recover loop",
                    extra={"loop_id": loop.id, "loop_name": loop.name, "error": str(e)},
                )

        logger.info(
            "[LoopService] Startup recovery complete",
            extra={"recovered": recovered, "total_enabled": len(loops)},
        )
        return recovered

    # =========================================================================
    # Internal — Scheduler Registration
    # =========================================================================

    def _register_with_scheduler(self, loop: ScheduledLoop) -> None:
        """Register a loop job with APScheduler based on trigger_type."""
        trigger = self._build_trigger(loop)
        job_id = f"loop_{loop.id}"

        self._scheduler.add_job(
            func=self._scheduler_callback,
            trigger=trigger,
            job_id=job_id,
            kwargs={"loop_id": loop.id},
        )
        logger.debug(
            "[LoopService] Registered with scheduler",
            extra={"loop_id": loop.id, "job_id": job_id},
        )

    def _unregister_from_scheduler(self, loop_id: str) -> None:
        """Remove a loop job from APScheduler."""
        job_id = f"loop_{loop_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass  # Job may not exist in scheduler

    @staticmethod
    def _build_trigger(loop: ScheduledLoop):
        """Build an APScheduler trigger from a ScheduledLoop."""
        trigger_type = loop.trigger_type
        if isinstance(trigger_type, TriggerType):
            trigger_type = trigger_type.value

        if trigger_type == TriggerType.CRON.value:
            return CronTrigger.from_crontab(loop.schedule, timezone=loop.timezone)

        elif trigger_type == TriggerType.INTERVAL.value:
            match = _INTERVAL_RE.match(loop.schedule)
            if not match:
                raise ValueError(
                    f"Invalid interval format: '{loop.schedule}'. Use e.g. '30m', '4h', '1d'."
                )
            value, unit = int(match.group(1)), match.group(2).lower()
            return IntervalTrigger(**{_INTERVAL_UNITS[unit]: value})

        elif trigger_type == TriggerType.ONESHOT.value:
            # schedule is ISO datetime string for oneshot
            run_at = datetime.fromisoformat(loop.schedule)
            return DateTrigger(run_date=run_at)

        else:
            raise ValueError(f"Unknown trigger_type: {trigger_type}")

    async def _scheduler_callback(self, loop_id: str) -> None:
        """APScheduler callback — loads loop from DB and executes.

        Uses asyncio.create_task for fire-and-forget dispatch so the
        APScheduler callback doesn't block.
        """
        with get_session() as db:
            loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
            if not loop:
                logger.warning("[LoopService] Scheduled loop not found", extra={"loop_id": loop_id})
                return
            db.expunge(loop)

        asyncio.create_task(self.execute_loop(loop, trigger_source="schedule"))

    # =========================================================================
    # Internal — Target Dispatch
    # =========================================================================

    async def _dispatch(self, loop: ScheduledLoop) -> Any:
        """Route execution to the correct target executor.

        Args:
            loop: ScheduledLoop with target_type and target_id.

        Returns:
            Execution result (format depends on target type).
        """
        target_type = loop.target_type
        if isinstance(target_type, TargetType):
            target_type = target_type.value

        config = loop.config or {}

        if target_type == TargetType.WORKFLOW.value:
            return await self._dispatch_workflow(loop.target_id, config)
        elif target_type == TargetType.AGENT.value:
            return await self._dispatch_agent(loop.target_id, config)
        elif target_type == TargetType.SKILL.value:
            return await self._dispatch_skill(loop.target_id, config)
        elif target_type == TargetType.ORCHESTRATOR_TASK.value:
            return await self._dispatch_orchestrator_task(loop.target_id, config)
        else:
            raise ValueError(f"Unknown target_type: {target_type}")

    async def _dispatch_workflow(self, scenario_name: str, config: dict) -> Any:
        """Dispatch to workflow via TriggerHandler with TriggerSource.SCHEDULE."""
        from core.workflows.triggers import TriggerSource, get_trigger_handler

        handler = get_trigger_handler()
        inputs = config.get("inputs", {})

        # Collect all SSE events — the trigger method is an async generator
        result = None
        async for event_str in handler.trigger(
            scenario_name=scenario_name,
            inputs=inputs,
            trigger_source=TriggerSource.SCHEDULE,
            user_id=config.get("user_id"),
        ):
            # Parse the last workflow_complete event for the result
            if "workflow_complete" in event_str:
                import json

                try:
                    data_str = event_str.replace("data: ", "").strip()
                    data = json.loads(data_str)
                    result = data.get("result")
                except (json.JSONDecodeError, ValueError):
                    pass

        return result

    async def _dispatch_agent(self, agent_name: str, config: dict) -> Any:
        """Dispatch to a registered agent.

        Looks up agent via MCP adapter registry and sends task.
        """
        from core.mcp.registry import MCPRegistry

        registry = MCPRegistry.get_instance()
        adapters = registry.get_adapters()

        for adapter in adapters:
            if adapter.name == agent_name:
                task = config.get("task", f"Scheduled execution of {agent_name}")
                context = config.get("context", {})
                # Agents expose execute or call method
                if hasattr(adapter, "execute"):
                    return await adapter.execute(task, context)
                elif hasattr(adapter, "call_tool"):
                    return await adapter.call_tool(task, context)

        raise ValueError(f"Agent not found: {agent_name}")

    async def _dispatch_skill(self, skill_name: str, config: dict) -> Any:
        """Dispatch to skill via the scheduler's executor callback."""
        if self._scheduler._executor_callback:
            context = config.get("context", {})
            return await self._scheduler._executor_callback(skill_name, context, "schedule")
        raise ValueError("No skill executor callback configured")

    async def _dispatch_orchestrator_task(self, task: str, config: dict) -> Any:
        """Dispatch to DryadeOrchestrator for general task execution."""
        from core.orchestrator.orchestrator import DryadeOrchestrator

        orchestrator = DryadeOrchestrator()
        result = await orchestrator.orchestrate(
            message=task,
            user_id=config.get("user_id", "system"),
            project_id=config.get("project_id"),
        )
        return result

# =============================================================================
# Module-level accessor
# =============================================================================

_loop_service: LoopService | None = None

def get_loop_service() -> LoopService:
    """Get or create the global LoopService instance."""
    global _loop_service
    if _loop_service is None:
        from core.autonomous.scheduler import get_proactive_scheduler

        scheduler = get_proactive_scheduler()
        _loop_service = LoopService(scheduler=scheduler)
    return _loop_service
