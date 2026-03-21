# Unit tests for core/orchestrator/flow_debugger.py (migrated Phase 222).

"""Unit tests for flow debugger business logic."""

import asyncio

import pytest

from core.orchestrator.flow_debugger import (
    DebugEvent,
    DebugEventType,
    FlowDebugger,
    debug_flow,
)

class MockFlow:
    """A mock flow with callable methods for testing."""

    def __init__(self):
        self.called = []

    def start(self):
        self.called.append("start")
        return "start_result"

    def process(self):
        self.called.append("process")
        return "process_result"

    def end(self):
        self.called.append("end")
        return "end_result"

@pytest.mark.unit
class TestDebugEventType:
    """Tests for DebugEventType enum."""

    def test_enum_values_exist(self):
        """Test all expected debug event types exist."""
        assert DebugEventType.BREAKPOINT == "breakpoint"
        assert DebugEventType.NODE_START == "node_start"
        assert DebugEventType.NODE_COMPLETE == "node_complete"
        assert DebugEventType.STATE_CHANGE == "state_change"
        assert DebugEventType.PAUSED == "paused"
        assert DebugEventType.RESUMED == "resumed"

    def test_enum_is_str(self):
        """Test DebugEventType is a string enum."""
        assert isinstance(DebugEventType.BREAKPOINT, str)

@pytest.mark.unit
class TestDebugEvent:
    """Tests for DebugEvent dataclass."""

    def test_creation_with_defaults(self):
        """Test creating a DebugEvent with minimal args."""
        event = DebugEvent(type=DebugEventType.BREAKPOINT)
        assert event.type == DebugEventType.BREAKPOINT
        assert event.node_id is None
        assert event.state is None
        assert event.result is None
        assert event.timestamp  # auto-generated

    def test_creation_with_all_fields(self):
        """Test creating a DebugEvent with all fields."""
        event = DebugEvent(
            type=DebugEventType.NODE_COMPLETE,
            node_id="process",
            state={"key": "value"},
            result="done",
        )
        assert event.node_id == "process"
        assert event.state == {"key": "value"}
        assert event.result == "done"

@pytest.mark.unit
class TestFlowDebugger:
    """Tests for FlowDebugger class."""

    def test_initialization(self):
        """Test FlowDebugger initializes with flow and empty state."""
        flow = MockFlow()
        debugger = FlowDebugger(flow)
        assert debugger.flow is flow
        assert len(debugger.breakpoints) == 0
        assert debugger.is_paused is False

    def test_add_breakpoint(self):
        """Test adding breakpoints."""
        debugger = FlowDebugger(MockFlow())
        debugger.add_breakpoint("process")
        assert "process" in debugger.breakpoints

    def test_remove_breakpoint(self):
        """Test removing breakpoints."""
        debugger = FlowDebugger(MockFlow())
        debugger.add_breakpoint("process")
        debugger.remove_breakpoint("process")
        assert "process" not in debugger.breakpoints

    def test_remove_nonexistent_breakpoint(self):
        """Test removing a breakpoint that doesn't exist doesn't raise."""
        debugger = FlowDebugger(MockFlow())
        debugger.remove_breakpoint("nonexistent")  # should not raise

    def test_clear_breakpoints(self):
        """Test clearing all breakpoints."""
        debugger = FlowDebugger(MockFlow())
        debugger.add_breakpoint("start")
        debugger.add_breakpoint("process")
        debugger.clear_breakpoints()
        assert len(debugger.breakpoints) == 0

    def test_list_breakpoints(self):
        """Test listing breakpoints."""
        debugger = FlowDebugger(MockFlow())
        debugger.add_breakpoint("start")
        debugger.add_breakpoint("end")
        bp_list = debugger.list_breakpoints()
        assert set(bp_list) == {"start", "end"}

    def test_get_state_no_state(self):
        """Test get_state returns None when flow has no state attribute."""
        debugger = FlowDebugger(MockFlow())
        assert debugger.get_state() is None

    def test_get_history_empty(self):
        """Test get_history returns empty list initially."""
        debugger = FlowDebugger(MockFlow())
        assert debugger.get_history() == []

    def test_debug_flow_convenience(self):
        """Test debug_flow convenience function creates FlowDebugger."""
        flow = MockFlow()
        debugger = debug_flow(flow)
        assert isinstance(debugger, FlowDebugger)
        assert debugger.flow is flow

    @pytest.mark.asyncio
    async def test_run_debug_emits_events(self):
        """Test run_debug emits NODE_START and NODE_COMPLETE events for each node."""
        flow = MockFlow()
        debugger = FlowDebugger(flow)
        # MockFlow has no __wrapped__ methods, so fallback nodes: start, process, end

        events = []
        async for event in debugger.run_debug():
            events.append(event)

        # Should have NODE_START + NODE_COMPLETE for each of start, process, end
        assert len(events) == 6
        assert events[0].type == DebugEventType.NODE_START
        assert events[0].node_id == "start"
        assert events[1].type == DebugEventType.NODE_COMPLETE
        assert events[1].node_id == "start"
        assert events[1].result == "start_result"

    @pytest.mark.asyncio
    async def test_breakpoint_pauses_execution(self):
        """Test that adding a breakpoint causes BREAKPOINT event before node."""
        flow = MockFlow()
        debugger = FlowDebugger(flow)
        debugger.add_breakpoint("process")

        events = []
        async for event in debugger.run_debug():
            events.append(event)
            if event.type == DebugEventType.BREAKPOINT:
                # Continue past the breakpoint
                await debugger.continue_()

        # Should include: start events + BREAKPOINT at process + process events + end events
        event_types = [(e.type, e.node_id) for e in events]
        assert (DebugEventType.BREAKPOINT, "process") in event_types
