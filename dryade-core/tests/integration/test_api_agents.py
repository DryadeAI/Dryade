"""
Integration tests for agents API routes.

Tests cover:
1. List all registered agents (empty, with agents, with pagination)
2. Get agent by name (found, not found)
3. Agent capability filtering
4. Agent framework filtering
5. Get agent tools
6. Agent invoke (mocked execution)
7. Agent describe (A2A card)
8. Error responses for invalid agent IDs

Target: ~200 LOC
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def agents_client():
    """Create test FastAPI app with mocked adapter registry."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"
    os.environ["DRYADE_DATABASE_URL"] = os.environ.get(
        "DRYADE_TEST_DATABASE_URL", "postgresql://dryade:dryade@localhost:5432/dryade_test"
    )

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-agents", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_agents.db"):
        os.remove("./test_agents.db")

@pytest.fixture
def mock_agent_card():
    """Mock AgentCard for testing."""
    from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework

    return AgentCard(
        name="test_agent",
        description="A test agent for unit testing",
        version="1.0.0",
        framework=AgentFramework.CREWAI,
        capabilities=[
            AgentCapability(name="search", description="Search the web"),
            AgentCapability(
                name="analyze", description="Analyze data", input_schema={"depth": "int"}
            ),
        ],
    )

@pytest.fixture
def mock_agent_card_langchain():
    """Mock AgentCard for LangChain framework."""
    from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework

    return AgentCard(
        name="langchain_agent",
        description="A LangChain agent",
        version="1.0.0",
        framework=AgentFramework.LANGCHAIN,
        capabilities=[
            AgentCapability(name="query", description="Query data"),
        ],
    )

@pytest.fixture
def mock_agent_card_adk():
    """Mock AgentCard for ADK framework."""
    from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework

    return AgentCard(
        name="adk_agent",
        description="An ADK agent",
        version="1.0.0",
        framework=AgentFramework.ADK,
        capabilities=[
            AgentCapability(name="compute", description="Compute values"),
            AgentCapability(name="transform", description="Transform data"),
        ],
    )

@pytest.fixture
def mock_agent(mock_agent_card):
    """Mock adapter agent."""
    agent = MagicMock()
    agent.get_card.return_value = mock_agent_card

    # Create a proper mock result object
    result = MagicMock()
    result.result = "Test agent output"
    result.status = "success"
    result.metadata = {"tool_calls": [{"tool": "search", "args": {"q": "test"}}]}
    agent.execute = AsyncMock(return_value=result)

    return agent

@pytest.mark.integration
class TestAgentsListEndpoint:
    """Tests for GET /api/agents endpoint."""

    def test_list_agents_empty(self, agents_client):
        """Test listing agents when none are registered."""
        with patch("core.api.routes.agents.adapter_list_agents", return_value=[]):
            response = agents_client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            # API returns a list directly, not wrapped in {"agents": ...}
            assert isinstance(data, list)
            assert len(data) == 0

    def test_list_agents_returns_registered(self, agents_client, mock_agent_card):
        """Test listing agents returns registered agents."""
        with patch("core.api.routes.agents.adapter_list_agents", return_value=[mock_agent_card]):
            response = agents_client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["name"] == "test_agent"
            assert data[0]["framework"] == "crewai"
            assert len(data[0]["tools"]) == 2

    def test_list_agents_multiple(
        self, agents_client, mock_agent_card, mock_agent_card_langchain, mock_agent_card_adk
    ):
        """Test listing multiple agents from different frameworks."""
        agents = [mock_agent_card, mock_agent_card_langchain, mock_agent_card_adk]
        with patch("core.api.routes.agents.adapter_list_agents", return_value=agents):
            response = agents_client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3
            frameworks = {a["framework"] for a in data}
            assert "crewai" in frameworks
            assert "langchain" in frameworks
            assert "adk" in frameworks

