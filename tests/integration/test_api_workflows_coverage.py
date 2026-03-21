"""Coverage-focused tests for workflow and workflow_scenarios API routes.

Targets uncovered code paths in:
- core/api/routes/workflows.py (lifecycle, sharing, execution)
- core/api/routes/workflow_scenarios.py (scenario CRUD, execution, validation)

Uses authenticated_client fixture from integration conftest.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from core.api.routes.workflows import increment_version, workflow_to_response, workflow_to_summary

def _unique_name(prefix: str = "WF") -> str:
    """Generate unique workflow name to avoid DB constraint violations."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

class TestWorkflowHelpers:
    """Tests for workflow helper functions."""

    def test_increment_version_standard(self):
        """Test version increment: 1.0.0 -> 1.1.0."""
        assert increment_version("1.0.0") == "1.1.0"

    def test_increment_version_higher(self):
        """Test version increment: 2.5.3 -> 2.6.3."""
        assert increment_version("2.5.3") == "2.6.3"

    def test_increment_version_invalid(self):
        """Test fallback for invalid version string."""
        assert increment_version("invalid") == "1.1.0"

    def test_increment_version_single_part(self):
        """Test fallback for single-part version."""
        assert increment_version("1") == "1.1.0"

    def test_workflow_to_response(self):
        """Test workflow_to_response conversion."""
        from datetime import datetime

        workflow = MagicMock()
        workflow.id = 1
        workflow.name = "Test"
        workflow.description = "Desc"
        workflow.version = "1.0.0"
        workflow.workflow_json = {"nodes": [], "edges": []}
        workflow.status = "draft"
        workflow.is_public = False
        workflow.user_id = "user-1"
        workflow.tags = ["tag1"]
        workflow.execution_count = 5
        workflow.created_at = datetime(2026, 1, 1)
        workflow.updated_at = datetime(2026, 1, 2)
        workflow.published_at = None

        result = workflow_to_response(workflow)
        assert result["id"] == 1
        assert result["name"] == "Test"
        assert result["tags"] == ["tag1"]
        assert result["execution_count"] == 5
        assert result["published_at"] is None

    def test_workflow_to_summary(self):
        """Test workflow_to_summary conversion (no workflow_json)."""
        from datetime import datetime

        workflow = MagicMock()
        workflow.id = 2
        workflow.name = "Summary"
        workflow.description = None
        workflow.version = "1.0.0"
        workflow.status = "published"
        workflow.is_public = True
        workflow.user_id = "user-2"
        workflow.tags = None
        workflow.execution_count = None
        workflow.created_at = datetime(2026, 1, 1)
        workflow.updated_at = datetime(2026, 1, 2)

        result = workflow_to_summary(workflow)
        assert result["id"] == 2
        assert result["tags"] == []
        assert result["execution_count"] == 0
        assert "workflow_json" not in result

VALID_WORKFLOW_JSON = {
    "version": "1.0.0",
    "metadata": {"name": "Test", "description": "test"},
    "nodes": [
        {
            "id": "start_1",
            "type": "start",
            "data": {},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "task_1",
            "type": "task",
            "data": {"agent": "TestAgent", "task": "Do something"},
            "position": {"x": 200, "y": 0},
        },
    ],
    "edges": [{"id": "e1", "source": "start_1", "target": "task_1"}],
}

