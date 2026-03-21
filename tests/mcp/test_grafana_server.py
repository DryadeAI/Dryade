"""Unit tests for Grafana MCP server wrapper.

Comprehensive tests for observability integration: dashboards, alerts,
Prometheus queries, and Loki log queries.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.grafana import (
    Alert,
    AlertAccessLevel,
    Dashboard,
    GrafanaServer,
    TimeRange,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock()
    registry.is_registered.return_value = True
    return registry

@pytest.fixture
def mock_result_text():
    """Create a factory for MCPToolCallResult with text content."""

    def _make_result(text: str, is_error: bool = False) -> MCPToolCallResult:
        return MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text=text)],
            isError=is_error,
        )

    return _make_result

@pytest.fixture
def mock_result_empty():
    """Create an empty MCPToolCallResult."""
    return MCPToolCallResult(content=[], isError=False)

# ============================================================================
# AlertAccessLevel Tests
# ============================================================================

class TestAlertAccessLevel:
    """Tests for AlertAccessLevel enum."""

    def test_view_only_value(self):
        """Test VIEW_ONLY enum value."""
        assert AlertAccessLevel.VIEW_ONLY.value == "view_only"

    def test_acknowledge_value(self):
        """Test ACKNOWLEDGE enum value."""
        assert AlertAccessLevel.ACKNOWLEDGE.value == "acknowledge"

    def test_full_management_value(self):
        """Test FULL_MANAGEMENT enum value."""
        assert AlertAccessLevel.FULL_MANAGEMENT.value == "full"

# ============================================================================
# TimeRange Tests
# ============================================================================

class TestTimeRange:
    """Tests for TimeRange dataclass."""

    def test_time_range_init(self):
        """Test TimeRange initialization."""
        start = datetime(2024, 1, 15, 10, 0, 0)
        end = datetime(2024, 1, 15, 11, 0, 0)

        tr = TimeRange(start=start, end=end)

        assert tr.start == start
        assert tr.end == end

    def test_time_range_last_hour(self):
        """Test TimeRange.last_hour() factory."""
        from datetime import timezone

        before = datetime.now(UTC)
        tr = TimeRange.last_hour()
        after = datetime.now(UTC)

        # End should be close to now (ensure both are tz-aware for comparison)
        tr_end = tr.end if tr.end.tzinfo else tr.end.replace(tzinfo=UTC)
        assert before <= tr_end <= after
        # Start should be approximately 1 hour before end
        delta = tr.end - tr.start
        assert timedelta(minutes=59) <= delta <= timedelta(minutes=61)

    def test_time_range_last_day(self):
        """Test TimeRange.last_day() factory."""
        tr = TimeRange.last_day()

        delta = tr.end - tr.start
        assert timedelta(hours=23) <= delta <= timedelta(hours=25)

    def test_time_range_last_week(self):
        """Test TimeRange.last_week() factory."""
        tr = TimeRange.last_week()

        delta = tr.end - tr.start
        assert timedelta(days=6) <= delta <= timedelta(days=8)

    def test_time_range_to_dict(self):
        """Test TimeRange.to_dict() returns Grafana-compatible format."""
        start = datetime(2024, 1, 15, 10, 0, 0)
        end = datetime(2024, 1, 15, 11, 0, 0)
        tr = TimeRange(start=start, end=end)

        data = tr.to_dict()

        assert data["from"] == "2024-01-15T10:00:00Z"
        assert data["to"] == "2024-01-15T11:00:00Z"

# ============================================================================
# Dashboard Tests
# ============================================================================

class TestDashboard:
    """Tests for Dashboard dataclass."""

    def test_dashboard_init_basic(self):
        """Test Dashboard initialization with basic fields."""
        dashboard = Dashboard(
            uid="abc123",
            title="System Overview",
            folder="Infrastructure",
        )

        assert dashboard.uid == "abc123"
        assert dashboard.title == "System Overview"
        assert dashboard.folder == "Infrastructure"
        assert dashboard.tags == []
        assert dashboard.url is None

    def test_dashboard_init_full(self):
        """Test Dashboard initialization with all fields."""
        dashboard = Dashboard(
            uid="abc123",
            title="System Overview",
            folder="Infrastructure",
            tags=["production", "monitoring"],
            url="https://grafana.example.com/d/abc123",
        )

        assert dashboard.tags == ["production", "monitoring"]
        assert dashboard.url == "https://grafana.example.com/d/abc123"

    def test_dashboard_to_dict(self):
        """Test Dashboard.to_dict() returns correct structure."""
        dashboard = Dashboard(
            uid="abc123",
            title="System Overview",
            folder="Infrastructure",
            tags=["prod"],
            url="https://grafana.example.com/d/abc123",
        )

        data = dashboard.to_dict()

        assert data == {
            "uid": "abc123",
            "title": "System Overview",
            "folder": "Infrastructure",
            "tags": ["prod"],
            "url": "https://grafana.example.com/d/abc123",
        }

# ============================================================================
# Alert Tests
# ============================================================================

class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_init_basic(self):
        """Test Alert initialization with basic fields."""
        alert = Alert(
            uid="alert-1",
            name="High CPU Usage",
            state="alerting",
        )

        assert alert.uid == "alert-1"
        assert alert.name == "High CPU Usage"
        assert alert.state == "alerting"
        assert alert.labels == {}
        assert alert.annotations == {}

    def test_alert_init_full(self):
        """Test Alert initialization with all fields."""
        alert = Alert(
            uid="alert-1",
            name="High CPU Usage",
            state="alerting",
            labels={"severity": "critical", "team": "infra"},
            annotations={"summary": "CPU above 90%"},
            active_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        assert alert.labels == {"severity": "critical", "team": "infra"}
        assert alert.annotations == {"summary": "CPU above 90%"}
        assert alert.active_at == datetime(2024, 1, 15, 10, 30, 0)

    def test_alert_states(self):
        """Test various alert states."""
        states = ["alerting", "pending", "normal", "no_data"]

        for state in states:
            alert = Alert(uid="test", name="Test", state=state)
            assert alert.state == state

# ============================================================================
# GrafanaServer Initialization Tests
# ============================================================================

class TestGrafanaServerInit:
    """Tests for GrafanaServer initialization."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'grafana'."""
        server = GrafanaServer(mock_registry)

        assert server._server_name == "grafana"
        assert server._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        server = GrafanaServer(mock_registry, server_name="custom-grafana")

        assert server._server_name == "custom-grafana"

    def test_init_default_alert_access_level(self, mock_registry):
        """Test default alert access level is VIEW_ONLY."""
        server = GrafanaServer(mock_registry)

        assert server._alert_access == AlertAccessLevel.VIEW_ONLY

    def test_init_custom_alert_access_level(self, mock_registry):
        """Test custom alert access level."""
        server = GrafanaServer(mock_registry, alert_access=AlertAccessLevel.FULL_MANAGEMENT)

        assert server._alert_access == AlertAccessLevel.FULL_MANAGEMENT

