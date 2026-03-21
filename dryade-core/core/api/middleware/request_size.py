"""Request Size Middleware.

Enforces maximum request body size to prevent abuse.
Target: ~40 LOC
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce maximum request body size."""

    def __init__(self, app, max_size_mb: float | None = None):
        """Initialize request size middleware.

        Args:
            app: FastAPI application
            max_size_mb: Maximum request body size in MB (default: 10MB)
        """
        super().__init__(app)
        self.max_size_bytes = int((max_size_mb or 10) * 1024 * 1024)
        self.enabled = True

    async def dispatch(self, request: Request, call_next):
        """Process request and check body size.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response or 413 if body too large
        """
        if not self.enabled:
            return await call_next(request)

        # Check Content-Length header
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": "Request body too large",
                            "max_size_mb": self.max_size_bytes / (1024 * 1024),
                            "received_mb": size / (1024 * 1024),
                        },
                    )
            except ValueError:
                pass  # Invalid Content-Length, let it proceed

        return await call_next(request)
