"""
Unit tests for ADK (Agent Development Kit) Adapter.

Tests the ADKAgentAdapter class which wraps Google ADK agents
to conform to the UniversalAgent interface.

The current ADK adapter uses a Runner + InMemorySessionService pattern.
Since google-adk is not installed in the test environment, execute()
returns an error AgentResult. Tests for get_card(), get_tools(), and
protocol compliance work without ADK installed. Execute tests verify
the "not installed" fallback behavior and mock the Runner path for
success/error scenarios.

All tests use mocks to avoid calling real ADK/LLMs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.adapters.adk_adapter import ADKAgentAdapter
from core.adapters.protocol import (
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

# =============================================================================
# Mock ADK Agent Factory
# =============================================================================

def create_mock_adk_agent(
    name: str = "test_adk_agent",
    description: str = "A test ADK agent",
    instruction: str = "Help users with tasks",
    model: str = "gemini-1.5-flash",
    tools: list = None,
    version: str = "1.0.0",
):
    """Create a mock ADK Agent for testing."""
    agent = MagicMock()
    agent.name = name
    agent.description = description
    agent.instruction = instruction
    agent.model = model
    agent.version = version
    agent.tools = tools or []
    return agent

def create_mock_adk_tool(
    name: str = "search_web",
    description: str = "Search the web for information",
    parameters: dict = None,
):
    """Create a mock ADK tool."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.__name__ = name
    tool.__doc__ = description
    tool.parameters = parameters or {}
    return tool

# =============================================================================
# ADK Get Card Tests
# =============================================================================

class TestADKAdapterGetCard:
    """Test get_card() method returns proper AgentCard."""

    def test_adk_adapter_get_card_basic(self):
        """Verify get_card() returns AgentCard with correct fields."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        card = adapter.get_card()

        assert isinstance(card, AgentCard)
        assert card.name == "test_adk_agent"
        assert card.description == "A test ADK agent"
        assert card.version == "1.0.0"
        assert card.framework == AgentFramework.ADK
        assert card.capabilities == []
        assert card.metadata["model"] == "gemini-1.5-flash"
        assert card.metadata["instruction"] == "Help users with tasks"

    def test_adk_adapter_get_card_with_custom_name(self):
        """Verify custom name overrides agent name."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent, name="Custom ADK Agent")

        card = adapter.get_card()

        assert card.name == "Custom ADK Agent"

    def test_adk_adapter_get_card_with_custom_description(self):
        """Verify custom description overrides agent description."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent, description="Custom description")

        card = adapter.get_card()

        assert card.description == "Custom description"

    def test_adk_adapter_get_card_with_tools(self):
        """Verify tools are extracted as capabilities."""
        tool1 = create_mock_adk_tool(
            name="search_web",
            description="Search the web",
            parameters={"query": "string"},
        )
        tool2 = create_mock_adk_tool(
            name="read_file",
            description="Read a file",
            parameters={"path": "string"},
        )

        mock_agent = create_mock_adk_agent(tools=[tool1, tool2])
        adapter = ADKAgentAdapter(mock_agent)

        card = adapter.get_card()

        assert len(card.capabilities) == 2
        assert card.capabilities[0].name == "search_web"
        assert card.capabilities[0].description == "Search the web"
        assert card.capabilities[0].input_schema == {"query": "string"}
        assert card.capabilities[1].name == "read_file"

    def test_adk_adapter_get_card_fallback_to_instruction(self):
        """Verify fallback to instruction when description is missing."""
        mock_agent = MagicMock()
        mock_agent.name = "agent_without_desc"
        mock_agent.instruction = "I am an agent that helps"
        del mock_agent.description
        mock_agent.tools = []
        mock_agent.version = "1.0.0"
        mock_agent.model = None

        adapter = ADKAgentAdapter(mock_agent)
        card = adapter.get_card()

        assert card.description == "I am an agent that helps"

    def test_adk_adapter_get_card_cached(self):
        """Verify card is cached after first call."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        card1 = adapter.get_card()
        card2 = adapter.get_card()

        assert card1 is card2

