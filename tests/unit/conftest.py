"""
Unit test fixtures for core extensions.

This module provides fixtures specific to unit testing the core extension
infrastructure. These fixtures are isolated and do not require external services.

Fixture Categories:
    - Extension Registry & Pipeline: mock_extension_registry, mock_extension_config,
                                     populated_extension_registry, mock_extension_pipeline
    - Context Store: mock_context_store, empty_context_store
    - State Management: sample_state_exports, mock_state_store, mock_state_store_with_conflicts
    - Async Context: async_context
    - Mock Functions: mock_decorated_function, mock_async_handler

Note:
    These fixtures are scoped to function level to ensure test isolation.
    Fixtures do not leak state between tests.
"""

import sys
import types
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# ``plugins`` namespace package for unit tests outside tests/unit/plugins/
# ---------------------------------------------------------------------------
# At runtime, core.plugins.PluginManager registers each plugin as
# ``plugins.<name>`` in sys.modules.  Tests that import plugin code directly
# (e.g. ``from plugins.zitadel_auth import ZitadelAuthPlugin``) need the
# ``plugins`` namespace to point at the tier directories in dryade-plugins/.
# ---------------------------------------------------------------------------

_PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "dryade-plugins"

if "plugins" not in sys.modules:
    _pkg = types.ModuleType("plugins")
    _pkg.__path__ = [  # type: ignore[attr-defined]
        str(_PLUGINS_ROOT / "starter"),
        str(_PLUGINS_ROOT / "team"),
        str(_PLUGINS_ROOT / "enterprise"),
    ]
    _pkg.__package__ = "plugins"
    sys.modules["plugins"] = _pkg

# =============================================================================
# Extension Registry and Pipeline Fixtures
# =============================================================================

@pytest.fixture
def mock_extension_registry():
    """Provide an empty ExtensionRegistry for testing.

    Scope:
        function (default)

    Returns:
        ExtensionRegistry: Empty registry ready for extension registration.

    Example:
        def test_register(mock_extension_registry):
            mock_extension_registry.register(some_config)
    """
    from core.extensions.pipeline import ExtensionRegistry

    return ExtensionRegistry()

@pytest.fixture
def mock_extension_config():
    """Provide sample ExtensionConfig instances for testing.

    Scope:
        function (default)

    Returns:
        dict[str, ExtensionConfig]: Four preconfigured extension configs:
            - input_validation: enabled, priority 1
            - semantic_cache: enabled, priority 2
            - self_healing: disabled, priority 3
            - sandbox: enabled, priority 4

    Note:
        self_healing is disabled by default to test enabled/disabled filtering.
    """
    from core.extensions.pipeline import ExtensionConfig, ExtensionType

    return {
        "input_validation": ExtensionConfig(
            name="test_input_validation",
            type=ExtensionType.INPUT_VALIDATION,
            enabled=True,
            priority=1,
        ),
        "semantic_cache": ExtensionConfig(
            name="test_semantic_cache",
            type=ExtensionType.SEMANTIC_CACHE,
            enabled=True,
            priority=2,
        ),
        "self_healing": ExtensionConfig(
            name="test_self_healing",
            type=ExtensionType.SELF_HEALING,
            enabled=False,  # Disabled for testing
            priority=3,
        ),
        "sandbox": ExtensionConfig(
            name="test_sandbox",
            type=ExtensionType.SANDBOX,
            enabled=True,
            priority=4,
        ),
    }

@pytest.fixture
def populated_extension_registry(mock_extension_registry, mock_extension_config):
    """Provide a registry pre-populated with test extensions.

    Scope:
        function (default)

    Dependencies:
        mock_extension_registry: Empty registry to populate.
        mock_extension_config: Extension configs to register.

    Returns:
        ExtensionRegistry: Registry with four registered extensions.
    """
    for config in mock_extension_config.values():
        mock_extension_registry.register(config)
    return mock_extension_registry

@pytest.fixture
def mock_extension_pipeline(populated_extension_registry):
    """Provide an ExtensionPipeline with mocked extensions.

    Scope:
        function (default)

    Dependencies:
        populated_extension_registry: Registry with registered extensions.

    Returns:
        ExtensionPipeline: Pipeline ready for execution testing.
    """
    from core.extensions.pipeline import ExtensionPipeline

    return ExtensionPipeline(populated_extension_registry)

# =============================================================================
# Context Store Fixtures
# =============================================================================

