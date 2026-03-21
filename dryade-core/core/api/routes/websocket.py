"""WebSocket Routes - Bidirectional streaming for chat and flows.

Features:
- Message sequencing with server-assigned sequence numbers
- Bounded message buffer for replay on reconnection
- Acknowledgment system with configurable retry logic
- Reconnection protocol with session resume
- Server-initiated heartbeat with timeout detection
- JWT authentication via query param or Authorization header
- Per-connection rate limiting with token bucket algorithm

Environment Variables:
- DRYADE_WS_BUFFER_SIZE: Max buffered messages per connection (default 100)
- DRYADE_WS_ACK_TIMEOUT_S: Timeout before retry in seconds (default 30.0)
- DRYADE_WS_MAX_RETRIES: Max retry attempts per message (default 3)
- DRYADE_WS_RETRY_INTERVAL_S: Retry check interval in seconds (default 5.0)
- DRYADE_WS_SESSION_TTL_S: Session preservation time after disconnect (default 300.0)
- DRYADE_WS_HANDSHAKE_TIMEOUT_S: Timeout for initial handshake (default 5.0)
- DRYADE_WS_HEARTBEAT_S: Heartbeat interval in seconds (default 30.0)
- DRYADE_WS_HEARTBEAT_TIMEOUT_S: Timeout before disconnect in seconds (default 90.0)
- DRYADE_WS_RATE_LIMIT_BURST: Max burst messages per connection (default 60)
- DRYADE_WS_RATE_LIMIT_PER_SEC: Token refill rate per second (default 1.0)
"""

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.api.routes.provider_health import CANCEL_EVENTS
from core.config import get_settings
from core.flows import FLOW_REGISTRY
from core.orchestrator.router import route_request
from core.utils.time import utcnow

logger = logging.getLogger(__name__)
router = APIRouter()

# Configuration from centralized Settings
_ws_settings = get_settings()
WS_BUFFER_SIZE = _ws_settings.ws_buffer_size
WS_ACK_TIMEOUT_S = _ws_settings.ws_ack_timeout_s
WS_MAX_RETRIES = _ws_settings.ws_max_retries
WS_RETRY_INTERVAL_S = _ws_settings.ws_retry_interval_s
WS_SESSION_TTL_S = _ws_settings.ws_session_ttl_s
WS_HANDSHAKE_TIMEOUT_S = _ws_settings.ws_handshake_timeout_s
HEARTBEAT_INTERVAL_S = _ws_settings.ws_heartbeat_s
HEARTBEAT_TIMEOUT_S = _ws_settings.ws_heartbeat_timeout_s
WS_RATE_LIMIT_BURST = _ws_settings.ws_rate_limit_burst
WS_RATE_LIMIT_PER_SEC = _ws_settings.ws_rate_limit_per_sec

class WebSocketAuthError(Exception):
    """Authentication failed for WebSocket connection."""

    pass

@dataclass
class RateLimiter:
    """Token bucket rate limiter for WebSocket messages."""

    max_tokens: int = field(default=WS_RATE_LIMIT_BURST)
    refill_rate: float = field(default=WS_RATE_LIMIT_PER_SEC)
    tokens: float = field(default_factory=lambda: float(WS_RATE_LIMIT_BURST))
    last_refill: float = field(default_factory=time.time)

    def consume(self, count: int = 1) -> bool:
        """Attempt to consume tokens. Returns False if rate limited."""
        now = time.time()
        # Refill tokens based on elapsed time
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        # Try to consume
        if self.tokens >= count:
            self.tokens -= count
            return True
        return False

async def authenticate_websocket(websocket: WebSocket) -> str | None | str:
    """Authenticate WebSocket connection via query param or header.

    Returns:
        - user_id (str) on success (query param or header auth worked)
        - None if auth is disabled
        - "pending" if no token found in query/header (caller should try first-message auth)
        - Raises WebSocketAuthError on invalid/expired token
    """
    settings = get_settings()

    # Auth disabled when not enabled or no jwt_secret configured
    if not settings.auth_enabled or not settings.jwt_secret:
        return None

    # Try query param first (backward compat for existing clients)
    token = websocket.query_params.get("token")

    # Fall back to Authorization header
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        # No token in query/header — caller should try first-message auth after accept
        return "pending"

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub") or payload.get("user_id")
    except jwt.ExpiredSignatureError as e:
        # Must accept before closing with custom code
        await websocket.accept()
        await websocket.close(code=4003, reason="Token expired")
        raise WebSocketAuthError("Token expired") from e
    except jwt.InvalidTokenError as e:
        # Must accept before closing with custom code
        await websocket.accept()
        await websocket.close(code=4003, reason="Invalid token")
        raise WebSocketAuthError(f"Token validation failed: {e}") from e

