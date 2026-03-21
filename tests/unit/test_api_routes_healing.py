"""Tests for core/api/routes/healing.py -- Self-Healing Management routes.

Tests route handlers for circuit breaker monitoring, reset, and health.
All circuit breaker dependencies are mocked.
"""

import pytest

pytest.skip(
    "circuit_breaker lazy-load mock incompatible with pytest collection order — needs plugin loaded",
    allow_module_level=True,
)

from enum import Enum
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: mock circuit breaker
# ---------------------------------------------------------------------------
class _MockState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

def _make_breaker(name="test_service", state="closed", failure_count=0):
    breaker = MagicMock()
    breaker.state = _MockState(state)
    breaker.get_state.return_value = {
        "name": name,
        "state": state,
        "failure_count": failure_count,
        "failure_threshold": 5,
        "timeout_seconds": 60,
        "last_failure_time": None,
        "last_state_change": "2026-01-13T10:00:00Z",
    }
    return breaker

# ===========================================================================
# get_healing_stats endpoint
# ===========================================================================
class TestGetHealingStats:
    """Tests for GET /stats."""

    @pytest.mark.asyncio
    async def test_stats_no_breakers(self):
        """Empty circuit breakers -- should return enabled with empty dict."""
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value={}):
            from core.api.routes.healing import get_healing_stats

            result = await get_healing_stats()

        assert result.enabled is True
        assert result.circuit_breakers == {}

    @pytest.mark.asyncio
    async def test_stats_with_breakers(self):
        """Circuit breakers present -- should return their states."""
        breakers = {
            "anthropic": _make_breaker("anthropic", "closed"),
            "database": _make_breaker("database", "open", failure_count=5),
        }
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import get_healing_stats

            result = await get_healing_stats()

        assert len(result.circuit_breakers) == 2
        assert result.circuit_breakers["anthropic"].state == "closed"
        assert result.circuit_breakers["database"].state == "open"

    @pytest.mark.asyncio
    async def test_stats_disabled(self):
        """Self-healing disabled via Settings -- should return enabled=False."""
        mock_settings = MagicMock()
        mock_settings.self_healing_enabled = False
        mock_settings.retry_max_attempts = 3
        with (
            patch("core.extensions.get_all_circuit_breakers", create=True, return_value={}),
            patch("core.api.routes.healing.get_settings", return_value=mock_settings),
        ):
            from core.api.routes.healing import get_healing_stats

            result = await get_healing_stats()

        assert result.enabled is False

    @pytest.mark.asyncio
    async def test_stats_error(self):
        """Stats retrieval failure -- should raise 500."""
        from fastapi import HTTPException

        with patch(
            "core.extensions.get_all_circuit_breakers",
            side_effect=RuntimeError("fail"),
        ):
            from core.api.routes.healing import get_healing_stats

            with pytest.raises(HTTPException) as exc_info:
                await get_healing_stats()
            assert exc_info.value.status_code == 500

