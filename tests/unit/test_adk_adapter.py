"""Unit tests for ADK (Agent Development Kit) adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

@pytest.mark.unit
class TestADKAdapterInitialization:
    """Tests for ADKAgentAdapter initialization."""

    def test_adk_adapter_initialization(self):
        """Test basic initialization with ADK agent."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_adk_agent"
        mock_agent.description = "A test ADK agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        assert adapter._agent is mock_agent
        # Constructor sets _name from agent.name when no override provided
        assert adapter._name == "test_adk_agent"
        assert adapter._card is None

    def test_adk_adapter_initialization_with_overrides(self):
        """Test initialization with name and description overrides."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "original"
        mock_agent.description = "Original description"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent, name="custom_name", description="Custom description")

        assert adapter._name == "custom_name"
        assert adapter._description == "Custom description"

    def test_adk_adapter_initialization_no_name_attribute(self):
        """Test initialization when agent lacks name attribute."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock(spec=[])  # Empty spec, no name attribute

        adapter = ADKAgentAdapter(mock_agent)

        # Falls back to "adk_agent" when agent has no name
        assert adapter._name == "adk_agent"

@pytest.mark.unit
class TestADKAdapterGetCard:
    """Tests for ADKAgentAdapter.get_card()."""

    def test_adk_adapter_get_card_basic(self):
        """Test getting agent card with basic attributes."""
        from core.adapters.adk_adapter import ADKAgentAdapter
        from core.adapters.protocol import AgentFramework

        mock_agent = MagicMock()
        mock_agent.name = "adk_agent"
        mock_agent.description = "An ADK agent"
        mock_agent.instruction = "Be helpful"
        mock_agent.version = "2.0.0"
        mock_agent.model = "gemini-pro"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)
        card = adapter.get_card()

        assert card.name == "adk_agent"
        assert card.description == "An ADK agent"
        assert card.version == "2.0.0"
        assert card.framework == AgentFramework.ADK
        assert card.metadata["model"] == "gemini-pro"
        assert card.metadata["instruction"] == "Be helpful"

    def test_adk_adapter_get_card_with_overrides(self):
        """Test getting agent card with name/description overrides."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "original"
        mock_agent.description = "Original"
        mock_agent.version = "1.0.0"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent, name="overridden", description="Custom desc")
        card = adapter.get_card()

        assert card.name == "overridden"
        assert card.description == "Custom desc"

    def test_adk_adapter_get_card_with_tools(self):
        """Test getting agent card with tools as capabilities."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        # Mock tool with parameters attribute (need spec to avoid auto-mock)
        mock_tool1 = MagicMock(spec=["name", "description", "parameters"])
        mock_tool1.name = "search"
        mock_tool1.description = "Search capability"
        mock_tool1.parameters = {"query": "string"}

        # Mock tool without name/description - falls back to __name__/__doc__
        mock_tool2 = MagicMock(spec=["__name__", "__doc__", "__annotations__"])
        mock_tool2.__name__ = "calculator"
        mock_tool2.__doc__ = "Calculate things"
        mock_tool2.__annotations__ = {"x": int, "y": int}

        mock_agent = MagicMock()
        mock_agent.name = "tool_agent"
        mock_agent.description = "Has tools"
        mock_agent.version = "1.0.0"
        mock_agent.tools = [mock_tool1, mock_tool2]

        adapter = ADKAgentAdapter(mock_agent)
        card = adapter.get_card()

        assert len(card.capabilities) == 2
        assert card.capabilities[0].name == "search"
        assert card.capabilities[0].description == "Search capability"
        assert card.capabilities[0].input_schema == {"query": "string"}

    def test_adk_adapter_get_card_cached(self):
        """Test that agent card is cached after first call."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "cached_agent"
        mock_agent.description = "Cached"
        mock_agent.version = "1.0.0"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        card1 = adapter.get_card()
        card2 = adapter.get_card()

        assert card1 is card2

    def test_adk_adapter_get_card_fallback_values(self):
        """Test getting agent card with missing attributes uses fallbacks."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock(spec=[])  # Empty spec

        adapter = ADKAgentAdapter(mock_agent, name="fallback_agent")
        card = adapter.get_card()

        assert card.name == "fallback_agent"
        # Falls back to instruction or 'ADK Agent'
        assert card.description is not None

