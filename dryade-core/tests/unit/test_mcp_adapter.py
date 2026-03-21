"""Unit tests for MCPAgentAdapter.

Tests the adapter that wraps MCP servers as UniversalAgent instances,
covering initialization, 3-tier tool matching, tool execution, error
handling, and the OpenAI function format conversion.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.adapters.protocol import AgentCapabilities, AgentFramework
from core.exceptions import MCPRegistryError, MCPTimeoutError, MCPTransportError
from core.mcp.adapter import SERVER_DESCRIPTIONS, MCPAgentAdapter, create_mcp_agent
from core.mcp.config import MCPServerConfig, MCPServerTransport
from core.mcp.protocol import MCPTool, MCPToolCallContent, MCPToolCallResult, MCPToolInputSchema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_tool(
    name: str,
    description: str = "",
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> MCPTool:
    """Create a minimal MCPTool for testing."""
    return MCPTool(
        name=name,
        description=description,
        inputSchema=MCPToolInputSchema(
            type="object",
            properties=properties or {},
            required=required or [],
        ),
    )

def _make_registry(
    server_name: str = "test-server",
    transport: MCPServerTransport = MCPServerTransport.STDIO,
    tools: list[MCPTool] | None = None,
) -> MagicMock:
    """Create a mock MCPRegistry that is pre-configured for *server_name*.

    Async methods (acall_tool, list_resources, list_prompts) are AsyncMock
    so they can be awaited in tests.
    """
    registry = MagicMock()

    config = MCPServerConfig(
        name=server_name,
        command=["echo", "mock"],
        transport=transport,
    )
    registry.get_config.return_value = config
    registry.list_tools.return_value = tools or []

    # Replace async methods with AsyncMock so they work with `await`
    registry.acall_tool = AsyncMock()
    registry.list_resources = AsyncMock(return_value=[])
    registry.list_prompts = AsyncMock(return_value=[])

    return registry

# ---------------------------------------------------------------------------
# TestAdapterInitialization
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAdapterInitialization:
    """Constructor, property access, and validation."""

    def test_init_with_explicit_registry(self):
        """Adapter stores server name, registry, and transport type."""
        registry = _make_registry("my-server")
        adapter = MCPAgentAdapter("my-server", registry=registry)

        assert adapter.server_name == "my-server"
        assert adapter._registry is registry
        assert adapter._version == "1.0.0"
        assert adapter._transport_type == "stdio"

    def test_init_with_description_override(self):
        """Custom description is stored and used in get_card()."""
        registry = _make_registry("my-server")
        adapter = MCPAgentAdapter("my-server", registry=registry, description="Custom desc")

        assert adapter._description == "Custom desc"

    def test_init_with_custom_version(self):
        """Custom version is stored."""
        registry = _make_registry("my-server")
        adapter = MCPAgentAdapter("my-server", registry=registry, version="2.0.0")

        assert adapter._version == "2.0.0"

    def test_init_unregistered_server_raises(self):
        """Constructing with an unregistered server raises MCPRegistryError."""
        registry = MagicMock()
        registry.get_config.side_effect = MCPRegistryError("Server 'unknown' is not registered")

        with pytest.raises(MCPRegistryError, match="not registered"):
            MCPAgentAdapter("unknown", registry=registry)

    def test_init_uses_global_registry_when_none(self):
        """When no registry is provided, get_registry() is called."""
        mock_reg = _make_registry("mem-server")
        with patch("core.mcp.adapter.get_registry", return_value=mock_reg):
            adapter = MCPAgentAdapter("mem-server")

        assert adapter._registry is mock_reg

    def test_http_transport_type(self):
        """HTTP transport value is stored correctly."""
        registry = MagicMock()
        http_config = MCPServerConfig(
            name="remote",
            command=[],
            transport=MCPServerTransport.HTTP,
            url="https://example.com/mcp",
        )
        registry.get_config.return_value = http_config
        registry.list_tools.return_value = []
        registry.acall_tool = AsyncMock()
        adapter = MCPAgentAdapter("remote", registry=registry)

        assert adapter._transport_type == "http"

# ---------------------------------------------------------------------------
# TestGetCard
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCard:
    """AgentCard generation from server config and tools."""

    def test_card_name_prefixed(self):
        """Card name is prefixed with 'mcp-'."""
        tools = [_make_tool("read_file", "Read a file")]
        registry = _make_registry("filesystem", tools=tools)
        adapter = MCPAgentAdapter("filesystem", registry=registry)

        card = adapter.get_card()
        assert card.name == "mcp-filesystem"

    def test_card_uses_known_server_description(self):
        """Known server gets description from SERVER_DESCRIPTIONS."""
        registry = _make_registry("github")
        adapter = MCPAgentAdapter("github", registry=registry)

        card = adapter.get_card()
        assert card.description == SERVER_DESCRIPTIONS["github"]

    def test_card_uses_description_override(self):
        """Explicit description overrides SERVER_DESCRIPTIONS."""
        registry = _make_registry("github")
        adapter = MCPAgentAdapter("github", registry=registry, description="My desc")

        card = adapter.get_card()
        assert card.description == "My desc"

    def test_card_fallback_description_for_unknown_server(self):
        """Unknown server gets generic fallback description."""
        registry = _make_registry("custom-tool")
        adapter = MCPAgentAdapter("custom-tool", registry=registry)

        card = adapter.get_card()
        assert card.description == "MCP server: custom-tool"

    def test_card_framework_is_mcp(self):
        """Card framework is always MCP."""
        registry = _make_registry("test-server")
        adapter = MCPAgentAdapter("test-server", registry=registry)

        card = adapter.get_card()
        assert card.framework == AgentFramework.MCP

    def test_card_metadata_contains_server_info(self):
        """Card metadata includes mcp_server, transport, tool_count, command."""
        tools = [_make_tool("t1"), _make_tool("t2")]
        registry = _make_registry("test-server", tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        card = adapter.get_card()
        assert card.metadata["mcp_server"] == "test-server"
        assert card.metadata["transport"] == "stdio"
        assert card.metadata["tool_count"] == 2
        assert card.metadata["command"] == ["echo", "mock"]

    def test_card_capabilities_from_tools(self):
        """Each MCP tool becomes an AgentCapability in the card."""
        tools = [
            _make_tool("search", "Search repos", {"query": {"type": "string"}}, ["query"]),
            _make_tool("list_repos", "List repositories"),
        ]
        registry = _make_registry("github", tools=tools)
        adapter = MCPAgentAdapter("github", registry=registry)

        card = adapter.get_card()
        assert len(card.capabilities) == 2
        assert card.capabilities[0].name == "search"
        assert card.capabilities[0].description == "Search repos"
        assert card.capabilities[0].input_schema["required"] == ["query"]

    def test_card_empty_capabilities_on_tool_list_failure(self):
        """If list_tools fails, capabilities is an empty list (not an error)."""
        registry = _make_registry("broken-server")
        registry.list_tools.side_effect = RuntimeError("connection refused")
        adapter = MCPAgentAdapter("broken-server", registry=registry)

        card = adapter.get_card()
        assert card.capabilities == []

# ---------------------------------------------------------------------------
# TestExactMatch (Tier 1)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExactMatch:
    """Tier 1: exact tool name match."""

    def test_exact_match_returns_tool_name(self):
        """Task that IS the tool name matches exactly."""
        tools = [_make_tool("search_repos"), _make_tool("list_repos")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("search_repos") == "search_repos"

    def test_exact_match_case_insensitive(self):
        """Exact match is case-insensitive."""
        tools = [_make_tool("Search_Repos")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("search_repos") == "Search_Repos"

    def test_exact_match_priority_over_contains(self):
        """Exact match wins even when other tools contain the name."""
        tools = [
            _make_tool("search"),
            _make_tool("search_repos"),
            _make_tool("advanced_search"),
        ]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        # "search" should exact-match "search", not fallback to contains
        assert adapter._match_tool_to_task("search") == "search"

    def test_no_match_returns_none(self):
        """No matching tool returns None."""
        tools = [_make_tool("read_file")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("completely_different") is None

# ---------------------------------------------------------------------------
# TestContainsMatch (Tier 2)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestContainsMatch:
    """Tier 2: tool name contained in task."""

    def test_contains_match(self):
        """Tool name found inside a longer task string."""
        tools = [_make_tool("search_repos")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("please search_repos for python") == "search_repos"

    def test_contains_match_case_insensitive(self):
        """Contains match is case-insensitive."""
        tools = [_make_tool("Create_Issue")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("use create_issue to report bug") == "Create_Issue"

    def test_contains_match_returns_first_hit(self):
        """When multiple tools match via contains, the first one wins."""
        tools = [_make_tool("list_files"), _make_tool("list_dirs")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = adapter._match_tool_to_task("please list_files and list_dirs")
        # First matching tool in iteration order
        assert result == "list_files"

    def test_contains_match_fallback_from_exact(self):
        """Contains is only reached when exact match fails."""
        tools = [_make_tool("get_status"), _make_tool("status")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        # "status" exact-matches "status", not "get_status" via contains
        assert adapter._match_tool_to_task("status") == "status"

# ---------------------------------------------------------------------------
# TestVerbMatch (Tier 3)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerbMatch:
    """Tier 3: action verb matching."""

    def test_search_verb_matches_search_tool(self):
        """Verb 'search' maps to tool containing 'search' in name."""
        tools = [_make_tool("code_search", "Search code")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("search for authentication code") == "code_search"

    def test_find_verb_matches_glob_tool(self):
        """Verb 'find' maps to tool with 'glob' pattern in name."""
        tools = [_make_tool("glob_files", "Find files by pattern")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("find all python files") == "glob_files"

    def test_list_verb_matches_directory_tool(self):
        """Verb 'list' maps to tool with 'directory' or 'list' in name/description."""
        tools = [_make_tool("show_directory", "Show directory contents")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("list all items") == "show_directory"

    def test_read_verb_matches_get_tool(self):
        """Verb 'read' maps to tool with 'get' in name."""
        tools = [_make_tool("get_file_content", "Read file content")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("read the readme file") == "get_file_content"

    def test_write_verb_matches_create_tool(self):
        """Verb 'write' maps to tool with 'create' in name."""
        tools = [_make_tool("create_file", "Create a new file")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("write a new config file") == "create_file"

    def test_query_verb_matches_execute_tool(self):
        """Verb 'query' maps to tool with 'execute' in name."""
        tools = [_make_tool("execute_sql", "Run SQL queries")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("query the database") == "execute_sql"

    def test_verb_matches_description_not_just_name(self):
        """Verb matching also checks tool description."""
        tools = [_make_tool("do_stuff", "Run a search across repos")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("search for something") == "do_stuff"

    def test_verb_match_returns_none_when_no_verbs_match(self):
        """If task contains no known verb, returns None."""
        tools = [_make_tool("read_file")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("deploy the application") is None

    def test_verb_match_with_tool_list_failure(self):
        """If list_tools raises, returns None instead of propagating."""
        registry = _make_registry()
        registry.list_tools.side_effect = RuntimeError("server down")
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter._match_tool_to_task("search something") is None

    def test_close_verb_matches_close_tool(self):
        tools = [_make_tool("end_session", "Close the session")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert adapter._match_tool_to_task("close the active session") == "end_session"

    def test_discover_verb_matches_schema_tool(self):
        tools = [_make_tool("inspect_schema", "Discover schema layout")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert adapter._match_tool_to_task("discover the database schema") == "inspect_schema"

    def test_create_verb_matches_create_tool(self):
        tools = [_make_tool("create_element", "Create a new element")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert adapter._match_tool_to_task("create a new logical function") == "create_element"

    def test_delete_verb_matches_remove_tool(self):
        tools = [_make_tool("remove_item", "Delete an item")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert adapter._match_tool_to_task("delete the obsolete component") == "remove_item"

    def test_trace_verb_matches_trace_tool(self):
        tools = [_make_tool("trace_requirements", "Trace reqs")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert (
            adapter._match_tool_to_task("trace all requirements to design") == "trace_requirements"
        )

# ---------------------------------------------------------------------------
# TestPartMatch (Tier 2.5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPartMatch:
    """Tier 2.5: tool name parts match task words."""

    def test_close_session_matches_natural_language(self):
        """'Close the model session gracefully' matches capella_close_session."""
        tools = [_make_tool("capella_open_session"), _make_tool("capella_close_session")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert (
            adapter._match_tool_to_task("Close the Capella model session gracefully.")
            == "capella_close_session"
        )

    def test_discover_schema_matches_natural_language(self):
        """'Discover the model schema' matches capella_discover_schema."""
        tools = [_make_tool("capella_discover_schema"), _make_tool("capella_list")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert (
            adapter._match_tool_to_task(
                "Discover the model schema to confirm layers and element types."
            )
            == "capella_discover_schema"
        )

    def test_trace_requirements_matches(self):
        """'Trace requirements across layers' matches capella_trace."""
        tools = [_make_tool("capella_trace"), _make_tool("capella_list")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        assert (
            adapter._match_tool_to_task("Trace requirements across architecture layers")
            == "capella_trace"
        )

    def test_partial_match_prefers_higher_score(self):
        """When multiple tools match, the one with higher part overlap wins."""
        tools = [_make_tool("capella_list"), _make_tool("capella_list_diagrams")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)
        result = adapter._match_tool_to_task("List all diagrams in the model")
        assert result == "capella_list_diagrams"

# ---------------------------------------------------------------------------
# TestToolExecution
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToolExecution:
    """Tool execution via execute() and _call_tool()."""

    @pytest.mark.asyncio
    async def test_explicit_tool_call(self):
        """Context with 'tool' key calls that tool directly."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="file contents here")],
            isError=False,
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute(
            "read the file",
            context={"tool": "read_file", "arguments": {"path": "/tmp/test.txt"}},
        )

        assert result.status == "ok"
        assert result.result == "file contents here"
        registry.acall_tool.assert_called_once_with(
            "test-server", "read_file", {"path": "/tmp/test.txt"}
        )

    @pytest.mark.asyncio
    async def test_null_arguments_sanitized(self):
        """Null values in arguments are stripped before calling MCP server."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="ok")],
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        await adapter.execute(
            "run tool",
            context={"tool": "my_tool", "arguments": {"query": "test", "filter": None}},
        )

        # The None value should be removed
        registry.acall_tool.assert_called_once_with("test-server", "my_tool", {"query": "test"})

    @pytest.mark.asyncio
    async def test_tool_matched_by_task_description(self):
        """When no explicit tool, _match_tool_to_task finds the right one."""
        tools = [_make_tool("search_code", "Search code in repository")]
        registry = _make_registry(tools=tools)
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="found it")],
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("search_code")

        assert result.status == "ok"
        assert result.result == "found it"

    @pytest.mark.asyncio
    async def test_no_matching_tool_returns_error(self):
        """When no tool matches the task, returns error with available tools."""
        tools = [_make_tool("read_file"), _make_tool("write_file")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("deploy everything")

        assert result.status == "error"
        assert "No tool found" in result.error
        assert result.metadata["error_type"] == "no_match"
        assert "read_file" in result.metadata["available_tools"]

    @pytest.mark.asyncio
    async def test_tool_error_result(self):
        """MCP tool returns isError=True."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Permission denied")],
            isError=True,
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "restricted"})

        assert result.status == "error"
        assert result.result == "Permission denied"
        assert result.metadata["is_error"] is True

    @pytest.mark.asyncio
    async def test_binary_content_formatted(self):
        """Binary content items are described with mime type."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[
                MCPToolCallContent(type="text", text="Header text"),
                MCPToolCallContent(type="image", data="base64data", mimeType="image/png"),
            ],
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "get_screenshot"})

        assert result.status == "ok"
        assert "Header text" in result.result
        assert "[Binary data: image/png]" in result.result

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self):
        """Empty content list yields None result with ok status."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(content=[])
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "noop"})

        assert result.status == "ok"
        assert result.result is None

    @pytest.mark.asyncio
    async def test_multiple_text_content_joined(self):
        """Multiple text content items are newline-joined."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[
                MCPToolCallContent(type="text", text="line 1"),
                MCPToolCallContent(type="text", text="line 2"),
            ],
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "multi"})

        assert result.result == "line 1\nline 2"

    @pytest.mark.asyncio
    async def test_metadata_includes_server_and_tool(self):
        """Successful result metadata has server, tool, and content_count."""
        registry = _make_registry()
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="ok")],
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "my_tool"})

        assert result.metadata["server"] == "test-server"
        assert result.metadata["tool"] == "my_tool"
        assert result.metadata["content_count"] == 1

# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestErrorHandling:
    """Error handling in execute() for various failure modes."""

    @pytest.mark.asyncio
    async def test_mcp_timeout_caught_by_execute(self):
        """MCPTimeoutError raised outside _call_tool is caught by execute()."""
        registry = _make_registry()
        # Simulate timeout during tool matching (list_tools called in _match_tool_to_task)
        # by making execute raise MCPTimeoutError in the outer try block.
        # We achieve this by patching _call_tool to re-raise as MCPTimeoutError.
        adapter = MCPAgentAdapter("test-server", registry=registry)
        adapter._call_tool = AsyncMock(side_effect=MCPTimeoutError("Server timed out"))

        result = await adapter.execute("x", context={"tool": "slow_tool"})

        assert result.status == "error"
        assert "timed out" in result.error
        assert result.metadata["error_type"] == "mcp_timeout"

    @pytest.mark.asyncio
    async def test_mcp_transport_error_caught_by_execute(self):
        """MCPTransportError raised outside _call_tool is caught by execute()."""
        adapter = MCPAgentAdapter("test-server", registry=_make_registry())
        adapter._call_tool = AsyncMock(side_effect=MCPTransportError("Connection refused"))

        result = await adapter.execute("x", context={"tool": "broken"})

        assert result.status == "error"
        assert "communication failed" in result.error
        assert result.metadata["error_type"] == "mcp_transport"

    @pytest.mark.asyncio
    async def test_acall_tool_exception_caught_by_call_tool(self):
        """Exceptions from acall_tool are caught by _call_tool's own handler."""
        registry = _make_registry()
        registry.acall_tool.side_effect = ValueError("bad args")
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "crasher"})

        assert result.status == "error"
        # _call_tool catches all exceptions with error_type "tool_call_error"
        assert result.metadata["error_type"] == "tool_call_error"
        assert "ValueError" in result.error

    @pytest.mark.asyncio
    async def test_generic_exception_caught_by_execute(self):
        """Unexpected exception outside _call_tool caught by execute() outer handler."""
        adapter = MCPAgentAdapter("test-server", registry=_make_registry())
        adapter._call_tool = AsyncMock(side_effect=RuntimeError("unexpected"))

        result = await adapter.execute("x", context={"tool": "crasher"})

        assert result.status == "error"
        assert "RuntimeError" in result.error
        assert result.metadata["error_type"] == "mcp_error"

    @pytest.mark.asyncio
    async def test_tool_call_internal_exception(self):
        """Exception during _call_tool (inside the try) returns error."""
        registry = _make_registry()
        # acall_tool raises inside _call_tool
        registry.acall_tool.side_effect = RuntimeError("broken pipe")
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("x", context={"tool": "pipe_tool"})

        # The outer execute handler catches RuntimeError
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_execute_with_none_context(self):
        """Execute with context=None defaults to empty dict, triggers matching."""
        tools = [_make_tool("echo", "Echo back")]
        registry = _make_registry(tools=tools)
        registry.acall_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="echoed")],
        )
        adapter = MCPAgentAdapter("test-server", registry=registry)

        result = await adapter.execute("echo", context=None)

        assert result.status == "ok"
        assert result.result == "echoed"

