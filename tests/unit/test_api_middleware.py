"""Tests for core/api/middleware/ -- All middleware modules.

Tests middleware initialization, request processing, and response modification.
Covers: RateLimitMiddleware, RequestSizeMiddleware, TracingMiddleware,
        ValidationMiddleware, ErrorMetrics, RequestMetricsMiddleware,
        AuthMiddleware, LLMContextMiddleware.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ===========================================================================
# RateLimitMiddleware
# ===========================================================================
class TestRateLimitMiddleware:
    """Tests for core/api/middleware/rate_limit.py."""

    def _make_app(self, rpm=5):
        from core.api.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=rpm)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        return TestClient(app, raise_server_exceptions=False)

    def test_normal_request_passes(self):
        """Requests within rate limit should pass."""
        client = self._make_app(rpm=10)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers

    def test_rate_limit_headers(self):
        """Response should include rate limit headers."""
        client = self._make_app(rpm=10)
        resp = client.get("/test")
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert int(resp.headers["X-RateLimit-Remaining"]) >= 0

    def test_rate_limit_exceeded(self):
        """Exceeding rate limit should return 429."""
        client = self._make_app(rpm=3)
        # Make 3 requests (should pass)
        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200
        # 4th request should be rate limited
        resp = client.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_disabled_via_env(self):
        """When disabled via env, requests should pass without limit."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        with patch.dict("os.environ", {"DRYADE_RATE_LIMIT_ENABLED": "false"}):
            middleware = RateLimitMiddleware(app, requests_per_minute=1)
        assert middleware.enabled is False

    def test_get_rate_limit_admin(self):
        """Admin users get higher rate limit."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        middleware = RateLimitMiddleware(app, requests_per_minute=60)
        mock_request = MagicMock()
        mock_request.state.user = {"role": "admin"}
        assert middleware._get_rate_limit(mock_request) == 1000

    def test_get_rate_limit_pro(self):
        """Pro users get medium rate limit."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        middleware = RateLimitMiddleware(app, requests_per_minute=60)
        mock_request = MagicMock()
        mock_request.state.user = {"role": "pro"}
        assert middleware._get_rate_limit(mock_request) == 300

    def test_get_rate_limit_default(self):
        """Users without role get default rate limit."""
        from core.api.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        middleware = RateLimitMiddleware(app, requests_per_minute=60)
        mock_request = MagicMock()
        mock_request.state.user = None
        assert middleware._get_rate_limit(mock_request) == 60

# ===========================================================================
# RequestSizeMiddleware
# ===========================================================================
class TestRequestSizeMiddleware:
    """Tests for core/api/middleware/request_size.py."""

    def _make_app(self, max_size_mb=1):
        from core.api.middleware.request_size import RequestSizeMiddleware

        app = FastAPI()
        app.add_middleware(RequestSizeMiddleware, max_size_mb=max_size_mb)

        @app.post("/upload")
        async def upload():
            return {"ok": True}

        return TestClient(app, raise_server_exceptions=False)

    def test_small_request_passes(self):
        """Small request body should pass."""
        client = self._make_app(max_size_mb=1)
        resp = client.post("/upload", content=b"small data", headers={"Content-Length": "10"})
        assert resp.status_code == 200

    def test_large_request_rejected(self):
        """Request exceeding max size should return 413."""
        client = self._make_app(max_size_mb=1)
        # Fake a 100MB content-length header
        resp = client.post(
            "/upload",
            content=b"x",
            headers={"Content-Length": str(100 * 1024 * 1024)},
        )
        assert resp.status_code == 413
        body = resp.json()
        assert "too large" in body["detail"]

    def test_no_content_length_passes(self):
        """Request without Content-Length should pass."""
        client = self._make_app(max_size_mb=1)
        resp = client.post("/upload", content=b"data")
        assert resp.status_code == 200

    def test_default_size_limit(self):
        """Default max size should be 10MB."""
        from core.api.middleware.request_size import RequestSizeMiddleware

        app = FastAPI()
        middleware = RequestSizeMiddleware(app)
        assert middleware.max_size_bytes == 10 * 1024 * 1024

