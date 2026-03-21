"""
Unit tests for CrewAI Agent Adapter.

Tests the CrewAIAgentAdapter class which wraps CrewAI agents
to conform to the UniversalAgent interface.

The CrewAI adapter's execute() method:
- Takes _context (prefixed) as second arg, not context
- Calls _configure_llm_from_context() before execution (must be mocked)
- Returns AgentResult with status="error" and error="Agent execution failed: {ExceptionType}"
  on error (does not include the original message in the error field)

All tests use mocks to avoid calling real LLMs.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.adapters.crewai_adapter import CrewAIAgentAdapter
from core.adapters.protocol import AgentCard, AgentFramework, AgentResult

class TestCrewAIAdapterGetCard:
    """Test get_card() method returns proper AgentCard."""

    def test_crewai_adapter_get_card_basic(self, mock_crewai_agent):
        """Verify get_card() returns AgentCard with correct fields."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        card = adapter.get_card()

        assert isinstance(card, AgentCard)
        assert card.name == "Test Agent"
        assert card.description == "Complete test tasks"
        assert card.version == "1.0"
        assert card.framework == AgentFramework.CREWAI
        assert card.capabilities == []
        assert card.metadata["backstory"] == "A test agent for unit testing"
        assert card.metadata["verbose"] is False

    def test_crewai_adapter_get_card_with_custom_name(self, mock_crewai_agent):
        """Verify custom name overrides agent role."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent, name="Custom Agent Name")

        card = adapter.get_card()

        assert card.name == "Custom Agent Name"

    def test_crewai_adapter_get_card_with_tools(self, mock_crewai_agent, mock_tool_with_schema):
        """Verify tools are extracted as capabilities."""
        mock_crewai_agent.tools = [mock_tool_with_schema]
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        card = adapter.get_card()

        assert len(card.capabilities) == 1
        assert card.capabilities[0].name == "schema_tool"
        assert card.capabilities[0].description == "A tool with schema"
        assert "properties" in card.capabilities[0].input_schema

class TestCrewAIAdapterExecute:
    """Test execute() method with mocked CrewAI execution.

    The execute() method calls _configure_llm_from_context() first,
    which imports from core.extensions. This must be mocked in tests.
    """

    @pytest.mark.asyncio
    async def test_crewai_adapter_execute_success(self, mock_crewai_agent):
        """Verify successful execution returns proper AgentResult."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        # Mock crewai module imports (imported inside execute method)
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "Task completed successfully"
        mock_crew_class = MagicMock(return_value=mock_crew_instance)
        mock_task_class = MagicMock()

        with patch.object(adapter, "_configure_llm_from_context"):
            with patch.dict(
                "sys.modules", {"crewai": MagicMock(Crew=mock_crew_class, Task=mock_task_class)}
            ):
                result = await adapter.execute("Complete the test task")

                assert isinstance(result, AgentResult)
                assert result.status == "ok"
                assert result.result == "Task completed successfully"
                assert result.metadata["framework"] == "crewai"
                assert "execution_time_ms" in result.metadata
                assert result.error is None

    @pytest.mark.asyncio
    async def test_crewai_adapter_execute_with_context(self, mock_crewai_agent):
        """Verify context dict is accepted during execution (as _context param)."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)
        context = {"user_id": "123", "session": "abc"}

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "Context-aware result"
        mock_crew_class = MagicMock(return_value=mock_crew_instance)
        mock_task_class = MagicMock()

        with patch.object(adapter, "_configure_llm_from_context"):
            with patch.dict(
                "sys.modules", {"crewai": MagicMock(Crew=mock_crew_class, Task=mock_task_class)}
            ):
                # The execute() signature uses _context (prefixed)
                result = await adapter.execute("Use context", context)

                assert result.status == "ok"
                assert result.result == "Context-aware result"
                # Verify Task was created (context passed via task description)
                mock_task_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_crewai_adapter_execute_error(self, mock_crewai_agent):
        """Verify error handling when kickoff raises exception."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.side_effect = RuntimeError("LLM connection failed")
        mock_crew_class = MagicMock(return_value=mock_crew_instance)
        mock_task_class = MagicMock()

        with patch.object(adapter, "_configure_llm_from_context"):
            with patch.dict(
                "sys.modules", {"crewai": MagicMock(Crew=mock_crew_class, Task=mock_task_class)}
            ):
                result = await adapter.execute("This will fail")

                assert result.status == "error"
                assert result.result is None
                # Error format is "Agent execution failed: {ExceptionType}"
                assert "Agent execution failed: RuntimeError" in result.error
                assert result.metadata["framework"] == "crewai"
                assert "execution_time_ms" in result.metadata

