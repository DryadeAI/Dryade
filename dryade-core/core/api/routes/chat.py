"""Chat Routes - Single-turn and streaming chat endpoints.

Uses ExecutionRouter for generic multi-domain execution.

Supports audio responses when AudioAgent returns synthesized speech.
Audio is delivered via dedicated "audio" SSE event with base64-encoded WAV.

Target: ~150 LOC
"""

import contextlib
import json
import logging
import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, joinedload

from core.api.models.openapi import response_with_errors
from core.api.routes.provider_health import CANCEL_EVENTS
from core.audit.tracer import AuditTracer
from core.auth.dependencies import get_current_user, get_db
from core.database.models import Conversation as DBConversation
from core.database.models import Message as DBMessage
from core.database.models import Project as DBProject
from core.database.models import ResourceShare as DBResourceShare
from core.database.models import ToolResult as DBToolResult
from core.extensions.events import to_openai_sse
from core.observability.metrics import record_tool_call
from core.orchestrator.router import route_request
from core.utils.time import utcnow

router = APIRouter()
logger = logging.getLogger(__name__)

# Strip <think>...</think> blocks from reasoning models (Qwen3, DeepSeek, etc.)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def _strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from LLM output."""
    if "<think>" not in text:
        return text
    return _THINK_RE.sub("", text).strip()

# Request/Response Models
class ToolCall(BaseModel):
    """Record of a tool invocation during chat execution."""

    tool: str = Field(..., description="Name of the tool that was called")
    args: dict[str, Any] = Field(..., description="Arguments passed to the tool")
    result: str | None = Field(None, description="Result returned by the tool")

class TokenUsage(BaseModel):
    """Token usage statistics for a chat completion."""

    prompt_tokens: int = Field(0, description="Number of tokens in the prompt", ge=0)
    completion_tokens: int = Field(0, description="Number of tokens in the completion", ge=0)
    total_tokens: int = Field(0, description="Total tokens (prompt + completion)", ge=0)

class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "What is the weather like today?",
                "conversation_id": None,
                "mode": "chat",
                "crew_id": None,
                "user_id": "user-123",
                "enable_thinking": False,
            }
        }
    )

    message: str = Field(..., description="User message content", max_length=10000)
    conversation_id: str | None = Field(
        None, description="Existing conversation ID to continue, or null for new conversation"
    )
    mode: Literal["chat", "crew", "flow", "planner", "autonomous", "orchestrate"] = Field(
        "chat",
        description="Execution mode. 'chat' (default) for AI conversation with auto-routing to agents. 'planner' for workflow plan generation. Legacy values (crew, flow, autonomous, orchestrate) are accepted and mapped automatically.",
    )
    leash_preset: Literal["conservative", "standard", "permissive"] | None = Field(
        None,
        description="Autonomy constraint preset for autonomous mode. Conservative: 5 actions, $0.10, 95% confidence. Standard: 20 actions, $0.50, 85% confidence. Permissive: 50 actions, $2.00, 70% confidence.",
    )
    crew_id: Literal["analysis_crew", "mbse_crew"] | None = Field(
        None,
        description="Crew ID when mode=crew. Uses adapter-based fallback if not specified.",
    )
    flow_name: str | None = Field(
        None, description="Flow name when mode=flow (e.g., 'AnalysisFlow')"
    )
    user_id: str | None = Field(
        None, description="User identifier for cost tracking and personalization"
    )
    enable_thinking: bool = Field(
        False, description="Enable LLM reasoning/thinking mode for complex tasks"
    )

class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    title: str | None = Field(None, description="Optional conversation title")
    mode: Literal["chat", "crew", "flow", "planner", "autonomous", "orchestrate"] = Field(
        "chat", description="Execution mode for this conversation. 'chat' or 'planner'."
    )

class AddMessageRequest(BaseModel):
    """Request to add a message to a conversation."""

    content: str = Field(..., description="Message content", min_length=1)
    role: Literal["user", "assistant"] = Field(..., description="Message role")

class ShareConversationRequest(BaseModel):
    """Request to share a conversation with another user."""

    user_id: str = Field(..., description="User ID to share with")
    permission: Literal["view", "edit"] = Field("view", description="Permission level")

class ClarifyRequest(BaseModel):
    """Request to respond to a pending clarification."""

    conversation_id: str = Field(..., description="Conversation with pending clarification")
    response: str = Field(..., description="User's response to the clarification prompt")
    selected_option: int | None = Field(
        None, description="Index of selected option (if options were provided)"
    )

class StateConflictResolutionRequest(BaseModel):
    """Request to resolve a state conflict during execution."""

    conversation_id: str = Field(..., description="Conversation with state conflict")
    state_key: str = Field(..., description="Key of the conflicting state variable")
    selected_value: Any = Field(..., description="User's selected value to resolve the conflict")

class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "response": "The weather today is sunny with a high of 72°F.",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "tool_calls": [],
                "exports": {},
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
                "mode": "chat",
            }
        }
    )

    response: str = Field(..., description="Assistant's response content")
    conversation_id: str = Field(..., description="Conversation ID for follow-up messages")
    tool_calls: list[ToolCall] = Field(
        default_factory=list, description="Tools invoked during execution"
    )
    exports: dict[str, Any] = Field(
        default_factory=dict, description="Exported data from flow execution"
    )
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token usage statistics")
    mode: str = Field("chat", description="Execution mode that was used")
    model_id: str | None = Field(
        None, description="AI model used for this response (EU AI Act transparency)"
    )
    provider: str | None = Field(None, description="LLM provider that served this response")
    orchestration_mode: str | None = Field(
        None, description="Orchestration mode used: chat, planner, orchestrate, tool_selection"
    )

class MessageToolCall(BaseModel):
    """Tool call record in message response."""

    tool: str = Field(..., description="Name of the tool")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: str | None = Field(None, description="Tool result")
    status: Literal["pending", "executing", "complete", "error"] = Field(
        "complete", description="Tool execution status"
    )
    duration_ms: float | None = Field(None, description="Execution duration in milliseconds")

class Message(BaseModel):
    """A single message in a conversation."""

    id: str = Field(..., description="Unique message identifier")
    role: Literal["user", "assistant", "system"] = Field(..., description="Message author role")
    content: str = Field(..., description="Message text content")
    timestamp: str = Field(..., description="ISO 8601 timestamp when message was created")
    created_at: str = Field(..., description="ISO 8601 timestamp (alias for timestamp)")
    thinking: str | None = Field(None, description="LLM reasoning/thinking for this message")
    cached: bool = Field(False, description="Whether response was cached")
    tool_calls: list[MessageToolCall] = Field(
        default_factory=list, description="Tool calls made during this message"
    )

