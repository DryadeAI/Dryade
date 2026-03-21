"""Local Tracing - CrewAI event capture and storage.

Captures CrewAI events and stores in PostgreSQL via SQLAlchemy ORM.
Target: ~200 LOC
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func

from core.utils.time import utcnow

def _safe_serialize(obj: Any) -> Any:
    """Safely serialize an object to JSON-compatible format.

    Handles non-serializable objects like functions, classes, and custom objects
    by converting them to string representations.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        try:
            return {k: _safe_serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
        except Exception:
            return str(obj)
    try:
        return str(obj)
    except Exception:
        return f"<unserializable: {type(obj).__name__}>"

class LocalTraceSink:
    """Store traces in PostgreSQL for local analysis."""

    def __init__(self):
        """Initialize trace sink (uses shared database engine)."""

    @staticmethod
    def _model():
        from core.database.models import TraceEvent

        return TraceEvent

    @staticmethod
    def _get_session():
        from core.database.session import get_session

        return get_session()

    def _to_str(self, val: Any) -> str | None:
        """Safely convert value to string for TEXT columns."""
        if val is None:
            return None
        if isinstance(val, str):
            return val
        if hasattr(val, "role"):
            return str(val.role)
        if hasattr(val, "name"):
            return str(val.name)
        if hasattr(val, "id"):
            return str(val.id)
        return str(val)

    def store(self, event_type: str, **kwargs) -> int:
        """Store a trace event."""
        TraceEvent = self._model()

        data = kwargs.get("data", {})
        try:
            data_json = json.dumps(_safe_serialize(data))
        except Exception:
            data_json = json.dumps({"_serialization_error": str(data)[:500]})

        with self._get_session() as session:
            record = TraceEvent(
                timestamp=utcnow().isoformat(),
                event_type=event_type,
                crew_id=self._to_str(kwargs.get("crew_id")),
                agent_name=self._to_str(kwargs.get("agent_name")),
                task_id=self._to_str(kwargs.get("task_id")),
                tool_name=self._to_str(kwargs.get("tool_name")),
                data=data_json,
                duration_ms=kwargs.get("duration_ms"),
                status=self._to_str(kwargs.get("status")) or "ok",
            )
            session.add(record)
            session.flush()
            return record.id

    def query(
        self,
        event_type: str | None = None,
        crew_id: str | None = None,
        agent_name: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query traces with optional filters."""
        TraceEvent = self._model()

        with self._get_session() as session:
            q = session.query(TraceEvent)

            if event_type:
                q = q.filter(TraceEvent.event_type == event_type)
            if crew_id:
                q = q.filter(TraceEvent.crew_id == crew_id)
            if agent_name:
                q = q.filter(TraceEvent.agent_name == agent_name)
            if since:
                q = q.filter(TraceEvent.timestamp >= since)

            q = q.order_by(TraceEvent.timestamp.desc()).limit(limit)
            rows = q.all()

            return [
                {
                    "id": row.id,
                    "timestamp": row.timestamp,
                    "event_type": row.event_type,
                    "crew_id": row.crew_id,
                    "agent_name": row.agent_name,
                    "task_id": row.task_id,
                    "tool_name": row.tool_name,
                    "data": row.data,
                    "duration_ms": row.duration_ms,
                    "status": row.status,
                }
                for row in rows
            ]

    def export_json(self, path: str, **filters) -> str:
        """Export traces to JSON file."""
        traces = self.query(**filters)
        with open(path, "w") as f:
            json.dump(traces, f, indent=2, default=str)
        return path

    def get_stats(self) -> dict[str, Any]:
        """Get trace statistics."""
        TraceEvent = self._model()

        with self._get_session() as session:
            total = session.query(func.count(TraceEvent.id)).scalar() or 0

            by_type_rows = (
                session.query(TraceEvent.event_type, func.count())
                .group_by(TraceEvent.event_type)
                .all()
            )
            by_type = dict(by_type_rows)

            avg_duration_rows = (
                session.query(TraceEvent.event_type, func.avg(TraceEvent.duration_ms))
                .filter(TraceEvent.duration_ms.isnot(None))
                .group_by(TraceEvent.event_type)
                .all()
            )
            avg_duration = dict(avg_duration_rows)

        return {
            "total_traces": total,
            "by_event_type": by_type,
            "avg_duration_ms": avg_duration,
        }

    def cleanup(self, days: int = 7):
        """Delete old traces."""
        TraceEvent = self._model()
        from datetime import UTC, timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

        with self._get_session() as session:
            session.query(TraceEvent).filter(TraceEvent.timestamp < cutoff).delete(
                synchronize_session="fetch"
            )

# Global sink instance (lazy initialization)
_trace_sink: LocalTraceSink | None = None

def get_trace_sink() -> LocalTraceSink:
    """Get or create the global trace sink."""
    global _trace_sink
    if _trace_sink is None:
        _trace_sink = LocalTraceSink()
    return _trace_sink

# Convenience functions
def trace_event(event_type: str, **kwargs) -> int:
    """Store a trace event."""
    return get_trace_sink().store(event_type, **kwargs)

def trace_crew_start(crew_id: str, crew_name: str, inputs: dict = None):
    """Trace crew kickoff start."""
    return trace_event(
        "crew_start", crew_id=crew_id, data={"crew_name": crew_name, "inputs": inputs}
    )

def trace_crew_complete(crew_id: str, duration_ms: float, status: str = "ok"):
    """Trace crew kickoff complete."""
    return trace_event("crew_complete", crew_id=crew_id, duration_ms=duration_ms, status=status)

def trace_agent_start(agent_name: str, task_id: str = None):
    """Trace agent execution start."""
    return trace_event("agent_start", agent_name=agent_name, task_id=task_id)

def trace_agent_complete(agent_name: str, duration_ms: float, task_id: str = None):
    """Trace agent execution complete."""
    return trace_event(
        "agent_complete", agent_name=agent_name, task_id=task_id, duration_ms=duration_ms
    )

def trace_tool_call(
    tool_name: str, args: dict = None, duration_ms: float = None, status: str = "ok"
):
    """Trace tool execution."""
    return trace_event(
        "tool_call",
        tool_name=tool_name,
        data={"args": args},
        duration_ms=duration_ms,
        status=status,
    )

def trace_llm_call(model: str, tokens_in: int, tokens_out: int, duration_ms: float):
    """Trace LLM call."""
    return trace_event(
        "llm_call",
        data={"model": model, "tokens_in": tokens_in, "tokens_out": tokens_out},
        duration_ms=duration_ms,
    )
