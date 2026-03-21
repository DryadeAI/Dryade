"""Tests for Research Assistant LangChain agent.

Tests cover:
- Agent card generation
- Web browsing tools (Playwright MCP)
- Memory tools (Knowledge graph)
- Filesystem tools (Reports)
- Error handling and graceful fallback
- Mock mode operation
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from agents.research_assistant import (
    ResearchAssistantAgent,
    create_research_assistant_agent,
)
from core.adapters.protocol import AgentFramework

class TestResearchAssistantAgent:
    """Test suite for ResearchAssistantAgent."""

    def test_create_agent_factory(self):
        """Test factory function creates LangChainAgentAdapter instance."""
        agent = create_research_assistant_agent()
        assert agent is not None
        # Factory returns LangChainAgentAdapter
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        assert isinstance(agent, LangChainAgentAdapter)

    def test_agent_card_framework(self):
        """Test agent card has LANGCHAIN framework."""
        agent = create_research_assistant_agent()
        card = agent.get_card()
        assert card.framework == AgentFramework.LANGCHAIN

    def test_agent_card_description(self):
        """Test agent card has meaningful description."""
        agent = create_research_assistant_agent()
        card = agent.get_card()
        assert "research" in card.description.lower()
        assert len(card.description) > 20  # Meaningful length

    def test_agent_card_name(self):
        """Test agent card has correct name."""
        agent = create_research_assistant_agent()
        card = agent.get_card()
        assert card.name == "research_assistant"

    def test_get_tools_returns_eight_tools(self):
        """Test get_tools returns 8 tools."""
        agent = create_research_assistant_agent()
        tools = agent.get_tools()
        assert len(tools) == 8

    def test_tools_include_playwright_tools(self):
        """Test tools include Playwright MCP tools."""
        agent = create_research_assistant_agent()
        tools = agent.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        assert "navigate_to_url" in tool_names
        assert "take_screenshot" in tool_names
        assert "click_element" in tool_names

    def test_tools_include_memory_tools(self):
        """Test tools include Memory MCP tools."""
        agent = create_research_assistant_agent()
        tools = agent.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        assert "store_research_finding" in tool_names
        assert "search_knowledge" in tool_names
        assert "link_findings" in tool_names

    def test_tools_include_filesystem_tools(self):
        """Test tools include Filesystem MCP tools."""
        agent = create_research_assistant_agent()
        tools = agent.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        assert "save_report" in tool_names
        assert "read_file" in tool_names

class TestWebBrowsingTools:
    """Test web browsing (Playwright) tools."""

    @pytest.fixture
    def mock_registry(self):
        """Mock MCP registry for tool calls."""
        with patch("core.mcp.tool_wrapper.get_registry") as mock:
            mock_result = MagicMock()
            mock_content = MagicMock()
            mock_content.type = "text"
            mock_content.text = "Success"
            mock_result.content = [mock_content]
            mock.return_value.call_tool.return_value = mock_result
            yield mock

    def test_navigate_to_url(self, mock_registry):
        """Test navigate_to_url calls playwright/playwright_navigate."""
        from agents.research_assistant import navigate_to_url

        result = navigate_to_url.invoke({"url": "https://example.com"})

        # Should have called playwright_navigate and playwright_snapshot
        calls = mock_registry.return_value.call_tool.call_args_list
        call_names = [c[0][1] for c in calls]  # Second positional arg is tool name
        assert "playwright_navigate" in call_names
        assert "Navigated to https://example.com" in result

    def test_take_screenshot(self, mock_registry):
        """Test take_screenshot calls playwright/playwright_screenshot."""
        from agents.research_assistant import take_screenshot

        result = take_screenshot.invoke({"name": "test_shot"})

        mock_registry.return_value.call_tool.assert_called_with(
            "playwright", "playwright_screenshot", {}
        )
        assert "test_shot" in result
        assert "captured" in result.lower() or "Success" in result

    def test_click_element(self, mock_registry):
        """Test click_element calls playwright/playwright_click."""
        from agents.research_assistant import click_element

        result = click_element.invoke({"selector": "button#submit"})

        mock_registry.return_value.call_tool.assert_called_with(
            "playwright", "playwright_click", {"selector": "button#submit"}
        )
        assert "button#submit" in result

class TestMemoryTools:
    """Test memory (knowledge graph) tools."""

    @pytest.fixture
    def mock_registry(self):
        """Mock MCP registry for tool calls."""
        with patch("core.mcp.tool_wrapper.get_registry") as mock:
            mock_result = MagicMock()
            mock_content = MagicMock()
            mock_content.type = "text"
            mock_content.text = "Created successfully"
            mock_result.content = [mock_content]
            mock.return_value.call_tool.return_value = mock_result
            yield mock

    def test_store_research_finding(self, mock_registry):
        """Test store_research_finding calls memory/create_entities with correct schema."""
        from agents.research_assistant import store_research_finding

        result = store_research_finding.invoke(
            {
                "entity_name": "AI Trends 2026",
                "entity_type": "finding",
                "observations": ["LLMs are improving", "Agents are popular"],
            }
        )

        mock_registry.return_value.call_tool.assert_called_once()
        call_args = mock_registry.return_value.call_tool.call_args

        assert call_args[0][0] == "memory"  # server
        assert call_args[0][1] == "create_entities"  # tool
        assert "entities" in call_args[0][2]  # kwargs

        entity = call_args[0][2]["entities"][0]
        assert entity["name"] == "AI Trends 2026"
        assert entity["entityType"] == "finding"
        assert len(entity["observations"]) == 2

    def test_search_knowledge(self, mock_registry):
        """Test search_knowledge calls memory/search_nodes with query."""
        from agents.research_assistant import search_knowledge

        result = search_knowledge.invoke({"query": "AI trends"})

        mock_registry.return_value.call_tool.assert_called_with(
            "memory", "search_nodes", {"query": "AI trends"}
        )
        assert "AI trends" in result

    def test_link_findings(self, mock_registry):
        """Test link_findings calls memory/create_relations."""
        from agents.research_assistant import link_findings

        result = link_findings.invoke(
            {
                "source": "Finding A",
                "target": "Finding B",
                "relation_type": "supports",
            }
        )

        mock_registry.return_value.call_tool.assert_called_once()
        call_args = mock_registry.return_value.call_tool.call_args

        assert call_args[0][0] == "memory"
        assert call_args[0][1] == "create_relations"

        relation = call_args[0][2]["relations"][0]
        assert relation["from"] == "Finding A"
        assert relation["to"] == "Finding B"
        assert relation["relationType"] == "supports"

class TestFilesystemTools:
    """Test filesystem tools."""

    @pytest.fixture
    def mock_registry(self):
        """Mock MCP registry for tool calls."""
        with patch("core.mcp.tool_wrapper.get_registry") as mock:
            mock_result = MagicMock()
            mock_content = MagicMock()
            mock_content.type = "text"
            mock_content.text = "File content here"
            mock_result.content = [mock_content]
            mock.return_value.call_tool.return_value = mock_result
            yield mock

    def test_save_report(self, mock_registry):
        """Test save_report calls filesystem/write_file with path and content."""
        from agents.research_assistant import save_report

        result = save_report.invoke(
            {
                "path": "/tmp/test_report.md",
                "content": "# Research Report\n\nFindings here.",
            }
        )

        mock_registry.return_value.call_tool.assert_called_with(
            "filesystem",
            "write_file",
            {"path": "/tmp/test_report.md", "content": "# Research Report\n\nFindings here."},
        )
        assert "/tmp/test_report.md" in result

    def test_read_file(self, mock_registry):
        """Test read_file calls filesystem/read_file with path."""
        from agents.research_assistant import read_file

        result = read_file.invoke({"path": "/tmp/existing_file.txt"})

        mock_registry.return_value.call_tool.assert_called_with(
            "filesystem", "read_file", {"path": "/tmp/existing_file.txt"}
        )
        assert "File content here" in result or "/tmp/existing_file.txt" in result

class TestIntegrationBehavior:
    """Test integration workflows."""

    @pytest.fixture
    def agent(self):
        """Create agent fixture."""
        return ResearchAssistantAgent()

    @pytest.mark.asyncio
    async def test_research_workflow_mock(self, agent):
        """Test research -> store -> report flow with mocked tools."""
        with patch("core.mcp.tool_wrapper.get_registry") as mock_registry:
            # Mock all MCP calls to succeed
            mock_result = MagicMock()
            mock_content = MagicMock()
            mock_content.type = "text"
            mock_content.text = '{"entities": [{"name": "test"}]}'
            mock_result.content = [mock_content]
            mock_registry.return_value.call_tool.return_value = mock_result

            # Execute search task
            result = await agent.execute(
                "Search for AI research findings", context={"query": "AI trends"}
            )

            assert result.status == "ok"
            assert result.result is not None

    @pytest.mark.asyncio
    async def test_error_handling_playwright_unavailable(self, agent):
        """Test graceful handling when Playwright fails.

        Tools catch exceptions and return error messages in the result string.
        This is graceful fallback - the agent continues and includes error info.
        """
        with patch("core.mcp.tool_wrapper.get_registry") as mock_registry:
            # Make Playwright calls fail
            def side_effect(server, tool, kwargs):
                if server == "playwright":
                    raise Exception("Playwright server not available")
                # Memory calls succeed
                mock_result = MagicMock()
                mock_content = MagicMock()
                mock_content.type = "text"
                mock_content.text = "cached data"
                mock_result.content = [mock_content]
                return mock_result

            mock_registry.return_value.call_tool.side_effect = side_effect

            # Execute task that would use Playwright
            result = await agent.execute(
                "Browse to https://example.com", context={"url": "https://example.com"}
            )

            # Tools catch exceptions and return error in result string (graceful fallback)
            # Status is 'ok' because the agent executed, but result contains error info
            assert result.status == "ok"
            assert "Failed" in result.result or "not available" in result.result

    @pytest.mark.asyncio
    async def test_error_handling_memory_unavailable(self, agent):
        """Test agent handles Memory failure gracefully.

        When Memory MCP is unavailable, tools return error messages in the
        result string rather than raising exceptions.
        """
        with patch("core.mcp.tool_wrapper.get_registry") as mock_registry:
            # Make all calls fail
            mock_registry.return_value.call_tool.side_effect = Exception(
                "Memory server not available"
            )

            # Execute search task
            result = await agent.execute("Search for findings")

            # Graceful handling: status is 'ok' but result contains error info
            assert result.status == "ok"
            assert "Failed" in result.result or "not available" in result.result

    @pytest.mark.asyncio
    async def test_execute_with_fallback_on_all_failures(self, agent):
        """Test execute_with_fallback handles complete failure gracefully."""
        # Patch at module level to affect both primary and cache lookup
        with patch.object(agent, "_execute_primary") as mock_primary:
            with patch.object(agent, "_get_cached_result") as mock_cache:
                # Both primary and cache fail
                mock_primary.side_effect = Exception("Primary execution failed")
                mock_cache.return_value = None  # No cache

                # Execute with fallback
                result = await agent.execute_with_fallback("Test research task")

                # Should get error result with graceful message
                assert result.status == "error"
                assert "failed" in result.error.lower()
                assert result.metadata.get("recoverable") is True

    @pytest.mark.asyncio
    async def test_execute_with_fallback_uses_cache(self, agent):
        """Test execute_with_fallback uses cache when primary fails."""
        with patch.object(agent, "_execute_primary") as mock_primary:
            with patch.object(agent, "_get_cached_result") as mock_cache:
                # Primary fails
                mock_primary.side_effect = Exception("Primary execution failed")
                # Cache succeeds
                mock_cache.return_value = "[Cached] Previous research findings..."

                # Execute with fallback
                result = await agent.execute_with_fallback("Test research task")

                # Should get partial result from cache
                assert result.status == "partial"
                assert "cached" in result.result.lower()
                assert result.metadata.get("cached") is True

class TestMockMode:
    """Test mock mode operation."""

    def test_mock_mode_for_tools(self):
        """Test tools respect DRYADE_MOCK_MODE."""
        from agents.research_assistant import navigate_to_url

        with patch.dict(os.environ, {"DRYADE_MOCK_MODE": "true"}):
            result = navigate_to_url.invoke({"url": "https://test.com"})

            # Mock mode returns JSON with mock: true
            # The result should contain mock data
            assert "mock" in result.lower() or "test.com" in result

class TestAgentConfig:
    """Test configuration loading."""

    def test_default_config_values(self):
        """Test agent uses default config when YAML not found."""
        agent = ResearchAssistantAgent(config={})
        assert agent.name == "research_assistant"

    def test_custom_config_override(self):
        """Test custom config overrides defaults."""
        custom_config = {
            "name": "custom_research",
            "description": "Custom research agent",
        }
        agent = ResearchAssistantAgent(config=custom_config)
        assert agent.name == "custom_research"
        assert agent.description == "Custom research agent"

    def test_config_file_loaded(self):
        """Test config.yaml is loaded when present."""
        agent = ResearchAssistantAgent()
        # Should have loaded from config.yaml
        assert agent.name == "research_assistant"
        assert "research" in agent.description.lower()

class TestToolSchemas:
    """Test tool schemas are correctly defined."""

    def test_navigate_to_url_schema(self):
        """Test navigate_to_url has correct parameter schema."""
        from agents.research_assistant import navigate_to_url

        # LangChain tools have args_schema
        schema = navigate_to_url.args_schema
        assert schema is not None
        schema_dict = schema.model_json_schema()
        assert "url" in schema_dict.get("properties", {})

    def test_store_research_finding_schema(self):
        """Test store_research_finding has correct parameter schema."""
        from agents.research_assistant import store_research_finding

        schema = store_research_finding.args_schema
        assert schema is not None
        schema_dict = schema.model_json_schema()
        props = schema_dict.get("properties", {})
        assert "entity_name" in props
        assert "entity_type" in props
        assert "observations" in props

    def test_link_findings_schema(self):
        """Test link_findings has correct parameter schema."""
        from agents.research_assistant import link_findings

        schema = link_findings.args_schema
        assert schema is not None
        schema_dict = schema.model_json_schema()
        props = schema_dict.get("properties", {})
        assert "source" in props
        assert "target" in props
        assert "relation_type" in props