@router.post(
    "/{conversation_id}/cancel",
    responses=response_with_errors(404),
    summary="Cancel running orchestration",
)
async def cancel_orchestration(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Cancel a running orchestration for a conversation.

    Signals the orchestrator loop to stop gracefully after the current step.
    Returns partial results already collected.

    Returns 404 if no active orchestration exists for this conversation.
    """
    from core.orchestrator.cancellation import get_cancellation_registry

    registry = get_cancellation_registry()
    cancelled = registry.request_cancel(conversation_id)

    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="No active orchestration found for this conversation",
        )

    return {"status": "cancelling", "conversation_id": conversation_id}

@router.get(
    "/{conversation_id}/stream-status",
    summary="Check if a conversation has an active stream",
)
async def get_stream_status(conversation_id: str) -> dict:
    """Check whether a conversation is currently streaming.

    Used by the frontend on mount to detect and rejoin active streams
    after navigation away and back.
    """
    from core.orchestrator.stream_registry import get_stream_registry

    stream = get_stream_registry().get(conversation_id)
    if not stream:
        return {"active": False}

    return {
        "active": True,
        "started_at": stream.started_at,
        "mode": stream.mode,
        "accumulated_content": stream.accumulated_content,
        "accumulated_thinking": stream.accumulated_thinking,
    }

@router.post(
    "",
    response_model=ChatResponse,
    responses=response_with_errors(400, 500, 503),
    summary="Execute chat message",
)
async def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Execute a chat message through the orchestration router.

    Supports four execution modes:
    - **chat**: Direct LLM conversation (default)
    - **crew**: Multi-agent crew execution
    - **flow**: Predefined workflow execution
    - **planner**: Dynamic flow generation and execution

    Returns a synchronous response. For streaming, use POST /stream endpoint.
    """
    from time import perf_counter

    from core.extensions.latency_tracker import record_latency

    request_start = perf_counter()
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Handle empty message gracefully
    if not request.message or not request.message.strip():
        return ChatResponse(
            response="It looks like your message was empty. Could you please provide your question or request?",
            conversation_id=conversation_id,
            mode=request.mode,
        )

    user_id = user.get("sub")  # Get user ID from JWT token

    tracer = AuditTracer(user_id=user_id, conversation_id=conversation_id, mode=request.mode)
    tracer.add_custom("chat_request", {"message_length": len(request.message), "mode": request.mode})

    # Load user's LLM configuration from database (Settings page)
    from core.providers.user_config import get_user_llm_config

    user_llm_config = get_user_llm_config(user_id, db) if user_id else None

    # Validate message size (max 10KB)
    if len(request.message.encode("utf-8")) > 10240:
        raise HTTPException(status_code=400, detail="Message size exceeds 10KB limit")

    try:
        # Create or get conversation
        conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
        if not conversation:
            conversation = DBConversation(
                id=conversation_id,
                user_id=user_id,
                title=request.message[:50],  # First 50 chars as title
                mode=request.mode,
                status="active",
            )
            db.add(conversation)

        # Store user message
        user_msg = DBMessage(
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            metadata_={"timestamp": utcnow().isoformat()},
        )
        db.add(user_msg)
        db.commit()

    except IntegrityError as e:
        db.rollback()
        logger.exception(
            f"Database integrity error storing user message: {e}",
            extra={"conversation_id": conversation_id, "error_type": "IntegrityError"},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save message. Please try again.",
        ) from e
    except OperationalError as e:
        db.rollback()
        logger.exception(
            f"Database operational error storing user message: {e}",
            extra={"conversation_id": conversation_id, "error_type": "OperationalError"},
        )
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable. Please retry in a moment.",
        ) from e
    except Exception as e:
        db.rollback()
        logger.exception(
            f"Unexpected database error storing user message: {e}",
            extra={"conversation_id": conversation_id, "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save message. Please try again.",
        ) from e

    response_text = ""
    exports = {}
    mode = request.mode
    model_id = None
    provider = None
    orchestration_mode = None
    tool_calls: list[ToolCall] = []
    usage = TokenUsage()

    try:
        async for event in route_request(
            message=request.message,
            conversation_id=conversation_id,
            user_id=user_id,
            mode_override=request.mode,
            stream=False,
            enable_thinking=request.enable_thinking,
            user_llm_config=user_llm_config,
            crew_id=request.crew_id,
            leash_preset=request.leash_preset,
            db=db,
        ):
            tracer.observe(event)
            if event.type == "complete":
                response_text = event.content
                exports = event.metadata.get("exports", {})
                mode = event.metadata.get("mode", "chat")
                model_id = event.metadata.get("model_id")
                provider = event.metadata.get("provider")
                orchestration_mode = event.metadata.get("orchestration_mode") or mode
                # Extract usage from complete event metadata
                raw_usage = event.metadata.get("usage", {})
                if raw_usage:
                    usage = TokenUsage(
                        prompt_tokens=raw_usage.get("prompt_tokens", 0),
                        completion_tokens=raw_usage.get("completion_tokens", 0),
                        total_tokens=raw_usage.get("total_tokens", 0),
                    )
            elif event.type == "tool_result":
                # Collect tool calls from tool_result events
                meta = event.metadata or {}
                tool_calls.append(
                    ToolCall(
                        tool=meta.get("tool", "unknown"),
                        args=meta.get("args", {}),
                        result=str(meta.get("result", event.content or "")),
                        status="complete" if meta.get("success", True) else "error",
                        duration_ms=meta.get("duration_ms"),
                    )
                )
            elif event.type == "error":
                response_text = f"Error: {event.content}"
    except RuntimeError as e:
        # Handle queue full/timeout errors with 503
        error_msg = str(e).lower()
        if "queue" in error_msg or "overloaded" in error_msg:
            logger.warning(
                f"LLM request queue rejection: {e}", extra={"conversation_id": conversation_id}
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily overloaded. Please retry in a moment.",
                headers={"Retry-After": "5"},
            ) from e
        raise

    # Fallback: if the complete event didn't provide model_id/provider,
    # derive them from the user's LLM config (EU AI Act transparency).
    if model_id is None and user_llm_config is not None:
        model_id = user_llm_config.model
        if provider is None:
            provider = user_llm_config.provider or (
                user_llm_config.endpoint if user_llm_config.endpoint else None
            )

    try:
        # Store assistant message (includes EU AI Act transparency metadata)
        assistant_msg = DBMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            metadata_={
                "mode": mode,
                "model_id": model_id,
                "provider": provider,
                "orchestration_mode": orchestration_mode,
            },
        )
        db.add(assistant_msg)
        db.commit()

    except IntegrityError as e:
        db.rollback()
        logger.exception(
            f"Database integrity error storing assistant message: {e}",
            extra={"conversation_id": conversation_id, "error_type": "IntegrityError"},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save response. Please try again.",
        ) from e
    except OperationalError as e:
        db.rollback()
        logger.exception(
            f"Database operational error storing assistant message: {e}",
            extra={"conversation_id": conversation_id, "error_type": "OperationalError"},
        )
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable. Please retry in a moment.",
        ) from e
    except Exception as e:
        db.rollback()
        logger.exception(
            f"Unexpected database error storing assistant message: {e}",
            extra={"conversation_id": conversation_id, "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save response. Please try again.",
        ) from e

    # Record latency for non-streaming endpoint
    total_ms = (perf_counter() - request_start) * 1000
    record_latency(
        conversation_id=conversation_id,
        mode=request.mode,
        total_ms=total_ms,
    )

    # Strip <think> blocks from reasoning models before returning
    response_text = _strip_think_blocks(response_text)

    try:
        tracer.persist()
    except Exception:
        logger.warning("AuditTracer.persist() failed (sync handler)", exc_info=True)

    return ChatResponse(
        response=response_text,
        conversation_id=conversation_id,
        tool_calls=tool_calls,
        exports=exports,
        usage=usage,
        mode=mode,
        model_id=model_id,
        provider=provider,
        orchestration_mode=orchestration_mode,
    )

@router.post(
    "/stream",
    responses=response_with_errors(400, 500, 503),
    summary="Stream chat response",
)
async def chat_stream(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Streaming chat endpoint using Server-Sent Events (SSE).

    Returns a stream of events:
    - **start**: Initial event with conversation_id
    - **token/content**: Text chunks as they're generated
    - **tool_start/tool_result**: Tool invocation events
    - **thinking**: LLM reasoning steps (if enable_thinking=true)
    - **complete**: Final event with metadata
    - **error**: Error events if something fails
    - **stream_complete**: Summary event with cache status
    - **[DONE]**: Stream termination marker

    Set `Accept: text/event-stream` header for streaming response.
    """
    import logging
    from time import perf_counter

    from core.extensions.latency_tracker import record_latency

    logger = logging.getLogger("dryade.chat.stream")

    request_start = perf_counter()
    conversation_id = request.conversation_id or str(uuid.uuid4())
    user_id = user.get("sub")  # Get user ID from JWT token

    tracer = AuditTracer(user_id=user_id, conversation_id=conversation_id, mode=request.mode)
    tracer.add_custom("chat_request", {"message_length": len(request.message), "mode": request.mode})

    # Load user's LLM configuration from database (Settings page)
    from core.providers.user_config import get_user_llm_config

    user_llm_config = get_user_llm_config(user_id, db) if user_id else None

    # Load user's fallback chain for resilient provider switching
    fallback_chain = None
    cancel_event = None
    if user_id:
        try:
            from core.providers.resilience.fallback_chain import get_fallback_chain

            fallback_chain = get_fallback_chain(user_id, db)
        except Exception:
            pass  # No fallback — proceed with single provider

    if fallback_chain and fallback_chain.entries and fallback_chain.enabled:
        import asyncio as _asyncio

        cancel_event = _asyncio.Event()
        CANCEL_EVENTS[conversation_id] = cancel_event

    logger.info("[CHAT API] ========== NEW CHAT REQUEST ==========")
    logger.info(f"[CHAT API] Conversation ID: {conversation_id}")
    logger.info(f"[CHAT API] Mode: {request.mode}")
    logger.info(f"[CHAT API] Message: {request.message[:100]}...")
    logger.info(f"[CHAT API] Enable thinking: {request.enable_thinking}")
    if request.flow_name:
        logger.info(f"[CHAT API] Flow name: {request.flow_name}")

    if request.mode == "planner":
        logger.info("[CHAT API] >>> PLANNER MODE ACTIVATED <<<")
        logger.info("[CHAT API] Request will be routed to dynamic planner for plan generation")

    # Validate message size (max 10KB)
    if len(request.message.encode("utf-8")) > 10240:
        raise HTTPException(status_code=400, detail="Message size exceeds 10KB limit")

    try:
        # Create or get conversation
        conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
        if not conversation:
            conversation = DBConversation(
                id=conversation_id,
                user_id=user_id,
                title=request.message[:50],  # First 50 chars as title
                mode=request.mode,
                status="active",
            )
            db.add(conversation)

        # Store user message
        user_msg = DBMessage(
            conversation_id=conversation_id,
            role="user",
            content=request.message,
            metadata_={"timestamp": utcnow().isoformat()},
        )
        db.add(user_msg)
        db.commit()
        logger.info("[STREAM] User message persisted to database")

    except Exception as e:
        db.rollback()
        logger.exception(f"[STREAM] Database error storing user message: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to save message. Please try again.",
        ) from e

    async def generate():
        nonlocal request_start

        # Include cache_enabled flag in start event
        yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id, 'cache_enabled': True})}\n\n"
        logger.info("[STREAM] Sent start event with cache_enabled=True")

        event_count = 0
        full_response = ""
        full_thinking = ""  # Track thinking/reasoning content for persistence
        response_mode = request.mode
        cache_hit = False  # Track if response came from cache
        tool_calls = []  # Track tool calls: [{tool_name, args, result, success, duration_ms}]
        ttft_recorded = False
        ttft_ms = None
        stream_model_id = None  # EU AI Act transparency
        stream_provider = None
        stream_orchestration_mode = None

        async def _run_with_fallback():
            """Yield ChatEvents from route_request with automatic provider fallback.

            When the user has a configured and enabled fallback chain, iterates
            through providers in order, emitting failover events between attempts.
            Falls back to the normal single-provider path when chain is unavailable.
            """
            from core.crypto import decrypt_key
            from core.database.models import ProviderApiKey
            from core.extensions.events import emit_failover
            from core.providers.resilience.events import log_failover_event
            from core.providers.resilience.failover_engine import PROVIDER_CIRCUIT_BREAKER
            from core.providers.resilience.fallback_chain import resolve_chain_configs
            from core.providers.user_config import UserLLMConfig

            def _user_config_fn(provider: str):
                try:
                    key_record = (
                        db.query(ProviderApiKey)
                        .filter(
                            ProviderApiKey.user_id == user_id,
                            ProviderApiKey.provider == provider,
                            ProviderApiKey.is_global == True,  # noqa: E712
                        )
                        .first()
                    )
                    api_key = None
                    if key_record:
                        try:
                            api_key = decrypt_key(key_record.key_encrypted)
                        except Exception:
                            pass

                    class _Info:
                        pass

                    info = _Info()
                    info.api_key = api_key
                    info.endpoint = None
                    return info
                except Exception:

                    class _InfoEmpty:
                        api_key = None
                        endpoint = None

                    return _InfoEmpty()

            resolved = resolve_chain_configs(fallback_chain, _user_config_fn)

            if not resolved:
                # No valid providers in chain — fall through to normal path
                async for ev in route_request(
                    message=request.message,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    mode_override=request.mode,
                    stream=True,
                    enable_thinking=request.enable_thinking,
                    user_llm_config=user_llm_config,
                    crew_id=request.crew_id,
                    leash_preset=request.leash_preset,
                    db=db,
                ):
                    yield ev
                return

            for idx, config in enumerate(resolved):
                if cancel_event and cancel_event.is_set():
                    break

                provider_key = f"{config.provider}:{config.model}"
                if not PROVIDER_CIRCUIT_BREAKER.can_execute(provider_key):
                    continue

                provider_llm_config = UserLLMConfig(
                    provider=config.provider,
                    model=config.model,
                    endpoint=config.base_url,
                    api_key=config.api_key,
                )

                try:
                    had_events = False
                    async for ev in route_request(
                        message=request.message,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        mode_override=request.mode,
                        stream=True,
                        enable_thinking=request.enable_thinking,
                        user_llm_config=provider_llm_config,
                        crew_id=request.crew_id,
                        leash_preset=request.leash_preset,
                        db=db,
                    ):
                        had_events = True
                        yield ev

                    if had_events:
                        PROVIDER_CIRCUIT_BREAKER.record_success(provider_key)
                        return
                except Exception as exc:
                    PROVIDER_CIRCUIT_BREAKER.record_failure(provider_key)
                    log_failover_event(config.provider, exc)

                    if idx + 1 < len(resolved):
                        next_provider = resolved[idx + 1].provider
                        yield emit_failover(config.provider, next_provider)
                    continue

            # All providers exhausted — emit error ChatEvent
            from core.extensions.events import emit_error as _emit_error

            yield _emit_error(
                message="All LLM providers are unavailable",
                code="all_providers_exhausted",
            )

        # Choose between fallback-enabled and standard path
        if fallback_chain and fallback_chain.entries and fallback_chain.enabled:
            event_source = _run_with_fallback()
        else:
            event_source = route_request(
                message=request.message,
                conversation_id=conversation_id,
                user_id=user_id,
                mode_override=request.mode,
                stream=True,
                enable_thinking=request.enable_thinking,
                user_llm_config=user_llm_config,
                crew_id=request.crew_id,
                leash_preset=request.leash_preset,
                db=db,
            )

        try:
            async for event in event_source:
                tracer.observe(event)
                event_count += 1

                # Track time to first token
                if not ttft_recorded and event.type in ("token", "content") and event.content:
                    ttft_ms = (perf_counter() - request_start) * 1000
                    ttft_recorded = True

                # Collect thinking/reasoning for database storage
                if event.type == "thinking":
                    if event.content:
                        full_thinking += ("\n\n" if full_thinking else "") + event.content

                # Collect response for database storage
                if event.type == "content" or event.type == "token":
                    if event.content:
                        full_response += event.content
                elif event.type == "complete":
                    if event.content:
                        full_response = event.content
                    response_mode = event.metadata.get("mode", request.mode)
                    # EU AI Act transparency metadata
                    stream_model_id = event.metadata.get("model_id")
                    stream_provider = event.metadata.get("provider")
                    stream_orchestration_mode = (
                        event.metadata.get("orchestration_mode") or response_mode
                    )
                    # Track cache hit status from complete event metadata
                    cache_hit = event.metadata.get("cached", False)
                    if cache_hit:
                        logger.info("[STREAM] Cache hit detected for this response")

                # Track tool calls
                elif event.type == "tool_start":
                    tool_calls.append(
                        {
                            "tool_name": event.metadata.get("tool", "unknown"),
                            "args": event.metadata.get("args", {}),
                            "result": None,
                            "success": True,
                            "duration_ms": None,
                            "tool_call_id": event.metadata.get("tool_call_id"),
                        }
                    )
                elif event.type == "tool_result" and tool_calls:
                    # Update the last tool call with result
                    tool_calls[-1]["result"] = str(event.metadata.get("result", ""))
                    tool_calls[-1]["success"] = event.metadata.get("success", True)
                    tool_calls[-1]["duration_ms"] = event.metadata.get("duration_ms")
                    with contextlib.suppress(Exception):
                        record_tool_call(
                            tool_calls[-1]["tool_name"],
                            "success" if tool_calls[-1]["success"] else "error",
                            (tool_calls[-1]["duration_ms"] or 0) / 1000,
                        )

                # Check for audio in agent results (AudioAgent returns audio in result)
                # Audio can be in metadata.result (from agent_complete) or in complete metadata
                audio_data = None
                if event.type == "agent_complete":
                    # Check if agent result contains audio
                    result = event.metadata.get("result", {})
                    if isinstance(result, dict) and result.get("audio"):
                        audio_data = {
                            "audio": result["audio"],
                            "audio_size": result.get("audio_size", 0),
                            "audio_format": result.get("audio_format", "wav"),
                            "text": result.get("text", ""),
                        }
                elif event.type == "complete":
                    # Check if complete event has audio in metadata
                    if event.metadata.get("audio"):
                        audio_data = {
                            "audio": event.metadata["audio"],
                            "audio_size": event.metadata.get("audio_size", 0),
                            "audio_format": event.metadata.get("audio_format", "wav"),
                            "text": event.content or "",
                        }

                # Emit dedicated audio event if audio data present
                if audio_data:
                    audio_event = {
                        "type": "audio",
                        "audio": audio_data["audio"],
                        "audio_size": audio_data["audio_size"],
                        "audio_format": audio_data["audio_format"],
                        "text": audio_data["text"],
                    }
                    logger.info(f"[STREAM] Emitting audio event: {audio_data['audio_size']} bytes")
                    yield f"data: {json.dumps(audio_event)}\n\n"

                sse_data = to_openai_sse(event)
                logger.debug(
                    f"[STREAM] Event #{event_count}: type={event.type}, content_len={len(str(event.content)) if event.content else 0}"
                )
                logger.debug(f"[STREAM] SSE data: {sse_data[:200]}...")
                yield sse_data

        except RuntimeError as e:
            error_msg = str(e).lower()
            if "queue" in error_msg or "overloaded" in error_msg:
                logger.warning(f"[STREAM] LLM request queue rejection: {e}")
                yield f"data: {json.dumps({'type': 'error', 'code': 'SERVICE_OVERLOADED', 'message': 'Service temporarily overloaded. Please retry in a moment.', 'retry_after': 5})}\n\n"
            else:
                logger.error(f"[STREAM] RuntimeError during streaming: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"[STREAM] Error during streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        # Store assistant response and tool results to database after stream completes
        # Skip persistence if no content was generated (error-only stream)
        if not full_response and not tool_calls:
            logger.info(
                "[STREAM] Skipping DB persistence - no content generated (error-only stream)"
            )
        else:
            # Fallback: if the complete event didn't provide model_id/provider,
            # derive them from the user's LLM config (EU AI Act transparency).
            if stream_model_id is None and user_llm_config is not None:
                stream_model_id = user_llm_config.model
                if stream_provider is None:
                    stream_provider = user_llm_config.provider or (
                        user_llm_config.endpoint if user_llm_config.endpoint else None
                    )

            try:
                # Get a new session for async context
                from core.database.session import get_session

                with get_session() as db_session:
                    # Store assistant message with cache status, thinking, and AI metadata
                    msg_metadata = {
                        "mode": response_mode,
                        "cached": cache_hit,
                        "model_id": stream_model_id,
                        "provider": stream_provider,
                        "orchestration_mode": stream_orchestration_mode,
                    }
                    if full_thinking:
                        msg_metadata["thinking"] = full_thinking
                    # Strip <think> blocks before persisting
                    clean_response = _strip_think_blocks(full_response)
                    assistant_msg = DBMessage(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=clean_response,
                        metadata_=msg_metadata,
                    )
                    db_session.add(assistant_msg)
                    db_session.flush()  # Get the message ID

                    # Store tool results linked to this message
                    for tool_call in tool_calls:
                        tool_result = DBToolResult(
                            message_id=assistant_msg.id,
                            tool_name=tool_call["tool_name"],
                            tool_call_id=tool_call.get("tool_call_id"),
                            arguments=tool_call["args"],
                            result=tool_call["result"],
                            success=tool_call["success"],
                            duration_ms=tool_call["duration_ms"],
                        )
                        db_session.add(tool_result)

                    db_session.commit()
                    logger.info(
                        f"[STREAM] Assistant message and {len(tool_calls)} tool results persisted to database"
                    )
            except Exception as e:
                logger.error(f"[STREAM] Database error storing assistant message: {e}")

        logger.info(
            f"[STREAM] Stream complete. Total events: {event_count}, cache_hit: {cache_hit}"
        )
        logger.info("[CHAT API] ========== CHAT REQUEST COMPLETE ==========")

        try:
            tracer.persist()
        except Exception:
            logger.warning("AuditTracer.persist() failed (stream handler)", exc_info=True)

        # Record latency at end of stream
        total_ms = (perf_counter() - request_start) * 1000
        record_latency(
            conversation_id=conversation_id,
            mode=request.mode,
            total_ms=total_ms,
            ttft_ms=ttft_ms,
            cache_hit=cache_hit,
        )

        # Clean up cancel event registration
        if cancel_event is not None:
            CANCEL_EVENTS.pop(conversation_id, None)

        # Emit final summary event with cache status and AI metadata before DONE
        yield f"data: {json.dumps({'type': 'stream_complete', 'cache_hit': cache_hit, 'event_count': event_count, 'model_id': stream_model_id, 'provider': stream_provider, 'orchestration_mode': stream_orchestration_mode})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

class ConversationHistoryResponse(BaseModel):
    """Paginated conversation history response."""

    messages: list[Message] = Field(..., description="List of messages in chronological order")
    total: int = Field(..., description="Total number of messages in conversation", ge=0)
    has_more: bool = Field(..., description="True if more messages available after this page")

@router.get(
    "/history/{conversation_id}",
    response_model=ConversationHistoryResponse,
    responses=response_with_errors(400, 401, 403, 404),
    summary="Get conversation history",
)
async def get_history(
    conversation_id: str,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationHistoryResponse:
    """Get chat history for a conversation with pagination.

    Returns messages in chronological order (oldest first).
    Maximum 100 messages per request.
    Users can only access their own conversations. Admins can access all.
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    # Validate pagination parameters
    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset must be non-negative")

    # Check if conversation exists
    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Ownership check: user must own conversation or be admin
    user_id = user.get("sub")
    if user.get("role") != "admin" and conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Count total messages
    total = db.query(DBMessage).filter(DBMessage.conversation_id == conversation_id).count()

    # Get messages with eager loading of tool results
    messages = (
        db.query(DBMessage)
        .options(joinedload(DBMessage.tool_results))
        .filter(DBMessage.conversation_id == conversation_id)
        .order_by(DBMessage.created_at)
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Convert to response format, extracting thinking, cached, and tool_calls from metadata/relations
    message_list = []
    for msg in messages:
        metadata = msg.metadata_ or {}
        ts = msg.created_at.isoformat()

        # Convert tool_results relation to tool_calls response format
        tool_calls = []
        if msg.role == "assistant" and msg.tool_results:
            for tr in msg.tool_results:
                tool_calls.append(
                    MessageToolCall(
                        tool=tr.tool_name,
                        args=tr.arguments or {},
                        result=tr.result,
                        status="error" if not tr.success else "complete",
                        duration_ms=tr.duration_ms,
                    )
                )

        message_list.append(
            Message(
                id=str(msg.id),
                role=msg.role,
                content=msg.content or "",
                timestamp=ts,
                created_at=ts,
                thinking=metadata.get("thinking") if msg.role == "assistant" else None,
                cached=metadata.get("cached", False) if msg.role == "assistant" else False,
                tool_calls=tool_calls,
            )
        )

    return ConversationHistoryResponse(
        messages=message_list, total=total, has_more=(offset + len(messages)) < total
    )

@router.delete(
    "/history/{conversation_id}",
    status_code=204,
    responses=response_with_errors(400, 500),
    summary="Clear conversation history",
)
async def clear_history(conversation_id: str, db: Session = Depends(get_db)) -> None:
    """Clear chat history for a conversation.

    Deletes the conversation and all associated messages.
    Returns 204 No Content on success.
    """
    import logging

    logger = logging.getLogger("dryade.chat.delete")

    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    try:
        # Delete conversation (cascade will delete messages)
        conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
        if conversation:
            user_id = conversation.user_id
            db.delete(conversation)
            db.commit()
            logger.info(
                f"Deleted conversation {conversation_id} for user {user_id} at {utcnow().isoformat()}"
            )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to clear conversation history. Please try again.",
        ) from e

class ConversationSummary(BaseModel):
    """Summary of a single conversation."""

    id: str = Field(..., description="Unique conversation identifier (UUID)")
    title: str | None = Field(
        None, description="Conversation title (first 50 chars of first message)"
    )
    mode: str = Field(..., description="Execution mode (chat, crew, flow, planner)")
    status: str = Field(..., description="Conversation status (active, archived)")
    message_count: int = Field(..., description="Total number of messages in conversation", ge=0)
    created_at: str = Field(..., description="ISO 8601 timestamp when conversation started")
    updated_at: str = Field(..., description="ISO 8601 timestamp of last activity")

class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""

    conversations: list[ConversationSummary] = Field(
        ..., description="List of conversation summaries"
    )
    total: int = Field(..., description="Total number of conversations", ge=0)

@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    responses=response_with_errors(400, 401),
    summary="List conversations",
)
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    """List conversations with message counts.

    Users see only their own conversations. Admins see all.
    Returns conversations sorted by most recent activity.
    Maximum 100 conversations per request.
    """
    # Validate pagination parameters
    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 100")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset must be non-negative")

    user_id = user.get("sub")

    # Build query - filter by owner unless admin
    query = db.query(DBConversation)
    if user.get("role") != "admin":
        query = query.filter(DBConversation.user_id == user_id)

    # Count total
    total = query.count()

    # Get conversations
    conversations = (
        query.order_by(DBConversation.updated_at.desc()).limit(limit).offset(offset).all()
    )

    # Build response with message counts
    summaries = []
    for conv in conversations:
        message_count = db.query(DBMessage).filter(DBMessage.conversation_id == conv.id).count()

        summaries.append(
            ConversationSummary(
                id=conv.id,
                title=conv.title,
                mode=conv.mode,
                status=conv.status,
                message_count=message_count,
                created_at=conv.created_at.isoformat(),
                updated_at=conv.updated_at.isoformat(),
            )
        )

    return ConversationListResponse(conversations=summaries, total=total)

