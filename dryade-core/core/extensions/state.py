"""State Export/Inject Protocol.

Enables cross-tool state propagation without hardcoding field names.
This is the ONE thing CrewAI doesn't do that we need.

Features:
- State export/inject decorators for tools
- Multi-value state tracking (supports multiple values per key)
- State conflict detection and resolution
- Pause-and-clarify flow for ambiguous state

Target: ~200 LOC
"""

from collections.abc import Callable
from datetime import UTC
from functools import wraps
from typing import Any

from pydantic import BaseModel, Field

def export_state(**mappings: str) -> Callable:
    """Declare what state a tool exports.

    Usage:
        @export_state(session_id="mbse.session_id")
        def open_model(path: str) -> dict:
            return {"session_id": "sess_123", "status": "ok"}

    Result dict will have: {"_exports": {"mbse.session_id": "sess_123"}}
    """

    def decorator(func: Callable) -> Callable:
        func._state_exports = mappings

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, dict):
                exports = {}
                for context_key, result_key in mappings.items():
                    if result_key in result and result[result_key] is not None:
                        exports[context_key] = result[result_key]
                if exports:
                    result["_exports"] = exports
            return result

        return wrapper

    return decorator

def requires_state(*keys: str) -> Callable:
    """Declare what state a tool requires.

    Usage:
        @requires_state("mbse.session_id")
        def query_model(session_id: str = None, kind: str = "Function"):
            ...

    The orchestrator auto-fills session_id from context.
    """

    def decorator(func: Callable) -> Callable:
        func._state_requires = list(keys)
        return func

    return decorator

def resolve_state(func: Callable, args: dict, context: dict) -> dict:
    """Auto-fill arguments from context based on @requires_state.

    Called by orchestrator before tool execution.
    """
    state_requires = getattr(func, "_state_requires", [])
    if not state_requires:
        return args

    updated = args.copy()
    for context_key in state_requires:
        param_name = context_key.split(".")[-1]
        value = context.get(context_key)
        if value is not None and param_name not in updated:
            updated[param_name] = value

    return updated

def extract_exports(results: list[dict]) -> dict[str, Any]:
    """Extract all exported state from tool results.

    Called by orchestrator after each tool execution.
    """
    state = {}
    for result in results:
        if isinstance(result, dict) and "_exports" in result:
            for key, value in result["_exports"].items():
                if value is not None:
                    state[key] = value
    return state

def get_state_metadata(func: Callable) -> dict[str, Any]:
    """Get state metadata from a decorated function."""
    return {
        "exports": getattr(func, "_state_exports", {}),
        "requires": getattr(func, "_state_requires", []),
    }

def has_state_decorators(func: Callable) -> bool:
    """Check if function has state decorators."""
    return hasattr(func, "_state_exports") or hasattr(func, "_state_requires")

# -----------------------------------------------------------------------------
# Multi-Value State Tracking & Conflict Resolution
# -----------------------------------------------------------------------------

class StateValue(BaseModel):
    """A single state value with its source metadata."""

    value: Any
    source: str  # Tool/agent that exported this value
    label: str | None = None  # Human-readable label
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __hash__(self):
        """Hash based on value and source for set operations."""
        return hash((str(self.value), self.source))

class StateConflict(BaseModel):
    """Represents a state conflict that needs user resolution."""

    state_key: str
    candidates: list[StateValue]
    required_by: str | None = None  # Tool/agent that needs this value
    resolved: bool = False
    selected_value: Any | None = None

