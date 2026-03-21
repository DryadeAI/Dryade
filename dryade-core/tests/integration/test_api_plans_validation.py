"""
Integration tests for plan pre-execution validation endpoint.

Tests cover:
1. Validate plan with valid nodes
2. Validate plan with missing agent
3. Validate MCP node without tool field (warning)
4. Validate MCP node with tool field
5. Validate nonexistent plan (404)
6. Validate plan access denied (403)
7. Validate plan with empty nodes
8. Execute plan blocks on invalid agents (422)

Target: ~130 LOC
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch targets: _resolve_agent_name does `from core.adapters import get_agent, list_agents`
# which resolves to the names in core/adapters/__init__.py (re-exported from registry).
# Patching at the __init__ level intercepts calls from both _resolve_agent_name and
# _validate_plan_agents.
_PATCH_GET_AGENT = "core.adapters.get_agent"
_PATCH_LIST_AGENTS = "core.adapters.list_agents"
_PATCH_MCP_REGISTRY = "core.mcp.registry.get_registry"

@pytest.fixture(scope="module")
def validation_client():
    """Create test FastAPI app with in-memory database."""
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

    def override_user():
        return {"sub": "val-user-a", "email": "val-a@test.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    if os.path.exists("./test_plans_validation.db"):
        os.remove("./test_plans_validation.db")

@pytest.fixture(scope="module")
def test_conversation(validation_client):
    """Create a conversation for plan tests."""
    from core.database.models import Conversation
    from core.database.session import get_session

    with get_session() as session:
        conv = Conversation(
            id="conv-validation-test",
            user_id="val-user-a",
            title="Validation Test",
            mode="planner",
        )
        session.add(conv)

    yield conv

    with get_session() as session:
        session.query(Conversation).filter_by(id="conv-validation-test").delete()

def _create_plan_with_mock(client, nodes, edges=None):
    """Helper to create a plan, mocking agent validation so creation succeeds."""
    mock_agent = MagicMock()
    with patch(_PATCH_GET_AGENT, return_value=mock_agent):
        response = client.post(
            "/api/plans",
            json={
                "conversation_id": "conv-validation-test",
                "name": "Validation Test Plan",
                "nodes": nodes,
                "edges": edges or [],
            },
        )
    assert response.status_code == 201, f"Plan creation failed: {response.json()}"
    return response.json()["id"]

@pytest.mark.integration
class TestValidatePlanEndpoint:
    """Tests for POST /api/plans/{plan_id}/validate endpoint."""

    def test_validate_plan_valid_nodes(self, validation_client, test_conversation):
        """Valid plan with a known agent returns valid=True."""
        mock_agent = MagicMock()
        with patch(_PATCH_GET_AGENT, return_value=mock_agent):
            plan_id = _create_plan_with_mock(
                validation_client,
                [{"id": "n1", "agent": "mock-agent", "task": "Do something"}],
            )
            response = validation_client.post(f"/api/plans/{plan_id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_plan_missing_agent(self, validation_client, test_conversation):
        """Plan with unknown agent returns valid=False with error."""
        # Create plan with mock allowing creation
        plan_id = _create_plan_with_mock(
            validation_client,
            [{"id": "n1", "agent": "nonexistent-agent-xyz", "task": "Do something"}],
        )
        # Validate with agent returning None (not found)
        with (
            patch(_PATCH_GET_AGENT, return_value=None),
            patch(_PATCH_LIST_AGENTS, return_value=[]),
        ):
            response = validation_client.post(f"/api/plans/{plan_id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("not found" in e for e in data["errors"])
        assert len(data["node_issues"]) == 1
        assert data["node_issues"][0]["node_id"] == "n1"

    def test_validate_plan_mcp_node_no_tool_warning(self, validation_client, test_conversation):
        """MCP node without tool field returns valid=True with warning."""
        mock_agent = MagicMock()
        with patch(_PATCH_GET_AGENT, return_value=mock_agent):
            plan_id = _create_plan_with_mock(
                validation_client,
                [{"id": "n1", "agent": "mcp-testserver", "task": "Do something"}],
            )
            response = validation_client.post(f"/api/plans/{plan_id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert any("no explicit" in w.lower() or "tool" in w.lower() for w in data["warnings"])

    def test_validate_plan_mcp_node_with_tool(self, validation_client, test_conversation):
        """MCP node with tool field warns about unregistered server but stays valid."""
        mock_agent = MagicMock()
        plan_id = _create_plan_with_mock(
            validation_client,
            [
                {
                    "id": "n1",
                    "agent": "mcp-testserver",
                    "task": "Do something",
                    "tool": "some_tool",
                    "arguments": {"path": "/test"},
                }
            ],
        )
        mock_registry = MagicMock()
        mock_registry.is_registered.return_value = False
        with (
            patch(_PATCH_GET_AGENT, return_value=mock_agent),
            patch(_PATCH_MCP_REGISTRY, return_value=mock_registry),
        ):
            response = validation_client.post(f"/api/plans/{plan_id}/validate")
        assert response.status_code == 200
        data = response.json()
        # Unregistered server produces warning, not error
        assert data["valid"] is True
        assert len(data["warnings"]) > 0

    def test_validate_plan_not_found(self, validation_client, test_conversation):
        """Validating nonexistent plan returns 404."""
        response = validation_client.post("/api/plans/99999/validate")
        assert response.status_code == 404

    def test_validate_plan_access_denied(self, validation_client, test_conversation):
        """Validating another user's plan returns 403."""
        from core.auth.dependencies import get_current_user

        # Create plan as user-a
        plan_id = _create_plan_with_mock(
            validation_client,
            [{"id": "n1", "agent": "test", "task": "Task"}],
        )

        # Switch to user-b
        def override_user_b():
            return {"sub": "val-user-b", "email": "val-b@test.com", "role": "user"}

        validation_client.app.dependency_overrides[get_current_user] = override_user_b
        try:
            response = validation_client.post(f"/api/plans/{plan_id}/validate")
            assert response.status_code == 403
        finally:
            # Restore user-a
            def override_user_a():
                return {"sub": "val-user-a", "email": "val-a@test.com", "role": "user"}

            validation_client.app.dependency_overrides[get_current_user] = override_user_a

    def test_validate_plan_empty_nodes(self, validation_client, test_conversation):
        """Plan with no nodes is valid (nothing to validate)."""
        plan_id = _create_plan_with_mock(validation_client, [])
        response = validation_client.post(f"/api/plans/{plan_id}/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["warnings"] == []

    def test_execute_plan_blocks_on_invalid_agent(self, validation_client, test_conversation):
        """execute_plan returns 422 when validation finds unknown agents."""
        # Create plan with mock allowing creation
        plan_id = _create_plan_with_mock(
            validation_client,
            [{"id": "n1", "agent": "bad-agent", "task": "Task"}],
        )
        # Execute with agent not found -> validation blocks with 422
        with (
            patch(_PATCH_GET_AGENT, return_value=None),
            patch(_PATCH_LIST_AGENTS, return_value=[]),
        ):
            response = validation_client.post(f"/api/plans/{plan_id}/execute", json={})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["validation"]["errors"]
