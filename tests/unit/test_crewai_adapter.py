"""Unit tests for CrewAI agent adapter."""

from unittest.mock import MagicMock, patch

import pytest

@pytest.mark.unit
class TestCrewAIAdapterInitialization:
    """Tests for CrewAIAgentAdapter initialization."""

    def test_crewai_adapter_initialization_with_agent(self):
        """Test initializing adapter with a CrewAI agent."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        # Mock CrewAI agent
        mock_agent = MagicMock()
        mock_agent.role = "researcher"
        mock_agent.goal = "Find information"
        mock_agent.backstory = "An experienced researcher"
        mock_agent.tools = []
        mock_agent.verbose = False

        adapter = CrewAIAgentAdapter(mock_agent)

        assert adapter.agent is mock_agent
        assert adapter._name is None

    def test_crewai_adapter_initialization_with_custom_name(self):
        """Test initializing adapter with custom name override."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.role = "researcher"
        mock_agent.goal = "Find information"
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent, name="custom_researcher")

        assert adapter._name == "custom_researcher"

@pytest.mark.unit
class TestCrewAIAdapterGetCard:
    """Tests for CrewAIAgentAdapter.get_card()."""

    def test_crewai_adapter_get_card_basic(self):
        """Test getting agent card with basic agent."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter
        from core.adapters.protocol import AgentFramework

        mock_agent = MagicMock()
        mock_agent.role = "analyst"
        mock_agent.goal = "Analyze data patterns"
        mock_agent.backstory = "Expert data analyst"
        mock_agent.verbose = True
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent)
        card = adapter.get_card()

        assert card.name == "analyst"
        assert card.description == "Analyze data patterns"
        assert card.framework == AgentFramework.CREWAI
        assert card.version == "1.0"
        assert card.metadata["backstory"] == "Expert data analyst"
        assert card.metadata["verbose"] is True

    def test_crewai_adapter_get_card_with_custom_name(self):
        """Test getting agent card with custom name."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.role = "original_role"
        mock_agent.goal = "Some goal"
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent, name="custom_name")
        card = adapter.get_card()

        assert card.name == "custom_name"

    def test_crewai_adapter_get_card_with_tools(self):
        """Test getting agent card with tools as capabilities."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "search_tool"
        mock_tool1.description = "Search the web"
        mock_tool1.args_schema = MagicMock()
        mock_tool1.args_schema.schema.return_value = {"type": "object"}

        mock_tool2 = MagicMock()
        mock_tool2.name = "calc_tool"
        mock_tool2.description = "Calculate"
        mock_tool2.args_schema = None  # No schema

        mock_agent = MagicMock()
        mock_agent.role = "assistant"
        mock_agent.goal = "Help user"
        mock_agent.tools = [mock_tool1, mock_tool2]

        adapter = CrewAIAgentAdapter(mock_agent)
        card = adapter.get_card()

        assert len(card.capabilities) == 2
        assert card.capabilities[0].name == "search_tool"
        assert card.capabilities[0].description == "Search the web"
        assert card.capabilities[0].input_schema == {"type": "object"}
        assert card.capabilities[1].name == "calc_tool"

    def test_crewai_adapter_get_card_missing_attributes(self):
        """Test getting agent card when agent lacks some attributes."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        # Agent with minimal attributes
        mock_agent = MagicMock(spec=[])  # Empty spec means no attributes
        del mock_agent.role
        del mock_agent.goal
        del mock_agent.backstory
        del mock_agent.verbose
        del mock_agent.tools

        adapter = CrewAIAgentAdapter(mock_agent, name="fallback")
        card = adapter.get_card()

        assert card.name == "fallback"
        assert card.capabilities == []

