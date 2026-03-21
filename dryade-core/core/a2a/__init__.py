"""A2A Protocol Server Module.

Provides the server-side implementation of the A2A (Agent-to-Agent) protocol,
enabling external orchestrators to discover and invoke Dryade agents via
JSON-RPC 2.0.
"""

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
    A2AAgentCard,
    A2AJsonRpcError,
    A2AJsonRpcRequest,
    A2AJsonRpcResponse,
    A2AMessage,
    A2APart,
    A2ASkill,
    A2ATask,
    A2ATaskStatus,
    jsonrpc_error,
)
from core.a2a.task_store import A2ATaskStore, get_task_store

__all__ = [
    "A2AAgentCard",
    "A2AJsonRpcError",
    "A2AJsonRpcRequest",
    "A2AJsonRpcResponse",
    "A2AMessage",
    "A2APart",
    "A2ASkill",
    "A2ATask",
    "A2ATaskStatus",
    "A2ATaskStore",
    "JSONRPC_INTERNAL_ERROR",
    "JSONRPC_INVALID_PARAMS",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_PARSE_ERROR",
    "build_a2a_agent_card",
    "get_task_store",
    "handle_message_send",
    "handle_message_stream",
    "handle_tasks_cancel",
    "handle_tasks_get",
    "jsonrpc_error",
]
