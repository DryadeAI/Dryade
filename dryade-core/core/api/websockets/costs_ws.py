"""WebSocket Route for real-time cost tracking.

Provides periodic updates of LLM usage costs to connected clients.
Follows the reliability protocol defined in core/api/routes/websocket.py.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.api.routes.websocket import (
    WebSocketAuthError,
    WebSocketSession,
    authenticate_websocket,
    handle_ack,
    handle_initial_message,
    heartbeat_loop,
    manager,
    periodic_retry,
    session_store,
)
from core.extensions import get_cost_summary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

@router.websocket("/costs")
async def websocket_costs(websocket: WebSocket):
    """Real-time cost updates WebSocket.

    Provides periodic cost summaries (every 5 seconds).
    Supports the same reconnection and reliability protocol as chat/flows.
    """
    client_id = f"costs_{int(time.time())}"  # Temporary ID until handshake

    # Authenticate before accepting
    try:
        user_id = await authenticate_websocket(websocket)
    except WebSocketAuthError:
        return

    await websocket.accept()

    # Handshake to determine if new or resume
    restored_session, last_seq = await handle_initial_message(websocket, client_id)

    if restored_session:
        session = restored_session
        session.websocket = websocket
        session.user_id = user_id
        manager.active[session.client_id] = websocket
        manager.sessions[session.client_id] = session
        logger.info(f"Cost session {session.client_id} resumed")
    else:
        session = WebSocketSession(client_id=client_id, websocket=websocket, user_id=user_id)
        manager.active[client_id] = websocket
        manager.sessions[client_id] = session
        await manager.send_sequenced(session, "new_session", {"session_id": client_id})

    # Start reliability tasks
    retry_task = asyncio.create_task(periodic_retry(session))
    heartbeat_task = asyncio.create_task(heartbeat_loop(session))

    # Start cost update task
    async def cost_push_loop():
        try:
            while True:
                # Get current costs
                summary = get_cost_summary()
                await manager.send_sequenced(session, "cost_update", summary)
                await asyncio.sleep(5)  # Update every 5 seconds
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in cost push loop: {e}")

    push_task = asyncio.create_task(cost_push_loop())

    try:
        while True:
            # Wait for messages from client (mostly acks/pongs)
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ack":
                ack_seq = data.get("seq")
                if ack_seq is not None:
                    handle_ack(session, ack_seq)

            elif msg_type == "pong":
                session.last_pong = time.time()

            elif msg_type == "ping":
                session.last_pong = time.time()
                await manager.send_sequenced(session, "pong", {})

    except WebSocketDisconnect:
        if session:
            session_store.save_for_reconnect(session)
            logger.debug(f"Cost session {session.client_id} saved for reconnect")
    finally:
        push_task.cancel()
        heartbeat_task.cancel()
        retry_task.cancel()
        await manager.disconnect(session.client_id)
