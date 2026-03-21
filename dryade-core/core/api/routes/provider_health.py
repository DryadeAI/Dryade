"""Provider Health API Routes.

Endpoints for LLM provider health monitoring and fallback chain management.

Routes:
    GET  /api/provider-health                   -- Health status for all providers
    GET  /api/user/provider-fallback-order      -- Read user's fallback chain
    PUT  /api/user/provider-fallback-order      -- Persist user's fallback chain
    POST /api/chat/{session_id}/cancel-fallback -- Cancel in-progress fallback
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cancel-fallback event registry
# Keyed by session_id. Chat routes register their asyncio.Event here before
# calling execute_with_fallback so the cancel endpoint can set it.
# ---------------------------------------------------------------------------
CANCEL_EVENTS: dict[str, asyncio.Event] = {}

# ============================================================================
# Request / Response Models
# ============================================================================

class ProviderHealthResponse(BaseModel):
    """Provider health status response."""

    providers: dict[str, dict]

class FallbackChainEntryRequest(BaseModel):
    """Single entry in a fallback chain request."""

    provider: str = Field(..., description="Provider name (e.g., 'openai', 'anthropic')")
    model: str = Field(..., description="Model name/ID (e.g., 'gpt-4o')")

class FallbackOrderRequest(BaseModel):
    """Request body for PUT /api/user/provider-fallback-order."""

    chain: list[FallbackChainEntryRequest] = Field(
        default_factory=list,
        description="Ordered list of provider+model pairs",
    )
    enabled: bool = Field(True, description="Whether fallback is active")

class FallbackOrderResponse(BaseModel):
    """Response for GET /api/user/provider-fallback-order."""

    chain: list[dict]
    enabled: bool

# ============================================================================
# Endpoints
# ============================================================================

@router.get("/api/provider-health", tags=["provider-health"])
async def get_provider_health(request: Request) -> ProviderHealthResponse:
    """Return health status for all monitored providers.

    Reads from the ProviderHealthMonitor singleton stored in app.state.
    Returns green/yellow/red per provider based on circuit breaker state.
    """
    monitor = getattr(request.app.state, "health_monitor", None)
    if monitor is None:
        # No monitor means no failures recorded — return empty (all green)
        return ProviderHealthResponse(providers={})

    status = monitor.get_health_status()
    return ProviderHealthResponse(providers=status)

@router.get("/api/user/provider-fallback-order", tags=["provider-health"])
async def get_fallback_order(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FallbackOrderResponse:
    """Return the current user's provider fallback chain.

    Returns an empty chain with enabled=False if not configured.
    """
    from core.providers.resilience.fallback_chain import get_fallback_chain

    chain = get_fallback_chain(current_user.id, db)

    if chain is None:
        return FallbackOrderResponse(chain=[], enabled=False)

    return FallbackOrderResponse(
        chain=[e.to_dict() for e in chain.entries],
        enabled=chain.enabled,
    )

@router.put("/api/user/provider-fallback-order", tags=["provider-health"])
async def set_fallback_order(
    body: FallbackOrderRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Persist a new provider fallback chain for the current user.

    Validates each entry has provider and model strings.
    Overwrites any existing chain.
    """
    from core.providers.resilience.fallback_chain import (
        FallbackChain,
        FallbackChainEntry,
        save_fallback_chain,
    )

    if not body.chain:
        # Allow empty chain to clear/disable fallback
        entries = []
    else:
        entries = [FallbackChainEntry(provider=e.provider, model=e.model) for e in body.chain]

    chain = FallbackChain(entries=entries, enabled=body.enabled)

    try:
        save_fallback_chain(current_user.id, chain, db)
    except Exception as exc:
        logger.error("Failed to save fallback chain: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save fallback chain")

    return {"status": "ok", "entries": len(entries), "enabled": body.enabled}

@router.post("/api/chat/{session_id}/cancel-fallback", tags=["provider-health"])
async def cancel_fallback(
    session_id: str,
    current_user=Depends(get_current_user),
) -> dict:
    """Cancel an in-progress provider fallback chain for a chat session.

    Sets the asyncio.Event that the execute_with_fallback caller registered
    before initiating the call. This stops iteration at the next provider
    boundary.

    The chat route (chat.py / websocket.py) must register an event via:
        CANCEL_EVENTS[session_id] = asyncio.Event()
    before calling execute_with_fallback(..., cancel_event=CANCEL_EVENTS[session_id]).
    """
    event = CANCEL_EVENTS.get(session_id)
    if event is None:
        # No active fallback for this session — not an error
        return {"status": "ok", "message": "No active fallback for this session"}

    event.set()
    logger.info("Fallback cancelled for session %s by user %s", session_id, current_user.id)
    return {"status": "ok", "message": "Fallback cancelled"}
