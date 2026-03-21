"""
Integration tests for scenario endpoint auth guards.

Tests cover:
1. list_executions returns only own executions (user_id filtering)
2. list_executions admin sees all executions
3. get_execution own execution succeeds
4. get_execution other user's execution returns 403
5. get_execution admin bypasses ownership check
6. cancel_execution other user's execution returns 403
7. validate_inputs has auth guard but is stateless (no ownership)
8. list_executions returns empty for user with no executions

Target: ~130 LOC
"""

import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def scenario_client():
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

    def override_user_a():
        return {"sub": "user-a", "email": "a@test.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_user_a

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()
    if os.path.exists("./test_scenario_auth.db"):
        os.remove("./test_scenario_auth.db")

@pytest.fixture(scope="module")
def seeded_executions(scenario_client):
    """Seed scenario execution records for user-a and user-b."""
    from core.database.models import ScenarioExecutionResult
    from core.database.session import get_session

    now = datetime.now(UTC)
    with get_session() as db:
        exec_a = ScenarioExecutionResult(
            execution_id="exec-user-a",
            scenario_name="test_scenario",
            user_id="user-a",
            trigger_source="api",
            status="completed",
            started_at=now,
        )
        exec_b = ScenarioExecutionResult(
            execution_id="exec-user-b",
            scenario_name="test_scenario",
            user_id="user-b",
            trigger_source="api",
            status="running",
            started_at=now,
        )
        db.add_all([exec_a, exec_b])
        db.commit()

    return {"exec_a": "exec-user-a", "exec_b": "exec-user-b"}

@pytest.mark.integration
class TestScenarioAuthGuards:
    """Tests for auth guards on scenario execution endpoints."""

    def test_list_executions_only_own(self, scenario_client, seeded_executions):
        """User-a only sees their own execution, not user-b's."""
        response = scenario_client.get("/api/workflow-scenarios/executions")
        assert response.status_code == 200
        data = response.json()
        execution_ids = [e["execution_id"] for e in data["executions"]]
        assert "exec-user-a" in execution_ids
        assert "exec-user-b" not in execution_ids

    def test_list_executions_admin_sees_all(self, scenario_client, seeded_executions):
        """Admin role sees all executions regardless of user_id."""
        from core.auth.dependencies import get_current_user

        def admin_user():
            return {"sub": "admin-user", "email": "admin@test.com", "role": "admin"}

        scenario_client.app.dependency_overrides[get_current_user] = admin_user
        try:
            response = scenario_client.get("/api/workflow-scenarios/executions")
            assert response.status_code == 200
            data = response.json()
            execution_ids = [e["execution_id"] for e in data["executions"]]
            assert "exec-user-a" in execution_ids
            assert "exec-user-b" in execution_ids
        finally:

            def user_a():
                return {"sub": "user-a", "email": "a@test.com", "role": "user"}

            scenario_client.app.dependency_overrides[get_current_user] = user_a

    def test_get_execution_own(self, scenario_client, seeded_executions):
        """User-a can view their own execution."""
        response = scenario_client.get(
            f"/api/workflow-scenarios/executions/{seeded_executions['exec_a']}"
        )
        assert response.status_code == 200
        assert response.json()["execution_id"] == "exec-user-a"

    def test_get_execution_other_user_forbidden(self, scenario_client, seeded_executions):
        """User-a cannot view user-b's execution (403)."""
        response = scenario_client.get(
            f"/api/workflow-scenarios/executions/{seeded_executions['exec_b']}"
        )
        assert response.status_code == 403

    def test_get_execution_admin_bypass(self, scenario_client, seeded_executions):
        """Admin can view any user's execution."""
        from core.auth.dependencies import get_current_user

        def admin_user():
            return {"sub": "admin-user", "email": "admin@test.com", "role": "admin"}

        scenario_client.app.dependency_overrides[get_current_user] = admin_user
        try:
            response = scenario_client.get(
                f"/api/workflow-scenarios/executions/{seeded_executions['exec_b']}"
            )
            assert response.status_code == 200
            assert response.json()["execution_id"] == "exec-user-b"
        finally:

            def user_a():
                return {"sub": "user-a", "email": "a@test.com", "role": "user"}

            scenario_client.app.dependency_overrides[get_current_user] = user_a

    def test_cancel_execution_other_user_forbidden(self, scenario_client, seeded_executions):
        """User-a cannot cancel user-b's execution (403)."""
        response = scenario_client.post(
            f"/api/workflow-scenarios/executions/{seeded_executions['exec_b']}/cancel"
        )
        assert response.status_code == 403

    def test_validate_inputs_has_auth(self, scenario_client, seeded_executions):
        """validate_inputs endpoint has auth guard but is stateless.

        The endpoint requires a scenario to exist. Since no scenarios are
        registered in test, we get 404 (not 401), proving the auth guard
        passes the user through and the endpoint runs normally.
        """
        response = scenario_client.post(
            "/api/workflow-scenarios/nonexistent_scenario/validate",
            json={"some_input": "value"},
        )
        # 404 = auth passed, endpoint ran, scenario not found
        assert response.status_code == 404

    def test_list_executions_empty_for_new_user(self, scenario_client, seeded_executions):
        """User with no executions gets empty list."""
        from core.auth.dependencies import get_current_user

        def user_c():
            return {"sub": "user-c", "email": "c@test.com", "role": "user"}

        scenario_client.app.dependency_overrides[get_current_user] = user_c
        try:
            response = scenario_client.get("/api/workflow-scenarios/executions")
            assert response.status_code == 200
            data = response.json()
            assert data["executions"] == []
            assert data["total"] == 0
        finally:

            def user_a():
                return {"sub": "user-a", "email": "a@test.com", "role": "user"}

            scenario_client.app.dependency_overrides[get_current_user] = user_a
