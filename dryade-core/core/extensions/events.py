"""Unified Event Stream Protocol.

Single event format for all execution modes: chat, crew, flow.
Frontend handles ONE type regardless of backend complexity.

This module provides:
- ChatEvent: Universal event structure for streaming
- Helper functions: emit_token, emit_thinking, emit_tool_*, etc.
- Event types for all phases: streaming, tools, agents, flows, clarification
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Event type literals for type safety
EventType = Literal[
    # Streaming
    "token",  # Streaming text chunk
    "thinking",  # Reasoning/thinking (for o1/thinking models)
    # Tool execution
    "tool_start",  # Tool being called
    "tool_result",  # Tool completed
    # Agent execution (crew mode)
    "agent_start",  # Agent execution started
    "agent_complete",  # Agent finished
    # Flow execution
    "node_start",  # Flow node started
    "node_complete",  # Flow node finished
    "flow_start",  # Flow execution started
    "flow_complete",  # Flow execution finished
    # User interaction
    "clarify",  # System asking user for clarification
    "clarify_response",  # User responded to clarification
    "escalation",  # Orchestrator needs user decision (inline question)
    # Orchestration events
    "reasoning",  # Orchestrator reasoning with visibility control
    "resource_suggestion",  # MCP resource suggestion requiring confirmation
    # State
    "state_export",  # State exported from tool
    "state_conflict",  # Multiple values available for required state key
    # Completion
    "complete",  # Final response
    "error",  # Error occurred
    # Rich orchestration events (Phase 82)
    "plan_preview",  # Execution plan visualization
    "plan_edit",  # Plan modification (bidirectional)
    "progress",  # Step progress with percentage
    "cost_update",  # Token/cost tracking
    "artifact",  # Agent-produced file/data
    "agent_retry",  # Retry attempt
    "agent_fallback",  # Alternative agent switch
    "cancel_ack",  # Cancellation acknowledgment
    "memory_update",  # Cross-session memory write
    # Provider resilience (Phase 146)
    "failover",  # LLM provider failover during streaming
    # Human-in-Loop approval (Phase 150)
    "approval_pending",  # Workflow paused, human approval needed
    "approval_resolved",  # Approval acted on (for live UI update)
]

class ChatEvent(BaseModel):
    """Universal event structure for all execution modes.

    This single event type is used for:
    - Chat mode: Simple token streaming
    - Crew mode: Multi-agent execution with tool calls
    - Flow mode: Graph-based execution with node events

    Frontend handles ONE type regardless of backend complexity.
    """

    type: EventType
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""

    def __init__(self, **data):
        """Initialize the event with automatic timestamp if not provided."""
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(UTC).isoformat()
        super().__init__(**data)

    def to_sse(self) -> str:
        """Convert to Server-Sent Event format."""
        return f"data: {self.model_dump_json()}\n\n"

    def to_ws(self) -> dict[str, Any]:
        """Convert to WebSocket message format."""
        return {"type": "event", "data": self.model_dump()}

# -----------------------------------------------------------------------------
# Token/Streaming Events
# -----------------------------------------------------------------------------

def emit_token(content: str) -> ChatEvent:
    """Emit a streaming text token."""
    return ChatEvent(type="token", content=content)

def emit_thinking(content: str, agent: str = "assistant") -> ChatEvent:
    """Emit thinking/reasoning content.

    Args:
        content: The thinking/reasoning text to display
        agent: Agent identifier for frontend filtering (default: "assistant")

    Returns:
        ChatEvent with type="thinking", content, and agent in metadata
    """
    return ChatEvent(type="thinking", content=content, metadata={"agent": agent})

# -----------------------------------------------------------------------------
# Tool Events
# -----------------------------------------------------------------------------

def emit_tool_start(tool: str, args: dict[str, Any]) -> ChatEvent:
    """Emit when a tool execution starts."""
    return ChatEvent(type="tool_start", metadata={"tool": tool, "args": args})

def emit_tool_result(tool: str, result: Any, duration_ms: float, success: bool = True) -> ChatEvent:
    """Emit when a tool execution completes."""
    return ChatEvent(
        type="tool_result",
        metadata={"tool": tool, "result": result, "duration_ms": duration_ms, "success": success},
    )

# -----------------------------------------------------------------------------
# Agent Events (Crew Mode)
# -----------------------------------------------------------------------------

def emit_agent_start(
    agent_name: str, task: str | None = None, context: dict[str, Any] | None = None
) -> ChatEvent:
    """Emit when an agent starts execution."""
    return ChatEvent(
        type="agent_start", metadata={"agent": agent_name, "task": task, "context": context or {}}
    )

def emit_agent_complete(agent_name: str, result: Any, duration_ms: float) -> ChatEvent:
    """Emit when an agent completes execution."""
    return ChatEvent(
        type="agent_complete",
        metadata={"agent": agent_name, "result": result, "duration_ms": duration_ms},
    )

# -----------------------------------------------------------------------------
# Flow Events
# -----------------------------------------------------------------------------

def emit_flow_start(flow_name: str, inputs: dict[str, Any] | None = None) -> ChatEvent:
    """Emit when a flow execution starts."""
    return ChatEvent(type="flow_start", metadata={"flow": flow_name, "inputs": inputs or {}})

def emit_node_start(node_id: str, node_type: str, flow_name: str | None = None) -> ChatEvent:
    """Emit when a flow node starts execution."""
    return ChatEvent(
        type="node_start", metadata={"node": node_id, "node_type": node_type, "flow": flow_name}
    )

def emit_node_complete(
    node_id: str, result: Any, duration_ms: float, next_nodes: list[str] | None = None
) -> ChatEvent:
    """Emit when a flow node completes execution."""
    return ChatEvent(
        type="node_complete",
        metadata={
            "node": node_id,
            "result": result,
            "duration_ms": duration_ms,
            "next_nodes": next_nodes or [],
        },
    )

def emit_flow_complete(flow_name: str, result: Any, duration_ms: float) -> ChatEvent:
    """Emit when a flow execution completes."""
    return ChatEvent(
        type="flow_complete",
        metadata={"flow": flow_name, "result": result, "duration_ms": duration_ms},
    )

# -----------------------------------------------------------------------------
# Clarification Events
# -----------------------------------------------------------------------------

def emit_clarify(
    question: str, options: list[str] | None = None, context: dict[str, Any] | None = None
) -> ChatEvent:
    """Emit when the system needs clarification from the user."""
    return ChatEvent(
        type="clarify",
        content=question,
        metadata={"options": options or [], "context": context or {}},
    )

def emit_clarify_response(response: str, selected_option: int | None = None) -> ChatEvent:
    """Emit when user responds to a clarification request."""
    return ChatEvent(
        type="clarify_response", content=response, metadata={"selected_option": selected_option}
    )

# -----------------------------------------------------------------------------
# State Events
# -----------------------------------------------------------------------------

def emit_state_export(exports: dict[str, Any]) -> ChatEvent:
    """Emit when state is exported from a tool."""
    return ChatEvent(type="state_export", metadata={"exports": exports})

def emit_state_conflict(
    state_key: str, candidates: list[dict[str, Any]], required_by: str | None = None
) -> ChatEvent:
    """Emit when multiple values are available for a required state key.

    The frontend should pause execution and prompt the user to select one.

    Args:
        state_key: The state key with conflicting values (e.g., "mbse.session_id")
        candidates: List of candidate values with their sources
                    [{"value": "sess_1", "source": "tool_a"}, {"value": "sess_2", "source": "tool_b"}]
        required_by: The tool/agent that requires this state key

    Example event:
        {
            "type": "state_conflict",
            "content": "Multiple sessions available. Which session should be used?",
            "metadata": {
                "state_key": "mbse.session_id",
                "candidates": [
                    {"value": "sess_abc", "source": "open_session", "label": "Model A (sess_abc)"},
                    {"value": "sess_def", "source": "open_session", "label": "Model B (sess_def)"}
                ],
                "required_by": "list_elements"
            }
        }
    """
    # Build human-readable question
    key_name = state_key.split(".")[-1].replace("_", " ")
    question = f"Multiple values available for '{key_name}'. Which one should be used?"

    return ChatEvent(
        type="state_conflict",
        content=question,
        metadata={"state_key": state_key, "candidates": candidates, "required_by": required_by},
    )

# -----------------------------------------------------------------------------
# Completion Events
# -----------------------------------------------------------------------------

def emit_complete(
    response: str,
    exports: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
    *,
    mode: str | None = None,
    model_id: str | None = None,
    provider: str | None = None,
    orchestration_mode: str | None = None,
) -> ChatEvent:
    """Emit when the response is complete."""
    metadata: dict[str, Any] = {"exports": exports or {}, "usage": usage or {}}
    if mode is not None:
        metadata["mode"] = mode
    if model_id is not None:
        metadata["model_id"] = model_id
    if provider is not None:
        metadata["provider"] = provider
    if orchestration_mode is not None:
        metadata["orchestration_mode"] = orchestration_mode
    return ChatEvent(type="complete", content=response, metadata=metadata)

def emit_error(
    message: str, code: str | None = None, details: dict[str, Any] | None = None
) -> ChatEvent:
    """Emit when an error occurs."""
    return ChatEvent(
        type="error", content=message, metadata={"code": code, "details": details or {}}
    )

# -----------------------------------------------------------------------------
# Rich Orchestration Events (Phase 82)
# -----------------------------------------------------------------------------

def emit_plan_preview(
    steps: list[dict],
    estimated_duration_s: float | None = None,
) -> ChatEvent:
    """Emit execution plan before orchestration starts."""
    return ChatEvent(
        type="plan_preview",
        content=f"Execution plan: {len(steps)} steps",
        metadata={
            "steps": steps,
            "step_count": len(steps),
            "estimated_duration_s": estimated_duration_s,
        },
    )

def emit_progress(
    current_step: int,
    total_steps: int,
    current_agent: str,
    eta_seconds: float | None = None,
) -> ChatEvent:
    """Emit step progress during orchestration."""
    pct = round((current_step / total_steps) * 100) if total_steps > 0 else 0
    return ChatEvent(
        type="progress",
        content=f"Step {current_step}/{total_steps} ({pct}%)",
        metadata={
            "current_step": current_step,
            "total_steps": total_steps,
            "percentage": pct,
            "eta_seconds": eta_seconds,
            "current_agent": current_agent,
        },
    )

def emit_cost_update(
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost_usd: float | None = None,
) -> ChatEvent:
    """Emit real-time token and cost tracking."""
    return ChatEvent(
        type="cost_update",
        metadata={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": estimated_cost_usd,
        },
    )

def emit_artifact(
    name: str,
    mime_type: str,
    size_bytes: int,
    preview: str | None = None,
) -> ChatEvent:
    """Emit when an agent produces a file or data artifact."""
    return ChatEvent(
        type="artifact",
        content=name,
        metadata={
            "name": name,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "preview": preview,
        },
    )

def emit_agent_retry(
    agent: str,
    attempt: int,
    max_attempts: int,
    error: str,
    wait_seconds: float = 0,
) -> ChatEvent:
    """Emit retry attempt details."""
    return ChatEvent(
        type="agent_retry",
        content=f"Retrying {agent} (attempt {attempt}/{max_attempts})",
        metadata={
            "agent": agent,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "error": error,
            "wait_seconds": wait_seconds,
        },
    )

def emit_agent_fallback(
    original_agent: str,
    fallback_agent: str,
    reason: str,
) -> ChatEvent:
    """Emit when switching to an alternative agent."""
    return ChatEvent(
        type="agent_fallback",
        content=f"Switching from {original_agent} to {fallback_agent}",
        metadata={
            "original_agent": original_agent,
            "fallback_agent": fallback_agent,
            "reason": reason,
        },
    )

def emit_failover(from_provider: str, to_provider: str) -> ChatEvent:
    """Emit when switching to a fallback LLM provider during streaming.

    Sent by _run_with_fallback (SSE) and _ws_run_with_fallback (WS) when the
    primary provider fails and the next provider in the fallback chain is tried.

    Args:
        from_provider: Provider key that failed (e.g. "openai").
        to_provider: Provider key being tried next (e.g. "anthropic").

    Returns:
        ChatEvent that the frontend's failover toast handler will consume.
    """
    return ChatEvent(
        type="failover",
        content=f"Switching from {from_provider} to {to_provider}",
        metadata={"from_provider": from_provider, "to_provider": to_provider},
    )

def emit_cancel_ack(
    partial_results_count: int,
    current_step: int | None = None,
    reason: str = "User requested cancellation",
) -> ChatEvent:
    """Emit cancellation acknowledgment."""
    return ChatEvent(
        type="cancel_ack",
        content="Orchestration cancelled. Partial results preserved.",
        metadata={
            "partial_results_count": partial_results_count,
            "current_step": current_step,
            "reason": reason,
        },
    )

def emit_memory_update(
    key: str,
    value_preview: str,
    scope: str = "session",
) -> ChatEvent:
    """Emit when cross-session memory is written."""
    return ChatEvent(
        type="memory_update",
        content=f"Memory updated: {key}",
        metadata={
            "key": key,
            "value_preview": value_preview[:200],
            "scope": scope,
        },
    )

# -----------------------------------------------------------------------------
# OpenAI-Compatible SSE Format
# -----------------------------------------------------------------------------

def to_openai_sse(event: ChatEvent, model: str = "dryade") -> str:
    r"""Convert ChatEvent to OpenAI-compatible SSE chunk format.

    Format: data: {"id":"...", "object":"chat.completion.chunk", ...}\n\n
    """
    import uuid

    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(datetime.now(UTC).timestamp())

    # Base chunk structure
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
    }

    # Map event types to OpenAI format
    if event.type == "token":
        chunk["choices"][0]["delta"] = {"content": event.content}
    elif event.type == "thinking":
        # vLLM-compatible reasoning_content format
        chunk["choices"][0]["delta"] = {"reasoning_content": event.content}
        # Also include Dryade event with flattened metadata for frontend ThinkingStream
        # Frontend expects: {type: "thinking", agent: string, content: string}
        dryade_event = {"type": "thinking", "content": event.content}
        dryade_event.update(event.metadata)  # Flatten metadata to top level
        chunk["dryade"] = dryade_event
    elif event.type == "complete":
        # Include content in the final chunk before signaling stop
        if event.content:
            chunk["choices"][0]["delta"] = {"content": event.content}
        else:
            chunk["choices"][0]["delta"] = {}
        chunk["choices"][0]["finish_reason"] = "stop"
    elif event.type == "error":
        chunk["choices"][0]["delta"] = {}
        chunk["choices"][0]["finish_reason"] = "error"
        # Include error details so frontend can display the real message
        chunk["error"] = {
            "message": event.content or "Unknown error",
            "code": event.metadata.get("code"),
        }
    else:
        # Dryade-specific events go in a custom field with flattened metadata
        dryade_event = {"type": event.type, "content": event.content}
        dryade_event.update(event.metadata)  # Flatten metadata to top level
        chunk["dryade"] = dryade_event

    import json

    return f"data: {json.dumps(chunk)}\n\n"

def emit_done() -> str:
    """Emit the [DONE] SSE termination message."""
    return "data: [DONE]\n\n"

# -----------------------------------------------------------------------------
# Approval Events (Phase 150)
# -----------------------------------------------------------------------------

def emit_approval_pending(
    approval_request_id: int,
    workflow_id: int,
    workflow_name: str,
    node_id: str,
    prompt: str,
) -> ChatEvent:
    """Emit when a workflow pauses for human approval."""
    return ChatEvent(
        type="approval_pending",
        content=f"Approval needed: {prompt[:100]}",
        metadata={
            "approval_request_id": approval_request_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "node_id": node_id,
            "prompt": prompt,
        },
    )

def emit_approval_resolved(
    approval_request_id: int,
    workflow_id: int,
    action: str,
    resolved_by: str,
) -> ChatEvent:
    """Emit when an approval request is resolved."""
    return ChatEvent(
        type="approval_resolved",
        content=f"Approval {action} by {resolved_by}",
        metadata={
            "approval_request_id": approval_request_id,
            "workflow_id": workflow_id,
            "action": action,
            "resolved_by": resolved_by,
        },
    )
