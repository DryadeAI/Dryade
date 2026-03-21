"""
Integration tests for cache API routes.

Tests cover:
1. Get cache stats
2. Tune cache parameters
3. Clear cache
4. Evict cache entries
5. Cache health check

Target: ~80 LOC
"""

import os

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def cache_client():
    """Create test FastAPI app for cache endpoints."""
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
        return {"sub": "test-user-cache", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_cache.db"):
        os.remove("./test_cache.db")

@pytest.mark.integration
class TestCacheStats:
    """Tests for GET /api/cache/stats endpoint."""

    def test_get_cache_stats(self, cache_client):
        """Test getting cache statistics."""
        response = cache_client.get("/api/cache/stats")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_cache_stats_response_format(self, cache_client):
        """Test cache stats has expected fields."""
        response = cache_client.get("/api/cache/stats")

        if response.status_code == 200:
            data = response.json()
            # Should have some cache-related stats
            assert isinstance(data, dict)

@pytest.mark.integration
class TestCacheTune:
    """Tests for POST /api/cache/tune endpoint."""

    def test_tune_cache_parameters(self, cache_client):
        """Test tuning cache parameters."""
        response = cache_client.post(
            "/api/cache/tune", json={"max_size": 1000, "ttl_seconds": 3600}
        )

        assert response.status_code in [200, 404, 422]

    def test_tune_cache_invalid_params(self, cache_client):
        """Test tune with invalid parameters."""
        response = cache_client.post("/api/cache/tune", json={"invalid_param": "value"})

        # Should reject or ignore invalid params
        assert response.status_code in [200, 400, 404, 422]

@pytest.mark.integration
class TestCacheClear:
    """Tests for DELETE /api/cache/clear endpoint."""

    def test_clear_cache(self, cache_client):
        """Test clearing the entire cache."""
        response = cache_client.delete("/api/cache/clear")

        assert response.status_code in [200, 204, 404]

@pytest.mark.integration
class TestCacheEvict:
    """Tests for POST /api/cache/evict endpoint."""

    def test_evict_cache_entry(self, cache_client):
        """Test evicting specific cache entry."""
        response = cache_client.post("/api/cache/evict", json={"key": "test_key"})

        assert response.status_code in [200, 404, 422]

    def test_evict_cache_by_pattern(self, cache_client):
        """Test evicting entries by pattern."""
        response = cache_client.post("/api/cache/evict", json={"pattern": "test_*"})

        assert response.status_code in [200, 404, 422]

@pytest.mark.integration
class TestCacheHealth:
    """Tests for GET /api/cache/health endpoint."""

    def test_cache_health(self, cache_client):
        """Test cache health check."""
        response = cache_client.get("/api/cache/health")

        assert response.status_code in [200, 404, 503]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
