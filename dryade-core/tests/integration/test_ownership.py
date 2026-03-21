"""
Integration tests for resource ownership enforcement.

Tests ownership checks, admin bypass, and public access on workflows.
Uses its own module-scoped app to avoid DB conflicts with other test files.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def ownership_app():
    """Create a dedicated app instance for ownership tests with its own DB."""
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

    yield app

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_ownership.db"):
        os.remove("./test_ownership.db")

def _make_client(app, user_id: str, role: str = "member"):
    """Create a test client with a specific user identity."""
    from core.auth.dependencies import get_current_user

    def override():
        return {"sub": user_id, "role": role, "email": f"{user_id}@test.com"}

    app.dependency_overrides[get_current_user] = override
    return TestClient(app, raise_server_exceptions=False)

def _create_workflow(client, name: str, is_public: bool = False):
    """Helper to create a workflow with a unique suffix to avoid DB collisions.

    Returns (response, actual_name) tuple so tests can assert on the real name.
    """
    unique_name = f"{name}-{uuid.uuid4().hex[:8]}"
    with patch("core.workflows.schema.list_agents", return_value=[]):
        response = client.post(
            "/api/workflows",
            json={
                "name": unique_name,
                "workflow_json": {
                    "version": "1.0.0",
                    "nodes": [
                        {
                            "id": "start_1",
                            "type": "start",
                            "data": {},
                            "position": {"x": 0, "y": 0},
                        },
                        {
                            "id": "end_1",
                            "type": "end",
                            "data": {},
                            "position": {"x": 0, "y": 100},
                        },
                    ],
                    "edges": [
                        {"id": "e1", "source": "start_1", "target": "end_1", "type": "default"},
                    ],
                },
                "is_public": is_public,
            },
        )
    return response, unique_name

@pytest.mark.integration
class TestOwnershipAccess:
    """Tests for owner access to resources."""

    def test_owner_can_access_own_workflow(self, ownership_app):
        """Owner can GET their own workflow."""
        client = _make_client(ownership_app, "owner-access-1")

        response, wf_name = _create_workflow(client, "My Workflow")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Access as same user
        get_response = client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == wf_name

        ownership_app.dependency_overrides.clear()

    def test_owner_can_update_own_workflow(self, ownership_app):
        """Owner can PUT to update their own workflow."""
        client = _make_client(ownership_app, "owner-update-1")

        response, _ = _create_workflow(client, "Original Name")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Update as owner
        update_response = client.put(f"/api/workflows/{workflow_id}", json={"name": "Updated Name"})
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Name"

        ownership_app.dependency_overrides.clear()

    def test_owner_can_delete_own_draft_workflow(self, ownership_app):
        """Owner can DELETE their own draft workflow."""
        client = _make_client(ownership_app, "owner-delete-1")

        response, _ = _create_workflow(client, "To Delete")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Delete as owner
        delete_response = client.delete(f"/api/workflows/{workflow_id}")
        assert delete_response.status_code == 204

        # Verify deleted
        get_response = client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 404

        ownership_app.dependency_overrides.clear()

@pytest.mark.integration
class TestOwnershipDenied:
    """Tests for access denied to non-owners."""

    def test_non_owner_cannot_access_private_workflow(self, ownership_app):
        """Non-owner cannot GET a private workflow."""
        client1 = _make_client(ownership_app, "deny-access-1")
        response, _ = _create_workflow(client1, "Private Workflow", is_public=False)
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Try to access as user2
        client2 = _make_client(ownership_app, "deny-access-2")
        get_response = client2.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 403

        ownership_app.dependency_overrides.clear()

    def test_non_owner_cannot_update_workflow(self, ownership_app):
        """Non-owner cannot PUT to update a workflow."""
        client1 = _make_client(ownership_app, "deny-update-1")
        response, _ = _create_workflow(client1, "User1 Workflow")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Try to update as user2
        client2 = _make_client(ownership_app, "deny-update-2")
        update_response = client2.put(f"/api/workflows/{workflow_id}", json={"name": "Hacked Name"})
        assert update_response.status_code == 403

        ownership_app.dependency_overrides.clear()

    def test_non_owner_cannot_delete_workflow(self, ownership_app):
        """Non-owner cannot DELETE a workflow."""
        client1 = _make_client(ownership_app, "deny-del-1")
        response, _ = _create_workflow(client1, "User1 Workflow Del")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Try to delete as user2
        client2 = _make_client(ownership_app, "deny-del-2")
        delete_response = client2.delete(f"/api/workflows/{workflow_id}")
        assert delete_response.status_code == 403

        ownership_app.dependency_overrides.clear()

@pytest.mark.integration
class TestAdminBypass:
    """Tests for admin access bypass."""

    def test_admin_can_access_any_workflow(self, ownership_app):
        """Admin can GET any user's private workflow."""
        client1 = _make_client(ownership_app, "admin-bypass-1")
        response, wf_name = _create_workflow(client1, "User1 Private", is_public=False)
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Access as admin
        admin_client = _make_client(ownership_app, "admin1", "admin")
        get_response = admin_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == wf_name

        ownership_app.dependency_overrides.clear()

    def test_admin_sees_all_workflows_in_list(self, ownership_app):
        """Admin sees all workflows in list endpoint."""
        client1 = _make_client(ownership_app, "admin-list-1")
        _, name1 = _create_workflow(client1, "User1 Workflow Admin Test")

        client2 = _make_client(ownership_app, "admin-list-2")
        _, name2 = _create_workflow(client2, "User2 Workflow Admin Test")

        # List as admin
        admin_client = _make_client(ownership_app, "admin-list", "admin")
        list_response = admin_client.get("/api/workflows")
        assert list_response.status_code == 200
        workflows = list_response.json()["workflows"]
        names = [w["name"] for w in workflows]
        assert name1 in names
        assert name2 in names

        ownership_app.dependency_overrides.clear()

@pytest.mark.integration
class TestPublicAccess:
    """Tests for public resource access."""

    def test_non_owner_can_view_public_workflow(self, ownership_app):
        """Non-owner can GET a public workflow."""
        client1 = _make_client(ownership_app, "public-view-1")
        response, wf_name = _create_workflow(client1, "Public Workflow", is_public=True)
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Access as user2
        client2 = _make_client(ownership_app, "public-view-2")
        get_response = client2.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == wf_name

        ownership_app.dependency_overrides.clear()

    def test_public_workflows_appear_in_list(self, ownership_app):
        """Public workflows from other users appear in list."""
        client1 = _make_client(ownership_app, "public-list-1")
        _, name1 = _create_workflow(client1, "Public From User1 List", is_public=True)

        client2 = _make_client(ownership_app, "public-list-2")
        _, name2 = _create_workflow(client2, "User2 Own List")

        # List as user2 - should see both
        list_response = client2.get("/api/workflows")
        assert list_response.status_code == 200
        workflows = list_response.json()["workflows"]
        names = [w["name"] for w in workflows]
        assert name1 in names
        assert name2 in names

        ownership_app.dependency_overrides.clear()
