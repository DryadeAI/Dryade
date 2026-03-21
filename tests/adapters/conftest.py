"""
pytest configuration for adapter unit tests.

Configures pytest-asyncio for async test support and provides
isolated registry state between tests.

Fixtures are defined in this file to ensure proper pytest discovery.
They are also exported from fixtures.py for external imports.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# pytest-asyncio is configured in pyproject.toml with asyncio_mode = "auto"
# No need to configure pytest_plugins here (deprecated for non-top-level conftest)

@pytest.fixture(autouse=True)
def clear_agent_registry():
    """Clear global agent registry before and after each test.

    This autouse fixture ensures test isolation by:
    1. Clearing the registry before the test runs
    2. Clearing it again after the test completes

    This prevents state leakage between tests when using
    the global registry singleton.
    """
    from core.adapters.registry import get_registry

    # Clear before test
    registry = get_registry()
    registry.clear()

    yield

    # Clear after test
    registry.clear()

@pytest.fixture
def isolated_registry():
    """Provide a fresh, isolated AgentRegistry instance.

    Unlike the global registry, this creates a new instance
    each time it's requested, ensuring complete isolation.

    Yields:
        AgentRegistry: Fresh registry instance
    """
    from core.adapters.registry import AgentRegistry

    registry = AgentRegistry()
    yield registry
    registry.clear()

# =============================================================================
# Agent Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_crewai_agent():
    """Provide a mock CrewAI Agent for testing CrewAIAgentAdapter.

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

@pytest.fixture
def mock_crewai_execution():
    """Provide mocks for CrewAI Crew and Task execution.

    This fixture patches the CrewAI imports to avoid needing
    the actual crewai package during tests.

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

@pytest.fixture
def mock_langchain_agent():
    """Provide a mock LangChain agent for testing LangChainAgentAdapter.

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

@pytest.fixture
def mock_a2a_agent():
    """Provide a mock A2A remote agent client.

    The mock simulates an A2A client with:
    - execute(): AsyncMock returning AgentResult
    - get_card(): Returns agent capability card

    Returns:
        MagicMock: Mock A2A client instance
    """
    from core.adapters.protocol import AgentResult

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

@pytest.fixture
def mock_registry():
    """Provide a fresh AgentRegistry instance per test.

    Unlike the autouse fixture that clears the global registry,
    this provides a completely separate registry instance.

    Yields:
        AgentRegistry: Fresh registry instance, cleared on teardown
    """
    from core.adapters.registry import AgentRegistry

    registry = AgentRegistry()
    yield registry
    registry.clear()

@pytest.fixture
def mock_tool():
    """Provide a generic AsyncMock tool function.

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

@pytest.fixture
def mock_tool_with_schema():
    """Provide a mock tool with args_schema for schema extraction tests.

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

@pytest.fixture
def all_mock_agents(
    mock_crewai_agent,
    mock_langchain_agent,
    mock_a2a_agent,
    mock_registry,
    mock_tool,
):
    """Provide all mock agents in a single dict.

    Returns:
        dict: All mock agents keyed by framework name
    """
    return {
        "crewai": mock_crewai_agent,
        "langchain": mock_langchain_agent,
        "a2a": mock_a2a_agent,
        "registry": mock_registry,
        "tool": mock_tool,
    }
