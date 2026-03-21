"""MCP-to-Plugin Security Bridge.

Provides MCPPluginProtocol -- a PluginProtocol subclass that wraps an MCP server.
This ensures MCP-based plugins go through the same security gates as regular
Python plugins: allowlist verification, hash checking, and tier enforcement.

Without this bridge, MCP servers defined in mcp_servers.yaml bypass the entire
plugin security model. MCPPluginProtocol closes that gap for new MCP-based plugins
(e.g., Capella suite extraction in Phase 182 Plan 11).

Usage in a plugin's dryade.json manifest:
    {
        "name": "capella_mcp",
        "version": "1.0.0",
        "required_tier": "team",
        "mcp_server": {
            "name": "capella",
            "command": ["python", "-m", "capella_server"],
            "args": [],
            "env": {}
        }
    }

Note: MCP imports (adapter, registry, config) are deferred to method bodies
to avoid pulling in sentence_transformers at module-import time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.ee.plugins_ee import PluginProtocol

logger = logging.getLogger(__name__)

def get_mcp_registry() -> Any:
    """Lazy import of MCP registry to avoid heavy import chain at module level."""
    from core.mcp.registry import get_registry

    return get_registry()

def get_agent_registry() -> Any:
    """Lazy import of agent registry to avoid heavy import chain at module level."""
    from core.adapters.registry import get_registry

    return get_registry()

def register_agent(adapter: Any) -> None:
    """Lazy import of register_agent."""
    from core.adapters.registry import register_agent as _register_agent

    _register_agent(adapter)

@dataclass
class MCPPluginProtocol(PluginProtocol):
    """Bridge: a plugin that wraps an MCP server.

    The plugin goes through normal allowlist/hash verification via PluginManager.
    On register(), it triggers MCP server registration via autoload APIs.
    On unregister(), it removes the MCP server from AgentRegistry.

    This closes the security gap where MCP servers in mcp_servers.yaml
    bypass the entire plugin security model.

    Attributes:
        mcp_server_name: Name for the MCP server in registries.
        mcp_command: Command to start the MCP server (e.g., ["python", "-m", "server"]).
        mcp_args: Additional command-line arguments.
        mcp_env: Environment variables for the MCP server process.
    """

    # PluginProtocol required fields
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    core_version_constraint: str = ">=1.0.0"

    # MCP server configuration
    mcp_server_name: str = ""
    mcp_command: list[str] = field(default_factory=list)
    mcp_args: list[str] = field(default_factory=list)
    mcp_env: dict[str, str] = field(default_factory=dict)

    def register(self, registry: Any) -> None:
        """Register MCP server as an agent after allowlist verification.

        This method is only called by PluginManager AFTER validate_before_load()
        has confirmed this plugin is in the signed allowlist. The security gate
        is in PluginManager, not here.

        Args:
            registry: The ExtensionRegistry for plugin extensions.
        """
        if not self.mcp_server_name:
            logger.error(f"MCPPluginProtocol '{self.name}' has no mcp_server_name, skipping")
            return

        from core.mcp.adapter import MCPAgentAdapter
        from core.mcp.config import MCPServerConfig, MCPServerTransport

        # Build full command from command + args
        full_command = list(self.mcp_command) + list(self.mcp_args)

        # Create MCP server config
        server_config = MCPServerConfig(
            name=self.mcp_server_name,
            command=full_command,
            transport=MCPServerTransport.STDIO,
            env=dict(self.mcp_env),
            enabled=True,
        )

        # Register with MCP registry
        mcp_registry = get_mcp_registry()
        if not mcp_registry.is_registered(server_config.name):
            mcp_registry.register(server_config)
            logger.info(f"MCPPluginProtocol: registered MCP server config '{server_config.name}'")

        # Create and register agent adapter
        agent_registry = get_agent_registry()
        agent_name = f"mcp-{server_config.name}"
        if agent_name not in agent_registry:
            adapter = MCPAgentAdapter(
                server_name=server_config.name,
                registry=mcp_registry,
                description=self.description,
            )
            register_agent(adapter)
            logger.info(f"MCPPluginProtocol: registered MCP agent '{agent_name}'")
        else:
            logger.debug(f"MCPPluginProtocol: agent '{agent_name}' already registered")

    def unregister(self) -> None:
        """Remove MCP server from AgentRegistry.

        Called during plugin shutdown or when plugin is removed from allowlist.
        """
        agent_name = f"mcp-{self.mcp_server_name}"
        agent_registry = get_agent_registry()
        try:
            agent_registry.unregister(agent_name)
            logger.info(f"MCPPluginProtocol: unregistered MCP agent '{agent_name}'")
        except Exception as e:
            logger.warning(f"MCPPluginProtocol: failed to unregister '{agent_name}': {e}")

    def shutdown(self) -> None:
        """Shutdown hook -- unregister MCP server on plugin shutdown."""
        self.unregister()