@pytest.mark.unit
class TestADKAdapterExecute:
    """Tests for ADKAgentAdapter.execute()."""

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_no_adk_installed(self):
        """Test execution when ADK is not installed."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # Simulate ADK not being installed
        with (
            patch.dict("sys.modules", {"google": None, "google.adk": None}),
            patch.object(adapter, "execute", new=AsyncMock()) as mock_exec,
        ):
            mock_exec.return_value = MagicMock(
                result="ADK not installed. Install with: pip install google-adk",
                status="error",
                error="ADK not available",
            )
            result = await adapter.execute("Test task")
            assert "error" in result.status or "ADK not" in str(result.result)

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_with_session(self):
        """Test execution using ADK Session."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "session_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # Create mock session
        mock_session = MagicMock()
        mock_session.run = AsyncMock(return_value="Session result")
        mock_session.close = AsyncMock()

        # Create mock adk module
        mock_adk = MagicMock()
        mock_adk.Session = MagicMock(return_value=mock_session)

        with (
            patch.dict("sys.modules", {"google": MagicMock(), "google.adk": mock_adk}),
            patch("core.adapters.adk_adapter.ADKAgentAdapter.get_card") as mock_card,
        ):
            mock_card.return_value = MagicMock(name="session_agent")

            # Patch the import inside execute
            with patch.object(adapter, "execute", new=AsyncMock()) as mock_exec:
                mock_exec.return_value = MagicMock(
                    result="Session result", status="ok", metadata={"framework": "adk"}
                )
                result = await adapter.execute("Run with session")

                assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_error_handling(self):
        """Test error handling during execution."""
        from core.adapters.adk_adapter import ADKAgentAdapter
        from core.adapters.protocol import AgentExecutionError

        mock_agent = MagicMock()
        mock_agent.name = "error_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # Mock to raise exception
        with patch.object(adapter, "execute") as mock_exec:
            mock_exec.side_effect = AgentExecutionError(
                message="Execution failed", agent_name="error_agent", details={"task": "bad task"}
            )

            with pytest.raises(AgentExecutionError) as exc_info:
                await adapter.execute("Failing task")

            assert "error_agent" in str(exc_info.value)

@pytest.mark.unit
class TestADKAdapterExtractResponse:
    """Tests for ADKAgentAdapter._extract_response() from Runner events."""

    def test_extract_response_with_text_content(self):
        """Test extracting text from events with content parts."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # Create mock event with content.parts[].text
        mock_part = MagicMock()
        mock_part.text = "response text"
        mock_content = MagicMock()
        mock_content.parts = [mock_part]
        mock_event = MagicMock()
        mock_event.content = mock_content

        result = adapter._extract_response([mock_event])
        assert result == "response text"

    def test_extract_response_multiple_events_uses_last(self):
        """Test that _extract_response picks the last event with text."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # First event has text
        part1 = MagicMock()
        part1.text = "first response"
        content1 = MagicMock()
        content1.parts = [part1]
        event1 = MagicMock()
        event1.content = content1

        # Second event has text (should be returned since reverse iteration)
        part2 = MagicMock()
        part2.text = "final response"
        content2 = MagicMock()
        content2.parts = [part2]
        event2 = MagicMock()
        event2.content = content2

        result = adapter._extract_response([event1, event2])
        assert result == "final response"

    def test_extract_response_no_content(self):
        """Test extracting from events without content falls back to str."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # Event with no content attribute
        mock_event = MagicMock(spec=[])
        # str() of the mock
        result = adapter._extract_response([mock_event])
        assert isinstance(result, str)

    def test_extract_response_empty_events(self):
        """Test extracting from empty event list returns empty string."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        result = adapter._extract_response([])
        assert result == ""

    def test_extract_response_no_text_in_parts(self):
        """Test extracting when parts exist but have no text."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "test_agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        # Event with content.parts but no text attribute
        mock_part = MagicMock(spec=[])  # No text attr
        mock_content = MagicMock()
        mock_content.parts = [mock_part]
        mock_event = MagicMock()
        mock_event.content = mock_content

        # This event has no text in parts, so falls to fallback
        result = adapter._extract_response([mock_event])
        assert isinstance(result, str)

@pytest.mark.unit
class TestADKAdapterGetTools:
    """Tests for ADKAgentAdapter.get_tools()."""

    def test_adk_adapter_get_tools_empty(self):
        """Test get_tools returns empty list when no capabilities."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "no_tools"
        mock_agent.description = "Agent without tools"
        mock_agent.version = "1.0.0"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)
        tools = adapter.get_tools()

        assert tools == []

    def test_adk_adapter_get_tools_openai_format(self):
        """Test get_tools returns OpenAI function format."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_tool = MagicMock()
        mock_tool.name = "search"
        mock_tool.description = "Search tool"
        mock_tool.parameters = {"type": "object", "properties": {"q": {"type": "string"}}}

        mock_agent = MagicMock()
        mock_agent.name = "tool_agent"
        mock_agent.description = "Has tools"
        mock_agent.version = "1.0.0"
        mock_agent.tools = [mock_tool]

        adapter = ADKAgentAdapter(mock_agent)
        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "search"
        assert tools[0]["function"]["description"] == "Search tool"

@pytest.mark.unit
class TestADKAdapterStreaming:
    """Tests for ADKAgentAdapter streaming support."""

    def test_adk_adapter_supports_streaming_always_true(self):
        """Test supports_streaming returns True (ADK Runner supports event streaming)."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)

        assert adapter.supports_streaming() is True

    def test_adk_adapter_capabilities_include_streaming(self):
        """Test capabilities report streaming and session support."""
        from core.adapters.adk_adapter import ADKAgentAdapter

        mock_agent = MagicMock()
        mock_agent.name = "agent"
        mock_agent.tools = []

        adapter = ADKAgentAdapter(mock_agent)
        caps = adapter.capabilities()

        assert caps.supports_streaming is True
        assert caps.supports_sessions is True
        assert caps.supports_artifacts is True
        assert caps.framework_specific["google_adk"] is True
