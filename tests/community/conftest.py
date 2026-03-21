"""
Pytest fixtures for Dryade plugin testing.

These fixtures help plugin developers test their plugins in isolation
without needing a full Dryade environment.

Usage in your plugin tests:

    # tests/test_my_plugin.py
    pytest_plugins = ['tests.community.conftest']

    def test_plugin_loads(plugin_context, mock_llm):
        from my_plugin import plugin
        await plugin.on_load(plugin_context)
        assert plugin.is_loaded
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

# =============================================================================
# Mock LLM
# =============================================================================

@dataclass
class MockLLMResponse:
    """Mock response from LLM."""

    content: str = "Mock LLM response"
    model: str = "mock-model"
    usage: dict = field(default_factory=lambda: {"total_tokens": 100})

class MockLLM:
    """Mock LLM for testing without API calls."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["Mock response"]
        self._call_count = 0
        self.calls: list[dict] = []

    async def generate(self, prompt: str, **kwargs) -> MockLLMResponse:
        """Generate mock response."""
        self.calls.append({"prompt": prompt, **kwargs})
        response = self.responses[self._call_count % len(self.responses)]
        self._call_count += 1
        return MockLLMResponse(content=response)

    def __call__(self, prompt: str, **kwargs):
        """Sync call for compatibility."""
        return asyncio.get_event_loop().run_until_complete(self.generate(prompt, **kwargs))

@pytest.fixture
def mock_llm():
    """Fixture providing a mock LLM.

    Usage:
        def test_with_llm(mock_llm):
            mock_llm.responses = ["Expected response"]
            result = my_function_using_llm()
            assert mock_llm.calls[0]["prompt"] == "expected prompt"
    """
    return MockLLM()

@pytest.fixture
def mock_llm_factory():
    """Factory fixture for custom mock LLMs.

    Usage:
        def test_multiple_responses(mock_llm_factory):
            llm = mock_llm_factory(["Response 1", "Response 2"])
            # First call returns "Response 1", second returns "Response 2"
    """

    def factory(responses: list[str] | None = None):
        return MockLLM(responses)

    return factory

# =============================================================================
# Plugin Context
# =============================================================================

@pytest.fixture
def plugin_context():
    """Fixture providing mock plugin context.

    Usage:
        async def test_plugin_init(plugin_context):
            from my_plugin import plugin
            await plugin.on_load(plugin_context)
            assert plugin.is_loaded
    """
    return {
        "app": MagicMock(),
        "settings": {
            "llm_model": "mock-model",
            "llm_provider": "mock",
            "debug": True,
        },
        "db_session": MagicMock(),
        "user": {
            "id": "test-user-id",
            "email": "test@example.com",
        },
    }

@pytest.fixture
def plugin_context_factory():
    """Factory for custom plugin contexts.

    Usage:
        def test_with_custom_settings(plugin_context_factory):
            ctx = plugin_context_factory(settings={"custom": True})
    """

    def factory(
        app: Any = None,
        settings: dict | None = None,
        db_session: Any = None,
        user: dict | None = None,
    ):
        return {
            "app": app or MagicMock(),
            "settings": settings or {"debug": True},
            "db_session": db_session or MagicMock(),
            "user": user or {"id": "test-user"},
        }

    return factory

# =============================================================================
# Mock Database
# =============================================================================

class MockDBSession:
    """Mock database session for testing."""

    def __init__(self):
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj: Any):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def query(self, model: type):
        return MockQuery(model)

class MockQuery:
    """Mock query builder."""

    def __init__(self, model: type):
        self.model = model
        self._filters: list = []
        self._results: list = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def filter_by(self, **kwargs):
        self._filters.append(kwargs)
        return self

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return self._results

    def with_results(self, results: list):
        """Set mock results."""
        self._results = results
        return self

@pytest.fixture
def mock_db_session():
    """Fixture providing mock database session."""
    return MockDBSession()

# =============================================================================
# API Request/Response Mocks
# =============================================================================

@pytest.fixture
def mock_request():
    """Fixture providing mock FastAPI request."""
    request = MagicMock()
    request.state.user = {"id": "test-user", "email": "test@example.com"}
    request.headers = {"authorization": "Bearer test-token"}
    request.query_params = {}
    return request

@pytest.fixture
def mock_response():
    """Fixture providing mock FastAPI response."""
    return MagicMock()

# =============================================================================
# MCP Mocks
# =============================================================================

class MockMCPServer:
    """Mock MCP server for testing tool calls."""

    def __init__(self, name: str = "mock-server"):
        self.name = name
        self.tools: dict[str, callable] = {}
        self.calls: list[dict] = []

    def register_tool(self, name: str, handler: callable):
        """Register a mock tool."""
        self.tools[name] = handler

    async def call_tool(self, tool_name: str, **kwargs) -> dict:
        """Call a registered tool."""
        self.calls.append({"tool": tool_name, **kwargs})
        if tool_name in self.tools:
            return await self.tools[tool_name](**kwargs)
        return {"result": f"Mock result for {tool_name}"}

@pytest.fixture
def mock_mcp_server():
    """Fixture providing mock MCP server."""
    return MockMCPServer()

# =============================================================================
# Event Fixtures
# =============================================================================

class MockEventEmitter:
    """Mock event emitter for testing event hooks."""

    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event_type: str, data: dict):
        self.events.append({"type": event_type, "data": data})

    def get_events(self, event_type: str | None = None):
        if event_type:
            return [e for e in self.events if e["type"] == event_type]
        return self.events

@pytest.fixture
def mock_event_emitter():
    """Fixture providing mock event emitter."""
    return MockEventEmitter()

# =============================================================================
# Async Helpers
# =============================================================================

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# =============================================================================
# Plugin Lifecycle Helpers
# =============================================================================

@pytest.fixture
def plugin_loader():
    """Helper for loading plugins in tests.

    Usage:
        async def test_plugin(plugin_loader, plugin_context):
            plugin = await plugin_loader("my_plugin", plugin_context)
            assert plugin.is_loaded
    """

    async def load(plugin_name: str, context: dict):
        # Import plugin module
        module = __import__(f"plugins.{plugin_name}", fromlist=["plugin"])
        plugin = module.plugin

        # Load with context
        await plugin.on_load(context)

        return plugin

    return load