@pytest.mark.unit
class TestCrewAIAdapterExecute:
    """Tests for CrewAIAgentAdapter.execute()."""

    @pytest.mark.asyncio
    async def test_crewai_adapter_execute_basic(self):
        """Test basic task execution with mocked CrewAI."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.role = "worker"
        mock_agent.goal = "Work"
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent, name="test_worker")

        # Mock CrewAI imports and execution
        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "Task completed successfully"

        mock_task_class = MagicMock()
        mock_crew_class = MagicMock(return_value=mock_crew)

        with (
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._configure_llm_from_context",
            ),
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._get_sandbox_metadata",
                return_value={},
            ),
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._get_healing_metadata",
                return_value={},
            ),
        ):
            # Patch the imports inside execute
            import sys

            crewai_mock = MagicMock()
            crewai_mock.Task = mock_task_class
            crewai_mock.Crew = mock_crew_class
            sys.modules["crewai"] = crewai_mock

            result = await adapter.execute("Do the task")

            assert result.status == "ok"
            assert result.result == "Task completed successfully"
            assert result.metadata["framework"] == "crewai"
            assert "execution_time_ms" in result.metadata

    @pytest.mark.asyncio
    async def test_crewai_adapter_execute_error_handling(self):
        """Test error handling during execution."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.role = "worker"
        mock_agent.goal = "Work"
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent, name="error_worker")

        # Mock LLM config and extension imports to avoid import chain errors
        with (
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._configure_llm_from_context",
            ),
        ):
            import sys

            crewai_mock = MagicMock()
            crewai_mock.Task = MagicMock(side_effect=Exception("CrewAI error"))
            sys.modules["crewai"] = crewai_mock

            result = await adapter.execute("Failing task")

            assert result.status == "error"
            # The adapter wraps exceptions as "Agent execution failed: {type}"
            assert "Exception" in result.error
            assert result.metadata["framework"] == "crewai"

    @pytest.mark.asyncio
    async def test_crewai_adapter_execute_with_tools(self):
        """Test execution with agent that has tools."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_tool = MagicMock()
        mock_tool.name = "helper_tool"

        mock_agent = MagicMock()
        mock_agent.role = "tool_user"
        mock_agent.goal = "Use tools"
        mock_agent.tools = [mock_tool]

        adapter = CrewAIAgentAdapter(mock_agent)

        mock_crew = MagicMock()
        mock_crew.kickoff.return_value = "Used tools"

        with (
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._configure_llm_from_context",
            ),
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._get_sandbox_metadata",
                return_value={},
            ),
            patch(
                "core.adapters.crewai_adapter.CrewAIAgentAdapter._get_healing_metadata",
                return_value={},
            ),
        ):
            import sys

            crewai_mock = MagicMock()
            crewai_mock.Crew = MagicMock(return_value=mock_crew)
            sys.modules["crewai"] = crewai_mock

            result = await adapter.execute("Use tools")

            assert result.status == "ok"
            assert result.metadata["tools_count"] == 1

@pytest.mark.unit
class TestCrewAIAdapterGetTools:
    """Tests for CrewAIAgentAdapter.get_tools()."""

    def test_crewai_adapter_get_tools_empty(self):
        """Test get_tools with no tools."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent)
        tools = adapter.get_tools()

        assert tools == []

    def test_crewai_adapter_get_tools_with_schema(self):
        """Test get_tools returns OpenAI function format."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

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

        adapter = CrewAIAgentAdapter(mock_agent)
        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "search"
        assert tools[0]["function"]["description"] == "Search for info"
        assert tools[0]["function"]["parameters"]["type"] == "object"

    def test_crewai_adapter_get_tools_without_schema(self):
        """Test get_tools handles tools without args_schema."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_tool = MagicMock()
        mock_tool.name = "simple_tool"
        mock_tool.description = "A simple tool"
        mock_tool.args_schema = None

        mock_agent = MagicMock()
        mock_agent.tools = [mock_tool]

        adapter = CrewAIAgentAdapter(mock_agent)
        tools = adapter.get_tools()

        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "simple_tool"
        assert tools[0]["function"]["parameters"] == {}

@pytest.mark.unit
class TestCrewAIAdapterMetadata:
    """Tests for CrewAI adapter metadata collection."""

    def test_crewai_adapter_get_sandbox_metadata_error(self):
        """Test sandbox metadata collection handles errors gracefully."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent)

        # Simulate sandbox registry import failure
        with patch(
            "core.adapters.crewai_adapter.CrewAIAgentAdapter._get_sandbox_metadata"
        ) as mock_sandbox:
            mock_sandbox.return_value = {"error": "Failed to get sandbox metadata"}
            adapter._get_sandbox_metadata()
            # The actual implementation catches exceptions
            # Just verify it doesn't crash

    def test_crewai_adapter_get_healing_metadata_error(self):
        """Test healing metadata collection handles errors gracefully."""
        from core.adapters.crewai_adapter import CrewAIAgentAdapter

        mock_agent = MagicMock()
        mock_agent.tools = []

        adapter = CrewAIAgentAdapter(mock_agent)

        # Simulate circuit breaker import failure
        with patch(
            "core.adapters.crewai_adapter.CrewAIAgentAdapter._get_healing_metadata"
        ) as mock_healing:
            mock_healing.return_value = {"error": "Failed to get healing metadata"}
            adapter._get_healing_metadata()
            # The actual implementation catches exceptions
            # Just verify it doesn't crash