class MultiValueStateStore:
    """State store that tracks multiple values per key.

    Instead of overwriting values, this store keeps track of all
    exported values and their sources. When a tool requires a value
    and multiple candidates exist, it triggers conflict resolution.
    """

    def __init__(self):
        """Initialize an empty multi-value state store."""
        self._store: dict[str, list[StateValue]] = {}
        self._pending_conflicts: dict[str, StateConflict] = {}
        self._resolved_selections: dict[str, Any] = {}

    def export(
        self,
        key: str,
        value: Any,
        source: str,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Export a value for a state key.

        Multiple values can be exported for the same key from different sources.
        """
        from datetime import datetime

        state_value = StateValue(
            value=value,
            source=source,
            label=label or f"{source}: {str(value)[:20]}",
            timestamp=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )

        if key not in self._store:
            self._store[key] = []

        # Avoid duplicates from same source
        self._store[key] = [sv for sv in self._store[key] if sv.source != source]
        self._store[key].append(state_value)

    def get(self, key: str) -> Any | None:
        """Get a value for a state key.

        Returns:
            - The selected value if conflict was resolved
            - The single value if only one exists
            - None if no values or unresolved conflict
        """
        # Check if user resolved this conflict
        if key in self._resolved_selections:
            return self._resolved_selections[key]

        values = self._store.get(key, [])
        if len(values) == 1:
            return values[0].value
        elif len(values) == 0:
            return None
        else:
            # Multiple values - conflict needs resolution
            return None

    def check_conflict(self, key: str, required_by: str | None = None) -> StateConflict | None:
        """Check if there's a conflict for a state key.

        Returns StateConflict if multiple values exist and no selection was made.
        """
        # Already resolved
        if key in self._resolved_selections:
            return None

        values = self._store.get(key, [])
        if len(values) <= 1:
            return None

        # Create conflict
        conflict = StateConflict(state_key=key, candidates=values, required_by=required_by)
        self._pending_conflicts[key] = conflict
        return conflict

    def resolve_conflict(self, key: str, selected_value: Any) -> bool:
        """Resolve a state conflict by selecting a value.

        Args:
            key: State key with conflict
            selected_value: The value selected by user

        Returns:
            True if conflict was resolved, False if no conflict existed
        """
        if key not in self._store:
            return False

        # Validate selected_value is one of the candidates
        values = self._store.get(key, [])
        valid = any(sv.value == selected_value for sv in values)
        if not valid:
            return False

        self._resolved_selections[key] = selected_value
        if key in self._pending_conflicts:
            self._pending_conflicts[key].resolved = True
            self._pending_conflicts[key].selected_value = selected_value

        return True

    def has_pending_conflict(self, key: str) -> bool:
        """Check if there's a pending (unresolved) conflict for a key."""
        if key in self._resolved_selections:
            return False
        return len(self._store.get(key, [])) > 1

    def get_all_conflicts(self) -> list[StateConflict]:
        """Get all pending conflicts."""
        conflicts = []
        for key, values in self._store.items():
            if len(values) > 1 and key not in self._resolved_selections:
                conflicts.append(StateConflict(state_key=key, candidates=values))
        return conflicts

    def clear(self, key: str | None = None) -> None:
        """Clear state values and resolutions."""
        if key:
            self._store.pop(key, None)
            self._resolved_selections.pop(key, None)
            self._pending_conflicts.pop(key, None)
        else:
            self._store.clear()
            self._resolved_selections.clear()
            self._pending_conflicts.clear()

    def to_dict(self) -> dict[str, Any]:
        """Export state store as dictionary."""
        return {key: self.get(key) for key in self._store}

# Global state store instance
_global_state_store: MultiValueStateStore | None = None

def get_state_store() -> MultiValueStateStore:
    """Get or create the global state store."""
    global _global_state_store
    if _global_state_store is None:
        _global_state_store = MultiValueStateStore()
    return _global_state_store

def reset_state_store() -> None:
    """Reset the global state store (for testing)."""
    global _global_state_store
    _global_state_store = MultiValueStateStore()

# -----------------------------------------------------------------------------
# State Resolution Helpers for Orchestrator
# -----------------------------------------------------------------------------

def resolve_state_with_conflicts(
    func: Callable, args: dict, store: MultiValueStateStore | None = None
) -> tuple[dict, list[StateConflict]]:
    """Resolve state requirements, detecting conflicts.

    Args:
        func: Function with @requires_state decorator
        args: Current arguments
        store: State store (uses global if not provided)

    Returns:
        Tuple of (resolved_args, list of conflicts)
    """
    store = store or get_state_store()
    state_requires = getattr(func, "_state_requires", [])

    if not state_requires:
        return args, []

    updated = args.copy()
    conflicts = []

    for context_key in state_requires:
        param_name = context_key.split(".")[-1]

        # Skip if already provided
        if param_name in updated and updated[param_name] is not None:
            continue

        # Check for conflict
        conflict = store.check_conflict(
            context_key, required_by=getattr(func, "__name__", "unknown")
        )
        if conflict:
            conflicts.append(conflict)
            continue

        # Get single value
        value = store.get(context_key)
        if value is not None:
            updated[param_name] = value

    return updated, conflicts

def export_state_to_store(
    result: dict, source: str, store: MultiValueStateStore | None = None
) -> dict[str, Any]:
    """Export state from a tool result to the store.

    Args:
        result: Tool result with potential _exports
        source: Source tool name
        store: State store (uses global if not provided)

    Returns:
        Dictionary of exported state keys and values
    """
    store = store or get_state_store()
    exports = {}

    if isinstance(result, dict) and "_exports" in result:
        for key, value in result["_exports"].items():
            if value is not None:
                store.export(key, value, source)
                exports[key] = value

    return exports
