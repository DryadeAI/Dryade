"""
Integration tests for flows API routes.

Tests cover:
1. List all flows
2. Get flow by name
3. Flow not found (404)
4. Get flow ReactFlow graph
5. Execute flow (mocked)
6. Execute flow streaming (mocked)
7. Get execution status
8. Resume execution
9. Flow validation errors

Target: ~120 LOC
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def flows_client():
    """Create test FastAPI app with mocked flow registry."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"
    os.environ["DRYADE_DATABASE_URL"] = os.environ.get(
        "DRYADE_TEST_DATABASE_URL",
        "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
    )

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-flows", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_flows.db"):
        os.remove("./test_flows.db")

@pytest.fixture
def mock_flow_registry():
    """Mock flow registry with test flows."""
    mock_flow_class = MagicMock()
    mock_flow_class.__name__ = "TestFlow"
    mock_flow_class.kickoff = MagicMock(return_value={"result": "completed"})

    mock_state = MagicMock()
    mock_state.test_input = None
    mock_flow_instance = MagicMock()
    mock_flow_instance.state = mock_state
    mock_flow_instance.kickoff.return_value = {"output": "flow result"}
    mock_flow_class.return_value = mock_flow_instance

    return {
        "test_flow": {
            "class": mock_flow_class,
            "description": "A test flow for integration testing",
            "entry_point": "start_node",
        }
    }

@pytest.fixture
def mock_flow_info():
    """Mock flow info data."""
    return {
        "nodes": ["start_node", "process_node", "end_node"],
        "edges": [
            {"source": "start_node", "target": "process_node"},
            {"source": "process_node", "target": "end_node"},
        ],
    }

@pytest.fixture
def mock_reactflow_graph():
    """Mock ReactFlow graph data."""
    return {
        "nodes": [
            {"id": "start_1", "type": "start", "position": {"x": 100, "y": 50}},
            {"id": "task_1", "type": "task", "position": {"x": 100, "y": 150}},
        ],
        "edges": [{"id": "e1", "source": "start_1", "target": "task_1"}],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }

@pytest.mark.integration
class TestFlowsListEndpoint:
    """Tests for GET /api/flows endpoint."""

    def test_list_flows_empty(self, flows_client):
        """Test listing flows when none registered."""
        with patch("core.api.routes.flows.FLOW_REGISTRY", {}):
            response = flows_client.get("/api/flows")
            assert response.status_code == 200
            data = response.json()
            assert "flows" in data
            assert data["flows"] == []

    def test_list_flows_returns_registered(self, flows_client, mock_flow_registry, mock_flow_info):
        """Test listing flows returns registered flows."""
        with (
            patch("core.api.routes.flows.FLOW_REGISTRY", mock_flow_registry),
            patch("core.api.routes.flows.get_flow_info", return_value=mock_flow_info),
        ):
            response = flows_client.get("/api/flows")
            assert response.status_code == 200
            data = response.json()
            assert "flows" in data
            assert len(data["flows"]) == 1
            assert data["flows"][0]["name"] == "test_flow"
            assert data["flows"][0]["description"] == "A test flow for integration testing"

@pytest.mark.integration
class TestFlowsGetEndpoint:
    """Tests for GET /api/flows/{name} endpoint."""

    def test_get_flow_by_name(self, flows_client, mock_flow_registry, mock_flow_info):
        """Test getting flow details by name."""
        with (
            patch("core.api.routes.flows.FLOW_REGISTRY", mock_flow_registry),
            patch("core.api.routes.flows.get_flow_info", return_value=mock_flow_info),
        ):
            response = flows_client.get("/api/flows/test_flow")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "test_flow"
            assert data["description"] == "A test flow for integration testing"
            assert "nodes" in data

    def test_get_flow_not_found(self, flows_client):
        """Test 404 when flow not found."""
        with patch("core.api.routes.flows.FLOW_REGISTRY", {}):
            response = flows_client.get("/api/flows/nonexistent_flow")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

