"""Standard response models for API consistency.

Provides reusable patterns for all API responses, enabling consistent
client handling and comprehensive OpenAPI documentation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from core.exceptions import DryadeError  # noqa: F401 - used in from_exception docstring

T = TypeVar("T")

class ErrorCode:
    """Standard error codes for API responses.

    Error codes follow the pattern: CATEGORY_NNN where:
    - CATEGORY is the error domain (VALIDATION, NOT_FOUND, AUTH, etc.)
    - NNN is a numeric identifier within that domain

    These codes enable clients to handle specific error types programmatically.
    """

    # Validation (4xx - client errors)
    VALIDATION_ERROR = "VALIDATION_001"
    MISSING_FIELD = "VALIDATION_002"
    INVALID_FORMAT = "VALIDATION_003"
    INVALID_INPUT = "VALIDATION_004"

    # Not Found (404)
    RESOURCE_NOT_FOUND = "NOT_FOUND_001"
    WORKFLOW_NOT_FOUND = "NOT_FOUND_002"
    AGENT_NOT_FOUND = "NOT_FOUND_003"
    PLAN_NOT_FOUND = "NOT_FOUND_004"
    CONVERSATION_NOT_FOUND = "NOT_FOUND_005"
    KNOWLEDGE_NOT_FOUND = "NOT_FOUND_006"
    PLUGIN_NOT_FOUND = "NOT_FOUND_007"

    # Authentication (401)
    UNAUTHORIZED = "AUTH_001"
    TOKEN_EXPIRED = "AUTH_002"
    INVALID_CREDENTIALS = "AUTH_003"

    # Authorization (403)
    ACCESS_DENIED = "AUTHZ_001"
    PERMISSION_DENIED = "AUTHZ_002"
    RESOURCE_LOCKED = "AUTHZ_003"

    # Conflict (409)
    RESOURCE_EXISTS = "CONFLICT_001"
    VERSION_CONFLICT = "CONFLICT_002"
    STATE_CONFLICT = "CONFLICT_003"

    # Server (5xx)
    INTERNAL_ERROR = "SERVER_001"
    SERVICE_UNAVAILABLE = "SERVER_002"
    TIMEOUT = "SERVER_003"
    DATABASE_ERROR = "SERVER_004"
    EXECUTION_ERROR = "SERVER_005"

    # Domain-specific
    WORKFLOW_EXECUTION_FAILED = "WORKFLOW_001"
    AGENT_EXECUTION_FAILED = "AGENT_001"
    PLUGIN_LOAD_FAILED = "PLUGIN_001"
    KNOWLEDGE_QUERY_FAILED = "KNOWLEDGE_001"

class HTTPStatus(IntEnum):
    """Standard HTTP status codes used in the API."""

    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    REQUEST_TIMEOUT = 408
    CONFLICT = 409
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503

class ErrorResponse(BaseModel):
    """Standard error response format for all API errors.

    Used by centralized exception handlers to ensure consistent
    error format across all endpoints.

    Attributes:
        error: Human-readable error message
        type: Error type identifier (validation_error, not_found, etc.)
        code: Machine-readable error code from ErrorCode class
        suggestion: Actionable suggestion for resolution
        detail: Additional error details for debugging
        timestamp: UTC timestamp when the error occurred
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Resource not found",
                "type": "not_found",
                "code": "NOT_FOUND_001",
                "suggestion": "Verify the resource ID and check if it was deleted.",
                "detail": "Workflow with ID 123 does not exist",
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    error: str = Field(..., description="Human-readable error message")
    type: str = Field(..., description="Error type identifier (validation_error, not_found, etc.)")
    code: str | None = Field(None, description="Machine-readable error code (e.g., NOT_FOUND_001)")
    suggestion: str | None = Field(None, description="Actionable suggestion for resolution")
    detail: str | None = Field(None, description="Additional error details for debugging")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the error occurred",
    )

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        error_type: str = "error",
        code: str | None = None,
        suggestion: str | None = None,
    ) -> ErrorResponse:
        """Create ErrorResponse from an exception.

        If the exception is a DryadeError (or subclass), extracts structured
        error information including code, suggestion, and context.

        Args:
            exc: The exception to convert
            error_type: Error type identifier (default: "error")
            code: Override error code (uses exception's code if not provided)
            suggestion: Override suggestion (uses exception's suggestion if not provided)

        Returns:
            ErrorResponse with extracted or provided error information
        """
        # Check if exception has to_dict (DryadeError and subclasses)
        if hasattr(exc, "to_dict") and callable(exc.to_dict):
            data = exc.to_dict()
            return cls(
                error=data.get("error", str(exc)),
                type=error_type,
                code=code or data.get("code"),
                suggestion=suggestion or data.get("suggestion"),
                detail=str(data.get("context")) if data.get("context") else None,
            )

        # Standard exception fallback
        return cls(
            error=str(exc),
            type=error_type,
            code=code,
            suggestion=suggestion,
        )

class SuccessResponse(BaseModel):
    """Standard success response for operations without specific return data.

    Used for DELETE operations and other actions that return simple confirmations.
    """

    model_config = ConfigDict(
        json_schema_extra={"example": {"success": True, "message": "Resource deleted successfully"}}
    )

    success: bool = Field(True, description="Indicates operation completed successfully")
    message: str | None = Field(None, description="Optional message describing the result")

class Pagination(BaseModel):
    """Pagination parameters for list endpoints.

    Use as a dependency in route handlers to parse query parameters.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"offset": 0, "limit": 20}})

    offset: int = Field(0, ge=0, description="Number of items to skip (0-based)")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of items to return (1-100)")

class PaginatedResponse[T](BaseModel):
    """Generic paginated response wrapper for list endpoints.

    Usage:
        class UserListResponse(PaginatedResponse[User]):
            pass

    Or directly in response_model:
        response_model=PaginatedResponse[User]
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"items": [], "total": 100, "offset": 0, "limit": 20, "has_more": True}
        }
    )

    items: list[T] = Field(..., description="List of items for the current page")
    total: int = Field(..., ge=0, description="Total number of items across all pages")
    offset: int = Field(..., ge=0, description="Current offset (number of items skipped)")
    limit: int = Field(..., ge=1, description="Maximum items per page")
    has_more: bool = Field(..., description="True if more pages are available after this one")

    @classmethod
    def create(cls, items: list[T], total: int, offset: int, limit: int) -> PaginatedResponse[T]:
        """Factory method to create paginated response with computed has_more.

        Args:
            items: List of items for current page
            total: Total count across all pages
            offset: Current offset
            limit: Page size limit

        Returns:
            PaginatedResponse with has_more computed
        """
        return cls(
            items=items,
            total=total,
            offset=offset,
            limit=limit,
            has_more=(offset + len(items)) < total,
        )
