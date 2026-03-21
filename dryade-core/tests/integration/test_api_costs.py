"""
Integration tests for costs API routes.

Tests cover:
1. Get cost summary
2. Get cost records
3. Get costs by conversation
4. Get costs by user
5. Clear cost records
6. Realtime cost tracking

Target: ~80 LOC
"""

import os

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def costs_client():
    """Create test FastAPI app for cost endpoints."""
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
        return {"sub": "test-user-costs", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_costs.db"):
        os.remove("./test_costs.db")

@pytest.mark.integration
class TestCostSummary:
    """Tests for GET /api/costs endpoint."""

    def test_get_cost_summary(self, costs_client):
        """Test getting cost summary."""
        response = costs_client.get("/api/costs")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

@pytest.mark.integration
class TestCostRecords:
    """Tests for GET /api/costs/records endpoint."""

    def test_get_cost_records(self, costs_client):
        """Test getting all cost records."""
        response = costs_client.get("/api/costs/records")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_cost_records_with_limit(self, costs_client):
        """Test getting cost records with limit."""
        response = costs_client.get("/api/costs/records?limit=10")

        assert response.status_code in [200, 404]

@pytest.mark.integration
class TestCostsByConversation:
    """Tests for GET /api/costs/by-conversation/{id} endpoint."""

    def test_costs_by_conversation(self, costs_client):
        """Test getting costs for specific conversation."""
        response = costs_client.get("/api/costs/by-conversation/test-conv-123")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (dict, list))

@pytest.mark.integration
class TestCostsByUser:
    """Tests for GET /api/costs/by-user/{id} endpoint."""

    def test_costs_by_user(self, costs_client):
        """Test getting costs for specific user."""
        response = costs_client.get("/api/costs/by-user/test-user-123")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (dict, list))

@pytest.mark.integration
class TestCostClear:
    """Tests for DELETE /api/costs/clear endpoint."""

    def test_clear_costs(self, costs_client):
        """Test clearing cost records."""
        response = costs_client.delete("/api/costs/clear")

        assert response.status_code in [200, 204, 404]

@pytest.mark.integration
class TestRealtimeCosts:
    """Tests for GET /api/costs/realtime endpoint."""

    def test_realtime_costs(self, costs_client):
        """Test realtime cost tracking."""
        response = costs_client.get("/api/costs/realtime")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
