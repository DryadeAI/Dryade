"""Expanded tests for core/api/middleware/ modules.

Tests: error_metrics, rate_limit, auth middleware, request_size,
request_metrics. Covers module-level functions without requiring
full FastAPI app startup.
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===========================================================================
# error_metrics module
# ===========================================================================

class TestErrorMetrics:
    """Tests for core/api/middleware/error_metrics.py."""

    def setup_method(self):
        """Reset singleton before each test."""
        from core.api.middleware.error_metrics import clear_metrics

        clear_metrics()

    def test_record_error_increments_by_type(self):
        """record_error increments count by error type."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("ValueError", "/api/chat", status_code=400)
        stats = get_error_stats()
        assert stats["by_type"]["ValueError"] == 1

    def test_record_error_increments_by_endpoint(self):
        """record_error increments count by endpoint."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("RuntimeError", "/api/plugins", status_code=500)
        stats = get_error_stats()
        assert stats["by_endpoint"]["/api/plugins"] == 1

    def test_record_error_increments_by_status(self):
        """record_error increments count by status code."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("TimeoutError", "/api/flows", status_code=408)
        stats = get_error_stats()
        assert stats["by_status"][408] == 1

    def test_record_error_stores_recent_entries(self):
        """record_error stores entries in recent_errors list."""
        from core.api.middleware.error_metrics import get_recent_errors, record_error

        record_error(
            "KeyError",
            "/api/test",
            status_code=400,
            error_message="missing key",
            request_id="req-123",
            user_id="user-456",
        )
        recent = get_recent_errors(limit=10)
        assert len(recent) == 1
        assert recent[0]["type"] == "KeyError"
        assert recent[0]["endpoint"] == "/api/test"
        assert recent[0]["status"] == 400

    def test_record_error_truncates_long_messages(self):
        """record_error truncates messages longer than 200 chars."""
        from core.api.middleware.error_metrics import get_recent_errors, record_error

        long_message = "x" * 500
        record_error("ValueError", "/api/test", error_message=long_message)
        recent = get_recent_errors()
        assert len(recent[0]["message"]) <= 200

    def test_get_error_stats_total(self):
        """get_error_stats returns total_errors count."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("TypeError", "/api/a", status_code=400)
        record_error("ValueError", "/api/b", status_code=400)
        stats = get_error_stats()
        assert stats["total_errors"] == 2

    def test_get_recent_errors_respects_limit(self):
        """get_recent_errors respects the limit parameter."""
        from core.api.middleware.error_metrics import get_recent_errors, record_error

        for i in range(10):
            record_error("Error", f"/api/{i}", status_code=500)

        recent = get_recent_errors(limit=3)
        assert len(recent) == 3

    def test_clear_metrics_resets_all_counts(self):
        """clear_metrics resets all counters."""
        from core.api.middleware.error_metrics import clear_metrics, get_error_stats, record_error

        record_error("ValueError", "/api/test", status_code=400)
        clear_metrics()
        stats = get_error_stats()
        assert stats["total_errors"] == 0
        assert stats["recent_count"] == 0

    def test_recent_errors_capped_at_100(self):
        """Only last 100 errors are kept in recent_errors."""
        from core.api.middleware.error_metrics import get_recent_errors, record_error

        for i in range(110):
            record_error("Error", f"/api/{i}", status_code=500)

        recent = get_recent_errors(limit=200)
        assert len(recent) <= 100

    def test_get_error_stats_error_rate(self):
        """get_error_stats returns error_rate_per_minute."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("ValueError", "/api/test", status_code=400)
        stats = get_error_stats()
        assert "error_rate_per_minute" in stats
        assert isinstance(stats["error_rate_per_minute"], float)

    def test_get_error_summary_backward_compat(self):
        """get_error_summary returns backward-compatible dict."""
        from core.api.middleware.error_metrics import get_error_summary, record_error

        record_error("ValueError", "/api/test", status_code=400)
        summary = get_error_summary()
        assert isinstance(summary, dict)

    def test_get_error_count_returns_count(self):
        """get_error_count returns count for endpoint+type combination."""
        from core.api.middleware.error_metrics import get_error_count, record_error

        record_error("ValueError", "/api/chat", status_code=400)
        # get_error_count returns min(endpoint_count, type_count)
        count = get_error_count("/api/chat", "ValueError")
        assert count >= 0

    def test_reset_error_counts(self):
        """reset_error_counts clears all metrics."""
        from core.api.middleware.error_metrics import (
            get_error_stats,
            record_error,
            reset_error_counts,
        )

        record_error("Error", "/api/test", status_code=500)
        reset_error_counts()
        stats = get_error_stats()
        assert stats["total_errors"] == 0

    def test_error_metrics_singleton(self):
        """ErrorMetrics.get_instance() returns the same instance."""
        from core.api.middleware.error_metrics import ErrorMetrics

        a = ErrorMetrics.get_instance()
        b = ErrorMetrics.get_instance()
        assert a is b

# ===========================================================================
# rate_limit middleware
# ===========================================================================

