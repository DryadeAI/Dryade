"""Composable middleware hooks for the routing and tool execution pipeline.

Phase 115.4: Provides a chain of pre/post hooks at 4 points:
1. pre_routing  -- before routing decision (can modify context)
2. post_routing -- after routing decision (observation only)
3. pre_tool_call -- before tool execution (can modify context)
4. post_tool_call -- after tool execution (observation only)

All hooks are best-effort: errors are logged but never propagate.
Follows the same resilience pattern as routing_metrics.py.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingContext",
    "ToolCallContext",
    "ToolCallResult",
    "PreRoutingHook",
    "PostRoutingHook",
    "PreToolCallHook",
    "PostToolCallHook",
    "MiddlewareChain",
    "get_middleware_chain",
]

@dataclass
class RoutingContext:
    """Context passed through the routing middleware pipeline."""

    goal: str
    model_tier: str
    meta_action_hint: bool
    router_hints: list[dict] | None = None
    available_agents: list = field(default_factory=list)
    selected_tools: list[dict] | None = None

@dataclass
class ToolCallContext:
    """Context for a single tool call in the middleware pipeline."""

    tool_name: str
    arguments: dict
    agent_name: str
    is_self_mod: bool

@dataclass
class ToolCallResult:
    """Result of a tool call for post-execution hooks."""

    success: bool
    result: Any
    error: str | None = None
    duration_ms: int = 0

# Type aliases for hook signatures
PreRoutingHook = Callable[[RoutingContext], Awaitable[RoutingContext | None]]
PostRoutingHook = Callable[[RoutingContext, Any], Awaitable[None]]
PreToolCallHook = Callable[[ToolCallContext], Awaitable[ToolCallContext | None]]
PostToolCallHook = Callable[[ToolCallContext, ToolCallResult], Awaitable[None]]

class MiddlewareChain:
    """Ordered chain of middleware hooks for routing and tool execution.

    Hooks execute in registration order. Errors are caught and logged
    but never propagate -- middleware must never break orchestration.
    """

    def __init__(self):
        self._pre_routing: list[PreRoutingHook] = []
        self._post_routing: list[PostRoutingHook] = []
        self._pre_tool_call: list[PreToolCallHook] = []
        self._post_tool_call: list[PostToolCallHook] = []

    def add_pre_routing(self, hook: PreRoutingHook) -> None:
        """Register a pre-routing hook."""
        self._pre_routing.append(hook)

    def add_post_routing(self, hook: PostRoutingHook) -> None:
        """Register a post-routing hook."""
        self._post_routing.append(hook)

    def add_pre_tool_call(self, hook: PreToolCallHook) -> None:
        """Register a pre-tool-call hook."""
        self._pre_tool_call.append(hook)

    def add_post_tool_call(self, hook: PostToolCallHook) -> None:
        """Register a post-tool-call hook."""
        self._post_tool_call.append(hook)

    async def run_pre_routing(self, ctx: RoutingContext) -> RoutingContext:
        """Execute all pre-routing hooks in order.

        If a hook returns a non-None RoutingContext, it replaces the
        current context for subsequent hooks.

        Args:
            ctx: The routing context to process.

        Returns:
            Possibly modified RoutingContext.
        """
        for hook in self._pre_routing:
            try:
                result = await hook(ctx)
                if result is not None:
                    ctx = result
            except Exception:
                logger.debug(
                    "[MIDDLEWARE] pre_routing hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )
        return ctx

    async def run_post_routing(self, ctx: RoutingContext, thought: Any) -> None:
        """Execute all post-routing hooks (fire-and-forget).

        Args:
            ctx: The routing context after routing decision.
            thought: The routing thought/decision result.
        """
        for hook in self._post_routing:
            try:
                await hook(ctx, thought)
            except Exception:
                logger.debug(
                    "[MIDDLEWARE] post_routing hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )

    async def run_pre_tool_call(self, ctx: ToolCallContext) -> ToolCallContext:
        """Execute all pre-tool-call hooks in order.

        If a hook returns a non-None ToolCallContext, it replaces the
        current context for subsequent hooks.

        Args:
            ctx: The tool call context to process.

        Returns:
            Possibly modified ToolCallContext.
        """
        for hook in self._pre_tool_call:
            try:
                result = await hook(ctx)
                if result is not None:
                    ctx = result
            except Exception:
                logger.debug(
                    "[MIDDLEWARE] pre_tool_call hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )
        return ctx

    async def run_post_tool_call(self, ctx: ToolCallContext, result: ToolCallResult) -> None:
        """Execute all post-tool-call hooks (fire-and-forget).

        Args:
            ctx: The tool call context.
            result: The tool call result.
        """
        for hook in self._post_tool_call:
            try:
                await hook(ctx, result)
            except Exception:
                logger.debug(
                    "[MIDDLEWARE] post_tool_call hook %s failed",
                    getattr(hook, "__name__", repr(hook)),
                    exc_info=True,
                )

    def clear(self) -> None:
        """Remove all registered hooks."""
        self._pre_routing.clear()
        self._post_routing.clear()
        self._pre_tool_call.clear()
        self._post_tool_call.clear()

# ─── Built-in hooks ──────────────────────────────────────────────────────────

async def logging_pre_routing_hook(ctx: RoutingContext) -> None:
    """Log routing start with model tier and goal preview."""
    goal_preview = ctx.goal[:80] + "..." if len(ctx.goal) > 80 else ctx.goal
    logger.info(
        "[MIDDLEWARE] Routing start: tier=%s meta_hint=%s goal='%s'",
        ctx.model_tier,
        ctx.meta_action_hint,
        goal_preview,
    )
    return None

async def metrics_post_routing_hook(ctx: RoutingContext, thought: Any) -> None:
    """Record routing metrics if enabled."""
    try:
        from core.orchestrator.config import get_orchestration_config

        if not get_orchestration_config().routing_metrics_enabled:
            return

        from core.orchestrator.routing_metrics import record_routing_metric

        record_routing_metric(
            message=ctx.goal,
            hint_fired=ctx.meta_action_hint,
            hint_type="middleware" if ctx.meta_action_hint else None,
        )
    except Exception:
        logger.debug("[MIDDLEWARE] metrics_post_routing_hook failed", exc_info=True)

async def logging_post_tool_hook(ctx: ToolCallContext, result: ToolCallResult) -> None:
    """Log tool execution with name, success, and duration."""
    logger.info(
        "[MIDDLEWARE] Tool executed: name=%s success=%s duration_ms=%d",
        ctx.tool_name,
        result.success,
        result.duration_ms,
    )

# ─── Singleton ────────────────────────────────────────────────────────────────

_middleware_chain: MiddlewareChain | None = None
_middleware_chain_lock = threading.Lock()

def get_middleware_chain() -> MiddlewareChain:
    """Get or create singleton MiddlewareChain instance.

    On first creation, registers built-in hooks if middleware is enabled
    in OrchestrationConfig.
    """
    global _middleware_chain
    if _middleware_chain is None:
        with _middleware_chain_lock:
            if _middleware_chain is None:
                chain = MiddlewareChain()
                try:
                    from core.orchestrator.config import get_orchestration_config

                    if get_orchestration_config().middleware_enabled:
                        chain.add_pre_routing(logging_pre_routing_hook)
                        chain.add_post_routing(metrics_post_routing_hook)
                        chain.add_post_tool_call(logging_post_tool_hook)
                except Exception:
                    logger.debug(
                        "[MIDDLEWARE] Failed to check config, returning empty chain",
                        exc_info=True,
                    )
                _middleware_chain = chain
    return _middleware_chain
