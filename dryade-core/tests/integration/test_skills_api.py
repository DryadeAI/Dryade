"""
Integration tests for skills API routes.

Tests cover:
1. GET /api/skills - list skills
2. GET /api/skills/{name} - get skill details
3. POST /api/skills - create skill
4. PUT /api/skills/{name} - update skill
5. DELETE /api/skills/{name} - delete skill
6. POST /api/skills/{name}/preview - preview formatted skill
7. POST /api/skills/{name}/test - test skill with input
8. Error cases (invalid name, duplicate, not found)

Target: ~80+ LOC
"""

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def skills_client():
    """Create test FastAPI app for skills endpoints."""
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
        return {"sub": "test-user-skills", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_skills.db"):
        os.remove("./test_skills.db")

@pytest.fixture(scope="module")
def test_skills_dir(tmp_path_factory):
    """Create a temporary user skills directory."""
    user_skills_dir = Path.home() / ".dryade" / "skills"
    user_skills_dir.mkdir(parents=True, exist_ok=True)
    return user_skills_dir

@pytest.fixture
def cleanup_test_skill(test_skills_dir):
    """Cleanup test skills after each test."""
    yield
    # Clean up any test skills created
    for skill_name in ["test-skill", "api-test-skill", "update-test-skill"]:
        skill_dir = test_skills_dir / skill_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

# =============================================================================
# Test: List Skills
# =============================================================================

@pytest.mark.integration
class TestListSkills:
    """Tests for GET /api/skills endpoint."""

    def test_list_skills(self, skills_client):
        """Test listing all skills."""
        response = skills_client.get("/api/skills")

        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert "total" in data
        assert "eligible_count" in data
        assert isinstance(data["skills"], list)

    def test_list_skills_include_ineligible(self, skills_client):
        """Test listing skills with ineligible included."""
        response = skills_client.get("/api/skills?include_ineligible=true")

        assert response.status_code == 200
        data = response.json()
        assert "skills" in data

    def test_list_eligible_skills_endpoint(self, skills_client):
        """Test the eligible-only convenience endpoint."""
        response = skills_client.get("/api/skills/eligible/list")

        assert response.status_code == 200
        data = response.json()
        assert "skills" in data

# =============================================================================
# Test: Get Skill Details
# =============================================================================

@pytest.mark.integration
class TestGetSkillDetails:
    """Tests for GET /api/skills/{name} endpoint."""

    def test_get_skill_not_found(self, skills_client):
        """Test 404 for non-existent skill."""
        response = skills_client.get("/api/skills/nonexistent-skill-xyz")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

# =============================================================================
# Test: Create Skill
# =============================================================================

@pytest.mark.integration
class TestCreateSkill:
    """Tests for POST /api/skills endpoint."""

    def test_create_skill(self, skills_client, cleanup_test_skill):
        """Test creating a new skill."""
        skill_data = {
            "name": "api-test-skill",
            "description": "A test skill created via API",
            "instructions": "# Test Instructions\n\nDo the test thing.",
            "emoji": "+",
        }

        response = skills_client.post("/api/skills", json=skill_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "api-test-skill"
        assert "skill_dir" in data
        assert "message" in data

    def test_create_skill_duplicate(self, skills_client, cleanup_test_skill):
        """Test that duplicate skill names return 409."""
        skill_data = {
            "name": "api-test-skill",
            "description": "First version",
            "instructions": "First instructions",
        }

        # Create first
        response = skills_client.post("/api/skills", json=skill_data)
        assert response.status_code == 201

        # Try to create duplicate
        response = skills_client.post("/api/skills", json=skill_data)
        assert response.status_code == 409

    def test_create_skill_invalid_name(self, skills_client):
        """Test that invalid skill names are rejected."""
        skill_data = {
            "name": "Invalid Name With Spaces",
            "description": "Test",
            "instructions": "Test",
        }

        response = skills_client.post("/api/skills", json=skill_data)

        # Should fail validation (422 Unprocessable Entity)
        assert response.status_code == 422

    def test_create_skill_with_requirements(self, skills_client, cleanup_test_skill):
        """Test creating a skill with system requirements."""
        skill_data = {
            "name": "api-test-skill",
            "description": "Skill with requirements",
            "instructions": "Do things",
            "os": ["linux", "darwin"],
            "requires_bins": ["python"],
            "requires_env": ["HOME"],
        }

        response = skills_client.post("/api/skills", json=skill_data)

        assert response.status_code == 201

# =============================================================================
# Test: Update Skill
# =============================================================================

@pytest.mark.integration
class TestUpdateSkill:
    """Tests for PUT /api/skills/{name} endpoint."""

    def test_update_skill(self, skills_client, cleanup_test_skill):
        """Test updating an existing skill."""
        # First create a skill
        create_data = {
            "name": "update-test-skill",
            "description": "Original description",
            "instructions": "Original instructions",
        }
        response = skills_client.post("/api/skills", json=create_data)
        assert response.status_code == 201

        # Now update it
        update_data = {
            "description": "Updated description",
            "instructions": "Updated instructions",
        }
        response = skills_client.put("/api/skills/update-test-skill", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["instructions"] == "Updated instructions"

    def test_update_skill_not_found(self, skills_client):
        """Test 404 when updating non-existent skill."""
        update_data = {"description": "New description"}

        response = skills_client.put("/api/skills/nonexistent-xyz", json=update_data)

        assert response.status_code == 404

# =============================================================================
# Test: Delete Skill
# =============================================================================

@pytest.mark.integration
class TestDeleteSkill:
    """Tests for DELETE /api/skills/{name} endpoint."""

    def test_delete_skill(self, skills_client, test_skills_dir):
        """Test deleting a skill."""
        # First create a skill
        create_data = {
            "name": "test-skill",
            "description": "To be deleted",
            "instructions": "Delete me",
        }
        response = skills_client.post("/api/skills", json=create_data)
        assert response.status_code == 201

        # Now delete it
        response = skills_client.delete("/api/skills/test-skill")

        assert response.status_code == 204

    def test_delete_skill_not_found(self, skills_client):
        """Test 404 when deleting non-existent skill."""
        response = skills_client.delete("/api/skills/nonexistent-xyz")

        assert response.status_code == 404

    def test_delete_skill_invalid_name(self, skills_client):
        """Test that path traversal attempts are blocked."""
        response = skills_client.delete("/api/skills/../../../etc")

        # Path traversal is handled - returns either 400 or 404
        assert response.status_code in [400, 404]

# =============================================================================
# Test: Preview Skill
# =============================================================================

@pytest.mark.integration
class TestPreviewSkill:
    """Tests for POST /api/skills/{name}/preview endpoint."""

    def test_preview_skill(self, skills_client, cleanup_test_skill):
        """Test previewing a skill's formatted output."""
        # First create a skill
        create_data = {
            "name": "api-test-skill",
            "description": "Preview test",
            "instructions": "# Test\n\nPreview instructions.",
        }
        response = skills_client.post("/api/skills", json=create_data)
        assert response.status_code == 201

        # Preview it
        response = skills_client.post("/api/skills/api-test-skill/preview")

        assert response.status_code == 200
        data = response.json()
        assert "formatted_prompt" in data
        assert "token_estimate" in data
        assert "guidance" in data
        assert "<available-skills>" in data["formatted_prompt"]

    def test_preview_skill_not_found(self, skills_client):
        """Test 404 when previewing non-existent skill."""
        response = skills_client.post("/api/skills/nonexistent-xyz/preview")

        assert response.status_code == 404

# =============================================================================
# Test: Test Skill
# =============================================================================

@pytest.mark.integration
class TestTestSkill:
    """Tests for POST /api/skills/{name}/test endpoint."""

    def test_test_skill(self, skills_client, cleanup_test_skill):
        """Test testing a skill with sample input."""
        # First create a skill
        create_data = {
            "name": "api-test-skill",
            "description": "Test skill for testing",
            "instructions": "Use this skill to help with testing.",
        }
        response = skills_client.post("/api/skills", json=create_data)
        assert response.status_code == 201

        # Test it - use embed=True format with sample_task key
        response = skills_client.post(
            "/api/skills/api-test-skill/test",
            json={"sample_task": "Help me run a test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "system_prompt_preview" in data
        assert "sample_task" in data
        assert "token_estimate" in data

    def test_test_skill_not_found(self, skills_client):
        """Test 404 when testing non-existent skill."""
        response = skills_client.post(
            "/api/skills/nonexistent-xyz/test",
            json={"sample_task": "Test input"},
        )

        assert response.status_code == 404

# =============================================================================
# Test: Full CRUD Flow
# =============================================================================

@pytest.mark.integration
class TestCRUDFlow:
    """Test complete CRUD workflow."""

    def test_full_crud_flow(self, skills_client, test_skills_dir):
        """Test create -> read -> update -> delete flow."""
        skill_name = "crud-test-skill"
        skill_dir = test_skills_dir / skill_name

        try:
            # 1. Create
            create_data = {
                "name": skill_name,
                "description": "CRUD test",
                "instructions": "Initial",
            }
            response = skills_client.post("/api/skills", json=create_data)
            assert response.status_code == 201

            # 2. Read
            response = skills_client.get(f"/api/skills/{skill_name}")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == skill_name
            assert data["description"] == "CRUD test"

            # 3. Update
            update_data = {"description": "Updated CRUD test"}
            response = skills_client.put(f"/api/skills/{skill_name}", json=update_data)
            assert response.status_code == 200
            data = response.json()
            assert data["description"] == "Updated CRUD test"

            # 4. Delete
            response = skills_client.delete(f"/api/skills/{skill_name}")
            assert response.status_code == 204

            # 5. Verify deleted
            response = skills_client.get(f"/api/skills/{skill_name}")
            assert response.status_code == 404

        finally:
            # Cleanup
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
