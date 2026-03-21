"""Tests for CrewAI event bridge."""

from datetime import datetime
from unittest.mock import MagicMock

from core.crew import CrewAIEventBridge, SSEEvent

class TestSSEEvent:
    """Test SSEEvent dataclass."""

    def test_sse_event_creation_with_required_fields(self):
        """SSEEvent can be created with required fields."""
        event = SSEEvent(type="agent_start")
        assert event.type == "agent_start"
        assert event.agent is None
        assert event.content is None
        assert event.tool is None
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_sse_event_with_all_fields(self):
        """SSEEvent can be created with all fields."""
        timestamp = datetime.utcnow()
        event = SSEEvent(
            type="agent_start",
            agent="Researcher",
            content="Starting research",
            tool="web_search",
            timestamp=timestamp,
            metadata={"task": "research"},
        )
        assert event.type == "agent_start"
        assert event.agent == "Researcher"
        assert event.content == "Starting research"
        assert event.tool == "web_search"
        assert event.timestamp == timestamp
        assert event.metadata == {"task": "research"}

    def test_sse_event_types(self):
        """SSEEvent supports expected event types."""
        expected_types = [
            "agent_start",
            "agent_complete",
            "tool_start",
            "tool_complete",
            "thinking_start",
            "thinking_complete",
        ]
        for event_type in expected_types:
            event = SSEEvent(type=event_type)
            assert event.type == event_type

class TestCrewAIEventBridge:
    """Test CrewAIEventBridge functionality."""

    def test_instantiation(self):
        """Bridge can be instantiated with emitter callback."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)
        assert bridge is not None
        assert not bridge.is_active
        assert bridge.current_agent is None

    def test_context_manager_lifecycle(self):
        """Context manager starts and stops handlers."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        # Before context
        assert not bridge.is_active

        with bridge:
            # During context - may or may not be active depending on crewai availability
            # but should not raise
            pass

        # After context - always inactive
        assert not bridge.is_active

    def test_start_stop_idempotent(self):
        """Multiple start/stop calls are safe."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        # Multiple starts should not raise
        bridge.start()
        bridge.start()

        # Multiple stops should not raise
        bridge.stop()
        bridge.stop()
        assert not bridge.is_active

    def test_is_active_property(self):
        """is_active property reflects handler state."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        assert not bridge.is_active

        bridge.start()
        # May or may not be active depending on crewai availability

        bridge.stop()
        assert not bridge.is_active

    def test_current_agent_property(self):
        """current_agent property is accessible."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        assert bridge.current_agent is None

    def test_context_manager_returns_self(self):
        """Context manager returns bridge instance."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        with bridge as b:
            assert b is bridge

    def test_emit_calls_emitter(self):
        """Internal _emit method calls the emitter callback."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        event = SSEEvent(type="test", agent="TestAgent")
        bridge._emit(event)

        emitter.assert_called_once_with(event)

    def test_emit_handles_emitter_exception(self):
        """_emit handles exceptions from emitter gracefully."""
        emitter = MagicMock(side_effect=Exception("Emitter error"))
        bridge = CrewAIEventBridge(emitter)

        event = SSEEvent(type="test")
        # Should not raise
        bridge._emit(event)

        emitter.assert_called_once()

    def test_nested_context_managers(self):
        """Nested context managers work correctly."""
        events1 = []
        events2 = []

        bridge1 = CrewAIEventBridge(lambda e: events1.append(e))
        bridge2 = CrewAIEventBridge(lambda e: events2.append(e))

        with bridge1:
            with bridge2:
                pass
            # bridge2 should be stopped
            assert not bridge2.is_active
        # bridge1 should be stopped
        assert not bridge1.is_active

class TestCrewAIEventBridgeWithoutCrewAI:
    """Test behavior when CrewAI is not available."""

    def test_start_without_crewai(self):
        """Start gracefully handles missing crewai."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        # Should not raise even if crewai not available
        bridge.start()

        # Stop should also work
        bridge.stop()

    def test_context_manager_without_crewai(self):
        """Context manager works without crewai."""
        emitter = MagicMock()
        bridge = CrewAIEventBridge(emitter)

        # Should not raise
        with bridge:
            pass

        assert not bridge.is_active