def validate_first_message_token(token: str) -> str | None:
    """Validate a JWT token from first-message auth.

    Returns user_id on success, None on failure.
    """
    settings = get_settings()
    if not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub") or payload.get("user_id")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        logger.warning(f"First-message auth token validation failed: {e}")
        return None

class ServerMessage(BaseModel):
    """Envelope for all server-to-client WebSocket messages.

    Provides sequence numbers for reliable delivery and acknowledgment tracking.
    """

    seq: int = Field(..., description="Server sequence number for ordering and ack")
    type: str = Field(..., description="Message type (token, complete, error, pong, etc.)")
    data: dict[str, Any] = Field(default_factory=dict, description="Message payload")
    timestamp: float = Field(..., description="Unix timestamp when message was created")

@dataclass
class WebSocketSession:
    """Per-connection state for message sequencing and reliability.

    Tracks sequence numbers, buffers recent messages, and manages
    unacknowledged messages for retry logic.
    """

    client_id: str
    websocket: WebSocket | None = None  # None when session is disconnected but preserved
    server_seq: int = 0  # Next server->client sequence number
    client_seq: int = 0  # Last received client->server sequence number
    buffer: deque[tuple[int, dict]] = field(default_factory=lambda: deque(maxlen=WS_BUFFER_SIZE))
    # unacked: seq -> (message_dict, sent_time, retry_count)
    unacked: dict[int, tuple[dict, float, int]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)  # For heartbeat timeout detection
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)
    user_id: str | None = None  # From authentication

class SessionStore:
    """Store disconnected sessions for reconnection."""

    def __init__(self, ttl_seconds: float = 300.0):
        """Initialize session store with TTL.

        Args:
            ttl_seconds: Time-to-live for disconnected sessions
        """
        self._sessions: dict[str, WebSocketSession] = {}
        self._disconnect_times: dict[str, float] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def save_for_reconnect(self, session: WebSocketSession):
        """Preserve session state on disconnect."""
        session.websocket = None  # Clear stale websocket
        with self._lock:
            self._sessions[session.client_id] = session
            self._disconnect_times[session.client_id] = time.time()

    def restore(self, client_id: str) -> WebSocketSession | None:
        """Restore session if not expired."""
        with self._lock:
            if client_id not in self._sessions:
                return None
            if time.time() - self._disconnect_times[client_id] > self._ttl:
                self._sessions.pop(client_id, None)
                self._disconnect_times.pop(client_id, None)
                return None
            return self._sessions.pop(client_id)

    def cleanup(self, client_id: str):
        """Remove session from store."""
        with self._lock:
            self._sessions.pop(client_id, None)
            self._disconnect_times.pop(client_id, None)

# Singleton session store for reconnection support
session_store = SessionStore(ttl_seconds=WS_SESSION_TTL_S)

class ConnectionManager:
    """Manage WebSocket connections with sequencing and reliability."""

    def __init__(self):
        """Initialize connection manager with empty registries."""
        self.active: dict[str, WebSocket] = {}
        self.sessions: dict[str, WebSocketSession] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str) -> WebSocketSession:
        """Accept connection and create session with initialized state.

        Handles collision: if client_id already has an active connection,
        the old connection is closed before being replaced (code 4002).
        """
        async with self._lock:
            # Close existing connection if present (collision handling)
            if client_id in self.active:
                old_ws = self.active[client_id]
                try:
                    await old_ws.close(code=4002, reason="Replaced by new connection")
                except Exception:
                    pass  # Old connection may already be closed
            await websocket.accept()
            self.active[client_id] = websocket
            session = WebSocketSession(client_id=client_id, websocket=websocket)
            self.sessions[client_id] = session
            return session

    async def disconnect(self, client_id: str):
        """Remove connection and session state."""
        async with self._lock:
            self.active.pop(client_id, None)
            self.sessions.pop(client_id, None)

    def get_session(self, client_id: str) -> WebSocketSession | None:
        """Return session by client_id, or None if not found."""
        return self.sessions.get(client_id)

    def buffer_message(self, session: WebSocketSession, seq: int, message: dict):
        """Add message to rolling buffer (bounded by maxlen)."""
        session.buffer.append((seq, message))

    async def send_sequenced(
        self, session: WebSocketSession, msg_type: str, data: dict[str, Any]
    ) -> int:
        """Send message with sequence number envelope.

        Assigns incrementing sequence number, wraps in ServerMessage envelope,
        buffers for potential replay, and tracks for acknowledgment.

        Returns the assigned sequence number.
        """
        seq = session.server_seq
        session.server_seq += 1

        envelope = ServerMessage(seq=seq, type=msg_type, data=data, timestamp=time.time())
        message_dict = envelope.model_dump()

        # Buffer for replay on reconnect
        self.buffer_message(session, seq, message_dict)

        # Track for ack/retry
        session.unacked[seq] = (message_dict, time.time(), 0)

        # Send to client
        await session.websocket.send_json(message_dict)
        session.last_activity = time.time()

        return seq

    async def send(self, client_id: str, message: dict[str, Any]):
        """Legacy send without sequencing (for backward compatibility)."""
        async with self._lock:
            websocket = self.active.get(client_id)
        if websocket:
            await websocket.send_json(message)

    async def broadcast(self, message: dict[str, Any]):
        """Broadcast to all connections (legacy, no sequencing)."""
        async with self._lock:
            connections = list(self.active.values())
        for ws in connections:
            await ws.send_json(message)

