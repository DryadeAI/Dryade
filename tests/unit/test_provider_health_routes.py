"""Tests for core/api/routes/provider_health.py -- Provider health endpoints.

Covers:
- GET  /api/provider-health (with/without monitor)
- GET  /api/user/provider-fallback-order (chain found, chain not found)
- PUT  /api/user/provider-fallback-order (save success, save failure, empty chain)
- POST /api/chat/{session_id}/cancel-fallback (event exists, no event)
- Request/Response model validation
- CANCEL_EVENTS registry
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from core.api.routes.provider_health import (
    CANCEL_EVENTS,
    FallbackChainEntryRequest,
    FallbackOrderRequest,
    FallbackOrderResponse,
    ProviderHealthResponse,
    cancel_fallback,
    get_fallback_order,
    get_provider_health,
    set_fallback_order,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_request(monitor=None):
    """Build a mock FastAPI Request with optional health_monitor on app.state."""
    request = MagicMock()
    if monitor is not None:
        request.app.state.health_monitor = monitor
    else:
        # Simulate no monitor attribute
        request.app.state = MagicMock(spec=[])
    return request

def _user(sub="user-1", role="member"):
    """Build a mock current_user object with .id attribute."""
    user = MagicMock()
    user.id = sub
    user.get = lambda key, default=None: {"sub": sub, "role": role}.get(key, default)
    return user

# ===========================================================================
# Model validation tests
# ===========================================================================

class TestModels:
    """Tests for request/response Pydantic models."""

    def test_provider_health_response(self):
        resp = ProviderHealthResponse(providers={"openai": {"status": "green"}})
        assert resp.providers["openai"]["status"] == "green"

    def test_fallback_chain_entry_request(self):
        entry = FallbackChainEntryRequest(provider="openai", model="gpt-4o")
        assert entry.provider == "openai"
        assert entry.model == "gpt-4o"

    def test_fallback_order_request_defaults(self):
        req = FallbackOrderRequest()
        assert req.chain == []
        assert req.enabled is True

    def test_fallback_order_request_with_chain(self):
        entry = FallbackChainEntryRequest(provider="anthropic", model="claude-3")
        req = FallbackOrderRequest(chain=[entry], enabled=False)
        assert len(req.chain) == 1
        assert req.enabled is False

    def test_fallback_order_response(self):
        resp = FallbackOrderResponse(
            chain=[{"provider": "openai", "model": "gpt-4o"}], enabled=True
        )
        assert len(resp.chain) == 1
        assert resp.enabled is True

# ===========================================================================
# GET /api/provider-health tests
# ===========================================================================

class TestGetProviderHealth:
    """Tests for get_provider_health endpoint."""

    async def test_no_monitor_returns_empty(self):
        """When no health_monitor on app.state, returns empty providers dict."""
        request = _mock_request(monitor=None)
        result = await get_provider_health(request)
        assert isinstance(result, ProviderHealthResponse)
        assert result.providers == {}

    async def test_with_monitor(self):
        """Returns health status from monitor."""
        monitor = MagicMock()
        monitor.get_health_status.return_value = {
            "openai": {"status": "green", "latency_ms": 120},
            "anthropic": {"status": "yellow", "latency_ms": 500},
        }
        request = _mock_request(monitor=monitor)
        result = await get_provider_health(request)
        assert result.providers["openai"]["status"] == "green"
        assert result.providers["anthropic"]["status"] == "yellow"

# ===========================================================================
# GET /api/user/provider-fallback-order tests
# ===========================================================================

class TestGetFallbackOrder:
    """Tests for get_fallback_order endpoint."""

    async def test_no_chain_configured(self):
        """Returns empty chain with enabled=False when no chain exists."""
        user = _user()
        db = MagicMock()

        with patch("core.providers.resilience.fallback_chain.get_fallback_chain") as mock_get:
            mock_get.return_value = None
            result = await get_fallback_order(current_user=user, db=db)

        assert isinstance(result, FallbackOrderResponse)
        assert result.chain == []
        assert result.enabled is False

    async def test_chain_found(self):
        """Returns existing chain with entries."""
        user = _user()
        db = MagicMock()

        mock_entry = MagicMock()
        mock_entry.to_dict.return_value = {"provider": "openai", "model": "gpt-4o"}
        mock_chain = MagicMock()
        mock_chain.entries = [mock_entry]
        mock_chain.enabled = True

        with patch("core.providers.resilience.fallback_chain.get_fallback_chain") as mock_get:
            mock_get.return_value = mock_chain
            result = await get_fallback_order(current_user=user, db=db)

        assert len(result.chain) == 1
        assert result.chain[0]["provider"] == "openai"
        assert result.enabled is True

# ===========================================================================
# PUT /api/user/provider-fallback-order tests
# ===========================================================================

class TestSetFallbackOrder:
    """Tests for set_fallback_order endpoint."""

    async def test_save_success(self):
        """Saves chain and returns ok status."""
        user = _user()
        db = MagicMock()
        body = FallbackOrderRequest(
            chain=[FallbackChainEntryRequest(provider="openai", model="gpt-4o")],
            enabled=True,
        )

        with (
            patch("core.providers.resilience.fallback_chain.save_fallback_chain") as mock_save,
            patch("core.providers.resilience.fallback_chain.FallbackChain"),
            patch("core.providers.resilience.fallback_chain.FallbackChainEntry"),
        ):
            result = await set_fallback_order(body=body, current_user=user, db=db)

        assert result["status"] == "ok"
        assert result["entries"] == 1
        assert result["enabled"] is True

    async def test_save_empty_chain(self):
        """Saving empty chain (disable fallback) succeeds."""
        user = _user()
        db = MagicMock()
        body = FallbackOrderRequest(chain=[], enabled=False)

        with (
            patch("core.providers.resilience.fallback_chain.save_fallback_chain"),
            patch("core.providers.resilience.fallback_chain.FallbackChain"),
            patch("core.providers.resilience.fallback_chain.FallbackChainEntry"),
        ):
            result = await set_fallback_order(body=body, current_user=user, db=db)

        assert result["status"] == "ok"
        assert result["entries"] == 0
        assert result["enabled"] is False

    async def test_save_failure_raises_500(self):
        """Raises HTTPException 500 when save fails."""
        user = _user()
        db = MagicMock()
        body = FallbackOrderRequest(
            chain=[FallbackChainEntryRequest(provider="openai", model="gpt-4o")],
            enabled=True,
        )

        with (
            patch("core.providers.resilience.fallback_chain.save_fallback_chain") as mock_save,
            patch("core.providers.resilience.fallback_chain.FallbackChain"),
            patch("core.providers.resilience.fallback_chain.FallbackChainEntry"),
        ):
            mock_save.side_effect = RuntimeError("DB error")
            with pytest.raises(HTTPException) as exc:
                await set_fallback_order(body=body, current_user=user, db=db)
            assert exc.value.status_code == 500

# ===========================================================================
# POST /api/chat/{session_id}/cancel-fallback tests
# ===========================================================================

class TestCancelFallback:
    """Tests for cancel_fallback endpoint."""

    async def test_no_active_fallback(self):
        """Returns ok message when no active fallback event for session."""
        user = _user()
        # Ensure session not in CANCEL_EVENTS
        CANCEL_EVENTS.pop("session-999", None)

        result = await cancel_fallback(session_id="session-999", current_user=user)
        assert result["status"] == "ok"
        assert "No active fallback" in result["message"]

    async def test_cancel_active_fallback(self):
        """Sets event and returns ok when active fallback exists."""
        user = _user()
        event = asyncio.Event()
        CANCEL_EVENTS["session-123"] = event

        try:
            assert not event.is_set()
            result = await cancel_fallback(session_id="session-123", current_user=user)
            assert result["status"] == "ok"
            assert "cancelled" in result["message"].lower()
            assert event.is_set()
        finally:
            CANCEL_EVENTS.pop("session-123", None)

# ===========================================================================
# CANCEL_EVENTS registry tests
# ===========================================================================

class TestCancelEventsRegistry:
    """Tests for the module-level CANCEL_EVENTS dict."""

    def test_cancel_events_is_dict(self):
        """CANCEL_EVENTS is a module-level dict."""
        assert isinstance(CANCEL_EVENTS, dict)

    def test_register_and_retrieve_event(self):
        """Can register and retrieve an asyncio.Event."""
        event = asyncio.Event()
        CANCEL_EVENTS["test-session"] = event
        try:
            assert CANCEL_EVENTS.get("test-session") is event
        finally:
            CANCEL_EVENTS.pop("test-session", None)
