"""Integration tests for developer productivity MCP servers.

Tests verify:
1. All 4 servers can be registered together
2. MCPAgentAdapter works for each server
3. Agent cards have correct metadata
4. Tools are in correct format for routing
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.adapters.protocol import AgentFramework
from core.mcp import MCPRegistry
from core.mcp.adapter import SERVER_DESCRIPTIONS, create_mcp_agent
from core.mcp.config import MCPServerTransport
from core.mcp.servers.context7 import Context7Server, create_context7_server
from core.mcp.servers.github import GitHubServer, create_github_server
from core.mcp.servers.linear import LinearServer, create_linear_server
from core.mcp.servers.playwright import PlaywrightServer, create_playwright_server

# ============================================================================
# Multi-Server Registry Tests
# ============================================================================

class TestMultiServerRegistry:
    """Tests for registering multiple servers."""

    def test_all_servers_register_without_conflict(self):
        """Test all 4 developer servers can be registered together."""
        registry = MCPRegistry()

        create_github_server(registry)
        create_context7_server(registry)
        create_playwright_server(registry)
        create_linear_server(registry)

        servers = list(registry.list_servers())
        assert len(servers) == 4
        assert set(servers) == {"github", "context7", "playwright", "linear"}

    def test_servers_have_unique_names(self):
        """Test each server has a unique name in registry."""
        registry = MCPRegistry()

        create_github_server(registry)
        create_context7_server(registry)
        create_playwright_server(registry)
        create_linear_server(registry)

        assert registry.get_config("github").name == "github"
        assert registry.get_config("context7").name == "context7"
        assert registry.get_config("playwright").name == "playwright"
        assert registry.get_config("linear").name == "linear"

    def test_servers_have_correct_transport_types(self):
        """Test servers have their expected transport types."""
        registry = MCPRegistry()

        create_github_server(registry)
        create_context7_server(registry)
        create_playwright_server(registry)
        create_linear_server(registry)

        # GitHub defaults to STDIO
        assert registry.get_config("github").transport == MCPServerTransport.STDIO
        # Context7 uses HTTP
        assert registry.get_config("context7").transport == MCPServerTransport.HTTP
        # Playwright uses STDIO
        assert registry.get_config("playwright").transport == MCPServerTransport.STDIO
        # Linear uses STDIO
        assert registry.get_config("linear").transport == MCPServerTransport.STDIO

    def test_http_github_server(self):
        """Test GitHub server can be created with HTTP transport."""
        registry = MCPRegistry()

        create_github_server(registry, use_http=True)

        config = registry.get_config("github")
        assert config.transport == MCPServerTransport.HTTP

# ============================================================================
# MCPAgentAdapter Integration Tests
# ============================================================================

class TestMCPAgentAdapterIntegration:
    """Tests for MCPAgentAdapter with developer servers."""

    @pytest.fixture
    def registry_with_servers(self):
        """Create registry with all 4 developer servers."""
        registry = MCPRegistry()
        create_github_server(registry)
        create_context7_server(registry)
        create_playwright_server(registry)
        create_linear_server(registry)
        # Mock list_tools to avoid actual server connections
        registry.list_tools = MagicMock(return_value=[])
        return registry

    def test_create_adapter_for_each_server(self, registry_with_servers):
        """Test adapter can be created for each server."""
        for server_name in ["github", "context7", "playwright", "linear"]:
            adapter = create_mcp_agent(server_name, registry=registry_with_servers)
            assert adapter is not None
            assert adapter._server_name == server_name

    def test_adapters_track_correct_transport(self, registry_with_servers):
        """Test adapters track the correct transport type."""
        github_adapter = create_mcp_agent("github", registry=registry_with_servers)
        context7_adapter = create_mcp_agent("context7", registry=registry_with_servers)
        playwright_adapter = create_mcp_agent("playwright", registry=registry_with_servers)
        linear_adapter = create_mcp_agent("linear", registry=registry_with_servers)

        assert github_adapter._transport_type == "stdio"
        assert context7_adapter._transport_type == "http"
        assert playwright_adapter._transport_type == "stdio"
        assert linear_adapter._transport_type == "stdio"

    def test_github_agent_card_metadata(self, registry_with_servers):
        """Test GitHub adapter has correct card metadata."""
        adapter = create_mcp_agent("github", registry=registry_with_servers)
        card = adapter.get_card()

        assert card.name == "mcp-github"
        assert "GitHub" in card.description
        assert card.framework == AgentFramework.MCP
        assert card.metadata["mcp_server"] == "github"
        assert card.metadata["transport"] == "stdio"

    def test_context7_agent_card_metadata(self, registry_with_servers):
        """Test Context7 adapter has correct card metadata."""
        adapter = create_mcp_agent("context7", registry=registry_with_servers)
        card = adapter.get_card()

        assert card.name == "mcp-context7"
        assert "documentation" in card.description.lower()
        assert card.framework == AgentFramework.MCP
        assert card.metadata["mcp_server"] == "context7"
        assert card.metadata["transport"] == "http"

    def test_playwright_agent_card_metadata(self, registry_with_servers):
        """Test Playwright adapter has correct card metadata."""
        adapter = create_mcp_agent("playwright", registry=registry_with_servers)
        card = adapter.get_card()

        assert card.name == "mcp-playwright"
        assert "browser" in card.description.lower()
        assert card.framework == AgentFramework.MCP
        assert card.metadata["mcp_server"] == "playwright"

    def test_linear_agent_card_metadata(self, registry_with_servers):
        """Test Linear adapter has correct card metadata."""
        adapter = create_mcp_agent("linear", registry=registry_with_servers)
        card = adapter.get_card()

        assert card.name == "mcp-linear"
        assert "issue" in card.description.lower()
        assert card.framework == AgentFramework.MCP
        assert card.metadata["mcp_server"] == "linear"

# ============================================================================
# Server Descriptions Tests
# ============================================================================

class TestServerDescriptions:
    """Tests for server-specific descriptions."""

    def test_all_developer_servers_have_descriptions(self):
        """Test all 4 developer servers have descriptions."""
        assert "github" in SERVER_DESCRIPTIONS
        assert "context7" in SERVER_DESCRIPTIONS
        assert "playwright" in SERVER_DESCRIPTIONS
        assert "linear" in SERVER_DESCRIPTIONS

    def test_github_description_contains_keywords(self):
        """Test GitHub description contains relevant keywords."""
        desc = SERVER_DESCRIPTIONS["github"]
        assert "GitHub" in desc
        # Should mention repos, issues, PRs, or code
        assert any(
            word in desc.lower() for word in ["repositories", "issues", "pull requests", "code"]
        )

    def test_context7_description_contains_keywords(self):
        """Test Context7 description contains relevant keywords."""
        desc = SERVER_DESCRIPTIONS["context7"]
        assert any(word in desc.lower() for word in ["documentation", "library", "api"])

    def test_playwright_description_contains_keywords(self):
        """Test Playwright description contains relevant keywords."""
        desc = SERVER_DESCRIPTIONS["playwright"]
        assert any(word in desc.lower() for word in ["browser", "automation", "testing"])

    def test_linear_description_contains_keywords(self):
        """Test Linear description contains relevant keywords."""
        desc = SERVER_DESCRIPTIONS["linear"]
        assert any(word in desc.lower() for word in ["issue", "project", "linear"])

# ============================================================================
# Tool Format Tests
# ============================================================================

class TestToolFormatting:
    """Tests for tool format compatibility."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock MCP tools."""
        mock_tool = MagicMock()
        mock_tool.name = "list_repos"
        mock_tool.description = "List repositories"
        mock_tool.inputSchema = MagicMock()
        mock_tool.inputSchema.type = "object"
        mock_tool.inputSchema.properties = {"owner": {"type": "string"}}
        mock_tool.inputSchema.required = ["owner"]
        return [mock_tool]

    def test_tools_in_openai_format(self, mock_tools):
        """Test tools are converted to OpenAI format correctly."""
        registry = MCPRegistry()
        create_github_server(registry)

        # Mock list_tools to return our mock tools
        registry.list_tools = MagicMock(return_value=mock_tools)

        adapter = create_mcp_agent("github", registry=registry)
        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "list_repos"
        assert tools[0]["function"]["description"] == "List repositories"
        assert tools[0]["function"]["parameters"]["type"] == "object"

    def test_tools_parameters_have_required_fields(self, mock_tools):
        """Test tool parameters include required field."""
        registry = MCPRegistry()
        create_github_server(registry)
        registry.list_tools = MagicMock(return_value=mock_tools)

        adapter = create_mcp_agent("github", registry=registry)
        tools = adapter.get_tools()

        params = tools[0]["function"]["parameters"]
        assert "required" in params
        assert params["required"] == ["owner"]

