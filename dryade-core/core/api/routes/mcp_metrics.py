"""MCP Server Health API.

Exposes MCP server health metrics for enterprise monitoring dashboards.
Complements the Prometheus metrics at /metrics with a REST API for:
- KPI Monitor plugin dashboards
- External monitoring integrations
- Programmatic health checks

Target: ~80 LOC
"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from core.mcp.registry import get_registry
from core.utils.time import utcnow

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# Response Models

class MCPServerHealth(BaseModel):
    """Health status for a single MCP server."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "restart_count": 0,
                "consecutive_failures": 0,
                "tool_count": 15,
            }
        }
    )

    status: str = Field(
        ..., description="Server status: stopped, starting, healthy, unhealthy, or crashed"
    )
    restart_count: int = Field(
        ..., ge=0, description="Number of automatic restarts since registration"
    )
    consecutive_failures: int = Field(
        default=0, ge=0, description="Consecutive request failures (resets on success)"
    )
    tool_count: int = Field(..., ge=0, description="Number of tools available from this server")

class MCPHealthResponse(BaseModel):
    """Complete MCP health summary response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-02-05T12:00:00Z",
                "servers": {
                    "filesystem": {
                        "status": "healthy",
                        "restart_count": 0,
                        "consecutive_failures": 0,
                        "tool_count": 15,
                    }
                },
                "total_registered": 5,
                "total_running": 3,
                "total_healthy": 3,
            }
        }
    )

    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of health check")
    servers: dict[str, MCPServerHealth] = Field(..., description="Per-server health status")
    total_registered: int = Field(..., ge=0, description="Total registered MCP servers")
    total_running: int = Field(..., ge=0, description="Number of running servers")
    total_healthy: int = Field(..., ge=0, description="Number of healthy servers")

class MCPServerDetailResponse(BaseModel):
    """Detailed health for a single MCP server."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "filesystem",
                "found": True,
                "status": "healthy",
                "restart_count": 0,
                "consecutive_failures": 0,
                "tool_count": 15,
            }
        }
    )

    name: str = Field(..., description="Server name")
    found: bool = Field(..., description="Whether server is registered")
    status: str | None = Field(None, description="Server status if found")
    restart_count: int | None = Field(None, description="Restart count if found")
    consecutive_failures: int | None = Field(None, description="Consecutive failures if found")
    tool_count: int | None = Field(None, description="Tool count if found")

@router.get(
    "/health",
    response_model=MCPHealthResponse,
    summary="MCP server health summary",
    description="Returns health status for all registered MCP servers. "
    "Includes status, restart counts, and tool availability.",
)
async def mcp_health():
    """Get MCP server health summary for monitoring dashboards.

    Returns:
        MCPHealthResponse with per-server health data and aggregate counts.

    Use for:
    - KPI Monitor plugin dashboards
    - External monitoring system integration
    - Debugging MCP server availability issues
    """
    registry = get_registry()
    summary = registry.get_health_summary()

    # Transform to response model format
    servers = {}
    for name, data in summary["servers"].items():
        servers[name] = MCPServerHealth(
            status=data["status"],
            restart_count=data["restart_count"],
            consecutive_failures=data.get("consecutive_failures", 0),
            tool_count=data["tool_count"],
        )

    return MCPHealthResponse(
        timestamp=utcnow().isoformat(),
        servers=servers,
        total_registered=summary["total_registered"],
        total_running=summary["total_running"],
        total_healthy=summary["total_healthy"],
    )

@router.get(
    "/health/{server_name}",
    response_model=MCPServerDetailResponse,
    summary="Single MCP server health",
    description="Returns health status for a specific MCP server by name.",
)
async def mcp_server_health(server_name: str):
    """Get health status for a specific MCP server.

    Args:
        server_name: Name of the MCP server to check.

    Returns:
        MCPServerDetailResponse with server health data.
        If server not found, returns found=False.
    """
    registry = get_registry()
    summary = registry.get_health_summary()

    if server_name not in summary["servers"]:
        return MCPServerDetailResponse(name=server_name, found=False)

    data = summary["servers"][server_name]
    return MCPServerDetailResponse(
        name=server_name,
        found=True,
        status=data["status"],
        restart_count=data["restart_count"],
        consecutive_failures=data.get("consecutive_failures", 0),
        tool_count=data["tool_count"],
    )