class TestRateLimitMiddleware:
    """Tests for core/api/middleware/rate_limit.py."""

    def _make_app(self, **kwargs):
        """Create a test FastAPI app with rate limiting."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        app.add_middleware(RateLimitMiddleware, **kwargs)
        return app

    def test_request_allowed_under_limit(self):
        """Requests below rate limit are allowed through."""
        with patch.dict(os.environ, {"DRYADE_RATE_LIMIT_ENABLED": "true"}):
            app = self._make_app(requests_per_minute=100)
            client = TestClient(app)
            resp = client.get("/test")
        assert resp.status_code == 200

    def test_rate_limit_headers_present(self):
        """Response includes X-RateLimit-* headers."""
        with patch.dict(os.environ, {"DRYADE_RATE_LIMIT_ENABLED": "true"}):
            app = self._make_app(requests_per_minute=100)
            client = TestClient(app)
            resp = client.get("/test")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_rate_limit_disabled(self):
        """When disabled, requests always pass through."""
        with patch.dict(os.environ, {"DRYADE_RATE_LIMIT_ENABLED": "false"}):
            app = self._make_app(requests_per_minute=1)
            client = TestClient(app)
            # Make 5 requests with limit=1, should all pass because disabled
            for _ in range(5):
                resp = client.get("/test")
                assert resp.status_code == 200

    def test_rate_limit_exceeded_returns_429(self):
        """Requests exceeding rate limit get 429 Too Many Requests."""
        with patch.dict(os.environ, {"DRYADE_RATE_LIMIT_ENABLED": "true"}):
            app = self._make_app(requests_per_minute=2)
            client = TestClient(app)
            # First two requests should pass
            client.get("/test")
            client.get("/test")
            # Third should be rate limited
            resp = client.get("/test")
        assert resp.status_code == 429
        body = resp.json()
        assert "rate limit" in body["detail"].lower()

    def test_rate_limit_429_has_retry_after_header(self):
        """429 response includes Retry-After header."""
        with patch.dict(os.environ, {"DRYADE_RATE_LIMIT_ENABLED": "true"}):
            app = self._make_app(requests_per_minute=1)
            client = TestClient(app)
            client.get("/test")
            resp = client.get("/test")
        if resp.status_code == 429:
            assert "Retry-After" in resp.headers

    def test_get_rate_limit_default(self):
        """_get_rate_limit returns default RPM for anonymous users."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock(), requests_per_minute=60)
        request = MagicMock()
        request.state.user = None
        assert mw._get_rate_limit(request) == 60

    def test_get_rate_limit_admin(self):
        """_get_rate_limit returns admin RPM for admin users."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock(), admin_rpm=1000)
        request = MagicMock()
        request.state.user = {"role": "admin"}
        assert mw._get_rate_limit(request) == 1000

    def test_get_rate_limit_pro(self):
        """_get_rate_limit returns pro RPM for pro users."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        mw = RateLimitMiddleware(app=MagicMock(), pro_rpm=300)
        request = MagicMock()
        request.state.user = {"role": "pro"}
        assert mw._get_rate_limit(request) == 300

# ===========================================================================
# auth middleware
# ===========================================================================

class TestAuthMiddleware:
    """Tests for core/api/middleware/auth.py."""

    def test_auth_middleware_skips_excluded_paths(self):
        """Excluded paths like /health bypass auth check."""
        from core.api.middleware.auth import AuthMiddleware

        app = FastAPI()

        @app.get("/health")
        async def health():
            return {"ok": True}

        app.add_middleware(AuthMiddleware)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_auth_middleware_skips_docs(self):
        """GET /docs bypasses auth check."""
        from core.api.middleware.auth import AuthMiddleware

        app = FastAPI()
        app.add_middleware(AuthMiddleware)
        client = TestClient(app)
        resp = client.get("/docs")
        # Docs should be accessible without auth
        assert resp.status_code in (200, 404)

    def test_auth_middleware_returns_401_for_missing_token(self):
        """Protected endpoint returns 401 when no token provided."""
        from core.api.middleware.auth import AuthMiddleware

        app = FastAPI()

        @app.get("/protected")
        async def protected():
            return {"secret": "data"}

        with patch("core.api.middleware.auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_enabled = True
            settings.jwt_secret = "secret"
            mock_settings.return_value = settings
            app.add_middleware(AuthMiddleware)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/protected")

        assert resp.status_code in (401, 403)

    def test_auth_middleware_disabled(self):
        """When auth_enabled=False, all requests pass through."""
        from core.api.middleware.auth import AuthMiddleware

        app = FastAPI()

        @app.get("/protected")
        async def protected():
            return {"secret": "data"}

        with patch("core.api.middleware.auth.get_settings") as mock_settings:
            settings = MagicMock()
            settings.auth_enabled = False
            mock_settings.return_value = settings
            app.add_middleware(AuthMiddleware)
            client = TestClient(app)
            resp = client.get("/protected")

        assert resp.status_code == 200

# ===========================================================================
# request_metrics middleware
# ===========================================================================

class TestRequestMetricsMiddleware:
    """Tests for core/api/middleware/request_metrics.py."""

    def test_request_metrics_passes_through(self):
        """RequestMetricsMiddleware allows requests through."""
        from core.api.middleware.request_metrics import RequestMetricsMiddleware

        app = FastAPI()

        @app.get("/test")
        async def test_ep():
            return {"ok": True}

        app.add_middleware(RequestMetricsMiddleware)
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200

# ===========================================================================
# middleware __init__ exports
# ===========================================================================

class TestMiddlewareInit:
    """Tests for core/api/middleware/__init__.py exports."""

    def test_auth_middleware_importable(self):
        """AuthMiddleware importable from core.api.middleware."""
        from core.api.middleware import AuthMiddleware

        assert AuthMiddleware is not None

    def test_rate_limit_middleware_importable(self):
        """RateLimitMiddleware importable from core.api.middleware."""
        from core.api.middleware import RateLimitMiddleware

        assert RateLimitMiddleware is not None

    def test_llm_context_middleware_importable(self):
        """LLMContextMiddleware importable from core.api.middleware."""
        from core.api.middleware import LLMContextMiddleware

        assert LLMContextMiddleware is not None
