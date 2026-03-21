"""
Unit tests for LangChain Agent Adapter.

Tests the LangChainAgentAdapter class which wraps LangChain agents
to conform to the UniversalAgent interface.

All tests use mocks to avoid calling real LLMs.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.adapters.langchain_adapter import LangChainAgentAdapter
from core.adapters.protocol import AgentCard, AgentFramework, AgentResult

class TestLangChainAdapterGetCard:
    """Test get_card() method returns proper AgentCard."""

    def test_langchain_adapter_get_card_basic(self, mock_langchain_agent):
        """Verify get_card() returns AgentCard with correct fields."""
        adapter = LangChainAgentAdapter(
            mock_langchain_agent,
            name="Test LangChain Agent",
            description="A test agent for unit testing",
        )

        card = adapter.get_card()

        assert isinstance(card, AgentCard)
        assert card.name == "Test LangChain Agent"
        assert card.description == "A test agent for unit testing"
        assert card.version == "1.0"
        assert card.framework == AgentFramework.LANGCHAIN
        assert card.capabilities == []
        assert "type" in card.metadata

    def test_langchain_adapter_get_card_includes_agent_type(self, mock_langchain_agent):
        """Verify agent type is included in metadata."""
        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Typed Agent", description="Agent with type metadata"
        )

        card = adapter.get_card()

        assert card.metadata["type"] == "MagicMock"

class TestLangChainAdapterExecute:
    """Test execute() method with mocked LangChain execution."""

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_success_ainvoke(self, mock_langchain_agent):
        """Verify ainvoke-style execution returns proper AgentResult."""
        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Ainvoke Agent", description="LangGraph-style agent"
        )

        result = await adapter.execute("Complete the test task")

        assert isinstance(result, AgentResult)
        assert result.status == "ok"
        assert result.result["output"] == "LangChain result"
        assert result.metadata["framework"] == "langgraph"
        assert result.error is None
        mock_langchain_agent.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_success_arun(self):
        """Verify arun-style execution when ainvoke not available."""
        # Create agent without ainvoke
        agent = MagicMock()
        del agent.ainvoke
        agent.arun = AsyncMock(return_value="Arun result")
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Arun Agent", description="LangChain style")

        result = await adapter.execute("Test task")

        assert result.status == "ok"
        assert result.result == "Arun result"
        assert result.metadata["framework"] == "langchain"
        agent.arun.assert_awaited_once_with("Test task")

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_success_sync_fallback(self):
        """Verify sync run() fallback when no async methods available."""
        agent = MagicMock()
        del agent.ainvoke
        del agent.arun
        agent.run = MagicMock(return_value="Sync result")
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Sync Agent", description="Sync only")

        result = await adapter.execute("Test task")

        assert result.status == "ok"
        assert result.result == "Sync result"
        assert result.metadata["framework"] == "langchain"
        agent.run.assert_called_once_with("Test task")

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_error(self, mock_langchain_agent):
        """Verify error handling when ainvoke raises exception."""
        mock_langchain_agent.ainvoke.side_effect = RuntimeError("LLM connection failed")

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Failing Agent", description="Will fail"
        )

        result = await adapter.execute("This will fail")

        assert result.status == "error"
        assert result.result is None
        # Error format is "Agent execution failed: {ExceptionType}"
        assert "Agent execution failed: RuntimeError" in result.error
        assert result.metadata["framework"] == "langchain"

class TestLangChainAdapterWithTools:
    """Test tool binding and extraction from LangChain agents."""

    def test_langchain_adapter_execute_with_tools_extraction(
        self, mock_langchain_agent, mock_tool_with_schema
    ):
        """Verify tools are correctly extracted from agent."""
        mock_langchain_agent.tools = [mock_tool_with_schema]

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Tool Agent", description="Agent with tools"
        )

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "schema_tool"
        assert tools[0]["function"]["description"] == "A tool with schema"

    def test_langchain_adapter_tool_extraction_empty(self, mock_langchain_agent):
        """Verify empty tools list returns empty result."""
        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="No Tools Agent", description="Agent without tools"
        )

        tools = adapter.get_tools()

        assert tools == []

    def test_langchain_adapter_tool_extraction_with_schema(
        self, mock_langchain_agent, mock_tool_with_schema
    ):
        """Verify tools with args_schema are extracted correctly."""
        mock_langchain_agent.tools = [mock_tool_with_schema]

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Schema Tool Agent", description="Agent with schema tools"
        )

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert "parameters" in tools[0]["function"]
        assert "properties" in tools[0]["function"]["parameters"]
        assert "query" in tools[0]["function"]["parameters"]["properties"]

    def test_langchain_adapter_tool_extraction_without_schema(self, mock_langchain_agent):
        """Verify tools without schema get empty parameters."""
        simple_tool = MagicMock()
        simple_tool.name = "simple_tool"
        simple_tool.description = "A simple tool"
        simple_tool.args_schema = None

        mock_langchain_agent.tools = [simple_tool]

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Simple Tool Agent", description="Agent with simple tool"
        )

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "simple_tool"
        assert tools[0]["function"]["parameters"] == {}

class TestLangChainAdapterStreaming:
    """Test streaming functionality."""

    def test_langchain_adapter_supports_streaming_with_astream(self):
        """Verify streaming support detected for astream."""
        agent = MagicMock()
        agent.astream = AsyncMock()
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Async Stream Agent", description="Streams")

        assert adapter.supports_streaming() is True

    def test_langchain_adapter_supports_streaming_with_stream(self):
        """Verify streaming support detected for sync stream."""
        agent = MagicMock()
        del agent.astream
        agent.stream = MagicMock()
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Sync Stream Agent", description="Streams")

        assert adapter.supports_streaming() is True

    def test_langchain_adapter_no_streaming_support(self, mock_langchain_agent):
        """Verify no streaming when methods missing."""
        # Remove streaming methods
        del mock_langchain_agent.astream
        del mock_langchain_agent.stream

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="No Stream Agent", description="No streaming"
        )

        assert adapter.supports_streaming() is False

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_stream_async(self):
        """Verify async streaming execution."""

        async def mock_astream(input_dict):
            yield {"output": "chunk1"}
            yield {"output": "chunk2"}
            yield {"output": "chunk3"}

        agent = MagicMock()
        agent.astream = mock_astream
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Stream Agent", description="Streams")

        chunks = []
        async for chunk in adapter.execute_stream("Test streaming"):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0]["output"] == "chunk1"
        assert chunks[2]["output"] == "chunk3"

    @pytest.mark.asyncio
    async def test_langchain_adapter_execute_stream_sync_fallback(self):
        """Verify sync streaming fallback."""

        def mock_stream(input_dict):
            yield {"output": "sync_chunk1"}
            yield {"output": "sync_chunk2"}

        agent = MagicMock()
        del agent.astream
        agent.stream = mock_stream
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Sync Stream Agent", description="Streams")

        chunks = []
        async for chunk in adapter.execute_stream("Test streaming"):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0]["output"] == "sync_chunk1"

class TestLangChainAdapterToolSchemaExtraction:
    """Test OpenAI function format tool schema extraction."""

    def test_langchain_adapter_tool_schema_openai_format(
        self, mock_langchain_agent, mock_tool_with_schema
    ):
        """Verify tools are extracted in OpenAI function format."""
        mock_langchain_agent.tools = [mock_tool_with_schema]

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="OpenAI Format Agent", description="Uses OpenAI format"
        )

        tools = adapter.get_tools()

        # Verify OpenAI function format structure
        assert len(tools) == 1
        tool = tools[0]
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    def test_langchain_adapter_multiple_tools_schema(self, mock_langchain_agent):
        """Verify multiple tools with different schemas."""
        tool1 = MagicMock()
        tool1.name = "search_tool"
        tool1.description = "Search the web"
        schema1 = MagicMock()
        schema1.schema.return_value = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        tool1.args_schema = schema1

        tool2 = MagicMock()
        tool2.name = "calculator_tool"
        tool2.description = "Perform calculations"
        schema2 = MagicMock()
        schema2.schema.return_value = {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "precision": {"type": "integer"},
            },
            "required": ["expression"],
        }
        tool2.args_schema = schema2

        mock_langchain_agent.tools = [tool1, tool2]

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Multi Tool Agent", description="Multiple tools"
        )

        tools = adapter.get_tools()

        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "search_tool"
        assert tools[1]["function"]["name"] == "calculator_tool"
        assert "query" in tools[0]["function"]["parameters"]["properties"]
        assert "expression" in tools[1]["function"]["parameters"]["properties"]

class TestLangChainAdapterFrameworkMetadata:
    """Test framework metadata in execution results."""

    @pytest.mark.asyncio
    async def test_langchain_adapter_framework_metadata_langgraph(self, mock_langchain_agent):
        """Verify framework='langgraph' when using ainvoke."""
        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="LangGraph Agent", description="Uses ainvoke"
        )

        result = await adapter.execute("Test task")

        assert result.metadata["framework"] == "langgraph"

    @pytest.mark.asyncio
    async def test_langchain_adapter_framework_metadata_langchain(self):
        """Verify framework='langchain' when using arun."""
        agent = MagicMock()
        del agent.ainvoke
        agent.arun = AsyncMock(return_value="Result")
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="LangChain Agent", description="Uses arun")

        result = await adapter.execute("Test task")

        assert result.metadata["framework"] == "langchain"

    @pytest.mark.asyncio
    async def test_langchain_adapter_error_framework_metadata(self, mock_langchain_agent):
        """Verify framework='langchain' in error results."""
        mock_langchain_agent.ainvoke.side_effect = RuntimeError("Error")

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Error Agent", description="Will error"
        )

        result = await adapter.execute("Test task")

        assert result.status == "error"
        assert result.metadata["framework"] == "langchain"

# =============================================================================
# LangChain Chain Composition and Memory Integration
# =============================================================================

class TestLangChainAdapterChainComposition:
    """Test LangChain chain composition and memory handling."""

    @pytest.mark.asyncio
    async def test_langchain_adapter_chain_with_memory(self):
        """Verify chains with memory state are handled correctly."""
        agent = MagicMock()
        agent.ainvoke = AsyncMock(
            return_value={
                "output": "Response with memory context",
                "chat_history": [{"role": "user", "content": "Previous message"}],
            }
        )
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Memory Agent", description="Agent with memory")

        result = await adapter.execute("Continuing conversation")

        assert result.status == "ok"
        assert "output" in result.result

    @pytest.mark.asyncio
    async def test_langchain_adapter_chain_sequential_execution(self):
        """Verify sequential chain execution tracking."""
        execution_count = {"count": 0}

        async def count_executions(input_dict):
            execution_count["count"] += 1
            return {"output": f"Execution {execution_count['count']}"}

        agent = MagicMock()
        agent.ainvoke = count_executions
        agent.tools = []

        adapter = LangChainAgentAdapter(
            agent, name="Sequential Agent", description="Sequential execution"
        )

        result1 = await adapter.execute("First task")
        result2 = await adapter.execute("Second task")

        assert result1.result["output"] == "Execution 1"
        assert result2.result["output"] == "Execution 2"
        assert execution_count["count"] == 2

    @pytest.mark.asyncio
    async def test_langchain_adapter_chain_with_intermediate_steps(self):
        """Verify handling of chains with intermediate execution steps."""
        agent = MagicMock()
        agent.ainvoke = AsyncMock(
            return_value={
                "output": "Final result",
                "intermediate_steps": [
                    ("tool_call_1", "result_1"),
                    ("tool_call_2", "result_2"),
                ],
            }
        )
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Chain Agent", description="Chain with steps")

        result = await adapter.execute("Multi-step task")

        assert result.status == "ok"
        assert result.result["output"] == "Final result"
        assert "intermediate_steps" in result.result

    @pytest.mark.asyncio
    async def test_langchain_adapter_complex_chain_output(self):
        """Verify handling of complex nested chain outputs."""
        complex_output = {
            "output": "Main response",
            "metadata": {"confidence": 0.95, "tokens": 150},
            "sources": [{"title": "Doc1", "score": 0.8}, {"title": "Doc2", "score": 0.75}],
            "reasoning": ["Step 1: Analyze", "Step 2: Synthesize", "Step 3: Respond"],
        }

        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value=complex_output)
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Complex Chain", description="Complex output")

        result = await adapter.execute("Complex task")

        assert result.status == "ok"
        assert result.result["output"] == "Main response"
        assert "sources" in result.result
        assert len(result.result["reasoning"]) == 3

    @pytest.mark.asyncio
    async def test_langchain_adapter_empty_output_field(self):
        """Verify handling of response with empty output field."""
        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value={"output": "", "status": "completed"})
        agent.tools = []

        adapter = LangChainAgentAdapter(
            agent, name="Empty Output Agent", description="Empty output"
        )

        result = await adapter.execute("Task with empty output")

        assert result.status == "ok"
        assert result.result["output"] == ""

    @pytest.mark.asyncio
    async def test_langchain_adapter_missing_output_field(self):
        """Verify handling of response without output field."""
        agent = MagicMock()
        agent.ainvoke = AsyncMock(return_value={"result": "Success", "data": "Some data"})
        agent.tools = []

        adapter = LangChainAgentAdapter(
            agent, name="No Output Field Agent", description="No output field"
        )

        result = await adapter.execute("Task without output")

        assert result.status == "ok"
        # Should return the whole response if no output field
        assert "result" in result.result or result.result is not None

# =============================================================================
# LangChain Error Handling Edge Cases
# =============================================================================

class TestLangChainAdapterErrorEdgeCases:
    """Test LangChain adapter error handling edge cases."""

    @pytest.mark.asyncio
    async def test_langchain_adapter_llm_rate_limit_error(self, mock_langchain_agent):
        """Verify LLM rate limit errors are handled gracefully."""
        mock_langchain_agent.ainvoke.side_effect = Exception("Rate limit exceeded: 429")

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Rate Limited Agent", description="Rate limited"
        )

        result = await adapter.execute("Rate limited task")

        assert result.status == "error"
        # Error format is "Agent execution failed: {ExceptionType}"
        assert "Agent execution failed: Exception" in result.error

    @pytest.mark.asyncio
    async def test_langchain_adapter_llm_context_length_error(self, mock_langchain_agent):
        """Verify context length errors are captured."""
        mock_langchain_agent.ainvoke.side_effect = ValueError("maximum context length exceeded")

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Context Error Agent", description="Context error"
        )

        result = await adapter.execute("Very long task context...")

        assert result.status == "error"
        # Error format is "Agent execution failed: {ExceptionType}"
        assert "Agent execution failed: ValueError" in result.error

    @pytest.mark.asyncio
    async def test_langchain_adapter_invalid_tool_call(self, mock_langchain_agent):
        """Verify invalid tool call errors are handled."""
        mock_langchain_agent.ainvoke.side_effect = AttributeError(
            "'NoneType' object has no attribute 'run'"
        )

        adapter = LangChainAgentAdapter(
            mock_langchain_agent, name="Invalid Tool Agent", description="Invalid tool"
        )

        result = await adapter.execute("Task with invalid tool")

        assert result.status == "error"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_langchain_adapter_timeout_during_execution(self):
        """Verify timeout errors during chain execution."""
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=TimeoutError("Chain execution timed out"))
        agent.tools = []

        adapter = LangChainAgentAdapter(agent, name="Timeout Agent", description="Timeout")

        result = await adapter.execute("Long running task")

        assert result.status == "error"
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_langchain_adapter_memory_error(self):
        """Verify memory errors during execution are handled."""
        agent = MagicMock()
        agent.ainvoke = AsyncMock(side_effect=MemoryError("Out of memory"))
        agent.tools = []

        adapter = LangChainAgentAdapter(
            agent, name="Memory Error Agent", description="Memory error"
        )

        result = await adapter.execute("Memory intensive task")

        assert result.status == "error"
        assert "memory" in result.error.lower()
