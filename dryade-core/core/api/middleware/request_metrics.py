"""Request metrics middleware.

Records request latency into Prometheus histograms and keeps a small
in-memory buffer of recent requests for the metrics API endpoints.
"""

import contextlib
import re
import time
import uuid
from collections import deque
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.observability.metrics import record_request

# Keep a small history of recent requests for UI
_recent_requests = deque(maxlen=200)

_uuid_like = re.compile(r"^[0-9a-fA-F-]{8,}$")
_int_like = re.compile(r"^[0-9]+$")

def get_recent_requests(limit: int | None = None) -> list[dict]:
    """Return a snapshot of recent requests (newest first)."""
    if limit is None or limit >= len(_recent_requests):
        return list(_recent_requests)[::-1]
    return list(_recent_requests)[-limit:][::-1]

def normalize_path(path: str) -> str:
    """Reduce path cardinality by replacing ids with placeholders."""
    parts = [p for p in path.split("/") if p]
    norm_parts = []
    for p in parts:
        if _uuid_like.match(p) or _int_like.match(p):
            norm_parts.append(":id")
        else:
            norm_parts.append(p)
    return "/" + "/".join(norm_parts)

class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to record request latency and keep recent request buffer."""

    async def dispatch(self, request: Request, call_next):
        # WebSocket connections don't produce HTTP responses
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        start = time.time()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.time() - start
            path = normalize_path(request.url.path)
            method = request.method
            status = locals().get("status_code", 500)

            # Heuristic for mode based on endpoint
            raw_path = request.url.path
            if raw_path.startswith("/api/chat"):
                mode = "chat"
            elif raw_path.startswith("/api/plans"):
                mode = "planner"
            elif raw_path.startswith("/api/workflows"):
                mode = "workflow"
            elif raw_path.startswith("/api/health") or raw_path.startswith("/api/queue"):
                mode = "health"
            elif raw_path.startswith("/api/agents"):
                mode = "agents"
            elif raw_path.startswith("/api/metrics") or raw_path.startswith("/api/costs"):
                mode = "metrics"
            elif raw_path.startswith("/api/auth") or raw_path.startswith("/api/users"):
                mode = "auth"
            else:
                mode = "system"

            # Record to Prometheus
            # Do not block requests if metrics fail
            with contextlib.suppress(Exception):
                record_request(method, path, status, duration)

            # Record recent request entry for UI
            with contextlib.suppress(Exception):
                _recent_requests.append(
                    {
                        "id": str(uuid.uuid4()),
                        "timestamp": datetime.now(UTC).isoformat(),
                        "mode": mode,
                        "latency_ms": duration * 1000,
                        "tokens": 0,
                        "status": "success" if 200 <= status < 400 else "error",
                        "error_message": None,
                        "path": path,
                        "method": method,
                        "status_code": status,
                    }
                )
