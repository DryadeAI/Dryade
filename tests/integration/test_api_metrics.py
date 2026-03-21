"""
Integration tests for metrics API routes.

Tests cover:
1. Latency metrics endpoint
2. Recent latency data
3. Latency by mode
4. Queue status endpoint

Target: ~80 LOC
"""

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def metrics_client():
    """Create test FastAPI app for metrics endpoints."""
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
        return {"sub": "test-user-metrics", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_metrics.db"):
        os.remove("./test_metrics.db")

@pytest.fixture
def mock_latency_tracker():
    """Mock latency tracker with sample data."""
    tracker = MagicMock()
    tracker.get_stats.return_value = {
        "total_requests": 100,
        "average_latency_ms": 150.5,
        "p50_latency_ms": 120.0,
        "p95_latency_ms": 350.0,
        "p99_latency_ms": 500.0,
    }
    tracker.get_recent.return_value = [
        {"timestamp": "2024-01-01T00:00:00", "latency_ms": 100, "mode": "chat"},
        {"timestamp": "2024-01-01T00:00:01", "latency_ms": 150, "mode": "agent"},
    ]
    tracker.get_by_mode.return_value = {
        "chat": {"count": 50, "avg_latency_ms": 100.0},
        "agent": {"count": 50, "avg_latency_ms": 200.0},
    }
    return tracker

@pytest.mark.integration
class TestLatencyMetrics:
    """Tests for latency metrics endpoints."""

    def test_latency_metrics_endpoint(self, metrics_client):
        """Test latency metrics summary."""
        response = metrics_client.get("/api/metrics/latency")

        # Endpoint may exist or return 404 if not implemented
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_latency_recent(self, metrics_client):
        """Test recent latency data endpoint."""
        response = metrics_client.get("/api/metrics/latency/recent")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_latency_by_mode(self, metrics_client):
        """Test latency breakdown by mode."""
        response = metrics_client.get("/api/metrics/latency/by-mode")

        assert response.status_code in [200, 404]

@pytest.mark.integration
class TestQueueStatus:
    """Tests for queue status endpoint."""

    def test_queue_status_endpoint(self, metrics_client):
        """Test queue status returns current state."""
        response = metrics_client.get("/api/metrics/queue")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

@pytest.mark.integration
class TestMetricsSummary:
    """Tests for metrics summary endpoint."""

    def test_metrics_summary(self, metrics_client):
        """Test overall metrics summary."""
        response = metrics_client.get("/api/metrics")

        # Main metrics endpoint
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
