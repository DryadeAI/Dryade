"""Tests for Database Analyst LangChain agent.

Tests cover:
- Agent card generation
- LangChain framework identification
- SQL query safety validation
- Tool definitions
- Streaming support
- Graceful fallback on errors
"""

from unittest.mock import patch

import pytest

from agents.database_analyst import (
    DatabaseAnalystAgent,
    _is_safe_query,
    create_database_analyst_agent,
)
from core.adapters.protocol import AgentFramework

class TestDatabaseAnalystAgent:
    """Test suite for DatabaseAnalystAgent."""

    def test_create_agent_factory(self):
        """Test factory function creates agent instance."""
        agent = create_database_analyst_agent()
        assert agent is not None
        assert isinstance(agent, DatabaseAnalystAgent)

    def test_agent_card_basic(self):
        """Test agent card has correct basic info."""
        agent = create_database_analyst_agent()
        card = agent.get_card()

        assert card.name == "database_analyst"
        assert card.framework == AgentFramework.LANGCHAIN
        assert "database" in card.description.lower() or "query" in card.description.lower()

    def test_agent_card_capabilities(self):
        """Test agent card lists expected capabilities."""
        agent = create_database_analyst_agent()
        card = agent.get_card()

        capability_names = [c.name for c in card.capabilities]
        assert "query_database" in capability_names
        assert "list_tables" in capability_names
        assert "describe_table" in capability_names
        assert "query_prometheus" in capability_names

    def test_get_tools_returns_list(self):
        """Test get_tools returns OpenAI function format."""
        agent = create_database_analyst_agent()
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
        agent = create_database_analyst_agent()
        tools = agent.get_tools()

        tool_names = [t["function"]["name"] for t in tools]
        assert "query_database" in tool_names
        assert "list_tables" in tool_names
        assert "describe_table" in tool_names
        assert "query_prometheus" in tool_names

class TestDatabaseAnalystStreaming:
    """Test streaming support."""

    def test_supports_streaming_true(self):
        """Test Database Analyst supports streaming."""
        agent = create_database_analyst_agent()
        assert agent.supports_streaming() is True

    def test_card_metadata_includes_streaming(self):
        """Test agent card metadata indicates streaming support."""
        agent = create_database_analyst_agent()
        card = agent.get_card()

        assert card.metadata.get("streaming") is True

    @pytest.mark.asyncio
    async def test_execute_stream_yields_progress(self):
        """Test execute_stream yields progress updates."""
        agent = create_database_analyst_agent()

        chunks = []
        async for chunk in agent.execute_stream("List tables"):
            chunks.append(chunk)

        # Should have at least start message
        assert len(chunks) > 0
        assert chunks[0]["step"] == "start"

class TestSQLQuerySafety:
    """Test SQL query safety validation."""

    def test_safe_select_query(self):
        """Test SELECT queries are allowed."""
        is_safe, reason = _is_safe_query("SELECT * FROM users")
        assert is_safe is True
        assert reason is None

    def test_safe_select_with_where(self):
        """Test SELECT with WHERE is allowed."""
        is_safe, reason = _is_safe_query("SELECT name FROM users WHERE id = 1")
        assert is_safe is True

    def test_unsafe_drop_table(self):
        """Test DROP TABLE is blocked."""
        is_safe, reason = _is_safe_query("DROP TABLE users")
        assert is_safe is False
        assert "DROP" in reason

    def test_unsafe_drop_database(self):
        """Test DROP DATABASE is blocked."""
        is_safe, reason = _is_safe_query("DROP DATABASE mydb")
        assert is_safe is False
        assert "DROP" in reason

    def test_unsafe_truncate(self):
        """Test TRUNCATE is blocked."""
        is_safe, reason = _is_safe_query("TRUNCATE TABLE users")
        assert is_safe is False
        assert "TRUNCATE" in reason

    def test_unsafe_delete_without_where(self):
        """Test DELETE without WHERE is blocked."""
        is_safe, reason = _is_safe_query("DELETE FROM users")
        assert is_safe is False
        assert "DELETE" in reason.upper() or "destructive" in reason.lower()

    def test_safe_delete_with_where(self):
        """Test DELETE with WHERE is allowed."""
        is_safe, reason = _is_safe_query("DELETE FROM users WHERE id = 1")
        assert is_safe is True

    def test_unsafe_update_without_where(self):
        """Test UPDATE without WHERE is blocked."""
        is_safe, reason = _is_safe_query("UPDATE users SET active = false")
        assert is_safe is False

    def test_safe_update_with_where(self):
        """Test UPDATE with WHERE is allowed."""
        is_safe, reason = _is_safe_query("UPDATE users SET active = false WHERE id = 1")
        assert is_safe is True

    def test_case_insensitivity(self):
        """Test validation is case insensitive."""
        is_safe, reason = _is_safe_query("drop table USERS")
        assert is_safe is False

class TestDatabaseAnalystGracefulFallback:
    """Test graceful fallback behavior."""

    @pytest.fixture
    def agent(self):
        """Create agent fixture."""
        return create_database_analyst_agent()

    @pytest.mark.asyncio
    async def test_graceful_fallback_when_adapter_unavailable(self, agent):
        """Test graceful error when LangChain adapter not initialized."""
        # Force adapter to None
        agent._adapter = None
        agent._init_error = "Test error - adapter not available"

        result = await agent.execute("List tables")

        assert result.status == "error"
        assert "Test error" in result.error
        assert result.metadata.get("recoverable") is True
        assert "required_servers" in result.metadata

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_execution_error(self, agent):
        """Test graceful error when execution fails."""
        if agent._adapter:
            with patch.object(
                agent._adapter, "execute", side_effect=Exception("DBHub server error")
            ):
                result = await agent.execute("SELECT * FROM users")

                assert result.status == "error"
                assert "Database analysis failed" in result.error
                assert "DBHub server error" in result.error

    def test_metadata_includes_required_servers(self, agent):
        """Test that card metadata includes required MCP servers."""
        card = agent.get_card()

        assert "required_servers" in card.metadata
        assert "dbhub" in card.metadata["required_servers"]
        assert "grafana" in card.metadata["required_servers"]

class TestDatabaseAnalystConfig:
    """Test configuration loading."""

    def test_default_config_values(self):
        """Test agent uses default config when YAML not found."""
        agent = DatabaseAnalystAgent(config={})

        assert agent.name == "database_analyst"
        assert "database" in agent.description.lower() or "query" in agent.description.lower()

    def test_custom_config_override(self):
        """Test custom config overrides defaults."""
        custom_config = {
            "name": "custom_analyst",
            "description": "Custom database analyst",
        }
        agent = DatabaseAnalystAgent(config=custom_config)

        assert agent.name == "custom_analyst"
        assert agent.description == "Custom database analyst"

class TestPrometheusQueryRouting:
    """Test Prometheus query routing to Grafana server."""

    def test_prometheus_tool_in_capabilities(self):
        """Test Prometheus tool is available in capabilities."""
        agent = create_database_analyst_agent()
        card = agent.get_card()

        capability_names = [c.name for c in card.capabilities]
        assert "query_prometheus" in capability_names

    def test_prometheus_tool_description(self):
        """Test Prometheus tool has correct description."""
        agent = create_database_analyst_agent()
        tools = agent.get_tools()

        prometheus_tool = next(
            (t for t in tools if t["function"]["name"] == "query_prometheus"),
            None,
        )
        assert prometheus_tool is not None
        assert "prometheus" in prometheus_tool["function"]["description"].lower()
