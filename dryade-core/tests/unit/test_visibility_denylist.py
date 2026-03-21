"""Tests for visibility filter denylist (ADR-002 Sub-Decision B).

Verifies strict behavioral equivalence between the old allowlist
(VISIBILITY_FILTER) and the new denylist (VISIBILITY_DENY).
"""

import pytest

from core.orchestrator.handlers._utils import (
    VISIBILITY_DENY,
    _should_emit,
)

# Complete EventType universe from core/extensions/events.py (28 types)
ALL_EVENT_TYPES = [
    "token",
    "thinking",
    "tool_start",
    "tool_result",
    "agent_start",
    "agent_complete",
    "node_start",
    "node_complete",
    "flow_start",
    "flow_complete",
    "clarify",
    "clarify_response",
    "escalation",
    "reasoning",
    "resource_suggestion",
    "state_export",
    "state_conflict",
    "complete",
    "error",
    "plan_preview",
    "plan_edit",
    "progress",
    "cost_update",
    "artifact",
    "agent_retry",
    "agent_fallback",
    "cancel_ack",
    "memory_update",
]

# Old allowlist (frozen reference for equivalence verification)
OLD_ALLOWLIST = {
    "minimal": {"complete", "error", "escalation", "cancel_ack"},
    "named-steps": {
        "complete",
        "error",
        "escalation",
        "cancel_ack",
        "agent_start",
        "agent_complete",
        "progress",
        "agent_retry",
        "agent_fallback",
        "plan_preview",
        "plan_edit",
        "artifact",
        "thinking",
        "reasoning",
        "token",  # tokens are answer content, not internal noise
    },
    "full-transparency": set(),  # empty = allow all
}

VISIBILITY_LEVELS = ["minimal", "named-steps", "full-transparency"]

def _old_should_emit(event_type: str, visibility: str) -> bool:
    """Reference implementation of the OLD allowlist-based filter."""
    if visibility == "full-transparency":
        return True
    allowed = OLD_ALLOWLIST.get(visibility, OLD_ALLOWLIST["named-steps"])
    return event_type in allowed

# ---------------------------------------------------------------------------
# Test 1: Behavioral equivalence matrix (28 types x 3 levels = 84 combos)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "event_type,visibility",
    [(et, vis) for vis in VISIBILITY_LEVELS for et in ALL_EVENT_TYPES],
)
def test_equivalence_matrix(event_type: str, visibility: str):
    """New denylist _should_emit matches old allowlist for every combination."""
    expected = _old_should_emit(event_type, visibility)
    actual = _should_emit(event_type, visibility)
    assert actual == expected, (
        f"Mismatch for ({event_type!r}, {visibility!r}): old={expected}, new={actual}"
    )

# ---------------------------------------------------------------------------
# Test 2: EventType count guard
# ---------------------------------------------------------------------------

def test_all_event_types_covered():
    """Ensure ALL_EVENT_TYPES list stays in sync with events.py (28 types)."""
    assert len(ALL_EVENT_TYPES) == 28

# ---------------------------------------------------------------------------
# Test 3: Unknown visibility defaults to named-steps
# ---------------------------------------------------------------------------

def test_unknown_visibility_defaults_to_named_steps():
    """Unknown visibility level falls back to named-steps deny set."""
    # complete is NOT in named-steps deny set -> should be visible
    assert _should_emit("complete", "nonexistent_level") is True
    # token is NOT in named-steps deny set -> should be visible
    assert _should_emit("token", "nonexistent_level") is True

# ---------------------------------------------------------------------------
# Test 4: New event types are visible by default (key behavioral improvement)
# ---------------------------------------------------------------------------

def test_new_event_type_visible_by_default():
    """Future event types not in any deny set are visible at all levels.

    This is the key behavioral improvement of the denylist approach:
    new EventTypes added to events.py are visible by default rather
    than silently dropped.
    """
    assert _should_emit("future_event_type", "named-steps") is True
    assert _should_emit("future_event_type", "full-transparency") is True
    assert _should_emit("future_event_type", "minimal") is True

# ---------------------------------------------------------------------------
# Test 5: Deny set structure
# ---------------------------------------------------------------------------

def test_deny_set_structure():
    """Verify deny set sizes match expected complements."""
    assert VISIBILITY_DENY["full-transparency"] == set()
    assert len(VISIBILITY_DENY["minimal"]) == 24
    assert len(VISIBILITY_DENY["named-steps"]) == 13

# ---------------------------------------------------------------------------
# Test 6: Minimal allows essentials
# ---------------------------------------------------------------------------

def test_minimal_allows_essentials():
    """Essential events (complete, error, escalation, cancel_ack) pass minimal."""
    for et in ("complete", "error", "escalation", "cancel_ack"):
        assert _should_emit(et, "minimal") is True, f"{et} should pass minimal"

# ---------------------------------------------------------------------------
# Test 7: Full transparency allows all
# ---------------------------------------------------------------------------

def test_full_transparency_allows_all():
    """Every known event type passes full-transparency."""
    for et in ALL_EVENT_TYPES:
        assert _should_emit(et, "full-transparency") is True, f"{et} should pass full-transparency"
