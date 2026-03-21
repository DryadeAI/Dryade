"""Tracing Middleware.

Request span tracing for observability.
Target: ~60 LOC
"""

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware to add request tracing spans."""

    def __init__(self, app, service_name: str = "dryade-api"):
        """Initialize tracing middleware.

        Args:
            app: FastAPI application
            service_name: Name of the service for tracing
        """
        super().__init__(app)
        self.service_name = service_name
        self.enabled = True

    async def dispatch(self, request: Request, call_next):
        """Process request and add tracing spans.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response with tracing headers
        """
        if not self.enabled:
            return await call_next(request)

        # Generate or extract trace ID
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:16]
        parent_span = request.headers.get("X-Span-ID")

        # Store tracing info in request state
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.parent_span = parent_span

        # Record start time
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Add tracing headers to response
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id
        response.headers["X-Request-Duration-Ms"] = f"{duration_ms:.2f}"

        # Log span info (integrate with observability)
        self._log_span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span=parent_span,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response

    def _log_span(
        self,
        trace_id: str,
        span_id: str,
        parent_span: str | None,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ):
        """Log span information for tracing."""
        # This can be extended to integrate with OpenTelemetry or other tracing systems
        try:
            from core.observability.tracing import record_span

            record_span(
                trace_id=trace_id,
                span_id=span_id,
                parent_span=parent_span,
                operation=f"{method} {path}",
                status_code=status_code,
                duration_ms=duration_ms,
                service=self.service_name,
            )
        except ImportError:
            pass  # Tracing module not available
