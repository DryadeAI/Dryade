# Grafana MCP Server

| Property | Value |
|----------|-------|
| Package | `@anthropic/mcp-server-grafana` |
| Category | Enterprise |
| Default | Disabled (requires credentials) |
| Transport | STDIO |
| Edition | Enterprise |

## Overview

The Grafana MCP server provides observability integration, enabling AI agents to manage dashboards, handle alerts, and execute metric queries through Prometheus and Loki data sources.

### Key Features

- **Dashboard Management** - Create, update, delete, and query dashboards
- **Alert Handling** - List, acknowledge, and manage alert rules
- **Metric Queries** - Execute PromQL range and instant queries
- **Log Queries** - Execute LogQL queries against Loki
- **Data Source Discovery** - List and inspect configured data sources

### Integrations

- **Prometheus** - Time-series metrics via PromQL
- **Loki** - Log aggregation via LogQL
- **Other data sources** - Access any Grafana-configured data source

## Setup Instructions

### Step 1: Get Grafana API Key

1. Log into your Grafana instance
2. Navigate to **Configuration** > **API Keys** (or **Administration** > **Service Accounts** in newer versions)
3. Click **Add API key** or create a new service account
4. Select appropriate role:
   - **Viewer** - Read-only access (dashboards, alerts, queries)
   - **Editor** - Create/modify dashboards and alerts
   - **Admin** - Full access including data source management
5. Copy the generated API key

### Step 2: Configure Environment

Add credentials to your `.env` file:

```bash
# .env file
GRAFANA_URL=https://your-grafana.example.com
GRAFANA_API_KEY=your-grafana-api-key-here
```

### Step 3: Enable Server

Edit `config/mcp_servers.yaml`:

```yaml
grafana:
  enabled: true
```

## Configuration

Full configuration in `config/mcp_servers.yaml`:

```yaml
grafana:
  enabled: false
  command:
    - npx
    - -y
    - '@anthropic/mcp-server-grafana'
  env:
    GRAFANA_URL: ${GRAFANA_URL}
    GRAFANA_API_KEY: ${GRAFANA_API_KEY}
  description: Observability integration (dashboards, alerts, queries)
  auto_restart: true
  max_restarts: 3
  timeout: 30.0
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable/disable the server |
| `auto_restart` | boolean | true | Restart on crash |
| `max_restarts` | integer | 3 | Maximum restart attempts |
| `timeout` | float | 30.0 | Operation timeout in seconds |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GRAFANA_URL` | Yes | Base URL of Grafana instance |
| `GRAFANA_API_KEY` | Yes | API key or service account token |

## Tool Reference

### Dashboard Tools

#### list_dashboards

List all dashboards with optional filtering.

| Property | Value |
|----------|-------|
| Parameters | `folder?: string`, `tags?: string[]` |
| Returns | `Dashboard[]` |
| Purpose | Discover available dashboards |

**Example:**

```python
# List all dashboards
dashboards = registry.call_tool("grafana", "list_dashboards", {})

# Filter by folder
dashboards = registry.call_tool("grafana", "list_dashboards", {
    "folder": "Production"
})

# Filter by tags
dashboards = registry.call_tool("grafana", "list_dashboards", {
    "tags": ["kubernetes", "monitoring"]
})
```

#### get_dashboard

Retrieve full dashboard JSON by UID.

| Property | Value |
|----------|-------|
| Parameters | `uid: string` |
| Returns | Dashboard JSON object |
| Purpose | Get complete dashboard configuration |

**Example:**

```python
dashboard = registry.call_tool("grafana", "get_dashboard", {
    "uid": "abc123def"
})
# Returns full dashboard JSON including panels, queries, variables
```

#### create_dashboard

Create a new dashboard.

| Property | Value |
|----------|-------|
| Parameters | `dashboard: object` |
| Returns | `Dashboard` with assigned UID |
| Purpose | Create new dashboard |

**Example:**