# ===========================================================================
# TracingMiddleware
# ===========================================================================
class TestTracingMiddleware:
    """Tests for core/api/middleware/tracing.py."""

    def _make_app(self):
        from core.api.middleware.tracing import TracingMiddleware

        app = FastAPI()
        app.add_middleware(TracingMiddleware, service_name="test-service")

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        return TestClient(app, raise_server_exceptions=False)

    def test_adds_trace_headers(self):
        """Response should include tracing headers."""
        client = self._make_app()
        with patch("core.api.middleware.tracing.TracingMiddleware._log_span"):
            resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-Trace-ID" in resp.headers
        assert "X-Span-ID" in resp.headers
        assert "X-Request-Duration-Ms" in resp.headers

    def test_propagates_trace_id(self):
        """Should use provided X-Trace-ID."""
        client = self._make_app()
        with patch("core.api.middleware.tracing.TracingMiddleware._log_span"):
            resp = client.get("/test", headers={"X-Trace-ID": "my-trace-123"})
        assert resp.headers["X-Trace-ID"] == "my-trace-123"

    def test_disabled(self):
        """When disabled, should pass through without tracing."""
        from core.api.middleware.tracing import TracingMiddleware

        app = FastAPI()
        mw = TracingMiddleware(app)
        mw.enabled = False

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        assert resp.status_code == 200
        # No tracing headers when disabled
        assert "X-Trace-ID" not in resp.headers

# ===========================================================================
# ValidationMiddleware
# ===========================================================================
class TestValidationMiddleware:
    """Tests for core/api/middleware/validation.py."""

    def _make_app(self):
        from core.api.middleware.validation import ValidationMiddleware

        app = FastAPI()
        app.add_middleware(ValidationMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"healthy": True}

        return TestClient(app, raise_server_exceptions=False)

    def test_validation_passes(self):
        """Normal request should pass validation."""
        client = self._make_app()
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_skip_health_endpoint(self):
        """Health endpoints should skip validation."""
        client = self._make_app()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_should_skip_validation(self):
        """Known paths should be skipped."""
        from core.api.middleware.validation import ValidationMiddleware

        app = FastAPI()
        mw = ValidationMiddleware(app)

        for skip_path in ["/health", "/ready", "/live", "/metrics", "/docs", "/openapi.json"]:
            mock_req = MagicMock()
            mock_req.url.path = skip_path
            assert mw._should_skip_validation(mock_req) is True

    def test_should_not_skip_api(self):
        """API paths should NOT be skipped."""
        from core.api.middleware.validation import ValidationMiddleware

        app = FastAPI()
        mw = ValidationMiddleware(app)
        mock_req = MagicMock()
        mock_req.url.path = "/api/chat"
        assert mw._should_skip_validation(mock_req) is False

# ===========================================================================
# ErrorMetrics (not a middleware class, but a metrics module)
# ===========================================================================
class TestErrorMetrics:
    """Tests for core/api/middleware/error_metrics.py."""

    def setup_method(self):
        """Clear metrics before each test."""
        from core.api.middleware.error_metrics import clear_metrics

        clear_metrics()

    def test_record_error(self):
        """Recording an error should increment counters."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("ValueError", "/api/chat", status_code=400, error_message="bad input")
        stats = get_error_stats()

        assert stats["total_errors"] == 1
        assert stats["by_type"]["ValueError"] == 1
        assert stats["by_endpoint"]["/api/chat"] == 1
        assert stats["by_status"][400] == 1

    def test_multiple_errors(self):
        """Multiple errors should aggregate correctly."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("ValueError", "/api/chat", status_code=400)
        record_error("ValueError", "/api/chat", status_code=400)
        record_error("RuntimeError", "/api/agents", status_code=500)

        stats = get_error_stats()
        assert stats["total_errors"] == 3
        assert stats["by_type"]["ValueError"] == 2
        assert stats["by_type"]["RuntimeError"] == 1

    def test_recent_errors(self):
        """Recent errors should be accessible."""
        from core.api.middleware.error_metrics import get_recent_errors, record_error

        record_error("TestError", "/test", error_message="test msg")
        recent = get_recent_errors(limit=5)

        assert len(recent) == 1
        assert recent[0]["type"] == "TestError"
        assert recent[0]["message"] == "test msg"

    def test_recent_errors_capped_at_100(self):
        """Recent errors list should be capped at 100."""
        from core.api.middleware.error_metrics import ErrorMetrics, record_error

        for i in range(110):
            record_error("Error", "/test")

        metrics = ErrorMetrics.get_instance()
        assert len(metrics.recent_errors) == 100

    def test_clear_metrics(self):
        """Clearing metrics should reset all counters."""
        from core.api.middleware.error_metrics import clear_metrics, get_error_stats, record_error

        record_error("ValueError", "/api/chat")
        clear_metrics()
        stats = get_error_stats()

        assert stats["total_errors"] == 0
        assert stats["recent_count"] == 0

    def test_get_error_summary(self):
        """Error summary should return endpoint:type keys."""
        from core.api.middleware.error_metrics import get_error_summary, record_error

        record_error("ValueError", "/api/chat")
        summary = get_error_summary()

        assert "/api/chat:ValueError" in summary

    def test_get_error_count(self):
        """Get count for specific endpoint+type combo."""
        from core.api.middleware.error_metrics import get_error_count, record_error

        record_error("ValueError", "/api/chat")
        record_error("ValueError", "/api/chat")

        count = get_error_count("/api/chat", "ValueError")
        assert count == 2

    def test_reset_error_counts(self):
        """Reset should clear all counts."""
        from core.api.middleware.error_metrics import (
            get_error_stats,
            record_error,
            reset_error_counts,
        )

        record_error("E", "/t")
        reset_error_counts()
        stats = get_error_stats()
        assert stats["total_errors"] == 0

    def test_error_rate(self):
        """Error rate should be calculated correctly."""
        from core.api.middleware.error_metrics import get_error_stats, record_error

        record_error("E", "/t")
        stats = get_error_stats()
        assert stats["error_rate_per_minute"] >= 0

