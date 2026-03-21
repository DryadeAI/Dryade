"""Grafana MCP Server wrapper.

Provides typed Python interface for Grafana MCP server
with full observability integration: dashboards, alerts, and direct queries.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry
from core.utils.time import utcnow

class AlertAccessLevel(Enum):
    """Alert management access level.

    Controls what alert operations are permitted:
    - VIEW_ONLY: Can only view alerts and their status
    - ACKNOWLEDGE: Can view and acknowledge alerts
    - FULL_MANAGEMENT: Full create/update/delete operations
    """

    VIEW_ONLY = "view_only"
    ACKNOWLEDGE = "acknowledge"
    FULL_MANAGEMENT = "full"

@dataclass
class TimeRange:
    """Time range for Prometheus/Loki queries.

    Provides a typed representation of query time ranges with
    convenient factory methods for common intervals.

    Attributes:
        start: Start of the time range (UTC).
        end: End of the time range (UTC).

    Example:
        >>> tr = TimeRange.last_hour()
        >>> tr.to_dict()
        {'from': '2024-01-15T10:00:00Z', 'to': '2024-01-15T11:00:00Z'}
    """

    start: datetime
    end: datetime

    @classmethod
    def last_hour(cls) -> TimeRange:
        """Create a time range for the last hour.

        Returns:
            TimeRange from 1 hour ago to now.
        """
        end = utcnow()
        return cls(start=end - timedelta(hours=1), end=end)

    @classmethod
    def last_day(cls) -> TimeRange:
        """Create a time range for the last 24 hours.

        Returns:
            TimeRange from 24 hours ago to now.
        """
        end = utcnow()
        return cls(start=end - timedelta(days=1), end=end)

    @classmethod
    def last_week(cls) -> TimeRange:
        """Create a time range for the last 7 days.

        Returns:
            TimeRange from 7 days ago to now.
        """
        end = utcnow()
        return cls(start=end - timedelta(weeks=1), end=end)

    def to_dict(self) -> dict[str, str]:
        """Convert to Grafana-compatible dict format.

        Returns:
            Dict with 'from' and 'to' keys in ISO format with Z suffix.
        """
        return {
            "from": self.start.isoformat() + "Z",
            "to": self.end.isoformat() + "Z",
        }

@dataclass
class Dashboard:
    """Grafana dashboard metadata.

    Represents dashboard information returned from list/get operations.

    Attributes:
        uid: Unique identifier for the dashboard.
        title: Display title of the dashboard.
        folder: Folder containing the dashboard (None for General).
        tags: List of tags associated with the dashboard.
        url: Full URL to access the dashboard in Grafana UI.
    """

    uid: str
    title: str
    folder: str | None
    tags: list[str] = field(default_factory=list)
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dict with all dashboard fields.
        """
        return {
            "uid": self.uid,
            "title": self.title,
            "folder": self.folder,
            "tags": self.tags,
            "url": self.url,
        }

@dataclass
class Alert:
    """Grafana alert instance.

    Represents an alert rule instance with its current state.

    Attributes:
        uid: Unique identifier for the alert.
        name: Display name of the alert rule.
        state: Current state (alerting, pending, normal, no_data).
        labels: Key-value labels attached to the alert.
        annotations: Descriptive annotations (summary, description, etc.).
        active_at: When the alert became active (None if not active).
    """

    uid: str
    name: str
    state: str  # alerting, pending, normal, no_data
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    active_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dict with all alert fields.
        """
        return {
            "uid": self.uid,
            "name": self.name,
            "state": self.state,
            "labels": self.labels,
            "annotations": self.annotations,
            "active_at": self.active_at.isoformat() if self.active_at else None,
        }

@dataclass
class QueryResult:
    """Result from Prometheus/Loki query.

    Contains query results with metadata about execution.

    Attributes:
        query: The PromQL or LogQL query that was executed.
        data: Result data (time series, instant vectors, or log streams).
        result_type: Type of result (matrix, vector, scalar, streams).
        execution_time_ms: Query execution time in milliseconds.
    """

    query: str
    data: list[dict[str, Any]]
    result_type: str  # matrix, vector, scalar, streams
    execution_time_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dict with all query result fields.
        """
        return {
            "query": self.query,
            "data": self.data,
            "result_type": self.result_type,
            "execution_time_ms": self.execution_time_ms,
        }