@pytest.mark.integration
class TestFlowsGraphEndpoint:
    """Tests for GET /api/flows/{name}/graph endpoint."""

    def test_get_flow_graph(self, flows_client, mock_flow_registry, mock_reactflow_graph):
        """Test getting ReactFlow visualization."""
        with (
            patch("core.api.routes.flows.FLOW_REGISTRY", mock_flow_registry),
            patch("core.api.routes.flows.flow_to_reactflow", return_value=mock_reactflow_graph),
        ):
            response = flows_client.get("/api/flows/test_flow/graph")
            assert response.status_code == 200
            data = response.json()
            assert "nodes" in data
            assert "edges" in data
            assert "viewport" in data
            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 1

    def test_get_graph_flow_not_found(self, flows_client):
        """Test 404 when getting graph for nonexistent flow."""
        with patch("core.api.routes.flows.FLOW_REGISTRY", {}):
            response = flows_client.get("/api/flows/nonexistent/graph")
            assert response.status_code == 404

@pytest.mark.integration
class TestFlowsExecuteEndpoint:
    """Tests for POST /api/flows/{name}/execute endpoint."""

    def test_execute_flow_success(self, flows_client, mock_flow_registry):
        """Test executing a flow successfully."""
        with patch("core.api.routes.flows.FLOW_REGISTRY", mock_flow_registry):
            response = flows_client.post(
                "/api/flows/test_flow/execute", json={"inputs": {"test_input": "hello"}}
            )
            assert response.status_code == 200
            data = response.json()
            assert "execution_id" in data
            assert data["status"] in ["complete", "resumed"]
            assert "result" in data

    def test_execute_flow_not_found(self, flows_client):
        """Test 404 when executing nonexistent flow."""
        with patch("core.api.routes.flows.FLOW_REGISTRY", {}):
            response = flows_client.post("/api/flows/nonexistent/execute", json={"inputs": {}})
            assert response.status_code == 404

@pytest.mark.integration
class TestFlowsExecutionStatusEndpoint:
    """Tests for GET /api/flows/executions/{execution_id} endpoint."""

    def test_get_execution_status(self, flows_client):
        """Test getting execution status."""
        from core.api.routes.flows import _executions

        test_exec_id = "test-exec-123"
        _executions[test_exec_id] = {"status": "complete", "result": {"output": "done"}}

        response = flows_client.get(f"/api/flows/executions/{test_exec_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == test_exec_id
        assert data["status"] == "complete"

        # Cleanup
        del _executions[test_exec_id]

    def test_get_execution_not_found(self, flows_client):
        """Test 404 when execution not found."""
        response = flows_client.get("/api/flows/executions/nonexistent-exec")
        assert response.status_code == 404

@pytest.mark.integration
class TestFlowsResumeEndpoint:
    """Tests for POST /api/flows/executions/{execution_id}/resume endpoint."""

    def test_resume_execution_not_found(self, flows_client):
        """Test 404 when resuming nonexistent execution."""
        response = flows_client.post("/api/flows/executions/nonexistent/resume")
        assert response.status_code == 404

    def test_resume_flow_not_found(self, flows_client):
        """Test 400 when execution has no associated flow."""
        from core.api.routes.flows import _executions

        test_exec_id = "test-resume-123"
        _executions[test_exec_id] = {"status": "paused", "flow_name": None}

        response = flows_client.post(f"/api/flows/executions/{test_exec_id}/resume")
        assert response.status_code == 400

        # Cleanup
        del _executions[test_exec_id]

@pytest.mark.integration
class TestFlowsStreamingEndpoint:
    """Tests for POST /api/flows/{name}/execute/stream endpoint."""

    def test_execute_stream_flow_not_found(self, flows_client):
        """Test 404 when streaming execution for nonexistent flow."""
        with patch("core.api.routes.flows.FLOW_REGISTRY", {}):
            response = flows_client.post(
                "/api/flows/nonexistent/execute/stream", json={"inputs": {}}
            )
            assert response.status_code == 404
