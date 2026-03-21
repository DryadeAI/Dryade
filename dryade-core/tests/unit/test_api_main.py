"""Tests for core/api/main.py -- App bootstrap and exception handlers.

Tests the FastAPI app creation, middleware stack, route mounting,
and centralized exception handlers. Uses TestClient for handler testing.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===========================================================================
# App creation and configuration
# ===========================================================================
class TestAppCreation:
    """Tests for the FastAPI app object created in main.py."""

    def test_app_is_fastapi_instance(self):
        """App should be a FastAPI instance."""
        from core.api.main import app

        assert isinstance(app, FastAPI)

    def test_app_title(self):
        """App should have correct title."""
        from core.api.main import app

        assert app.title == "Dryade API"

    def test_app_version(self):
        """App should have correct version."""
        from core.api.main import app

        assert app.version == "1.0.0"

    def test_docs_url(self):
        """App should have /docs URL configured."""
        from core.api.main import app

        assert app.docs_url == "/docs"

    def test_openapi_url(self):
        """App should have /openapi.json URL configured."""
        from core.api.main import app

        assert app.openapi_url == "/openapi.json"

# ===========================================================================
# Tags metadata
# ===========================================================================
class TestTagsMetadata:
    """Tests for OpenAPI tag descriptions."""

    def test_tags_metadata_exists(self):
        """Tags metadata should be a non-empty list."""
        from core.api.main import tags_metadata

        assert isinstance(tags_metadata, list)
        assert len(tags_metadata) > 0

    def test_core_tags_present(self):
        """Core tags (auth, chat, agents) should always be present."""
        from core.api.main import tags_metadata

        tag_names = {t["name"] for t in tags_metadata}
        for required_tag in ["auth", "chat", "agents", "health", "websocket"]:
            assert required_tag in tag_names, f"Missing required tag: {required_tag}"

    def test_tags_have_descriptions(self):
        """Each tag should have a description."""
        from core.api.main import tags_metadata

        for tag in tags_metadata:
            assert "name" in tag
            assert "description" in tag
            assert len(tag["description"]) > 0

# ===========================================================================
# Exception handlers
# ===========================================================================
class TestExceptionHandlers:
    """Tests for centralized exception handlers defined in main.py.

    Each handler imports record_error locally from core.api.middleware.error_metrics,
    so we patch at that source module level.
    """

    _RECORD_ERROR_PATH = "core.api.middleware.error_metrics.record_error"

    def test_value_error_handler(self):
        """ValueError should return 400 Bad Request."""
        from core.api.main import value_error_handler

        test_app = FastAPI()

        @test_app.get("/fail")
        async def fail():
            raise ValueError("Bad input value")

        test_app.add_exception_handler(ValueError, value_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/fail")

        assert resp.status_code == 400
        body = resp.json()
        assert body["type"] == "validation_error"
        assert body["code"] == "VALIDATION_001"

    def test_file_not_found_handler(self):
        """FileNotFoundError should return 404."""
        from core.api.main import not_found_handler

        test_app = FastAPI()

        @test_app.get("/missing")
        async def missing():
            raise FileNotFoundError("File not found")

        test_app.add_exception_handler(FileNotFoundError, not_found_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/missing")

        assert resp.status_code == 404
        body = resp.json()
        assert body["type"] == "not_found"

    def test_key_error_handler(self):
        """KeyError should return 400."""
        from core.api.main import key_error_handler

        test_app = FastAPI()

        @test_app.get("/key-fail")
        async def key_fail():
            raise KeyError("missing_key")

        test_app.add_exception_handler(KeyError, key_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/key-fail")

        assert resp.status_code == 400
        body = resp.json()
        assert body["type"] == "missing_key"

    def test_timeout_error_handler(self):
        """TimeoutError should return 408."""
        from core.api.main import timeout_error_handler

        test_app = FastAPI()

        @test_app.get("/timeout")
        async def timeout():
            raise TimeoutError("Request timed out")

        test_app.add_exception_handler(TimeoutError, timeout_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/timeout")

        assert resp.status_code == 408
        body = resp.json()
        assert body["type"] == "timeout"

    def test_runtime_error_handler(self):
        """RuntimeError should return 500."""
        from core.api.main import runtime_error_handler

        test_app = FastAPI()

        @test_app.get("/runtime-fail")
        async def runtime_fail():
            raise RuntimeError("Something broke")

        test_app.add_exception_handler(RuntimeError, runtime_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/runtime-fail")

        assert resp.status_code == 500
        body = resp.json()
        assert body["type"] == "runtime_error"

    def test_general_exception_handler(self):
        """Unhandled exceptions should return 500."""
        from core.api.main import general_exception_handler

        test_app = FastAPI()

        @test_app.get("/unexpected")
        async def unexpected():
            raise Exception("Unexpected error")

        test_app.add_exception_handler(Exception, general_exception_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/unexpected")

        assert resp.status_code == 500
        body = resp.json()
        assert body["type"] == "internal_error"
        assert body["code"] == "SERVER_001"

# ===========================================================================
# Route registration
# ===========================================================================
class TestRouteRegistration:
    """Tests that routes are properly registered on the app."""

    def test_routes_registered(self):
        """Core routes should be registered on the app."""
        from core.api.main import app

        route_paths = {r.path for r in app.routes if hasattr(r, "path")}

        # Check key routes are mounted
        assert "/api/chat/{path:path}" in route_paths or any("/api/chat" in p for p in route_paths)
        assert any("/api/agents" in p for p in route_paths)
        assert any("/health" in p for p in route_paths)

    @pytest.mark.asyncio
    async def test_root_redirect(self):
        """Root / should redirect to docs."""
        from core.api.main import root

        result = await root()
        assert result.status_code == 307  # RedirectResponse
        assert result.headers["location"] == "/docs"

    @pytest.mark.asyncio
    async def test_api_info(self):
        """GET /api should return API info."""
        from core.api.main import api_info

        result = await api_info()
        assert result["name"] == "Dryade API"
        assert result["version"] == "1.0.0"
        assert result["docs"] == "/docs"

# ===========================================================================
# Enterprise routes availability
# ===========================================================================
class TestEnterpriseRoutes:
    """Tests for enterprise route availability flag."""

    def test_enterprise_flag_exists(self):
        """ENTERPRISE_ROUTES_AVAILABLE flag should be defined."""
        from core.api.main import ENTERPRISE_ROUTES_AVAILABLE

        assert isinstance(ENTERPRISE_ROUTES_AVAILABLE, bool)
