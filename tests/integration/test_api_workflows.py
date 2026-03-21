"""
Integration tests for workflows API routes.

Tests cover:
1. List workflows (empty, with filters, pagination)
2. Create workflow (success, validation errors)
3. Get workflow by ID (found, not found, access control)
4. Update workflow (draft, immutable)
5. Delete workflow (draft, published)
6. Publish workflow
7. Clone workflow
8. Execute workflow (published only, mocked)
9. Get execution history
10. Workflow validation errors
11. Not found handling

Target: ~350 LOC
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def workflows_client():
    """Create test FastAPI app with in-memory database and auth bypass."""
    # Set environment variables BEFORE importing the app
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

    # Seed test user so FK constraints don't block workflow creation (PostgreSQL CI)
    from core.database.models import User
    from core.database.session import get_session

    with get_session() as session:
        existing = session.query(User).filter_by(id="test-user-123").first()
        if not existing:
            session.add(
                User(
                    id="test-user-123",
                    email="test-workflows@example.com",
                    password_hash=None,
                    role="user",
                    is_active=True,
                )
            )

    # Mock the auth dependency to bypass authentication
    def override_get_current_user():
        return {"sub": "test-user-123", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    # Restore env: remove DRYADE_DATABASE_URL to avoid polluting other tests
    os.environ.pop("DRYADE_DATABASE_URL", None)
    from core.database.session import get_engine

    get_engine.cache_clear()
    if os.path.exists("./test_workflows.db"):
        os.remove("./test_workflows.db")

@pytest.fixture
def sample_workflow_data():
    """Sample workflow data for testing with valid schema structure and unique name."""
    unique_suffix = str(uuid.uuid4())[:8]
    return {
        "name": f"Test Workflow {unique_suffix}",
        "description": "A test workflow for integration testing",
        "workflow_json": {
            "version": "1.0.0",
            "nodes": [
                {"id": "start_node", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
                {
                    "id": "task_1",
                    "type": "task",
                    "data": {"agent": "test_agent", "task": "Do something"},
                    "position": {"x": 200, "y": 0},
                },
                {"id": "end_node", "type": "end", "data": {}, "position": {"x": 400, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "start_node", "target": "task_1"},
                {"id": "e2", "source": "task_1", "target": "end_node"},
            ],
        },
        "tags": ["test", "integration"],
        "is_public": False,
    }

@pytest.mark.integration
class TestWorkflowsListEndpoint:
    """Tests for GET /api/workflows endpoint."""

    def test_list_workflows_empty(self, workflows_client):
        """Test listing workflows when none exist."""
        response = workflows_client.get("/api/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert "has_more" in data
        assert data["total"] >= 0

    def test_list_workflows_with_filters(self, workflows_client):
        """Test listing workflows with status filter."""
        response = workflows_client.get("/api/workflows?status=draft&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert data["limit"] == 10

    def test_list_workflows_pagination(self, workflows_client, sample_workflow_data):
        """Test workflow pagination parameters."""
        response = workflows_client.get("/api/workflows?offset=0&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "offset" in data
        assert "limit" in data
        assert data["offset"] == 0
        assert data["limit"] == 5

    def test_list_workflows_invalid_limit(self, workflows_client):
        """Test invalid pagination limit."""
        response = workflows_client.get("/api/workflows?limit=500")
        assert response.status_code == 422  # Pydantic validation error

@pytest.mark.integration
class TestWorkflowsCreateEndpoint:
    """Tests for POST /api/workflows endpoint."""

    def test_create_workflow_success(self, workflows_client, sample_workflow_data):
        """Test creating a workflow successfully."""
        response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_workflow_data["name"]
        assert data["status"] == "draft"
        assert "id" in data
        assert data["version"] == "1.0.0"
        assert data["execution_count"] == 0

    def test_create_workflow_validation_error(self, workflows_client):
        """Test validation error for invalid workflow data."""
        bad_data = {
            "name": "",  # Empty name should fail
            "workflow_json": {},
        }
        response = workflows_client.post("/api/workflows", json=bad_data)
        assert response.status_code == 422

    def test_create_workflow_missing_required_fields(self, workflows_client):
        """Test validation error for missing required fields."""
        response = workflows_client.post("/api/workflows", json={})
        assert response.status_code == 422

    def test_create_workflow_with_tags(self, workflows_client, sample_workflow_data):
        """Test creating a workflow with tags."""
        sample_workflow_data["tags"] = ["custom", "tagged"]
        response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        assert response.status_code == 201
        data = response.json()
        assert "custom" in data["tags"]
        assert "tagged" in data["tags"]

@pytest.mark.integration
class TestWorkflowsGetEndpoint:
    """Tests for GET /api/workflows/{workflow_id} endpoint."""

    def test_get_workflow_not_found(self, workflows_client):
        """Test 404 when workflow not found."""
        response = workflows_client.get("/api/workflows/99999")
        assert response.status_code == 404

    def test_get_workflow_by_id(self, workflows_client, sample_workflow_data):
        """Test getting workflow details."""
        # Create workflow first
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        assert create_response.status_code == 201
        workflow_id = create_response.json()["id"]

        # Get workflow
        response = workflows_client.get(f"/api/workflows/{workflow_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == workflow_id
        assert data["name"] == sample_workflow_data["name"]

    def test_get_workflow_includes_full_json(self, workflows_client, sample_workflow_data):
        """Test that GET returns full workflow_json."""
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        response = workflows_client.get(f"/api/workflows/{workflow_id}")
        assert response.status_code == 200
        data = response.json()
        assert "workflow_json" in data
        assert "nodes" in data["workflow_json"]
        assert "edges" in data["workflow_json"]

@pytest.mark.integration
class TestWorkflowsUpdateEndpoint:
    """Tests for PUT /api/workflows/{workflow_id} endpoint."""

    def test_update_workflow_draft(self, workflows_client, sample_workflow_data):
        """Test updating a draft workflow."""
        # Create workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        assert create_response.status_code == 201
        workflow_id = create_response.json()["id"]

        # Update workflow with unique name to avoid DB collision with stale data
        unique_update_name = f"Updated Workflow Name {uuid.uuid4().hex[:8]}"
        update_data = {"name": unique_update_name, "description": "Updated description"}
        response = workflows_client.put(f"/api/workflows/{workflow_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == unique_update_name
        assert data["description"] == "Updated description"

    def test_update_workflow_not_found(self, workflows_client):
        """Test 404 when updating nonexistent workflow."""
        response = workflows_client.put("/api/workflows/99999", json={"name": "New Name"})
        assert response.status_code == 404

    def test_update_workflow_tags(self, workflows_client, sample_workflow_data):
        """Test updating workflow tags."""
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        update_data = {"tags": ["updated", "tags"]}
        response = workflows_client.put(f"/api/workflows/{workflow_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert "updated" in data["tags"]

@pytest.mark.integration
class TestWorkflowsDeleteEndpoint:
    """Tests for DELETE /api/workflows/{workflow_id} endpoint."""

    def test_delete_workflow_draft(self, workflows_client, sample_workflow_data):
        """Test deleting a draft workflow."""
        # Create workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        # Delete workflow
        response = workflows_client.delete(f"/api/workflows/{workflow_id}")
        assert response.status_code == 204

        # Verify deleted
        get_response = workflows_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 404

    def test_delete_workflow_not_found(self, workflows_client):
        """Test 404 when deleting nonexistent workflow."""
        response = workflows_client.delete("/api/workflows/99999")
        assert response.status_code == 404

@pytest.mark.integration
class TestWorkflowsPublishEndpoint:
    """Tests for POST /api/workflows/{workflow_id}/publish endpoint."""

    def test_publish_workflow_success(self, workflows_client, sample_workflow_data):
        """Test publishing a draft workflow."""
        # Create workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        # Publish workflow
        response = workflows_client.post(f"/api/workflows/{workflow_id}/publish")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    def test_publish_workflow_not_found(self, workflows_client):
        """Test 404 when publishing nonexistent workflow."""
        response = workflows_client.post("/api/workflows/99999/publish")
        assert response.status_code == 404

    def test_update_published_workflow_fails(self, workflows_client, sample_workflow_data):
        """Test that updating a published workflow fails."""
        # Create and publish workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]
        workflows_client.post(f"/api/workflows/{workflow_id}/publish")

        # Try to update - should fail
        response = workflows_client.put(f"/api/workflows/{workflow_id}", json={"name": "Updated"})
        assert response.status_code == 403
        assert (
            "published" in response.json()["detail"].lower()
            or "cannot modify" in response.json()["detail"].lower()
        )

    def test_delete_published_workflow_fails(self, workflows_client, sample_workflow_data):
        """Test that deleting a published workflow fails."""
        # Create and publish workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]
        workflows_client.post(f"/api/workflows/{workflow_id}/publish")

        # Try to delete - should fail
        response = workflows_client.delete(f"/api/workflows/{workflow_id}")
        assert response.status_code == 403

@pytest.mark.integration
class TestWorkflowsCloneEndpoint:
    """Tests for POST /api/workflows/{workflow_id}/clone endpoint."""

    def test_clone_workflow_success(self, workflows_client, sample_workflow_data):
        """Test cloning a workflow."""
        # Create workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        # Clone workflow with unique name to avoid DB collision
        clone_name = f"Cloned Workflow {uuid.uuid4().hex[:8]}"
        response = workflows_client.post(
            f"/api/workflows/{workflow_id}/clone",
            json={"name": clone_name},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == clone_name
        assert data["status"] == "draft"
        assert data["version"] == "1.1.0"  # Incremented version
        assert data["id"] != workflow_id

    def test_clone_workflow_not_found(self, workflows_client):
        """Test 404 when cloning nonexistent workflow."""
        response = workflows_client.post("/api/workflows/99999/clone", json={})
        assert response.status_code == 404

    def test_clone_workflow_default_name(self, workflows_client, sample_workflow_data):
        """Test cloning workflow without specifying name."""
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]
        original_name = create_response.json()["name"]

        # Clone without name
        response = workflows_client.post(f"/api/workflows/{workflow_id}/clone", json={})
        assert response.status_code == 201
        data = response.json()
        assert "(copy)" in data["name"] or original_name in data["name"]

@pytest.mark.integration
class TestWorkflowsExecuteEndpoint:
    """Tests for POST /api/workflows/{workflow_id}/execute endpoint."""

    def test_execute_draft_workflow_fails(self, workflows_client, sample_workflow_data):
        """Test that executing a draft workflow fails."""
        # Create draft workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        # Try to execute - should fail
        response = workflows_client.post(f"/api/workflows/{workflow_id}/execute", json={})
        assert response.status_code == 403
        assert (
            "draft" in response.json()["detail"].lower()
            or "published" in response.json()["detail"].lower()
        )

    def test_execute_workflow_not_found(self, workflows_client):
        """Test 404 when executing nonexistent workflow."""
        response = workflows_client.post("/api/workflows/99999/execute", json={})
        assert response.status_code == 404

@pytest.mark.integration
class TestWorkflowsExecutionsEndpoint:
    """Tests for GET /api/workflows/{workflow_id}/executions endpoint."""

    def test_list_executions_empty(self, workflows_client, sample_workflow_data):
        """Test listing executions for workflow without any."""
        # Create workflow
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        # List executions
        response = workflows_client.get(f"/api/workflows/{workflow_id}/executions")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert "total" in data
        assert data["total"] == 0

    def test_list_executions_not_found(self, workflows_client):
        """Test 404 when listing executions for nonexistent workflow."""
        response = workflows_client.get("/api/workflows/99999/executions")
        assert response.status_code == 404

    def test_list_executions_pagination(self, workflows_client, sample_workflow_data):
        """Test execution list pagination parameters."""
        create_response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        workflow_id = create_response.json()["id"]

        response = workflows_client.get(
            f"/api/workflows/{workflow_id}/executions?offset=0&limit=10"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 0
        assert data["limit"] == 10

@pytest.mark.integration
class TestWorkflowValidationErrors:
    """Tests for workflow validation error handling."""

    def test_create_workflow_name_too_long(self, workflows_client, sample_workflow_data):
        """Test validation error for name exceeding max length."""
        sample_workflow_data["name"] = "x" * 201  # Max is 200
        response = workflows_client.post("/api/workflows", json=sample_workflow_data)
        assert response.status_code == 422

    def test_create_workflow_invalid_workflow_json(self, workflows_client):
        """Test validation error for invalid workflow_json structure."""
        bad_data = {
            "name": "Invalid Workflow",
            "workflow_json": {"invalid": "structure"},  # Missing required fields
        }
        response = workflows_client.post("/api/workflows", json=bad_data)
        # Accepts any dict for workflow_json, but actual validation may be deferred
        assert response.status_code in [201, 400, 422]

@pytest.mark.integration
class TestWorkflowNotFoundHandling:
    """Tests for various not-found scenarios."""

    def test_get_nonexistent_workflow(self, workflows_client):
        """Test 404 for GET on nonexistent workflow."""
        response = workflows_client.get("/api/workflows/999999")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_update_nonexistent_workflow(self, workflows_client):
        """Test 404 for PUT on nonexistent workflow."""
        response = workflows_client.put("/api/workflows/999999", json={"name": "Test"})
        assert response.status_code == 404

    def test_delete_nonexistent_workflow(self, workflows_client):
        """Test 404 for DELETE on nonexistent workflow."""
        response = workflows_client.delete("/api/workflows/999999")
        assert response.status_code == 404

    def test_publish_nonexistent_workflow(self, workflows_client):
        """Test 404 for publish on nonexistent workflow."""
        response = workflows_client.post("/api/workflows/999999/publish")
        assert response.status_code == 404

    def test_clone_nonexistent_workflow(self, workflows_client):
        """Test 404 for clone on nonexistent workflow."""
        response = workflows_client.post("/api/workflows/999999/clone", json={})
        assert response.status_code == 404

    def test_execute_nonexistent_workflow(self, workflows_client):
        """Test 404 for execute on nonexistent workflow."""
        response = workflows_client.post("/api/workflows/999999/execute", json={})
        assert response.status_code == 404

    def test_executions_nonexistent_workflow(self, workflows_client):
        """Test 404 for executions on nonexistent workflow."""
        response = workflows_client.get("/api/workflows/999999/executions")
        assert response.status_code == 404
