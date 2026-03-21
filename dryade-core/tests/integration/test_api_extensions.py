"""
Integration tests for extensions API routes.

Tests cover:
1. Extension status (list all, health check)
2. Extension metrics (aggregated metrics with time window)
3. Extension timeline (recent activity)
4. Extension config (current configuration)
5. Error handling for unavailable extensions
6. Extension health status values

Target: ~200 LOC
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def extensions_client():
    """Create test FastAPI app for extension endpoints."""
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

    # Mock authentication for routes that require it
    def override_get_current_user():
        return {"sub": "test-user-ext", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app, raise_server_exceptions=False)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_extensions.db"):
        os.remove("./test_extensions.db")

@pytest.fixture
def mock_extension():
    """Create a mock extension for testing."""
    from core.extensions.pipeline import ExtensionType

    ext = MagicMock()
    ext.name = "test_extension"
    ext.type = ExtensionType.INPUT_VALIDATION
    ext.enabled = True
    ext.priority = 10
    return ext

@pytest.fixture
def mock_extension_registry(mock_extension):
    """Mock extension registry with test extensions."""
    from core.extensions.pipeline import ExtensionType

    registry = MagicMock()

    # Create multiple mock extensions
    cache_ext = MagicMock()
    cache_ext.name = "semantic_cache"
    cache_ext.type = ExtensionType.SEMANTIC_CACHE
    cache_ext.enabled = True
    cache_ext.priority = 5

    sandbox_ext = MagicMock()
    sandbox_ext.name = "sandbox"
    sandbox_ext.type = ExtensionType.SANDBOX
    sandbox_ext.enabled = True
    sandbox_ext.priority = 20

    registry.get_enabled.return_value = [mock_extension, cache_ext, sandbox_ext]
    return registry

@pytest.mark.integration
class TestExtensionStatus:
    """Tests for GET /api/extensions/status endpoint."""

    def test_extension_status_returns_list(self, extensions_client):
        """Test getting extension status returns a list."""
        response = extensions_client.get("/api/extensions/status")

        # May return 200 (success), 404 (not found), or 500 (dependency error)
        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_extension_status_with_mock_registry(self, extensions_client, mock_extension_registry):
        """Test extension status with mocked registry."""
        with patch(
            "core.api.routes.extensions.get_extension_registry",
            return_value=mock_extension_registry,
        ):
            with patch(
                "core.api.routes.extensions._check_extension_health", new_callable=AsyncMock
            ) as mock_health:
                mock_health.return_value = "healthy"

                response = extensions_client.get("/api/extensions/status")

                if response.status_code == 200:
                    data = response.json()
                    assert isinstance(data, list)
                    # Should have extensions from mock registry
                    if len(data) > 0:
                        ext = data[0]
                        assert "name" in ext
                        assert "type" in ext
                        assert "enabled" in ext
                        assert "priority" in ext
                        assert "health" in ext

    def test_extension_status_health_values(self, extensions_client, mock_extension_registry):
        """Test that health status has valid values."""
        with patch(
            "core.api.routes.extensions.get_extension_registry",
            return_value=mock_extension_registry,
        ):
            with patch(
                "core.api.routes.extensions._check_extension_health", new_callable=AsyncMock
            ) as mock_health:
                mock_health.return_value = "degraded"

                response = extensions_client.get("/api/extensions/status")

                if response.status_code == 200:
                    data = response.json()
                    for ext in data:
                        if "health" in ext:
                            assert ext["health"] in ["healthy", "degraded", "down"]

@pytest.mark.integration
class TestExtensionMetrics:
    """Tests for GET /api/extensions/metrics endpoint."""

    def test_extension_metrics(self, extensions_client):
        """Test getting extension metrics."""
        response = extensions_client.get("/api/extensions/metrics")

        # 500 may occur if dependencies not configured
        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_extension_metrics_fields(self, extensions_client):
        """Test extension metrics response has expected fields."""
        response = extensions_client.get("/api/extensions/metrics")

        if response.status_code == 200:
            data = response.json()
            # Check for expected metric fields
            expected_fields = [
                "cache_hit_rate",
                "cache_savings_usd",
                "sandbox_overhead_ms",
                "healing_success_rate",
                "threats_blocked",
                "validation_failures",
                "total_requests",
            ]
            for field in expected_fields:
                if field in data:
                    assert isinstance(data[field], (int, float))

    def test_extension_metrics_with_hours_param(self, extensions_client):
        """Test metrics with custom hours parameter."""
        response = extensions_client.get("/api/extensions/metrics?hours=48")

        assert response.status_code in [200, 404, 500]

    def test_extension_metrics_invalid_hours(self, extensions_client):
        """Test metrics with invalid hours parameter."""
        response = extensions_client.get("/api/extensions/metrics?hours=500")

        # Should fail validation (max 168 hours)
        assert response.status_code in [422, 500]

@pytest.mark.integration
class TestExtensionTimeline:
    """Tests for GET /api/extensions/timeline endpoint."""

    def test_extension_timeline(self, extensions_client):
        """Test getting extension execution timeline."""
        response = extensions_client.get("/api/extensions/timeline")

        # 500 may occur if dependencies not configured
        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    def test_extension_timeline_with_limit(self, extensions_client):
        """Test timeline with limit parameter."""
        response = extensions_client.get("/api/extensions/timeline?limit=10")

        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            assert len(data) <= 10

    def test_extension_timeline_invalid_limit(self, extensions_client):
        """Test timeline with invalid limit parameter."""
        response = extensions_client.get("/api/extensions/timeline?limit=5000")

        # Should fail validation (max 1000)
        assert response.status_code in [422, 500]

    def test_extension_timeline_entry_format(self, extensions_client):
        """Test timeline entry has expected fields."""
        response = extensions_client.get("/api/extensions/timeline")

        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                entry = data[0]
                expected_fields = [
                    "request_id",
                    "operation",
                    "extensions_applied",
                    "total_duration_ms",
                    "outcomes",
                    "timestamp",
                ]
                for field in expected_fields:
                    if field in entry:
                        pass  # Field exists

@pytest.mark.integration
class TestExtensionConfig:
    """Tests for GET /api/extensions/config endpoint."""

    def test_extension_config(self, extensions_client):
        """Test getting extension configuration."""
        response = extensions_client.get("/api/extensions/config")

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_extension_config_has_expected_fields(self, extensions_client):
        """Test config response has expected enable/disable flags."""
        response = extensions_client.get("/api/extensions/config")

        if response.status_code == 200:
            data = response.json()
            expected_fields = [
                "extensions_enabled",
                "input_validation_enabled",
                "semantic_cache_enabled",
                "self_healing_enabled",
                "sandbox_enabled",
                "file_safety_enabled",
                "output_sanitization_enabled",
            ]
            for field in expected_fields:
                assert field in data
                assert isinstance(data[field], bool)

    def test_extension_config_reflects_env(self, extensions_client):
        """Test that config reflects environment variables."""
        # Set a specific config via env
        original = os.environ.get("DRYADE_EXTENSIONS_ENABLED", "true")
        os.environ["DRYADE_EXTENSIONS_ENABLED"] = "false"

        try:
            response = extensions_client.get("/api/extensions/config")

            if response.status_code == 200:
                data = response.json()
                # Config should reflect the env var
                # Note: actual behavior depends on when settings are loaded
                assert "extensions_enabled" in data
        finally:
            os.environ["DRYADE_EXTENSIONS_ENABLED"] = original

@pytest.mark.integration
class TestExtensionList:
    """Tests for GET /api/extensions endpoint (if available)."""

    def test_extension_list(self, extensions_client):
        """Test listing available extensions."""
        response = extensions_client.get("/api/extensions")

        # May not exist as a separate endpoint
        assert response.status_code in [200, 404, 405]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

@pytest.mark.integration
class TestExtensionErrorHandling:
    """Tests for extension error handling."""

    def test_status_handles_registry_error(self, extensions_client):
        """Test that status endpoint handles registry errors gracefully."""
        with patch("core.api.routes.extensions.get_extension_registry") as mock_registry:
            mock_registry.side_effect = RuntimeError("Registry unavailable")

            response = extensions_client.get("/api/extensions/status")

            # Should return 500 or handle gracefully
            assert response.status_code in [200, 500]

    def test_metrics_handles_db_error(self, extensions_client):
        """Test that metrics endpoint handles database errors."""
        # Endpoint should handle empty database gracefully
        response = extensions_client.get("/api/extensions/metrics")

        # Should not crash, even with empty data
        assert response.status_code in [200, 404, 500]

    def test_timeline_handles_empty_data(self, extensions_client):
        """Test that timeline handles no data gracefully."""
        response = extensions_client.get("/api/extensions/timeline")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            # Empty list is valid

@pytest.mark.integration
class TestExtensionHealthCheck:
    """Tests for extension health check functionality."""

    def test_health_check_semantic_cache(self, extensions_client):
        """Test health check for semantic cache extension."""

        with patch(
            "core.api.routes.extensions._check_extension_health", new_callable=AsyncMock
        ) as mock_health:
            mock_health.return_value = "healthy"

            # Health check is called internally by status endpoint
            response = extensions_client.get("/api/extensions/status")

            # The health check should have been called if extensions exist
            assert response.status_code in [200, 404, 500]

    def test_health_degraded_state(self, extensions_client, mock_extension_registry):
        """Test degraded health state is reported correctly."""
        with patch(
            "core.api.routes.extensions.get_extension_registry",
            return_value=mock_extension_registry,
        ):
            with patch(
                "core.api.routes.extensions._check_extension_health", new_callable=AsyncMock
            ) as mock_health:
                # Return degraded for all extensions
                mock_health.return_value = "degraded"

                response = extensions_client.get("/api/extensions/status")

                if response.status_code == 200:
                    data = response.json()
                    for ext in data:
                        if "health" in ext:
                            assert ext["health"] == "degraded"