```python
result = registry.call_tool("grafana", "create_dashboard", {
    "dashboard": {
        "title": "API Performance",
        "panels": [...],
        "tags": ["api", "performance"]
    }
})
```

#### update_dashboard

Update an existing dashboard.

| Property | Value |
|----------|-------|
| Parameters | `uid: string`, `dashboard: object` |
| Returns | Updated `Dashboard` |
| Purpose | Modify dashboard configuration |

**Example:**

```python
result = registry.call_tool("grafana", "update_dashboard", {
    "uid": "abc123def",
    "dashboard": {
        "title": "API Performance v2",
        "panels": [...]
    }
})
```

#### delete_dashboard

Delete a dashboard by UID.

| Property | Value |
|----------|-------|
| Parameters | `uid: string` |
| Returns | `void` |
| Purpose | Remove dashboard |

**Example:**

```python
registry.call_tool("grafana", "delete_dashboard", {
    "uid": "abc123def"
})
```

### Alert Tools

#### list_alerts

List current alerts with optional filtering.

| Property | Value |
|----------|-------|
| Parameters | `state?: string`, `labels?: object` |
| Returns | `Alert[]` |
| Purpose | View active/pending/resolved alerts |

**Example:**

```python
# List all firing alerts
alerts = registry.call_tool("grafana", "list_alerts", {
    "state": "firing"
})

# Filter by labels
alerts = registry.call_tool("grafana", "list_alerts", {
    "labels": {"severity": "critical", "team": "platform"}
})
```

#### get_alert

Get detailed information about a specific alert.

| Property | Value |
|----------|-------|
| Parameters | `uid: string` |
| Returns | `Alert` object |
| Purpose | Inspect alert details |

**Example:**

```python
alert = registry.call_tool("grafana", "get_alert", {
    "uid": "alert-123"
})
# Returns: state, labels, annotations, evaluation time, etc.
```

#### acknowledge_alert

Acknowledge an alert to silence notifications.

| Property | Value |
|----------|-------|
| Parameters | `uid: string`, `comment?: string` |
| Returns | `void` |
| Purpose | Acknowledge alert |

**Example:**

```python
registry.call_tool("grafana", "acknowledge_alert", {
    "uid": "alert-123",
    "comment": "Investigating - ticket INFRA-456"
})
```

#### create_alert_rule

Create a new alert rule.

| Property | Value |
|----------|-------|
| Parameters | `rule: object` |
| Returns | `Alert` |
| Purpose | Define new alerting condition |

**Example:**

```python
result = registry.call_tool("grafana", "create_alert_rule", {
    "rule": {
        "name": "High CPU Usage",
        "condition": "avg(rate(cpu_usage[5m])) > 0.8",
        "for": "5m",
        "labels": {"severity": "warning"},
        "annotations": {"summary": "CPU usage above 80%"}
    }
})
```

#### update_alert_rule

Update an existing alert rule.

| Property | Value |
|----------|-------|
| Parameters | `uid: string`, `rule: object` |
| Returns | Updated `Alert` |
| Purpose | Modify alert configuration |

#### delete_alert_rule

Delete an alert rule.

| Property | Value |
|----------|-------|
| Parameters | `uid: string` |
| Returns | `void` |
| Purpose | Remove alert rule |

### Query Tools

#### query_prometheus

Execute a PromQL range query.

| Property | Value |
|----------|-------|
| Parameters | `query: string`, `from?: string`, `to?: string`, `step?: string` |
| Returns | `QueryResult` with time series |
| Purpose | Query Prometheus metrics over time |

**Example:**

```python
# CPU usage over the last hour
result = registry.call_tool("grafana", "query_prometheus", {
    "query": "rate(process_cpu_seconds_total[5m])",
    "from": "now-1h",
    "to": "now",
    "step": "1m"
})

# Memory by container
result = registry.call_tool("grafana", "query_prometheus", {
    "query": "container_memory_usage_bytes{namespace='production'}",
    "from": "now-6h",
    "to": "now"
})
```

