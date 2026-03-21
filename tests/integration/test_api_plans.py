"""
Integration tests for plans API routes.

Tests cover:
1. List plans (empty, with filters)
2. Create plan (success, validation errors)
3. Get plan by ID
4. Update plan (draft, immutable)
5. Delete plan (draft, executing)
6. Execute plan
7. List executions
8. Submit feedback
9. Plan templates

Target: ~220 LOC
"""

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def plans_client(integration_test_app):
    """Test client for plans API tests, reusing the session-scoped app."""
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-plans", "email": "test@example.com", "role": "user"}

    integration_test_app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        yield client

    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def sample_plan_data():
    """Sample plan data for testing."""
    return {
        "conversation_id": "test-conv-123",
        "name": "Test Research Plan",
        "description": "A plan for testing",
        "nodes": [
            {"id": "node1", "agent": "research_assistant", "task": "Research topic"},
            {
                "id": "node2",
                "agent": "project_manager",
                "task": "Write summary",
                "depends_on": ["node1"],
            },
        ],
        "edges": [{"from": "node1", "to": "node2"}],
        "confidence": 0.85,
        "status": "draft",
    }

@pytest.fixture
def created_conversation(integration_test_app):
    """Create a conversation for plan tests (idempotent — handles existing rows)."""
    from core.database.models import Conversation
    from core.database.session import get_session

    with get_session() as session:
        conv = session.query(Conversation).filter_by(id="test-conv-123").first()
        if not conv:
            conv = Conversation(
                id="test-conv-123",
                user_id="test-user-plans",
                title="Test Conversation",
                mode="planner",
            )
            session.add(conv)

    yield conv

