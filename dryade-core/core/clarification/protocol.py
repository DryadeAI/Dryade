"""Core Clarification Protocol - Mid-execution user interaction.

Provides basic clarification models and functions for human-in-the-loop
operations in autonomous execution.

Features:
- Structured clarification requests with optional choices
- Async user response handling
- Timeout with configurable defaults

The clarify plugin extends this with:
- Structured forms (Team/Enterprise)
- Preference memory (Team/Enterprise)
- CrewAI tool wrapper

Usage:
    from core.clarification import request_clarification, ClarificationResponse

    response = await request_clarification(
        conversation_id="conv_123",
        question="Which environment should I deploy to?",
        options=["staging", "production"],
        timeout=300.0
    )
"""

import asyncio
import threading
from typing import Any

from pydantic import BaseModel, Field


class ClarificationRequest(BaseModel):
    """Request for user clarification."""

    question: str
    options: list[str] = Field(default_factory=list)
    required: bool = True
    default: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)

class ClarificationResponse(BaseModel):
    """User response to clarification."""

    value: str
    selected_option: int | None = None

# Global storage for pending clarifications
_pending_clarifications: dict[str, asyncio.Event] = {}
_clarification_responses: dict[str, ClarificationResponse] = {}
_clarification_lock = threading.Lock()

async def request_clarification(
    conversation_id: str,
    question: str,
    options: list[str] | None = None,
    timeout: float = 300.0,
    default: str | None = None,
) -> str:
    """Request clarification from user.

    Emits a clarify event and waits for user response.

    Args:
        conversation_id: Current conversation ID
        question: Question to ask the user
        options: Optional list of choices
        timeout: Max wait time in seconds (default 5 minutes)
        default: Default value if timeout (optional)

    Returns:
        User's response string

    Raises:
        TimeoutError: If user doesn't respond in time and no default provided
    """
    from core.extensions.events import emit_clarify

    # Create event for this conversation
    event = asyncio.Event()
    with _clarification_lock:
        _pending_clarifications[conversation_id] = event

    # The caller should yield this event to the frontend
    emit_clarify(question, options)

    # Wait for response (OUTSIDE the lock to avoid blocking other conversations)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        with _clarification_lock:
            response = _clarification_responses.pop(conversation_id, None)
        if response:
            return response.value
        elif default is not None:
            return default
        else:
            raise TimeoutError("No response received")
    except TimeoutError as e:
        if default is not None:
            return default
        raise TimeoutError(f"User did not respond within {timeout}s") from e
    finally:
        with _clarification_lock:
            _pending_clarifications.pop(conversation_id, None)

def submit_clarification(conversation_id: str, response: ClarificationResponse) -> bool:
    """Submit user's clarification response.

    Called by API route when user responds.

    Args:
        conversation_id: Conversation ID
        response: User's response

    Returns:
        True if a pending request was found, False otherwise
    """
    with _clarification_lock:
        if conversation_id not in _pending_clarifications:
            return False

        _clarification_responses[conversation_id] = response
        _pending_clarifications[conversation_id].set()
        return True

def has_pending_clarification(conversation_id: str) -> bool:
    """Check if there's a pending clarification for a conversation."""
    with _clarification_lock:
        return conversation_id in _pending_clarifications

def cancel_clarification(conversation_id: str) -> bool:
    """Cancel a pending clarification request."""
    with _clarification_lock:
        if conversation_id in _pending_clarifications:
            _pending_clarifications[conversation_id].set()
            _pending_clarifications.pop(conversation_id, None)
            _clarification_responses.pop(conversation_id, None)
            return True
        return False
