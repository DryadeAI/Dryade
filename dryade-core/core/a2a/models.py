# ruff: noqa: N815 — A2A protocol spec requires camelCase field names
"""A2A Protocol Server Models.

Pydantic v2 models for JSON-RPC 2.0 request/response envelopes,
A2A task lifecycle, and agent discovery (AgentCard).

See: https://github.com/a2aproject/A2A (protocol v0.3.0)
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# JSON-RPC 2.0 standard error codes
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# ------------------------------------------------------------------
# A2A protocol models
# ------------------------------------------------------------------

class A2APart(BaseModel):
    """A single part of an A2A message (text-only for now)."""

    text: str | None = None

class A2AMessage(BaseModel):
    """An A2A message with role and parts."""

    role: Literal["user", "agent"]
    parts: list[A2APart]

class A2ATaskStatus(BaseModel):
    """Status of an A2A task."""

    state: Literal["working", "completed", "failed", "canceled", "rejected", "input-required"]
    message: A2AMessage | None = None

class A2ATask(BaseModel):
    """An A2A task object."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    contextId: str
    status: A2ATaskStatus
    artifacts: list[dict[str, Any]] = []
    kind: Literal["task"] = "task"

class A2ASkill(BaseModel):
    """A skill exposed by an A2A agent."""

    id: str
    name: str
    description: str
    tags: list[str] = []
    examples: list[str] = []

class A2AAgentCard(BaseModel):
    """A2A Agent Card for discovery (/.well-known/agent.json)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    url: str
    version: str = "1.0.0"
    protocolVersion: str = "0.3.0"
    defaultInputModes: list[str] = ["text"]
    defaultOutputModes: list[str] = ["text"]
    capabilities: dict[str, Any] = {"streaming": True, "pushNotifications": False}
    skills: list[A2ASkill] = []
    provider: dict[str, str] = {"organization": "Dryade", "url": "https://dryade.ai"}
    authentication: dict[str, Any] = {"schemes": ["bearer"]}

# ------------------------------------------------------------------
# JSON-RPC 2.0 envelope models
# ------------------------------------------------------------------

class A2AJsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request envelope."""

    jsonrpc: Literal["2.0"]
    method: str
    params: dict[str, Any] = {}
    id: str | int

class A2AJsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 success response envelope."""

    jsonrpc: Literal["2.0"] = "2.0"
    result: dict[str, Any]
    id: str | int

class A2AJsonRpcError(BaseModel):
    """JSON-RPC 2.0 error response envelope."""

    jsonrpc: Literal["2.0"] = "2.0"
    error: dict[str, Any]
    id: str | int | None = None

def jsonrpc_error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response dict.

    Args:
        request_id: The request ID (or None for parse errors).
        code: JSON-RPC error code.
        message: Human-readable error message.

    Returns:
        Complete JSON-RPC 2.0 error response dict.
    """
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": request_id,
    }
