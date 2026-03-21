"""End-to-end tests for Workflow CRUD operations.

Tests the complete workflow lifecycle: create, list, get, update, publish,
clone, delete, and execution history retrieval.
"""

import uuid

import pytest

WORKFLOW_BASE = "/api/workflows"

MINIMAL_WORKFLOW_JSON = {
    "version": "1.0.0",
    "nodes": [
        {"id": "start_1", "type": "start", "data": {"label": "Start"}},
        {"id": "task_1", "type": "task", "data": {"label": "Step 1"}},
        {"id": "end_1", "type": "end", "data": {"label": "End"}},
    ],
    "edges": [
        {"id": "e1", "source": "start_1", "target": "task_1"},
        {"id": "e2", "source": "task_1", "target": "end_1"},
    ],
}

def _create_payload(
    name: str = "Test Workflow", description: str = "desc", tags: list | None = None
):
    """Build a workflow creation payload."""
    return {
        "name": name,
        "description": description,
        "workflow_json": MINIMAL_WORKFLOW_JSON,
        "tags": tags or ["test"],
    }

def _create_workflow(client, name: str | None = None, **overrides):
    """Helper: POST a new workflow and return the JSON response.

    Uses a unique name per invocation to avoid (name, version, user_id)
    uniqueness conflicts across tests in the session-scoped DB.
    """
    if name is None:
        name = f"Test Workflow {uuid.uuid4().hex[:8]}"
    payload = _create_payload(name=name)
    payload.update(overrides)
    resp = client.post(WORKFLOW_BASE, json=payload)
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.text}"
    return resp.json()

@pytest.mark.e2e
class TestWorkflowCRUD:
    """E2E tests for the workflow management API."""

    # ------------------------------------------------------------------
    # 1. Create
    # ------------------------------------------------------------------

    def test_create_workflow(self, e2e_client):
        """POST /api/workflows returns 201 with id, name, and status=draft."""
        data = _create_workflow(e2e_client)

        assert "id" in data
        assert data["name"].startswith("Test Workflow")
        assert data["status"] == "draft"

    # ------------------------------------------------------------------
    # 2. List
    # ------------------------------------------------------------------

    def test_list_workflows(self, e2e_client):
        """Creating 2 workflows then listing returns both."""
        suffix = uuid.uuid4().hex[:6]
        w1 = _create_workflow(e2e_client, name=f"List WF 1 {suffix}")
        w2 = _create_workflow(e2e_client, name=f"List WF 2 {suffix}")

        resp = e2e_client.get(WORKFLOW_BASE)
        assert resp.status_code == 200

        body = resp.json()
        returned_ids = {w["id"] for w in body["workflows"]}

        assert w1["id"] in returned_ids
        assert w2["id"] in returned_ids

    # ------------------------------------------------------------------
    # 3. Get detail
    # ------------------------------------------------------------------

    def test_get_workflow_detail(self, e2e_client):
        """GET /api/workflows/{id} returns all expected fields."""
        wf_name = f"Detail WF {uuid.uuid4().hex[:6]}"
        created = _create_workflow(e2e_client, name=wf_name)

        resp = e2e_client.get(f"{WORKFLOW_BASE}/{created['id']}")
        assert resp.status_code == 200

        data = resp.json()
        for field in (
            "id",
            "name",
            "description",
            "version",
            "workflow_json",
            "status",
            "is_public",
            "user_id",
            "tags",
            "execution_count",
            "created_at",
            "updated_at",
        ):
            assert field in data, f"Missing field: {field}"

        assert data["id"] == created["id"]
        assert data["name"] == wf_name
        assert data["status"] == "draft"

    # ------------------------------------------------------------------
    # 4. Update draft
    # ------------------------------------------------------------------

    def test_update_draft_workflow(self, e2e_client):
        """PUT update on a draft workflow changes name and description."""
        suffix = uuid.uuid4().hex[:6]
        created = _create_workflow(e2e_client, name=f"Before Update {suffix}")

        new_name = f"After Update {suffix}"
        resp = e2e_client.put(
            f"{WORKFLOW_BASE}/{created['id']}",
            json={"name": new_name, "description": "new desc"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["name"] == new_name
        assert data["description"] == "new desc"

    # ------------------------------------------------------------------
    # 5. Publish
    # ------------------------------------------------------------------

    def test_publish_workflow(self, e2e_client):
        """POST publish transitions a draft to published status."""
        created = _create_workflow(e2e_client, name=f"Publish WF {uuid.uuid4().hex[:6]}")

        resp = e2e_client.post(f"{WORKFLOW_BASE}/{created['id']}/publish")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "published"
        assert data["published_at"] is not None

    # ------------------------------------------------------------------
    # 6. Clone published workflow
    # ------------------------------------------------------------------

    def test_clone_published_workflow(self, e2e_client):
        """Clone a published workflow: new id and incremented version."""
        created = _create_workflow(e2e_client, name=f"Clone Source {uuid.uuid4().hex[:6]}")

        # Publish first
        pub_resp = e2e_client.post(f"{WORKFLOW_BASE}/{created['id']}/publish")
        assert pub_resp.status_code == 200

        # Clone
        clone_resp = e2e_client.post(
            f"{WORKFLOW_BASE}/{created['id']}/clone",
            json={},
        )
        assert clone_resp.status_code == 201

        cloned = clone_resp.json()
        assert cloned["id"] != created["id"]
        assert cloned["status"] == "draft"
        # Version should be incremented from 1.0.0 -> 1.1.0
        assert cloned["version"] == "1.1.0"

    # ------------------------------------------------------------------
    # 7. Delete draft
    # ------------------------------------------------------------------

    def test_delete_draft_workflow(self, e2e_client):
        """DELETE a draft workflow returns 204 and it disappears from listings."""
        created = _create_workflow(e2e_client, name=f"Delete Me {uuid.uuid4().hex[:6]}")
        wf_id = created["id"]

        resp = e2e_client.delete(f"{WORKFLOW_BASE}/{wf_id}")
        assert resp.status_code == 204

        # Confirm it is gone
        get_resp = e2e_client.get(f"{WORKFLOW_BASE}/{wf_id}")
        assert get_resp.status_code in (403, 404)

    # ------------------------------------------------------------------
    # 8. List executions (empty)
    # ------------------------------------------------------------------

    def test_list_executions_empty(self, e2e_client):
        """GET executions for a new workflow returns an empty list."""
        created = _create_workflow(e2e_client, name=f"Exec History WF {uuid.uuid4().hex[:6]}")

        resp = e2e_client.get(f"{WORKFLOW_BASE}/{created['id']}/executions")
        assert resp.status_code == 200

        body = resp.json()
        assert body["executions"] == []
        assert body["total"] == 0
