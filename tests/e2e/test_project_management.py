"""End-to-end tests for project management and conversation assignment.

Tests the complete project lifecycle: creation, listing, archiving,
and assigning/removing conversations from projects.
"""

import pytest

pytestmark = pytest.mark.e2e

class TestProjectManagement:
    """E2E tests for the project management workflow."""

    def test_create_project(self, e2e_client):
        """Create a project with all fields and verify the response."""
        resp = e2e_client.post(
            "/api/projects",
            json={
                "name": "Test Project",
                "description": "A project for E2E testing",
                "icon": "\U0001f4c1",
                "color": "#3B82F6",
            },
        )

        assert resp.status_code == 201
        data = resp.json()

        assert data["name"] == "Test Project"
        assert data["description"] == "A project for E2E testing"
        assert data["icon"] == "\U0001f4c1"
        assert data["color"] == "#3B82F6"
        assert data["is_archived"] is False
        assert data["conversation_count"] == 0
        assert data["id"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    def test_assign_conversation_to_project(self, e2e_client):
        """Create a project and conversation, assign the conversation, then verify."""
        # Create project
        proj_resp = e2e_client.post(
            "/api/projects",
            json={"name": "Assignment Project", "description": "For assignment test"},
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        # Create conversation
        conv_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Conv for project", "mode": "chat"},
        )
        assert conv_resp.status_code == 201
        conversation_id = conv_resp.json()["id"]

        # Assign conversation to project
        move_resp = e2e_client.patch(
            f"/api/chat/conversations/{conversation_id}/project",
            json={"project_id": project_id},
        )
        assert move_resp.status_code == 200
        assert move_resp.json()["project_id"] == project_id

        # List project conversations and verify the conversation is present
        list_resp = e2e_client.get(f"/api/projects/{project_id}/conversations")
        assert list_resp.status_code == 200
        conversations = list_resp.json()["conversations"]
        conv_ids = [c["id"] for c in conversations]
        assert conversation_id in conv_ids

    def test_list_projects_with_counts(self, e2e_client):
        """Create a project, assign two conversations, and verify conversation_count."""
        # Create project
        proj_resp = e2e_client.post(
            "/api/projects",
            json={"name": "Count Project", "description": "For count test"},
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        # Create and assign two conversations
        for i in range(2):
            conv_resp = e2e_client.post(
                "/api/chat/conversations",
                json={"title": f"Conv {i}", "mode": "chat"},
            )
            assert conv_resp.status_code == 201
            conversation_id = conv_resp.json()["id"]

            move_resp = e2e_client.patch(
                f"/api/chat/conversations/{conversation_id}/project",
                json={"project_id": project_id},
            )
            assert move_resp.status_code == 200

        # List projects and find ours
        list_resp = e2e_client.get("/api/projects")
        assert list_resp.status_code == 200

        projects = list_resp.json()["projects"]
        target = next((p for p in projects if p["id"] == project_id), None)
        assert target is not None
        assert target["conversation_count"] == 2

    def test_remove_conversation_from_project(self, e2e_client):
        """Assign a conversation to a project, then remove it with project_id=null."""
        # Create project
        proj_resp = e2e_client.post(
            "/api/projects",
            json={"name": "Remove Project", "description": "For removal test"},
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        # Create conversation
        conv_resp = e2e_client.post(
            "/api/chat/conversations",
            json={"title": "Conv to remove", "mode": "chat"},
        )
        assert conv_resp.status_code == 201
        conversation_id = conv_resp.json()["id"]

        # Assign to project
        move_resp = e2e_client.patch(
            f"/api/chat/conversations/{conversation_id}/project",
            json={"project_id": project_id},
        )
        assert move_resp.status_code == 200
        assert move_resp.json()["project_id"] == project_id

        # Remove from project
        remove_resp = e2e_client.patch(
            f"/api/chat/conversations/{conversation_id}/project",
            json={"project_id": None},
        )
        assert remove_resp.status_code == 200
        assert remove_resp.json()["project_id"] is None

        # Verify the conversation is no longer in the project
        list_resp = e2e_client.get(f"/api/projects/{project_id}/conversations")
        assert list_resp.status_code == 200
        conversations = list_resp.json()["conversations"]
        conv_ids = [c["id"] for c in conversations]
        assert conversation_id not in conv_ids

    def test_archive_project(self, e2e_client):
        """Create a project, archive it via PATCH, and verify the archived state."""
        # Create project
        proj_resp = e2e_client.post(
            "/api/projects",
            json={"name": "Archive Project", "description": "For archive test"},
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]
        assert proj_resp.json()["is_archived"] is False

        # Archive the project
        archive_resp = e2e_client.patch(
            f"/api/projects/{project_id}",
            json={"is_archived": True},
        )
        assert archive_resp.status_code == 200
        assert archive_resp.json()["is_archived"] is True

        # Verify via GET that the project is archived
        get_resp = e2e_client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_archived"] is True

        # Archived projects should be excluded from default list
        list_resp = e2e_client.get("/api/projects")
        assert list_resp.status_code == 200
        listed_ids = [p["id"] for p in list_resp.json()["projects"]]
        assert project_id not in listed_ids

        # But included when explicitly requested
        list_all_resp = e2e_client.get("/api/projects?include_archived=true")
        assert list_all_resp.status_code == 200
        all_ids = [p["id"] for p in list_all_resp.json()["projects"]]
        assert project_id in all_ids
