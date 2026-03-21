"""Tests for core/api/routes/safety.py -- Safety Management routes.

Tests route handlers for validation violations, safety stats, and sanitization stats.
All database dependencies are mocked.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: mock validation failure and sanitization event
# ---------------------------------------------------------------------------
def _make_validation_failure(model_type="ChatRequest", route="/api/chat", errors=None):
    vf = MagicMock()
    vf.model_type = model_type
    vf.route = route
    vf.errors = errors or ["messages: field required"]
    vf.created_at = datetime(2026, 1, 13, 12, 0, 0)
    return vf

def _make_sanitization_event(
    context="html", route="/api/chat", original_length=100, sanitized_length=95
):
    se = MagicMock()
    se.context = context
    se.route = route
    se.original_length = original_length
    se.sanitized_length = sanitized_length
    se.modifications = ["XSS removed"]
    se.created_at = datetime(2026, 1, 13, 12, 0, 0)
    return se

# ===========================================================================
# get_violations endpoint
# ===========================================================================
class TestGetViolations:
    """Tests for GET /violations."""

    @pytest.mark.asyncio
    async def test_violations_no_data(self):
        """No violations -- should return empty lists."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        with patch("core.api.routes.safety.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.safety import get_violations

            result = await get_violations()

        assert result["total_violations"] == 0
        assert result["validation_failures"] == []
        assert result["sanitization_events"] == []
        assert result["time_period"] == "last_24h"

    @pytest.mark.asyncio
    async def test_violations_with_data(self):
        """Violations present -- should return them formatted."""
        vf = _make_validation_failure()
        se = _make_sanitization_event()

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        # First call returns validation failures, second returns sanitization events
        mock_query.all.side_effect = [[vf], [se]]

        with patch("core.api.routes.safety.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.safety import get_violations

            result = await get_violations()

        assert result["total_violations"] == 2
        assert len(result["validation_failures"]) == 1
        assert result["validation_failures"][0]["model_type"] == "ChatRequest"
        assert len(result["sanitization_events"]) == 1
        assert result["sanitization_events"][0]["context"] == "html"

    @pytest.mark.asyncio
    async def test_violations_error(self):
        """Database error -- should return error response (not raise)."""
        with patch("core.api.routes.safety.get_session", side_effect=RuntimeError("DB down")):
            from core.api.routes.safety import get_violations

            result = await get_violations()

        # Safety routes return error in response, not raise
        assert result["total_violations"] == 0
        assert result["error"] is not None

# ===========================================================================
# get_safety_stats endpoint
# ===========================================================================
class TestGetSafetyStats:
    """Tests for GET /stats."""

    @pytest.mark.asyncio
    async def test_stats_empty(self):
        """No data -- should return zeros."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.scalar.return_value = 0
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_query.group_by.return_value = mock_query

        with patch("core.api.routes.safety.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.safety import get_safety_stats

            result = await get_safety_stats()

        assert result.validation_failures == 0
        assert result.sanitization_events == 0
        assert result.most_common_violations == []

    @pytest.mark.asyncio
    async def test_stats_with_data(self):
        """Stats with data -- should aggregate correctly."""
        vf1 = _make_validation_failure(errors=["field required"])
        vf2 = _make_validation_failure(errors=["field required"])
        vf3 = _make_validation_failure(errors=["invalid type"])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        # Calls: count(VF), count(SE), query VF recent, group_by SE context
        mock_query.scalar.side_effect = [5, 10]
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.side_effect = [[vf1, vf2, vf3], []]  # recent failures, context stats
        mock_query.group_by.return_value = mock_query

        with patch("core.api.routes.safety.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.safety import get_safety_stats

            result = await get_safety_stats()

        assert result.validation_failures == 5
        assert result.sanitization_events == 10
        # Most common should be "field required" with count 2
        assert len(result.most_common_violations) > 0
        assert result.most_common_violations[0]["error"] == "field required"
        assert result.most_common_violations[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_stats_error(self):
        """Database error -- should return zeros (graceful degradation)."""
        with patch("core.api.routes.safety.get_session", side_effect=RuntimeError("DB down")):
            from core.api.routes.safety import get_safety_stats

            result = await get_safety_stats()

        assert result.validation_failures == 0
        assert result.sanitization_events == 0

# ===========================================================================
# get_sanitization_stats endpoint
# ===========================================================================
class TestGetSanitizationStats:
    """Tests for GET /sanitization_stats."""

    @pytest.mark.asyncio
    async def test_sanitization_stats_empty(self):
        """No data -- should return zeros for all contexts."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.scalar.side_effect = [0, 0.0]
        mock_query.group_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        with patch("core.api.routes.safety.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.safety import get_sanitization_stats

            result = await get_sanitization_stats()

        assert result["total_events"] == 0
        assert result["by_context"]["html"] == 0
        assert result["by_context"]["sql"] == 0
        assert result["avg_size_reduction_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_sanitization_stats_with_data(self):
        """Stats with data -- should return context breakdown."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.scalar.side_effect = [150, 3.5]
        mock_query.group_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        # Context counts
        mock_query.all.return_value = [("html", 100), ("sql", 30), ("json", 20)]

        with patch("core.api.routes.safety.get_session") as mock_gs:
            mock_gs.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_gs.return_value.__exit__ = MagicMock(return_value=False)

            from core.api.routes.safety import get_sanitization_stats

            result = await get_sanitization_stats()

        assert result["total_events"] == 150
        assert result["by_context"]["html"] == 100
        assert result["by_context"]["sql"] == 30
        assert result["avg_size_reduction_pct"] == 3.5

    @pytest.mark.asyncio
    async def test_sanitization_stats_error(self):
        """Database error -- should return zeros with error message."""
        with patch("core.api.routes.safety.get_session", side_effect=RuntimeError("DB error")):
            from core.api.routes.safety import get_sanitization_stats

            result = await get_sanitization_stats()

        assert result["total_events"] == 0
        assert result["error"] is not None