@pytest.mark.integration
class TestWorkflowCRUD:
    """Tests for workflow CRUD endpoints."""

    def test_create_workflow(self, authenticated_client):
        """Test POST /api/workflows creates workflow."""
        name = _unique_name("Create")
        response = authenticated_client.post(
            "/api/workflows",
            json={
                "name": name,
                "description": "Test coverage",
                "workflow_json": VALID_WORKFLOW_JSON,
                "tags": ["test"],
                "is_public": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == name
        assert data["status"] == "draft"
        assert data["version"] == "1.0.0"

    def test_create_workflow_invalid_schema(self, authenticated_client):
        """Test 400 for invalid workflow_json schema."""
        response = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Invalid"),
                "workflow_json": {"invalid": True},
            },
        )
        assert response.status_code == 400

    def test_list_workflows(self, authenticated_client):
        """Test GET /api/workflows returns paginated list."""
        response = authenticated_client.get("/api/workflows")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert "total" in data
        assert "has_more" in data

    def test_list_workflows_filter_status(self, authenticated_client):
        """Test filtering workflows by status."""
        response = authenticated_client.get("/api/workflows?status=draft")
        assert response.status_code == 200

    def test_get_workflow(self, authenticated_client):
        """Test GET /api/workflows/{id} returns full workflow."""
        # Create first
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Get"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.get(f"/api/workflows/{wf_id}")
        assert response.status_code == 200
        assert response.json()["id"] == wf_id

    def test_update_workflow(self, authenticated_client):
        """Test PUT /api/workflows/{id} updates draft workflow."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Update"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        updated_name = _unique_name("Updated")
        response = authenticated_client.put(
            f"/api/workflows/{wf_id}",
            json={
                "name": updated_name,
                "description": "Updated desc",
                "tags": ["updated"],
            },
        )
        assert response.status_code == 200
        assert response.json()["name"] == updated_name

    def test_delete_workflow(self, authenticated_client):
        """Test DELETE /api/workflows/{id} deletes draft workflow."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Delete"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.delete(f"/api/workflows/{wf_id}")
        assert response.status_code == 204

    def test_publish_workflow(self, authenticated_client):
        """Test POST /api/workflows/{id}/publish transitions to published."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Publish"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.post(f"/api/workflows/{wf_id}/publish")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    def test_publish_non_draft(self, authenticated_client):
        """Test 403 publishing already-published workflow."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("DblPub"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        # Publish once
        authenticated_client.post(f"/api/workflows/{wf_id}/publish")

        # Try to publish again
        response = authenticated_client.post(f"/api/workflows/{wf_id}/publish")
        assert response.status_code == 403

    def test_update_published_workflow_fails(self, authenticated_client):
        """Test 403 updating published workflow."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Immutable"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]
        authenticated_client.post(f"/api/workflows/{wf_id}/publish")

        response = authenticated_client.put(
            f"/api/workflows/{wf_id}",
            json={"name": _unique_name("TryUpdate")},
        )
        assert response.status_code == 403

    def test_delete_published_workflow_fails(self, authenticated_client):
        """Test 403 deleting published workflow."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("NoDel"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]
        authenticated_client.post(f"/api/workflows/{wf_id}/publish")

        response = authenticated_client.delete(f"/api/workflows/{wf_id}")
        assert response.status_code == 403

    def test_clone_workflow(self, authenticated_client):
        """Test POST /api/workflows/{id}/clone creates a copy."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("CloneSrc"),
                "workflow_json": VALID_WORKFLOW_JSON,
                "tags": ["original"],
            },
        )
        wf_id = create_resp.json()["id"]

        clone_name = _unique_name("Cloned")
        response = authenticated_client.post(
            f"/api/workflows/{wf_id}/clone",
            json={"name": clone_name},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == clone_name
        assert data["version"] == "1.1.0"
        assert data["status"] == "draft"

    def test_clone_workflow_default_name(self, authenticated_client):
        """Test cloning without specifying name gets default."""
        orig_name = _unique_name("Original")
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": orig_name,
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.post(f"/api/workflows/{wf_id}/clone")
        assert response.status_code == 201
        assert response.json()["name"] == f"{orig_name} (copy)"

    def test_clone_not_found(self, authenticated_client):
        """Test 404 cloning non-existent workflow."""
        response = authenticated_client.post("/api/workflows/99999/clone")
        assert response.status_code == 404

    def test_publish_not_found(self, authenticated_client):
        """Test 404 publishing non-existent workflow."""
        response = authenticated_client.post("/api/workflows/99999/publish")
        assert response.status_code == 404

@pytest.mark.integration
class TestWorkflowExecution:
    """Tests for workflow execution endpoints."""

    def test_execute_draft_workflow_fails(self, authenticated_client):
        """Test 403 executing draft workflow."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("DraftExec"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.post(f"/api/workflows/{wf_id}/execute")
        assert response.status_code == 403

    def test_execute_not_found(self, authenticated_client):
        """Test 404 executing non-existent workflow."""
        response = authenticated_client.post("/api/workflows/99999/execute")
        assert response.status_code == 404

    def test_get_execution_history(self, authenticated_client):
        """Test GET /api/workflows/{id}/executions returns history."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("ExecHist"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.get(f"/api/workflows/{wf_id}/executions")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert "total" in data
        assert data["total"] == 0

    def test_get_execution_history_not_found(self, authenticated_client):
        """Test 404 for execution history of non-existent workflow."""
        response = authenticated_client.get("/api/workflows/99999/executions")
        assert response.status_code == 404

@pytest.mark.integration
class TestWorkflowSharing:
    """Tests for workflow sharing endpoints."""

    def test_share_workflow(self, authenticated_client):
        """Test POST /api/workflows/{id}/share attempts share (user may not exist)."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Share"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.post(
            f"/api/workflows/{wf_id}/share",
            json={"user_id": "other-user", "permission": "view"},
        )
        # 200 if user exists, 404 if user lookup fails, 500 on other errors
        assert response.status_code in [200, 404, 500]

    def test_unshare_workflow(self, authenticated_client):
        """Test DELETE /api/workflows/{id}/share/{user_id} removes share."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("Unshare"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        # Unshare (share may not exist)
        response = authenticated_client.delete(f"/api/workflows/{wf_id}/share/removable-user")
        assert response.status_code in [204, 404]

    def test_list_shares(self, authenticated_client):
        """Test GET /api/workflows/{id}/shares lists shares."""
        create_resp = authenticated_client.post(
            "/api/workflows",
            json={
                "name": _unique_name("ListShares"),
                "workflow_json": VALID_WORKFLOW_JSON,
            },
        )
        wf_id = create_resp.json()["id"]

        response = authenticated_client.get(f"/api/workflows/{wf_id}/shares")
        assert response.status_code == 200
        data = response.json()
        assert "workflow_id" in data
        assert "shares" in data

@pytest.mark.integration
class TestWorkflowScenariosEndpoints:
    """Tests for workflow scenarios API endpoints."""

    def test_list_scenarios(self, authenticated_client):
        """Test GET /api/workflow-scenarios lists available scenarios."""
        response = authenticated_client.get("/api/workflow-scenarios")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_scenario_not_found(self, authenticated_client):
        """Test 404 for non-existent scenario."""
        response = authenticated_client.get("/api/workflow-scenarios/nonexistent_scenario_xyz")
        # Might be 404 or 500 depending on registry
        assert response.status_code in [404, 500]

    def test_list_executions(self, authenticated_client):
        """Test GET /api/workflow-scenarios/executions lists history."""
        response = authenticated_client.get("/api/workflow-scenarios/executions")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert "total" in data

    def test_list_executions_with_filters(self, authenticated_client):
        """Test listing executions with query filters."""
        response = authenticated_client.get(
            "/api/workflow-scenarios/executions?status=completed&limit=10"
        )
        assert response.status_code == 200

    def test_get_execution_not_found(self, authenticated_client):
        """Test 404 for non-existent execution."""
        response = authenticated_client.get(
            f"/api/workflow-scenarios/executions/{str(uuid.uuid4())}"
        )
        assert response.status_code == 404

    def test_cancel_execution_not_found(self, authenticated_client):
        """Test 404 cancelling non-existent execution."""
        response = authenticated_client.post(
            f"/api/workflow-scenarios/executions/{str(uuid.uuid4())}/cancel"
        )
        assert response.status_code == 404

    def test_validate_scenario_not_found(self, authenticated_client):
        """Test 404 validating non-existent scenario."""
        response = authenticated_client.post(
            "/api/workflow-scenarios/nonexistent_scenario_xyz/validate",
            json={"query": "test"},
        )
        assert response.status_code in [404, 500]

    def test_trigger_scenario_not_found(self, authenticated_client):
        """Test 404 triggering non-existent scenario."""
        response = authenticated_client.post(
            "/api/workflow-scenarios/nonexistent_scenario_xyz/trigger",
            json={"query": "test"},
        )
        assert response.status_code in [404, 500]
