"""
Shared pytest fixtures for integration tests.

Provides:
- Test client fixtures with auth bypass
- Rate limit handling
- Database session fixtures
- Mock extension registry
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

def _setup_test_env():
    """Set up environment variables for testing."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"
    # Set a test-safe JWT secret to avoid validator rejection of the default
    # "dev-secret-change-me-..." value (fixed in 171-02 to reject this pattern)
    os.environ.setdefault(
        "DRYADE_JWT_SECRET",
        "test-integration-jwt-secret-abcdef0123456789abcdef0123456789",
    )

def _disable_rate_limiting(app):
    """Disable rate limiting middleware for tests."""
    # Access the middleware stack and disable rate limiting
    for middleware in app.user_middleware:
        if hasattr(middleware, "cls"):
            cls_name = getattr(middleware.cls, "__name__", "")
            if "RateLimit" in cls_name:
                # Mark middleware options to disable
                if "kwargs" in middleware.__dict__:
                    middleware.kwargs["requests_per_minute"] = 10000

@pytest.fixture(scope="session")
def integration_test_app():
    """Create FastAPI app instance for integration testing.

    This fixture:
    - Sets up test environment variables
    - Clears cached settings
    - Initializes in-memory database
    - Disables rate limiting
    """
    _setup_test_env()

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app

    # Try to disable rate limiting
    _disable_rate_limiting(app)

    return app

@pytest.fixture
def authenticated_client(integration_test_app) -> Generator[TestClient, None, None]:
    """Provide an authenticated test client.

    Mocks get_current_user to bypass authentication.
    Each test gets a fresh override that's cleaned up after.
    """
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-integration", "email": "test@example.com", "role": "user"}

    integration_test_app.dependency_overrides[get_current_user] = override_get_current_user

    # Clear rate limiter state if possible
    try:
        for middleware in integration_test_app.middleware_stack.app.middleware:
            if hasattr(middleware, "requests"):
                middleware.requests.clear()
    except Exception:
        pass

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        yield client

    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def admin_client(integration_test_app) -> Generator[TestClient, None, None]:
    """Provide an admin-authenticated test client.

    Mocks get_current_user with admin role.
    """
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "admin-user", "email": "admin@example.com", "role": "admin"}

    integration_test_app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(integration_test_app, raise_server_exceptions=False) as client:
        yield client

    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def mock_extension_registry():
    """Mock extension registry for testing extension endpoints."""
    from unittest.mock import MagicMock, patch

    mock_registry = MagicMock()
    mock_registry.get_enabled.return_value = []

    with patch("core.extensions.pipeline.get_extension_registry", return_value=mock_registry):
        yield mock_registry

@pytest.fixture
def test_extension_config():
    """Test configuration for extensions."""
    return {
        "extensions_enabled": True,
        "input_validation_enabled": True,
        "semantic_cache_enabled": False,  # Disabled for tests
        "self_healing_enabled": True,
        "sandbox_enabled": False,  # Disabled for tests
        "file_safety_enabled": False,  # Disabled for tests
        "output_sanitization_enabled": True,
    }

@pytest.fixture
def cleanup_test_db():
    """No-op fixture — PostgreSQL test cleanup is handled by transaction rollback.

    Retained for backward compatibility with tests that reference this fixture.
    Kept as a no-op for backward compatibility with tests that reference it.
    """
    yield