class TestCrewAIAdapterToolExtraction:
    """Test tool extraction from CrewAI agents."""

    def test_crewai_adapter_tool_extraction_empty(self, mock_crewai_agent):
        """Verify empty tools list returns empty result."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        tools = adapter.get_tools()

        assert tools == []

    def test_crewai_adapter_tool_extraction_with_schema(
        self, mock_crewai_agent, mock_tool_with_schema
    ):
        """Verify tools with schema are extracted correctly."""
        mock_crewai_agent.tools = [mock_tool_with_schema]
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "schema_tool"
        assert tools[0]["function"]["description"] == "A tool with schema"
        assert "properties" in tools[0]["function"]["parameters"]
        assert "query" in tools[0]["function"]["parameters"]["properties"]

    def test_crewai_adapter_tool_extraction_without_schema(self, mock_crewai_agent):
        """Verify tools without schema get empty parameters."""
        simple_tool = MagicMock()
        simple_tool.name = "simple_tool"
        simple_tool.description = "A simple tool"
        # No args_schema attribute
        del simple_tool.args_schema

        mock_crewai_agent.tools = [simple_tool]
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "simple_tool"
        assert tools[0]["function"]["parameters"] == {}

    def test_crewai_adapter_tool_extraction_multiple(
        self, mock_crewai_agent, mock_tool_with_schema
    ):
        """Verify multiple tools are extracted."""
        tool2 = MagicMock()
        tool2.name = "tool2"
        tool2.description = "Second tool"
        tool2.args_schema = None

        mock_crewai_agent.tools = [mock_tool_with_schema, tool2]
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        tools = adapter.get_tools()

        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "schema_tool"
        assert tools[1]["function"]["name"] == "tool2"

class TestCrewAIAdapterFrameworkMetadata:
    """Test framework metadata in execution results."""

    @pytest.mark.asyncio
    async def test_crewai_adapter_framework_metadata(self, mock_crewai_agent):
        """Verify framework='crewai' in result metadata."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "Result"
        mock_crew_class = MagicMock(return_value=mock_crew_instance)
        mock_task_class = MagicMock()

        with patch.object(adapter, "_configure_llm_from_context"):
            with patch.dict(
                "sys.modules", {"crewai": MagicMock(Crew=mock_crew_class, Task=mock_task_class)}
            ):
                result = await adapter.execute("Test task")

                assert result.metadata["framework"] == "crewai"

    @pytest.mark.asyncio
    async def test_crewai_adapter_tools_count_in_metadata(
        self, mock_crewai_agent, mock_tool_with_schema
    ):
        """Verify tools_count appears in metadata on success."""
        mock_crewai_agent.tools = [mock_tool_with_schema]
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "Result"
        mock_crew_class = MagicMock(return_value=mock_crew_instance)
        mock_task_class = MagicMock()

        with patch.object(adapter, "_configure_llm_from_context"):
            with patch.dict(
                "sys.modules", {"crewai": MagicMock(Crew=mock_crew_class, Task=mock_task_class)}
            ):
                result = await adapter.execute("Test task")

                assert result.metadata["tools_count"] == 1

class TestCrewAIAdapterCrewWrapping:
    """Test agent wrapping in minimal Crew for execution."""

    @pytest.mark.asyncio
    async def test_crewai_adapter_crew_wrapping(self, mock_crewai_agent):
        """Verify agent is wrapped in Crew with Task for execution."""
        adapter = CrewAIAgentAdapter(mock_crewai_agent)

        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = "Wrapped result"
        mock_crew_class = MagicMock(return_value=mock_crew_instance)
        mock_task_instance = MagicMock()
        mock_task_class = MagicMock(return_value=mock_task_instance)

        with patch.object(adapter, "_configure_llm_from_context"):
            with patch.dict(
                "sys.modules", {"crewai": MagicMock(Crew=mock_crew_class, Task=mock_task_class)}
            ):
                await adapter.execute("Test wrapping")

                # Verify Task was created with the agent
                mock_task_class.assert_called_once()
                task_call_kwargs = mock_task_class.call_args.kwargs
                assert task_call_kwargs["agent"] == mock_crewai_agent
                assert "Test wrapping" in task_call_kwargs["description"]

                # Verify Crew was created with the agent and task
                mock_crew_class.assert_called_once()
                crew_call_kwargs = mock_crew_class.call_args.kwargs
                assert crew_call_kwargs["agents"] == [mock_crewai_agent]
                assert crew_call_kwargs["tasks"] == [mock_task_instance]
                assert crew_call_kwargs["verbose"] is False

                # Verify kickoff was called
                mock_crew_instance.kickoff.assert_called_once()