# ============================================================================
# GrafanaServer Dashboard Operations Tests
# ============================================================================

class TestGrafanaServerDashboards:
    """Tests for dashboard operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return GrafanaServer(mock_registry)

    def test_list_dashboards(self, server, mock_registry, mock_result_text):
        """Test list_dashboards returns dashboard list."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                [
                    {"uid": "abc", "title": "Dashboard 1", "folderTitle": "General"},
                    {"uid": "def", "title": "Dashboard 2", "folderTitle": "Apps"},
                ]
            )
        )

        dashboards = server.list_dashboards()

        assert len(dashboards) == 2
        assert dashboards[0].uid == "abc"
        assert dashboards[0].title == "Dashboard 1"
        mock_registry.call_tool.assert_called_once()

    def test_list_dashboards_with_folder_filter(self, server, mock_registry, mock_result_text):
        """Test list_dashboards with folder filter."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps([{"uid": "abc", "title": "Dashboard 1", "folderTitle": "Apps"}])
        )

        server.list_dashboards(folder="Apps")

        args = mock_registry.call_tool.call_args
        assert args[0][2].get("folder") == "Apps"

    def test_list_dashboards_with_tags(self, server, mock_registry, mock_result_text):
        """Test list_dashboards with tag filter."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps([{"uid": "abc", "title": "Dashboard 1", "folderTitle": "General"}])
        )

        server.list_dashboards(tags=["production"])

        args = mock_registry.call_tool.call_args
        assert args[0][2].get("tags") == ["production"]

    def test_get_dashboard(self, server, mock_registry, mock_result_text):
        """Test get_dashboard returns dashboard dict."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "uid": "abc",
                    "title": "System Overview",
                    "folderTitle": "Infrastructure",
                    "tags": ["prod"],
                    "url": "https://grafana.example.com/d/abc",
                }
            )
        )

        dashboard = server.get_dashboard("abc")

        # get_dashboard returns a raw dict, not a Dashboard object
        assert isinstance(dashboard, dict)
        assert dashboard["uid"] == "abc"
        assert dashboard["title"] == "System Overview"
        mock_registry.call_tool.assert_called_once_with("grafana", "get_dashboard", {"uid": "abc"})

# ============================================================================
# GrafanaServer Alert Operations Tests
# ============================================================================

class TestGrafanaServerAlerts:
    """Tests for alert operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return GrafanaServer(mock_registry)

    def test_list_alerts(self, server, mock_registry, mock_result_text):
        """Test list_alerts returns alert list."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                [
                    {"uid": "alert-1", "name": "CPU Alert", "state": "alerting"},
                    {"uid": "alert-2", "name": "Memory Alert", "state": "normal"},
                ]
            )
        )

        alerts = server.list_alerts()

        assert len(alerts) == 2
        assert alerts[0].uid == "alert-1"
        assert alerts[0].state == "alerting"

    def test_list_alerts_with_state_filter(self, server, mock_registry, mock_result_text):
        """Test list_alerts with state filter."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps([{"uid": "alert-1", "name": "CPU Alert", "state": "alerting"}])
        )

        server.list_alerts(state="alerting")

        args = mock_registry.call_tool.call_args
        assert args[0][2].get("state") == "alerting"

    def test_acknowledge_alert_allowed(self, mock_registry, mock_result_text):
        """Test acknowledge_alert is allowed with ACKNOWLEDGE access."""
        server = GrafanaServer(mock_registry, alert_access=AlertAccessLevel.ACKNOWLEDGE)
        mock_registry.call_tool.return_value = mock_result_text(json.dumps({"success": True}))

        server.acknowledge_alert("alert-1")

        mock_registry.call_tool.assert_called_once()

    def test_acknowledge_alert_blocked_view_only(self, mock_registry):
        """Test acknowledge_alert is blocked with VIEW_ONLY access."""
        server = GrafanaServer(mock_registry, alert_access=AlertAccessLevel.VIEW_ONLY)

        with pytest.raises(PermissionError, match="VIEW_ONLY"):
            server.acknowledge_alert("alert-1")

        mock_registry.call_tool.assert_not_called()

