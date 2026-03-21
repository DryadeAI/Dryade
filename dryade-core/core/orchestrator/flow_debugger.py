# Migrated from plugins/starter/debugger/flow_debugger.py into core (Phase 222).

"""Agent Debugger - Step-through execution with breakpoints.

Enables debugging flows with pause, step, and inspect capabilities.
Target: ~150 LOC
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DebugEventType(str, Enum):
    """Debug event types."""

    BREAKPOINT = "breakpoint"
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"
    STATE_CHANGE = "state_change"
    PAUSED = "paused"
    RESUMED = "resumed"

@dataclass
class DebugEvent:
    """A debug event."""

    type: DebugEventType
    node_id: str | None = None
    state: dict[str, Any] | None = None
    result: Any | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

class FlowDebugger:
    """Debug flows with breakpoints and step-through execution.

    Usage:
        debugger = FlowDebugger(my_flow)
        debugger.add_breakpoint("analyze")

        async for event in debugger.run_debug():
            if event.type == DebugEventType.BREAKPOINT:
                # Inspect state
                print(event.state)
                # Continue or step
                await debugger.step()  # or debugger.continue_()
    """

    def __init__(self, flow):
        """Initialize flow debugger for the given flow.

        Args:
            flow: The flow definition to debug.
        """
        self.flow = flow
        self.breakpoints: set[str] = set()
        self._paused = False
        self._step_mode = False
        self._continue_event = asyncio.Event()
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._execution_history: list[DebugEvent] = []

    def add_breakpoint(self, node_id: str):
        """Add breakpoint at node."""
        self.breakpoints.add(node_id)

    def remove_breakpoint(self, node_id: str):
        """Remove breakpoint."""
        self.breakpoints.discard(node_id)

    def clear_breakpoints(self):
        """Clear all breakpoints."""
        self.breakpoints.clear()

    def list_breakpoints(self) -> list[str]:
        """List all breakpoints."""
        return list(self.breakpoints)

    @property
    def is_paused(self) -> bool:
        """Check if debugger is paused."""
        return self._paused

    def get_state(self) -> dict[str, Any] | None:
        """Get current flow state."""
        if hasattr(self.flow, "state") and hasattr(self.flow.state, "model_dump"):
            return self.flow.state.model_dump()
        return None

    def get_history(self) -> list[dict]:
        """Get execution history."""
        return [
            {
                "type": e.type.value,
                "node_id": e.node_id,
                "state": e.state,
                "result": str(e.result) if e.result else None,
                "timestamp": e.timestamp,
            }
            for e in self._execution_history
        ]

    async def step(self):
        """Execute one node then pause."""
        self._step_mode = True
        self._paused = False
        self._continue_event.set()

    async def continue_(self):
        """Continue until next breakpoint."""
        self._step_mode = False
        self._paused = False
        self._continue_event.set()

    async def pause(self):
        """Pause execution at next opportunity."""
        self._step_mode = True

    async def _emit_event(self, event: DebugEvent):
        """Emit a debug event."""
        self._execution_history.append(event)
        await self._event_queue.put(event)

    async def run_debug(self, inputs: dict | None = None) -> AsyncGenerator[DebugEvent, None]:
        """Run flow with debugging enabled."""
        # Start execution in background
        execution_task = asyncio.create_task(self._execute_with_hooks(inputs))

        try:
            while True:
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                    yield event
                except TimeoutError:
                    if execution_task.done():
                        # Drain remaining events
                        while not self._event_queue.empty():
                            yield await self._event_queue.get()
                        break
        finally:
            if not execution_task.done():
                execution_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await execution_task

    async def _execute_with_hooks(self, _inputs: dict | None = None):
        """Execute flow with debug hooks."""
        # Get flow nodes (methods decorated with @start/@listen)
        nodes = self._get_flow_nodes()

        for node_id in nodes:
            # Check breakpoint or step mode
            if node_id in self.breakpoints or self._step_mode:
                self._paused = True
                await self._emit_event(
                    DebugEvent(
                        type=DebugEventType.BREAKPOINT,
                        node_id=node_id,
                        state=self.get_state(),
                    )
                )

                # Wait for continue/step
                self._continue_event.clear()
                await self._continue_event.wait()

            # Emit node start
            await self._emit_event(
                DebugEvent(
                    type=DebugEventType.NODE_START,
                    node_id=node_id,
                )
            )

            # Execute node
            method = getattr(self.flow, node_id, None)
            if method:
                try:
                    if asyncio.iscoroutinefunction(method):
                        result = await method()
                    else:
                        result = method()

                    # Emit node complete
                    await self._emit_event(
                        DebugEvent(
                            type=DebugEventType.NODE_COMPLETE,
                            node_id=node_id,
                            result=result,
                            state=self.get_state(),
                        )
                    )
                except Exception as e:
                    await self._emit_event(
                        DebugEvent(
                            type=DebugEventType.NODE_COMPLETE,
                            node_id=node_id,
                            result=f"Error: {e}",
                        )
                    )

    def _get_flow_nodes(self) -> list[str]:
        """Get list of flow node method names."""
        nodes = []
        for name in dir(self.flow):
            if name.startswith("_"):
                continue
            method = getattr(self.flow, name, None)
            if callable(method) and hasattr(method, "__wrapped__"):
                # Check if it's a decorated flow method
                nodes.append(name)
        return nodes if nodes else ["start", "process", "end"]  # Fallback

# Convenience function to create debugger
def debug_flow(flow) -> FlowDebugger:
    """Create a debugger for a flow."""
    return FlowDebugger(flow)
