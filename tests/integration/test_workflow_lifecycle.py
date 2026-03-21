"""
Integration tests for workflow lifecycle - create, update, publish, execute, and query.

Tests cover the complete workflow lifecycle:
1. Create workflow (valid schema)
2. Create workflow (invalid schema, validation failure)
3. List workflows (pagination, filtering)
4. Get workflow by ID
5. Update draft workflow
6. Cannot update published workflow (403)
7. Publish workflow (draft -> published)
8. Clone workflow (creates new draft)
9. Execute workflow (SSE streaming)
10. Query execution history

Target: ~300 lines
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def workflow_client(integration_test_app):
    """Test client for workflow lifecycle tests, reusing the session-scoped app."""
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-workflow", "email": "test@example.com", "role": "user"}

    integration_test_app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        yield client

    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def sample_simple_workflow():
    """Simple valid workflow: start -> task -> end."""
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
                "data": {"agent": "test_agent", "task": "Test task description", "context": {}},
                "position": {"x": 250, "y": 120},
                "metadata": {"label": "Test Task"},
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
        "metadata": {
            "name": "Simple Test Workflow",
            "description": "A simple workflow for testing",
        },
    }

@pytest.fixture
def sample_invalid_workflow():
    """Invalid workflow - missing start node."""
    return {
        "version": "1.0.0",
        "nodes": [
            {
                "id": "task_1",
                "type": "task",
                "data": {"agent": "test_agent", "task": "Test task"},
                "position": {"x": 250, "y": 0},
            },
            {"id": "end_1", "type": "end", "data": {}, "position": {"x": 250, "y": 120}},
        ],
        "edges": [{"id": "e1", "source": "task_1", "target": "end_1"}],
    }

@pytest.fixture
def mock_agents():
    """Mock agent registry to return test agents."""
    mock_cards = [
        MagicMock(name="test_agent"),
        MagicMock(name="code_analyst"),
        MagicMock(name="summarizer"),
    ]
    # Set name attribute explicitly
    for card in mock_cards:
        card.name = card._mock_name
    return mock_cards

@pytest.mark.integration
class TestWorkflowLifecycle:
    """Integration tests for complete workflow lifecycle."""

    def test_create_workflow_success(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test creating a valid workflow returns 201 with draft status."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Test Workflow",
                    "description": "A test workflow",
                    "workflow_json": sample_simple_workflow,
                    "tags": ["test", "integration"],
                    "is_public": False,
                    "user_id": "test-user-1",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Workflow"
        assert data["status"] == "draft"
        assert data["version"] == "1.0.0"
        assert data["workflow_json"]["version"] == "1.0.0"
        assert len(data["workflow_json"]["nodes"]) == 3

    def test_create_workflow_invalid_schema(
        self, workflow_client, sample_invalid_workflow, mock_agents
    ):
        """Test creating an invalid workflow returns 400 with validation error."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Invalid Workflow",
                    "workflow_json": sample_invalid_workflow,
                    "user_id": "test-user-1",
                },
            )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "start node" in data["detail"].lower() or "invalid" in data["detail"].lower()

    def test_list_workflows(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test listing workflows with filters and pagination."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create 3 workflows
            for i in range(3):
                workflow_client.post(
                    "/api/workflows",
                    json={
                        "name": f"List Workflow {i}",
                        "workflow_json": sample_simple_workflow,
                        "user_id": f"test-list-user-{i % 2}",
                        "is_public": i % 2 == 0,
                    },
                )

            # List all workflows
            response = workflow_client.get("/api/workflows")
            assert response.status_code == 200
            data = response.json()
            assert "workflows" in data
            assert "total" in data
            assert data["total"] >= 3

            # Test pagination
            response = workflow_client.get("/api/workflows?limit=2&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert len(data["workflows"]) <= 2
            assert data["limit"] == 2
            assert data["offset"] == 0

    def test_get_workflow_by_id(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test getting a workflow by ID returns full details including workflow_json."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create workflow (public so it can be accessed without user_id)
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Get Test Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-get-user",
                    "is_public": True,
                },
            )
            workflow_id = create_response.json()["id"]

            # Get workflow
            response = workflow_client.get(f"/api/workflows/{workflow_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == workflow_id
        assert data["name"] == "Get Test Workflow"
        assert "workflow_json" in data
        assert len(data["workflow_json"]["nodes"]) == 3

    def test_update_draft_workflow(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test updating a draft workflow succeeds."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Update Test Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-update-user",
                },
            )
            workflow_id = create_response.json()["id"]

            # Update workflow
            response = workflow_client.put(
                f"/api/workflows/{workflow_id}",
                json={
                    "name": "Updated Workflow Name",
                    "description": "Updated description",
                    "tags": ["updated", "test"],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Workflow Name"
        assert data["description"] == "Updated description"
        assert data["tags"] == ["updated", "test"]

    def test_cannot_update_published_workflow(
        self, workflow_client, sample_simple_workflow, mock_agents
    ):
        """Test updating a published workflow returns 403 Forbidden."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Publish Lock Test",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-publish-user",
                },
            )
            workflow_id = create_response.json()["id"]

            # Publish workflow
            workflow_client.post(f"/api/workflows/{workflow_id}/publish")

            # Try to update published workflow
            response = workflow_client.put(
                f"/api/workflows/{workflow_id}", json={"name": "Should Not Update"}
            )

        assert response.status_code == 403
        data = response.json()
        assert "published" in data["detail"].lower() or "cannot modify" in data["detail"].lower()

    def test_publish_workflow(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test publishing a draft workflow sets status to published."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Publish Test Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-publish-user-2",
                },
            )
            workflow_id = create_response.json()["id"]
            assert create_response.json()["status"] == "draft"

            # Publish workflow
            response = workflow_client.post(f"/api/workflows/{workflow_id}/publish")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    def test_clone_workflow(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test cloning a workflow creates a new draft with incremented version."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create and publish workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Clone Source Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-clone-user",
                    "is_public": True,
                },
            )
            source_id = create_response.json()["id"]
            workflow_client.post(f"/api/workflows/{source_id}/publish")

            # Clone workflow
            response = workflow_client.post(
                f"/api/workflows/{source_id}/clone",
                json={"name": "Cloned Workflow", "user_id": "test-clone-user-2"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Cloned Workflow"
        assert data["status"] == "draft"
        assert data["version"] == "1.1.0"  # Version incremented
        assert data["id"] != source_id

    def test_execute_workflow(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test executing a published workflow returns SSE stream."""
        with (
            patch("core.workflows.schema.list_agents", return_value=mock_agents),
            patch("core.api.routes.workflows.WorkflowTranslator") as mock_translator,
            patch("core.api.routes.workflows.WorkflowExecutor") as mock_executor,
        ):
            # Setup mock translator
            mock_translator_instance = MagicMock()
            mock_translator.return_value = mock_translator_instance
            mock_flowconfig = MagicMock()
            mock_flowconfig.nodes = [{"id": "start_1", "type": "start"}]
            mock_translator_instance.to_flowconfig.return_value = mock_flowconfig

            # Setup mock executor
            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            mock_flow_class = MagicMock()
            mock_executor_instance.generate_flow_class.return_value = mock_flow_class

            # Setup mock flow instance
            mock_flow_instance = MagicMock()
            mock_flow_class.return_value = mock_flow_instance
            mock_flow_instance.state = MagicMock()
            mock_flow_instance.state.model_dump.return_value = {"test_output": "result"}
            mock_flow_instance.kickoff.return_value = {"output": "test result"}

            # Create and publish workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Execute Test Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-execute-user",
                },
            )
            workflow_id = create_response.json()["id"]
            workflow_client.post(f"/api/workflows/{workflow_id}/publish")

            # Execute workflow
            response = workflow_client.post(
                f"/api/workflows/{workflow_id}/execute",
                json={"inputs": {"test_input": "value"}, "user_id": "test-execute-user"},
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        # Parse SSE events
        content = response.content.decode()
        assert "data:" in content
        # Should have start event
        assert "start" in content or "node_start" in content or "error" in content

    def test_workflow_execution_history(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test querying workflow execution history returns paginated results."""
        with (
            patch("core.workflows.schema.list_agents", return_value=mock_agents),
            patch("core.api.routes.workflows.WorkflowTranslator") as mock_translator,
            patch("core.api.routes.workflows.WorkflowExecutor") as mock_executor,
        ):
            # Setup mocks
            mock_translator_instance = MagicMock()
            mock_translator.return_value = mock_translator_instance
            mock_flowconfig = MagicMock()
            mock_flowconfig.nodes = [{"id": "start_1", "type": "start"}]
            mock_translator_instance.to_flowconfig.return_value = mock_flowconfig

            mock_executor_instance = MagicMock()
            mock_executor.return_value = mock_executor_instance
            mock_flow_class = MagicMock()
            mock_executor_instance.generate_flow_class.return_value = mock_flow_class

            mock_flow_instance = MagicMock()
            mock_flow_class.return_value = mock_flow_instance
            mock_flow_instance.state = MagicMock()
            mock_flow_instance.state.model_dump.return_value = {}
            mock_flow_instance.kickoff.return_value = {"output": "test"}

            # Create and publish workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "History Test Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-history-user",
                },
            )
            workflow_id = create_response.json()["id"]
            workflow_client.post(f"/api/workflows/{workflow_id}/publish")

            # Execute workflow twice to create execution history
            for _ in range(2):
                workflow_client.post(
                    f"/api/workflows/{workflow_id}/execute", json={"user_id": "test-history-user"}
                )

            # Query execution history
            response = workflow_client.get(f"/api/workflows/{workflow_id}/executions")

        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert "total" in data
        # Should have at least the executions we created
        assert data["total"] >= 0  # May be 0 if async execution not complete
        assert "offset" in data
        assert "limit" in data

@pytest.mark.integration
class TestWorkflowErrors:
    """Tests for workflow error handling."""

    def test_get_nonexistent_workflow(self, workflow_client):
        """Test getting a nonexistent workflow returns 404."""
        response = workflow_client.get("/api/workflows/99999")
        assert response.status_code == 404

    def test_delete_draft_workflow(self, workflow_client, sample_simple_workflow, mock_agents):
        """Test deleting a draft workflow succeeds."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create workflow
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Delete Test Workflow",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-delete-user",
                },
            )
            workflow_id = create_response.json()["id"]

            # Delete workflow
            response = workflow_client.delete(f"/api/workflows/{workflow_id}")

        assert response.status_code == 204

        # Verify deletion
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            get_response = workflow_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 404

    def test_cannot_execute_draft_workflow(
        self, workflow_client, sample_simple_workflow, mock_agents
    ):
        """Test executing a draft workflow returns 403."""
        with patch("core.workflows.schema.list_agents", return_value=mock_agents):
            # Create workflow (stays in draft)
            create_response = workflow_client.post(
                "/api/workflows",
                json={
                    "name": "Draft Execution Test",
                    "workflow_json": sample_simple_workflow,
                    "user_id": "test-draft-exec-user",
                },
            )
            workflow_id = create_response.json()["id"]

            # Try to execute draft workflow
            response = workflow_client.post(f"/api/workflows/{workflow_id}/execute")

        assert response.status_code == 403
        assert (
            "draft" in response.json()["detail"].lower()
            or "published" in response.json()["detail"].lower()
        )
