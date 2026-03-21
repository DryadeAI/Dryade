"""Unit tests for MCP Agent Adapter.

Comprehensive tests for MCPAgentAdapter covering:
- Initialization and validation
- get_card() functionality
- get_tools() with OpenAI format conversion
- execute() with task routing
- create_mcp_agent factory function

Uses mocked MCPRegistry and pytest-asyncio for async tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.protocol import AgentFramework, UniversalAgent
from core.mcp.adapter import MCPAgentAdapter, create_mcp_agent
from core.mcp.config import MCPServerConfig
from core.mcp.protocol import MCPTool, MCPToolCallContent, MCPToolCallResult, MCPToolInputSchema
from core.mcp.registry import MCPRegistryError

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry."""
    registry = MagicMock()
    # Default config for memory server
    registry.get_config.return_value = MCPServerConfig(
        name="memory",
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
    )
    # Default tools
    registry.list_tools.return_value = [
        MCPTool(
            name="create_entities",
            description="Create new entities",
            inputSchema=MCPToolInputSchema(
                type="object",
                properties={"entities": {"type": "array"}},
                required=["entities"],
            ),
        ),
        MCPTool(
            name="read_graph",
            description="Read the knowledge graph",
            inputSchema=MCPToolInputSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
    ]
    return registry

@pytest.fixture
def sample_tool():
    """Create a sample MCPTool for testing."""
    return MCPTool(
        name="test_tool",
        description="A test tool",
        inputSchema=MCPToolInputSchema(
            type="object",
            properties={"arg1": {"type": "string"}},
            required=["arg1"],
        ),
    )

@pytest.fixture
def mock_result():
    """Create a successful MCPToolCallResult."""
    return MCPToolCallResult(
        content=[MCPToolCallContent(type="text", text="Success")],
        isError=False,
    )

@pytest.fixture
def mock_error_result():
    """Create an error MCPToolCallResult."""
    return MCPToolCallResult(
        content=[MCPToolCallContent(type="text", text="Error occurred")],
        isError=True,
    )

# ============================================================================
# Initialization Tests
# ============================================================================

class TestInitialization:
    """Tests for MCPAgentAdapter initialization."""

    def test_init_with_registry(self, mock_registry):
        """Test initialization with provided registry."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        assert adapter._server_name == "memory"
        assert adapter._registry is mock_registry
        mock_registry.get_config.assert_called_once_with("memory")

    def test_init_validates_server_registered(self, mock_registry):
        """Test initialization validates server is registered."""
        mock_registry.get_config.side_effect = MCPRegistryError("not registered")

        with pytest.raises(MCPRegistryError):
            MCPAgentAdapter("nonexistent", registry=mock_registry)

    def test_init_with_description(self, mock_registry):
        """Test initialization with custom description."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry, description="Custom desc")

        assert adapter._description == "Custom desc"

    def test_init_with_version(self, mock_registry):
        """Test initialization with custom version."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry, version="2.0.0")

        assert adapter._version == "2.0.0"

    def test_init_default_version(self, mock_registry):
        """Test default version is 1.0.0."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        assert adapter._version == "1.0.0"

    def test_server_name_property(self, mock_registry):
        """Test server_name property returns correct value."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        assert adapter.server_name == "memory"

    def test_is_subclass_of_universal_agent(self):
        """Test MCPAgentAdapter is subclass of UniversalAgent."""
        assert issubclass(MCPAgentAdapter, UniversalAgent)

# ============================================================================
# get_card Tests
# ============================================================================

class TestGetCard:
    """Tests for get_card() functionality."""

    def test_get_card_returns_agent_card(self, mock_registry):
        """Test get_card returns AgentCard with correct fields."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        assert card.name == "mcp-memory"
        assert card.framework == AgentFramework.MCP
        assert card.version == "1.0.0"

    def test_get_card_default_description(self, mock_registry):
        """Test get_card uses server-specific or fallback description."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        # memory has server-specific description
        assert "memory" in card.description.lower() or "knowledge" in card.description.lower()

    def test_get_card_custom_description(self, mock_registry):
        """Test get_card uses custom description."""
        adapter = MCPAgentAdapter(
            "memory",
            registry=mock_registry,
            description="Knowledge graph server",
        )

        card = adapter.get_card()

        assert card.description == "Knowledge graph server"

    def test_get_card_includes_capabilities(self, mock_registry):
        """Test get_card includes capabilities from tools."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        assert len(card.capabilities) == 2
        assert card.capabilities[0].name == "create_entities"
        assert card.capabilities[1].name == "read_graph"

    def test_get_card_capability_has_input_schema(self, mock_registry):
        """Test capabilities include input schema."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        cap = card.capabilities[0]
        assert "type" in cap.input_schema
        assert "properties" in cap.input_schema
        assert "required" in cap.input_schema

    def test_get_card_metadata_includes_command(self, mock_registry):
        """Test metadata includes command and server info."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        assert "command" in card.metadata
        assert card.metadata["command"] == ["npx", "-y", "@modelcontextprotocol/server-memory"]
        assert card.metadata["mcp_server"] == "memory"
        assert card.metadata["transport"] == "stdio"
        assert "tool_count" in card.metadata

    def test_get_card_endpoint_is_none(self, mock_registry):
        """Test endpoint is None for local MCP servers."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        assert card.endpoint is None

    def test_get_card_handles_tool_listing_failure(self, mock_registry):
        """Test get_card handles tool listing failure gracefully."""
        mock_registry.list_tools.side_effect = Exception("Server not started")
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        assert card.capabilities == []

# ============================================================================
# get_tools Tests
# ============================================================================

class TestGetTools:
    """Tests for get_tools() functionality."""

    def test_get_tools_returns_list(self, mock_registry):
        """Test get_tools returns list of tools."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        tools = adapter.get_tools()

        assert isinstance(tools, list)
        assert len(tools) == 2

    def test_get_tools_openai_format(self, mock_registry):
        """Test tools are in OpenAI function format."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        tools = adapter.get_tools()

        tool = tools[0]
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    def test_get_tools_parameters_structure(self, mock_registry):
        """Test tool parameters have correct structure."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        tools = adapter.get_tools()

        params = tools[0]["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params

    def test_get_tools_handles_failure(self, mock_registry):
        """Test get_tools returns empty list on failure."""
        mock_registry.list_tools.side_effect = Exception("Failed")
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        tools = adapter.get_tools()

        assert tools == []

    def test_get_tools_empty_server(self, mock_registry):
        """Test get_tools with server that has no tools."""
        mock_registry.list_tools.return_value = []
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        tools = adapter.get_tools()

        assert tools == []

# ============================================================================
# execute Tests
# ============================================================================

class TestExecute:
    """Tests for execute() functionality."""

    @pytest.mark.asyncio
    async def test_execute_with_explicit_tool(self, mock_registry, mock_result):
        """Test execute with explicit tool in context."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute(
            "Create entities",
            context={"tool": "create_entities", "arguments": {"entities": []}},
        )

        assert result.status == "ok"
        assert result.result == "Success"
        mock_registry.acall_tool.assert_called_once_with(
            "memory", "create_entities", {"entities": []}
        )

    @pytest.mark.asyncio
    async def test_execute_matches_tool_by_name(self, mock_registry, mock_result):
        """Test execute matches task to tool name."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute("create_entities for my data")

        assert result.status == "ok"
        mock_registry.acall_tool.assert_called_once_with("memory", "create_entities", {})

    @pytest.mark.asyncio
    async def test_execute_no_matching_tool(self, mock_registry):
        """Test execute returns error when no tool matches."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute("unknown task")

        assert result.status == "error"
        assert "No tool found" in result.error
        assert "available_tools" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_handles_tool_error(self, mock_registry, mock_error_result):
        """Test execute handles tool error result."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_error_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute(
            "task",
            context={"tool": "create_entities", "arguments": {}},
        )

        assert result.status == "error"
        assert result.result == "Error occurred"
        assert result.metadata["is_error"] is True

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self, mock_registry):
        """Test execute handles exceptions gracefully."""
        mock_registry.acall_tool = AsyncMock(side_effect=Exception("Connection failed"))
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute(
            "task",
            context={"tool": "create_entities"},
        )

        assert result.status == "error"
        # Error format is "Tool call failed: {ExceptionType}"
        assert "Tool call failed: Exception" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_none_context(self, mock_registry, mock_result):
        """Test execute handles None context."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute("create_entities", context=None)

        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_execute_result_metadata(self, mock_registry, mock_result):
        """Test execute result includes metadata."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute(
            "task",
            context={"tool": "create_entities"},
        )

        assert result.metadata["server"] == "memory"
        assert result.metadata["tool"] == "create_entities"
        assert "content_count" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_binary_content(self, mock_registry):
        """Test execute handles binary content in result."""
        binary_result = MCPToolCallResult(
            content=[MCPToolCallContent(type="image", data="base64data", mimeType="image/png")],
            isError=False,
        )
        mock_registry.acall_tool = AsyncMock(return_value=binary_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute(
            "task",
            context={"tool": "read_image"},
        )

        assert result.status == "ok"
        assert "Binary data" in result.result

    @pytest.mark.asyncio
    async def test_execute_empty_content(self, mock_registry):
        """Test execute handles empty content."""
        empty_result = MCPToolCallResult(content=[], isError=False)
        mock_registry.acall_tool = AsyncMock(return_value=empty_result)
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        result = await adapter.execute(
            "task",
            context={"tool": "void_op"},
        )

        assert result.status == "ok"
        assert result.result is None

# ============================================================================
# Tool Matching Tests
# ============================================================================

class TestToolMatching:
    """Tests for internal tool matching logic."""

    def test_match_exact_tool_name(self, mock_registry):
        """Test exact tool name matching."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        match = adapter._match_tool_to_task("create_entities")

        assert match == "create_entities"

    def test_match_tool_name_in_task(self, mock_registry):
        """Test tool name contained in task."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        match = adapter._match_tool_to_task("Please create_entities for me")

        assert match == "create_entities"

    def test_match_case_insensitive(self, mock_registry):
        """Test matching is case-insensitive."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        match = adapter._match_tool_to_task("CREATE_ENTITIES")

        assert match == "create_entities"

    def test_match_no_match_found(self, mock_registry):
        """Test returns None when no match found."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        match = adapter._match_tool_to_task("do something random")

        assert match is None

    def test_match_handles_list_tools_failure(self, mock_registry):
        """Test returns None on list_tools failure."""
        mock_registry.list_tools.side_effect = Exception("Failed")
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        match = adapter._match_tool_to_task("create_entities")

        assert match is None

# ============================================================================
# supports_streaming Tests
# ============================================================================

class TestSupportsStreaming:
    """Tests for supports_streaming() method."""

    def test_supports_streaming_returns_false(self, mock_registry):
        """Test MCP adapter does not support streaming."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        assert adapter.supports_streaming() is False

# ============================================================================
# create_mcp_agent Factory Tests
# ============================================================================

class TestCreateMcpAgent:
    """Tests for create_mcp_agent factory function."""

    def test_factory_creates_adapter(self, mock_registry):
        """Test factory creates MCPAgentAdapter instance."""
        adapter = create_mcp_agent("memory", registry=mock_registry)

        assert isinstance(adapter, MCPAgentAdapter)
        assert adapter.server_name == "memory"

    def test_factory_with_description(self, mock_registry):
        """Test factory passes description."""
        adapter = create_mcp_agent(
            "memory",
            registry=mock_registry,
            description="Custom",
        )

        assert adapter._description == "Custom"

    def test_factory_with_version(self, mock_registry):
        """Test factory passes version."""
        adapter = create_mcp_agent(
            "memory",
            registry=mock_registry,
            version="3.0.0",
        )

        assert adapter._version == "3.0.0"

    def test_factory_raises_on_unregistered(self, mock_registry):
        """Test factory raises for unregistered server."""
        mock_registry.get_config.side_effect = MCPRegistryError("not registered")

        with pytest.raises(MCPRegistryError):
            create_mcp_agent("nonexistent", registry=mock_registry)

# ============================================================================
# AgentFramework.MCP Tests
# ============================================================================

class TestAgentFrameworkMCP:
    """Tests for AgentFramework.MCP enum value."""

    def test_mcp_enum_exists(self):
        """Test MCP enum value exists."""
        assert hasattr(AgentFramework, "MCP")
        assert AgentFramework.MCP.value == "mcp"

    def test_adapter_uses_mcp_framework(self, mock_registry):
        """Test adapter card uses MCP framework."""
        adapter = MCPAgentAdapter("memory", registry=mock_registry)

        card = adapter.get_card()

        assert card.framework == AgentFramework.MCP
        assert card.framework.value == "mcp"

# ============================================================================
# Integration-Style Mock Tests
# ============================================================================

class TestIntegrationMock:
    """Integration-style tests with mocked registry."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_registry, mock_result):
        """Test full workflow: create, get_card, execute, get_tools."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result)

        # Create adapter
        adapter = create_mcp_agent("memory", registry=mock_registry)

        # Get card
        card = adapter.get_card()
        assert card.name == "mcp-memory"
        assert len(card.capabilities) == 2

        # Get tools
        tools = adapter.get_tools()
        assert len(tools) == 2

        # Execute
        result = await adapter.execute(
            "Create entities",
            context={"tool": "create_entities", "arguments": {}},
        )
        assert result.status == "ok"

    def test_multiple_adapters_same_registry(self, mock_registry):
        """Test multiple adapters can share registry."""
        adapter1 = MCPAgentAdapter("memory", registry=mock_registry)
        adapter2 = MCPAgentAdapter("memory", registry=mock_registry)

        assert adapter1._registry is adapter2._registry

    def test_adapter_with_different_servers(self):
        """Test adapters for different servers."""
        registry = MagicMock()
        registry.get_config.side_effect = [
            MCPServerConfig(name="memory", command=["npx", "-y", "server-memory"]),
            MCPServerConfig(name="git", command=["uvx", "mcp-server-git"]),
        ]
        registry.list_tools.return_value = []

        memory_adapter = MCPAgentAdapter("memory", registry=registry)
        # Reset for second call
        registry.get_config.side_effect = [
            MCPServerConfig(name="git", command=["uvx", "mcp-server-git"]),
        ]
        git_adapter = MCPAgentAdapter("git", registry=registry)

        assert memory_adapter.server_name == "memory"
        assert git_adapter.server_name == "git"
