"""Per-action autonomy levels for self-modification tools.

Phase 115.3: Provides granular autonomy control over individual self-mod tools.
ActionAutonomy maps tool names to AutonomyLevel (auto/confirm/approve), allowing
layered safety on top of LeashConfig without replacing existing presets.

AutonomyLevel semantics:
- AUTO: Execute without asking (read-only tools, search).
- CONFIRM: Execute and log for audit trail (memory edits).
- APPROVE: Full approval workflow via PendingEscalation (system changes).
"""

import threading
from enum import Enum

from pydantic import BaseModel, Field

__all__ = [
    "AutonomyLevel",
    "ActionAutonomy",
    "get_action_autonomy",
    "reset_action_autonomy",
]

class AutonomyLevel(str, Enum):
    """Autonomy level for a self-modification action."""

    AUTO = "auto"
    CONFIRM = "confirm"
    APPROVE = "approve"

class ActionAutonomy(BaseModel):
    """Per-action autonomy map for self-modification tools.

    Maps tool names to AutonomyLevel. Unknown tools default to APPROVE (safest).
    This is additive to LeashConfig -- conservative/standard/permissive presets
    still work; ActionAutonomy adds a finer-grained layer on top.
    """

    action_map: dict[str, AutonomyLevel] = Field(
        default_factory=lambda: {
            # Read-only: always auto
            "search_capabilities": AutonomyLevel.AUTO,
            "memory_search": AutonomyLevel.AUTO,
            # Memory edits: confirm by default (execute + audit log)
            "memory_insert": AutonomyLevel.CONFIRM,
            "memory_replace": AutonomyLevel.CONFIRM,
            "memory_rethink": AutonomyLevel.CONFIRM,
            # System changes: require full approval
            # Phase 167: "create" replaces "self_improve", "create_agent", "create_tool"
            "create": AutonomyLevel.APPROVE,
            "memory_delete": AutonomyLevel.CONFIRM,
            "modify_config": AutonomyLevel.APPROVE,
            "add_mcp_server": AutonomyLevel.APPROVE,
            "remove_mcp_server": AutonomyLevel.APPROVE,
            "configure_mcp_server": AutonomyLevel.APPROVE,
            # Factory actions (Phase 119.4)
            "factory_create_agent": AutonomyLevel.APPROVE,
            "factory_create_tool": AutonomyLevel.APPROVE,
            "factory_create_skill": AutonomyLevel.CONFIRM,
            "factory_update_artifact": AutonomyLevel.CONFIRM,
            "factory_delete_artifact": AutonomyLevel.APPROVE,
            "factory_test_artifact": AutonomyLevel.AUTO,
        }
    )

    def check_autonomy(self, action_type: str) -> AutonomyLevel:
        """Get autonomy level for an action. Unknown actions default to APPROVE."""
        return self.action_map.get(action_type, AutonomyLevel.APPROVE)

# ---------------------------------------------------------------------------
# Singleton with double-checked locking (same pattern as capability_registry.py)
# ---------------------------------------------------------------------------

_action_autonomy: ActionAutonomy | None = None
_action_autonomy_lock = threading.Lock()

def get_action_autonomy() -> ActionAutonomy:
    """Get or create singleton ActionAutonomy instance."""
    global _action_autonomy
    if _action_autonomy is None:
        with _action_autonomy_lock:
            if _action_autonomy is None:
                _action_autonomy = ActionAutonomy()
    return _action_autonomy

def reset_action_autonomy() -> None:
    """Reset the singleton action autonomy (for testing)."""
    global _action_autonomy
    _action_autonomy = None
