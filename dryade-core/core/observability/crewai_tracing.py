"""CrewAI Tracing Integration.

Hooks into CrewAI's event/callback system to capture all execution events
and bridges them to both the local trace storage AND the unified event stream.

Features:
- Automatic callback registration with CrewAI (1.8.0+ API)
- Full trace capture (crew, agent, task, tool, LLM)
- Bridge to Dryade unified events
- Span context propagation (trace_id, span_id)
- Shared event extraction via core.crew.event_helpers
"""

import time
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any

from core.crew.event_helpers import extract_agent_name, extract_tool_name
from core.observability.tracing import trace_event

# -----------------------------------------------------------------------------
# Span Context Management
# -----------------------------------------------------------------------------

class SpanContext:
    """Maintains trace/span context for correlation."""

    def __init__(self, trace_id: str | None = None, parent_span_id: str | None = None):
        """Initialize span context with optional trace/parent IDs.

        Args:
            trace_id: Optional trace ID (generated if not provided)
            parent_span_id: Optional parent span ID for nested spans
        """
        self.trace_id = trace_id or f"trace_{uuid.uuid4().hex[:16]}"
        self.span_id = f"span_{uuid.uuid4().hex[:8]}"
        self.parent_span_id = parent_span_id
        self.start_time = time.time()
        self.end_time: float | None = None
        self.attributes: dict[str, Any] = {}

    def child(self) -> "SpanContext":
        """Create a child span context."""
        return SpanContext(trace_id=self.trace_id, parent_span_id=self.span_id)

    def finish(self) -> float:
        """Mark span as finished, return duration in ms."""
        self.end_time = time.time()
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        """Export context as dictionary."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "attributes": self.attributes,
        }

# Thread-local storage for current context
import threading  # noqa: E402

_context_stack = threading.local()

def get_current_context() -> SpanContext | None:
    """Get the current span context."""
    stack = getattr(_context_stack, "stack", [])
    return stack[-1] if stack else None

def push_context(ctx: SpanContext) -> None:
    """Push a span context onto the stack."""
    if not hasattr(_context_stack, "stack"):
        _context_stack.stack = []
    _context_stack.stack.append(ctx)

def pop_context() -> SpanContext | None:
    """Pop the current span context."""
    stack = getattr(_context_stack, "stack", [])
    return stack.pop() if stack else None

# -----------------------------------------------------------------------------
# CrewAI Callback Handler
# -----------------------------------------------------------------------------

class CrewAITracingCallback:
    """Callback handler for CrewAI execution events.

    Captures all CrewAI events and:
    1. Stores them in the local trace database
    2. Emits unified Dryade events (if event_handler provided)
    """

    def __init__(self, event_handler: Callable | None = None):
        """Initialize the tracing callback.

        Args:
            event_handler: Optional async function to emit Dryade events.
                           Signature: async def handler(event: ChatEvent)
        """
        self.event_handler = event_handler
        self._active_crews: dict[str, SpanContext] = {}
        self._active_agents: dict[str, SpanContext] = {}
        self._active_tasks: dict[str, SpanContext] = {}
        self._active_tools: dict[str, SpanContext] = {}

    async def _emit_event(self, event_type: str, **kwargs):
        """Emit a Dryade event if handler is configured."""
        if self.event_handler:
            from core.extensions.events import ChatEvent

            event = ChatEvent(type=event_type, metadata=kwargs)
            await self.event_handler(event)

    def on_crew_start(self, crew_id: str, crew_name: str, inputs: dict[str, Any] = None):
        """Called when a crew starts execution."""
        ctx = SpanContext()
        ctx.attributes["crew_name"] = crew_name
        self._active_crews[crew_id] = ctx
        push_context(ctx)

        # Store trace
        trace_event(
            "crew_start",
            crew_id=crew_id,
            data={"crew_name": crew_name, "inputs": inputs, **ctx.to_dict()},
        )

    def on_crew_complete(self, crew_id: str, result: Any = None, error: str = None):
        """Called when a crew completes execution."""
        ctx = self._active_crews.pop(crew_id, None)
        duration_ms = ctx.finish() if ctx else 0
        pop_context()

        status = "error" if error else "ok"
        trace_event(
            "crew_complete",
            crew_id=crew_id,
            duration_ms=duration_ms,
            status=status,
            data={
                "result": str(result)[:1000] if result else None,
                "error": error,
                **(ctx.to_dict() if ctx else {}),
            },
        )

    def on_agent_start(self, agent_name: str, task: str = None):
        """Called when an agent starts execution."""
        parent = get_current_context()
        ctx = parent.child() if parent else SpanContext()
        ctx.attributes["agent_name"] = agent_name
        self._active_agents[agent_name] = ctx
        push_context(ctx)

        trace_event("agent_start", agent_name=agent_name, data={"task": task, **ctx.to_dict()})

    def on_agent_complete(self, agent_name: str, result: Any = None, error: str = None):
        """Called when an agent completes execution."""
        ctx = self._active_agents.pop(agent_name, None)
        duration_ms = ctx.finish() if ctx else 0
        pop_context()

        status = "error" if error else "ok"
        trace_event(
            "agent_complete",
            agent_name=agent_name,
            duration_ms=duration_ms,
            status=status,
            data={
                "result": str(result)[:1000] if result else None,
                "error": error,
                **(ctx.to_dict() if ctx else {}),
            },
        )

    def on_task_start(self, task_id: str, description: str = None, agent: str = None):
        """Called when a task starts execution."""
        parent = get_current_context()
        ctx = parent.child() if parent else SpanContext()
        ctx.attributes["task_description"] = description
        self._active_tasks[task_id] = ctx
        push_context(ctx)

        trace_event(
            "task_start",
            task_id=task_id,
            agent_name=agent,
            data={"description": description, **ctx.to_dict()},
        )

    def on_task_complete(self, task_id: str, output: Any = None, error: str = None):
        """Called when a task completes execution."""
        ctx = self._active_tasks.pop(task_id, None)
        duration_ms = ctx.finish() if ctx else 0
        pop_context()

        status = "error" if error else "ok"
        trace_event(
            "task_complete",
            task_id=task_id,
            duration_ms=duration_ms,
            status=status,
            data={
                "output": str(output)[:1000] if output else None,
                "error": error,
                **(ctx.to_dict() if ctx else {}),
            },
        )

    def on_tool_start(self, tool_name: str, args: dict[str, Any] = None):
        """Called when a tool starts execution."""
        parent = get_current_context()
        ctx = parent.child() if parent else SpanContext()
        ctx.attributes["tool_name"] = tool_name
        self._active_tools[tool_name] = ctx

        trace_event("tool_start", tool_name=tool_name, data={"args": args, **ctx.to_dict()})

    def on_tool_complete(self, tool_name: str, result: Any = None, error: str = None):
        """Called when a tool completes execution."""
        ctx = self._active_tools.pop(tool_name, None)
        duration_ms = ctx.finish() if ctx else 0

        status = "error" if error else "ok"
        trace_event(
            "tool_complete",
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            data={
                "result": str(result)[:500] if result else None,
                "error": error,
                **(ctx.to_dict() if ctx else {}),
            },
        )

    def on_llm_start(self, model: str, messages: list[dict] = None):
        """Called when an LLM call starts."""
        parent = get_current_context()
        ctx = parent.child() if parent else SpanContext()
        ctx.attributes["model"] = model
        self._active_tools[f"llm_{model}"] = ctx

        trace_event(
            "llm_start",
            data={
                "model": model,
                "message_count": len(messages) if messages else 0,
                **ctx.to_dict(),
            },
        )

    def on_llm_complete(
        self,
        model: str,
        response: str = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error: str = None,
    ):
        """Called when an LLM call completes."""
        ctx = self._active_tools.pop(f"llm_{model}", None)
        duration_ms = ctx.finish() if ctx else 0

        status = "error" if error else "ok"
        trace_event(
            "llm_complete",
            duration_ms=duration_ms,
            status=status,
            data={
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "response_length": len(response) if response else 0,
                "error": error,
                **(ctx.to_dict() if ctx else {}),
            },
        )

# -----------------------------------------------------------------------------
# CrewAI Event Listener Registration
# -----------------------------------------------------------------------------

def register_crewai_tracing(callback: CrewAITracingCallback = None):
    """Register tracing callbacks with CrewAI's event system.

    This hooks into CrewAI's built-in event listeners to capture all
    execution events automatically.

    Requires CrewAI 1.8.0+ with the crewai.events module.
    """
    callback = callback or CrewAITracingCallback()

    try:
        from crewai.events import (
            AgentExecutionCompletedEvent,
            AgentExecutionStartedEvent,
            CrewKickoffCompletedEvent,
            CrewKickoffStartedEvent,
            LLMCallCompletedEvent,
            LLMCallStartedEvent,
            TaskCompletedEvent,
            TaskStartedEvent,
            ToolUsageFinishedEvent,
            ToolUsageStartedEvent,
            crewai_event_bus,
        )

        # Register crew events (handler receives source, event)
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def handle_crew_start(source, event):
            callback.on_crew_start(
                crew_id=str(getattr(event, "crew_id", id(source))),
                crew_name=getattr(event, "crew_name", str(source)),
                inputs=getattr(event, "inputs", None),
            )

        @crewai_event_bus.on(CrewKickoffCompletedEvent)
        def handle_crew_complete(source, event):
            callback.on_crew_complete(
                crew_id=str(getattr(event, "crew_id", id(source))),
                result=getattr(event, "result", None),
                error=getattr(event, "error", None),
            )

        # Register agent events (use shared extraction helpers)
        @crewai_event_bus.on(AgentExecutionStartedEvent)
        def handle_agent_start(source, event):
            agent_name = extract_agent_name(event)
            callback.on_agent_start(
                agent_name=str(agent_name or source), task=getattr(event, "task", None)
            )

        @crewai_event_bus.on(AgentExecutionCompletedEvent)
        def handle_agent_complete(source, event):
            agent_name = extract_agent_name(event)
            callback.on_agent_complete(
                agent_name=str(agent_name or source),
                result=getattr(event, "result", None),
                error=getattr(event, "error", None),
            )

        # Register task events
        @crewai_event_bus.on(TaskStartedEvent)
        def handle_task_start(source, event):
            task = getattr(event, "task", source)
            task_id = getattr(task, "id", None) or str(id(task))
            callback.on_task_start(
                task_id=str(task_id),
                description=getattr(task, "description", None),
                agent=getattr(task, "agent", None),
            )

        @crewai_event_bus.on(TaskCompletedEvent)
        def handle_task_complete(source, event):
            task = getattr(event, "task", source)
            task_id = getattr(task, "id", None) or str(id(task))
            callback.on_task_complete(
                task_id=str(task_id),
                output=getattr(event, "output", None),
                error=getattr(event, "error", None),
            )

        # Register tool events (use shared extraction helpers)
        @crewai_event_bus.on(ToolUsageStartedEvent)
        def handle_tool_start(source, event):
            callback.on_tool_start(
                tool_name=extract_tool_name(event, fallback=str(source)),
                args=getattr(event, "args", None),
            )

        @crewai_event_bus.on(ToolUsageFinishedEvent)
        def handle_tool_complete(source, event):
            callback.on_tool_complete(
                tool_name=extract_tool_name(event, fallback=str(source)),
                result=getattr(event, "result", None),
                error=getattr(event, "error", None),
            )

        # Register LLM events
        @crewai_event_bus.on(LLMCallStartedEvent)
        def handle_llm_start(_source, event):
            callback.on_llm_start(
                model=getattr(event, "model", "unknown"), messages=getattr(event, "messages", None)
            )

        @crewai_event_bus.on(LLMCallCompletedEvent)
        def handle_llm_complete(_source, event):
            callback.on_llm_complete(
                model=getattr(event, "model", "unknown"),
                response=getattr(event, "response", None),
                tokens_in=getattr(event, "prompt_tokens", 0),
                tokens_out=getattr(event, "completion_tokens", 0),
                error=getattr(event, "error", None),
            )

        import logging

        logging.getLogger(__name__).info("CrewAI tracing registered (1.8.0+ API)")
        return True

    except ImportError as e:
        import logging

        logging.getLogger(__name__).warning(f"CrewAI event bus not available: {e}")
        return False

# -----------------------------------------------------------------------------
# Manual Tracing Decorator (Fallback)
# -----------------------------------------------------------------------------

def traced(name: str | None = None):
    """Decorator to add tracing to any function.

    Use this for custom functions that should be traced but aren't
    automatically captured by CrewAI events.

    Usage:
        @traced("my_operation")
        def do_something():
            ...
    """

    def decorator(func: Callable):
        trace_name = name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            parent = get_current_context()
            ctx = parent.child() if parent else SpanContext()
            push_context(ctx)

            trace_event(f"{trace_name}_start", data={"function": func.__name__, **ctx.to_dict()})

            try:
                result = func(*args, **kwargs)
                duration_ms = ctx.finish()
                trace_event(
                    f"{trace_name}_complete",
                    duration_ms=duration_ms,
                    status="ok",
                    data={**ctx.to_dict()},
                )
                return result
            except Exception as e:
                duration_ms = ctx.finish()
                trace_event(
                    f"{trace_name}_complete",
                    duration_ms=duration_ms,
                    status="error",
                    data={"error": str(e), **ctx.to_dict()},
                )
                raise
            finally:
                pop_context()

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            parent = get_current_context()
            ctx = parent.child() if parent else SpanContext()
            push_context(ctx)

            trace_event(f"{trace_name}_start", data={"function": func.__name__, **ctx.to_dict()})

            try:
                result = await func(*args, **kwargs)
                duration_ms = ctx.finish()
                trace_event(
                    f"{trace_name}_complete",
                    duration_ms=duration_ms,
                    status="ok",
                    data={**ctx.to_dict()},
                )
                return result
            except Exception as e:
                duration_ms = ctx.finish()
                trace_event(
                    f"{trace_name}_complete",
                    duration_ms=duration_ms,
                    status="error",
                    data={"error": str(e), **ctx.to_dict()},
                )
                raise
            finally:
                pop_context()

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator

# -----------------------------------------------------------------------------
# Global Initialization
# -----------------------------------------------------------------------------

_tracing_initialized = False

def init_crewai_tracing(event_handler: Callable | None = None) -> bool:
    """Initialize CrewAI tracing globally.

    Call this at application startup to enable automatic tracing.

    Args:
        event_handler: Optional async function to receive Dryade events

    Returns:
        True if tracing was initialized successfully
    """
    global _tracing_initialized

    if _tracing_initialized:
        return True

    callback = CrewAITracingCallback(event_handler=event_handler)
    success = register_crewai_tracing(callback)
    _tracing_initialized = success

    return success
