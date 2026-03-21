"""Dryade Extensions - Core Only.

This module exports only core extensions that are fundamental to Dryade.
Optional extensions are loaded via the plugin system (core.plugins).

Core extensions (always present):
- events.py: SSE streaming
- context.py: Context hierarchy
- state.py: State management
- pipeline.py: Extension infrastructure
- decorator.py: @with_extensions decorator
"""

# Core extensions - fundamental to Dryade operation
from core.extensions.context import (
    ContextScope,
    ContextStore,
    get_context,
    get_context_value,
    set_context,
)
from core.extensions.decorator import with_extensions
from core.extensions.events import (
    ChatEvent,
    emit_agent_complete,
    emit_agent_start,
    emit_clarify,
    emit_clarify_response,
    emit_complete,
    emit_done,
    emit_error,
    emit_flow_complete,
    emit_flow_start,
    emit_node_complete,
    emit_node_start,
    emit_state_export,
    emit_thinking,
    emit_token,
    emit_tool_result,
    emit_tool_start,
    to_openai_sse,
)
from core.extensions.pipeline import (
    ExtensionConfig,
    ExtensionPipeline,
    ExtensionRegistry,
    ExtensionRequest,
    ExtensionResponse,
    ExtensionType,
    build_pipeline,
    get_extension_registry,
)
from core.extensions.state import export_state, extract_exports, requires_state, resolve_state

# Core exports - always available
__all__ = [
    # State management (fundamental)
    "export_state",
    "requires_state",
    "resolve_state",
    "extract_exports",
    # Context hierarchy (fundamental)
    "ContextScope",
    "ContextStore",
    "get_context",
    "set_context",
    "get_context_value",
    # Events (fundamental - SSE streaming)
    "ChatEvent",
    "emit_token",
    "emit_thinking",
    "emit_tool_start",
    "emit_tool_result",
    "emit_agent_start",
    "emit_agent_complete",
    "emit_node_start",
    "emit_node_complete",
    "emit_flow_start",
    "emit_flow_complete",
    "emit_clarify",
    "emit_clarify_response",
    "emit_state_export",
    "emit_complete",
    "emit_error",
    "emit_done",
    "to_openai_sse",
    # Extension Pipeline (fundamental infrastructure)
    "ExtensionType",
    "ExtensionConfig",
    "ExtensionRequest",
    "ExtensionResponse",
    "ExtensionRegistry",
    "ExtensionPipeline",
    "get_extension_registry",
    "build_pipeline",
    "with_extensions",
]

# =============================================================================
# Optional Plugin Re-exports (Lazy via __getattr__)
# =============================================================================
# Plugin symbols are loaded lazily on first access via module __getattr__.
# Direct imports from plugin modules (e.g., `from plugins.safety import ...`)
# are preferred. Importing from core.extensions emits a DeprecationWarning.

import importlib as _importlib
import warnings as _warnings

class _PluginStub:
    """Sentinel for missing plugin symbols.

    Supports | operator for type annotations (e.g., CheckpointStore | None).
    Falsy so `if X:` guards work. Raises RuntimeError when called.
    """

    def __init__(self, name: str):
        self._name = name

    def __or__(self, other):
        return type(f"Optional_{self._name}", (), {})

    def __ror__(self, other):
        return type(f"Optional_{self._name}", (), {})

    def __call__(self, *args, **kwargs):
        raise RuntimeError(
            f"Plugin not available: '{self._name}' requires a plugin that is not loaded"
        )

    def __bool__(self):
        return False

    def __repr__(self):
        return f"<PluginStub: {self._name}>"

def _try_import(module_path: str, names: list):
    """Safely import and add to __all__ if plugin is available.

    DEPRECATED: Kept for backward compatibility with tests.
    Prefer lazy __getattr__ for new plugin re-exports.
    """
    try:
        module = __import__(module_path, fromlist=names)
        for name in names:
            if hasattr(module, name):
                globals()[name] = getattr(module, name)
                if name not in __all__:
                    __all__.append(name)
    except ImportError:
        for name in names:
            if name not in globals():
                globals()[name] = _PluginStub(name)
                if name not in __all__:
                    __all__.append(name)

