"""Request-scoped Cost User ID Context.

Uses contextvars for thread/async-safe propagation of the authenticated
user_id through the request lifecycle so that the litellm cost callback
and ThinkingProvider cost handlers can tag records with the real user.

Usage:
    # In middleware (at request start):
    set_cost_user_id(user_id)

    # In any cost recording call site:
    uid = get_cost_user_id()

    # In middleware (at request end):
    clear_cost_user_id()
"""

from contextvars import ContextVar

# Context variable for request-scoped cost attribution user ID
_cost_user_id: ContextVar[str | None] = ContextVar("cost_user_id", default=None)

def set_cost_user_id(user_id: str) -> None:
    """Set the user ID for cost attribution in the current request context.

    Called by LLMContextMiddleware and WebSocket handler after
    authenticating the user.

    Args:
        user_id: Authenticated user's ID (JWT 'sub' claim)
    """
    _cost_user_id.set(user_id)

def get_cost_user_id() -> str | None:
    """Get the user ID for cost attribution in the current request context.

    Returns:
        User ID if set by middleware/handler, None otherwise.
    """
    return _cost_user_id.get()

def clear_cost_user_id() -> None:
    """Clear the cost user ID context.

    Called by middleware/handler at end of request for cleanup.
    Not strictly necessary (contextvars are request-scoped),
    but good practice for explicit cleanup.
    """
    _cost_user_id.set(None)

__all__ = [
    "set_cost_user_id",
    "get_cost_user_id",
    "clear_cost_user_id",
]
