# Migrated from plugins/starter/conversation/branching.py into core (Phase 222).

"""Conversation Undo/Branching.

Enables "what-if" exploration without losing progress.
Inspired by Orchestral AI's context.undo() and context.copy() patterns.

Features:
- Checkpoint-based undo (revert to previous states)
- Conversation branching (explore alternatives)
- State snapshot and restore

Target: ~80 LOC
"""

import copy
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

class ConversationCheckpoint(BaseModel):
    """Snapshot of conversation state at a point in time."""

    name: str
    state: dict[str, Any]
    messages: list[dict]
    timestamp: str

    class Config:
        """Pydantic configuration for ConversationCheckpoint."""

        extra = "allow"

class ConversationBranch:
    """Enable undo and branching for experimentation.

    Usage:
        branch = ConversationBranch("conv-123")

        # Add messages
        branch.add_message({"role": "user", "content": "Hello"})
        branch.checkpoint("after_greeting")

        branch.add_message({"role": "assistant", "content": "Hi there!"})

        # Undo last interaction
        branch.undo()

        # Or branch for alternative exploration
        alt_branch = branch.branch("alternative")
    """

    def __init__(self, conversation_id: str):
        """Initialize conversation branching manager.

        Args:
            conversation_id: Unique identifier for the conversation.
        """
        self.conversation_id = conversation_id
        self._history: list[ConversationCheckpoint] = []
        self._messages: list[dict] = []
        self._state: dict[str, Any] = {}

    @property
    def messages(self) -> list[dict]:
        """Get current messages."""
        return self._messages

    @property
    def state(self) -> dict[str, Any]:
        """Get current state."""
        return self._state

    def add_message(self, message: dict):
        """Add a message to the conversation."""
        self._messages.append(message)

    def set_state(self, key: str, value: Any):
        """Set a state value."""
        self._state[key] = value

    def checkpoint(self, name: str | None = None) -> str:
        """Save current state as checkpoint.

        Args:
            name: Optional checkpoint name

        Returns:
            Checkpoint name
        """
        checkpoint_name = name or f"checkpoint_{len(self._history)}"
        self._history.append(
            ConversationCheckpoint(
                name=checkpoint_name,
                state=copy.deepcopy(self._state),
                messages=copy.deepcopy(self._messages),
                timestamp=datetime.now(UTC).isoformat(),
            )
        )
        return checkpoint_name

    def undo(self, steps: int = 1) -> bool:
        """Undo last N interactions.

        Args:
            steps: Number of steps to undo

        Returns:
            True if undo succeeded, False if not enough history
        """
        if steps > len(self._history):
            return False

        if len(self._history) > steps:
            target = self._history[-(steps + 1)]
        elif self._history:
            target = self._history[0]
        else:
            return False

        self._state = copy.deepcopy(target.state)
        self._messages = copy.deepcopy(target.messages)
        self._history = self._history[:-(steps)]
        return True

    def restore(self, checkpoint_name: str) -> bool:
        """Restore to a named checkpoint.

        Args:
            checkpoint_name: Name of checkpoint to restore

        Returns:
            True if restore succeeded
        """
        for i, cp in enumerate(self._history):
            if cp.name == checkpoint_name:
                self._state = copy.deepcopy(cp.state)
                self._messages = copy.deepcopy(cp.messages)
                self._history = self._history[: i + 1]
                return True
        return False

    def branch(self, name: str) -> "ConversationBranch":
        """Create a branch for alternative exploration.

        Args:
            name: Branch name

        Returns:
            New ConversationBranch with copied state
        """
        new_branch = ConversationBranch(f"{self.conversation_id}:branch:{name}")
        new_branch._history = copy.deepcopy(self._history)
        new_branch._messages = copy.deepcopy(self._messages)
        new_branch._state = copy.deepcopy(self._state)
        new_branch.checkpoint(f"branch_start:{name}")
        return new_branch

    def list_checkpoints(self) -> list[dict]:
        """List all checkpoints.

        Returns:
            List of checkpoint info dicts
        """
        return [
            {"name": cp.name, "timestamp": cp.timestamp, "message_count": len(cp.messages)}
            for cp in self._history
        ]

    def clear(self):
        """Clear all history and state."""
        self._history.clear()
        self._messages.clear()
        self._state.clear()

# -----------------------------------------------------------------------------
# Conversation manager for multi-conversation support
# -----------------------------------------------------------------------------

_branches: dict[str, ConversationBranch] = {}

def get_branch(conversation_id: str) -> ConversationBranch:
    """Get or create a conversation branch."""
    if conversation_id not in _branches:
        _branches[conversation_id] = ConversationBranch(conversation_id)
    return _branches[conversation_id]

def delete_branch(conversation_id: str) -> bool:
    """Delete a conversation branch."""
    if conversation_id in _branches:
        del _branches[conversation_id]
        return True
    return False
