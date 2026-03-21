"""
Shared pytest fixtures for Dryade V2 tests.

This module provides common fixtures used across unit, integration, and e2e tests.
It is automatically loaded by pytest for all tests in the tests/ directory.

Fixture Categories:
    - Configuration: mock_settings
    - Mocks: mock_llm, mock_mcp_bridge
    - Sample Data: sample_messages, sample_conversation_id, sample_user_id,
                   capella_session_mock, sample_elements, sample_state_exports
    - Context: async_context
    - HTTP Clients: async_client, test_app
    - Database: db_session, test_app_with_db

Custom Markers:
    - @pytest.mark.unit: Unit tests (fast, isolated)
    - @pytest.mark.integration: Integration tests (may use real services)
    - @pytest.mark.e2e: End-to-end tests (full stack)
    - @pytest.mark.slow: Slow-running tests
    - @pytest.mark.requires_llm: Tests requiring LLM service
    - @pytest.mark.requires_mcp: Tests requiring MCP server
"""

import os

# Set JWT secret BEFORE any core imports — module-level imports in test files
# trigger Settings() during collection, which rejects the default value
# (insecure pattern check added in Phase 171).
os.environ.setdefault(
    "DRYADE_JWT_SECRET",
    "test-ci-jwt-secret-abcdef0123456789abcdef0123456789",
)

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]

# =============================================================================
# Event Loop Configuration
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests.

    Scope:
        session - shared across all tests in the session

    Returns:
        asyncio.AbstractEventLoop: Event loop for async test execution.

    Note:
        This fixture is required by pytest-asyncio for session-scoped async fixtures.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def mock_settings():
    """Provide a Settings object configured for testing.

    Scope:
        function (default)

    Returns:
        Settings: Configuration with safe test defaults:
            - env: development
            - auth_enabled: False
            - redis_enabled: False

    Example:
        def test_something(mock_settings):
            assert mock_settings.debug is True
    """
    from core.config import Settings

    return Settings(
        env="development",
        debug=True,
        log_level="DEBUG",
        llm_mode="vllm",
        llm_model="test-model",
        llm_base_url="http://localhost:8000/v1",
        auth_enabled=False,
        redis_enabled=False,
    )

# =============================================================================
# Mock Fixtures (External Services)
# =============================================================================

@pytest.fixture
def mock_llm():
    """Provide a mock LLM client for testing without API calls.

    Scope:
        function (default)

    Returns:
        MagicMock: Mock with preconfigured sync and async methods:
            - call() -> "Mock LLM response"
            - acall() -> "Mock async LLM response"

    Example:
        def test_chat(mock_llm):
            mock_llm.call.return_value = "Custom response"
    """
    mock = MagicMock()
    mock.call.return_value = "Mock LLM response"
    mock.acall = AsyncMock(return_value="Mock async LLM response")
    return mock

@pytest.fixture
def mock_mcp_bridge():
    """Provide a mock MCP bridge for testing Capella integration.

    Scope:
        function (default)

    Returns:
        MagicMock: Mock returning {"status": "ok", "result": "mock"} by default.

    Example:
        def test_mcp_call(mock_mcp_bridge):
            result = mock_mcp_bridge.call("some_tool", {})
    """
    mock = MagicMock()
    mock.call.return_value = {"status": "ok", "result": "mock"}
    return mock

# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_messages():
    """Provide sample chat messages for conversation testing.

    Scope:
        function (default)

    Returns:
        list[dict]: Two messages - a system prompt and user message.
    """
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]

@pytest.fixture
def sample_conversation_id():
    """Provide a sample conversation ID.

    Scope:
        function (default)

    Returns:
        str: "test-conv-123"
    """
    return "test-conv-123"

@pytest.fixture
def sample_user_id():
    """Provide a sample user ID.

    Scope:
        function (default)

    Returns:
        str: "test-user-456"
    """
    return "test-user-456"

@pytest.fixture
def capella_session_mock():
    """Provide a mock Capella/MCP session object.

    Scope:
        function (default)

    Returns:
        dict: Session with session_id, model_path, and status.
    """
    return {
        "session_id": "test-session-789",
        "model_path": "/path/to/test.aird",
        "status": "active",
    }

