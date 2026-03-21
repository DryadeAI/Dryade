"""Prometheus Metrics for Dryade.

Target: ~100 LOC
"""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Request metrics
REQUEST_COUNT = Counter(
    "dryade_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "dryade_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# CrewAI metrics
CREW_EXECUTIONS = Counter(
    "dryade_crew_executions_total", "Total crew executions", ["crew_name", "status"]
)

CREW_DURATION = Histogram(
    "dryade_crew_duration_seconds",
    "Crew execution duration",
    ["crew_name"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

AGENT_CALLS = Counter("dryade_agent_calls_total", "Total agent calls", ["agent_name"])

TOOL_CALLS = Counter("dryade_tool_calls_total", "Total tool calls", ["tool_name", "status"])

TOOL_DURATION = Histogram(
    "dryade_tool_duration_seconds",
    "Tool execution duration",
    ["tool_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
)

# LLM metrics
LLM_TOKENS = Counter(
    "dryade_llm_tokens_total",
    "Total LLM tokens",
    ["model", "type"],  # label values: input/output
)

LLM_CALLS = Counter("dryade_llm_calls_total", "Total LLM calls", ["model", "status"])

LLM_LATENCY = Histogram(
    "dryade_llm_latency_seconds",
    "LLM call latency",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# System metrics
ACTIVE_SESSIONS = Gauge("dryade_active_sessions", "Number of active MCP sessions")

ACTIVE_WEBSOCKETS = Gauge("dryade_active_websockets", "Number of active WebSocket connections")

# MCP Server metrics
MCP_SERVER_STATUS = Gauge(
    "dryade_mcp_server_status",
    "MCP server status (0=stopped, 1=starting, 2=healthy, 3=unhealthy, 4=crashed)",
    ["server_name"],
)

MCP_SERVER_RESTARTS = Counter(
    "dryade_mcp_server_restarts_total",
    "Total MCP server restart count",
    ["server_name"],
)

MCP_TOOL_CALLS = Counter(
    "dryade_mcp_tool_calls_total",
    "Total MCP tool calls",
    ["server_name", "tool_name", "status"],  # status: ok/error
)

MCP_TOOL_DURATION = Histogram(
    "dryade_mcp_tool_duration_seconds",
    "MCP tool call duration",
    ["server_name", "tool_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
)

# Metrics endpoint router
router = APIRouter()

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Helper functions for recording metrics
def record_request(method: str, endpoint: str, status: int, duration: float):
    """Record HTTP request metrics."""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

def record_crew_execution(crew_name: str, status: str, duration: float):
    """Record crew execution metrics."""
    CREW_EXECUTIONS.labels(crew_name=crew_name, status=status).inc()
    CREW_DURATION.labels(crew_name=crew_name).observe(duration)

def record_agent_call(agent_name: str):
    """Record agent call."""
    AGENT_CALLS.labels(agent_name=agent_name).inc()

def record_tool_call(tool_name: str, status: str, duration: float):
    """Record tool call metrics."""
    TOOL_CALLS.labels(tool_name=tool_name, status=status).inc()
    TOOL_DURATION.labels(tool_name=tool_name).observe(duration)

def record_llm_call(
    model: str, tokens_in: int, tokens_out: int, duration: float, status: str = "ok"
):
    """Record LLM call metrics."""
    LLM_CALLS.labels(model=model, status=status).inc()
    LLM_TOKENS.labels(model=model, type="input").inc(tokens_in)
    LLM_TOKENS.labels(model=model, type="output").inc(tokens_out)
    LLM_LATENCY.labels(model=model).observe(duration)

def set_active_sessions(count: int):
    """Set active sessions gauge."""
    ACTIVE_SESSIONS.set(count)

def set_active_websockets(count: int):
    """Set active WebSocket connections gauge."""
    ACTIVE_WEBSOCKETS.set(count)

# MCP metrics helper functions
def record_mcp_tool_call(server_name: str, tool_name: str, status: str, duration: float):
    """Record MCP tool call metrics."""
    MCP_TOOL_CALLS.labels(server_name=server_name, tool_name=tool_name, status=status).inc()
    MCP_TOOL_DURATION.labels(server_name=server_name, tool_name=tool_name).observe(duration)

# Status enum to numeric mapping for Gauge
_MCP_STATUS_VALUES = {
    "stopped": 0,
    "starting": 1,
    "healthy": 2,
    "unhealthy": 3,
    "crashed": 4,
}

def update_mcp_server_status(server_name: str, status: str):
    """Update MCP server status gauge."""
    MCP_SERVER_STATUS.labels(server_name=server_name).set(_MCP_STATUS_VALUES.get(status, -1))

def record_mcp_server_restart(server_name: str):
    """Record MCP server restart."""
    MCP_SERVER_RESTARTS.labels(server_name=server_name).inc()
