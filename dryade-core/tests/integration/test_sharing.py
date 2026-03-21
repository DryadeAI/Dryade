"""
Integration tests for resource sharing.

Tests sharing workflows between users with view/edit permissions.
Uses its own module-scoped app to avoid DB/auth conflicts with other tests.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def sharing_app():
    """Create a dedicated app instance for sharing tests with its own DB."""
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

    from core.database.session import get_engine, get_session, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app

    # Seed test users into DB for sharing operations
    from core.database.models import User

    with get_session() as session:
        for uid, email in [
            ("owner1", "owner1@test.com"),
            ("target_user", "target@test.com"),
            ("shared_user", "shared@test.com"),
            ("viewer_user", "viewer@test.com"),
            ("editor_user", "editor@test.com"),
            ("to_unshare", "unshare@test.com"),
            ("share1", "share1@test.com"),
            ("share2", "share2@test.com"),
            ("hacker", "hacker@test.com"),
            ("recipient", "recipient@test.com"),
        ]:
            existing = session.query(User).filter_by(id=uid).first()
            if not existing:
                session.add(User(id=uid, email=email, password_hash="x", role="member"))

    yield app

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_sharing.db"):
        os.remove("./test_sharing.db")

def _make_client(app, user_id: str, role: str = "member"):
    """Create a test client with a specific user identity."""
    from core.auth.dependencies import get_current_user

    def override():
        return {"sub": user_id, "role": role, "email": f"{user_id}@test.com"}

    app.dependency_overrides[get_current_user] = override
    return TestClient(app, raise_server_exceptions=False)

def _create_workflow(client, name: str, is_public: bool = False):
    """Create a workflow with unique name."""
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
                        {"id": "end_1", "type": "end", "data": {}, "position": {"x": 0, "y": 100}},
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
class TestShareWorkflow:
    """Tests for POST /workflows/{id}/share."""

    def test_owner_can_share_workflow(self, sharing_app):
        """Owner can share workflow with another user."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "Workflow to Share")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share with target user
        share_response = client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "target_user", "permission": "view"},
        )
        assert share_response.status_code == 200
        assert share_response.json()["shared_with"] == "target_user"
        assert share_response.json()["permission"] == "view"

        sharing_app.dependency_overrides.clear()

    def test_non_owner_cannot_share_workflow(self, sharing_app):
        """Non-owner cannot share a workflow."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "Owner Workflow")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Try to share as non-owner
        hacker_client = _make_client(sharing_app, "hacker")
        share_response = hacker_client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "target_user", "permission": "edit"},
        )
        assert share_response.status_code == 403

        sharing_app.dependency_overrides.clear()

@pytest.mark.integration
class TestSharedAccess:
    """Tests for accessing shared resources."""

    def test_shared_user_can_view_workflow(self, sharing_app):
        """User with share can view the workflow."""
        client = _make_client(sharing_app, "owner1")

        response, wf_name = _create_workflow(client, "Shared Workflow", is_public=False)
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share with user
        share_response = client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "shared_user", "permission": "view"},
        )
        assert share_response.status_code == 200

        # Access as shared user
        shared_client = _make_client(sharing_app, "shared_user")
        get_response = shared_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == wf_name

        sharing_app.dependency_overrides.clear()

    def test_view_permission_cannot_edit(self, sharing_app):
        """User with view permission cannot edit the workflow."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "View Only Workflow")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share with view permission
        client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "viewer_user", "permission": "view"},
        )

        # Try to edit as viewer
        viewer_client = _make_client(sharing_app, "viewer_user")
        update_response = viewer_client.put(
            f"/api/workflows/{workflow_id}", json={"name": "Hacked Name"}
        )
        assert update_response.status_code == 403

        sharing_app.dependency_overrides.clear()

    def test_edit_permission_can_update(self, sharing_app):
        """User with edit permission can update the workflow."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "Editable Workflow")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share with edit permission
        client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "editor_user", "permission": "edit"},
        )

        # Edit as editor
        editor_client = _make_client(sharing_app, "editor_user")
        update_response = editor_client.put(
            f"/api/workflows/{workflow_id}", json={"name": "Editor Updated Name"}
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Editor Updated Name"

        sharing_app.dependency_overrides.clear()

@pytest.mark.integration
class TestUnshare:
    """Tests for DELETE /workflows/{id}/share/{user_id}."""

    def test_owner_can_unshare(self, sharing_app):
        """Owner can remove sharing from a workflow."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "Workflow to Unshare")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share
        client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "to_unshare", "permission": "view"},
        )

        # Unshare
        unshare_response = client.delete(f"/api/workflows/{workflow_id}/share/to_unshare")
        assert unshare_response.status_code == 204

        # Verify user can no longer access
        unshared_client = _make_client(sharing_app, "to_unshare")
        get_response = unshared_client.get(f"/api/workflows/{workflow_id}")
        assert get_response.status_code == 403

        sharing_app.dependency_overrides.clear()

@pytest.mark.integration
class TestListShares:
    """Tests for GET /workflows/{id}/shares."""

    def test_owner_can_list_shares(self, sharing_app):
        """Owner can list all shares for a workflow."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "Multi-shared Workflow")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share with two users
        client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "share1", "permission": "view"},
        )
        client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "share2", "permission": "edit"},
        )

        # List shares
        list_response = client.get(f"/api/workflows/{workflow_id}/shares")
        assert list_response.status_code == 200
        shares = list_response.json()["shares"]
        assert len(shares) == 2

        user_ids = [s["user_id"] for s in shares]
        assert "share1" in user_ids
        assert "share2" in user_ids

        sharing_app.dependency_overrides.clear()

    def test_non_owner_cannot_list_shares(self, sharing_app):
        """Non-owner cannot list shares for a workflow."""
        client = _make_client(sharing_app, "owner1")

        response, _ = _create_workflow(client, "Private Shares")
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Try to list shares as non-owner
        hacker_client = _make_client(sharing_app, "hacker")
        list_response = hacker_client.get(f"/api/workflows/{workflow_id}/shares")
        assert list_response.status_code == 403

        sharing_app.dependency_overrides.clear()

@pytest.mark.integration
class TestSharedWorkflowsInList:
    """Tests for shared workflows appearing in list endpoint."""

    def test_shared_workflows_appear_in_list(self, sharing_app):
        """Shared workflows appear in user's workflow list."""
        client = _make_client(sharing_app, "owner1")

        response, wf_name = _create_workflow(client, "Shared to Recipient", is_public=False)
        assert response.status_code == 201
        workflow_id = response.json()["id"]

        # Share
        client.post(
            f"/api/workflows/{workflow_id}/share",
            json={"user_id": "recipient", "permission": "view"},
        )

        # List as recipient
        recipient_client = _make_client(sharing_app, "recipient")
        list_response = recipient_client.get("/api/workflows")
        assert list_response.status_code == 200
        workflows = list_response.json()["workflows"]
        names = [w["name"] for w in workflows]
        assert wf_name in names

        sharing_app.dependency_overrides.clear()