@pytest.fixture
def sample_elements():
    """Provide sample Capella model elements for testing.

    Scope:
        function (default)

    Returns:
        list[dict]: Three elements - two LogicalFunctions and one LogicalComponent.
    """
    return [
        {"uuid": "elem-1", "name": "Function A", "type": "LogicalFunction"},
        {"uuid": "elem-2", "name": "Function B", "type": "LogicalFunction"},
        {"uuid": "elem-3", "name": "Component X", "type": "LogicalComponent"},
    ]

@pytest.fixture
def async_context():
    """Provide context data for async operation testing.

    Scope:
        function (default)

    Returns:
        dict: Context with conversation_id, user_id, session_id, model_path.
    """
    return {
        "conversation_id": "test-conv-123",
        "user_id": "test-user-456",
        "session_id": "test-session-789",
        "model_path": "/path/to/model.aird",
    }

@pytest.fixture
def sample_state_exports():
    """Provide sample state export data for state management testing.

    Scope:
        function (default)

    Returns:
        list[dict]: Three results with varying _exports configurations.
    """
    return [
        {"session_id": "sess_123", "status": "ok", "_exports": {"mbse.session_id": "sess_123"}},
        {"count": 10, "items": ["a", "b"], "_exports": {"mbse.item_count": 10}},
        {"result": "done"},  # No exports
    ]

# =============================================================================
# HTTP Client Fixtures
# =============================================================================

@pytest.fixture
async def async_client():
    """Provide an async HTTP client for API testing.

    Scope:
        function (default)

    Yields:
        httpx.AsyncClient: Client configured for localhost:8080.

    Note:
        Requires the API server to be running.
    """
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:8080") as client:
        yield client

@pytest.fixture
def test_app():
    """Provide a synchronous test client for the FastAPI application.

    Scope:
        function (default)

    Yields:
        TestClient: FastAPI TestClient wrapping the main app with auth bypass.

    Example:
        def test_health(test_app):
            response = test_app.get("/health")
            assert response.status_code == 200
    """
    from fastapi.testclient import TestClient

    from core.api.main import app
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-default", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Provide an in-memory SQLite database session for testing.

    Scope:
        function (default)

    Yields:
        sqlalchemy.orm.Session: Database session with all tables created.

    Note:
        Tables are created before yielding and dropped after the test.
        Uses in-memory SQLite for complete test isolation.

    Example:
        def test_create_user(db_session):
            user = User(email="test@example.com")
            db_session.add(user)
            db_session.commit()
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.database.models import Base

    # PostgreSQL test database for test isolation
    engine = create_engine(
        os.environ.get(
            "DRYADE_TEST_DATABASE_URL",
            "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
        ),
        echo=False,
    )
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)

    # Truncate tables before each test to prevent key collisions from prior runs.
    with Session() as _cleanup:
        from core.database.models import User

        _cleanup.query(User).delete()
        _cleanup.commit()

    session = Session()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_app_with_db(db_session):
    """Provide a test client with database session override.

    Scope:
        function (default)

    Dependencies:
        db_session: The in-memory database session to use.

    Yields:
        TestClient: FastAPI TestClient with get_db dependency overridden.

    Note:
        Dependency overrides are cleared after the test completes.

    Example:
        def test_api_with_db(test_app_with_db):
            response = test_app_with_db.post("/api/v1/users", json={...})
    """
    from fastapi.testclient import TestClient

    from core.api.main import app
    from core.auth.dependencies import get_current_user, get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return {"sub": "test-user-db", "email": "test@example.com", "role": "user"}

    # Override the central get_db function and auth
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()

# =============================================================================
# Internal API Mock (prevents port 9471 binding during tests)
# =============================================================================

@pytest.fixture(autouse=True)
def mock_internal_api():
    """Prevent internal API from binding port 9471 during tests."""
    try:
        with patch("core.internal_api.start_internal_api", new=AsyncMock()):
            yield
    except (ImportError, AttributeError):
        # internal_api module may not exist in all configurations
        yield

# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure custom pytest markers.

    Registers the following markers:
        - unit: Unit tests (fast, isolated, no external dependencies)
        - integration: Integration tests (may use databases, services)
        - e2e: End-to-end tests (full application stack)
        - slow: Tests that take significant time to run
        - requires_llm: Tests that require LLM service availability
        - requires_mcp: Tests that require MCP server availability
    """
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "requires_llm: Tests requiring LLM")
    config.addinivalue_line("markers", "requires_mcp: Tests requiring MCP server")
