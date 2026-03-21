"""
MCP Gateway - Docker Container Orchestration for MCP Servers

This module provides centralized management of MCP server containers with:
- Resource isolation (CPU, memory limits)
- Network isolation between servers
- Read-only mounts for model files
- Container lifecycle management (start, stop, health checks)
"""

from core.mcp.gateway.server import GatewayServer, app

__all__ = ["app", "GatewayServer"]
