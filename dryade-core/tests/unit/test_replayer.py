# Unit tests for core/orchestrator/replayer.py (migrated Phase 222).

"""Unit tests for replayer (time-travel) business logic."""

import json

import pytest

from core.orchestrator.replayer import (
    EventType,
    ExecutionTrace,
    TimeTravel,
    TraceEvent,
    get_time_travel,
)

@pytest.mark.unit
class TestEventType:
    """Tests for EventType enum."""

    def test_enum_values_exist(self):
        """Test all expected event types exist."""
        assert EventType.LLM_CALL == "llm_call"
        assert EventType.TOOL_CALL == "tool_call"
        assert EventType.STATE_CHANGE == "state_change"
        assert EventType.DECISION == "decision"
        assert EventType.ERROR == "error"

    def test_enum_is_str(self):
        """Test EventType is a string enum."""
        assert isinstance(EventType.LLM_CALL, str)

@pytest.mark.unit
class TestTraceEvent:
    """Tests for TraceEvent dataclass."""

    def test_creation_with_type_only(self):
        """Test creating a TraceEvent with just the type."""
        event = TraceEvent(type=EventType.LLM_CALL)
        assert event.type == EventType.LLM_CALL
        assert event.input_data == {}
        assert event.output_data == {}
        assert event.duration_ms == 0.0
        assert event.metadata == {}
        assert event.timestamp  # auto-generated

    def test_creation_with_all_fields(self):
        """Test creating a TraceEvent with all fields."""
        event = TraceEvent(
            type=EventType.TOOL_CALL,
            input_data={"tool": "search"},
            output_data={"results": ["a", "b"]},
            duration_ms=42.5,
            metadata={"provider": "brave"},
        )
        assert event.input_data == {"tool": "search"}
        assert event.output_data == {"results": ["a", "b"]}
        assert event.duration_ms == 42.5
        assert event.metadata == {"provider": "brave"}

@pytest.mark.unit
class TestExecutionTrace:
    """Tests for ExecutionTrace dataclass."""

    def test_creation_defaults(self):
        """Test ExecutionTrace has auto-generated id and timestamp."""
        trace = ExecutionTrace()
        assert trace.id  # UUID string
        assert trace.started_at  # auto-generated
        assert trace.completed_at is None
        assert trace.events == []
        assert trace.final_state == {}

    def test_events_append(self):
        """Test events can be appended to a trace."""
        trace = ExecutionTrace()
        event = TraceEvent(type=EventType.LLM_CALL)
        trace.events.append(event)
        assert len(trace.events) == 1
        assert trace.events[0].type == EventType.LLM_CALL