# ===========================================================================
# RequestMetricsMiddleware
# ===========================================================================
class TestRequestMetricsMiddleware:
    """Tests for core/api/middleware/request_metrics.py."""

    def test_normalize_path_uuids(self):
        """UUID-like path segments should be replaced with :id."""
        from core.api.middleware.request_metrics import normalize_path

        result = normalize_path("/api/agents/550e8400-e29b-41d4-a716-446655440000/execute")
        assert result == "/api/agents/:id/execute"

    def test_normalize_path_integers(self):
        """Integer path segments should be replaced with :id."""
        from core.api.middleware.request_metrics import normalize_path

        result = normalize_path("/api/users/12345/profile")
        assert result == "/api/users/:id/profile"

    def test_normalize_path_no_change(self):
        """Normal path segments should remain unchanged."""
        from core.api.middleware.request_metrics import normalize_path

        result = normalize_path("/api/health")
        assert result == "/api/health"

    def test_get_recent_requests(self):
        """Should return recent requests from the buffer."""
        from core.api.middleware.request_metrics import _recent_requests, get_recent_requests

        _recent_requests.clear()
        _recent_requests.append({"id": "1", "path": "/test"})
        _recent_requests.append({"id": "2", "path": "/test2"})

        result = get_recent_requests(limit=10)
        assert len(result) == 2
        # Newest first
        assert result[0]["id"] == "2"

    def test_get_recent_requests_limited(self):
        """Should respect limit parameter."""
        from core.api.middleware.request_metrics import _recent_requests, get_recent_requests

        _recent_requests.clear()
        for i in range(5):
            _recent_requests.append({"id": str(i)})

        result = get_recent_requests(limit=2)
        assert len(result) == 2

    def test_middleware_records_request(self):
        """Middleware should record requests to buffer."""
        from core.api.middleware.request_metrics import RequestMetricsMiddleware, _recent_requests

        _recent_requests.clear()

        app = FastAPI()
        app.add_middleware(RequestMetricsMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        with patch("core.api.middleware.request_metrics.record_request"):
            resp = client.get("/test")

        assert resp.status_code == 200
        assert len(_recent_requests) >= 1

# ===========================================================================
# AuthMiddleware
# ===========================================================================
class TestAuthMiddleware:
    """Tests for core/api/middleware/auth.py."""

    @staticmethod
    def _build_app_and_settings(auth_enabled=True, jwt_secret="test-secret-key"):
        """Build a FastAPI app + settings mock (caller keeps patch alive)."""
        from core.api.middleware.auth import AuthMiddleware

        settings_mock = MagicMock()
        settings_mock.auth_enabled = auth_enabled
        settings_mock.jwt_secret = jwt_secret

        app = FastAPI()
        app.add_middleware(
            AuthMiddleware,
            exclude=["/health", "/api/auth/login"],
        )

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"healthy": True}

        @app.get("/api/auth/login")
        async def login():
            return {"token": "xxx"}

        return app, settings_mock

    def test_excluded_path_passes(self):
        """Excluded paths should not require auth."""
        app, settings_mock = self._build_app_and_settings()
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_missing_auth_header(self):
        """Missing auth header should return 401."""
        app, settings_mock = self._build_app_and_settings()
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test")
        assert resp.status_code == 401
        assert "Missing" in resp.json()["detail"]

    def test_invalid_auth_format(self):
        """Non-Bearer auth header should return 401."""
        app, settings_mock = self._build_app_and_settings()
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test", headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401
        assert "Invalid authorization" in resp.json()["detail"]

    def test_auth_disabled(self):
        """With auth disabled, all requests should pass."""
        app, settings_mock = self._build_app_and_settings(auth_enabled=False)
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test")
        assert resp.status_code == 200

    def test_no_jwt_secret(self):
        """Missing JWT_SECRET should return 500."""
        app, settings_mock = self._build_app_and_settings(jwt_secret=None)
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test", headers={"Authorization": "Bearer sometoken"})
        assert resp.status_code == 500
        assert "JWT_SECRET" in resp.json()["detail"]

    def test_valid_token(self):
        """Valid JWT token should pass authentication."""
        from datetime import datetime, timedelta

        import jwt as pyjwt

        secret = "test-secret-key"
        token = pyjwt.encode(
            {"sub": "user1", "role": "user", "exp": datetime.utcnow() + timedelta(hours=1)},
            secret,
            algorithm="HS256",
        )

        app, settings_mock = self._build_app_and_settings(jwt_secret=secret)
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_expired_token(self):
        """Expired JWT token should return 401."""
        from datetime import datetime, timedelta

        import jwt as pyjwt

        secret = "test-secret-key"
        token = pyjwt.encode(
            {"sub": "user1", "exp": datetime.utcnow() - timedelta(hours=1)},
            secret,
            algorithm="HS256",
        )

        app, settings_mock = self._build_app_and_settings(jwt_secret=secret)
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"]

    def test_invalid_token(self):
        """Invalid JWT token should return 401."""
        app, settings_mock = self._build_app_and_settings(jwt_secret="test-secret-key")
        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/test", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401
        assert "Invalid token" in resp.json()["detail"]