#### query_prometheus_instant

Execute a PromQL instant query (current values).

| Property | Value |
|----------|-------|
| Parameters | `query: string` |
| Returns | `QueryResult` |
| Purpose | Get current metric values |

**Example:**

```python
# Current memory usage
result = registry.call_tool("grafana", "query_prometheus_instant", {
    "query": "process_resident_memory_bytes"
})

# Count of running pods
result = registry.call_tool("grafana", "query_prometheus_instant", {
    "query": "count(kube_pod_status_phase{phase='Running'})"
})
```

#### query_loki

Execute a LogQL query against Loki.

| Property | Value |
|----------|-------|
| Parameters | `query: string`, `from?: string`, `to?: string`, `limit?: int` |
| Returns | `QueryResult` with log entries |
| Purpose | Search and analyze logs |

**Example:**

```python
# Search for errors
result = registry.call_tool("grafana", "query_loki", {
    "query": '{app="dryade"} |= "error"',
    "from": "now-1h",
    "to": "now",
    "limit": 100
})

# Extract structured fields
result = registry.call_tool("grafana", "query_loki", {
    "query": '{job="api"} | json | status >= 500',
    "from": "now-30m",
    "to": "now"
})
```

### Data Source Tools

#### list_data_sources

List all configured data sources.

| Property | Value |
|----------|-------|
| Parameters | (none) |
| Returns | `DataSource[]` |
| Purpose | Discover available data sources |

**Example:**

```python
sources = registry.call_tool("grafana", "list_data_sources", {})
for source in sources:
    print(f"{source['name']}: {source['type']}")
```

#### get_data_source

Get details about a specific data source.

| Property | Value |
|----------|-------|
| Parameters | `uid: string` |
| Returns | `DataSource` |
| Purpose | Inspect data source configuration |

**Example:**

```python
source = registry.call_tool("grafana", "get_data_source", {
    "uid": "prometheus-main"
})
```

## Python Wrapper Usage

```python
from core.mcp import get_registry
from core.mcp.servers import GrafanaServer

registry = get_registry()
grafana = GrafanaServer(registry)

# List dashboards
dashboards = grafana.list_dashboards(tags=["production"])
for d in dashboards:
    print(f"{d['title']} (uid: {d['uid']})")

# Query metrics
cpu_data = grafana.query_prometheus(
    query="rate(process_cpu_seconds_total{job='api'}[5m])",
    from_time="now-1h",
    to_time="now"
)

# Check alerts
firing = grafana.list_alerts(state="firing")
for alert in firing:
    print(f"ALERT: {alert['name']} - {alert['state']}")

# Search logs
errors = grafana.query_loki(
    query='{app="dryade"} |= "error"',
    limit=50
)
for entry in errors:
    print(f"{entry['timestamp']}: {entry['line']}")
```

## PromQL Examples

### Common Patterns

```python
# Request rate per endpoint
result = grafana.query_prometheus(
    query='sum(rate(http_requests_total[5m])) by (endpoint)',
    from_time="now-1h",
    to_time="now"
)

# Error rate percentage
result = grafana.query_prometheus(
    query='sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
    from_time="now-1h",
    to_time="now"
)

# 95th percentile latency
result = grafana.query_prometheus(
    query='histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))',
    from_time="now-1h",
    to_time="now"
)

# Memory growth rate
result = grafana.query_prometheus(
    query='deriv(process_resident_memory_bytes[1h])',
    from_time="now-6h",
    to_time="now"
)
```

### Aggregations

```python
# Total by label
'sum(metric) by (label)'

# Average across instances
'avg(metric) without (instance)'

# Top 10 by value
'topk(10, metric)'

# Rate of change
'rate(counter[5m])'
'irate(counter[5m])'  # instant rate

# Increase over time
'increase(counter[1h])'
```

## LogQL Examples

### Search Patterns

