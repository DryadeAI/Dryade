"""Tests for DevOps Engineer MCP-native agent.

Tests cover:
- Agent card generation
- Task routing to MCP tools
- Error handling for unknown tasks
- Mock mode operation
- Tracing integration
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from agents.devops_engineer import DevOpsEngineerAgent, create_devops_engineer_agent
from core.adapters.protocol import AgentFramework

class TestDevOpsEngineerAgent:
    """Test suite for DevOpsEngineerAgent."""

    def test_create_agent_factory(self):
        """Test factory function creates agent instance."""
        agent = create_devops_engineer_agent()
        assert agent is not None
        assert isinstance(agent, DevOpsEngineerAgent)

    def test_agent_card_basic(self):
        """Test agent card has correct basic info."""
        agent = create_devops_engineer_agent()
        card = agent.get_card()

        assert card.name == "devops_engineer"
        assert card.framework == AgentFramework.MCP
        assert "DevOps" in card.description or "devops" in card.description.lower()
        assert card.version == "1.0.0"

    def test_agent_card_capabilities(self):
        """Test agent card lists expected capabilities."""
        agent = create_devops_engineer_agent()
        card = agent.get_card()

        capability_names = [c.name for c in card.capabilities]
        assert "git_operations" in capability_names
        assert "file_operations" in capability_names
        assert "github_operations" in capability_names

    def test_agent_card_metadata(self):
        """Test agent card has required server metadata."""
        agent = create_devops_engineer_agent()
        card = agent.get_card()

        assert "required_servers" in card.metadata
        assert "git" in card.metadata["required_servers"]
        assert "filesystem" in card.metadata["required_servers"]

    def test_get_tools_returns_list(self):
        """Test get_tools returns OpenAI function format."""
        agent = create_devops_engineer_agent()
        tools = agent.get_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0

        # Check first tool has correct structure
        tool = tools[0]
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]

    def test_tools_include_expected_names(self):
        """Test tools include expected MCP tool wrappers."""
        agent = create_devops_engineer_agent()
        tools = agent.get_tools()

        tool_names = [t["function"]["name"] for t in tools]
        assert "git_status" in tool_names
        assert "git_diff" in tool_names
        assert "read_file" in tool_names

class TestDevOpsAgentTaskRouting:
    """Test task routing to MCP tools."""

    @pytest.fixture
    def agent(self):
        """Create agent fixture."""
        return create_devops_engineer_agent()

    @pytest.mark.asyncio
    async def test_route_git_status(self, agent):
        """Test git status task routing."""
        with patch.object(agent._tools["git_status"], "call") as mock_call:
            mock_call.return_value = "On branch main\nnothing to commit"

            result = await agent.execute("Check git status")

            assert result.status == "ok"
            assert "branch main" in result.result
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_git_diff(self, agent):
        """Test git diff task routing."""
        with patch.object(agent._tools["git_diff"], "call") as mock_call:
            mock_call.return_value = "diff --git a/file.py"

            result = await agent.execute("Show git diff")

            assert result.status == "ok"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_git_log(self, agent):
        """Test git log task routing."""
        with patch.object(agent._tools["git_log"], "call") as mock_call:
            mock_call.return_value = "commit abc123\nAuthor: Test"

            result = await agent.execute("Show commit history")

            assert result.status == "ok"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_read_file_with_context(self, agent):
        """Test file read with path in context."""
        with patch.object(agent._tools["read_file"], "call") as mock_call:
            mock_call.return_value = "file contents"

            result = await agent.execute("Read the file", context={"path": "/tmp/test.txt"})

            assert result.status == "ok"
            mock_call.assert_called_once_with(path="/tmp/test.txt")

    @pytest.mark.asyncio
    async def test_route_deploy_check(self, agent):
        """Test deployment check (multi-step)."""
        with patch.object(agent._tools["git_status"], "call") as mock_status:
            with patch.object(agent._tools["git_log"], "call") as mock_log:
                mock_status.return_value = "On branch main"
                mock_log.return_value = "commit abc123"

                result = await agent.execute("Check deploy status")

                assert result.status == "ok"
                assert "Git Status" in result.result
                assert "Recent Commits" in result.result
                mock_status.assert_called_once()
                mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_unknown_task(self, agent):
        """Test unknown task returns error."""
        result = await agent.execute("Do something completely unknown xyz")

        assert result.status == "error"
        assert result.error is not None
        assert "Unknown task" in result.error

class TestDevOpsAgentErrorHandling:
    """Test error handling in DevOps agent."""

    @pytest.fixture
    def agent(self):
        """Create agent fixture."""
        return create_devops_engineer_agent()

    @pytest.mark.asyncio
    async def test_mcp_call_error(self, agent):
        """Test error handling when MCP call fails."""
        with patch.object(agent._tools["git_status"], "call") as mock_call:
            mock_call.side_effect = Exception("MCP server not available")

            result = await agent.execute("Check git status")

            assert result.status == "error"
            assert "MCP server not available" in result.error

    @pytest.mark.asyncio
    async def test_github_without_credentials(self, agent):
        """Test GitHub operation without owner/repo."""
        result = await agent.execute("Check GitHub PRs")

        assert result.status == "error"
        assert "owner" in result.error.lower() or "repo" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_file_without_path(self, agent):
        """Test file read without path raises error."""
        result = await agent.execute("Read the file")

        assert result.status == "error"
        assert "path" in result.error.lower()

class TestDevOpsAgentMockMode:
    """Test mock mode operation."""

    @pytest.fixture
    def agent(self):
        """Create agent fixture."""
        return create_devops_engineer_agent()

    def test_mock_mode_off_by_default(self, agent):
        """Test mock mode is off by default."""
        # Check one of the tool wrappers
        assert agent._tools["git_status"]._mock_mode is False

    def test_mock_mode_from_env(self, agent):
        """Test mock mode enabled via environment."""
        with patch.dict(os.environ, {"DRYADE_MOCK_MODE": "true"}):
            # Need to re-check since property reads env each time
            assert agent._tools["git_status"]._mock_mode is True

    @pytest.mark.asyncio
    async def test_mock_mode_returns_mock_response(self, agent):
        """Test mock mode returns mock data structure."""
        with patch.dict(os.environ, {"DRYADE_MOCK_MODE": "true"}):
            result = await agent.execute("Check git status")

            assert result.status == "ok"
            # Mock response should be JSON with mock: true
            data = json.loads(result.result)
            assert data["mock"] is True
            assert data["server"] == "git"
            assert data["tool"] == "git_status"

class TestDevOpsAgentTracing:
    """Test tracing integration."""

    def test_wrapper_traces_on_success(self):
        """Test MCPToolWrapper calls trace_event on successful call."""
        from core.mcp.tool_wrapper import MCPToolWrapper

        wrapper = MCPToolWrapper("git", "git_status", "Test")

        with patch("core.mcp.tool_wrapper.trace_event") as mock_trace:
            with patch("core.mcp.tool_wrapper.get_registry") as mock_registry:
                # Mock registry response
                mock_result = MagicMock()
                mock_content = MagicMock()
                mock_content.type = "text"
                mock_content.text = "On branch main"
                mock_result.content = [mock_content]
                mock_registry.return_value.call_tool.return_value = mock_result

                wrapper.call(repo_path=".")

                # trace_event should be called for start and complete
                assert mock_trace.call_count == 2

                # Check start event
                start_call = mock_trace.call_args_list[0]
                assert start_call[0][0] == "mcp_tool_start"

                # Check complete event
                complete_call = mock_trace.call_args_list[1]
                assert complete_call[0][0] == "mcp_tool_complete"
                assert complete_call[1]["status"] == "ok"

    def test_wrapper_traces_on_error(self):
        """Test MCPToolWrapper calls trace_event on error."""
        from core.mcp.tool_wrapper import MCPToolWrapper

        wrapper = MCPToolWrapper("git", "git_status", "Test")

        with patch("core.mcp.tool_wrapper.trace_event") as mock_trace:
            with patch("core.mcp.tool_wrapper.get_registry") as mock_registry:
                # Mock registry to raise error
                mock_registry.return_value.call_tool.side_effect = Exception("MCP error")

                with pytest.raises(Exception, match="MCP error"):
                    wrapper.call(repo_path=".")

                # trace_event should be called for start and complete (with error)
                assert mock_trace.call_count == 2

                # Check error status in complete event
                complete_call = mock_trace.call_args_list[1]
                assert complete_call[0][0] == "mcp_tool_complete"
                assert complete_call[1]["status"] == "error"

    def test_wrapper_traces_mock_mode(self):
        """Test MCPToolWrapper traces in mock mode."""
        from core.mcp.tool_wrapper import MCPToolWrapper

        wrapper = MCPToolWrapper("git", "git_status", "Test")

        with patch("core.mcp.tool_wrapper.trace_event") as mock_trace:
            with patch.dict(os.environ, {"DRYADE_MOCK_MODE": "true"}):
                wrapper.call(repo_path=".")

                # trace_event should be called for start and complete
                assert mock_trace.call_count == 2

                # Check mock flag in start event data
                start_call = mock_trace.call_args_list[0]
                assert start_call[1]["data"]["mock_mode"] is True

class TestDevOpsAgentConfig:
    """Test configuration loading."""

    def test_default_config_values(self):
        """Test agent uses default config when YAML not found."""
        agent = DevOpsEngineerAgent(config={})

        assert agent.name == "devops_engineer"
        assert agent.version == "1.0.0"

    def test_custom_config_override(self):
        """Test custom config overrides defaults."""
        custom_config = {
            "name": "custom_devops",
            "version": "2.0.0",
            "description": "Custom description",
        }
        agent = DevOpsEngineerAgent(config=custom_config)

        assert agent.name == "custom_devops"
        assert agent.version == "2.0.0"
        assert agent.description == "Custom description"

class TestMCPToolWrapper:
    """Test MCPToolWrapper directly."""

    def test_extract_mcp_text_helper(self):
        """Test extract_mcp_text helper function."""
        from core.mcp.tool_wrapper import extract_mcp_text

        # Create mock result
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.type = "text"
        mock_content.text = "Hello, World!"
        mock_result.content = [mock_content]

        text = extract_mcp_text(mock_result)
        assert text == "Hello, World!"

    def test_extract_mcp_text_empty(self):
        """Test extract_mcp_text with no text content."""
        from core.mcp.tool_wrapper import extract_mcp_text

        mock_result = MagicMock()
        mock_result.content = []

        text = extract_mcp_text(mock_result)
        assert text == ""

    def test_extract_mcp_text_none_result(self):
        """Test extract_mcp_text with None result."""
        from core.mcp.tool_wrapper import extract_mcp_text

        text = extract_mcp_text(None)
        assert text == ""

    def test_wrapper_repr(self):
        """Test MCPToolWrapper string representation."""
        from core.mcp.tool_wrapper import MCPToolWrapper

        wrapper = MCPToolWrapper("github", "get_repo", "Test")
        assert repr(wrapper) == "MCPToolWrapper('github', 'get_repo')"

class TestSetupWizard:
    """Test setup wizard helpers."""

    def test_get_setup_instructions_known_server(self):
        """Test getting instructions for known server."""
        from core.mcp.setup_wizard import get_setup_instructions

        instructions = get_setup_instructions("github")

        assert instructions["name"] == "GitHub"
        assert "GITHUB_TOKEN" in instructions["env_vars"]
        assert len(instructions["setup_steps"]) > 0

    def test_get_setup_instructions_unknown_server(self):
        """Test getting instructions for unknown server."""
        from core.mcp.setup_wizard import get_setup_instructions

        instructions = get_setup_instructions("unknown_server_xyz")

        assert instructions["name"] == "Unknown_Server_Xyz"
        assert instructions["env_vars"] == []

    def test_check_agent_setup_with_missing_servers(self):
        """Test setup check with unregistered servers."""
        from core.mcp.setup_wizard import check_agent_setup

        # Most servers won't be registered in test environment
        status = check_agent_setup("test_agent", ["nonexistent_server"])

        assert status["ready"] is False
        assert len(status["missing"]) > 0
        assert status["missing"][0]["reason"] == "not_registered"
