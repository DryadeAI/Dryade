# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.
"""Internal HTTP API for Plugin Manager push operations.

This module provides a minimal FastAPI application running on a separate
port (default 9471, localhost only) that Plugin Manager uses to push
signed allowlists to core.

Security model:
- Bound to 127.0.0.1 only -- PM must be on the same machine or use SSH tunnel.
- No bearer token or additional auth -- the Ed25519 signature on the allowlist
  payload IS the authentication.
- No docs/openapi endpoints exposed.

Usage:
    In core/api/main.py lifespan:

        from core.ee.internal_api import start_internal_api, set_hot_reload_callback
        set_hot_reload_callback(my_reload_function)
        internal_task = asyncio.create_task(start_internal_api())
"""

import inspect
import logging
import time
from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from core.ee.allowlist_ee import verify_and_load_allowlist, write_allowlist_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level hot-reload callback
# ---------------------------------------------------------------------------

_hot_reload_callback: Callable | None = None

# Last allowlist update info (for GET /api/plugins/update-status polling)
_last_allowlist_update: dict | None = None

def set_hot_reload_callback(callback: Callable) -> None:
    """Set the callback invoked after a successful allowlist push.

    The callback is called (with no arguments) after a valid allowlist
    has been written to disk. Typically triggers plugin re-discovery
    in core/api/main.py.

    Args:
        callback: Callable to invoke on successful push.
    """
    global _hot_reload_callback
    _hot_reload_callback = callback

def get_last_allowlist_update() -> dict | None:
    """Get the last allowlist update info for status polling.

    Returns:
        Dict with 'version' and 'timestamp' keys, or None if no update received.
    """
    return _last_allowlist_update

# ---------------------------------------------------------------------------
# FastAPI app (minimal -- no docs, no redoc, no openapi)
# ---------------------------------------------------------------------------

internal_app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

@internal_app.post("/v1/allowlist")
async def receive_allowlist(request: Request) -> JSONResponse:
    """Receive a signed allowlist from Plugin Manager.

    Validates the Ed25519 signature via TOFU-pinned key, writes the
    allowlist to disk, and triggers hot-reload if a callback is set.

    Returns:
        200 {"status": "accepted"} on success.
        400 {"status": "rejected"} on invalid signature or payload
            (no details -- security).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"status": "rejected"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    result = verify_and_load_allowlist(body)
    if result is None:
        return JSONResponse(
            {"status": "rejected"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not write_allowlist_file(body):
        logger.error("Allowlist verified but failed to write to disk")
        return JSONResponse(
            {"status": "rejected"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    logger.info("Allowlist accepted: %d plugins", len(result.plugins))

    # Trigger hot-reload callback (supports both sync and async callbacks)
    if _hot_reload_callback is not None:
        try:
            result = _hot_reload_callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Hot-reload callback failed")

    return JSONResponse({"status": "accepted"})

@internal_app.post("/internal/allowlist-updated")
async def allowlist_updated(request: Request) -> JSONResponse:
    """Notification endpoint: PM calls this after successfully applying a new allowlist.

    PM writes the allowlist file first (primary delivery), then calls this endpoint
    as an optimization to trigger immediate hot-reload rather than waiting for the
    AllowlistWatchdog's polling interval.

    This is a fire-and-forget notification from PM's perspective — PM logs a warning
    if this fails but does NOT consider the allowlist delivery failed.

    Security: Only accessible on localhost:9471. No additional auth needed since
    the actual allowlist verification happened via Ed25519 signature during push.

    Request body (optional):
        {"version": <u64>}

    Returns:
        200 {"status": "ok"} always
    """
    global _last_allowlist_update

    version = None
    try:
        body = await request.json()
        version = body.get("version")
    except Exception:
        pass  # Body is optional

    timestamp = time.time()
    _last_allowlist_update = {
        "version": version,
        "timestamp": timestamp,
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
    }

    logger.info("PM notified allowlist update (version=%s) — triggering hot-reload", version)

    # Trigger hot-reload callback (same as when PM pushes via /v1/allowlist)
    if _hot_reload_callback is not None:
        try:
            result = _hot_reload_callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Hot-reload callback failed during allowlist-updated notification")

    return JSONResponse({"status": "ok"})

# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

async def start_internal_api(port: int = 9471, host: str = "127.0.0.1") -> None:
    """Start the internal API server.

    Args:
        port: Port to listen on (default 9471).
        host: Host to bind to (default 127.0.0.1). Use 0.0.0.0 in Docker.
    """
    import uvicorn

    config = uvicorn.Config(
        internal_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()

async def stop_internal_api() -> None:
    """Stop the internal API server.

    Placeholder for graceful shutdown coordination.
    """
    pass
