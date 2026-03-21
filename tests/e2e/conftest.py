"""E2E test fixtures.

Extends integration fixtures with multi-user support and LLM mocking.
Everything runs for real (DB, middleware, routing) except the LLM layer.
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Import integration fixtures so they're available to e2e tests.
# (pytest_plugins is only allowed in top-level conftest.py)
from tests.integration.conftest import integration_test_app  # noqa: F401

# ---------------------------------------------------------------------------
# App & DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(integration_test_app) -> Generator[Session, None, None]:
    """Provide a database session tied to the integration test app's engine."""
    from sqlalchemy.orm import sessionmaker

    from core.database.session import get_engine

    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ---------------------------------------------------------------------------
# Authenticated clients
# ---------------------------------------------------------------------------

def _make_client(app, user_id: str, email: str, role: str = "user"):
    """Create a TestClient with get_current_user overridden."""
    from core.auth.dependencies import get_current_user

    def override():
        return {"sub": user_id, "email": email, "role": role}

    app.dependency_overrides[get_current_user] = override
    return TestClient(app, raise_server_exceptions=False)

@pytest.fixture
def e2e_client(integration_test_app) -> Generator[TestClient, None, None]:
    """Primary E2E user client."""
    client = _make_client(integration_test_app, "test-user-e2e", "e2e@example.com")
    with client:
        yield client
    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def second_user_client(integration_test_app) -> Generator[TestClient, None, None]:
    """Second user for cross-user / sharing tests."""
    client = _make_client(integration_test_app, "test-user-e2e-2", "e2e2@example.com")
    with client:
        yield client
    integration_test_app.dependency_overrides.clear()

@pytest.fixture
def admin_e2e_client(integration_test_app) -> Generator[TestClient, None, None]:
    """Admin role client."""
    client = _make_client(integration_test_app, "admin-e2e", "admin-e2e@example.com", role="admin")
    with client:
        yield client
    integration_test_app.dependency_overrides.clear()

# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_route_request():
    """Patch route_request so no real LLM calls happen.

    Returns a canned assistant response for any chat request.
    """

    async def _fake_route(message, *, conversation_id=None, mode=None, user_id=None, **kw):
        return {
            "response": f"Mock response to: {message[:50]}",
            "conversation_id": conversation_id or "mock-conv",
            "tool_calls": [],
            "tokens": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    with patch("core.api.routes.chat.route_request", new=AsyncMock(side_effect=_fake_route)):
        yield