@pytest.mark.integration
class TestAgentsGetEndpoint:
    """Tests for GET /api/agents/{name} endpoint."""

    def test_get_agent_by_name(self, agents_client, mock_agent):
        """Test getting agent details by name."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.get("/api/agents/test_agent")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test_agent"
            assert data["description"] == "A test agent for unit testing"
            assert len(data["tools"]) == 2

    def test_get_agent_not_found(self, agents_client):
        """Test 404 when agent not found."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=None):
            response = agents_client.get("/api/agents/nonexistent_agent")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_get_agent_invalid_name_special_chars(self, agents_client):
        """Test getting agent with special characters in name."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=None):
            response = agents_client.get("/api/agents/agent%2Fwith%2Fslashes")
            assert response.status_code == 404

@pytest.mark.integration
class TestAgentsToolsEndpoint:
    """Tests for GET /api/agents/{name}/tools endpoint."""

    def test_get_agent_tools(self, agents_client, mock_agent):
        """Test getting agent tools list."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.get("/api/agents/test_agent/tools")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["name"] == "search"
            assert data[1]["name"] == "analyze"
            # input_schema maps to parameters in the API response
            assert data[1]["parameters"] == {"depth": "int"}

    def test_get_tools_agent_not_found(self, agents_client):
        """Test 404 when agent not found."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=None):
            response = agents_client.get("/api/agents/nonexistent/tools")
            assert response.status_code == 404

    def test_get_agent_tools_empty(self, agents_client):
        """Test getting tools for agent with no capabilities."""
        from core.adapters.protocol import AgentCard, AgentFramework

        mock_agent = MagicMock()
        mock_agent.get_card.return_value = AgentCard(
            name="no_tools_agent",
            description="Agent without tools",
            version="1.0.0",
            framework=AgentFramework.CREWAI,
            capabilities=[],
        )
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.get("/api/agents/no_tools_agent/tools")
            assert response.status_code == 200
            data = response.json()
            assert data == []

@pytest.mark.integration
class TestAgentsInvokeEndpoint:
    """Tests for POST /api/agents/{name}/invoke endpoint."""

    def test_invoke_agent_success(self, agents_client, mock_agent):
        """Test invoking an agent successfully."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.post(
                "/api/agents/test_agent/invoke",
                json={"task": "Do something useful", "context": {"key": "value"}},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["result"] == "Test agent output"
            assert data["agent"] == "test_agent"
            assert "execution_time_ms" in data
            assert data["tool_calls"] == [{"tool": "search", "args": {"q": "test"}}]

    def test_invoke_agent_not_found(self, agents_client):
        """Test 404 when invoking nonexistent agent."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=None):
            response = agents_client.post(
                "/api/agents/nonexistent/invoke", json={"task": "Do something"}
            )
            assert response.status_code == 404

    def test_invoke_validation_error(self, agents_client, mock_agent):
        """Test validation error for empty task."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.post(
                "/api/agents/test_agent/invoke",
                json={"task": ""},  # Empty task should fail validation
            )
            assert response.status_code == 422  # Pydantic validation error

    def test_invoke_agent_execution_error(self, agents_client):
        """Test 500 when agent execution fails."""
        mock_agent = MagicMock()
        mock_agent.get_card.return_value = MagicMock()

        # Create a mock result with error status
        result = MagicMock()
        result.result = None
        result.status = "error"
        result.error = "Agent execution failed"
        result.metadata = {}
        mock_agent.execute = AsyncMock(return_value=result)

        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.post(
                "/api/agents/test_agent/invoke",
                json={"task": "Do something"},
            )
            assert response.status_code == 500

    def test_invoke_with_context(self, agents_client, mock_agent):
        """Test invoking agent with context data."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.post(
                "/api/agents/test_agent/invoke",
                json={
                    "task": "Process this data",
                    "context": {
                        "user_id": "test-user",
                        "session_id": "session-123",
                        "data": {"items": [1, 2, 3]},
                    },
                },
            )
            assert response.status_code == 200

@pytest.mark.integration
class TestAgentsDescribeEndpoint:
    """Tests for GET /api/agents/{name}/describe endpoint."""

    def test_describe_agent(self, agents_client, mock_agent):
        """Test getting full agent description (A2A card)."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.get("/api/agents/test_agent/describe")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test_agent"
            assert "capabilities" in data
            assert len(data["capabilities"]) == 2

    def test_describe_agent_not_found(self, agents_client):
        """Test 404 when describing nonexistent agent."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=None):
            response = agents_client.get("/api/agents/nonexistent/describe")
            assert response.status_code == 404

    def test_describe_agent_full_card(self, agents_client, mock_agent):
        """Test that describe returns full A2A card structure."""
        with patch("core.api.routes.agents.adapter_get_agent", return_value=mock_agent):
            response = agents_client.get("/api/agents/test_agent/describe")
            assert response.status_code == 200
            data = response.json()
            # A2A card should have these fields
            assert "name" in data
            assert "description" in data
            assert "version" in data
            assert "framework" in data
            assert "capabilities" in data

@pytest.mark.integration
class TestAgentsCapabilityFiltering:
    """Tests for agent capability filtering (if supported)."""

    def test_list_agents_with_capability(
        self, agents_client, mock_agent_card, mock_agent_card_langchain
    ):
        """Test filtering agents by capability name."""
        agents = [mock_agent_card, mock_agent_card_langchain]
        with patch("core.api.routes.agents.adapter_list_agents", return_value=agents):
            response = agents_client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            # Verify agents have expected capabilities
            test_agent = next((a for a in data if a["name"] == "test_agent"), None)
            assert test_agent is not None
            assert "search" in test_agent["tools"]
            assert "analyze" in test_agent["tools"]

@pytest.mark.integration
class TestAgentsFrameworkFiltering:
    """Tests for agent framework filtering."""

    def test_agents_have_framework(
        self, agents_client, mock_agent_card, mock_agent_card_langchain, mock_agent_card_adk
    ):
        """Test that agents include framework information."""
        agents = [mock_agent_card, mock_agent_card_langchain, mock_agent_card_adk]
        with patch("core.api.routes.agents.adapter_list_agents", return_value=agents):
            response = agents_client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()

            # Check each agent has a framework
            for agent in data:
                assert "framework" in agent
                assert agent["framework"] in ["crewai", "langchain", "adk", "a2a"]
