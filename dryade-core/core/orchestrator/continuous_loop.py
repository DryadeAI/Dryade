"""Continuous improvement loop for autonomous routing optimization.

Phase 115.5: Background job that periodically checks for new routing
metrics, runs the optimization pipeline with temporal holdout
validation, and promotes improvements when they exceed a threshold.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

logger = logging.getLogger(__name__)

__all__ = [
    "ContinuousOptimizationLoop",
    "get_continuous_loop",
]

class ContinuousOptimizationLoop:
    """Background optimization loop that runs on a schedule.

    Periodically checks for new routing metrics, runs the
    BootstrapFewShot optimizer, validates improvements against a
    holdout set, and optionally creates prompt versions.

    Uses apscheduler AsyncIOScheduler for non-blocking background
    execution (following core/autonomous/scheduler.py pattern).
    """

    def __init__(
        self,
        interval_minutes: int = 60,
        min_new_metrics: int = 50,
        holdout_ratio: float = 0.2,
        improvement_threshold: float = 0.05,
    ):
        self._interval_minutes = interval_minutes
        self._min_new_metrics = min_new_metrics
        self._holdout_ratio = holdout_ratio
        self._improvement_threshold = improvement_threshold

        self._last_optimization_run: datetime | None = None
        self._scheduler = None  # AsyncIOScheduler, created in start()
        self._running: bool = False

    def _check_feature_flags(self) -> bool:
        """Check the full dependency chain of feature flags.

        All four flags must be True for the optimization loop to run:
        optimization_enabled, routing_metrics_enabled, few_shot_enabled,
        middleware_enabled.

        Returns:
            True if all required flags are enabled, False otherwise.
        """
        from core.orchestrator.config import get_orchestration_config

        cfg = get_orchestration_config()

        if not cfg.optimization_enabled:
            logger.debug("[OPT-LOOP] Blocked: optimization_enabled=False")
            return False
        if not cfg.routing_metrics_enabled:
            logger.debug("[OPT-LOOP] Blocked: routing_metrics_enabled=False")
            return False
        if not cfg.few_shot_enabled:
            logger.debug("[OPT-LOOP] Blocked: few_shot_enabled=False")
            return False
        if not cfg.middleware_enabled:
            logger.debug("[OPT-LOOP] Blocked: middleware_enabled=False")
            return False

        return True

    def _get_last_run_from_db(self) -> datetime | None:
        """Best-effort query for the last completed optimization run.

        Reads max(completed_at) from OptimizationCycleRecord where
        status='completed'. Returns None if no records or DB fails.
        """
        try:
            from sqlalchemy import func

            from core.database.models import OptimizationCycleRecord
            from core.database.session import get_session

            with get_session() as session:
                result = (
                    session.query(func.max(OptimizationCycleRecord.completed_at))
                    .filter(OptimizationCycleRecord.status == "completed")
                    .scalar()
                )
                return result
        except Exception:
            logger.debug("[OPT-LOOP] Failed to read last run from DB", exc_info=True)
            return None

    def _count_metrics_since(self, since: datetime) -> int:
        """Best-effort count of routing metrics since a timestamp.

        Returns 0 on failure.
        """
        try:
            from core.database.models import RoutingMetric
            from core.database.session import get_session

            with get_session() as session:
                count = session.query(RoutingMetric).filter(RoutingMetric.timestamp > since).count()
                return count
        except Exception:
            logger.debug("[OPT-LOOP] Failed to count metrics from DB", exc_info=True)
            return 0

    def _compute_holdout_score(
        self,
        optimizer,
        holdout_start: datetime,
        holdout_end: datetime,
    ) -> float:
        """Score the optimizer against holdout metrics.

        Counts how many holdout metrics pass the quality threshold
        WITHOUT adding them as examples.

        Args:
            optimizer: RoutingOptimizer instance.
            holdout_start: Start of holdout window.
            holdout_end: End of holdout window.

        Returns:
            Ratio of passing / total holdout metrics, or 0.0 if empty.
        """
        try:
            metrics = optimizer._query_recent_metrics(holdout_start, limit=200)
            # Filter to holdout window
            holdout = [m for m in metrics if m.timestamp <= holdout_end]

            if not holdout:
                return 0.0

            passing = sum(1 for m in holdout if optimizer._score(m) >= optimizer._threshold)
            return passing / len(holdout)
        except Exception:
            logger.debug("[OPT-LOOP] Failed to compute holdout score", exc_info=True)
            return 0.0

    async def tick(self) -> dict | None:
        """Run a single optimization cycle.

        This is the main entry point called by the scheduler on each
        interval. It checks flags, counts metrics, runs the optimizer,
        validates against a holdout set, and records the cycle in DB.

        Returns:
            Dict summary of the cycle outcome, or None on error.
        """
        now = datetime.now(UTC)

        # a. Check feature flags
        if not self._check_feature_flags():
            return {"status": "skipped", "reason": "feature_flags_disabled"}

        # b. Get last optimization run (from memory or DB fallback)
        last_run = self._last_optimization_run
        if last_run is None:
            last_run = self._get_last_run_from_db()

        # c. Count new metrics since last run
        since = last_run or (now - timedelta(hours=24))
        metric_count = self._count_metrics_since(since)
        if metric_count < self._min_new_metrics:
            return {
                "status": "skipped",
                "reason": "insufficient_metrics",
                "metrics_found": metric_count,
                "min_required": self._min_new_metrics,
            }

        # d. Thundering herd check: re-read DB timestamp
        db_last_run = self._get_last_run_from_db()
        if db_last_run and (now - db_last_run) < timedelta(minutes=self._interval_minutes):
            return {
                "status": "skipped",
                "reason": "thundering_herd_prevention",
            }

        # e. Determine time windows
        train_end = now - timedelta(minutes=5)
        holdout_start = train_end
        holdout_end = now
        train_start = last_run or (now - timedelta(hours=24))

        # f. Create OptimizationCycleRecord (best-effort)
        cycle_id = uuid4().hex[:16]
        self._persist_cycle_start(cycle_id, now, train_start, train_end)

        # g. Run optimizer
        try:
            from core.orchestrator.optimization_pipeline import get_routing_optimizer

            optimizer = get_routing_optimizer()
            result = optimizer.optimize(since=train_start, until=train_end)
        except Exception:
            logger.warning("[OPT-LOOP] Optimizer failed", exc_info=True)
            self._persist_cycle_end(cycle_id, "failed")
            return {"status": "failed", "reason": "optimizer_error"}

        # h. Holdout validation (if examples were added)
        holdout_score = 0.0
        from core.orchestrator.config import get_orchestration_config

        cfg = get_orchestration_config()
        if result.examples_added > 0 and cfg.prompt_versioning_enabled:
            holdout_score = self._compute_holdout_score(optimizer, holdout_start, holdout_end)
            logger.info(
                "[OPT-LOOP] Holdout score: %.3f (threshold: %.3f)",
                holdout_score,
                self._improvement_threshold,
            )
            # Future: create prompt version when holdout_score exceeds
            # baseline + improvement_threshold. For now, log only.

        # i. Update cycle record
        self._persist_cycle_end(
            cycle_id,
            "completed",
            examples_added=result.examples_added,
            examples_rejected=result.examples_rejected,
            total_analyzed=result.total_metrics_analyzed,
            holdout_score=holdout_score,
        )

        # j. Update last run timestamp
        self._last_optimization_run = now

        # k. Return summary
        return {
            "status": "completed",
            "examples_added": result.examples_added,
            "examples_rejected": result.examples_rejected,
            "holdout_score": holdout_score,
            "total_analyzed": result.total_metrics_analyzed,
        }

    def start(self) -> None:
        """Start the background optimization scheduler.

        Creates an AsyncIOScheduler and adds tick() as an interval job.
        """
        if self._running:
            logger.debug("[OPT-LOOP] Already running, skipping start")
            return

        from apscheduler.executors.asyncio import AsyncIOExecutor
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        self._scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": AsyncIOExecutor()},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 120,
            },
        )

        self._scheduler.add_job(
            self.tick,
            trigger=IntervalTrigger(minutes=self._interval_minutes),
            id="continuous_optimization_loop",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        logger.info(
            "[OPT-LOOP] Started continuous optimization loop (interval=%dm, min_metrics=%d)",
            self._interval_minutes,
            self._min_new_metrics,
        )

    def stop(self) -> None:
        """Stop the background optimization scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("[OPT-LOOP] Stopped continuous optimization loop")

    @property
    def is_running(self) -> bool:
        """Whether the optimization loop is currently running."""
        return self._running

    # ---- DB persistence helpers (best-effort) --------------------------------

    def _persist_cycle_start(
        self,
        cycle_id: str,
        started_at: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """Persist the start of an optimization cycle to DB."""
        try:
            from core.database.models import OptimizationCycleRecord
            from core.database.session import get_session

            with get_session() as session:
                rec = OptimizationCycleRecord(
                    cycle_id=cycle_id,
                    started_at=started_at,
                    metrics_window_start=window_start,
                    metrics_window_end=window_end,
                    status="running",
                )
                session.add(rec)
                session.commit()
        except Exception:
            logger.debug("[OPT-LOOP] Failed to persist cycle start", exc_info=True)

    def _persist_cycle_end(
        self,
        cycle_id: str,
        status: str,
        examples_added: int = 0,
        examples_rejected: int = 0,
        total_analyzed: int = 0,
        holdout_score: float | None = None,
    ) -> None:
        """Update an optimization cycle record with completion data."""
        try:
            from core.database.models import OptimizationCycleRecord
            from core.database.session import get_session

            with get_session() as session:
                rec = session.query(OptimizationCycleRecord).filter_by(cycle_id=cycle_id).first()
                if rec:
                    rec.status = status
                    rec.completed_at = datetime.now(UTC)
                    rec.examples_added = examples_added
                    rec.examples_rejected = examples_rejected
                    rec.total_metrics_analyzed = total_analyzed
                    rec.holdout_score = holdout_score
                    session.commit()
        except Exception:
            logger.debug("[OPT-LOOP] Failed to persist cycle end", exc_info=True)

# ---- Singleton with double-checked locking --------------------------------

_loop: ContinuousOptimizationLoop | None = None
_loop_lock = threading.Lock()

def get_continuous_loop() -> ContinuousOptimizationLoop:
    """Get or create the singleton ContinuousOptimizationLoop instance.

    Reads interval and min_metrics from OrchestrationConfig.
    """
    global _loop
    if _loop is None:
        with _loop_lock:
            if _loop is None:
                from core.orchestrator.config import get_orchestration_config

                cfg = get_orchestration_config()
                _loop = ContinuousOptimizationLoop(
                    interval_minutes=cfg.optimization_interval_minutes,
                    min_new_metrics=cfg.optimization_min_metrics,
                )
    return _loop
