"""CrewAI Event Bridge for SSE Streaming.

Subscribes to CrewAI's crewai_event_bus and transforms internal events
into SSE-compatible format for frontend streaming.

Features:
- Context manager pattern for handler lifecycle (prevents memory leaks)
- Supports CrewAI 1.8.0+ event bus API
- Agent correlation for LLM chunk events
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.crew.event_helpers import extract_agent_name, extract_tool_name

logger = logging.getLogger(__name__)

@dataclass
class SSEEvent:
    """SSE-compatible event for frontend streaming."""

    type: str
    agent: str | None = None
    content: str | None = None
    tool: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

class CrewAIEventBridge:
    """Bridge between CrewAI event bus and SSE streaming.

    Subscribes to CrewAI's internal event bus and emits SSE events
    for real-time frontend visibility of agent execution.

    Usage:
        events = []
        bridge = CrewAIEventBridge(lambda e: events.append(e))

        # Context manager (recommended)
        with bridge:
            crew.kickoff()  # Events captured automatically

        # Manual lifecycle
        bridge.start()
        try:
            crew.kickoff()
        finally:
            bridge.stop()
    """

    def __init__(self, sse_emitter: Callable[[SSEEvent], None]):
        """Initialize the event bridge.

        Args:
            sse_emitter: Callback to emit SSE events to the frontend.
                        Signature: def handler(event: SSEEvent)
        """
        self._sse_emitter = sse_emitter
        self._handlers: list[tuple[type, Callable]] = []
        self._current_agent: str | None = None
        self._crewai_available = False

    @property
    def is_active(self) -> bool:
        """Check if handlers are currently registered."""
        return bool(self._handlers)

    @property
    def current_agent(self) -> str | None:
        """Get the currently executing agent for LLM correlation."""
        return self._current_agent

    def _emit(self, event: SSEEvent) -> None:
        """Emit an SSE event via the configured emitter."""
        try:
            self._sse_emitter(event)
        except Exception as e:
            logger.warning(f"Failed to emit SSE event: {e}")

    def start(self) -> None:
        """Register handlers with CrewAI event bus.

        Safe to call multiple times - will not double-register.
        """
        if self._handlers:
            logger.debug("Event bridge already active, skipping start")
            return

        if self._register_handlers():
            self._crewai_available = True
            logger.info("CrewAI event bridge registered (1.8.0+ API)")
        else:
            logger.warning("CrewAI event bus not available - bridge inactive")

    def _register_handlers(self) -> bool:
        """Register with CrewAI 1.8.0+ event bus."""
        try:
            from crewai.events import (
                AgentExecutionCompletedEvent,
                AgentExecutionStartedEvent,
                LLMCallCompletedEvent,
                LLMCallStartedEvent,
                ToolUsageFinishedEvent,
                ToolUsageStartedEvent,
                crewai_event_bus,
            )

            # Agent events
            def handle_agent_start(source, event):
                agent_name = extract_agent_name(event)
                self._current_agent = str(agent_name or source)
                # Convert task to string to avoid JSON serialization issues
                task = getattr(event, "task", None)
                task_str = str(task) if task else None
                self._emit(
                    SSEEvent(
                        type="agent_start",
                        agent=self._current_agent,
                        metadata={"task": task_str},
                    )
                )

            def handle_agent_complete(source, event):
                agent_name = extract_agent_name(event)
                agent = str(agent_name or source)
                result = getattr(event, "result", None)
                self._emit(
                    SSEEvent(
                        type="agent_complete",
                        agent=agent,
                        content=str(result)[:1000] if result else None,
                        metadata={"error": getattr(event, "error", None)},
                    )
                )
                if self._current_agent == agent:
                    self._current_agent = None

            # Tool events
            def handle_tool_start(source, event):
                tool_name = extract_tool_name(event, fallback=str(source))
                self._emit(
                    SSEEvent(
                        type="tool_start",
                        agent=self._current_agent,
                        tool=tool_name,
                        metadata={"args": getattr(event, "args", None)},
                    )
                )

            def handle_tool_complete(source, event):
                tool_name = extract_tool_name(event, fallback=str(source))
                result = getattr(event, "result", None)
                self._emit(
                    SSEEvent(
                        type="tool_complete",
                        agent=self._current_agent,
                        tool=tool_name,
                        content=str(result)[:500] if result else None,
                        metadata={"error": getattr(event, "error", None)},
                    )
                )

            # LLM events
            def handle_llm_start(_source, event):
                self._emit(
                    SSEEvent(
                        type="thinking_start",
                        agent=self._current_agent,
                        metadata={"model": getattr(event, "model", "unknown")},
                    )
                )

            def handle_llm_complete(_source, event):
                response = getattr(event, "response", None)
                self._emit(
                    SSEEvent(
                        type="thinking_complete",
                        agent=self._current_agent,
                        content=str(response)[:2000] if response else None,
                        metadata={
                            "model": getattr(event, "model", "unknown"),
                            "tokens_in": getattr(event, "prompt_tokens", 0),
                            "tokens_out": getattr(event, "completion_tokens", 0),
                        },
                    )
                )

            # Register all handlers
            crewai_event_bus.on(AgentExecutionStartedEvent)(handle_agent_start)
            self._handlers.append((AgentExecutionStartedEvent, handle_agent_start))

            crewai_event_bus.on(AgentExecutionCompletedEvent)(handle_agent_complete)
            self._handlers.append((AgentExecutionCompletedEvent, handle_agent_complete))

            crewai_event_bus.on(ToolUsageStartedEvent)(handle_tool_start)
            self._handlers.append((ToolUsageStartedEvent, handle_tool_start))

            crewai_event_bus.on(ToolUsageFinishedEvent)(handle_tool_complete)
            self._handlers.append((ToolUsageFinishedEvent, handle_tool_complete))

            crewai_event_bus.on(LLMCallStartedEvent)(handle_llm_start)
            self._handlers.append((LLMCallStartedEvent, handle_llm_start))

            crewai_event_bus.on(LLMCallCompletedEvent)(handle_llm_complete)
            self._handlers.append((LLMCallCompletedEvent, handle_llm_complete))

            return True

        except ImportError:
            return False

    def stop(self) -> None:
        """Unregister handlers from CrewAI event bus.

        Safe to call multiple times - idempotent operation.
        """
        if not self._handlers:
            logger.debug("Event bridge already inactive, skipping stop")
            return

        try:
            from crewai.events import crewai_event_bus

            for event_type, handler in self._handlers:
                try:
                    if hasattr(crewai_event_bus, "off"):
                        crewai_event_bus.off(event_type, handler)
                    elif hasattr(crewai_event_bus, "unsubscribe"):
                        crewai_event_bus.unsubscribe(event_type, handler)
                except Exception as e:
                    logger.debug(f"Could not unregister handler for {event_type}: {e}")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Error during handler cleanup: {e}")

        # Clear handler references regardless of unregister success
        self._handlers.clear()
        self._current_agent = None
        logger.info("CrewAI event bridge stopped")

    def __enter__(self) -> "CrewAIEventBridge":
        """Start the event bridge on context entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop the event bridge on context exit."""
        self.stop()