# ============================================================================
# Agent Discovery Tests
# ============================================================================

class TestAgentDiscovery:
    """Tests for agent discovery capabilities."""

    @pytest.fixture
    def registry_with_servers(self):
        """Create registry with all 4 developer servers."""
        registry = MCPRegistry()
        create_github_server(registry)
        create_context7_server(registry)
        create_playwright_server(registry)
        create_linear_server(registry)
        # Mock list_tools to avoid actual server connections
        registry.list_tools = MagicMock(return_value=[])
        return registry

    def test_all_adapters_have_mcp_framework(self, registry_with_servers):
        """Test all adapters report MCP framework."""
        for server_name in ["github", "context7", "playwright", "linear"]:
            adapter = create_mcp_agent(server_name, registry=registry_with_servers)
            card = adapter.get_card()
            assert card.framework == AgentFramework.MCP

    def test_all_adapters_have_unique_card_names(self, registry_with_servers):
        """Test all adapters have unique card names."""
        card_names = set()
        for server_name in ["github", "context7", "playwright", "linear"]:
            adapter = create_mcp_agent(server_name, registry=registry_with_servers)
            card = adapter.get_card()
            assert card.name not in card_names
            card_names.add(card.name)

        assert len(card_names) == 4

    def test_adapter_names_are_namespaced(self, registry_with_servers):
        """Test adapter card names are prefixed with 'mcp-'."""
        for server_name in ["github", "context7", "playwright", "linear"]:
            adapter = create_mcp_agent(server_name, registry=registry_with_servers)
            card = adapter.get_card()
            assert card.name.startswith("mcp-")
            assert card.name == f"mcp-{server_name}"

