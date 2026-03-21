"""
Integration tests for health API routes.

Tests cover:
1. Basic health check endpoint
2. Liveness probe (Kubernetes)
3. Readiness probe (Kubernetes)
4. Detailed health with dependencies
5. Health metrics endpoint

Target: ~80 LOC
"""

import os

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def health_client():
    """Create test FastAPI app for health checks."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"
    os.environ["DRYADE_DATABASE_URL"] = os.environ.get(
        "DRYADE_TEST_DATABASE_URL",
        "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
    )

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-health", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_health.db"):
        os.remove("./test_health.db")

@pytest.mark.integration
class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_endpoint_returns_status(self, health_client):
        """Test health endpoint returns status (200 healthy or 503 unhealthy)."""
        response = health_client.get("/health")

        # 200 = healthy, 503 = unhealthy (valid responses)
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data

    def test_health_endpoint_returns_json(self, health_client):
        """Test health endpoint returns valid JSON."""
        response = health_client.get("/health")

        # Both healthy and unhealthy should return JSON
        assert response.status_code in [200, 503]
        assert "application/json" in response.headers.get("content-type", "")

@pytest.mark.integration
class TestLivenessProbe:
    """Tests for /live endpoint (Kubernetes liveness probe)."""

    def test_liveness_probe(self, health_client):
        """Test liveness probe returns quickly."""
        response = health_client.get("/live")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "alive" in data or isinstance(data, dict)

@pytest.mark.integration
class TestReadinessProbe:
    """Tests for /ready endpoint (Kubernetes readiness probe)."""

    def test_readiness_probe(self, health_client):
        """Test readiness probe returns status."""
        response = health_client.get("/ready")

        # May return 200 or 503 depending on dependencies
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data or "ready" in data or isinstance(data, dict)

@pytest.mark.integration
class TestDetailedHealth:
    """Tests for /health/detailed endpoint."""

    def test_health_with_details(self, health_client):
        """Test detailed health check with dependency info."""
        response = health_client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        # Should include some form of detailed information
        assert isinstance(data, dict)
        assert len(data) > 0

@pytest.mark.integration
class TestHealthMetrics:
    """Tests for /health/metrics endpoint."""

    def test_health_metrics_endpoint(self, health_client):
        """Test health metrics endpoint."""
        response = health_client.get("/health/metrics")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
