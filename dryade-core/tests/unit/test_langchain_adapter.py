"""Unit tests for LangChain/LangGraph agent adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

@pytest.mark.unit
class TestLangChainAdapterInitialization:
    """Tests for LangChainAgentAdapter initialization."""

    def test_langchain_adapter_initialization(self):
        """Test basic initialization with LangChain agent."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock()
        adapter = LangChainAgentAdapter(
            mock_agent, name="test_agent", description="Test LangChain agent"
        )

        assert adapter.agent is mock_agent
        assert adapter.name == "test_agent"
        assert adapter.description == "Test LangChain agent"

@pytest.mark.unit
class TestLangChainAdapterGetCard:
    """Tests for LangChainAgentAdapter.get_card()."""

    def test_langchain_adapter_get_card(self):
        """Test getting agent card."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter
        from core.adapters.protocol import AgentFramework

        mock_agent = MagicMock()
        mock_agent.__class__.__name__ = "AgentExecutor"

        adapter = LangChainAgentAdapter(
            mock_agent, name="lang_agent", description="A LangChain agent"
        )
        card = adapter.get_card()

        assert card.name == "lang_agent"
        assert card.description == "A LangChain agent"
        assert card.version == "1.0"
        assert card.framework == AgentFramework.LANGCHAIN
        assert card.metadata["type"] == "AgentExecutor"
        assert card.capabilities == []

    def test_langchain_adapter_get_card_langgraph(self):
        """Test getting agent card for LangGraph CompiledGraph."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock()
        mock_agent.__class__.__name__ = "CompiledGraph"

        adapter = LangChainAgentAdapter(
            mock_agent, name="graph_agent", description="A LangGraph agent"
        )
        card = adapter.get_card()

        assert card.name == "graph_agent"
        assert card.metadata["type"] == "CompiledGraph"

@pytest.mark.unit
class TestLangChainAdapterExecute:
    """Tests for LangChainAgentAdapter.execute()."""

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_ainvoke(self):
        """Test execution using ainvoke (LangGraph style)."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value={"output": "Task done"})

        adapter = LangChainAgentAdapter(mock_agent, name="async_agent", description="Async")

        result = await adapter.execute("Do something", {"key": "value"})

        assert result.status == "ok"
        assert result.result == {"output": "Task done"}
        assert result.metadata["framework"] == "langgraph"
        mock_agent.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_arun(self):
        """Test execution using arun (LangChain AgentExecutor style)."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=["arun"])
        mock_agent.arun = AsyncMock(return_value="Completed task")

        adapter = LangChainAgentAdapter(mock_agent, name="arun_agent", description="Uses arun")

        result = await adapter.execute("Do task")

        assert result.status == "ok"
        assert result.result == "Completed task"
        assert result.metadata["framework"] == "langchain"
        mock_agent.arun.assert_awaited_once_with("Do task")

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_run_sync(self):
        """Test execution using synchronous run."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=["run"])
        mock_agent.run = MagicMock(return_value="Sync result")

        adapter = LangChainAgentAdapter(mock_agent, name="sync_agent", description="Sync")

        result = await adapter.execute("Sync task")

        assert result.status == "ok"
        assert result.result == "Sync result"
        mock_agent.run.assert_called_once_with("Sync task")

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_no_method(self):
        """Test execution when agent has no run methods."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=[])  # No methods

        adapter = LangChainAgentAdapter(mock_agent, name="no_method", description="No method")

        result = await adapter.execute("Task")

        assert result.status == "error"
        assert "run" in result.error.lower() or "method" in result.error.lower()

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_error_handling(self):
        """Test error handling during execution."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(side_effect=Exception("LangChain error"))

        adapter = LangChainAgentAdapter(mock_agent, name="error_agent", description="Errors")

        result = await adapter.execute("Failing task")

        assert result.status == "error"
        # The adapter wraps exceptions as "Agent execution failed: {type}"
        assert "Exception" in result.error
        assert result.metadata["framework"] == "langchain"

@pytest.mark.unit
class TestLangChainAdapterGetTools:
    """Tests for LangChainAgentAdapter.get_tools()."""

    def test_langchain_adapter_get_tools_empty(self):
        """Test get_tools with no tools."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=[])

        adapter = LangChainAgentAdapter(mock_agent, name="no_tools", description="No tools")
        tools = adapter.get_tools()

        assert tools == []

    def test_langchain_adapter_get_tools_with_schema(self):
        """Test get_tools with tools that have schemas."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_tool = MagicMock()
        mock_tool.name = "search"
        mock_tool.description = "Search for info"
        mock_tool.args_schema = MagicMock()
        mock_tool.args_schema.schema.return_value = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

        mock_agent = MagicMock()
        mock_agent.tools = [mock_tool]

        adapter = LangChainAgentAdapter(mock_agent, name="tool_agent", description="Has tools")
        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "search"
        assert tools[0]["function"]["description"] == "Search for info"
        assert tools[0]["function"]["parameters"]["type"] == "object"

    def test_langchain_adapter_get_tools_without_schema(self):
        """Test get_tools with tools that lack args_schema."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_tool = MagicMock()
        mock_tool.name = "simple_tool"
        mock_tool.description = "Simple"
        mock_tool.args_schema = None

        mock_agent = MagicMock()
        mock_agent.tools = [mock_tool]

        adapter = LangChainAgentAdapter(mock_agent, name="simple", description="Simple agent")
        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["parameters"] == {}

@pytest.mark.unit
class TestLangChainAdapterStreaming:
    """Tests for LangChainAgentAdapter streaming support."""

    def test_langchain_adapter_supports_streaming_astream(self):
        """Test supports_streaming with astream method."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock()
        mock_agent.astream = AsyncMock()

        adapter = LangChainAgentAdapter(mock_agent, name="stream", description="Streams")

        assert adapter.supports_streaming() is True

    def test_langchain_adapter_supports_streaming_stream(self):
        """Test supports_streaming with stream method."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=["stream"])
        mock_agent.stream = MagicMock()

        adapter = LangChainAgentAdapter(mock_agent, name="stream", description="Streams")

        assert adapter.supports_streaming() is True

    def test_langchain_adapter_supports_streaming_false(self):
        """Test supports_streaming when no streaming methods exist."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=["run"])

        adapter = LangChainAgentAdapter(mock_agent, name="no_stream", description="No stream")

        assert adapter.supports_streaming() is False

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_stream_astream(self):
        """Test execute_stream with astream method."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        async def mock_stream(*args, **kwargs):
            yield "chunk1"
            yield "chunk2"
            yield "chunk3"

        mock_agent = MagicMock()
        mock_agent.astream = mock_stream

        adapter = LangChainAgentAdapter(mock_agent, name="stream", description="Streams")

        chunks = []
        async for chunk in adapter.execute_stream("Task"):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks == ["chunk1", "chunk2", "chunk3"]

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_stream_not_supported(self):
        """Test execute_stream raises when not supported."""
        from core.adapters.langchain_adapter import LangChainAgentAdapter

        mock_agent = MagicMock(spec=["run"])

        adapter = LangChainAgentAdapter(mock_agent, name="no_stream", description="No stream")

        with pytest.raises(NotImplementedError, match="does not support streaming"):
            async for _ in adapter.execute_stream("Task"):
                pass
