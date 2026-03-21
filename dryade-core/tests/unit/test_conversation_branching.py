# Tests for core.services.conversation_branching (migrated from plugin Phase 222).

"""Unit tests for conversation branching business logic."""

import pytest

from core.services.conversation_branching import (
    ConversationBranch,
    ConversationCheckpoint,
    _branches,
    delete_branch,
    get_branch,
)

@pytest.fixture(autouse=True)
def _clean_branches():
    """Clean up global _branches dict between tests."""
    _branches.clear()
    yield
    _branches.clear()

@pytest.mark.unit
class TestConversationBranch:
    """Test ConversationBranch creation and checkpoint management."""

    def test_create_branch(self):
        branch = ConversationBranch("conv-1")
        assert branch.conversation_id == "conv-1"
        assert branch.messages == []
        assert branch.state == {}

    def test_add_message(self):
        branch = ConversationBranch("conv-1")
        branch.add_message({"role": "user", "content": "Hello"})
        assert len(branch.messages) == 1
        assert branch.messages[0]["content"] == "Hello"

    def test_set_state(self):
        branch = ConversationBranch("conv-1")
        branch.set_state("key", "value")
        assert branch.state["key"] == "value"

    def test_checkpoint_saves_state(self):
        branch = ConversationBranch("conv-1")
        branch.add_message({"role": "user", "content": "Hello"})
        branch.set_state("step", 1)
        name = branch.checkpoint("cp1")
        assert name == "cp1"

        checkpoints = branch.list_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0]["name"] == "cp1"
        assert checkpoints[0]["message_count"] == 1

    def test_checkpoint_auto_names(self):
        branch = ConversationBranch("conv-1")
        name = branch.checkpoint()
        assert name == "checkpoint_0"

@pytest.mark.unit
class TestConversationUndo:
    """Test branch undo restores previous checkpoint state."""

    def test_undo_restores_checkpoint(self):
        branch = ConversationBranch("conv-1")
        branch.add_message({"role": "user", "content": "msg1"})
        branch.checkpoint("before")
        branch.add_message({"role": "user", "content": "msg2"})
        branch.checkpoint("after")

        assert len(branch.messages) == 2
        result = branch.undo(steps=1)
        assert result is True
        assert len(branch.messages) == 1
        assert branch.messages[0]["content"] == "msg1"

    def test_undo_fails_with_no_history(self):
        branch = ConversationBranch("conv-1")
        result = branch.undo()
        assert result is False

    def test_undo_too_many_steps_fails(self):
        branch = ConversationBranch("conv-1")
        branch.checkpoint("cp1")
        result = branch.undo(steps=5)
        assert result is False

    def test_restore_named_checkpoint(self):
        branch = ConversationBranch("conv-1")
        branch.add_message({"role": "user", "content": "msg1"})
        branch.checkpoint("early")
        branch.add_message({"role": "user", "content": "msg2"})
        branch.checkpoint("late")

        result = branch.restore("early")
        assert result is True
        assert len(branch.messages) == 1

    def test_restore_nonexistent_fails(self):
        branch = ConversationBranch("conv-1")
        assert branch.restore("nonexistent") is False

@pytest.mark.unit
class TestConversationBranchExploration:
    """Test what-if exploration creates child branches."""

    def test_branch_creates_independent_copy(self):
        branch = ConversationBranch("conv-1")
        branch.add_message({"role": "user", "content": "original"})
        branch.checkpoint("before_branch")

        alt = branch.branch("alt")
        alt.add_message({"role": "user", "content": "alternative"})

        # Original unchanged
        assert len(branch.messages) == 1
        # Alt has both messages
        assert len(alt.messages) == 2
        assert "branch:alt" in alt.conversation_id

    def test_branch_has_start_checkpoint(self):
        branch = ConversationBranch("conv-1")
        branch.checkpoint("cp1")
        alt = branch.branch("explore")
        checkpoints = alt.list_checkpoints()
        assert any("branch_start:explore" in cp["name"] for cp in checkpoints)

@pytest.mark.unit
class TestBranchRegistry:
    """Test get_branch and delete_branch module-level functions."""

    def test_get_branch_creates_new(self):
        branch = get_branch("conv-new")
        assert branch.conversation_id == "conv-new"

    def test_get_branch_returns_existing(self):
        b1 = get_branch("conv-1")
        b1.add_message({"role": "user", "content": "Hello"})
        b2 = get_branch("conv-1")
        assert len(b2.messages) == 1  # same instance

    def test_delete_branch_removes(self):
        get_branch("conv-del")
        assert delete_branch("conv-del") is True
        # After deletion, get_branch creates a new one
        branch = get_branch("conv-del")
        assert len(branch.messages) == 0

    def test_delete_nonexistent_returns_false(self):
        assert delete_branch("nonexistent") is False

@pytest.mark.unit
class TestConversationClear:
    """Test clear method."""

    def test_clear_resets_everything(self):
        branch = ConversationBranch("conv-1")
        branch.add_message({"role": "user", "content": "Hello"})
        branch.set_state("key", "val")
        branch.checkpoint("cp1")
        branch.clear()
        assert branch.messages == []
        assert branch.state == {}
        assert branch.list_checkpoints() == []