# ---------------------------------------------------------------------------
# TestGetTools (OpenAI Format)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetTools:
    """get_tools() returns MCP tools in OpenAI function format."""

    def test_openai_format_structure(self):
        """Each tool has type=function with function.name/description/parameters."""
        tools = [
            _make_tool("search", "Search repos", {"q": {"type": "string"}}, ["q"]),
        ]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        openai_tools = adapter.get_tools()

        assert len(openai_tools) == 1
        t = openai_tools[0]
        assert t["type"] == "function"
        assert t["function"]["name"] == "search"
        assert t["function"]["description"] == "Search repos"
        assert t["function"]["parameters"]["type"] == "object"
        assert t["function"]["parameters"]["required"] == ["q"]

    def test_multiple_tools(self):
        """Multiple MCP tools produce multiple OpenAI tool entries."""
        tools = [_make_tool("a"), _make_tool("b"), _make_tool("c")]
        registry = _make_registry(tools=tools)
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert len(adapter.get_tools()) == 3

    def test_get_tools_on_failure_returns_empty(self):
        """If list_tools fails, get_tools returns empty list."""
        registry = _make_registry()
        registry.list_tools.side_effect = RuntimeError("server down")
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter.get_tools() == []

# ---------------------------------------------------------------------------
# TestCapabilities
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCapabilities:
    """Agent capabilities and feature flags."""

    def test_supports_streaming_false(self):
        """MCP adapters never support streaming."""
        registry = _make_registry()
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter.supports_streaming() is False

    def test_capabilities_basic(self):
        """capabilities() returns AgentCapabilities with MCP settings."""
        registry = _make_registry()
        adapter = MCPAgentAdapter("test-server", registry=registry)

        caps = adapter.capabilities()

        assert isinstance(caps, AgentCapabilities)
        assert caps.supports_streaming is False
        assert caps.max_retries == 3
        assert caps.timeout_seconds == 60
        assert caps.framework_specific["mcp_server"] == "test-server"

    def test_get_memory_returns_none(self):
        """MCP servers have no memory."""
        registry = _make_registry()
        adapter = MCPAgentAdapter("test-server", registry=registry)

        assert adapter.get_memory() is None

