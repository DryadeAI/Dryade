"""Tests for per-action autonomy levels (Phase 115.3).

Covers:
- Default autonomy levels for all 12 self-mod tools
- Unknown action defaults to APPROVE
- Custom action map overrides
- LeashConfig integration with action_autonomy
- Existing presets unaffected
"""

import pytest

from core.autonomous.leash import (
    LEASH_CONSERVATIVE,
    LEASH_PERMISSIVE,
    LEASH_STANDARD,
    LeashConfig,
)
from core.orchestrator.action_autonomy import (
    ActionAutonomy,
    AutonomyLevel,
    reset_action_autonomy,
)

@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the ActionAutonomy singleton between tests."""
    reset_action_autonomy()
    yield
    reset_action_autonomy()

def test_default_autonomy_levels():
    """Verify default action_map has correct levels for all 12 tools."""
    a = ActionAutonomy()

    # Read-only: AUTO
    assert a.check_autonomy("search_capabilities") == AutonomyLevel.AUTO
    assert a.check_autonomy("memory_search") == AutonomyLevel.AUTO

    # Memory edits: CONFIRM
    assert a.check_autonomy("memory_insert") == AutonomyLevel.CONFIRM
    assert a.check_autonomy("memory_replace") == AutonomyLevel.CONFIRM
    assert a.check_autonomy("memory_rethink") == AutonomyLevel.CONFIRM

    # System changes: APPROVE
    assert a.check_autonomy("self_improve") == AutonomyLevel.APPROVE
    assert a.check_autonomy("create_agent") == AutonomyLevel.APPROVE
    assert a.check_autonomy("create_tool") == AutonomyLevel.APPROVE
    assert a.check_autonomy("modify_config") == AutonomyLevel.APPROVE
    assert a.check_autonomy("add_mcp_server") == AutonomyLevel.APPROVE
    assert a.check_autonomy("remove_mcp_server") == AutonomyLevel.APPROVE
    assert a.check_autonomy("configure_mcp_server") == AutonomyLevel.APPROVE

def test_unknown_action_defaults_to_approve():
    """Unknown tool name returns APPROVE (safest default)."""
    a = ActionAutonomy()
    assert a.check_autonomy("unknown_tool") == AutonomyLevel.APPROVE
    assert a.check_autonomy("") == AutonomyLevel.APPROVE
    assert a.check_autonomy("definitely_not_a_tool") == AutonomyLevel.APPROVE

def test_custom_action_map():
    """Create ActionAutonomy with custom map, verify override works."""
    custom = ActionAutonomy(
        action_map={
            "self_improve": AutonomyLevel.AUTO,  # Override from APPROVE to AUTO
            "memory_insert": AutonomyLevel.APPROVE,  # Override from CONFIRM to APPROVE
        }
    )
    assert custom.check_autonomy("self_improve") == AutonomyLevel.AUTO
    assert custom.check_autonomy("memory_insert") == AutonomyLevel.APPROVE
    # Unknown tool still defaults to APPROVE
    assert custom.check_autonomy("create_agent") == AutonomyLevel.APPROVE

def test_leash_config_with_action_autonomy():
    """Create LeashConfig with action_autonomy set, verify check_action_autonomy."""
    autonomy = ActionAutonomy()
    lc = LeashConfig(action_autonomy=autonomy)
    assert lc.action_autonomy is not None
    assert lc.check_action_autonomy("memory_search") == AutonomyLevel.AUTO
    assert lc.check_action_autonomy("self_improve") == AutonomyLevel.APPROVE
    assert lc.check_action_autonomy("memory_insert") == AutonomyLevel.CONFIRM

def test_leash_config_without_action_autonomy():
    """Default LeashConfig has action_autonomy=None, check returns None."""
    lc = LeashConfig()
    assert lc.action_autonomy is None
    assert lc.check_action_autonomy("memory_search") is None
    assert lc.check_action_autonomy("self_improve") is None

def test_existing_presets_unchanged():
    """LEASH_CONSERVATIVE, LEASH_STANDARD, LEASH_PERMISSIVE all have action_autonomy=None."""
    assert LEASH_CONSERVATIVE.action_autonomy is None
    assert LEASH_STANDARD.action_autonomy is None
    assert LEASH_PERMISSIVE.action_autonomy is None

    # Verify presets still have their expected constraint values
    assert LEASH_CONSERVATIVE.max_tokens == 10000
    assert LEASH_CONSERVATIVE.confidence_threshold == 0.95
    assert LEASH_STANDARD.max_tokens == 50000
    assert LEASH_PERMISSIVE.max_tokens == 200000
    assert LEASH_PERMISSIVE.confidence_threshold == 0.70