@pytest.mark.integration
class TestPlansListEndpoint:
    """Tests for GET /api/plans endpoint."""

    def test_list_plans_empty(self, plans_client):
        """Test listing plans when none exist."""
        response = plans_client.get("/api/plans")
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert data["total"] >= 0
        assert "has_more" in data

    def test_list_plans_with_filters(self, plans_client):
        """Test listing plans with filters."""
        response = plans_client.get("/api/plans?status=draft&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert data["limit"] == 10

@pytest.mark.integration
class TestPlansCreateEndpoint:
    """Tests for POST /api/plans endpoint."""

    def test_create_plan_success(self, plans_client, sample_plan_data, created_conversation):
        """Test creating a plan successfully."""
        response = plans_client.post("/api/plans", json=sample_plan_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_plan_data["name"]
        assert data["status"] == "draft"
        assert "id" in data
        assert data["execution_count"] == 0

    def test_create_plan_missing_conversation(self, plans_client, sample_plan_data):
        """Test 404 when conversation doesn't exist."""
        bad_data = {**sample_plan_data, "conversation_id": "nonexistent-conv"}
        response = plans_client.post("/api/plans", json=bad_data)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_create_plan_validation_error(self, plans_client, created_conversation):
        """Test validation error for invalid plan data."""
        bad_data = {
            "conversation_id": "test-conv-123",
            "name": "",  # Empty name should fail
            "nodes": [],
        }
        response = plans_client.post("/api/plans", json=bad_data)
        assert response.status_code == 422

@pytest.mark.integration
class TestPlansGetEndpoint:
    """Tests for GET /api/plans/{plan_id} endpoint."""

    def test_get_plan_not_found(self, plans_client):
        """Test 404 when plan not found."""
        response = plans_client.get("/api/plans/99999")
        assert response.status_code == 404

    def test_get_plan_by_id(self, plans_client, sample_plan_data, created_conversation):
        """Test getting plan details."""
        # Create plan first
        create_response = plans_client.post("/api/plans", json=sample_plan_data)
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]

        # Get plan
        response = plans_client.get(f"/api/plans/{plan_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == plan_id
        assert data["name"] == sample_plan_data["name"]

@pytest.mark.integration
class TestPlansUpdateEndpoint:
    """Tests for PUT /api/plans/{plan_id} endpoint."""

    def test_update_plan_draft(self, plans_client, sample_plan_data, created_conversation):
        """Test updating a draft plan."""
        # Create plan
        create_response = plans_client.post("/api/plans", json=sample_plan_data)
        plan_id = create_response.json()["id"]

        # Update plan
        update_data = {"name": "Updated Plan Name", "status": "approved"}
        response = plans_client.put(f"/api/plans/{plan_id}", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Plan Name"
        assert data["status"] == "approved"

    def test_update_plan_not_found(self, plans_client):
        """Test 404 when updating nonexistent plan."""
        response = plans_client.put("/api/plans/99999", json={"name": "New Name"})
        assert response.status_code == 404

@pytest.mark.integration
class TestPlansDeleteEndpoint:
    """Tests for DELETE /api/plans/{plan_id} endpoint."""

    def test_delete_plan_success(self, plans_client, sample_plan_data, created_conversation):
        """Test deleting a draft plan."""
        # Create plan
        create_response = plans_client.post("/api/plans", json=sample_plan_data)
        plan_id = create_response.json()["id"]

        # Delete plan
        response = plans_client.delete(f"/api/plans/{plan_id}")
        assert response.status_code == 204

        # Verify deleted
        get_response = plans_client.get(f"/api/plans/{plan_id}")
        assert get_response.status_code == 404

    def test_delete_plan_not_found(self, plans_client):
        """Test 404 when deleting nonexistent plan."""
        response = plans_client.delete("/api/plans/99999")
        assert response.status_code == 404

@pytest.mark.integration
class TestPlansExecuteEndpoint:
    """Tests for POST /api/plans/{plan_id}/execute endpoint."""

    def test_execute_plan(self, plans_client, sample_plan_data, created_conversation):
        """Test executing a plan creates execution record."""
        # Create plan
        create_response = plans_client.post("/api/plans", json=sample_plan_data)
        plan_id = create_response.json()["id"]

        # Execute plan
        response = plans_client.post(f"/api/plans/{plan_id}/execute", json={})
        assert response.status_code == 200
        data = response.json()
        assert "execution_id" in data
        assert data["status"] == "executing"

    def test_execute_plan_not_found(self, plans_client):
        """Test 404 when executing nonexistent plan."""
        response = plans_client.post("/api/plans/99999/execute", json={})
        assert response.status_code == 404

@pytest.mark.integration
class TestPlansExecutionsEndpoint:
    """Tests for GET /api/plans/{plan_id}/executions endpoint."""

    def test_list_executions_empty(self, plans_client, sample_plan_data, created_conversation):
        """Test listing executions for plan without any."""
        # Create plan
        create_response = plans_client.post("/api/plans", json=sample_plan_data)
        plan_id = create_response.json()["id"]

        # List executions
        response = plans_client.get(f"/api/plans/{plan_id}/executions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_executions_not_found(self, plans_client):
        """Test 404 when listing executions for nonexistent plan."""
        response = plans_client.get("/api/plans/99999/executions")
        assert response.status_code == 404

@pytest.mark.integration
class TestPlansFeedbackEndpoint:
    """Tests for POST /api/plans/{plan_id}/feedback endpoint."""

    def test_submit_feedback_plan_not_found(self, plans_client):
        """Test 404 when submitting feedback for nonexistent plan."""
        feedback_data = {"execution_id": "exec-123", "rating": 5, "comment": "Great!"}
        response = plans_client.post("/api/plans/99999/feedback", json=feedback_data)
        assert response.status_code == 404

@pytest.mark.integration
class TestPlanTemplatesEndpoint:
    """Tests for plan templates endpoints."""

    def test_list_templates(self, plans_client):
        """Test listing plan templates."""
        response = plans_client.get("/api/plan-templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data

    def test_list_templates_with_category(self, plans_client):
        """Test listing templates filtered by category."""
        response = plans_client.get("/api/plan-templates?category=testing")
        assert response.status_code == 200

class TestResolveStepReferences:
    """Unit tests for _resolve_step_references helper."""

    def test_no_references(self):
        """Plain values pass through unchanged."""
        from core.api.routes.plans import _resolve_step_references

        args = {"path": "/home/user/model.aird", "count": 5}
        result = _resolve_step_references(args, {})
        assert result == {"path": "/home/user/model.aird", "count": 5}

    def test_full_step_reference(self):
        """{{step_1}} resolves to full step output."""
        from core.api.routes.plans import _resolve_step_references

        args = {"session_id": "{{step_1}}"}
        results = {"step_1": "abc123"}
        result = _resolve_step_references(args, results)
        assert result == {"session_id": "abc123"}

    def test_json_field_reference(self):
        """{{step_1.session_id}} extracts field from JSON output."""
        from core.api.routes.plans import _resolve_step_references

        args = {"session_id": "{{step_1.session_id}}"}
        results = {"step_1": '{"status": "ok", "session_id": "abc123"}'}
        result = _resolve_step_references(args, results)
        assert result == {"session_id": "abc123"}

    def test_missing_step(self):
        """Missing step reference keeps placeholder intact."""
        from core.api.routes.plans import _resolve_step_references

        args = {"session_id": "{{step_99}}"}
        result = _resolve_step_references(args, {})
        assert result == {"session_id": "{{step_99}}"}

    def test_non_json_output_with_field(self):
        """Non-JSON output with field reference falls back to full output."""
        from core.api.routes.plans import _resolve_step_references

        args = {"data": "{{step_1.field}}"}
        results = {"step_1": "plain text output"}
        result = _resolve_step_references(args, results)
        assert result == {"data": "plain text output"}

    def test_non_string_values_pass_through(self):
        """Non-string values (int, bool, list) pass through unchanged."""
        from core.api.routes.plans import _resolve_step_references

        args = {"count": 10, "verbose": True, "tags": ["a", "b"]}
        result = _resolve_step_references(args, {})
        assert result == {"count": 10, "verbose": True, "tags": ["a", "b"]}

    def test_mixed_references_and_literals(self):
        """Mix of references and literal values."""
        from core.api.routes.plans import _resolve_step_references

        args = {
            "session_id": "{{step_1.session_id}}",
            "element_type": "LogicalFunction",
            "layer": "LA",
        }
        results = {"step_1": '{"session_id": "sess_abc"}'}
        result = _resolve_step_references(args, results)
        assert result == {
            "session_id": "sess_abc",
            "element_type": "LogicalFunction",
            "layer": "LA",
        }

class TestResolveAgentName:
    """Unit tests for _resolve_agent_name fuzzy matching."""

    def test_exact_match(self):
        """Exact agent name returns directly."""
        from unittest.mock import MagicMock, patch

        mock_agent = MagicMock()
        with patch("core.adapters.get_agent", return_value=mock_agent):
            from core.api.routes.plans import _resolve_agent_name

            name, agent = _resolve_agent_name("mcp-capella")
            assert name == "mcp-capella"
            assert agent is mock_agent

    def test_normalised_match_dot_to_underscore(self):
        """capella.capella -> mcp-capella via substring match."""
        from unittest.mock import MagicMock, patch

        mock_card = MagicMock()
        mock_card.name = "mcp-capella"
        mock_agent = MagicMock()

        def fake_get_agent(name):
            if name == "mcp-capella":
                return mock_agent
            return None

        with (
            patch("core.adapters.get_agent", side_effect=fake_get_agent),
            patch("core.adapters.list_agents", return_value=[mock_card]),
        ):
            from core.api.routes.plans import _resolve_agent_name

            name, agent = _resolve_agent_name("capella.capella")
            # "capella_capella" contains "capella" which is in "mcp_capella"
            assert agent is mock_agent

    def test_substring_match(self):
        """Substring matching picks best overlap."""
        from unittest.mock import MagicMock, patch

        mock_card_1 = MagicMock()
        mock_card_1.name = "mcp-capella"
        mock_card_2 = MagicMock()
        mock_card_2.name = "capella_traceability_healer"
        mock_agent = MagicMock()

        def fake_get_agent(name):
            if name == "capella_traceability_healer":
                return mock_agent
            return None

        with (
            patch("core.adapters.get_agent", side_effect=fake_get_agent),
            patch(
                "core.adapters.list_agents",
                return_value=[mock_card_1, mock_card_2],
            ),
        ):
            from core.api.routes.plans import _resolve_agent_name

            name, agent = _resolve_agent_name("capella_traceability")
            # "capella_traceability" is a substring of "capella_traceability_healer"
            assert name == "capella_traceability_healer"
            assert agent is mock_agent

    def test_mcp_prefix_fallback(self):
        """'capella' with mcp- prefix -> 'mcp-capella'."""
        from unittest.mock import MagicMock, patch

        mock_agent = MagicMock()

        def fake_get_agent(name):
            if name == "mcp-capella":
                return mock_agent
            return None

        with (
            patch("core.adapters.get_agent", side_effect=fake_get_agent),
            patch("core.adapters.list_agents", return_value=[]),
        ):
            from core.api.routes.plans import _resolve_agent_name

            name, agent = _resolve_agent_name("capella")
            assert name == "mcp-capella"
            assert agent is mock_agent

    def test_unresolvable_returns_none(self):
        """Completely unknown name returns None."""
        from unittest.mock import patch

        with (
            patch("core.adapters.get_agent", return_value=None),
            patch("core.adapters.list_agents", return_value=[]),
        ):
            from core.api.routes.plans import _resolve_agent_name

            name, agent = _resolve_agent_name("totally_unknown_agent")
            assert agent is None