def _import_cache_wrapper():
    """Import and alias cache wrapper functions.

    DEPRECATED: Kept for backward compatibility with tests.
    """
    try:
        from plugins.semantic_cache.wrapper import cached_llm_call, cached_llm_stream

        globals()["cached_llm_call_async"] = cached_llm_call
        globals()["cached_llm_stream_async"] = cached_llm_stream
        if "cached_llm_call_async" not in __all__:
            __all__.append("cached_llm_call_async")
        if "cached_llm_stream_async" not in __all__:
            __all__.append("cached_llm_stream_async")
    except ImportError:
        pass  # Plugin not available

# Clarification (core module - always available)
from core.clarification import (  # noqa: F401 — re-exported via __all__.extend()
    ClarificationRequest,
    ClarificationResponse,
    cancel_clarification,
    has_pending_clarification,
    request_clarification,
    submit_clarification,
)

__all__.extend(
    [
        "ClarificationRequest",
        "ClarificationResponse",
        "request_clarification",
        "submit_clarification",
        "has_pending_clarification",
        "cancel_clarification",
    ]
)

# ---------------------------------------------------------------------------
# Lazy plugin re-export registry
# Maps symbol name -> (module_path, attr_name_in_module)
# When a name appears in multiple modules, the first listed wins.
# ---------------------------------------------------------------------------
_PLUGIN_IMPORTS: dict[str, tuple[str, str]] = {}

def _register(module_path: str, names: list[str]) -> None:
    """Register plugin symbols for lazy loading via __getattr__."""
    for name in names:
        if name not in _PLUGIN_IMPORTS:
            _PLUGIN_IMPORTS[name] = (module_path, name)

# Semantic cache
_register(
    "plugins.semantic_cache",
    [
        "SemanticCache",
        "get_semantic_cache",
        "get_cache_config",
        "cached_llm_call",
        "cached_llm_stream",
        "CacheHitMarker",
    ],
)
_register("plugins.semantic_cache.embedder", ["EmbeddingGenerator"])

# Semantic cache wrapper aliases
_PLUGIN_IMPORTS["cached_llm_call_async"] = ("plugins.semantic_cache.wrapper", "cached_llm_call")
_PLUGIN_IMPORTS["cached_llm_stream_async"] = ("plugins.semantic_cache.wrapper", "cached_llm_stream")

# Sandbox
_register(
    "plugins.sandbox",
    [
        "IsolationLevel",
        "SandboxConfig",
        "SandboxResult",
        "ToolSandbox",
        "get_sandbox",
        "sandboxed_execute",
        "execute_sandboxed_tool",
    ],
)
_register("plugins.sandbox.cache", ["get_sandbox_cache"])
_register("plugins.sandbox.registry", ["get_sandbox_registry"])

# File safety
_register(
    "plugins.file_safety",
    [
        "FileSafetyGuard",
        "file_guard",
        "ScanResult",
        "record_file_read",
        "check_can_edit",
        "refresh_file_hash",
    ],
)
_register(
    "plugins.file_safety.scanner",
    [
        "get_clamav_scanner",
        "get_yara_scanner",
        "is_file_safe",
        "scan_file_combined",
    ],
)

# Self-healing
_register(
    "plugins.self_healing",
    [
        "ErrorType",
        "HealingResult",
        "SelfHealingExecutor",
        "get_self_healer",
        "with_self_healing",
        "execute_with_self_healing",
        "CircuitBreaker",
        "get_circuit_breaker",
    ],
)
_register(
    "plugins.self_healing.circuit_breaker",
    [
        "get_all_circuit_breakers",
    ],
)