@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationSummary,
    responses=response_with_errors(400, 401, 403, 404),
    summary="Get single conversation",
)
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationSummary:
    """Get a single conversation by ID.

    Users can only access their own conversations. Admins can access all.
    Returns 404 if conversation not found or 403 if access denied.
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    # Get conversation
    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Ownership check: user must own conversation or be admin
    user_id = user.get("sub")
    if user.get("role") != "admin" and conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Count messages
    message_count = db.query(DBMessage).filter(DBMessage.conversation_id == conversation.id).count()

    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        mode=conversation.mode,
        status=conversation.status,
        message_count=message_count,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )

class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""

    title: str | None = Field(None, description="New conversation title", max_length=200)
    mode: str | None = Field(None, description="Chat mode: chat, crew, flow, planner")

@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationSummary,
    responses=response_with_errors(400, 401, 403, 404, 500),
    summary="Update conversation",
)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationSummary:
    """Update a conversation's title.

    Users can only update their own conversations. Admins can update all.
    Returns 404 if conversation not found or 403 if access denied.
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    # Get conversation
    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Ownership check: user must own conversation or be admin
    user_id = user.get("sub")
    if user.get("role") != "admin" and conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Update fields
    if request.title is not None:
        conversation.title = request.title
    if request.mode is not None:
        conversation.mode = request.mode

    try:
        db.commit()
        db.refresh(conversation)
    except Exception as e:
        db.rollback()
        logger.exception(f"Error updating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to update conversation") from e

    # Count messages
    message_count = db.query(DBMessage).filter(DBMessage.conversation_id == conversation.id).count()

    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        mode=conversation.mode,
        status=conversation.status,
        message_count=message_count,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )

