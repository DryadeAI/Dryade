from sqlalchemy import text

"""
Shared pytest fixtures for integration tests.

Provides:
- Test client fixtures with auth bypass
- Rate limit handling
- Database session fixtures
- Mock extension registry
- Plugin namespace setup for imports
"""

import os
import sys
import types
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Set JWT secret BEFORE any core imports — module-level imports in test files
# trigger Settings() during collection, which rejects the default value.
os.environ.setdefault(
    "DRYADE_JWT_SECRET",
    "test-integration-jwt-secret-abcdef0123456789abcdef0123456789",
)

import pytest
from fastapi.testclient import TestClient

# --- Plugin namespace setup (mirrors tests/unit/plugins/conftest.py) ---
_PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"
if "plugins" not in sys.modules:
    _pkg = types.ModuleType("plugins")
    _pkg.__path__ = [
        str(_PLUGINS_ROOT / "starter"),
        str(_PLUGINS_ROOT / "team"),
        str(_PLUGINS_ROOT / "enterprise"),
    ]
    _pkg.__package__ = "plugins"
    sys.modules["plugins"] = _pkg

def _setup_test_env():
    """Set up environment variables for testing."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"
    # Use a dedicated test database to isolate integration tests from dev data.
    # CI sets DRYADE_TEST_DATABASE_URL; local dev falls back to dryade_test.
    os.environ["DRYADE_DATABASE_URL"] = os.environ.get(
        "DRYADE_TEST_DATABASE_URL",
        "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
    )

def _seed_integration_test_users():
    """Seed test users required by integration tests into the database.

    These users are referenced by FK in conversations, workflows, scenarios, and plans.
    Safe to call multiple times — skips existing users.
    """
    from core.database.models import User
    from core.database.session import get_session

    # All user IDs used across integration test fixtures that create DB rows
    # referencing users via FK (conversations, scenario executions, plans, etc.)
    test_users = [
        ("test-user-integration", "test@example.com", "user"),
        ("admin-user", "admin@example.com", "admin"),
        ("test-user-workflow", "workflow@example.com", "user"),
        ("test-user-plans", "plans@example.com", "user"),
        ("test-user-costs", "costs@example.com", "user"),
        ("val-user-a", "val-a@test.com", "user"),
        ("val-user-b", "val-b@test.com", "user"),
        ("user-a", "a@test.com", "user"),
        ("user-b", "b@test.com", "user"),
        ("user-c", "c@test.com", "user"),
        ("test-user-123", "user123@example.com", "user"),
        # Users referenced by test_api_chat_coverage.py conversation sharing tests
        ("other-user", "other-user@test.com", "user"),
        ("dup-user", "dup-user@test.com", "user"),
        ("perm-user", "perm-user@test.com", "user"),
        ("remove-user", "remove-user@test.com", "user"),
        # Users referenced by test_sharing.py workflow sharing tests
        ("owner1", "owner1@test.com", "user"),
        ("target_user", "target@test.com", "user"),
        ("shared_user", "shared@test.com", "user"),
        ("viewer_user", "viewer@test.com", "user"),
        ("editor_user", "editor@test.com", "user"),
        ("to_unshare", "unshare@test.com", "user"),
        ("share1", "share1@test.com", "user"),
        ("share2", "share2@test.com", "user"),
        ("hacker", "hacker@test.com", "user"),
        ("recipient", "recipient@test.com", "user"),
    ]

    try:
        with get_session() as session:
            for uid, email, role in test_users:
                existing = session.query(User).filter_by(id=uid).first()
                if not existing:
                    session.add(
                        User(id=uid, email=email, password_hash=None, role=role, is_active=True)
                    )
    except Exception:
        # Non-fatal: if user seeding fails (e.g., no DB connection), tests will
        # handle FK violations themselves. Auth tests that register real users still work.
        pass

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
    - Prevents port 9471 binding and watchdog start during tests
    """
    _setup_test_env()

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    # Patch internal API and watchdog BEFORE importing app (lifespan binds port 9471)
    _noop = AsyncMock()
    patches = []
    for target in [
        "core.ee.internal_api.start_internal_api",
        "core.internal_api.start_internal_api",
        "core.allowlist_watchdog.AllowlistWatchdog.start",
    ]:
        try:
            p = patch(target, new=_noop)
            p.start()
            patches.append(p)
        except (ImportError, AttributeError):
            pass

    # Disable tier user-limit enforcement so auth registration tests aren't blocked.
    # The import is `from core.ee.allowlist_ee import get_tier_metadata` inside
    # AuthService.register(), so we must patch at the source module.
    try:
        p = patch("core.ee.allowlist_ee.get_tier_metadata", return_value=None)
        p.start()
        patches.append(p)
    except (ImportError, AttributeError):
        pass

    from core.api.main import app

    # Try to disable rate limiting
    _disable_rate_limiting(app)

    # Seed test users so FK constraints don't block conversation/workflow creation
    _seed_integration_test_users()

    yield app

    for p in patches:
        p.stop()

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
    """Cleanup any test database files after tests."""
    yield

    # Clean up test database files
    import glob

    for db_file in glob.glob("./test_*.db"):
        try:
            os.remove(db_file)
        except OSError:
            pass

@pytest.fixture(autouse=True, scope="module")
def _clean_db_between_modules():
    """Truncate all user-created data between test modules to prevent FK conflicts."""
    from core.database.session import get_session

    yield
    try:
        with get_session() as session:
            session.execute(
                text(
                    "TRUNCATE TABLE resource_shares, workflow_executions, plan_executions, messages, conversations, workflows, plans CASCADE"
                )
            )
            session.commit()
    except Exception:
        pass  # Tables may not exist in all test runs