# ============================================================================
# Server Wrapper Factory Tests
# ============================================================================

class TestServerWrapperFactories:
    """Tests for server wrapper factory functions."""

    def test_github_factory_returns_server(self):
        """Test create_github_server returns GitHubServer."""
        registry = MCPRegistry()
        server = create_github_server(registry)
        assert isinstance(server, GitHubServer)

    def test_context7_factory_returns_server(self):
        """Test create_context7_server returns Context7Server."""
        registry = MCPRegistry()
        server = create_context7_server(registry)
        assert isinstance(server, Context7Server)

    def test_playwright_factory_returns_server(self):
        """Test create_playwright_server returns PlaywrightServer."""
        registry = MCPRegistry()
        server = create_playwright_server(registry)
        assert isinstance(server, PlaywrightServer)

    def test_linear_factory_returns_server(self):
        """Test create_linear_server returns LinearServer."""
        registry = MCPRegistry()
        server = create_linear_server(registry)
        assert isinstance(server, LinearServer)

    def test_factory_auto_register_default(self):
        """Test factories auto-register by default."""
        registry = MCPRegistry()

        create_github_server(registry)
        assert registry.is_registered("github")

    def test_factory_auto_register_false(self):
        """Test factories can skip auto-registration."""
        registry = MCPRegistry()

        # Register first to have config available
        registry.register(GitHubServer.get_stdio_config())

        # Create without auto-register (should not error since already registered)
        server = create_github_server(registry, auto_register=False)
        assert server is not None

    def test_factory_does_not_duplicate_registration(self):
        """Test factory doesn't register if already registered."""
        registry = MCPRegistry()

        # First call registers
        create_github_server(registry)
        assert registry.is_registered("github")

        # Second call should not error (skips duplicate)
        create_github_server(registry)
        assert registry.is_registered("github")