# ---------------------------------------------------------------------------
# TestFactoryFunction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFactoryFunction:
    """create_mcp_agent() factory function."""

    def test_factory_creates_adapter(self):
        """Factory returns an MCPAgentAdapter instance."""
        registry = _make_registry("mem-server")
        adapter = create_mcp_agent("mem-server", registry=registry)

        assert isinstance(adapter, MCPAgentAdapter)
        assert adapter.server_name == "mem-server"

    def test_factory_passes_description(self):
        """Factory passes description to adapter."""
        registry = _make_registry("mem-server")
        adapter = create_mcp_agent("mem-server", registry=registry, description="My desc")

        assert adapter._description == "My desc"

    def test_factory_passes_version(self):
        """Factory passes version to adapter."""
        registry = _make_registry("mem-server")
        adapter = create_mcp_agent("mem-server", registry=registry, version="3.0.0")

        assert adapter._version == "3.0.0"

    def test_factory_unregistered_server_raises(self):
        """Factory raises when server is not registered."""
        registry = MagicMock()
        registry.get_config.side_effect = MCPRegistryError("not registered")

        with pytest.raises(MCPRegistryError):
            create_mcp_agent("missing", registry=registry)

# ---------------------------------------------------------------------------
# TestListResources and TestListPrompts
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestListResources:
    """list_resources() async method."""

    @pytest.mark.asyncio
    async def test_list_resources_success(self):
        """Returns resource list from registry."""
        registry = _make_registry()
        resource = MagicMock()
        resource.uri = "file:///tmp/test"
        resource.name = "test file"
        resource.description = "A test file"
        registry.list_resources = AsyncMock(return_value=[resource])

        adapter = MCPAgentAdapter("test-server", registry=registry)
        resources = await adapter.list_resources()

        assert len(resources) == 1
        assert resources[0]["uri"] == "file:///tmp/test"
        assert resources[0]["name"] == "test file"

    @pytest.mark.asyncio
    async def test_list_resources_failure_returns_empty(self):
        """If list_resources fails, returns empty list."""
        registry = _make_registry()
        registry.list_resources = AsyncMock(side_effect=RuntimeError("no resources"))
        adapter = MCPAgentAdapter("test-server", registry=registry)

        resources = await adapter.list_resources()
        assert resources == []

@pytest.mark.unit
class TestListPrompts:
    """list_prompts() async method."""

    @pytest.mark.asyncio
    async def test_list_prompts_success(self):
        """Returns prompt list from registry."""
        registry = _make_registry()
        prompt = MagicMock()
        prompt.name = "summarize"
        prompt.description = "Summarize text"
        registry.list_prompts = AsyncMock(return_value=[prompt])

        adapter = MCPAgentAdapter("test-server", registry=registry)
        prompts = await adapter.list_prompts()

        assert len(prompts) == 1
        assert prompts[0]["name"] == "summarize"

    @pytest.mark.asyncio
    async def test_list_prompts_failure_returns_empty(self):
        """If list_prompts fails, returns empty list."""
        registry = _make_registry()
        registry.list_prompts = AsyncMock(side_effect=RuntimeError("no prompts"))
        adapter = MCPAgentAdapter("test-server", registry=registry)

        prompts = await adapter.list_prompts()
        assert prompts == []
