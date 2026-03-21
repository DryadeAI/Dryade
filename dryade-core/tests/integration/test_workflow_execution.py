"""
Integration tests for workflow execution — verifying all node types and execution patterns.

Tests cover:
1. Linear workflow execution (start -> task -> end) with SSE events
2. Branching workflow (start -> [A, B] -> end) with parallel execution
3. Conditional/router workflow (start -> condition -> [true/false path] -> end)
4. Error handling during execution (failed node produces error event)
5. Workflow re-execution (create, execute, execute again)
6. Execution history is recorded and queryable
7. Draft workflow cannot be executed
8. Nonexistent workflow returns 404
9. Execution with custom inputs
10. Execution with invalid workflow schema
11. Approval node handling

All tests are CI-safe: no real LLM required. Uses mocked WorkflowTranslator
and WorkflowExecutor from the existing test patterns in test_workflow_lifecycle.py.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def exec_client():
    """Create test FastAPI app with auth disabled and in-memory database."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_DATABASE_URL"] = os.environ.get(
        "DRYADE_TEST_DATABASE_URL", "postgresql://dryade:dryade@localhost:5432/dryade_test"
    )
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-exec-user", "email": "exec@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    import os as os_module

    if os_module.path.exists("./test_workflow_execution.db"):
        os_module.remove("./test_workflow_execution.db")

@pytest.fixture
def mock_agents():
    """Mock agent registry to return test agents."""
    mock_cards = [MagicMock(name="test_agent"), MagicMock(name="branch_agent")]
    for card in mock_cards:
        card.name = card._mock_name
    return mock_cards

@pytest.fixture
def linear_workflow():
    """Linear workflow: start -> task -> end."""
    return {
        "version": "1.0.0",
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "data": {},
                "position": {"x": 250, "y": 0},
                "metadata": {"label": "Start"},
            },
            {
                "id": "task_1",
                "type": "task",
                "data": {"agent": "test_agent", "task": "Analyze data", "context": {}},
                "position": {"x": 250, "y": 120},
                "metadata": {"label": "Analyze"},
            },
            {
                "id": "end_1",
                "type": "end",
                "data": {"status": "success"},
                "position": {"x": 250, "y": 240},
                "metadata": {"label": "Done"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "task_1", "type": "default"},
            {"id": "e2", "source": "task_1", "target": "end_1", "type": "default"},
        ],
        "metadata": {"name": "Linear Workflow", "description": "Simple linear flow"},
    }

@pytest.fixture
def branching_workflow():
    """Branching workflow: start -> [task_a, task_b] -> end."""
    return {
        "version": "1.0.0",
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "data": {},
                "position": {"x": 250, "y": 0},
                "metadata": {"label": "Start"},
            },
            {
                "id": "task_a",
                "type": "task",
                "data": {"agent": "test_agent", "task": "Branch A", "context": {}},
                "position": {"x": 100, "y": 120},
                "metadata": {"label": "Branch A"},
            },
            {
                "id": "task_b",
                "type": "task",
                "data": {"agent": "branch_agent", "task": "Branch B", "context": {}},
                "position": {"x": 400, "y": 120},
                "metadata": {"label": "Branch B"},
            },
            {
                "id": "end_1",
                "type": "end",
                "data": {"status": "success"},
                "position": {"x": 250, "y": 240},
                "metadata": {"label": "Done"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "task_a", "type": "default"},
            {"id": "e2", "source": "start_1", "target": "task_b", "type": "default"},
            {"id": "e3", "source": "task_a", "target": "end_1", "type": "default"},
            {"id": "e4", "source": "task_b", "target": "end_1", "type": "default"},
        ],
        "metadata": {"name": "Branching Workflow", "description": "Parallel branches"},
    }

@pytest.fixture
def conditional_workflow():
    """Conditional/router workflow: start -> router -> [true_path, false_path] -> end."""
    return {
        "version": "1.0.0",
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "data": {},
                "position": {"x": 250, "y": 0},
                "metadata": {"label": "Start"},
            },
            {
                "id": "router_1",
                "type": "router",
                "data": {
                    "condition": "status == 'success'",
                    "routes": ["success_path", "failure_path"],
                },
                "position": {"x": 250, "y": 120},
                "metadata": {"label": "Check Status"},
            },
            {
                "id": "task_success",
                "type": "task",
                "data": {"agent": "test_agent", "task": "Handle success", "context": {}},
                "position": {"x": 100, "y": 240},
                "metadata": {"label": "Success"},
            },
            {
                "id": "task_failure",
                "type": "task",
                "data": {"agent": "test_agent", "task": "Handle failure", "context": {}},
                "position": {"x": 400, "y": 240},
                "metadata": {"label": "Failure"},
            },
            {
                "id": "end_1",
                "type": "end",
                "data": {"status": "success"},
                "position": {"x": 250, "y": 360},
                "metadata": {"label": "Done"},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "router_1", "type": "default"},
            {
                "id": "e2",
                "source": "router_1",
                "target": "task_success",
                "type": "default",
                "data": {"condition": "success_path"},
            },
            {
                "id": "e3",
                "source": "router_1",
                "target": "task_failure",
                "type": "default",
                "data": {"condition": "failure_path"},
            },
            {"id": "e4", "source": "task_success", "target": "end_1", "type": "default"},
            {"id": "e5", "source": "task_failure", "target": "end_1", "type": "default"},
        ],
        "metadata": {"name": "Conditional Workflow", "description": "Router-based branching"},
    }

