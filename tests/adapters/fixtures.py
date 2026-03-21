"""
Reusable agent mock fixtures for adapter testing.

This module re-exports fixtures for convenience when importing
from external modules. All fixtures are defined in conftest.py
for proper pytest discovery.

Usage:
    # In pytest tests, fixtures are auto-discovered from conftest.py
    def test_example(mock_crewai_agent):
        assert mock_crewai_agent.role == "Test Agent"

    # For external imports (outside pytest)
    from tests.adapters.fixtures import create_mock_crewai_agent
    agent = create_mock_crewai_agent()

Provides AsyncMock-based fixtures for testing all adapter types:
- CrewAI agents
- LangChain agents
- A2A remote agents
- Generic mock tools

All async methods use AsyncMock to ensure proper awaitable behavior.
"""

from unittest.mock import AsyncMock, MagicMock

from core.adapters.protocol import AgentResult

def create_mock_crewai_agent():
    """Create a mock CrewAI Agent for testing CrewAIAgentAdapter.

    The mock simulates a CrewAI Agent with:
    - role: "Test Agent"
    - goal: "Complete test tasks"
    - backstory: "A test agent for unit testing"
    - tools: Empty list
    - verbose: False

    Returns:
        MagicMock: Mock CrewAI Agent instance
    """
    agent = MagicMock()
    agent.role = "Test Agent"
    agent.goal = "Complete test tasks"
    agent.backstory = "A test agent for unit testing"
    agent.tools = []
    agent.verbose = False

    return agent

def create_mock_crewai_execution():
    """Create mocks for CrewAI Crew and Task execution.

    Returns:
        dict: Contains 'crew_mock' and 'task_mock' for patching
    """
    crew_mock = MagicMock()
    crew_mock.kickoff.return_value = "Task completed successfully"

    task_mock = MagicMock()

    return {
        "crew_mock": crew_mock,
        "task_mock": task_mock,
        "result": "Task completed successfully",
    }

def create_mock_langchain_agent():
    """Create a mock LangChain agent for testing LangChainAgentAdapter.

    The mock simulates a LangChain AgentExecutor with:
    - ainvoke(): AsyncMock returning dict with output
    - arun(): AsyncMock returning string result
    - tools: Empty list

    Returns:
        MagicMock: Mock LangChain AgentExecutor instance
    """
    agent = MagicMock()

    # LangGraph-style ainvoke (returns dict)
    agent.ainvoke = AsyncMock(return_value={"output": "LangChain result", "intermediate_steps": []})

    # LangChain-style arun (returns string)
    agent.arun = AsyncMock(return_value="LangChain result")

    # Sync fallback
    agent.run = MagicMock(return_value="LangChain sync result")

    # Empty tools list
    agent.tools = []

    return agent

def create_mock_a2a_agent():
    """Create a mock A2A remote agent client.

    The mock simulates an A2A client with:
    - execute(): AsyncMock returning AgentResult
    - get_card(): Returns agent capability card

    Returns:
        MagicMock: Mock A2A client instance
    """
    agent = MagicMock()

    # A2A execute returns AgentResult
    agent.execute = AsyncMock(
        return_value=AgentResult(
            result="A2A remote result",
            status="ok",
            metadata={"framework": "a2a", "remote": True},
        )
    )

    # A2A agent card
    agent.get_card = MagicMock(
        return_value={
            "name": "Remote A2A Agent",
            "description": "A remote agent via A2A protocol",
            "version": "1.0",
            "capabilities": [],
        }
    )

    return agent

def create_mock_registry():
    """Create a fresh AgentRegistry instance.

    Returns:
        AgentRegistry: Fresh registry instance
    """
    from core.adapters.registry import AgentRegistry

    return AgentRegistry()

def create_mock_tool():
    """Create a generic AsyncMock tool function.

    The tool is configured to:
    - Return {"status": "ok", "result": "tool result"} by default
    - Be awaitable (AsyncMock)
    - Track call assertions

    Returns:
        AsyncMock: Awaitable mock tool function
    """
    tool = AsyncMock(return_value={"status": "ok", "result": "tool result"})
    tool.name = "mock_tool"
    tool.description = "A mock tool for testing"
    return tool

def create_mock_tool_with_schema():
    """Create a mock tool with args_schema for schema extraction tests.

    Returns:
        MagicMock: Mock tool with args_schema attribute
    """
    tool = MagicMock()
    tool.name = "schema_tool"
    tool.description = "A tool with schema"

    # Mock Pydantic-style args_schema
    schema_mock = MagicMock()
    schema_mock.schema.return_value = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }
    tool.args_schema = schema_mock

    return tool

# Export names for backwards compatibility (using factory functions)
mock_crewai_agent = create_mock_crewai_agent
mock_crewai_execution = create_mock_crewai_execution
mock_langchain_agent = create_mock_langchain_agent
mock_a2a_agent = create_mock_a2a_agent
mock_registry = create_mock_registry
mock_tool = create_mock_tool
mock_tool_with_schema = create_mock_tool_with_schema

__all__ = [
    # Factory functions (preferred)
    "create_mock_crewai_agent",
    "create_mock_crewai_execution",
    "create_mock_langchain_agent",
    "create_mock_a2a_agent",
    "create_mock_registry",
    "create_mock_tool",
    "create_mock_tool_with_schema",
    # Aliases for backwards compatibility
    "mock_crewai_agent",
    "mock_crewai_execution",
    "mock_langchain_agent",
    "mock_a2a_agent",
    "mock_registry",
    "mock_tool",
    "mock_tool_with_schema",
]
