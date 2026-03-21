"""Core Clarification Protocol.

Basic clarification models and functions for human-in-the-loop operations.
This is the core protocol - plugins can extend with structured forms,
preference memory, and other enhanced features.
"""

from .protocol import (
    ClarificationRequest,
    ClarificationResponse,
    cancel_clarification,
    has_pending_clarification,
    request_clarification,
    submit_clarification,
)

__all__ = [
    "ClarificationRequest",
    "ClarificationResponse",
    "request_clarification",
    "submit_clarification",
    "has_pending_clarification",
    "cancel_clarification",
]
