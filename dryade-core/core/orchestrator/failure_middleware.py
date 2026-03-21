"""Composable failure handling middleware pipeline.

Phase 118.8: Provides a pipeline of pre/post/recovery hooks at 3 points:
1. pre_failure  -- before classification/LLM reasoning (can modify context, short-circuit)
2. post_failure -- after failure action decided (can override action, short-circuit)
3. on_recovery  -- after recovery attempt (observation only, fire-and-forget)

Plus pluggable RecoveryStrategy ABC for custom recovery implementations.

All hooks are best-effort: errors are logged but never propagate.
Follows the same resilience pattern as middleware.py (Phase 115.4).
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.orchestrator.models import (
    ErrorClassification,
    FailureAction,
    OrchestrationObservation,
    ToolError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FailureContext",
    "RecoveryResult",
    "RecoveryStrategy",
    "PreFailureHook",
    "PostFailureHook",
    "OnRecoveryHook",
    "FailurePipeline",
    "get_failure_pipeline",
    "logging_pre_failure",
    "history_on_recovery",
]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FailureContext:
    """Context object passed through all failure middleware hooks.

    Carries the failed observation, classification results, current failure
    action, and metadata for hooks to communicate.
    """

    observation: OrchestrationObservation
    error_classification: ErrorClassification | None
    failure_action: FailureAction | None
    failure_depth: int
    tool_error: ToolError | None
    metadata: dict[str, Any]
    short_circuit: bool = False
    recovery_strategy: RecoveryStrategy | None = None

@dataclass
class RecoveryResult:
    """Result of a recovery strategy execution."""

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# RecoveryStrategy ABC
# ---------------------------------------------------------------------------

class RecoveryStrategy(ABC):
    """Abstract base class for pluggable recovery implementations.

    Strategies are checked in registration order; first ``can_handle() == True``
    wins.  Subclasses must implement ``name``, ``can_handle``, and ``execute``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name."""
        ...

    @abstractmethod
    def can_handle(self, ctx: FailureContext) -> bool:
        """Return whether this strategy can handle the given failure context."""
        ...

    @abstractmethod
    async def execute(self, ctx: FailureContext) -> RecoveryResult:
        """Perform recovery and return the result."""
        ...

# ---------------------------------------------------------------------------
# Hook type aliases
# ---------------------------------------------------------------------------

PreFailureHook = Callable[[FailureContext], Awaitable[FailureContext | None]]
"""Runs BEFORE failure_think / classification decision.

Can modify FailureContext (e.g., enrich metadata, override classification).
If returns non-None FailureContext, replaces current context.
If sets ``short_circuit=True``, pipeline skips classification and uses
``failure_action`` directly.
"""

PostFailureHook = Callable[[FailureContext], Awaitable[FailureContext | None]]
"""Runs AFTER failure_action has been decided.

Can modify the decided action (e.g., upgrade RETRY to ESCALATE).
If sets ``short_circuit=True``, pipeline skips remaining PostFailure hooks.
If sets ``recovery_strategy``, that strategy is used instead of default handler.
"""

OnRecoveryHook = Callable[[FailureContext, RecoveryResult], Awaitable[None]]
"""Runs AFTER a recovery attempt completes (success or failure).