# ===========================================================================
# LLMContextMiddleware
# ===========================================================================
class TestLLMContextMiddleware:
    """Tests for core/api/middleware/llm_config.py."""

    def test_skip_excluded_paths(self):
        """Excluded paths should skip LLM config loading."""
        settings_mock = MagicMock()
        settings_mock.llm_config_source = "database"

        with patch("core.api.middleware.llm_config.get_settings", return_value=settings_mock):
            from core.api.middleware.llm_config import LLMContextMiddleware

            app = FastAPI()
            app.add_middleware(LLMContextMiddleware, exclude=["/health"])

            @app.get("/health")
            async def health():
                return {"ok": True}

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")

        assert resp.status_code == 200

    def test_skip_env_config_source(self):
        """When config source is 'env', should skip loading."""
        settings_mock = MagicMock()
        settings_mock.llm_config_source = "env"

        with patch("core.api.middleware.llm_config.get_settings", return_value=settings_mock):
            from core.api.middleware.llm_config import LLMContextMiddleware

            app = FastAPI()
            app.add_middleware(LLMContextMiddleware)

            @app.get("/api/test")
            async def test_endpoint():
                return {"ok": True}

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/test")

        assert resp.status_code == 200

# ===========================================================================
# create_token helper
# ===========================================================================
class TestCreateToken:
    """Tests for create_token helper function."""

    def test_create_token(self):
        """Should create a valid JWT token."""
        import jwt as pyjwt

        settings_mock = MagicMock()
        settings_mock.jwt_secret = "test-secret"

        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            from core.api.middleware.auth import create_token

            token = create_token("user1", role="admin")

        payload = pyjwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["sub"] == "user1"
        assert payload["role"] == "admin"

    def test_create_token_no_secret(self):
        """Should raise ValueError when JWT_SECRET not set."""
        settings_mock = MagicMock()
        settings_mock.jwt_secret = None

        with patch("core.api.middleware.auth.get_settings", return_value=settings_mock):
            from core.api.middleware.auth import create_token

            with pytest.raises(ValueError, match="JWT_SECRET"):
                create_token("user1")

# ===========================================================================
# get_current_user helper
# ===========================================================================
class TestGetCurrentUser:
    """Tests for get_current_user helper function."""

    def test_returns_user(self):
        """Should return user from request state."""
        from core.api.middleware.auth import get_current_user

        mock_request = MagicMock()
        mock_request.state.user = {"sub": "user1", "role": "admin"}

        user = get_current_user(mock_request)
        assert user["sub"] == "user1"

    def test_returns_none_when_missing(self):
        """Should return None when no user in state."""
        from core.api.middleware.auth import get_current_user

        mock_request = MagicMock(spec=[])
        mock_request.state = MagicMock(spec=[])

        user = get_current_user(mock_request)
        assert user is None