@pytest.fixture
def mock_context_store():
    """Provide a ContextStore pre-populated with test data.

    Scope:
        function (default)

    Returns:
        ContextStore: Store with values at all scope levels and a cascade key.

    Pre-populated keys:
        - test.conversation_key: "conv_value" (CONVERSATION scope)
        - test.session_key: "session_value" (SESSION scope)
        - test.project_key: "project_value" (PROJECT scope)
        - test.user_key: "user_value" (USER scope)
        - test.global_key: "global_value" (GLOBAL scope)
        - test.cascade_key: "cascade_conv" (CONVERSATION) and "cascade_global" (GLOBAL)

    Note:
        The cascade_key exists at multiple scopes to test scope resolution.
    """
    from core.extensions.context import ContextScope, ContextStore

    store = ContextStore()

    # Set test values at different scopes
    store.set("test.conversation_key", "conv_value", ContextScope.CONVERSATION)
    store.set("test.session_key", "session_value", ContextScope.SESSION)
    store.set("test.project_key", "project_value", ContextScope.PROJECT)
    store.set("test.user_key", "user_value", ContextScope.USER)
    store.set("test.global_key", "global_value", ContextScope.GLOBAL)

    # Set a value that exists at multiple scopes (for cascade testing)
    store.set("test.cascade_key", "cascade_conv", ContextScope.CONVERSATION)
    store.set("test.cascade_key", "cascade_global", ContextScope.GLOBAL)

    return store

@pytest.fixture
def empty_context_store():
    """Provide an empty ContextStore.

    Scope:
        function (default)

    Returns:
        ContextStore: Fresh store with no values set.
    """
    from core.extensions.context import ContextStore

    return ContextStore()

# =============================================================================
# State Management Fixtures
# =============================================================================

@pytest.fixture
def sample_state_exports():
    """Provide sample state export data for testing.

    Scope:
        function (default)

    Returns:
        list[dict]: Three result dictionaries demonstrating different export patterns:
            - First: has _exports with session_id
            - Second: has _exports with item_count
            - Third: no _exports (tests absence handling)
    """
    return [
        {"session_id": "sess_123", "status": "ok", "_exports": {"mbse.session_id": "sess_123"}},
        {"count": 10, "items": ["a", "b"], "_exports": {"mbse.item_count": 10}},
        {"result": "done"},  # No exports
    ]

@pytest.fixture
def mock_state_store():
    """Provide a MultiValueStateStore with initial state.

    Scope:
        function (default)

    Returns:
        MultiValueStateStore: Store with one exported value:
            - mbse.session_id: "sess_001" (from tool_a, label="Session A")
    """
    from core.extensions.state import MultiValueStateStore

    store = MultiValueStateStore()

    # Add some initial state
    store.export("mbse.session_id", "sess_001", "tool_a", label="Session A")

    return store

@pytest.fixture
def mock_state_store_with_conflicts():
    """Provide a MultiValueStateStore with conflicting values.

    Scope:
        function (default)

    Returns:
        MultiValueStateStore: Store with conflicting values for the same key:
            - mbse.session_id: "sess_001" from tool_a
            - mbse.session_id: "sess_002" from tool_b

    Note:
        Use this to test conflict resolution and disambiguation.
    """
    from core.extensions.state import MultiValueStateStore

    store = MultiValueStateStore()

    # Add conflicting values for the same key
    store.export("mbse.session_id", "sess_001", "tool_a", label="Session A")
    store.export("mbse.session_id", "sess_002", "tool_b", label="Session B")

    return store

# =============================================================================
# Async Context Fixtures
# =============================================================================

@pytest.fixture
def async_context():
    """Provide context data for async operation testing.

    Scope:
        function (default)

    Returns:
        dict: Context with unique async-prefixed test IDs.

    Note:
        Uses different IDs than root conftest to avoid confusion.
    """
    return {
        "conversation_id": "test-conv-async-123",
        "user_id": "test-user-async-456",
        "session_id": "test-session-async-789",
    }

# =============================================================================
# Mock Functions for State Decorators
# =============================================================================

@pytest.fixture
def mock_decorated_function():
    """Provide a mock function with state decorators applied.

    Scope:
        function (default)

    Returns:
        Callable: Function decorated with @export_state and @requires_state.

    Note:
        The function exports session_id and requires mbse.model_path.
        Use this to test decorator behavior.
    """
    from core.extensions.state import export_state, requires_state

    @export_state(session_id="mbse.session_id")
    @requires_state("mbse.model_path")
    def mock_tool(model_path: str = None) -> dict:
        return {
            "session_id": f"sess_{model_path[-5:] if model_path else 'none'}",
            "status": "ok",
        }

    return mock_tool

@pytest.fixture
def mock_async_handler():
    """Provide a mock async handler for pipeline testing.

    Scope:
        function (default)

    Returns:
        Callable: Async function that returns {"result": "success", "data": <input>}.
    """

    async def handler(data: dict[str, Any]) -> Any:
        return {"result": "success", "data": data}

    return handler