@dataclass
class DataSource:
    """Grafana data source.

    Represents a configured data source in Grafana.

    Attributes:
        uid: Unique identifier for the data source.
        name: Display name of the data source.
        type: Data source type (prometheus, loki, influxdb, etc.).
        url: Connection URL for the data source.
        is_default: Whether this is the default data source of its type.
    """

    uid: str
    name: str
    type: str  # prometheus, loki, influxdb, etc.
    url: str | None = None
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dict with all data source fields.
        """
        return {
            "uid": self.uid,
            "name": self.name,
            "type": self.type,
            "url": self.url,
            "is_default": self.is_default,
        }

class GrafanaServer:
    """Typed wrapper for Grafana MCP server.

    Provides typed Python methods for Grafana operations:
    - Dashboard management: list, get, create, update, delete
    - Alert management: list, get, acknowledge, create (per access level)
    - Direct queries: Prometheus PromQL, Loki LogQL
    - Data sources: list, get

    The server supports configurable alert access levels to control
    what operations are permitted. Time ranges can be customized per-query
    or use sensible defaults.

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="grafana",
        ...     command=["npx", "-y", "grafana-mcp"],
        ...     env={"GRAFANA_URL": "http://localhost:3000", "GRAFANA_TOKEN": "..."}
        ... )
        >>> registry.register(config)
        >>> grafana = GrafanaServer(registry)
        >>> dashboards = grafana.list_dashboards()
        >>> alerts = grafana.list_alerts(state="alerting")
    """

    def __init__(
        self,
        registry: MCPRegistry,
        server_name: str = "grafana",
        alert_access: AlertAccessLevel = AlertAccessLevel.VIEW_ONLY,
        default_time_range: TimeRange | None = None,
    ) -> None:
        """Initialize GrafanaServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the grafana server in registry.
            alert_access: Alert management access level.
            default_time_range: Default time range for queries. If not provided,
                uses TimeRange.last_hour().
        """
        self._registry = registry
        self._server_name = server_name
        self._alert_access = alert_access
        self._default_time_range = default_time_range or TimeRange.last_hour()

    # -------------------------------------------------------------------------
    # Dashboard Methods
    # -------------------------------------------------------------------------

    def list_dashboards(
        self,
        folder: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Dashboard]:
        """List available dashboards with optional filtering.

        Args:
            folder: Filter by folder name (None for all folders).
            tags: Filter by tags (dashboards must have all specified tags).

        Returns:
            List of Dashboard objects matching the criteria.

        Raises:
            MCPTransportError: If the dashboard list cannot be retrieved.

        Example:
            >>> dashboards = grafana.list_dashboards(tags=["production"])
            >>> for d in dashboards:
            ...     print(f"{d.title}: {d.uid}")
        """
        args: dict[str, Any] = {}
        if folder:
            args["folder"] = folder
        if tags:
            args["tags"] = tags

        result = self._registry.call_tool(self._server_name, "list_dashboards", args)
        text = self._extract_text(result)
        if not text:
            return []

        data = json.loads(text)
        dashboards = []
        for item in data:
            dashboards.append(
                Dashboard(
                    uid=item.get("uid", ""),
                    title=item.get("title", ""),
                    folder=item.get("folder"),
                    tags=item.get("tags", []),
                    url=item.get("url"),
                )
            )
        return dashboards

    def get_dashboard(self, uid: str) -> dict[str, Any]:
        """Get full dashboard JSON by UID.

        Retrieves the complete dashboard model including panels,
        variables, and all configuration.

        Args:
            uid: Dashboard unique identifier.

        Returns:
            Full dashboard JSON as a dictionary.

        Raises:
            MCPTransportError: If the dashboard cannot be retrieved.

        Example:
            >>> dashboard = grafana.get_dashboard("abc123")
            >>> panels = dashboard.get("panels", [])
        """
        result = self._registry.call_tool(self._server_name, "get_dashboard", {"uid": uid})
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return {}

    def create_dashboard(self, dashboard: dict[str, Any]) -> Dashboard:
        """Create a new dashboard.

        Args:
            dashboard: Dashboard configuration dict with panels, title, etc.
                Must include at minimum a "title" field.

        Returns:
            Dashboard object with the created dashboard's metadata.

        Raises:
            MCPTransportError: If the dashboard cannot be created.

        Example:
            >>> new_dash = grafana.create_dashboard({
            ...     "title": "My Dashboard",
            ...     "panels": [...]
            ... })
        """
        result = self._registry.call_tool(
            self._server_name, "create_dashboard", {"dashboard": dashboard}
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return Dashboard(
                uid=data.get("uid", ""),
                title=data.get("title", dashboard.get("title", "")),
                folder=data.get("folder"),
                tags=data.get("tags", []),
                url=data.get("url"),
            )
        return Dashboard(uid="", title=dashboard.get("title", ""), folder=None)

    def update_dashboard(self, uid: str, dashboard: dict[str, Any]) -> Dashboard:
        """Update an existing dashboard.

        Args:
            uid: Dashboard unique identifier.
            dashboard: Updated dashboard configuration dict.

        Returns:
            Dashboard object with the updated dashboard's metadata.

        Raises:
            MCPTransportError: If the dashboard cannot be updated.

        Example:
            >>> updated = grafana.update_dashboard("abc123", {
            ...     "title": "Updated Title",
            ...     "panels": [...]
            ... })
        """
        result = self._registry.call_tool(
            self._server_name,
            "update_dashboard",
            {"uid": uid, "dashboard": dashboard},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return Dashboard(
                uid=data.get("uid", uid),
                title=data.get("title", dashboard.get("title", "")),
                folder=data.get("folder"),
                tags=data.get("tags", []),
                url=data.get("url"),
            )
        return Dashboard(uid=uid, title=dashboard.get("title", ""), folder=None)

    def delete_dashboard(self, uid: str) -> None:
        """Delete a dashboard.

        Args:
            uid: Dashboard unique identifier to delete.

        Raises:
            MCPTransportError: If the dashboard cannot be deleted.

        Example:
            >>> grafana.delete_dashboard("abc123")
        """
        self._registry.call_tool(self._server_name, "delete_dashboard", {"uid": uid})

    # -------------------------------------------------------------------------
    # Alert Methods
    # -------------------------------------------------------------------------

    def list_alerts(
        self,
        state: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> list[Alert]:
        """List alerts, optionally filtered by state or labels.

        Args:
            state: Filter by state (alerting, pending, normal, no_data).
            labels: Filter by label key-value pairs.

        Returns:
            List of Alert objects matching criteria.

        Raises:
            MCPTransportError: If the alert list cannot be retrieved.

        Example:
            >>> firing = grafana.list_alerts(state="alerting")
            >>> for alert in firing:
            ...     print(f"ALERT: {alert.name}")
        """
        args: dict[str, Any] = {}
        if state:
            args["state"] = state
        if labels:
            args["labels"] = labels

        result = self._registry.call_tool(self._server_name, "list_alerts", args)
        text = self._extract_text(result)
        if not text:
            return []

        data = json.loads(text)
        alerts = []
        for item in data:
            active_at = None
            if item.get("active_at"):
                with contextlib.suppress(ValueError, AttributeError):
                    active_at = datetime.fromisoformat(item["active_at"].replace("Z", "+00:00"))

            alerts.append(
                Alert(
                    uid=item.get("uid", ""),
                    name=item.get("name", ""),
                    state=item.get("state", ""),
                    labels=item.get("labels", {}),
                    annotations=item.get("annotations", {}),
                    active_at=active_at,
                )
            )
        return alerts

    def get_alert(self, uid: str) -> Alert:
        """Get a specific alert by UID.

        Args:
            uid: Alert unique identifier.

        Returns:
            Alert object with full details.

        Raises:
            MCPTransportError: If the alert cannot be retrieved.

        Example:
            >>> alert = grafana.get_alert("alert-123")
            >>> print(alert.annotations.get("description"))
        """
        result = self._registry.call_tool(self._server_name, "get_alert", {"uid": uid})
        text = self._extract_text(result)
        if text:
            item = json.loads(text)
            active_at = None
            if item.get("active_at"):
                with contextlib.suppress(ValueError, AttributeError):
                    active_at = datetime.fromisoformat(item["active_at"].replace("Z", "+00:00"))

            return Alert(
                uid=item.get("uid", ""),
                name=item.get("name", ""),
                state=item.get("state", ""),
                labels=item.get("labels", {}),
                annotations=item.get("annotations", {}),
                active_at=active_at,
            )
        return Alert(uid=uid, name="", state="unknown")

    def acknowledge_alert(self, uid: str, comment: str = "") -> None:
        """Acknowledge an alert.

        Acknowledging an alert marks it as seen and stops notifications
        for the current firing instance.

        Args:
            uid: Alert UID to acknowledge.
            comment: Optional comment for the acknowledgment.

        Raises:
            PermissionError: If alert_access is VIEW_ONLY.
            MCPTransportError: If the alert cannot be acknowledged.

        Example:
            >>> grafana.acknowledge_alert("alert-123", "Investigating")
        """
        if self._alert_access == AlertAccessLevel.VIEW_ONLY:
            raise PermissionError("Alert access level VIEW_ONLY does not allow acknowledgment")

        args: dict[str, Any] = {"uid": uid}
        if comment:
            args["comment"] = comment

        self._registry.call_tool(self._server_name, "acknowledge_alert", args)

    def create_alert_rule(self, rule: dict[str, Any]) -> Alert:
        """Create a new alert rule.

        Args:
            rule: Alert rule configuration dict including:
                - name: Rule name
                - condition: PromQL/LogQL condition
                - duration: How long condition must be true
                - labels: Labels to attach
                - annotations: Annotations (summary, description, etc.)

        Returns:
            Alert object for the created rule.

        Raises:
            PermissionError: If alert_access is not FULL_MANAGEMENT.
            MCPTransportError: If the alert rule cannot be created.

        Example:
            >>> rule = grafana.create_alert_rule({
            ...     "name": "High CPU",
            ...     "condition": "avg(cpu_usage) > 80",
            ...     "duration": "5m",
            ...     "labels": {"severity": "warning"},
            ...     "annotations": {"summary": "CPU usage is high"}
            ... })
        """
        if self._alert_access != AlertAccessLevel.FULL_MANAGEMENT:
            raise PermissionError(
                f"Alert access level {self._alert_access.value} does not allow creating rules"
            )

        result = self._registry.call_tool(self._server_name, "create_alert_rule", {"rule": rule})
        text = self._extract_text(result)
        if text:
            item = json.loads(text)
            return Alert(
                uid=item.get("uid", ""),
                name=item.get("name", rule.get("name", "")),
                state=item.get("state", "normal"),
                labels=item.get("labels", rule.get("labels", {})),
                annotations=item.get("annotations", rule.get("annotations", {})),
            )
        return Alert(
            uid="",
            name=rule.get("name", ""),
            state="normal",
            labels=rule.get("labels", {}),
            annotations=rule.get("annotations", {}),
        )

    def update_alert_rule(self, uid: str, rule: dict[str, Any]) -> Alert:
        """Update an existing alert rule.

        Args:
            uid: Alert rule UID to update.
            rule: Updated alert rule configuration.

        Returns:
            Alert object for the updated rule.

        Raises:
            PermissionError: If alert_access is not FULL_MANAGEMENT.
            MCPTransportError: If the alert rule cannot be updated.

        Example:
            >>> updated = grafana.update_alert_rule("alert-123", {
            ...     "condition": "avg(cpu_usage) > 90"
            ... })
        """
        if self._alert_access != AlertAccessLevel.FULL_MANAGEMENT:
            raise PermissionError(
                f"Alert access level {self._alert_access.value} does not allow updating rules"
            )

        result = self._registry.call_tool(
            self._server_name, "update_alert_rule", {"uid": uid, "rule": rule}
        )
        text = self._extract_text(result)
        if text:
            item = json.loads(text)
            return Alert(
                uid=item.get("uid", uid),
                name=item.get("name", rule.get("name", "")),
                state=item.get("state", "normal"),
                labels=item.get("labels", rule.get("labels", {})),
                annotations=item.get("annotations", rule.get("annotations", {})),
            )
        return Alert(uid=uid, name=rule.get("name", ""), state="normal")

    def delete_alert_rule(self, uid: str) -> None:
        """Delete an alert rule.

        Args:
            uid: Alert rule UID to delete.

        Raises:
            PermissionError: If alert_access is not FULL_MANAGEMENT.
            MCPTransportError: If the alert rule cannot be deleted.

        Example:
            >>> grafana.delete_alert_rule("alert-123")
        """
        if self._alert_access != AlertAccessLevel.FULL_MANAGEMENT:
            raise PermissionError(
                f"Alert access level {self._alert_access.value} does not allow deleting rules"
            )

        self._registry.call_tool(self._server_name, "delete_alert_rule", {"uid": uid})

    # -------------------------------------------------------------------------
    # Query Methods (Prometheus and Loki)
    # -------------------------------------------------------------------------

    def query_prometheus(
        self,
        query: str,
        time_range: TimeRange | None = None,
    ) -> QueryResult:
        """Execute a Prometheus range query.

        Queries Prometheus through Grafana's data source proxy,
        returning time series data over the specified range.

        Args:
            query: PromQL query string.
            time_range: Time range for the query. If not provided,
                uses the default time range.

        Returns:
            QueryResult with time series data.

        Raises:
            MCPTransportError: If the query fails.

        Example:
            >>> result = grafana.query_prometheus(
            ...     "rate(http_requests_total[5m])",
            ...     TimeRange.last_hour()
            ... )
            >>> for series in result.data:
            ...     print(series["metric"])
        """
        tr = time_range or self._default_time_range
        result = self._registry.call_tool(
            self._server_name,
            "query_prometheus",
            {"query": query, **tr.to_dict()},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return QueryResult(
                query=query,
                data=data.get("data", []),
                result_type=data.get("resultType", "matrix"),
                execution_time_ms=data.get("executionTime"),
            )
        return QueryResult(query=query, data=[], result_type="matrix")

    def query_prometheus_instant(self, query: str) -> QueryResult:
        """Execute a Prometheus instant query.

        Returns the current value(s) at this moment in time.

        Args:
            query: PromQL query string.

        Returns:
            QueryResult with instant vector data.

        Raises:
            MCPTransportError: If the query fails.

        Example:
            >>> result = grafana.query_prometheus_instant("up")
            >>> for vector in result.data:
            ...     print(f"{vector['metric']}: {vector['value']}")
        """
        result = self._registry.call_tool(
            self._server_name,
            "query_prometheus_instant",
            {"query": query},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return QueryResult(
                query=query,
                data=data.get("data", []),
                result_type=data.get("resultType", "vector"),
                execution_time_ms=data.get("executionTime"),
            )
        return QueryResult(query=query, data=[], result_type="vector")

    def query_loki(
        self,
        query: str,
        time_range: TimeRange | None = None,
        limit: int = 1000,
    ) -> QueryResult:
        """Execute a Loki log query.

        Queries Loki through Grafana's data source proxy,
        returning log streams matching the LogQL expression.

        Args:
            query: LogQL query string.
            time_range: Time range for the query. If not provided,
                uses the default time range.
            limit: Maximum number of log entries to return (default: 1000).

        Returns:
            QueryResult with log stream data.

        Raises:
            MCPTransportError: If the query fails.

        Example:
            >>> result = grafana.query_loki(
            ...     '{app="myapp"} |= "error"',
            ...     TimeRange.last_day(),
            ...     limit=100
            ... )
            >>> for stream in result.data:
            ...     for entry in stream["values"]:
            ...         print(entry[1])  # Log line
        """
        tr = time_range or self._default_time_range
        result = self._registry.call_tool(
            self._server_name,
            "query_loki",
            {"query": query, "limit": limit, **tr.to_dict()},
        )
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return QueryResult(
                query=query,
                data=data.get("data", []),
                result_type=data.get("resultType", "streams"),
                execution_time_ms=data.get("executionTime"),
            )
        return QueryResult(query=query, data=[], result_type="streams")

    # -------------------------------------------------------------------------
    # Data Source Methods
    # -------------------------------------------------------------------------

    def list_data_sources(self) -> list[DataSource]:
        """List all configured data sources.

        Returns:
            List of DataSource objects for all configured sources.

        Raises:
            MCPTransportError: If the data source list cannot be retrieved.

        Example:
            >>> sources = grafana.list_data_sources()
            >>> prometheus = next(s for s in sources if s.type == "prometheus")
        """
        result = self._registry.call_tool(self._server_name, "list_data_sources", {})
        text = self._extract_text(result)
        if not text:
            return []

        data = json.loads(text)
        sources = []
        for item in data:
            sources.append(
                DataSource(
                    uid=item.get("uid", ""),
                    name=item.get("name", ""),
                    type=item.get("type", ""),
                    url=item.get("url"),
                    is_default=item.get("isDefault", False),
                )
            )
        return sources

    def get_data_source(self, uid: str) -> DataSource:
        """Get a specific data source by UID.

        Args:
            uid: Data source unique identifier.

        Returns:
            DataSource object with full details.

        Raises:
            MCPTransportError: If the data source cannot be retrieved.

        Example:
            >>> source = grafana.get_data_source("prometheus-1")
            >>> print(f"URL: {source.url}")
        """
        result = self._registry.call_tool(self._server_name, "get_data_source", {"uid": uid})
        text = self._extract_text(result)
        if text:
            item = json.loads(text)
            return DataSource(
                uid=item.get("uid", ""),
                name=item.get("name", ""),
                type=item.get("type", ""),
                url=item.get("url"),
                is_default=item.get("isDefault", False),
            )
        return DataSource(uid=uid, name="", type="")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""
