# Migrated from plugins/starter/mcp/bridge.py into core (Phase 222).
# Generic MCPBridge only -- Capella-specific tools excluded (17 @tool decorators).
"""Generic bridge between CrewAI tools and MCP servers.

Provides the stateless MCPBridge class for communicating with any MCP server,
plus utility functions for dynamic tool discovery and wrapper generation.
"""

import logging
from typing import Any

import httpx
from crewai.tools import tool

logger = logging.getLogger("dryade.bridge")

class MCPBridge:
    """Stateless bridge to MCP server."""

    def __init__(self, base_url: str):
        """Initialize MCP bridge.

        Args:
            base_url: MCP server URL (e.g. "http://localhost:8000").
        """
        self.base_url = base_url
        self._client = httpx.Client(timeout=300)

    def call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call MCP tool and return result."""
        response = self._client.post(
            f"{self.base_url}/tools/{tool_name}",
            json=args,
        )
        response.raise_for_status()
        return response.json()

    def list_tools(self) -> list[dict[str, Any]]:
        """List available MCP tools."""
        response = self._client.get(f"{self.base_url}/tools")
        response.raise_for_status()
        return response.json()

# Global bridge instance (lazy initialization)
_bridge: MCPBridge | None = None

def get_bridge(base_url: str | None = None) -> MCPBridge:
    """Get or create the global MCP bridge instance.

    Args:
        base_url: MCP server URL. Required on first call, optional thereafter.

    Returns:
        MCPBridge instance.

    Raises:
        ValueError: If no URL provided and no bridge exists yet.
    """
    global _bridge
    if _bridge is None:
        if base_url is None:
            raise ValueError("base_url is required when creating the first MCPBridge instance")
        _bridge = MCPBridge(base_url)
    return _bridge

def reset_bridge() -> None:
    """Reset the global bridge instance (for testing)."""
    global _bridge
    _bridge = None

def create_tool_wrapper(bridge: MCPBridge, tool_config: Any) -> callable:
    """Auto-generate a CrewAI @tool wrapper from MCP tool definition.

    Args:
        bridge: MCPBridge instance for the domain
        tool_config: ToolConfig with name, description, mcp_tool, and state

    Returns:
        Callable tool function decorated with @tool
    """
    tool_name = tool_config.name
    mcp_tool = tool_config.mcp_tool
    description = tool_config.description

    # Get state configuration
    state = getattr(tool_config, "state", None)
    exports = state.exports if state else {}
    requires = state.requires if state else []

    def dynamic_tool(**kwargs) -> str:
        """Dynamically generated tool wrapper."""
        result = bridge.call(mcp_tool, kwargs)
        if isinstance(result, dict):
            # Handle exports
            if exports:
                result["_exports"] = {}
                for result_key, context_key in exports.items():
                    if result_key in result:
                        result["_exports"][context_key] = result[result_key]
            return str(result)
        return str(result)

    # Set function metadata
    dynamic_tool.__name__ = tool_name
    dynamic_tool.__doc__ = description

    # Apply decorators
    wrapped = tool(tool_name)(dynamic_tool)

    # Store state metadata for introspection
    if requires:
        wrapped._state_requires = requires
    if exports:
        wrapped._state_exports = exports

    return wrapped

def discover_mcp_tools(mcp_url: str) -> list[dict[str, Any]]:
    """Discover all tools from an MCP server.

    Args:
        mcp_url: URL of the MCP server

    Returns:
        List of tool definitions from the server
    """
    bridge = MCPBridge(mcp_url)
    return bridge.list_tools()
