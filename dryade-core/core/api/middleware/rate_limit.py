"""Rate Limiting Middleware.

Simple in-memory rate limiting with tiered support.
For production, use Redis-based rate limiting.
Target: ~40 LOC
"""

import os
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiting middleware."""

    def __init__(
        self,
        app,
        requests_per_minute: int | None = None,
        pro_rpm: int | None = None,
        admin_rpm: int | None = None,
    ):
        """Initialize rate limit middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Default rate limit per client (default: 60)
            pro_rpm: Rate limit for pro-tier users (default: 300)
            admin_rpm: Rate limit for admin-tier users (default: 1000)
        """
        super().__init__(app)
        self.default_rpm = requests_per_minute or 60
        self.pro_rpm = pro_rpm or 300
        self.admin_rpm = admin_rpm or 1000
        self.requests: dict = defaultdict(list)
        # Check environment variable for rate limiting (default: enabled)
        self.enabled = os.getenv("DRYADE_RATE_LIMIT_ENABLED", "true").lower() != "false"

    async def dispatch(self, request: Request, call_next):
        """Process request and enforce rate limits.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response with rate limit headers
        """
        # WebSocket connections are long-lived; skip rate limiting
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        if not self.enabled:
            return await call_next(request)

        # Get client identifier (prefer API key, fallback to IP)
        auth_header = request.headers.get("Authorization", "")
        auth_parts = auth_header.split()
        auth_token = auth_parts[-1][:32] if auth_parts else None

        client_id = (
            request.headers.get("X-API-Key")
            or auth_token
            or (request.client.host if request.client else "unknown")
        )

        # Get rate limit for this client (could be tier-based)
        rpm = self._get_rate_limit(request)

        # Clean old requests (older than 60 seconds)
        now = time.time()
        self.requests[client_id] = [t for t in self.requests[client_id] if now - t < 60]

        # Check limit
        if len(self.requests[client_id]) >= rpm:
            retry_after = 60 - int(now - self.requests[client_id][0])
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        # Record request
        self.requests[client_id].append(now)

        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rpm)
        response.headers["X-RateLimit-Remaining"] = str(rpm - len(self.requests[client_id]))
        response.headers["X-RateLimit-Reset"] = str(int(now) + 60)

        return response

    def _get_rate_limit(self, request: Request) -> int:
        """Get rate limit for request (tier-based)."""
        # Check if user has a tier (from auth)
        user = getattr(request.state, "user", None)
        if user:
            role = user.get("role", "user")
            if role == "admin":
                return self.admin_rpm  # Admin tier
            elif role == "pro":
                return self.pro_rpm  # Pro tier

        return self.default_rpm  # Free tier