manager = ConnectionManager()

async def retry_unacked(session: WebSocketSession) -> int:
    """Retry unacked messages after timeout.

    Iterates through unacked messages and resends those that have exceeded
    the ack timeout. Messages that exceed max retries are dropped with a warning.

    Returns:
        Number of messages retried this iteration.
    """
    now = time.time()
    retried_count = 0

    # Use list() to allow dict modification during iteration
    for seq, (message, sent_time, retry_count) in list(session.unacked.items()):
        if now - sent_time > WS_ACK_TIMEOUT_S:
            if retry_count >= WS_MAX_RETRIES:
                # Give up after max retries
                logger.warning(
                    f"Message {seq} for client {session.client_id} failed "
                    f"after {WS_MAX_RETRIES} retries, dropping"
                )
                del session.unacked[seq]
            else:
                # Resend with incremented retry count
                try:
                    await session.websocket.send_json(message)
                    session.unacked[seq] = (message, now, retry_count + 1)
                    retried_count += 1
                    logger.debug(
                        f"Retrying message {seq} for client {session.client_id} "
                        f"(attempt {retry_count + 1})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to retry message {seq} for client {session.client_id}: {e}"
                    )

    return retried_count

async def periodic_retry(session: WebSocketSession):
    """Background task that periodically checks for and retries unacked messages.

    Runs until cancelled, checking every WS_RETRY_INTERVAL_S seconds.
    """
    try:
        while True:
            await asyncio.sleep(WS_RETRY_INTERVAL_S)
            await retry_unacked(session)
    except asyncio.CancelledError:
        logger.debug(f"Retry task cancelled for client {session.client_id}")
        raise

def handle_ack(session: WebSocketSession, ack_seq: int) -> bool:
    """Handle acknowledgment from client.

    Removes the acknowledged message from the unacked dict.

    Returns:
        True if ack was valid (message existed), False otherwise.
    """
    if ack_seq in session.unacked:
        del session.unacked[ack_seq]
        session.last_activity = time.time()
        return True
    else:
        logger.debug(f"Received ack for unknown seq {ack_seq} from client {session.client_id}")
        return False

async def handle_initial_message(
    websocket: WebSocket, client_id: str, *, auth_pending: bool = False
) -> tuple[WebSocketSession | None, int, dict | None, str | None]:
    """Handle first message to determine new vs resume vs auth session.

    Waits for initial handshake message with very short timeout (100ms, or 5s if auth_pending).
    If client sends {"type": "resume", "last_seq": N} as first message, attempts to restore session.
    If client sends {"type": "auth", "token": "..."} as first message, validates the token.
    Otherwise assumes new session.

    Args:
        websocket: The accepted WebSocket connection.
        client_id: The connection identifier (conversation_id or execution_id).
        auth_pending: If True, extends timeout to 5s to wait for first-message auth.

    Returns:
        Tuple of (restored_session or None, last_seq, consumed_data or None, auth_user_id or None).
        consumed_data is non-None when a non-resume/non-auth message arrived during the
        handshake window and must be processed by the caller.

    Raises:
        WebSocketDisconnect: If client disconnects during handshake wait.
    """
    # Use longer timeout when waiting for first-message auth
    timeout = 5.0 if auth_pending else 0.1
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=timeout)
    except TimeoutError:
        # Assume new session if no message within timeout
        return None, 0, None, None
    # Let WebSocketDisconnect propagate to caller

    if data.get("type") == "resume":
        last_seq = data.get("last_seq", 0)
        return session_store.restore(client_id), last_seq, None, None

    if data.get("type") == "auth":
        token = data.get("token")
        if token:
            user_id = validate_first_message_token(token)
            return None, 0, None, user_id
        return None, 0, None, None

    # Non-resume/non-auth message consumed during handshake — return it so the caller
    # can process it in the main loop instead of silently dropping it.
    return None, 0, data, None