class MoveToProjectRequest(BaseModel):
    """Request to move a conversation to a project."""

    project_id: str | None = Field(
        ..., description="Project ID to move to, or null to remove from project"
    )

class MoveToProjectResponse(BaseModel):
    """Response from moving a conversation to a project."""

    id: str
    title: str | None
    project_id: str | None
    message: str

class BulkDeleteRequest(BaseModel):
    """Request to bulk delete conversations."""

    conversation_ids: list[str] = Field(..., min_length=1, max_length=100)

class BulkDeleteResponse(BaseModel):
    """Response from bulk delete operation."""

    deleted_count: int
    failed_ids: list[str] = Field(default_factory=list)
    message: str

class DeleteAllConversationsResponse(BaseModel):
    """Response from delete all conversations operation."""

    deleted_count: int
    message: str

@router.patch(
    "/conversations/{conversation_id}/project",
    response_model=MoveToProjectResponse,
    responses=response_with_errors(400, 401, 403, 404, 500),
    summary="Move conversation to project",
    description="Assign or remove a conversation from a project.",
)
async def move_conversation_to_project(
    conversation_id: str,
    request: MoveToProjectRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MoveToProjectResponse:
    """Move a conversation to a project or remove from project.

    Args:
        conversation_id: Conversation UUID
        request: Project ID to move to (or null to remove)

    Returns:
        Updated conversation with project assignment

    Raises:
        404: Conversation or project not found
        403: Access denied
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    user_id = user.get("sub")

    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Ownership check: user must own conversation or be admin
    if user.get("role") != "admin" and conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    project_id = request.project_id

    # Validate project exists if provided
    if project_id:
        project = (
            db.query(DBProject)
            .filter(DBProject.id == project_id, DBProject.user_id == user_id)
            .first()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    try:
        conversation.project_id = project_id
        db.commit()
        db.refresh(conversation)

        return MoveToProjectResponse(
            id=conversation.id,
            title=conversation.title,
            project_id=conversation.project_id,
            message=f"Conversation {'moved to project' if project_id else 'removed from project'}",
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error moving conversation to project: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to move conversation. Please try again."
        ) from e

@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=201,
    responses=response_with_errors(400, 401, 500),
    summary="Create new conversation",
)
async def create_conversation(
    request: CreateConversationRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationSummary:
    """Create a new conversation.

    Creates an empty conversation that can be populated with messages.
    Returns 201 with the created conversation.
    """
    user_id = user.get("sub")
    conversation_id = str(uuid.uuid4())

    try:
        conversation = DBConversation(
            id=conversation_id,
            user_id=user_id,
            title=request.title or "New Conversation",
            mode=request.mode,
            status="active",
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            mode=conversation.mode,
            status=conversation.status,
            message_count=0,
            created_at=conversation.created_at.isoformat(),
            updated_at=conversation.updated_at.isoformat(),
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error creating conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create conversation. Please try again.",
        ) from e

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=Message,
    status_code=201,
    responses=response_with_errors(400, 401, 403, 404, 500),
    summary="Add message to conversation",
)
async def add_message_to_conversation(
    conversation_id: str,
    request: AddMessageRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    """Add a message to a conversation without triggering LLM response.

    Useful for manually constructing conversation history.
    Returns 201 with the created message.
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    # Verify conversation exists and belongs to user
    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = user.get("sub")
    if user.get("role") != "admin" and conversation.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        message = DBMessage(
            conversation_id=conversation_id,
            role=request.role,
            content=request.content,
            metadata_={"timestamp": utcnow().isoformat()},
        )
        db.add(message)
        conversation.updated_at = utcnow()
        db.commit()
        db.refresh(message)

        return Message(
            id=str(message.id),
            role=message.role,
            content=message.content or "",
            timestamp=message.created_at.isoformat(),
            created_at=message.created_at.isoformat(),
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error adding message to conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to add message. Please try again.",
        ) from e

@router.patch(
    "/conversations/{conversation_id}/share",
    response_model=dict[str, str],
    responses=response_with_errors(400, 401, 403, 404, 500),
    summary="Share conversation with user",
)
async def share_conversation(
    conversation_id: str,
    request: ShareConversationRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Share a conversation with another user.

    Only the conversation owner can share. Creates a ResourceShare record.
    Returns success message on completion.
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    # Verify conversation exists and belongs to user (owner only can share)
    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = user.get("sub")
    if conversation.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Only conversation owner can share conversations"
        )

    try:
        # Check if share already exists
        existing_share = (
            db.query(DBResourceShare)
            .filter(
                DBResourceShare.resource_type == "conversation",
                DBResourceShare.resource_id == conversation_id,
                DBResourceShare.user_id == request.user_id,
            )
            .first()
        )

        if existing_share:
            # Update permission if different
            if existing_share.permission != request.permission:
                existing_share.permission = request.permission
                db.commit()
                return {"message": "Conversation share permission updated"}
            return {"message": "Conversation already shared with this user"}

        # Create new share record
        share = DBResourceShare(
            resource_type="conversation",
            resource_id=conversation_id,
            user_id=request.user_id,
            permission=request.permission,
            shared_by=user_id,
        )
        db.add(share)
        db.commit()
        return {"message": "Conversation shared successfully"}
    except Exception as e:
        db.rollback()
        logger.exception(f"Error sharing conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to share conversation. Please try again.",
        ) from e

@router.delete(
    "/conversations/{conversation_id}/share/{user_id}",
    response_model=dict[str, str],
    responses=response_with_errors(400, 401, 403, 404),
    summary="Unshare conversation from user",
)
async def unshare_conversation(
    conversation_id: str,
    user_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Unshare a conversation from a user.

    Only the conversation owner can unshare. Deletes the ResourceShare record.
    Returns success message even if share didn't exist.
    """
    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    # Verify conversation exists and belongs to user (owner only)
    conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    current_user_id = user.get("sub")
    if conversation.user_id != current_user_id:
        raise HTTPException(
            status_code=403, detail="Only conversation owner can unshare conversations"
        )

    try:
        # Delete share record
        share = (
            db.query(DBResourceShare)
            .filter(
                DBResourceShare.resource_type == "conversation",
                DBResourceShare.resource_id == conversation_id,
                DBResourceShare.user_id == user_id,
            )
            .first()
        )
        if share:
            db.delete(share)
            db.commit()
            return {"message": "Conversation unshared successfully"}
        return {"message": "Conversation was not shared with this user"}
    except Exception as e:
        db.rollback()
        logger.exception(f"Error unsharing conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to unshare conversation. Please try again.",
        ) from e

@router.delete(
    "/conversations/bulk",
    response_model=BulkDeleteResponse,
    responses=response_with_errors(400, 401, 500),
    summary="Bulk delete conversations",
)
async def bulk_delete_conversations(
    request: BulkDeleteRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BulkDeleteResponse:
    """Bulk delete multiple conversations by ID.

    Deletes up to 100 conversations at once. Only deletes conversations
    owned by the authenticated user (or all if admin).
    Returns count of deleted conversations and list of any failed IDs.
    """
    user_id = user.get("sub")
    is_admin = user.get("role") == "admin"

    deleted_count = 0
    failed_ids = []

    for conv_id in request.conversation_ids:
        try:
            # Validate UUID format
            uuid.UUID(conv_id)

            # Get conversation
            conversation = db.query(DBConversation).filter_by(id=conv_id).first()
            if not conversation:
                failed_ids.append(conv_id)
                continue

            # Check ownership (unless admin)
            if not is_admin and conversation.user_id != user_id:
                failed_ids.append(conv_id)
                continue

            # Delete conversation (cascade deletes messages)
            db.delete(conversation)
            deleted_count += 1

        except ValueError:
            # Invalid UUID format
            failed_ids.append(conv_id)
        except Exception as e:
            logger.warning(f"Failed to delete conversation {conv_id}: {e}")
            failed_ids.append(conv_id)

    try:
        db.commit()
        logger.info(
            f"Bulk deleted {deleted_count} conversations for user {user_id} "
            f"at {utcnow().isoformat()}"
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error committing bulk delete: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete conversations. Please try again.",
        ) from e

    return BulkDeleteResponse(
        deleted_count=deleted_count,
        failed_ids=failed_ids,
        message=f"Deleted {deleted_count} conversation(s)"
        + (f", {len(failed_ids)} failed" if failed_ids else ""),
    )

@router.delete(
    "/conversations/all",
    response_model=DeleteAllConversationsResponse,
    responses=response_with_errors(401, 500),
    summary="Delete all conversations",
)
async def delete_all_conversations(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteAllConversationsResponse:
    """Delete ALL conversations for the authenticated user.

    This is a destructive operation that permanently removes all
    conversations and their messages. Use with caution.
    """
    user_id = user.get("sub")

    try:
        # Count before delete for response
        count = db.query(DBConversation).filter(DBConversation.user_id == user_id).count()

        # Delete messages first (FK constraint), then conversations
        conv_ids = [
            c.id
            for c in db.query(DBConversation.id).filter(DBConversation.user_id == user_id).all()
        ]
        if conv_ids:
            db.query(DBMessage).filter(DBMessage.conversation_id.in_(conv_ids)).delete(
                synchronize_session=False
            )
        db.query(DBConversation).filter(DBConversation.user_id == user_id).delete(
            synchronize_session=False
        )
        db.commit()

        logger.info(
            f"Deleted all {count} conversations for user {user_id} at {utcnow().isoformat()}"
        )

        return DeleteAllConversationsResponse(
            deleted_count=count,
            message=f"Deleted all {count} conversation(s)",
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting all conversations for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete conversations. Please try again.",
        ) from e

@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    responses=response_with_errors(400, 404, 500),
    summary="Delete conversation",
)
async def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a conversation and all its messages.

    Cascade deletes all messages and tool results associated with the conversation.
    Returns 204 No Content on success, 404 if conversation not found.
    """
    import logging

    logger = logging.getLogger("dryade.chat.delete")

    # Validate conversation_id format
    try:
        uuid.UUID(conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format") from e

    try:
        # Delete conversation (cascade will delete messages and tool results)
        conversation = db.query(DBConversation).filter_by(id=conversation_id).first()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        user_id = conversation.user_id
        db.delete(conversation)
        db.commit()
        logger.info(
            f"Admin deleted conversation {conversation_id} for user {user_id} at {utcnow().isoformat()}"
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete conversation. Please try again.",
        ) from e

@router.get(
    "/modes",
    summary="List execution modes",
)
async def list_modes() -> dict[str, Any]:
    """List available execution modes.

    NOTE: Frontend 'chat' mode maps to backend ExecutionMode.ORCHESTRATE.
    The orchestrator handles all messages including simple chat.
    Frontend 'planner' maps to backend ExecutionMode.PLANNER.
    """
    return {
        "modes": [
            {
                "name": "chat",
                "description": "Conversation with AI (auto-routes to agents when needed)",
                "default": True,
            },
            {
                "name": "planner",
                "description": "AI-generated workflow plan with approval flow",
                "default": False,
            },
        ]
    }

# -----------------------------------------------------------------------------
# Clarification & State Conflict Resolution Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/clarify",
    responses=response_with_errors(404),
    summary="Submit clarification response",
)
async def submit_clarification(request: ClarifyRequest) -> dict[str, bool]:
    """Submit a response to a pending clarification request.

    Called when the frontend receives a 'clarify' event and the user provides a response.
    Routes to autonomous mode handler first if there's a pending autonomous clarification,
    otherwise falls back to the standard clarification handler.
    Returns 404 if no pending clarification exists for the conversation.
    """
    from core.autonomous.chat_adapter import (
        has_pending_autonomous_clarification,
        submit_autonomous_clarification,
    )
    from core.extensions import ClarificationResponse, submit_clarification

    response = ClarificationResponse(
        value=request.response, selected_option=request.selected_option
    )

    # Check autonomous mode first (separate from planner/flow mode clarifications)
    if has_pending_autonomous_clarification(request.conversation_id):
        found = submit_autonomous_clarification(request.conversation_id, response)
        if found:
            logger.info(
                f"[clarify] Submitted autonomous clarification for {request.conversation_id}"
            )
            return {"success": True}

    # Fall back to standard clarification handler (planner/flow modes)
    found = submit_clarification(request.conversation_id, response)
    if not found:
        raise HTTPException(status_code=404, detail="No pending clarification found")

    return {"success": True}

@router.post(
    "/resolve-state-conflict",
    responses=response_with_errors(404),
    summary="Resolve state conflict",
)
async def resolve_state_conflict(request: StateConflictResolutionRequest) -> dict[str, bool]:
    """Submit a resolution to a pending state conflict.

    Called when the frontend receives a 'state_conflict' event and the user selects a value.
    Returns 404 if no pending state conflict exists.
    """
    from core.extensions import submit_state_conflict_resolution
    from core.extensions.state import get_state_store

    # Submit to async wait mechanism
    found = submit_state_conflict_resolution(
        request.conversation_id, request.state_key, request.selected_value
    )

    if not found:
        # Also try to resolve directly in state store (for non-streaming contexts)
        store = get_state_store()
        resolved = store.resolve_conflict(request.state_key, request.selected_value)
        if not resolved:
            raise HTTPException(status_code=404, detail="No pending state conflict found")

    return {"success": True}

@router.get(
    "/pending-conflicts/{conversation_id}",
    summary="Get pending conflicts",
)
async def get_pending_conflicts(conversation_id: str) -> dict[str, Any]:
    """Get any pending clarification or state conflict for a conversation.

    Returns status of pending clarifications and list of unresolved state conflicts.
    """
    from core.extensions import has_pending_clarification
    from core.extensions.state import get_state_store

    store = get_state_store()
    conflicts = store.get_all_conflicts()

    return {
        "has_pending_clarification": has_pending_clarification(conversation_id),
        "state_conflicts": [
            {
                "state_key": c.state_key,
                "candidates": [
                    {"value": sv.value, "source": sv.source, "label": sv.label}
                    for sv in c.candidates
                ],
                "required_by": c.required_by,
            }
            for c in conflicts
        ],
    }

# ============================================================================
# Image Upload for Vision Analysis
# ============================================================================

_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

@router.post(
    "/{conversation_id}/upload",
    responses=response_with_errors(400, 413, 415),
    summary="Upload an image for vision analysis",
)
async def upload_image(
    conversation_id: str,
    file: UploadFile = File(...),
    user: Any = Depends(get_current_user),
) -> dict:
    """Upload an image to attach to the next chat message for vision analysis.

    Accepts PNG, JPEG, GIF, and WebP images up to 10MB.
    Returns base64-encoded image data with metadata.
    SVG is rejected (XSS vector). EXIF data is stripped for privacy.
    """
    import base64
    import io

    try:
        from PIL import Image as PILImage
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Pillow (PIL) is required for image upload. Install with: pip install Pillow",
        )

    # Read file content
    content = await file.read()

    # Size check
    if len(content) > _MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Maximum size is {_MAX_IMAGE_SIZE // (1024 * 1024)}MB.",
        )

    # MIME type check
    mime_type = file.content_type or ""
    if mime_type not in _ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{mime_type}'. Allowed: {', '.join(sorted(_ALLOWED_IMAGE_MIMES))}",
        )

    # Validate it's actually an image using Pillow
    try:
        img = PILImage.open(io.BytesIO(content))
        img.verify()
        # Re-open after verify (verify consumes the image)
        img = PILImage.open(io.BytesIO(content))
        width, height = img.size
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="File is not a valid image or is corrupted.",
        )

    # Strip EXIF data by re-saving without metadata
    output = io.BytesIO()
    # Convert to RGB if needed (strips alpha for JPEG compat, keeps PNG as-is)
    if img.mode in ("RGBA", "LA", "P") and mime_type == "image/jpeg":
        img = img.convert("RGB")
    img.save(output, format=img.format or "PNG")
    clean_content = output.getvalue()

    # Encode to base64
    b64_data = base64.b64encode(clean_content).decode("ascii")

    return {
        "image_id": str(uuid.uuid4()),
        "base64": b64_data,
        "mime_type": mime_type,
        "width": width,
        "height": height,
    }