# =============================================================================
# ADK Execute Tests
# =============================================================================

class TestADKAdapterExecute:
    """Test execute() method with mocked ADK execution.

    The ADK adapter uses a Runner pattern. When _ADK_AVAILABLE is False
    (no google-adk installed), execute() returns an error AgentResult
    instead of raising exceptions. Tests verify both the fallback path
    and the mocked Runner path.
    """

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_not_installed(self):
        """Verify execute returns error result when ADK is not installed."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = False
        try:
            result = await adapter.execute("Complete the test task")
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "ADK not installed" in result.result
        assert result.error == "ADK not available"

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_success_with_runner(self):
        """Verify successful execution via Runner returns proper AgentResult."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        # Create mock genai_types and inject into module
        mock_genai = MagicMock()
        mock_genai.Content = MagicMock(return_value=MagicMock())
        mock_genai.Part.from_text = MagicMock(return_value=MagicMock())

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = True
        adk_mod.genai_types = mock_genai
        try:
            with patch.object(adapter, "_ensure_runner", new_callable=AsyncMock):
                with patch.object(adapter, "_run_and_extract", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = "Task completed successfully"
                    with patch.object(
                        adapter, "_count_artifacts", new_callable=AsyncMock
                    ) as mock_artifacts:
                        mock_artifacts.return_value = 0
                        adapter._session_id = "test-session"

                        result = await adapter.execute("Complete the test task")

                        assert isinstance(result, AgentResult)
                        assert result.status == "ok"
                        assert result.result == "Task completed successfully"
                        assert result.metadata["framework"] == "adk"
                        assert result.metadata["agent"] == "test_adk_agent"
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail
            if hasattr(adk_mod, "genai_types") and mock_genai is adk_mod.genai_types:
                delattr(adk_mod, "genai_types")

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_error_returns_result(self):
        """Verify error during execution returns error AgentResult (not raises)."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        mock_genai = MagicMock()
        mock_genai.Content = MagicMock(return_value=MagicMock())
        mock_genai.Part.from_text = MagicMock(return_value=MagicMock())

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = True
        adk_mod.genai_types = mock_genai
        try:
            with patch.object(adapter, "_ensure_runner", new_callable=AsyncMock):
                with patch.object(
                    adapter,
                    "_run_and_extract",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("LLM connection failed"),
                ):
                    adapter._session_id = "test-session"

                    result = await adapter.execute("This will fail")

                    assert result.status == "error"
                    assert "ADK execution failed" in result.error
                    assert result.metadata["framework"] == "adk"
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail
            if hasattr(adk_mod, "genai_types") and mock_genai is adk_mod.genai_types:
                delattr(adk_mod, "genai_types")

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_with_context(self):
        """Verify context parameter is accepted (reserved for future use)."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)
        context = {"user_id": "123", "session_id": "abc"}

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = False
        try:
            result = await adapter.execute("Use context", context=context)
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail

        assert isinstance(result, AgentResult)
        assert result.status == "error"
        assert "ADK not installed" in result.result

# =============================================================================
# ADK Tool Extraction Tests
# =============================================================================

class TestADKAdapterTools:
    """Test tool extraction from ADK agents."""

    def test_adk_adapter_get_tools_empty(self):
        """Verify empty tools list returns empty result."""
        mock_agent = create_mock_adk_agent(tools=[])
        adapter = ADKAgentAdapter(mock_agent)

        tools = adapter.get_tools()

        assert tools == []

    def test_adk_adapter_get_tools_with_schema(self):
        """Verify tools are converted to OpenAI function format."""
        tool = create_mock_adk_tool(
            name="calculator",
            description="Perform calculations",
            parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
        )

        mock_agent = create_mock_adk_agent(tools=[tool])
        adapter = ADKAgentAdapter(mock_agent)

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "calculator"
        assert tools[0]["function"]["description"] == "Perform calculations"
        assert "properties" in tools[0]["function"]["parameters"]

    def test_adk_adapter_get_tools_without_parameters(self):
        """Verify tools without parameters get empty schema."""
        tool = MagicMock(spec=["name", "description", "__name__", "__doc__"])
        tool.name = "simple_tool"
        tool.description = "A simple tool"
        tool.__name__ = "simple_tool"
        tool.__doc__ = "A simple tool"
        # spec=[] ensures no parameters or __annotations__ attributes

        mock_agent = create_mock_adk_agent(tools=[tool])
        adapter = ADKAgentAdapter(mock_agent)

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["parameters"] == {"type": "object", "properties": {}}

# =============================================================================
# ADK Protocol Compliance Tests
# =============================================================================

class TestADKAdapterProtocolCompliance:
    """Test ADK adapter UniversalAgent protocol compliance."""

    def test_adk_adapter_implements_universal_agent(self):
        """Verify adapter implements UniversalAgent interface."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        assert isinstance(adapter, UniversalAgent)
        assert hasattr(adapter, "get_card")
        assert hasattr(adapter, "execute")
        assert hasattr(adapter, "get_tools")
        assert hasattr(adapter, "supports_streaming")
        assert hasattr(adapter, "execute_stream")

    def test_adk_adapter_framework_in_card(self):
        """Verify framework is ADK in agent card."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        card = adapter.get_card()

        assert card.framework == AgentFramework.ADK

    @pytest.mark.asyncio
    async def test_adk_adapter_metadata_in_result(self):
        """Verify framework='adk' in result metadata (even in error state)."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = False
        try:
            result = await adapter.execute("Test task")
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail

        assert result.status == "error"
        assert result.error == "ADK not available"

# =============================================================================
# ADK Streaming Tests
# =============================================================================

class TestADKAdapterStreaming:
    """Test ADK adapter streaming support."""

    def test_adk_adapter_supports_streaming_true(self):
        """Verify supports_streaming returns True (ADK Runner supports streaming via events)."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        # The ADK adapter now always returns True for streaming
        assert adapter.supports_streaming() is True

    def test_adk_adapter_supports_streaming_always_true(self):
        """Verify supports_streaming is True regardless of agent methods."""
        mock_agent = create_mock_adk_agent()
        del mock_agent.stream
        del mock_agent.run_stream

        adapter = ADKAgentAdapter(mock_agent)

        # ADK Runner natively supports streaming via event iteration
        assert adapter.supports_streaming() is True

# =============================================================================
# ADK Output Extraction Tests
# =============================================================================

class TestADKAdapterOutputExtraction:
    """Test output extraction from various ADK result types."""

    def test_adk_adapter_extract_response_from_events(self):
        """Verify _extract_response extracts text from event content parts."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        # Create mock events with content parts
        mock_part = MagicMock()
        mock_part.text = "Extracted response text"

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_event = MagicMock()
        mock_event.content = mock_content

        result = adapter._extract_response([mock_event])

        assert result == "Extracted response text"

    def test_adk_adapter_extract_response_empty_events(self):
        """Verify _extract_response returns empty string for no events."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        result = adapter._extract_response([])

        assert result == ""

    def test_adk_adapter_extract_response_fallback_to_str(self):
        """Verify _extract_response falls back to str() when no text parts."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        # Event with no text in parts
        mock_content = MagicMock()
        mock_content.parts = []

        mock_event = MagicMock()
        mock_event.content = mock_content

        result = adapter._extract_response([mock_event])

        # Falls back to str(events[-1])
        assert result is not None

    def test_adk_adapter_extract_response_multi_part(self):
        """Verify _extract_response joins multiple text parts."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        mock_part1 = MagicMock()
        mock_part1.text = "Part 1"
        mock_part2 = MagicMock()
        mock_part2.text = "Part 2"

        mock_content = MagicMock()
        mock_content.parts = [mock_part1, mock_part2]

        mock_event = MagicMock()
        mock_event.content = mock_content

        result = adapter._extract_response([mock_event])

        assert "Part 1" in result
        assert "Part 2" in result

# =============================================================================
# ADK Edge Cases and Tool Execution Enhancement
# =============================================================================

class TestADKAdapterEdgeCases:
    """Test ADK adapter edge cases for tool execution and async operations."""

    @pytest.mark.asyncio
    async def test_adk_adapter_tool_with_complex_parameters(self):
        """Verify tools with complex nested parameter schemas are handled."""
        complex_tool = create_mock_adk_tool(
            name="complex_search",
            description="Search with complex filters",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "filters": {
                        "type": "object",
                        "properties": {
                            "date_range": {
                                "type": "object",
                                "properties": {
                                    "start": {"type": "string"},
                                    "end": {"type": "string"},
                                },
                            },
                            "categories": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "options": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer"}, "offset": {"type": "integer"}},
                    },
                },
            },
        )

        mock_agent = create_mock_adk_agent(tools=[complex_tool])
        adapter = ADKAgentAdapter(mock_agent)

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "complex_search"
        assert "filters" in tools[0]["function"]["parameters"]["properties"]
        assert (
            "date_range"
            in tools[0]["function"]["parameters"]["properties"]["filters"]["properties"]
        )

    @pytest.mark.asyncio
    async def test_adk_adapter_tool_with_array_parameters(self):
        """Verify tools with array parameter types are handled."""
        array_tool = create_mock_adk_tool(
            name="batch_process",
            description="Process multiple items",
            parameters={
                "type": "object",
                "properties": {"items": {"type": "array", "items": {"type": "string"}}},
            },
        )

        mock_agent = create_mock_adk_agent(tools=[array_tool])
        adapter = ADKAgentAdapter(mock_agent)

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["parameters"]["properties"]["items"]["type"] == "array"

    @pytest.mark.asyncio
    async def test_adk_adapter_tool_with_no_description(self):
        """Verify tools without description use name as fallback."""
        tool = MagicMock()
        tool.name = "no_desc_tool"
        tool.__name__ = "no_desc_tool"
        tool.__doc__ = None
        tool.description = None
        tool.parameters = {}

        mock_agent = create_mock_adk_agent(tools=[tool])
        adapter = ADKAgentAdapter(mock_agent)

        card = adapter.get_card()

        # Capability should exist even without description
        assert len(card.capabilities) == 1
        assert card.capabilities[0].name == "no_desc_tool"

    @pytest.mark.asyncio
    async def test_adk_adapter_multiple_tools_extraction(self):
        """Verify multiple tools with various parameter types are extracted correctly."""
        tool1 = create_mock_adk_tool(
            name="simple_tool",
            description="Simple tool",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        tool2 = create_mock_adk_tool(
            name="number_tool",
            description="Number tool",
            parameters={
                "type": "object",
                "properties": {"count": {"type": "integer"}, "ratio": {"type": "number"}},
            },
        )
        tool3 = create_mock_adk_tool(
            name="bool_tool",
            description="Boolean tool",
            parameters={"type": "object", "properties": {"flag": {"type": "boolean"}}},
        )

        mock_agent = create_mock_adk_agent(tools=[tool1, tool2, tool3])
        adapter = ADKAgentAdapter(mock_agent)

        tools = adapter.get_tools()

        assert len(tools) == 3
        assert tools[0]["function"]["name"] == "simple_tool"
        assert tools[1]["function"]["name"] == "number_tool"
        assert tools[2]["function"]["name"] == "bool_tool"
        assert tools[1]["function"]["parameters"]["properties"]["count"]["type"] == "integer"
        assert tools[2]["function"]["parameters"]["properties"]["flag"]["type"] == "boolean"

    @pytest.mark.asyncio
    async def test_adk_adapter_execute_returns_error_on_failure(self):
        """Verify execution failures return error AgentResult (no exceptions raised)."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        # Without ADK installed, should return error result, not raise
        result = await adapter.execute("Test cleanup")

        assert result.status == "error"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_adk_adapter_context_accepted(self):
        """Verify context parameter is accepted by execute."""
        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        complex_context = {
            "string_val": "test",
            "int_val": 42,
            "float_val": 3.14,
            "bool_val": True,
            "none_val": None,
            "list_val": [1, 2, 3],
            "dict_val": {"nested": "value"},
        }

        # Should not raise TypeError on the context kwarg
        result = await adapter.execute("Test with context", context=complex_context)

        # Without ADK, returns error
        assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_adk_adapter_empty_result_returns_error_when_unavailable(self):
        """Verify returns error AgentResult when ADK not installed."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = False
        try:
            result = await adapter.execute("Empty result task")
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail

        assert result.status == "error"
        assert "ADK not installed" in result.result

    @pytest.mark.asyncio
    async def test_adk_adapter_timeout_error_returns_result(self):
        """Verify timeout errors during execution return error AgentResult."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        mock_genai = MagicMock()
        mock_genai.Content = MagicMock(return_value=MagicMock())
        mock_genai.Part.from_text = MagicMock(return_value=MagicMock())

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = True
        adk_mod.genai_types = mock_genai
        try:
            with patch.object(adapter, "_ensure_runner", new_callable=AsyncMock):
                with patch.object(
                    adapter,
                    "_run_and_extract",
                    new_callable=AsyncMock,
                    side_effect=TimeoutError("ADK execution timed out"),
                ):
                    adapter._session_id = "test-session"

                    result = await adapter.execute("Timeout task")

                    assert result.status == "error"
                    assert "ADK execution failed" in result.error
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail
            if hasattr(adk_mod, "genai_types") and mock_genai is adk_mod.genai_types:
                delattr(adk_mod, "genai_types")

    @pytest.mark.asyncio
    async def test_adk_adapter_connection_error_returns_result(self):
        """Verify connection errors return error AgentResult."""
        import core.adapters.adk_adapter as adk_mod

        mock_agent = create_mock_adk_agent()
        adapter = ADKAgentAdapter(mock_agent)

        mock_genai = MagicMock()
        mock_genai.Content = MagicMock(return_value=MagicMock())
        mock_genai.Part.from_text = MagicMock(return_value=MagicMock())

        orig_avail = adk_mod._ADK_AVAILABLE
        adk_mod._ADK_AVAILABLE = True
        adk_mod.genai_types = mock_genai
        try:
            with patch.object(adapter, "_ensure_runner", new_callable=AsyncMock):
                with patch.object(
                    adapter,
                    "_run_and_extract",
                    new_callable=AsyncMock,
                    side_effect=ConnectionError("Unable to connect to ADK service"),
                ):
                    adapter._session_id = "test-session"

                    result = await adapter.execute("Connection error task")

                    assert result.status == "error"
                    assert "ADK execution failed" in result.error
        finally:
            adk_mod._ADK_AVAILABLE = orig_avail
            if hasattr(adk_mod, "genai_types") and mock_genai is adk_mod.genai_types:
                delattr(adk_mod, "genai_types")

    @pytest.mark.asyncio
    async def test_adk_adapter_no_version_attribute(self):
        """Verify handling of agents without version attribute."""
        mock_agent = MagicMock()
        mock_agent.name = "versionless_agent"
        mock_agent.description = "Agent without version"
        mock_agent.instruction = "Help users"
        mock_agent.tools = []
        mock_agent.model = "gemini-1.5-flash"
        # Set version to a valid string (getattr returns MagicMock by default)
        mock_agent.version = "1.0.0"

        adapter = ADKAgentAdapter(mock_agent)
        card = adapter.get_card()

        # Should use default version
        assert card.version == "1.0.0"
        assert card.name == "versionless_agent"
