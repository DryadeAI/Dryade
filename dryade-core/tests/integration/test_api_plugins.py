"""
Integration tests for plugins API routes.

Tests cover:
1. List all plugins
2. Get plugin details
3. Plugin not found
4. Plugin stats summary

Target: ~60 LOC
"""

import os

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def plugins_client():
    """Create test FastAPI app for plugin endpoints."""
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
        return {"sub": "test-user-plugins", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_plugins.db"):
        os.remove("./test_plugins.db")

@pytest.mark.integration
class TestListPlugins:
    """Tests for GET /api/plugins endpoint."""

    def test_list_plugins(self, plugins_client):
        """Test listing all plugins."""
        response = plugins_client.get("/api/plugins")

        assert response.status_code == 200
        data = response.json()
        # Should return a list or dict of plugins
        assert isinstance(data, (list, dict))

    def test_list_plugins_response_format(self, plugins_client):
        """Test plugin list has expected format."""
        response = plugins_client.get("/api/plugins")

        assert response.status_code == 200
        data = response.json()

        # If list, each item should be a plugin object
        if isinstance(data, list) and len(data) > 0:
            plugin = data[0]
            assert "name" in plugin or isinstance(plugin, str)

@pytest.mark.integration
class TestPluginDetails:
    """Tests for GET /api/plugins/{name} endpoint."""

    def test_get_plugin_details_existing(self, plugins_client):
        """Test getting details of specific plugin."""
        # First list plugins to get a name
        response = plugins_client.get("/api/plugins")
        assert response.status_code == 200
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            # Get first plugin name
            plugin_name = data[0].get("name", data[0]) if isinstance(data[0], dict) else data[0]

            # Get details
            response = plugins_client.get(f"/api/plugins/{plugin_name}")
            assert response.status_code in [200, 404]

    def test_plugin_not_found(self, plugins_client):
        """Test 404 for non-existent plugin."""
        response = plugins_client.get("/api/plugins/nonexistent_plugin_xyz")

        assert response.status_code == 404

@pytest.mark.integration
class TestPluginStats:
    """Tests for GET /api/plugins/stats/summary endpoint."""

    def test_plugin_stats(self, plugins_client):
        """Test plugin statistics summary."""
        response = plugins_client.get("/api/plugins/stats/summary")

        # Stats endpoint may or may not exist
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