Fire-and-forget (observation only, no return value).
For logging, metrics, learning, plugin notifications.
"""

# ---------------------------------------------------------------------------
# FailurePipeline
# ---------------------------------------------------------------------------

class FailurePipeline:
    """Ordered pipeline of failure middleware hooks.

    Hooks execute in priority order (lower number = earlier).
    Errors are caught and logged but never propagate -- middleware must
    never break orchestration.
    """

    def __init__(self) -> None:
        # Each list stores (priority, insertion_index, hook) tuples for stable sorting.
        self._pre_failure: list[tuple[int, int, PreFailureHook]] = []
        self._post_failure: list[tuple[int, int, PostFailureHook]] = []
        self._on_recovery: list[OnRecoveryHook] = []
        self._recovery_strategies: list[RecoveryStrategy] = []
        self._insertion_counter: int = 0

    # --- Registration ---

    def add_pre_failure(self, hook: PreFailureHook, *, priority: int = 100) -> None:
        """Register a pre-failure hook, ordered by priority (lower = earlier)."""
        idx = self._insertion_counter
        self._insertion_counter += 1
        self._pre_failure.append((priority, idx, hook))
        self._pre_failure.sort(key=lambda t: (t[0], t[1]))

    def add_post_failure(self, hook: PostFailureHook, *, priority: int = 100) -> None:
        """Register a post-failure hook, ordered by priority (lower = earlier)."""
        idx = self._insertion_counter
        self._insertion_counter += 1
        self._post_failure.append((priority, idx, hook))
        self._post_failure.sort(key=lambda t: (t[0], t[1]))

    def add_on_recovery(self, hook: OnRecoveryHook) -> None:
        """Register an on-recovery hook (fire-and-forget, no priority)."""
        self._on_recovery.append(hook)

    def register_recovery_strategy(self, strategy: RecoveryStrategy) -> None:
        """Add a recovery strategy (checked in registration order)."""
        self._recovery_strategies.append(strategy)

    # --- Execution ---

    async def run_pre_failure(self, ctx: FailureContext) -> FailureContext:
        """Execute all pre-failure hooks in priority order.

        If a hook returns a non-None FailureContext, it replaces the current
        context.  If ``short_circuit`` is set, remaining hooks are skipped.
        """
        for _priority, _idx, hook in self._pre_failure:
            try:
                result = await hook(ctx)
                try:
                    from core.orchestrator.failure_metrics import record_failure_middleware

                    record_failure_middleware(hook_type="pre_failure", success=True)
                except Exception:
                    pass
                if result is not None:
                    ctx = result
                if ctx.short_circuit:
                    break
            except Exception:
                try:
                    from core.orchestrator.failure_metrics import record_failure_middleware

                    record_failure_middleware(hook_type="pre_failure", success=False)
                except Exception:
                    pass
                logger.debug(
                    "[FAILURE_MIDDLEWARE] pre_failure hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )
        return ctx

    async def run_post_failure(self, ctx: FailureContext) -> FailureContext:
        """Execute all post-failure hooks in priority order.

        If a hook returns a non-None FailureContext, it replaces the current
        context.  If ``short_circuit`` is set, remaining hooks are skipped.
        """
        for _priority, _idx, hook in self._post_failure:
            try:
                result = await hook(ctx)
                try:
                    from core.orchestrator.failure_metrics import record_failure_middleware

                    record_failure_middleware(hook_type="post_failure", success=True)
                except Exception:
                    pass
                if result is not None:
                    ctx = result
                if ctx.short_circuit:
                    break
            except Exception:
                try:
                    from core.orchestrator.failure_metrics import record_failure_middleware

                    record_failure_middleware(hook_type="post_failure", success=False)
                except Exception:
                    pass
                logger.debug(
                    "[FAILURE_MIDDLEWARE] post_failure hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )
        return ctx

    async def run_on_recovery(self, ctx: FailureContext, result: RecoveryResult) -> None:
        """Execute all on-recovery hooks (fire-and-forget).

        All hooks run even if some fail.
        """
        for hook in self._on_recovery:
            try:
                await hook(ctx, result)
                try:
                    from core.orchestrator.failure_metrics import record_failure_middleware

                    record_failure_middleware(hook_type="on_recovery", success=True)
                except Exception:
                    pass
            except Exception:
                try:
                    from core.orchestrator.failure_metrics import record_failure_middleware

                    record_failure_middleware(hook_type="on_recovery", success=False)
                except Exception:
                    pass
                logger.debug(
                    "[FAILURE_MIDDLEWARE] on_recovery hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )

    async def find_recovery_strategy(self, ctx: FailureContext) -> RecoveryStrategy | None:
        """Return the first registered strategy that can handle the context.

        Returns None if no strategy matches.
        """
        for strategy in self._recovery_strategies:
            try:
                if strategy.can_handle(ctx):
                    return strategy
            except Exception:
                logger.debug(
                    "[FAILURE_MIDDLEWARE] strategy %s.can_handle() failed",
                    getattr(strategy, "name", repr(strategy)),
                    exc_info=True,
                )
        return None

    def clear(self) -> None:
        """Remove all registered hooks and strategies."""
        self._pre_failure.clear()
        self._post_failure.clear()
        self._on_recovery.clear()
        self._recovery_strategies.clear()

# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------

async def logging_pre_failure(ctx: FailureContext) -> None:
    """Built-in PreFailure hook: log failure context for observability.

    Observation-only -- does not modify the context.
    """
    agent_name = getattr(ctx.observation, "agent_name", "unknown")
    action_val = ctx.failure_action.value if ctx.failure_action else "None"
    logger.info(
        "[FAILURE_MIDDLEWARE] PreFailure: agent=%s, action=%s, depth=%d",
        agent_name,
        action_val,
        ctx.failure_depth,
    )
    return None

async def history_on_recovery(ctx: FailureContext, result: RecoveryResult) -> None:
    """Built-in OnRecovery hook: log recovery outcome.

    Placeholder for future failure-learning integration.
    """
    agent_name = getattr(ctx.observation, "agent_name", "unknown")
    logger.info(
        "[FAILURE_MIDDLEWARE] Recovery: success=%s, agent=%s",
        result.success,
        agent_name,
    )

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_failure_pipeline: FailurePipeline | None = None
_failure_pipeline_lock = threading.Lock()

def get_failure_pipeline() -> FailurePipeline:
    """Get or create singleton FailurePipeline instance.

    Registers built-in hooks when ``failure_middleware_enabled`` is True.

    Uses double-checked locking for thread safety (same pattern as
    ``get_middleware_chain()`` in middleware.py).
    """
    global _failure_pipeline
    if _failure_pipeline is None:
        with _failure_pipeline_lock:
            if _failure_pipeline is None:
                pipeline = FailurePipeline()
                try:
                    from core.orchestrator.config import get_orchestration_config

                    if get_orchestration_config().failure_middleware_enabled:
                        pipeline.add_pre_failure(logging_pre_failure, priority=0)
                        pipeline.add_on_recovery(history_on_recovery)
                except Exception:
                    pass  # Config unavailable -- skip built-in hooks
                _failure_pipeline = pipeline
    return _failure_pipeline
