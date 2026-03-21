"""OpenAPI helpers for consistent error documentation.

Provides standard response definitions for use in FastAPI route decorators.
"""

from typing import Any

from core.api.models.responses import ErrorResponse

# Standard HTTP error responses for OpenAPI documentation.
# Use in route decorators: responses={**STANDARD_RESPONSES, 404: ...}
STANDARD_RESPONSES: dict[int, dict[str, Any]] = {
    400: {
        "model": ErrorResponse,
        "description": "Bad request - invalid input parameters or validation failed",
    },
    401: {
        "model": ErrorResponse,
        "description": "Unauthorized - authentication required or token invalid",
    },
    403: {
        "model": ErrorResponse,
        "description": "Forbidden - insufficient permissions for this operation",
    },
    404: {"model": ErrorResponse, "description": "Not found - requested resource does not exist"},
    408: {
        "model": ErrorResponse,
        "description": "Request timeout - operation took too long to complete",
    },
    409: {
        "model": ErrorResponse,
        "description": "Conflict - resource already exists or constraint violation",
    },
    500: {
        "model": ErrorResponse,
        "description": "Internal server error - unexpected error occurred",
    },
    503: {
        "model": ErrorResponse,
        "description": "Service unavailable - dependency down or system overloaded",
    },
}

def response_with_errors(
    *error_codes: int, **custom_responses: dict[str, Any]
) -> dict[int, dict[str, Any]]:
    """Build responses dict by merging standard errors with custom responses.

    Usage:
        @router.get(
            "/items/{id}",
            responses=response_with_errors(404, 503)
        )

        @router.post(
            "/items",
            responses=response_with_errors(400, 409, custom_201={"description": "Created"})
        )

    Args:
        *error_codes: HTTP status codes to include from STANDARD_RESPONSES
        **custom_responses: Additional responses with key format "custom_{code}"

    Returns:
        Dict suitable for FastAPI responses parameter
    """
    result: dict[int, dict[str, Any]] = {}

    # Add requested standard responses
    for code in error_codes:
        if code in STANDARD_RESPONSES:
            result[code] = STANDARD_RESPONSES[code]

    # Add custom responses (key format: custom_201, custom_202, etc.)
    for key, value in custom_responses.items():
        if key.startswith("custom_"):
            try:
                code = int(key.replace("custom_", ""))
                result[code] = value
            except ValueError:
                pass  # Ignore malformed keys

    return result