# ============================================================================
# GrafanaServer Query Operations Tests
# ============================================================================

class TestGrafanaServerQueries:
    """Tests for Prometheus and Loki query operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return GrafanaServer(mock_registry)

    def test_query_prometheus(self, server, mock_registry, mock_result_text):
        """Test query_prometheus returns QueryResult with metric data."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "data": [
                        {
                            "metric": {"__name__": "cpu_usage"},
                            "values": [[1705315200, "0.85"]],
                        }
                    ],
                    "resultType": "matrix",
                }
            )
        )

        result = server.query_prometheus(
            "rate(cpu_usage[5m])",
            time_range=TimeRange.last_hour(),
        )

        from core.mcp.servers.grafana import QueryResult as GrafanaQueryResult

        assert isinstance(result, GrafanaQueryResult)
        assert result.result_type == "matrix"
        assert result.query == "rate(cpu_usage[5m])"
        mock_registry.call_tool.assert_called_once()

    def test_query_prometheus_no_step_param(self, server):
        """Test query_prometheus does not accept a 'step' keyword argument."""
        import inspect

        sig = inspect.signature(server.query_prometheus)
        assert "step" not in sig.parameters

    def test_query_loki(self, server, mock_registry, mock_result_text):
        """Test query_loki returns QueryResult with log data."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "data": [
                        {
                            "stream": {"app": "web"},
                            "values": [["1705315200", "Error occurred"]],
                        }
                    ],
                    "resultType": "streams",
                }
            )
        )

        result = server.query_loki(
            '{app="web"} |= "error"',
            time_range=TimeRange.last_hour(),
        )

        from core.mcp.servers.grafana import QueryResult as GrafanaQueryResult

        assert isinstance(result, GrafanaQueryResult)
        assert result.result_type == "streams"
        assert result.query == '{app="web"} |= "error"'
        mock_registry.call_tool.assert_called_once()

    def test_query_loki_with_limit(self, server, mock_registry, mock_result_text):
        """Test query_loki with limit."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"data": {"resultType": "streams", "result": []}})
        )

        server.query_loki(
            '{app="web"}',
            time_range=TimeRange.last_hour(),
            limit=100,
        )

        args = mock_registry.call_tool.call_args
        assert args[0][2].get("limit") == 100