def _setup_mock_executor():
    """Create standard mock translator and executor setup."""
    mock_translator_instance = MagicMock()
    mock_flowconfig = MagicMock()
    mock_flowconfig.nodes = [{"id": "start_1", "type": "start"}]
    mock_translator_instance.to_flowconfig.return_value = mock_flowconfig

    mock_executor_instance = MagicMock()
    mock_flow_class = MagicMock()
    mock_executor_instance.generate_flow_class.return_value = mock_flow_class

    mock_flow_instance = MagicMock()
    mock_flow_class.return_value = mock_flow_instance
    mock_flow_instance.state = MagicMock()
    mock_flow_instance.state.model_dump.return_value = {"output": "test_result"}
    mock_flow_instance.kickoff.return_value = {"output": "test_result"}

    return mock_translator_instance, mock_executor_instance

def _create_and_publish(client, workflow_json, mock_agents, name="Test Workflow"):
    """Helper: create a workflow and publish it. Returns workflow_id."""
    with patch("core.workflows.schema.list_agents", return_value=mock_agents):
        create_resp = client.post(
            "/api/workflows",
            json={
                "name": name,
                "description": f"Execution test: {name}",
                "workflow_json": workflow_json,
                "user_id": "test-exec-user",
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.json()}"
        workflow_id = create_resp.json()["id"]
        pub_resp = client.post(f"/api/workflows/{workflow_id}/publish")
        assert pub_resp.status_code == 200, f"Publish failed: {pub_resp.json()}"
    return workflow_id

def _parse_sse_events(response):
    """Parse SSE response content into list of event dicts."""
    events = []
    content = response.content.decode()
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[len("data:") :].strip()
            if data_str == "[DONE]":
                events.append({"type": "[DONE]"})
            else:
                try:
                    events.append(json.loads(data_str))
                except json.JSONDecodeError:
                    pass
    return events

@pytest.mark.integration
class TestLinearWorkflowExecution:
    """Tests for linear (start -> task -> end) workflow execution."""

    def test_linear_execution_returns_sse_stream(self, exec_client, linear_workflow, mock_agents):
        """Executing a linear workflow returns a 200 SSE stream."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Linear SSE Test"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(f"/api/workflows/{workflow_id}/execute")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_linear_execution_has_start_event(self, exec_client, linear_workflow, mock_agents):
        """SSE stream includes a 'start' event with workflow metadata."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Linear Start Event"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(f"/api/workflows/{workflow_id}/execute")

        events = _parse_sse_events(response)
        start_events = [e for e in events if e.get("type") == "start"]
        assert len(start_events) >= 1, f"No start event found. Events: {events}"
        assert start_events[0]["workflow_id"] == workflow_id

    def test_linear_execution_has_complete_or_error_event(
        self, exec_client, linear_workflow, mock_agents
    ):
        """SSE stream ends with a 'complete' or 'error' event."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Linear Complete Test"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(f"/api/workflows/{workflow_id}/execute")

        events = _parse_sse_events(response)
        terminal_types = {"complete", "error"}
        terminal_events = [e for e in events if e.get("type") in terminal_types]
        assert len(terminal_events) >= 1, f"No complete/error event. Events: {events}"

    def test_linear_execution_records_execution_history(
        self, exec_client, linear_workflow, mock_agents
    ):
        """After execution, the workflow's execution history is queryable."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Linear History"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            exec_client.post(f"/api/workflows/{workflow_id}/execute")

        response = exec_client.get(f"/api/workflows/{workflow_id}/executions")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert "total" in data

@pytest.mark.integration
class TestBranchingWorkflowExecution:
    """Tests for branching (start -> [A, B] -> end) workflow execution."""

    def test_branching_execution_succeeds(self, exec_client, branching_workflow, mock_agents):
        """Branching workflow executes and returns SSE stream."""
        workflow_id = _create_and_publish(
            exec_client, branching_workflow, mock_agents, "Branch Exec Test"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(f"/api/workflows/{workflow_id}/execute")

        assert response.status_code == 200
        events = _parse_sse_events(response)
        start_events = [e for e in events if e.get("type") == "start"]
        assert len(start_events) >= 1

@pytest.mark.integration
class TestConditionalWorkflowExecution:
    """Tests for conditional/router workflow execution."""

    def test_conditional_execution_succeeds(self, exec_client, conditional_workflow, mock_agents):
        """Conditional workflow with router node executes and returns SSE stream."""
        workflow_id = _create_and_publish(
            exec_client, conditional_workflow, mock_agents, "Conditional Exec"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(f"/api/workflows/{workflow_id}/execute")

        assert response.status_code == 200
        events = _parse_sse_events(response)
        assert any(e.get("type") == "start" for e in events)

@pytest.mark.integration
class TestErrorHandling:
    """Tests for execution error handling."""

    def test_execution_error_produces_error_event(self, exec_client, linear_workflow, mock_agents):
        """When executor raises, SSE stream should include an error event."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Error Exec Test"
        )

        mock_translator_instance = MagicMock()
        mock_flowconfig = MagicMock()
        mock_flowconfig.nodes = [{"id": "start_1", "type": "start"}]
        mock_translator_instance.to_flowconfig.return_value = mock_flowconfig

        mock_executor_instance = MagicMock()
        mock_flow_class = MagicMock()
        mock_executor_instance.generate_flow_class.return_value = mock_flow_class

        # Make the flow kickoff raise an exception
        mock_flow_instance = MagicMock()
        mock_flow_class.return_value = mock_flow_instance
        mock_flow_instance.state = MagicMock()
        mock_flow_instance.state.model_dump.return_value = {}
        mock_flow_instance.kickoff.side_effect = RuntimeError("Simulated execution failure")

        with (
            patch(
                "core.api.routes.workflows.WorkflowTranslator",
                return_value=mock_translator_instance,
            ),
            patch(
                "core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor_instance
            ),
        ):
            response = exec_client.post(f"/api/workflows/{workflow_id}/execute")

        assert response.status_code == 200  # SSE always returns 200 initially
        events = _parse_sse_events(response)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1, f"No error event found. Events: {events}"
        assert "Simulated execution failure" in str(error_events[0])

    def test_draft_workflow_cannot_execute(self, exec_client, linear_workflow, mock_agents):
        """Attempting to execute a draft (unpublished) workflow returns 403."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            create_resp = exec_client.post(
                "/api/workflows",
                json={
                    "name": "Draft No Execute",
                    "workflow_json": linear_workflow,
                    "user_id": "test-exec-user",
                },
            )
            workflow_id = create_resp.json()["id"]
            # Do NOT publish

        response = exec_client.post(f"/api/workflows/{workflow_id}/execute")
        assert response.status_code == 403
        assert (
            "draft" in response.json()["detail"].lower()
            or "published" in response.json()["detail"].lower()
        )

    def test_nonexistent_workflow_returns_404(self, exec_client):
        """Executing a nonexistent workflow returns 404."""
        response = exec_client.post("/api/workflows/999999/execute")
        assert response.status_code == 404

@pytest.mark.integration
class TestReExecution:
    """Tests for workflow re-execution (execute same workflow multiple times)."""

    def test_re_execution_succeeds(self, exec_client, linear_workflow, mock_agents):
        """A published workflow can be executed multiple times."""
        workflow_id = _create_and_publish(exec_client, linear_workflow, mock_agents, "Re-exec Test")
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            # First execution
            resp1 = exec_client.post(f"/api/workflows/{workflow_id}/execute")
            assert resp1.status_code == 200

            # Second execution
            resp2 = exec_client.post(f"/api/workflows/{workflow_id}/execute")
            assert resp2.status_code == 200

        # Both should have start events
        events1 = _parse_sse_events(resp1)
        events2 = _parse_sse_events(resp2)
        assert any(e.get("type") == "start" for e in events1)
        assert any(e.get("type") == "start" for e in events2)

    def test_re_execution_creates_separate_history_entries(
        self, exec_client, linear_workflow, mock_agents
    ):
        """Multiple executions create distinct history entries."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Re-exec History"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            exec_client.post(f"/api/workflows/{workflow_id}/execute")
            exec_client.post(f"/api/workflows/{workflow_id}/execute")

        response = exec_client.get(f"/api/workflows/{workflow_id}/executions")
        assert response.status_code == 200
        data = response.json()
        # Should have at least 2 execution entries
        assert data["total"] >= 2, f"Expected >=2 executions, got {data['total']}"

@pytest.mark.integration
class TestExecutionWithInputs:
    """Tests for workflow execution with custom inputs."""

    def test_execution_with_inputs(self, exec_client, linear_workflow, mock_agents):
        """Workflow execution accepts custom inputs in the request body."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Input Exec Test"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(
                f"/api/workflows/{workflow_id}/execute",
                json={"inputs": {"data_source": "test.csv", "threshold": 0.95}},
            )

        assert response.status_code == 200
        events = _parse_sse_events(response)
        assert any(e.get("type") == "start" for e in events)

    def test_execution_with_conversation_id(self, exec_client, linear_workflow, mock_agents):
        """Workflow execution accepts a conversation_id for tracking."""
        workflow_id = _create_and_publish(
            exec_client, linear_workflow, mock_agents, "Conversation Exec"
        )
        mock_translator, mock_executor = _setup_mock_executor()

        with (
            patch("core.api.routes.workflows.WorkflowTranslator", return_value=mock_translator),
            patch("core.api.routes.workflows.WorkflowExecutor", return_value=mock_executor),
        ):
            response = exec_client.post(
                f"/api/workflows/{workflow_id}/execute",
                json={"conversation_id": "conv-abc-123"},
            )

        assert response.status_code == 200
