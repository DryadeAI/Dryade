"""Tests for core.orchestrator.prompt_manager -- Phase 115.5.

Covers content-addressed IDs, activate/deactivate, rollback,
history filtering, and singleton.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from core.orchestrator.prompt_manager import (
    PromptVersionManager,
    get_prompt_manager,
)

def _make_manager() -> PromptVersionManager:
    """Create a PromptVersionManager with DB loading disabled."""
    with patch.object(PromptVersionManager, "_load_from_db"):
        mgr = PromptVersionManager()
    # Also disable DB persistence during tests
    mgr._persist_version = lambda v: None
    mgr._update_active_in_db = lambda vid, active: None
    return mgr

# ---- Content-addressed IDs --------------------------------------------------

class TestCreateVersion:
    def test_generates_content_hash(self):
        mgr = _make_manager()
        pv = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="Hello world",
            created_by="test",
        )
        expected = hashlib.sha256(b"Hello world").hexdigest()[:16]
        assert pv.version_id == expected

    def test_different_content_different_id(self):
        mgr = _make_manager()
        v1 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="Content A",
            created_by="test",
        )
        v2 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="Content B",
            created_by="test",
        )
        assert v1.version_id != v2.version_id

    def test_same_content_same_id(self):
        """Content-addressed: same content produces same version_id."""
        mgr = _make_manager()
        v1 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="Same content",
            created_by="test",
        )
        v2 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="Same content",
            created_by="test",
        )
        assert v1.version_id == v2.version_id

# ---- Activate / Deactivate --------------------------------------------------

class TestActivate:
    def test_sets_active(self):
        mgr = _make_manager()
        pv = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="test content",
            created_by="test",
        )
        mgr.activate(pv.version_id)
        active = mgr.get_active("system", "frontier")
        assert active is not None
        assert active.version_id == pv.version_id
        assert active.is_active is True

    def test_deactivates_previous(self):
        mgr = _make_manager()
        v1 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="version 1",
            created_by="test",
        )
        mgr.activate(v1.version_id)

        v2 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="version 2",
            created_by="test",
        )
        mgr.activate(v2.version_id)

        # v1 should no longer be active
        assert v1.is_active is False
        # v2 should be the active one
        active = mgr.get_active("system", "frontier")
        assert active.version_id == v2.version_id

    def test_nonexistent_returns_false(self):
        mgr = _make_manager()
        result = mgr.activate("nonexistent_version_id")
        assert result is False

# ---- Rollback ---------------------------------------------------------------

class TestRollback:
    def test_rollback_to_parent(self):
        mgr = _make_manager()
        v1 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="original",
            created_by="test",
        )
        mgr.activate(v1.version_id)

        v2 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="updated",
            created_by="test",
            parent_version_id=v1.version_id,
        )
        mgr.activate(v2.version_id)

        # Rollback should restore v1
        rolled_back = mgr.rollback("system", "frontier")
        assert rolled_back is not None
        assert rolled_back.version_id == v1.version_id
        assert rolled_back.is_active is True

    def test_rollback_no_parent_returns_none(self):
        mgr = _make_manager()
        v1 = mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="root version",
            created_by="test",
        )
        mgr.activate(v1.version_id)

        result = mgr.rollback("system", "frontier")
        assert result is None

# ---- Get active / history ---------------------------------------------------

class TestGetActive:
    def test_nonexistent_returns_none(self):
        mgr = _make_manager()
        result = mgr.get_active("unknown_key", "unknown_tier")
        assert result is None

class TestGetHistory:
    def test_returns_ordered(self):
        mgr = _make_manager()
        now = datetime.now(UTC)

        # Create versions with different timestamps
        for i in range(3):
            pv = mgr.create_version(
                prompt_key="system",
                model_tier="frontier",
                content=f"version {i}",
                created_by="test",
            )
            # Manually set created_at for predictable ordering
            pv.created_at = now - timedelta(minutes=10 - i)

        history = mgr.get_history("system")
        assert len(history) == 3
        # Should be reverse chronological (newest first)
        for i in range(len(history) - 1):
            assert history[i].created_at >= history[i + 1].created_at

    def test_filters_by_tier(self):
        mgr = _make_manager()
        mgr.create_version(
            prompt_key="system",
            model_tier="frontier",
            content="frontier version",
            created_by="test",
        )
        mgr.create_version(
            prompt_key="system",
            model_tier="weak",
            content="weak version",
            created_by="test",
        )

        frontier_history = mgr.get_history("system", model_tier="frontier")
        assert len(frontier_history) == 1
        assert frontier_history[0].model_tier == "frontier"

        weak_history = mgr.get_history("system", model_tier="weak")
        assert len(weak_history) == 1
        assert weak_history[0].model_tier == "weak"

# ---- Singleton ---------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        import core.orchestrator.prompt_manager as mod

        mod._prompt_manager = None
        with patch.object(PromptVersionManager, "_load_from_db"):
            m1 = get_prompt_manager()
            m2 = get_prompt_manager()
        assert m1 is m2
        # Cleanup
        mod._prompt_manager = None