```python
# Simple text search
'{app="dryade"} |= "error"'

# Negative search
'{app="dryade"} != "debug"'

# Regex match
'{job="api"} |~ "user_id=\\d+"'

# Case insensitive
'{app="dryade"} |~ "(?i)warning"'
```

### JSON Parsing

```python
# Parse JSON and filter
'{job="api"} | json | status >= 500'

# Extract specific fields
'{job="api"} | json | line_format "{{.method}} {{.path}} {{.status}}"'

# Filter by JSON field
'{job="api"} | json | user_id = "12345"'
```

### Metrics from Logs

```python
# Count log entries
'count_over_time({app="dryade"} |= "error" [1h])'

# Rate of errors
'rate({app="dryade"} |= "error" [5m])'

# Bytes processed
'bytes_over_time({job="api"}[1h])'
```

## Use Cases

### Automated Alert Triage

```python
# Get firing alerts and analyze
alerts = grafana.list_alerts(state="firing")

for alert in alerts:
    # Get related metrics
    query = alert.get('query', '')
    if query:
        data = grafana.query_prometheus(query=query, from_time="now-1h")
        # Analyze trend, find root cause

    # Get related logs
    labels = alert.get('labels', {})
    if 'app' in labels:
        logs = grafana.query_loki(
            query=f'{{app="{labels["app"]}"}} |= "error"',
            limit=20
        )
```

### Dashboard Provisioning

```python
# Create standardized dashboard for new service
def create_service_dashboard(service_name):
    dashboard = {
        "title": f"{service_name} Overview",
        "tags": ["auto-generated", service_name],
        "panels": [
            create_request_rate_panel(service_name),
            create_error_rate_panel(service_name),
            create_latency_panel(service_name),
            create_resource_panel(service_name)
        ]
    }
    return grafana.create_dashboard(dashboard)
```

### Metric-Based Decisions

```python
# Check if scaling is needed
cpu = grafana.query_prometheus_instant(
    query='avg(rate(container_cpu_usage_seconds_total{app="api"}[5m]))'
)

if cpu > 0.8:
    # Trigger scale up
    pass
elif cpu < 0.2:
    # Trigger scale down
    pass
```

## Troubleshooting

### Unauthorized Error

```
Error: Unauthorized (401)
```

**Causes:**
- Invalid or expired API key
- API key lacks required permissions

**Solutions:**
1. Generate new API key in Grafana
2. Verify key has appropriate role (Viewer/Editor/Admin)
3. Check GRAFANA_API_KEY in `.env`

### Dashboard Not Found

```
Error: Dashboard not found
```

**Causes:**
- Incorrect dashboard UID
- Dashboard was deleted
- Insufficient permissions

**Solutions:**
1. Use `list_dashboards` to find correct UID
2. Verify dashboard exists in Grafana UI
3. Check API key permissions

### Query Timeout

```
Error: Query timeout
```

**Causes:**
- Complex query on large dataset
- Missing recording rules
- Prometheus/Loki resource constraints

**Solutions:**
1. Reduce time range (e.g., `now-1h` instead of `now-7d`)
2. Add more specific label filters
3. Use recording rules for expensive queries
4. Increase `timeout` in configuration

### Empty Query Results

```
Query returned no data
```

**Causes:**
- Incorrect metric name
- Label selectors too restrictive
- No data in time range

**Solutions:**
1. Verify metric exists: `count(metric_name)`
2. Check available labels: `metric_name{}`
3. Expand time range
4. Test query in Grafana Explore

### Connection Refused

```
Error: Connection refused
```

**Causes:**
- Incorrect GRAFANA_URL
- Grafana not accessible from host
- Network/firewall issues

**Solutions:**
1. Verify URL is correct (include protocol)
2. Test with `curl $GRAFANA_URL/api/health`
3. Check network connectivity

## Related Documentation

- [MCP Overview](../README.md)
- [Tool Inventory](../INVENTORY.md)
- [Agent Integration](../integration/agent-integration.md)
- [Prometheus Query Documentation](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Loki Query Documentation](https://grafana.com/docs/loki/latest/logql/)
