"""Clarification State Preservation.

Preserves orchestration state across clarification turns so that when
the user answers a clarification question, the orchestrator can resume
with the original goal + user's answer merged.

Flow:
1. Orchestrator determines needs_clarification=True, returns clarification question
2. ClarificationRegistry stores the original goal, context, and question
3. User's answer arrives as a fresh request
4. Router detects pending clarification, merges original goal with answer
5. Re-dispatches through ORCHESTRATE handler with merged goal

Modeled after EscalationRegistry (core/orchestrator/escalation.py).
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    "PendingClarification",
    "ClarificationRegistry",
    "get_clarification_registry",
]

class PendingClarification(BaseModel):
    """A pending clarification waiting for the user's response.

    Attributes:
        clarification_id: Unique identifier for this clarification.
        conversation_id: The conversation this clarification belongs to.
        original_goal: The full user message that triggered clarification.
        original_context: The orchestration context dict (router_hints, etc.).
        clarification_question: What the orchestrator asked the user.
        created_at: When the clarification was created.
        ttl_seconds: Time-to-live in seconds (stale clarifications expire).
    """

    clarification_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    original_goal: str
    original_context: dict[str, Any] = Field(default_factory=dict)
    clarification_question: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: int = 1800  # 30 minutes

class ClarificationRegistry:
    """Registry for pending clarifications.

    Stores clarifications in memory, keyed by conversation_id.
    Only one pending clarification per conversation at a time.
    Expired clarifications are automatically cleared on access.
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingClarification] = {}

    def register(self, clarification: PendingClarification) -> None:
        """Register a new pending clarification.

        Replaces any existing clarification for the same conversation.
        """
        self._pending[clarification.conversation_id] = clarification
        logger.info(
            f"[CLARIFICATION] Registered pending clarification "
            f"{clarification.clarification_id} for conversation "
            f"{clarification.conversation_id}: "
            f"'{clarification.clarification_question[:80]}...'"
        )

    def get_pending(self, conversation_id: str) -> PendingClarification | None:
        """Get pending clarification for a conversation, if any.

        Returns None if no pending clarification exists or if the
        existing one has expired (TTL exceeded). Expired entries are
        automatically cleared.
        """
        pending = self._pending.get(conversation_id)
        if pending is None:
            return None

        # Check TTL expiry
        elapsed = (datetime.now(UTC) - pending.created_at).total_seconds()
        if elapsed > pending.ttl_seconds:
            logger.info(
                f"[CLARIFICATION] Expired clarification "
                f"{pending.clarification_id} for conversation "
                f"{conversation_id} (elapsed={elapsed:.0f}s, ttl={pending.ttl_seconds}s)"
            )
            self._pending.pop(conversation_id, None)
            return None

        return pending

    def clear(self, conversation_id: str) -> PendingClarification | None:
        """Clear and return the pending clarification for a conversation."""
        clarification = self._pending.pop(conversation_id, None)
        if clarification:
            logger.info(
                f"[CLARIFICATION] Cleared clarification "
                f"{clarification.clarification_id} for conversation "
                f"{conversation_id}"
            )
        return clarification

    def clear_all(self) -> None:
        """Clear all pending clarifications."""
        self._pending.clear()

# Global registry instance
_registry: ClarificationRegistry | None = None

def get_clarification_registry() -> ClarificationRegistry:
    """Get the global clarification registry."""
    global _registry
    if _registry is None:
        _registry = ClarificationRegistry()
    return _registry
