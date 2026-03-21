"""Shared utilities for orchestrate-mode handler modules.

Leaf dependency: imports only from core.extensions.events, never from
sibling handler files.  All tier handlers import from here.

Contents:
- VISIBILITY_DENY denylist (Phase 92, ADR-002 Sub-Decision B)
- _should_emit() visibility gate
- Event helper factories (_emit_escalation, _emit_reasoning, _emit_resource_suggestion)
- INSTANT_SYSTEM_PROMPT constant (Phase 90)
"""

from core.extensions.events import ChatEvent

# =============================================================================
# Visibility Filter -- Denylist (Phase 92, ADR-002 Sub-Decision B)
# Gates which events reach the SSE stream based on user preference.
# Events are always generated internally (for logging, cost tracking, etc.)
# but only emitted to the user if NOT in the deny set.
#
# Denylist semantics: new EventTypes are visible by default. To hide a
# new internal event, add it explicitly to the deny set for the level(s)
# where it should be hidden.
# =============================================================================

VISIBILITY_DENY: dict[str, set[str]] = {
    "minimal": {
        # Deny everything except: complete, error, escalation, cancel_ack
        "token",
        "thinking",
        "reasoning",
        "agent_start",
        "agent_complete",
        "tool_start",
        "tool_result",
        "node_start",
        "node_complete",
        "flow_start",
        "flow_complete",
        "plan_preview",
        "plan_edit",
        "progress",
        "artifact",
        "agent_retry",
        "agent_fallback",
        "resource_suggestion",
        "state_export",
        "state_conflict",
        "cost_update",
        "memory_update",
        "clarify",
        "clarify_response",
    },
    "named-steps": {
        # Deny noisy/internal events not useful for named-step visibility
        "tool_start",
        "tool_result",
        "node_start",
        "node_complete",
        "flow_start",
        "flow_complete",
        "resource_suggestion",
        "state_export",
        "state_conflict",
        "cost_update",
        "memory_update",
        "clarify",
        "clarify_response",
    },
    "full-transparency": set(),  # Empty = deny nothing = allow all
}

def _should_emit(event_type: str, visibility: str) -> bool:
    """Check if an event should be emitted based on visibility level.

    Uses denylist semantics: events are visible by default.
    New event types added in the future are VISIBLE unless
    explicitly added to a deny set.
    """
    deny_set = VISIBILITY_DENY.get(visibility, VISIBILITY_DENY["named-steps"])
    return event_type not in deny_set

# =============================================================================
# Local Event Helpers for ORCHESTRATE mode
# =============================================================================

def _emit_escalation(
    question: str,
    task_context: str | None = None,
    has_auto_fix: bool = False,
    auto_fix_description: str | None = None,
) -> ChatEvent:
    """Emit escalation event - inline question in chat per user decision.

    Args:
        question: The question to ask the user
        task_context: Context about what task failed
        has_auto_fix: Whether an automatic fix is available (user can just say "yes")
        auto_fix_description: Human-readable description of what the auto-fix does
    """
    return ChatEvent(
        type="escalation",
        content=question,
        metadata={
            "task_context": task_context,
            "inline": True,  # Per user decision: inline in chat, not modal
            "has_auto_fix": has_auto_fix,
            "auto_fix_description": auto_fix_description,
        },
    )

def _emit_reasoning(
    summary: str, detailed: str | None = None, visibility: str = "summary"
) -> ChatEvent:
    """Emit reasoning event with configurable visibility per user decision."""
    return ChatEvent(
        type="reasoning",
        content=summary,
        metadata={
            "detailed": detailed,
            "visibility": visibility,  # "summary" | "detailed" | "hidden"
            "expandable": detailed is not None,
        },
    )

def _emit_resource_suggestion(resources: list[dict], agent_name: str) -> ChatEvent:
    """Emit MCP resource suggestion - per user decision: suggest but confirm."""
    return ChatEvent(
        type="resource_suggestion",
        content=f"I found {len(resources)} relevant resources. Use them?",
        metadata={
            "agent_name": agent_name,
            "resources": resources,
            "requires_confirmation": True,
        },
    )

# =============================================================================
# INSTANT Tier Constants (Phase 90)
# =============================================================================

INSTANT_SYSTEM_PROMPT = (
    "You are Dryade, an AI orchestration assistant. "
    "Respond naturally to the user. Do not use JSON format. "
    "Do not discuss agents or tools unless asked about your capabilities."
)
