"""Conversation service -- shared business logic for conversation history.

Extracted from core/api/routes/chat.py to break the circular import chain
where core/orchestrator/router.py imported from the API layer:

    core/orchestrator/router.py -> core/api/routes/chat.py -> core/orchestrator/router.py

The function has no API-layer dependencies (only uses database models and
session), so it belongs in a service layer accessible to both the API routes
and the core orchestrator.
"""

import logging
import uuid

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def get_recent_history(
    conversation_id: str, limit: int = 5, db: Session | None = None
) -> list[dict[str, str]]:
    """Get recent conversation history.

    Args:
        conversation_id: Conversation ID
        limit: Maximum number of recent messages to return (default: 5, max: 100)
        db: Database session (optional - creates one if not provided)

    Returns:
        List of message dicts with role and content keys
    """
    from core.database.models import Message as DBMessage
    from core.database.session import get_session

    # Validate limit
    if limit > 100:
        raise ValueError("Limit cannot exceed 100")

    # Validate conversation_id format (UUID)
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise ValueError("Invalid conversation_id format (must be UUID)") from e

    # Create session if not provided (allows direct calls outside FastAPI DI)
    own_session = db is None
    if own_session:
        # get_session() is a context manager, use it properly
        session_cm = get_session()
        db = session_cm.__enter__()

    try:
        # Query database for recent messages
        messages = (
            db.query(DBMessage)
            .filter(DBMessage.conversation_id == conversation_id)
            .order_by(DBMessage.created_at.desc())
            .limit(limit)
            .all()
        )

        # Return in chronological order (oldest first)
        messages = list(reversed(messages))

        # Format as role/content pairs (no timestamp)
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.role in ("user", "assistant")  # Filter out system messages
        ]
    finally:
        if own_session:
            session_cm.__exit__(None, None, None)
