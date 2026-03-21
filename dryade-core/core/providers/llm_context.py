"""Request-scoped LLM Configuration Context.

Uses contextvars for thread/async-safe propagation of user LLM config
through the request lifecycle. Middleware sets the context at request start,
and all LLM call sites can retrieve it without explicit parameter passing.

Usage:
    # In middleware (at request start):
    set_user_llm_context(user_config)

    # In any LLM call site:
    config = get_user_llm_context()
    if config and config.is_configured():
        # Use user's database config
    else:
        # Fall back to environment

    # In middleware (at request end):
    clear_user_llm_context()
"""

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.providers.user_config import UserLLMConfig

# Context variable for request-scoped user LLM configuration
_user_llm_context: ContextVar["UserLLMConfig | None"] = ContextVar("user_llm_context", default=None)

def set_user_llm_context(config: "UserLLMConfig") -> None:
    """Set the user LLM config for the current request context.

    Called by LLMContextMiddleware after loading config from database.

    Args:
        config: User's LLM configuration loaded from database
    """
    _user_llm_context.set(config)

def get_user_llm_context() -> "UserLLMConfig | None":
    """Get the user LLM config for the current request context.

    Returns:
        UserLLMConfig if set by middleware, None otherwise.
        Check config.is_configured() to verify user has configured LLM.
    """
    return _user_llm_context.get()

def clear_user_llm_context() -> None:
    """Clear the user LLM context.

    Called by middleware at end of request for cleanup.
    Not strictly necessary (contextvars are request-scoped),
    but good practice for explicit cleanup.
    """
    _user_llm_context.set(None)

__all__ = [
    "set_user_llm_context",
    "get_user_llm_context",
    "clear_user_llm_context",
]