# ============================================================================
# GrafanaServer Config Tests
# ============================================================================

class TestGrafanaServerConfig:
    """Tests for configuration -- GrafanaServer has no get_http_config class method."""

    def test_no_get_http_config_method(self):
        """Verify get_http_config does not exist (config is external)."""
        assert not hasattr(GrafanaServer, "get_http_config")

    def test_default_time_range_used(self, mock_registry):
        """Test that GrafanaServer uses default time range when none provided."""
        server = GrafanaServer(mock_registry)
        assert server._default_time_range is not None

    def test_custom_default_time_range(self, mock_registry):
        """Test that GrafanaServer accepts a custom default time range."""
        tr = TimeRange.last_day()
        server = GrafanaServer(mock_registry, default_time_range=tr)
        assert server._default_time_range is tr

# ============================================================================
# GrafanaServer Error Handling Tests
# ============================================================================

class TestGrafanaServerErrors:
    """Tests for error handling."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return GrafanaServer(mock_registry)

    def test_query_error_response_parsed_as_json(self, server, mock_registry):
        """Test error response text is still parsed (source does not check isError)."""
        mock_registry.call_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Query failed")],
            isError=True,
        )

        # Source tries json.loads on the text; "Query failed" is not valid JSON
        with pytest.raises(json.JSONDecodeError):
            server.query_prometheus("up", time_range=TimeRange.last_hour())

    def test_invalid_json_response(self, server, mock_registry, mock_result_text):
        """Test handling of invalid JSON response raises JSONDecodeError."""
        mock_registry.call_tool.return_value = mock_result_text("not valid json")

        with pytest.raises(json.JSONDecodeError):
            server.list_dashboards()

    def test_empty_query_sent_to_server(self, server, mock_registry, mock_result_text):
        """Test empty Prometheus query is sent to server (no client-side validation)."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"data": [], "resultType": "matrix"})
        )

        # Source code does not validate empty queries client-side
        result = server.query_prometheus("", time_range=TimeRange.last_hour())
        assert result.data == []
        mock_registry.call_tool.assert_called_once()
