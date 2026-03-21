"""Context Hierarchy Extension.

5-level scope hierarchy: conversation → session → project → user → global.
Target: ~150 LOC
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

class ContextScope(str, Enum):
    """Context scope levels (most specific to most general)."""

    CONVERSATION = "conversation"  # Single conversation
    SESSION = "session"  # User session (can span conversations)
    PROJECT = "project"  # Project-level (model, workspace)
    USER = "user"  # User preferences
    GLOBAL = "global"  # System-wide defaults

@dataclass
class ContextValue:
    """A value in the context store."""

    value: Any
    scope: ContextScope
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

class ContextStore:
    """Hierarchical context storage.

    Values are stored at specific scopes and retrieved with cascade:
    conversation → session → project → user → global

    Usage:
        context = ContextStore()
        context.set("model.path", "/path/to/model", ContextScope.PROJECT)
        path = context.get("model.path")  # Finds value at PROJECT scope
    """

    def __init__(self):
        """Initialize an empty hierarchical context store."""
        self._stores: dict[ContextScope, dict[str, ContextValue]] = {
            scope: {} for scope in ContextScope
        }
        self._lock = threading.RLock()

    def set(
        self,
        key: str,
        value: Any,
        scope: ContextScope = ContextScope.CONVERSATION,
        metadata: dict | None = None,
    ):
        """Set a value at a specific scope."""
        with self._lock:
            self._stores[scope][key] = ContextValue(
                value=value, scope=scope, metadata=metadata or {}
            )

    def get(self, key: str, default: Any = None, scope: ContextScope | None = None) -> Any:
        """Get a value, cascading through scopes if not found.

        If scope is specified, only check that scope.
        Otherwise, cascade from CONVERSATION → GLOBAL.
        """
        with self._lock:
            if scope:
                # Direct scope lookup
                ctx = self._stores[scope].get(key)
                return ctx.value if ctx else default

            # Cascade through scopes
            for s in ContextScope:
                ctx = self._stores[s].get(key)
                if ctx:
                    return ctx.value

            return default

    def get_with_scope(self, key: str, default: Any = None) -> tuple:
        """Get value and its scope."""
        with self._lock:
            for scope in ContextScope:
                ctx = self._stores[scope].get(key)
                if ctx:
                    return ctx.value, scope
            return default, None

    def delete(self, key: str, scope: ContextScope | None = None):
        """Delete a value from a specific scope or all scopes."""
        with self._lock:
            if scope:
                self._stores[scope].pop(key, None)
            else:
                for s in ContextScope:
                    self._stores[s].pop(key, None)

    def clear_scope(self, scope: ContextScope):
        """Clear all values at a specific scope."""
        with self._lock:
            self._stores[scope].clear()

    def list_keys(self, scope: ContextScope | None = None) -> list:
        """List all keys at a scope or across all scopes."""
        with self._lock:
            if scope:
                return list(self._stores[scope].keys())
            # Unique keys across all scopes
            all_keys = set()
            for store in self._stores.values():
                all_keys.update(store.keys())
            return list(all_keys)

    def export(self, scope: ContextScope | None = None) -> dict[str, Any]:
        """Export context as a dictionary."""
        with self._lock:
            if scope:
                return {key: ctx.value for key, ctx in self._stores[scope].items()}
            # Export all with scope info
            result = {}
            for s in ContextScope:
                for key, ctx in self._stores[s].items():
                    if key not in result:  # First found wins (cascade order)
                        result[key] = {
                            "value": ctx.value,
                            "scope": s.value,
                        }
            return result

# Decorator for scope-aware functions
def context_scope(scope: ContextScope):
    """Decorator to export tool results to specific context scope.

    Usage:
        @context_scope(ContextScope.SESSION)
        @export_state(session_id="mbse.session_id")
        def open_model(path: str) -> dict:
            ...
    """

    def decorator(func: Callable) -> Callable:
        func._context_scope = scope
        return func

    return decorator

# Global context instance
_context: ContextStore | None = None
_context_lock = threading.Lock()

def get_context() -> ContextStore:
    """Get or create global context store."""
    global _context
    with _context_lock:
        if _context is None:
            _context = ContextStore()
    return _context

def set_context(key: str, value: Any, scope: ContextScope = ContextScope.CONVERSATION):
    """Convenience function to set context."""
    get_context().set(key, value, scope)

def get_context_value(key: str, default: Any = None) -> Any:
    """Convenience function to get context."""
    return get_context().get(key, default)
