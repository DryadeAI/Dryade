"""API response models package.

Provides standard response patterns for consistent API documentation
and client handling.
"""

from core.api.models.openapi import (
    STANDARD_RESPONSES,
    response_with_errors,
)
from core.api.models.responses import (
    ErrorResponse,
    HTTPStatus,
    PaginatedResponse,
    Pagination,
    SuccessResponse,
)

__all__ = [
    "ErrorResponse",
    "HTTPStatus",
    "Pagination",
    "PaginatedResponse",
    "SuccessResponse",
    "STANDARD_RESPONSES",
    "response_with_errors",
]
