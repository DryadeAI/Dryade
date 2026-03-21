"""
Example tests demonstrating plugin testing fixtures.

These tests show how to use the fixtures from conftest.py
to test plugins in isolation.

Run with: pytest tests/community/test_plugin_fixtures.py -v
"""

import pytest

# Import fixtures
pytest_plugins = ["tests.community.conftest"]

class TestMockLLM:
    """Tests demonstrating mock LLM usage."""

    def test_mock_llm_basic(self, mock_llm):
        """Basic LLM mock returns default response."""
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(mock_llm.generate("Hello"))
        assert response.content == "Mock response"
        assert mock_llm.calls[0]["prompt"] == "Hello"

    def test_mock_llm_custom_responses(self, mock_llm_factory):
        """LLM mock with custom responses."""
        import asyncio

        llm = mock_llm_factory(["First response", "Second response"])

        r1 = asyncio.get_event_loop().run_until_complete(llm.generate("Q1"))
        r2 = asyncio.get_event_loop().run_until_complete(llm.generate("Q2"))

        assert r1.content == "First response"
        assert r2.content == "Second response"

    def test_mock_llm_tracks_calls(self, mock_llm):
        """LLM mock tracks all calls for assertions."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(
            mock_llm.generate("test prompt", temperature=0.7)
        )

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["prompt"] == "test prompt"
        assert mock_llm.calls[0]["temperature"] == 0.7

class TestPluginContext:
    """Tests demonstrating plugin context fixtures."""

    def test_default_context(self, plugin_context):
        """Default context has required fields."""
        assert "app" in plugin_context
        assert "settings" in plugin_context
        assert "db_session" in plugin_context
        assert "user" in plugin_context

    def test_context_settings(self, plugin_context):
        """Context settings are accessible."""
        assert plugin_context["settings"]["debug"] is True

    def test_custom_context(self, plugin_context_factory):
        """Factory creates custom context."""
        ctx = plugin_context_factory(
            settings={"custom_key": "custom_value"},
            user={"id": "custom-user"},
        )
        assert ctx["settings"]["custom_key"] == "custom_value"
        assert ctx["user"]["id"] == "custom-user"

class TestMockDatabase:
    """Tests demonstrating database mocks."""

    def test_mock_session_add(self, mock_db_session):
        """Mock session tracks added objects."""
        obj = {"id": 1, "name": "test"}
        mock_db_session.add(obj)

        assert obj in mock_db_session.added

    def test_mock_session_commit(self, mock_db_session):
        """Mock session tracks commits."""
        mock_db_session.commit()
        assert mock_db_session.committed is True

    def test_mock_query_results(self, mock_db_session):
        """Mock query returns configured results."""

        class FakeModel:
            pass

        results = [FakeModel(), FakeModel()]
        query = mock_db_session.query(FakeModel).with_results(results)

        assert query.all() == results
        assert query.first() == results[0]

class TestMockMCP:
    """Tests demonstrating MCP mocks."""

    @pytest.mark.asyncio
    async def test_mcp_default_result(self, mock_mcp_server):
        """MCP server returns default mock result."""
        result = await mock_mcp_server.call_tool("unknown_tool")
        assert "Mock result" in result["result"]

    @pytest.mark.asyncio
    async def test_mcp_custom_handler(self, mock_mcp_server):
        """MCP server uses custom tool handlers."""

        async def custom_handler(**kwargs):
            return {"custom": True, "args": kwargs}

        mock_mcp_server.register_tool("my_tool", custom_handler)
        result = await mock_mcp_server.call_tool("my_tool", param="value")

        assert result["custom"] is True
        assert result["args"]["param"] == "value"

    @pytest.mark.asyncio
    async def test_mcp_tracks_calls(self, mock_mcp_server):
        """MCP server tracks all tool calls."""
        await mock_mcp_server.call_tool("tool1", arg="val1")
        await mock_mcp_server.call_tool("tool2", arg="val2")

        assert len(mock_mcp_server.calls) == 2
        assert mock_mcp_server.calls[0]["tool"] == "tool1"
        assert mock_mcp_server.calls[1]["tool"] == "tool2"

class TestEventEmitter:
    """Tests demonstrating event emitter mocks."""

    def test_event_emission(self, mock_event_emitter):
        """Event emitter captures events."""
        mock_event_emitter.emit("test_event", {"key": "value"})

        events = mock_event_emitter.get_events()
        assert len(events) == 1
        assert events[0]["type"] == "test_event"
        assert events[0]["data"]["key"] == "value"

    def test_event_filtering(self, mock_event_emitter):
        """Event emitter filters by type."""
        mock_event_emitter.emit("type_a", {"a": 1})
        mock_event_emitter.emit("type_b", {"b": 2})
        mock_event_emitter.emit("type_a", {"a": 3})

        type_a_events = mock_event_emitter.get_events("type_a")
        assert len(type_a_events) == 2

class TestExamplePlugin:
    """Example of testing a real plugin structure."""

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self, plugin_context, mock_llm):
        """Example: Test plugin load/unload lifecycle."""
        # This is how you would test a real plugin:
        #
        # from my_plugin import plugin
        #
        # await plugin.on_load(plugin_context)
        # assert plugin.is_loaded
        #
        # await plugin.on_unload()
        # assert not plugin.is_loaded

        # For this example, we just verify the fixtures work
        assert plugin_context is not None
        assert mock_llm is not None

    @pytest.mark.asyncio
    async def test_plugin_with_mcp(self, plugin_context, mock_mcp_server, mock_llm):
        """Example: Test plugin that uses MCP tools."""

        # Register expected tool
        async def read_file_mock(path: str):
            return {"content": f"Contents of {path}"}

        mock_mcp_server.register_tool("read_file", read_file_mock)

        # Test tool call
        result = await mock_mcp_server.call_tool("read_file", path="/test.txt")
        assert "Contents of /test.txt" in result["content"]
