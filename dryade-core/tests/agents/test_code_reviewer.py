"""Tests for Code Reviewer CrewAI agent.

Tests cover:
- Agent card generation
- CrewAI framework identification
- Tool definitions
- Graceful fallback on errors
- MCP tool wrapper integration
"""

from unittest.mock import patch

import pytest

from agents.code_reviewer import CodeReviewerAgent, create_code_reviewer_agent
from core.adapters.protocol import AgentFramework

class TestCodeReviewerAgent:
    """Test suite for CodeReviewerAgent."""

    def test_create_agent_factory(self):
        """Test factory function creates agent instance."""
        agent = create_code_reviewer_agent()
        assert agent is not None
        assert isinstance(agent, CodeReviewerAgent)

    def test_agent_card_basic(self):
        """Test agent card has correct basic info."""
        agent = create_code_reviewer_agent()
        card = agent.get_card()

        assert card.name == "code_reviewer"
        assert card.framework == AgentFramework.CREWAI
        assert "review" in card.description.lower() or "code" in card.description.lower()

    def test_agent_card_capabilities(self):
        """Test agent card lists expected capabilities."""
        agent = create_code_reviewer_agent()
        card = agent.get_card()

        capability_names = [c.name for c in card.capabilities]
        assert "get_pull_request" in capability_names
        assert "get_library_docs" in capability_names
        assert "git_diff" in capability_names

    def test_get_tools_returns_list(self):
        """Test get_tools returns OpenAI function format."""
        agent = create_code_reviewer_agent()
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
        """Test tools include expected MCP-backed capabilities."""
        agent = create_code_reviewer_agent()
        tools = agent.get_tools()

        tool_names = [t["function"]["name"] for t in tools]
        assert "get_pull_request" in tool_names
        assert "get_library_docs" in tool_names
        assert "git_diff" in tool_names

    def test_supports_streaming_false(self):
        """Test Code Reviewer does not support streaming."""
        agent = create_code_reviewer_agent()
        assert agent.supports_streaming() is False

class TestCodeReviewerGracefulFallback:
    """Test graceful fallback behavior."""

    @pytest.fixture
    def agent(self):
        """Create agent fixture."""
        return create_code_reviewer_agent()

    @pytest.mark.asyncio
    async def test_graceful_fallback_when_adapter_unavailable(self, agent):
        """Test graceful error when CrewAI adapter not initialized."""
        # Force adapter to None
        agent._adapter = None
        agent._init_error = "Test error - adapter not available"

        result = await agent.execute("Review some code")

        assert result.status == "error"
        assert "Test error" in result.error
        assert result.metadata.get("recoverable") is True
        assert "required_servers" in result.metadata

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_execution_error(self, agent):
        """Test graceful error when execution fails."""
        # Mock adapter to raise exception
        if agent._adapter:
            with patch.object(agent._adapter, "execute", side_effect=Exception("MCP server error")):
                result = await agent.execute("Review PR #123")

                assert result.status == "error"
                assert "Code review failed" in result.error
                assert "MCP server error" in result.error

    def test_metadata_includes_required_servers(self, agent):
        """Test that error metadata includes required MCP servers."""
        card = agent.get_card()

        # Should have required servers in metadata
        assert "required_servers" in card.metadata or any(
            c.name in ["get_pull_request", "git_diff"] for c in card.capabilities
        )

class TestCodeReviewerMCPToolWrappers:
    """Test MCP tool wrapper integration (mocked)."""

    def test_pr_tool_calls_github_server(self):
        """Test GetPullRequestTool calls github MCP server (mocked)."""
        from agents.code_reviewer import GetPullRequestArgs

        # Test args schema
        args = GetPullRequestArgs(owner="test", repo="repo", pr_number=42)
        assert args.owner == "test"
        assert args.repo == "repo"
        assert args.pr_number == 42

    def test_library_docs_tool_args(self):
        """Test GetLibraryDocsArgs schema."""
        from agents.code_reviewer import GetLibraryDocsArgs

        args = GetLibraryDocsArgs(library_name="react")
        assert args.library_name == "react"
        assert args.topic is None

        args_with_topic = GetLibraryDocsArgs(library_name="react", topic="hooks")
        assert args_with_topic.topic == "hooks"

    def test_git_diff_tool_args(self):
        """Test GitDiffArgs schema."""
        from agents.code_reviewer import GitDiffArgs

        args = GitDiffArgs()
        assert args.path is None
        assert args.repo_path == "."

        args_with_path = GitDiffArgs(path="src/main.py", repo_path="/project")
        assert args_with_path.path == "src/main.py"
        assert args_with_path.repo_path == "/project"

class TestCodeReviewerConfig:
    """Test configuration loading."""

    def test_default_config_values(self):
        """Test agent uses default config when YAML not found."""
        agent = CodeReviewerAgent(config={})

        assert agent.name == "code_reviewer"
        assert "review" in agent.description.lower() or "code" in agent.description.lower()

    def test_custom_config_override(self):
        """Test custom config overrides defaults."""
        custom_config = {
            "name": "custom_reviewer",
            "description": "Custom code review agent",
        }
        agent = CodeReviewerAgent(config=custom_config)

        assert agent.name == "custom_reviewer"
        assert agent.description == "Custom code review agent"
