"""A2A Protocol Server Endpoints.

Exposes Dryade agents to external A2A-compliant orchestrators:
  - GET /.well-known/agent.json — Public discovery (A2A AgentCard)
  - GET /.well-known/agent-card.json — Alias for discovery (v0.3.0)
  - POST /a2a — JSON-RPC 2.0 handler (authenticated)

Discovery is excluded from auth middleware. The /a2a endpoint requires
Bearer token authentication via the standard AuthMiddleware.

JSON-RPC errors always return HTTP 200 per the A2A spec — the error
is conveyed in the JSON-RPC response body.
"""

import json
import logging
from collections.abc import AsyncGenerator
from json import JSONDecodeError

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.a2a.executor import (
    build_a2a_agent_card,
    handle_message_send,
    handle_message_stream,
    handle_tasks_cancel,
    handle_tasks_get,
)
from core.a2a.models import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    jsonrpc_error,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Discovery router — public, excluded from auth middleware
# ------------------------------------------------------------------
discovery_router = APIRouter(tags=["a2a-discovery"])

# ------------------------------------------------------------------
# JSON-RPC router — requires auth (NOT in exclude list)
# ------------------------------------------------------------------
jsonrpc_router = APIRouter(tags=["a2a"])

# ------------------------------------------------------------------
# Discovery endpoints
# ------------------------------------------------------------------

@discovery_router.get("/.well-known/agent.json")
async def get_agent_card(request: Request) -> JSONResponse:
    """Return the A2A AgentCard for this Dryade instance.

    Public endpoint (no auth required). External orchestrators use this
    to discover available agents and their capabilities.
    """
    base_url = str(request.base_url).rstrip("/")
    card = build_a2a_agent_card(base_url)
    return JSONResponse(content=card)

@discovery_router.get("/.well-known/agent-card.json")
async def get_agent_card_v03(request: Request) -> JSONResponse:
    """Return the A2A AgentCard (v0.3.0 path alias).

    Same as /.well-known/agent.json — both paths are specified
    in the A2A protocol for backward compatibility.
    """
    base_url = str(request.base_url).rstrip("/")
    card = build_a2a_agent_card(base_url)
    return JSONResponse(content=card)

# ------------------------------------------------------------------
# JSON-RPC endpoint
# ------------------------------------------------------------------

# Dispatch table for synchronous methods
_METHOD_HANDLERS = {
    "message/send": handle_message_send,
    "tasks/get": handle_tasks_get,
    "tasks/cancel": handle_tasks_cancel,
}

async def _sse_generator(params: dict, request_id: str | int) -> AsyncGenerator[bytes, None]:
    """Yield SSE events from A2A message/stream handler."""
    try:
        async for event in handle_message_stream(params):
            yield f"data: {json.dumps(event)}\n\n".encode()
        yield b"data: [DONE]\n\n"
    except Exception as e:
        logger.exception(f"A2A stream error: {e}")
        error_event = jsonrpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(e))
        yield f"data: {json.dumps(error_event)}\n\n".encode()

@jsonrpc_router.post("/a2a", response_model=None)
async def handle_jsonrpc(request: Request) -> JSONResponse | StreamingResponse:
    """Handle A2A JSON-RPC 2.0 requests.

    Dispatches to the appropriate handler based on the JSON-RPC method:
      - message/send: Synchronous agent execution
      - message/stream: SSE streaming execution
      - tasks/get: Retrieve stored task
      - tasks/cancel: Cancel a task

    All errors return HTTP 200 with a JSON-RPC error object in the body,
    per the A2A protocol specification.
    """
    # Parse JSON body
    try:
        body = await request.json()
    except (JSONDecodeError, Exception):
        return JSONResponse(
            content=jsonrpc_error(None, JSONRPC_PARSE_ERROR, "Parse error"),
            status_code=200,
        )

    # Validate JSON-RPC envelope
    request_id = body.get("id")
    if body.get("jsonrpc") != "2.0" or "method" not in body:
        return JSONResponse(
            content=jsonrpc_error(request_id, JSONRPC_INVALID_REQUEST, "Invalid JSON-RPC request"),
            status_code=200,
        )

    method = body["method"]
    params = body.get("params", {})

    # Streaming method
    if method == "message/stream":
        return StreamingResponse(
            _sse_generator(params, request_id),
            media_type="text/event-stream",
        )

    # Synchronous methods
    handler = _METHOD_HANDLERS.get(method)
    if handler is None:
        return JSONResponse(
            content=jsonrpc_error(
                request_id,
                JSONRPC_METHOD_NOT_FOUND,
                f"Method not found: {method}",
            ),
            status_code=200,
        )

    try:
        result = await handler(params)
        return JSONResponse(
            content={"jsonrpc": "2.0", "result": result, "id": request_id},
            status_code=200,
        )
    except ValueError as e:
        return JSONResponse(
            content=jsonrpc_error(request_id, JSONRPC_INVALID_PARAMS, str(e)),
            status_code=200,
        )
    except Exception as e:
        logger.exception(f"A2A handler error for {method}: {e}")
        return JSONResponse(
            content=jsonrpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(e)),
            status_code=200,
        )
