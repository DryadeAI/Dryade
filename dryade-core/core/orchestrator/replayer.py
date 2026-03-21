# Migrated from plugins/starter/replay/replayer.py into core (Phase 222).

"""Time-Travel Replay.

Record and replay agent executions for debugging.
Target: ~150 LOC

Inspired by LangGraph Time Travel and AgentOps.
See: https://dev.to/sreeni5018/debugging-non-deterministic-llm-agents-implementing-checkpoint-based-state-replay-with-langgraph-5171
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

class EventType(str, Enum):
    """Types of recorded events."""

    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    STATE_CHANGE = "state_change"
    DECISION = "decision"
    ERROR = "error"

@dataclass
class TraceEvent:
    """A single event in the execution trace."""

    type: EventType
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutionTrace:
    """Complete trace of an agent execution."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str | None = None
    events: list[TraceEvent] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

class TimeTravel:
    """Record and replay agent executions.

    Usage:
        tt = TimeTravel()

        # Record execution
        trace_id = tt.start_recording()
        tt.record_event(EventType.LLM_CALL, input={"prompt": "..."}, output={"text": "..."})
        tt.record_event(EventType.TOOL_CALL, input={"tool": "search"}, output={"results": [...]})
        tt.stop_recording()

        # Replay later
        for event in tt.replay(trace_id):
            print(event)
    """

    def __init__(self, storage_path: str = ".traces"):
        """Initialize time-travel recorder with storage directory.

        Args:
            storage_path: Directory path to store execution traces.
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._current_trace: ExecutionTrace | None = None
        self._traces: dict[str, ExecutionTrace] = {}

    def start_recording(self, metadata: dict | None = None) -> str:
        """Start recording a new execution trace."""
        self._current_trace = ExecutionTrace(metadata=metadata or {})
        return self._current_trace.id

    def record_event(
        self,
        event_type: EventType,
        input_data: dict | None = None,
        output_data: dict | None = None,
        duration_ms: float = 0.0,
        metadata: dict | None = None,
    ):
        """Record an event in the current trace."""
        if self._current_trace is None:
            raise RuntimeError("No active recording. Call start_recording() first.")

        event = TraceEvent(
            type=event_type,
            input_data=input_data or {},
            output_data=output_data or {},
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self._current_trace.events.append(event)

    def stop_recording(self, final_state: dict | None = None) -> ExecutionTrace:
        """Stop recording and save the trace."""
        if self._current_trace is None:
            raise RuntimeError("No active recording.")

        self._current_trace.completed_at = datetime.utcnow().isoformat()
        self._current_trace.final_state = final_state or {}

        # Save to memory and disk
        self._traces[self._current_trace.id] = self._current_trace
        self._save_trace(self._current_trace)

        trace = self._current_trace
        self._current_trace = None
        return trace

    def _save_trace(self, trace: ExecutionTrace):
        """Save trace to disk."""
        path = self.storage_path / f"{trace.id}.json"
        data = {
            "id": trace.id,
            "started_at": trace.started_at,
            "completed_at": trace.completed_at,
            "events": [
                {
                    "type": e.type.value,
                    "timestamp": e.timestamp,
                    "input_data": e.input_data,
                    "output_data": e.output_data,
                    "duration_ms": e.duration_ms,
                    "metadata": e.metadata,
                }
                for e in trace.events
            ],
            "final_state": trace.final_state,
            "metadata": trace.metadata,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load_trace(self, trace_id: str) -> ExecutionTrace:
        """Load a trace from disk or memory."""
        if trace_id in self._traces:
            return self._traces[trace_id]

        path = self.storage_path / f"{trace_id}.json"
        if not path.exists():
            raise ValueError(f"Trace {trace_id} not found")

        with open(path) as f:
            data = json.load(f)

        trace = ExecutionTrace(
            id=data["id"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            events=[
                TraceEvent(
                    type=EventType(e["type"]),
                    timestamp=e["timestamp"],
                    input_data=e["input_data"],
                    output_data=e["output_data"],
                    duration_ms=e["duration_ms"],
                    metadata=e["metadata"],
                )
                for e in data["events"]
            ],
            final_state=data.get("final_state", {}),
            metadata=data.get("metadata", {}),
        )

        self._traces[trace_id] = trace
        return trace

    def replay(self, trace_id: str):
        """Replay a trace, yielding events one by one."""
        trace = self.load_trace(trace_id)
        yield from trace.events

    def replay_from(self, trace_id: str, event_index: int):
        """Replay from a specific event index."""
        trace = self.load_trace(trace_id)
        yield from trace.events[event_index:]

    def branch(self, trace_id: str, event_index: int) -> str:
        """Create a branch from an existing trace at a specific point."""
        parent = self.load_trace(trace_id)
        new_id = self.start_recording(
            metadata={
                "branched_from": trace_id,
                "branch_point": event_index,
            }
        )

        # Copy events up to branch point
        for event in parent.events[:event_index]:
            self._current_trace.events.append(event)

        return new_id

    def list_traces(self) -> list[dict]:
        """List all available traces."""
        traces = []
        for path in self.storage_path.glob("*.json"):
            try:
                with open(path) as f:
                    data = json.load(f)
                    traces.append(
                        {
                            "id": data["id"],
                            "started_at": data["started_at"],
                            "completed_at": data.get("completed_at"),
                            "event_count": len(data.get("events", [])),
                        }
                    )
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(traces, key=lambda x: x["started_at"], reverse=True)

# Global instance
_time_travel: TimeTravel | None = None

def get_time_travel() -> TimeTravel:
    """Get or create global TimeTravel instance."""
    global _time_travel
    if _time_travel is None:
        _time_travel = TimeTravel()
    return _time_travel