@pytest.mark.unit
class TestTimeTravel:
    """Tests for TimeTravel recording and replay."""

    def test_start_recording(self, tmp_path):
        """Test start_recording returns a trace ID."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        trace_id = tt.start_recording()
        assert trace_id  # non-empty string
        assert tt._current_trace is not None

    def test_record_event(self, tmp_path):
        """Test record_event adds event to current trace."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        tt.start_recording()
        tt.record_event(
            EventType.LLM_CALL,
            input_data={"prompt": "hello"},
            output_data={"text": "world"},
            duration_ms=100.0,
        )
        assert len(tt._current_trace.events) == 1
        assert tt._current_trace.events[0].type == EventType.LLM_CALL
        assert tt._current_trace.events[0].input_data == {"prompt": "hello"}

    def test_record_event_without_recording_raises(self, tmp_path):
        """Test record_event raises if no active recording."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        with pytest.raises(RuntimeError, match="No active recording"):
            tt.record_event(EventType.LLM_CALL)

    def test_stop_recording(self, tmp_path):
        """Test stop_recording saves trace to disk and returns it."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        trace_id = tt.start_recording()
        tt.record_event(EventType.TOOL_CALL, input_data={"tool": "search"})
        trace = tt.stop_recording(final_state={"result": "done"})

        assert trace.id == trace_id
        assert trace.completed_at is not None
        assert trace.final_state == {"result": "done"}
        assert len(trace.events) == 1
        assert tt._current_trace is None  # cleared after stop

        # Verify file written to disk
        trace_file = tmp_path / "traces" / f"{trace_id}.json"
        assert trace_file.exists()
        data = json.loads(trace_file.read_text())
        assert data["id"] == trace_id
        assert len(data["events"]) == 1

    def test_stop_recording_without_start_raises(self, tmp_path):
        """Test stop_recording raises if no active recording."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        with pytest.raises(RuntimeError, match="No active recording"):
            tt.stop_recording()

    def test_replay_yields_events(self, tmp_path):
        """Test replay yields events from a saved trace."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        trace_id = tt.start_recording()
        tt.record_event(EventType.LLM_CALL, input_data={"prompt": "a"})
        tt.record_event(EventType.TOOL_CALL, input_data={"tool": "b"})
        tt.record_event(EventType.STATE_CHANGE, input_data={"key": "c"})
        tt.stop_recording()

        events = list(tt.replay(trace_id))
        assert len(events) == 3
        assert events[0].type == EventType.LLM_CALL
        assert events[1].type == EventType.TOOL_CALL
        assert events[2].type == EventType.STATE_CHANGE

    def test_replay_from_index(self, tmp_path):
        """Test replay_from yields events starting from given index."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        trace_id = tt.start_recording()
        tt.record_event(EventType.LLM_CALL)
        tt.record_event(EventType.TOOL_CALL)
        tt.record_event(EventType.DECISION)
        tt.stop_recording()

        events = list(tt.replay_from(trace_id, 1))
        assert len(events) == 2
        assert events[0].type == EventType.TOOL_CALL
        assert events[1].type == EventType.DECISION

    def test_load_trace_from_disk(self, tmp_path):
        """Test load_trace reads trace from disk when not in memory."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        trace_id = tt.start_recording(metadata={"test": True})
        tt.record_event(EventType.ERROR, input_data={"err": "timeout"})
        tt.stop_recording(final_state={"status": "failed"})

        # Create a fresh TimeTravel instance (no in-memory traces)
        tt2 = TimeTravel(storage_path=str(tmp_path / "traces"))
        loaded = tt2.load_trace(trace_id)
        assert loaded.id == trace_id
        assert len(loaded.events) == 1
        assert loaded.events[0].type == EventType.ERROR
        assert loaded.final_state == {"status": "failed"}
        assert loaded.metadata == {"test": True}

    def test_load_nonexistent_trace_raises(self, tmp_path):
        """Test load_trace raises ValueError for missing trace."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        with pytest.raises(ValueError, match="not found"):
            tt.load_trace("nonexistent-id")

    def test_branch_creates_new_trace(self, tmp_path):
        """Test branch creates a new trace with events up to branch point."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))
        trace_id = tt.start_recording()
        tt.record_event(EventType.LLM_CALL)
        tt.record_event(EventType.TOOL_CALL)
        tt.record_event(EventType.DECISION)
        tt.stop_recording()

        new_id = tt.branch(trace_id, 2)
        assert new_id != trace_id
        assert tt._current_trace is not None
        assert len(tt._current_trace.events) == 2
        assert tt._current_trace.metadata["branched_from"] == trace_id

    def test_list_traces(self, tmp_path):
        """Test list_traces returns saved trace summaries."""
        tt = TimeTravel(storage_path=str(tmp_path / "traces"))

        # Create two traces
        id1 = tt.start_recording()
        tt.record_event(EventType.LLM_CALL)
        tt.stop_recording()

        id2 = tt.start_recording()
        tt.record_event(EventType.TOOL_CALL)
        tt.record_event(EventType.DECISION)
        tt.stop_recording()

        traces = tt.list_traces()
        assert len(traces) == 2
        ids = {t["id"] for t in traces}
        assert id1 in ids
        assert id2 in ids

    def test_get_time_travel_singleton(self, tmp_path, monkeypatch):
        """Test get_time_travel returns the same instance."""
        import core.orchestrator.replayer as replayer_mod

        # Reset the global
        monkeypatch.setattr(replayer_mod, "_time_travel", None)

        tt1 = get_time_travel()
        tt2 = get_time_travel()
        assert tt1 is tt2
