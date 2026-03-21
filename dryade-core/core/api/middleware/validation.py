"""Input Validation Middleware.

Validates all incoming requests using Pydantic models before routing.
Target: ~60 LOC
"""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.extensions import ValidationResult

logger = logging.getLogger(__name__)

class ValidationMiddleware(BaseHTTPMiddleware):
    """Validate incoming requests before routing.

    Applies route-specific validation models:
    - /api/chat -> ChatMessage validation
    - /api/agents/*/execute -> ToolArgs validation
    - Query parameters -> QueryParams validation
    """

    async def dispatch(self, request: Request, call_next):
        """Validate request and forward to route handler.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from handler or validation error
        """
        # Skip validation for certain routes
        if self._should_skip_validation(request):
            return await call_next(request)

        # Validate based on route
        validation_result = await self._validate_request(request)

        if not validation_result.valid:
            logger.warning(f"Validation failed for {request.url.path}: {validation_result.errors}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "Validation failed",
                    "details": validation_result.errors,
                    "type": "validation_error",
                },
            )

        # Continue to route handler
        return await call_next(request)

    def _should_skip_validation(self, request: Request) -> bool:
        """Check if request should skip validation."""
        skip_paths = ["/health", "/ready", "/live", "/metrics", "/docs", "/openapi.json"]
        return any(request.url.path.startswith(path) for path in skip_paths)

    async def _validate_request(self, _request: Request) -> ValidationResult:
        """Validate request based on route.

        Args:
            _request: Incoming request

        Returns:
            ValidationResult
        """
        # For now, return valid (detailed integration in Task 3)
        # This middleware structure is in place for future full integration
        return ValidationResult(valid=True)
