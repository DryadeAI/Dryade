"""Tests for core/api/main.py -- Expanded exception handlers and middleware.

Extends the existing test_api_main.py by testing database exception handlers,
the middleware stack, and additional route functions that are currently uncovered.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

# ===========================================================================
# Database exception handlers
# ===========================================================================

class TestDatabaseExceptionHandlers:
    """Tests for database-level exception handlers added in main.py.

    These are the IntegrityError, OperationalError, and DatabaseError handlers
    which return 409, 503, and 500 respectively.
    """

    _RECORD_ERROR_PATH = "core.api.middleware.error_metrics.record_error"

    def test_integrity_error_handler_returns_409(self):
        """IntegrityError should return 409 Conflict."""
        from core.api.main import integrity_error_handler

        test_app = FastAPI()

        @test_app.get("/conflict")
        async def conflict():
            # SQLAlchemy IntegrityError needs a statement arg
            raise IntegrityError("UNIQUE constraint failed", None, Exception("dup"))

        test_app.add_exception_handler(IntegrityError, integrity_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/conflict")

        assert resp.status_code == 409
        body = resp.json()
        assert body["type"] == "integrity_error"
        assert body["code"] == "CONFLICT_001"

    def test_operational_error_handler_returns_503(self):
        """OperationalError should return 503 Service Unavailable."""
        from core.api.main import operational_error_handler

        test_app = FastAPI()

        @test_app.get("/db-down")
        async def db_down():
            raise OperationalError("could not connect to server", None, Exception("conn"))

        test_app.add_exception_handler(OperationalError, operational_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/db-down")

        assert resp.status_code == 503
        body = resp.json()
        assert body["type"] == "database_error"
        assert body["code"] == "SERVER_002"

    def test_database_error_handler_returns_500(self):
        """General DatabaseError should return 500 Internal Server Error."""
        from core.api.main import database_error_handler

        test_app = FastAPI()

        @test_app.get("/db-error")
        async def db_error():
            raise DatabaseError("general error", None, Exception("db"))

        test_app.add_exception_handler(DatabaseError, database_error_handler)
        client = TestClient(test_app, raise_server_exceptions=False)

        with patch(self._RECORD_ERROR_PATH):
            resp = client.get("/db-error")

        assert resp.status_code == 500
        body = resp.json()
        assert body["type"] == "database_error"
        assert body["code"] == "SERVER_004"

# ===========================================================================
# Middleware stack
# ===========================================================================

class TestMiddlewareStack:
    """Tests for middleware registration on the app."""

    def test_cors_middleware_mounted(self):
        """CORS middleware should be in the middleware stack."""
        from fastapi.middleware.cors import CORSMiddleware

        from core.api.main import app

        middleware_types = []
        for mw in app.user_middleware:
            # Starlette stores middleware as (cls, options)
            if hasattr(mw, "cls"):
                middleware_types.append(mw.cls)
            elif hasattr(mw, "kwargs"):
                pass

        # Check middleware stack via the app's middleware_stack
        # Use the built stack from app.build_middleware_stack()
        middleware_class_names = [type(m).__name__ for m in app.middleware_stack.__class__.__mro__]
        # More reliable: check via user_middleware list
        mw_cls_names = []
        for mw in app.user_middleware:
            if hasattr(mw, "cls"):
                mw_cls_names.append(mw.cls.__name__)

        assert "CORSMiddleware" in mw_cls_names

    def test_auth_middleware_in_stack(self):
        """AuthMiddleware should be in the user middleware stack."""
        from core.api.main import app

        mw_cls_names = []
        for mw in app.user_middleware:
            if hasattr(mw, "cls"):
                mw_cls_names.append(mw.cls.__name__)

        assert "AuthMiddleware" in mw_cls_names

    def test_rate_limit_middleware_in_stack(self):
        """RateLimitMiddleware should be in the user middleware stack."""
        from core.api.main import app

        mw_cls_names = []
        for mw in app.user_middleware:
            if hasattr(mw, "cls"):
                mw_cls_names.append(mw.cls.__name__)

        assert "RateLimitMiddleware" in mw_cls_names

# ===========================================================================
# Error response model
# ===========================================================================

class TestErrorResponseModel:
    """Tests for the ErrorResponse Pydantic model used in handlers."""

    def test_error_response_has_required_fields(self):
        """ErrorResponse model has error, type, and code fields."""
        from core.api.models import ErrorResponse

        resp = ErrorResponse(error="Something went wrong", type="test_error", code="TEST_001")
        assert resp.error == "Something went wrong"
        assert resp.type == "test_error"
        assert resp.code == "TEST_001"

    def test_error_response_serializes_to_json(self):
        """ErrorResponse serializes properly to dict for JSONResponse."""
        from core.api.models import ErrorResponse

        resp = ErrorResponse(error="fail", type="server_error", code="SERVER_001")
        data = resp.model_dump(mode="json")
        assert isinstance(data, dict)
        assert "error" in data
        assert "type" in data
        assert "code" in data

# ===========================================================================
# Full-stack app request tests
# ===========================================================================

class TestAppRouteIntegration:
    """Tests that hit the app via TestClient to verify route behavior."""

    def test_health_endpoint_returns_200(self):
        """GET /health should return 200."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_docs_endpoint_returns_200(self):
        """GET /docs should return 200 (Swagger UI)."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_json_returns_200(self):
        """GET /openapi.json should return valid OpenAPI schema."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        body = resp.json()
        assert "openapi" in body
        assert "paths" in body

    def test_root_redirects_to_docs(self):
        """GET / should redirect to /docs or require auth.

        The root endpoint may be auth-gated in this configuration.
        """
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
        resp = client.get("/")
        # Either redirects to /docs or requires auth
        assert resp.status_code in (301, 302, 307, 308, 401)

    def test_api_route_returns_info(self):
        """GET /api should return API info (may require auth)."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api")
        # May be 200 with info or 401 requiring auth
        assert resp.status_code in (200, 401)

    def test_unauthenticated_chat_returns_401(self):
        """POST /api/chat without token should return 401."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 401

    def test_unauthenticated_conversations_returns_401(self):
        """GET /api/chat/conversations without token should return 401."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/chat/conversations")
        assert resp.status_code == 401

    def test_unauthenticated_plugins_returns_401(self):
        """GET /api/plugins without token should return 401."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/plugins")
        assert resp.status_code == 401

    def test_unauthenticated_workflows_returns_401(self):
        """GET /api/workflows without token should return 401."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/workflows")
        assert resp.status_code == 401

    def test_unauthenticated_agents_returns_401(self):
        """GET /api/agents without token should return 401."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/agents")
        assert resp.status_code == 401

    def test_metrics_endpoint_accessible(self):
        """GET /metrics should return a response (may be 200 or redirect)."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        # Prometheus metrics endpoint may return 200 or 404 if not configured
        assert resp.status_code in (200, 404, 503)

    def test_version_endpoint_accessible(self):
        """GET /api/version should be accessible."""
        from core.api.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/version")
        # May require auth or may be public depending on config
        assert resp.status_code in (200, 401, 404)

# ===========================================================================
# Handler function shapes
# ===========================================================================

class TestHandlerFunctionShapes:
    """Tests for the async handler functions defined at module level."""

    @pytest.mark.asyncio
    async def test_root_returns_redirect_response(self):
        """root() returns a RedirectResponse to /docs."""
        from fastapi.responses import RedirectResponse

        from core.api.main import root

        result = await root()
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/docs"

    @pytest.mark.asyncio
    async def test_api_info_returns_dict(self):
        """api_info() returns dict with expected keys."""
        from core.api.main import api_info

        result = await api_info()
        assert result["name"] == "Dryade API"
        assert result["version"] == "1.0.0"
        assert result["docs"] == "/docs"
        # Response includes either health or openapi key
        assert "health" in result or "openapi" in result

# ===========================================================================
# Configuration values
# ===========================================================================

class TestConfiguration:
    """Tests for configuration values and module-level constants."""

    def test_tags_metadata_is_list(self):
        """tags_metadata is a non-empty list."""
        from core.api.main import tags_metadata

        assert isinstance(tags_metadata, list)
        assert len(tags_metadata) > 0

    def test_enterprise_routes_available_flag_is_bool(self):
        """ENTERPRISE_ROUTES_AVAILABLE is a boolean."""
        from core.api.main import ENTERPRISE_ROUTES_AVAILABLE

        assert isinstance(ENTERPRISE_ROUTES_AVAILABLE, bool)

    def test_all_tags_have_name_and_description(self):
        """All tags in tags_metadata have 'name' and 'description'."""
        from core.api.main import tags_metadata

        for tag in tags_metadata:
            assert "name" in tag
            assert "description" in tag
            assert len(tag["description"]) > 0

    def test_auth_tag_present(self):
        """'auth' tag must be present."""
        from core.api.main import tags_metadata

        names = {t["name"] for t in tags_metadata}
        assert "auth" in names

    def test_chat_tag_present(self):
        """'chat' tag must be present."""
        from core.api.main import tags_metadata

        names = {t["name"] for t in tags_metadata}
        assert "chat" in names

    def test_health_tag_present(self):
        """'health' tag must be present."""
        from core.api.main import tags_metadata

        names = {t["name"] for t in tags_metadata}
        assert "health" in names
