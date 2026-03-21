"""LLM Configuration Context Middleware.

Loads user's LLM configuration from database and sets it in contextvars
for the duration of the request. This enables all LLM call sites to access
user-specific settings without explicit parameter passing.

Runs after AuthMiddleware (requires request.state.user from JWT).
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import get_settings
from core.logs import get_logger

logger = get_logger(__name__)

class LLMContextMiddleware(BaseHTTPMiddleware):
    """Middleware to load user LLM config into contextvars.

    Extracts user_id from JWT (set by AuthMiddleware), loads their
    LLM configuration from database, and sets it in contextvars.

    Only active when llm_config_source is "database" or "auto".
    """

    def __init__(self, app, exclude: list[str] | None = None):
        """Initialize LLM context middleware.

        Args:
            app: FastAPI application
            exclude: Path prefixes to skip (e.g., health checks)
        """
        super().__init__(app)
        self.exclude = exclude or [
            "/health",
            "/api/health",
            "/ready",
            "/live",
            "/metrics",
            "/docs",
            "/openapi.json",
        ]
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        """Load user LLM config and set in contextvars.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # WebSocket connections set LLM context inside the handler
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        from core.providers.cost_context import (
            clear_cost_user_id,
            set_cost_user_id,
        )
        from core.providers.llm_context import (
            clear_user_llm_context,
            set_user_llm_context,
        )

        # Skip excluded paths
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude):
            return await call_next(request)

        # Get user from JWT (set by AuthMiddleware)
        user = getattr(request.state, "user", None)
        if not user:
            # No authenticated user - proceed without user config
            return await call_next(request)

        user_id = user.get("sub")
        if not user_id:
            logger.warning("JWT payload missing 'sub' claim")
            return await call_next(request)

        # Set cost context for ALL authenticated requests (regardless of
        # llm_config_source) so that DryadeCostCallback always has user_id.
        set_cost_user_id(user_id)

        # Skip LLM context loading if config source is "env"
        if self.settings.llm_config_source != "env":
            # Load user's LLM config from database
            try:
                from core.database.session import get_session
                from core.providers.user_config import get_user_llm_config

                with get_session() as db:
                    user_config = get_user_llm_config(user_id, db)

                if user_config.is_configured():
                    set_user_llm_context(user_config)
                    logger.debug(
                        f"Set LLM context for user {user_id}: "
                        f"provider={user_config.provider}, model={user_config.model}"
                    )
                else:
                    logger.debug(f"User {user_id} has no LLM config in database")

            except Exception as e:
                # Log but don't fail the request - will fall back to env vars
                logger.warning(f"Failed to load LLM config for user {user_id}: {e}")

        try:
            response = await call_next(request)
            return response
        finally:
            # Clean up contexts (good practice, though contextvars are request-scoped)
            clear_user_llm_context()
            clear_cost_user_id()

__all__ = ["LLMContextMiddleware"]