async def replay_missed_messages(session: WebSocketSession, from_seq: int) -> int:
    """Replay buffered messages from sequence number.

    Sends all messages in the buffer with seq > from_seq.

    Returns:
        Number of messages replayed.
    """
    replayed = 0
    for seq, message in session.buffer:
        if seq > from_seq:
            await session.websocket.send_json(message)
            replayed += 1
    return replayed

async def heartbeat_loop(session: WebSocketSession):
    """Send periodic heartbeats and detect timeouts.

    Runs until cancelled, sending heartbeat every HEARTBEAT_INTERVAL_S seconds.
    Closes connection if no pong received within HEARTBEAT_TIMEOUT_S.
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)

            # Check for timeout (no pong received)
            if time.time() - session.last_pong > HEARTBEAT_TIMEOUT_S:
                logger.warning(f"Session {session.client_id} heartbeat timeout")
                if session.websocket:
                    await session.websocket.close(code=1008, reason="Heartbeat timeout")
                break

            # Send heartbeat
            try:
                await manager.send_sequenced(
                    session,
                    "heartbeat",
                    {
                        "server_time": time.time(),
                    },
                )
            except Exception as e:
                logger.warning(f"Heartbeat send failed for {session.client_id}: {e}")
                break
    except asyncio.CancelledError:
        logger.debug(f"Heartbeat task cancelled for client {session.client_id}")
        raise

def is_connection_healthy(session: WebSocketSession) -> bool:
    """Check if connection is responsive.

    Returns True if last pong was received within HEARTBEAT_TIMEOUT_S.
    """
    return time.time() - session.last_pong < HEARTBEAT_TIMEOUT_S

@router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    """Bidirectional chat WebSocket with message sequencing and acknowledgments.

    Supports reconnection: client sends {"type": "resume", "last_seq": N} as first message.
    Server responds with {"type": "resumed", "from_seq": N, "replay_count": M} or
    {"type": "new_session", "session_id": "..."} for new connections.

    Authentication: Token via query param (?token=...) or Authorization header.
    Auth disabled when JWT_SECRET not configured (matches REST API pattern).

    Client ack format: {"type": "ack", "seq": N}
    Server messages wrapped in ServerMessage envelope with incrementing seq.
    """
    # Authenticate before accepting connection
    try:
        user_id = await authenticate_websocket(websocket)
    except WebSocketAuthError:
        return  # Already closed with error code

    auth_pending = user_id == "pending"
    if auth_pending:
        user_id = None

    await websocket.accept()

    # Handle reconnection/auth handshake
    restored_session, last_seq, initial_data, first_msg_user_id = await handle_initial_message(
        websocket, conversation_id, auth_pending=auth_pending
    )

    # Resolve user_id from first-message auth if query/header auth was pending
    if auth_pending:
        if first_msg_user_id:
            user_id = first_msg_user_id
        else:
            # First-message auth failed or no auth message received
            await websocket.close(code=4001, reason="Missing or invalid authentication token")
            return

    if restored_session:
        # Resume existing session
        session = restored_session
        session.websocket = websocket
        session.user_id = user_id  # Update user_id in case token changed
        async with manager._lock:
            # Close existing connection if present (collision handling)
            old_ws = manager.active.get(conversation_id)
            if old_ws and old_ws is not websocket:
                try:
                    await old_ws.close(code=4002, reason="Replaced by new connection")
                except Exception:
                    pass
            manager.active[conversation_id] = websocket
            manager.sessions[conversation_id] = session
        session.last_activity = time.time()

        # Replay missed messages
        replay_count = await replay_missed_messages(session, last_seq)
        await websocket.send_json(
            {"type": "resumed", "from_seq": last_seq + 1, "replay_count": replay_count}
        )
        logger.info(f"Session {conversation_id} resumed, replayed {replay_count} messages")
    else:
        # New session
        session = WebSocketSession(client_id=conversation_id, websocket=websocket, user_id=user_id)
        async with manager._lock:
            # Close existing connection if present (collision handling)
            old_ws = manager.active.get(conversation_id)
            if old_ws and old_ws is not websocket:
                try:
                    await old_ws.close(code=4002, reason="Replaced by new connection")
                except Exception:
                    pass
            manager.active[conversation_id] = websocket
            manager.sessions[conversation_id] = session
        await manager.send_sequenced(session, "new_session", {"session_id": conversation_id})

    # Start background tasks
    retry_task = asyncio.create_task(periodic_retry(session))
    heartbeat_task = asyncio.create_task(heartbeat_loop(session))

    try:
        # If handle_initial_message consumed a non-resume message during the
        # handshake window, process it first instead of waiting for a new one.
        pending_data = initial_data
        while True:
            if pending_data is not None:
                data = pending_data
                pending_data = None
            else:
                data = await websocket.receive_json()
            msg_type = data.get("type", "message")
            session.last_activity = time.time()

            # Rate limiting check (skip for ack and pong to not interfere with protocol)
            if msg_type not in ("ack", "pong") and not session.rate_limiter.consume():
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "RATE_LIMITED",
                        "message": "Too many messages, please slow down",
                        "retry_after": 1.0,
                    }
                )
                continue

            # Handle client acknowledgment of server messages
            if msg_type == "ack":
                ack_seq = data.get("seq")
                if ack_seq is not None:
                    handle_ack(session, ack_seq)
                continue

            # Handle pong response to server heartbeat
            if msg_type == "pong":
                session.last_pong = time.time()
                continue

            # Handle ping from client - also update last_pong for connection liveness
            if msg_type == "ping":
                session.last_pong = time.time()
                await manager.send_sequenced(session, "pong", {})
                continue

            if msg_type == "cancel":
                from core.orchestrator.cancellation import get_cancellation_registry

                cancelled = get_cancellation_registry().request_cancel(conversation_id)
                await manager.send_sequenced(session, "cancel_ack", {"cancelled": cancelled})
                continue

            if msg_type == "message":
                content = data.get("content", "")
                mode = data.get("mode", "chat")
                enable_thinking = data.get("enable_thinking", False)
                crew_id = data.get("crew_id")
                leash_preset = data.get("leash_preset")
                event_visibility = data.get("event_visibility")
                # Vision input: optional image attachments (max 4)
                raw_attachments = data.get("image_attachments")
                image_attachments: list[dict[str, str]] | None = None
                if isinstance(raw_attachments, list):
                    image_attachments = [
                        {"base64": a["base64"], "mime_type": a.get("mime_type", "image/png")}
                        for a in raw_attachments[:4]
                        if isinstance(a, dict) and "base64" in a
                    ] or None

                # Send acknowledgment (server acks client message)
                await manager.send_sequenced(session, "message_ack", {"received": content[:50]})

                # DB persistence: create/get conversation + persist user message

                from core.database.models import (
                    Conversation as DBConversation,
                )
                from core.database.models import (
                    Message as DBMessage,
                )
                from core.database.models import (
                    ToolResult as DBToolResult,
                )
                from core.database.session import get_session as get_db_session
                from core.orchestrator.stream_registry import get_stream_registry
                from core.providers.cost_context import clear_cost_user_id, set_cost_user_id
                from core.providers.llm_context import clear_user_llm_context, set_user_llm_context
                from core.providers.user_config import get_user_llm_config

                user_llm_config = None
                fallback_chain = None
                try:
                    with get_db_session() as db_session:
                        # Load user LLM config
                        if session.user_id:
                            user_llm_config = get_user_llm_config(session.user_id, db_session)

                        # Load fallback chain for resilient provider switching.
                        # MUST happen inside the db_session context — session closes at commit().
                        if session.user_id:
                            try:
                                from core.providers.resilience.fallback_chain import (
                                    get_fallback_chain,
                                )

                                fallback_chain = get_fallback_chain(session.user_id, db_session)
                            except Exception:
                                pass  # No fallback — proceed with single provider

                        # Set cost context for user attribution in cost records
                        if session.user_id:
                            set_cost_user_id(session.user_id)

                        # Set contextvar so ThinkingProvider/_call_llm can find user config
                        if user_llm_config and user_llm_config.is_configured():
                            set_user_llm_context(user_llm_config)

                        # Create or get conversation
                        conversation = (
                            db_session.query(DBConversation).filter_by(id=conversation_id).first()
                        )
                        if not conversation:
                            conversation = DBConversation(
                                id=conversation_id,
                                user_id=session.user_id,
                                title=content[:50],
                                mode=mode,
                                status="active",
                            )
                            db_session.add(conversation)

                        # Store user message
                        user_msg = DBMessage(
                            conversation_id=conversation_id,
                            role="user",
                            content=content,
                            metadata_={"timestamp": utcnow().isoformat()},
                        )
                        db_session.add(user_msg)
                        db_session.commit()
                except Exception as e:
                    logger.error(f"WS DB error persisting user message: {e}")

                # Set up cancel event for fallback chain cancellation.
                # Must happen outside the db_session context (which is now closed).
                ws_cancel_event = None
                if fallback_chain and fallback_chain.entries and fallback_chain.enabled:
                    ws_cancel_event = asyncio.Event()
                    CANCEL_EVENTS[conversation_id] = ws_cancel_event

                # Register active stream for reconnection recovery
                stream_registry = get_stream_registry()
                active_stream = stream_registry.register(conversation_id, mode=mode)

                full_response = ""
                full_thinking = ""
                tool_calls: list[dict] = []
                response_mode = mode

                # Run stream consumption as background task so we can
                # still receive client messages (cancel, ack, pong) during streaming.
                stream_error: Exception | None = None

                async def _consume_stream():
                    nonlocal full_response, full_thinking, tool_calls, response_mode, stream_error
                    try:

                        async def _ws_run_with_fallback():
                            """Yield ChatEvents from route_request with automatic provider fallback.

                            When the user has a configured and enabled fallback chain, iterates
                            through providers in order, emitting failover events between attempts.
                            Falls back to the normal single-provider path when chain is unavailable.
                            """
                            from core.crypto import decrypt_key
                            from core.database.models import ProviderApiKey
                            from core.extensions.events import emit_error, emit_failover
                            from core.providers.resilience.events import log_failover_event
                            from core.providers.resilience.failover_engine import (
                                PROVIDER_CIRCUIT_BREAKER,
                            )
                            from core.providers.resilience.fallback_chain import (
                                resolve_chain_configs,
                            )
                            from core.providers.user_config import UserLLMConfig

                            def _user_config_fn(provider: str):
                                try:
                                    with get_db_session() as _db:
                                        key_record = (
                                            _db.query(ProviderApiKey)
                                            .filter(
                                                ProviderApiKey.user_id == session.user_id,
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
                                    message=content,
                                    conversation_id=conversation_id,
                                    user_id=session.user_id,
                                    mode_override=mode,
                                    stream=True,
                                    enable_thinking=enable_thinking,
                                    user_llm_config=user_llm_config,
                                    crew_id=crew_id,
                                    leash_preset=leash_preset,
                                    event_visibility=event_visibility,
                                ):
                                    yield ev
                                return

                            for idx, config in enumerate(resolved):
                                if ws_cancel_event and ws_cancel_event.is_set():
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
                                        message=content,
                                        conversation_id=conversation_id,
                                        user_id=session.user_id,
                                        mode_override=mode,
                                        stream=True,
                                        enable_thinking=enable_thinking,
                                        user_llm_config=provider_llm_config,
                                        crew_id=crew_id,
                                        leash_preset=leash_preset,
                                        event_visibility=event_visibility,
                                        image_attachments=image_attachments,
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
                            yield emit_error(
                                message="All LLM providers are unavailable",
                                code="all_providers_exhausted",
                            )

                        # Choose between fallback-enabled and standard path
                        if fallback_chain and fallback_chain.entries and fallback_chain.enabled:
                            event_source = _ws_run_with_fallback()
                        else:
                            event_source = route_request(
                                message=content,
                                conversation_id=conversation_id,
                                user_id=session.user_id,
                                mode_override=mode,
                                stream=True,
                                enable_thinking=enable_thinking,
                                user_llm_config=user_llm_config,
                                crew_id=crew_id,
                                leash_preset=leash_preset,
                                event_visibility=event_visibility,
                                image_attachments=image_attachments,
                            )

                        async for event in event_source:
                            # Accumulate content for DB + stream recovery
                            if event.type in ("token", "content") and event.content:
                                full_response += event.content
                                active_stream.accumulated_content = full_response
                            elif event.type == "thinking" and event.content:
                                full_thinking += ("\n\n" if full_thinking else "") + event.content
                                active_stream.accumulated_thinking = full_thinking
                            elif event.type == "complete" and event.content:
                                full_response = event.content
                                response_mode = event.metadata.get("mode", mode)
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
                                active_stream.tool_calls = tool_calls
                            elif event.type == "tool_result" and tool_calls:
                                tool_result_raw = event.metadata.get("result", "")
                                tool_calls[-1]["result"] = str(tool_result_raw)
                                tool_calls[-1]["success"] = event.metadata.get("success", True)
                                tool_calls[-1]["duration_ms"] = event.metadata.get("duration_ms")
                                # Extract image content from tool results (JSON with images key)
                                image_content: list[dict[str, str]] = []
                                if isinstance(tool_result_raw, str):
                                    try:
                                        parsed = json.loads(tool_result_raw)
                                        if isinstance(parsed, dict) and "images" in parsed:
                                            for img in parsed["images"]:
                                                if isinstance(img, dict) and "data" in img:
                                                    image_content.append(
                                                        {
                                                            "data": img["data"],
                                                            "mimeType": img.get(
                                                                "mimeType", "image/png"
                                                            ),
                                                        }
                                                    )
                                    except (json.JSONDecodeError, TypeError):
                                        pass
                                if image_content:
                                    tool_calls[-1]["image_content"] = image_content

                            # Forward every event to client
                            event_data = {"content": event.content}
                            if event.metadata:
                                event_data.update(event.metadata)
                            await manager.send_sequenced(session, event.type, event_data)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        stream_error = e
                    finally:
                        stream_registry.complete(conversation_id)
                        clear_user_llm_context()
                        clear_cost_user_id()
                        # Clean up cancel event registration for fallback chain
                        if ws_cancel_event is not None:
                            CANCEL_EVENTS.pop(conversation_id, None)

                stream_task = asyncio.create_task(_consume_stream())

                # Listen for client messages while the stream runs
                try:
                    while not stream_task.done():
                        recv_task = asyncio.ensure_future(websocket.receive_json())
                        done, _pending = await asyncio.wait(
                            [stream_task, recv_task],
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if recv_task in done:
                            inner_data = recv_task.result()
                            inner_type = inner_data.get("type", "")
                            if inner_type == "cancel":
                                from core.orchestrator.cancellation import get_cancellation_registry

                                cancelled = get_cancellation_registry().request_cancel(
                                    conversation_id
                                )
                                await manager.send_sequenced(
                                    session, "cancel_ack", {"cancelled": cancelled}
                                )
                            elif inner_type == "ack":
                                ack_seq = inner_data.get("seq")
                                if ack_seq is not None:
                                    handle_ack(session, ack_seq)
                            elif inner_type == "pong":
                                session.last_pong = time.time()
                        else:
                            # Stream finished, cancel pending recv
                            recv_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await recv_task
                except WebSocketDisconnect:
                    stream_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stream_task
                    raise

                await stream_task
                if stream_error:
                    logger.error(f"WS streaming error: {stream_error}")
                    await manager.send_sequenced(session, "error", {"message": str(stream_error)})

                # DB persistence: store assistant message + tool results
                if full_response or tool_calls:
                    try:
                        with get_db_session() as db_session:
                            msg_metadata: dict[str, Any] = {"mode": response_mode}
                            if full_thinking:
                                msg_metadata["thinking"] = full_thinking
                            assistant_msg = DBMessage(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=full_response,
                                metadata_=msg_metadata,
                            )
                            db_session.add(assistant_msg)
                            db_session.flush()

                            for tc in tool_calls:
                                tool_result = DBToolResult(
                                    message_id=assistant_msg.id,
                                    tool_name=tc["tool_name"],
                                    tool_call_id=tc.get("tool_call_id"),
                                    arguments=tc["args"],
                                    result=tc["result"],
                                    success=tc["success"],
                                    duration_ms=tc["duration_ms"],
                                )
                                db_session.add(tool_result)

                            db_session.commit()
                            logger.info(
                                f"WS: persisted assistant msg + {len(tool_calls)} tool results"
                            )
                    except Exception as e:
                        logger.error(f"WS DB error storing assistant message: {e}")

    except WebSocketDisconnect:
        # Save session for potential reconnection
        if session:
            session_store.save_for_reconnect(session)
            logger.debug(f"Session {conversation_id} saved for reconnect")
    finally:
        heartbeat_task.cancel()
        retry_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        with contextlib.suppress(asyncio.CancelledError):
            await retry_task
        await manager.disconnect(conversation_id)

@router.websocket("/ws/flow/{execution_id}")
async def websocket_flow(websocket: WebSocket, execution_id: str):
    """Flow execution progress WebSocket with message sequencing and acknowledgments.

    Supports reconnection: client sends {"type": "resume", "last_seq": N} as first message.
    Server responds with {"type": "resumed", "from_seq": N, "replay_count": M} or
    {"type": "new_session", "session_id": "..."} for new connections.

    Authentication: Token via query param (?token=...) or Authorization header.
    Auth disabled when JWT_SECRET not configured (matches REST API pattern).

    Client ack format: {"type": "ack", "seq": N}
    Server messages wrapped in ServerMessage envelope with incrementing seq.
    """
    # Authenticate before accepting connection
    try:
        user_id = await authenticate_websocket(websocket)
    except WebSocketAuthError:
        return  # Already closed with error code

    auth_pending = user_id == "pending"
    if auth_pending:
        user_id = None

    await websocket.accept()

    # Handle reconnection/auth handshake
    restored_session, last_seq, initial_data, first_msg_user_id = await handle_initial_message(
        websocket, execution_id, auth_pending=auth_pending
    )

    # Resolve user_id from first-message auth if query/header auth was pending
    if auth_pending:
        if first_msg_user_id:
            user_id = first_msg_user_id
        else:
            # First-message auth failed or no auth message received
            await websocket.close(code=4001, reason="Missing or invalid authentication token")
            return

    if restored_session:
        # Resume existing session
        session = restored_session
        session.websocket = websocket
        session.user_id = user_id  # Update user_id in case token changed
        async with manager._lock:
            old_ws = manager.active.get(execution_id)
            if old_ws and old_ws is not websocket:
                try:
                    await old_ws.close(code=4002, reason="Replaced by new connection")
                except Exception:
                    pass
            manager.active[execution_id] = websocket
            manager.sessions[execution_id] = session
        session.last_activity = time.time()

        # Replay missed messages
        replay_count = await replay_missed_messages(session, last_seq)
        await websocket.send_json(
            {"type": "resumed", "from_seq": last_seq + 1, "replay_count": replay_count}
        )
        logger.info(f"Session {execution_id} resumed, replayed {replay_count} messages")
    else:
        # New session
        session = WebSocketSession(client_id=execution_id, websocket=websocket, user_id=user_id)
        async with manager._lock:
            old_ws = manager.active.get(execution_id)
            if old_ws and old_ws is not websocket:
                try:
                    await old_ws.close(code=4002, reason="Replaced by new connection")
                except Exception:
                    pass
            manager.active[execution_id] = websocket
            manager.sessions[execution_id] = session
        await manager.send_sequenced(session, "new_session", {"session_id": execution_id})

    # Start background tasks
    retry_task = asyncio.create_task(periodic_retry(session))
    heartbeat_task = asyncio.create_task(heartbeat_loop(session))

    try:
        # If handle_initial_message consumed a non-resume message during the
        # handshake window, process it first instead of waiting for a new one.
        pending_data = initial_data
        while True:
            if pending_data is not None:
                data = pending_data
                pending_data = None
            else:
                data = await websocket.receive_json()
            msg_type = data.get("type", "status")
            session.last_activity = time.time()

            # Rate limiting check (skip for ack and pong to not interfere with protocol)
            if msg_type not in ("ack", "pong") and not session.rate_limiter.consume():
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "RATE_LIMITED",
                        "message": "Too many messages, please slow down",
                        "retry_after": 1.0,
                    }
                )
                continue

            # Handle client acknowledgment of server messages
            if msg_type == "ack":
                ack_seq = data.get("seq")
                if ack_seq is not None:
                    handle_ack(session, ack_seq)
                continue

            # Handle pong response to server heartbeat
            if msg_type == "pong":
                session.last_pong = time.time()
                continue

            # Handle ping from client - also update last_pong for connection liveness
            if msg_type == "ping":
                session.last_pong = time.time()
                await manager.send_sequenced(session, "pong", {})
                continue

            # Handle cancel message (GAP-101: JSON message via WebSocket)
            if msg_type == "cancel":
                await manager.send_sequenced(session, "cancelled", {})
                continue

            if msg_type == "execute":
                flow_name = data.get("flow")
                inputs = data.get("inputs", {})

                if flow_name not in FLOW_REGISTRY:
                    await manager.send_sequenced(
                        session, "error", {"message": f"Flow '{flow_name}' not found"}
                    )
                    continue

                try:
                    flow_class = FLOW_REGISTRY[flow_name]["class"]
                    flow = flow_class()

                    for key, value in inputs.items():
                        if hasattr(flow.state, key):
                            setattr(flow.state, key, value)

                    await manager.send_sequenced(session, "start", {"flow": flow_name})

                    result = flow.kickoff()

                    await manager.send_sequenced(
                        session,
                        "complete",
                        {"result": result if isinstance(result, dict) else str(result)},
                    )

                except Exception as e:
                    await manager.send_sequenced(session, "error", {"message": str(e)})

    except WebSocketDisconnect:
        # Save session for potential reconnection
        if session:
            session_store.save_for_reconnect(session)
            logger.debug(f"Session {execution_id} saved for reconnect")
    finally:
        heartbeat_task.cancel()
        retry_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        with contextlib.suppress(asyncio.CancelledError):
            await retry_task
        await manager.disconnect(execution_id)