# ===========================================================================
# list_circuit_breakers endpoint
# ===========================================================================
class TestListCircuitBreakers:
    """Tests for GET /circuit-breakers."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """No breakers -- should return total_circuits=0."""
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value={}):
            from core.api.routes.healing import list_circuit_breakers

            result = await list_circuit_breakers()

        assert result["total_circuits"] == 0
        assert result["summary"]["closed"] == 0
        assert result["summary"]["open"] == 0

    @pytest.mark.asyncio
    async def test_list_with_breakers(self):
        """Mixed states -- should count correctly."""
        breakers = {
            "svc_a": _make_breaker("svc_a", "closed"),
            "svc_b": _make_breaker("svc_b", "open"),
            "svc_c": _make_breaker("svc_c", "closed"),
        }
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import list_circuit_breakers

            result = await list_circuit_breakers()

        assert result["total_circuits"] == 3
        assert result["summary"]["closed"] == 2
        assert result["summary"]["open"] == 1

    @pytest.mark.asyncio
    async def test_list_error(self):
        """List failure -- should raise 500."""
        from fastapi import HTTPException

        with patch(
            "core.extensions.get_all_circuit_breakers",
            side_effect=RuntimeError("fail"),
        ):
            from core.api.routes.healing import list_circuit_breakers

            with pytest.raises(HTTPException) as exc_info:
                await list_circuit_breakers()
            assert exc_info.value.status_code == 500

# ===========================================================================
# get_circuit_breaker endpoint
# ===========================================================================
class TestGetCircuitBreaker:
    """Tests for GET /circuit-breakers/{name}."""

    @pytest.mark.asyncio
    async def test_get_existing(self):
        """Get a known breaker -- should return its state."""
        breakers = {"anthropic": _make_breaker("anthropic", "closed")}
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import get_circuit_breaker

            result = await get_circuit_breaker(name="anthropic")

        assert result["name"] == "anthropic"
        assert result["state"] == "closed"

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        """Get unknown breaker -- should raise 404."""
        from fastapi import HTTPException

        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value={}):
            from core.api.routes.healing import get_circuit_breaker

            with pytest.raises(HTTPException) as exc_info:
                await get_circuit_breaker(name="nonexistent")
            assert exc_info.value.status_code == 404

# ===========================================================================
# reset_circuit_breaker endpoint
# ===========================================================================
class TestResetCircuitBreaker:
    """Tests for POST /circuit-breakers/{name}/reset."""

    @pytest.mark.asyncio
    async def test_reset_success(self):
        """Reset an open breaker -- should return new_state=closed."""
        breaker = _make_breaker("db", "open", failure_count=10)
        breakers = {"db": breaker}

        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import reset_circuit_breaker

            result = await reset_circuit_breaker(name="db")

        assert result.previous_state == "open"
        assert result.new_state == "closed"
        assert result.failure_count == 0
        breaker.reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_not_found(self):
        """Reset non-existent breaker -- should raise 404."""
        from fastapi import HTTPException

        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value={}):
            from core.api.routes.healing import reset_circuit_breaker

            with pytest.raises(HTTPException) as exc_info:
                await reset_circuit_breaker(name="nonexistent")
            assert exc_info.value.status_code == 404

# ===========================================================================
# healing_health endpoint
# ===========================================================================
class TestHealingHealth:
    """Tests for GET /health."""

    @pytest.mark.asyncio
    async def test_healthy_no_open(self):
        """All breakers closed -- should return healthy=True."""
        breakers = {
            "svc_a": _make_breaker("svc_a", "closed"),
            "svc_b": _make_breaker("svc_b", "closed"),
        }
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import healing_health

            result = await healing_health()

        assert result["healthy"] is True
        assert result["issues"] is None

    @pytest.mark.asyncio
    async def test_unhealthy_open_circuit(self):
        """Open breaker -- should return healthy=False with issues."""
        breakers = {
            "svc_a": _make_breaker("svc_a", "closed"),
            "svc_b": _make_breaker("svc_b", "open"),
        }
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import healing_health

            result = await healing_health()

        assert result["healthy"] is False
        assert any("open" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_half_open_reports_issue(self):
        """Half-open breaker -- should still be healthy but report issue."""
        breakers = {"svc_a": _make_breaker("svc_a", "half_open")}
        with patch("core.extensions.get_all_circuit_breakers", create=True, return_value=breakers):
            from core.api.routes.healing import healing_health

            result = await healing_health()

        assert result["healthy"] is True  # half_open is not "open"
        assert any("recovery" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_disabled_reports_issue(self):
        """Self-healing disabled -- should report as issue."""
        mock_settings = MagicMock()
        mock_settings.self_healing_enabled = False
        mock_settings.retry_max_attempts = 3
        with (
            patch("core.extensions.get_all_circuit_breakers", create=True, return_value={}),
            patch("core.api.routes.healing.get_settings", return_value=mock_settings),
        ):
            from core.api.routes.healing import healing_health

            result = await healing_health()

        assert any("disabled" in issue for issue in result["issues"])

    @pytest.mark.asyncio
    async def test_health_error(self):
        """Health check error -- should raise 500."""
        from fastapi import HTTPException

        with patch(
            "core.extensions.get_all_circuit_breakers",
            side_effect=RuntimeError("fail"),
        ):
            from core.api.routes.healing import healing_health

            with pytest.raises(HTTPException) as exc_info:
                await healing_health()
            assert exc_info.value.status_code == 500