# Safety (migrated from plugin to core in Phase 222)
_register(
    "core.safety.validator",
    [
        "SafetyLevel",
        "SafetyRule",
        "SafetyClassifier",
        "safety_classifier",
        "classify_safety",
        "is_safe_operation",
        "is_blocked_operation",
        "ValidationResult",
        "validate_input",
        "sanitize_output",
    ],
)

# VLLM LLM (migrated from plugin to core)
_register("core.providers.vllm_llm", ["VLLMBaseLLM", "get_vllm_llm", "create_vllm_for_crewai"])

# MCP bridge (migrated from plugin to core in Phase 222)
_register("core.mcp.bridge", ["MCPBridge", "get_bridge", "create_tool_wrapper"])

# Cost tracking (migrated from plugin to core in Phase 191)
_register(
    "core.cost_tracker",
    [
        "CostTracker",
        "get_cost_tracker",
        "record_cost",
        "get_cost_summary",
    ],
)

# Checkpoint
_register("plugins.checkpoint", ["CheckpointMixin", "CheckpointStore"])

# Debugger (migrated from plugin to core in Phase 222)
_register(
    "core.orchestrator.flow_debugger",
    [
        "FlowDebugger",
        "debug_flow",
        "DebugEvent",
        "DebugEventType",
    ],
)

# Replay (migrated from plugin to core in Phase 222)
_register(
    "core.orchestrator.replayer",
    [
        "EventType",
        "TraceEvent",
        "ExecutionTrace",
        "TimeTravel",
        "get_time_travel",
    ],
)

# Clarification plugin extensions
_register("plugins.clarify", ["create_ask_user_tool"])

# Escalation
_register(
    "plugins.escalation",
    [
        "EscalationAction",
        "EscalationConfig",
        "EscalationRequest",
        "HITLEscalator",
        "get_escalator",
    ],
)

# Conversation (migrated from plugin to core in Phase 222)
_register(
    "core.services.conversation_branching",
    [
        "ConversationBranch",
        "ConversationCheckpoint",
        "get_branch",
        "delete_branch",
    ],
)

# Message hygiene (migrated from plugin to core in Phase 222)
_register(
    "core.services.message_hygiene",
    [
        "cleanup_orphaned_tool_results",
        "ensure_tool_call_ids",
        "validate_message_sequence",
        "sanitize_conversation",
        "deduplicate_messages",
        "truncate_messages",
        "get_conversation_stats",
    ],
)

# ReactFlow (migrated from plugin to core in Phase 222)
_register(
    "core.flows.reactflow_converter",
    [
        "flow_to_reactflow",
        "get_node_style",
        "export_flow_json",
        "get_flow_info",
    ],
)

# Flow editor (migrated from plugin to core in Phase 222)
_register(
    "core.flows.editor",
    [
        "NodeType",
        "FlowNode",
        "FlowEdge",
        "FlowDefinition",
        "FlowChange",
        "FlowValidationResult",
        "validate_flow",
        "apply_change",
        "generate_flow_code",
    ],
)

def __getattr__(name: str):
    """Lazy-load plugin symbols with deprecation warning."""
    if name in _PLUGIN_IMPORTS:
        module_path, attr_name = _PLUGIN_IMPORTS[name]
        _warnings.warn(
            f"Importing '{name}' from core.extensions is deprecated. "
            f"Import from {module_path} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            mod = _importlib.import_module(module_path)
            value = getattr(mod, attr_name)
        except (ImportError, AttributeError):
            value = _PluginStub(name)
        # Only cache successful imports in module globals.  PluginStubs must
        # NOT be cached because plugins are loaded after route modules import
        # from core.extensions.  If we cache a stub, later imports would keep
        # getting the stub even after the plugin is available.
        if not isinstance(value, _PluginStub):
            globals()[name] = value
        if name not in __all__:
            __all__.append(name)
        return value
    raise AttributeError(f"module 'core.extensions' has no attribute {name!r}")
