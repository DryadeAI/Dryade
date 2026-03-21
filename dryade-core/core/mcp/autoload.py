"""MCP Agent Auto-Registration.

Provides automatic registration of MCP servers as agents in the AgentRegistry.
Reads configuration from config/mcp_servers.yaml and creates MCPAgentAdapter
instances for enabled servers.

The registration hook is called during API startup to wire MCP servers into
the agent discovery system, making them appear in /api/agents alongside
native agents.

Key design decisions:
- Config-driven: Users enable servers via YAML, not code changes
- Lazy start preserved: MCPRegistry lazy-starts servers on first tool call
- Idempotent: Safe to call multiple times (won't double-register)

Usage:
    from core.mcp.autoload import register_mcp_agents

    # During API startup
    count = register_mcp_agents()
    logger.info(f"Registered {count} MCP agents")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from core.adapters.registry import get_registry as get_agent_registry
from core.adapters.registry import register_agent
from core.mcp.adapter import SERVER_DESCRIPTIONS, MCPAgentAdapter
from core.mcp.config import MCPServerConfig, MCPServerTransport
from core.mcp.registry import get_registry as get_mcp_registry

logger = logging.getLogger(__name__)

def _default_config_path() -> Path:
    """Resolve MCP config path from Settings (supports env var override)."""
    from core.config import get_settings

    return Path(get_settings().mcp_config_path)

def load_mcp_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load MCP server configuration from YAML file.

    Args:
        config_path: Path to config file. Uses DEFAULT_CONFIG_PATH if not provided.

    Returns:
        Parsed configuration dictionary with 'servers' key.
        Returns empty dict if file doesn't exist.

    Example:
        >>> config = load_mcp_config()
        >>> config.get("servers", {}).keys()
        dict_keys(['filesystem', 'git', 'memory', ...])
    """
    path = Path(config_path) if config_path else _default_config_path()
    logger.debug(f"MCP config path: {path.absolute()}")

    if not path.exists():
        logger.warning(f"MCP config not found at {path.absolute()}, no servers will be registered")
        return {}

    try:
        with open(path) as f:
            config = yaml.safe_load(f) or {}
        server_count = len(config.get("servers", {}))
        logger.info(f"MCP config loaded from {path.absolute()}: {server_count} servers defined")
        return config
    except Exception as e:
        logger.error(f"Failed to load MCP config from {path}: {e}")
        return {}

def get_enabled_mcp_servers(config: dict[str, Any] | None = None) -> list[str]:
    """Get list of enabled MCP server names from config.

    Args:
        config: Pre-loaded config dict, or None to load from default path.

    Returns:
        List of server names that have enabled: true.

    Example:
        >>> servers = get_enabled_mcp_servers()
        >>> "memory" in servers  # If memory is enabled in config
        True
    """
    if config is None:
        config = load_mcp_config()

    servers = config.get("servers", {})
    enabled = [name for name, cfg in servers.items() if cfg.get("enabled", False)]
    return enabled

def _config_to_mcp_server_config(name: str, cfg: dict[str, Any]) -> MCPServerConfig:
    """Convert YAML config dict to MCPServerConfig.

    Args:
        name: Server name (used as config name).
        cfg: Configuration dictionary from YAML.

    Returns:
        Validated MCPServerConfig instance.
    """
    # Keep hyphens for registry consistency with SERVER_DESCRIPTIONS
    registry_name = name.lower()

    # Determine transport
    transport_str = cfg.get("transport", "stdio").lower()
    transport = MCPServerTransport.HTTP if transport_str == "http" else MCPServerTransport.STDIO

    return MCPServerConfig(
        name=registry_name,
        command=cfg.get("command", []),
        transport=transport,
        url=cfg.get("url"),
        auth_type=cfg.get("auth_type", "none"),
        credential_service=cfg.get("credential_service"),
        headers=cfg.get("headers", {}),
        env=cfg.get("env", {}),
        timeout=cfg.get("timeout", 30.0),
        startup_delay=cfg.get("startup_delay", 2.0),
        auto_restart=cfg.get("auto_restart", True),
        max_restarts=cfg.get("max_restarts", 3),
        enabled=cfg.get("enabled", False),
    )

def register_mcp_agents(config_path: Path | str | None = None) -> int:
    """Register enabled MCP servers as agents in the AgentRegistry.

    Reads config from YAML, creates MCPAgentAdapter for each enabled server,
    and registers them in the global AgentRegistry. Also registers server
    configs in MCPRegistry for lifecycle management.

    This function is idempotent - calling it multiple times won't create
    duplicate registrations.

    Args:
        config_path: Optional path to config file.

    Returns:
        Number of MCP agents registered.

    Example:
        >>> count = register_mcp_agents()
        >>> print(f"Registered {count} MCP agents")
        Registered 3 MCP agents
    """
    config = load_mcp_config(config_path)
    servers = config.get("servers", {})

    if not servers:
        logger.info("No MCP servers configured in config file")
        return 0

    # Count enabled servers for better logging
    enabled_servers = [name for name, cfg in servers.items() if cfg.get("enabled", False)]
    logger.info(
        f"MCP autoload: found {len(servers)} servers, {len(enabled_servers)} enabled: {enabled_servers}"
    )

    mcp_registry = get_mcp_registry()
    agent_registry = get_agent_registry()
    registered_count = 0

    for name, cfg in servers.items():
        if not cfg.get("enabled", False):
            logger.debug(f"MCP server '{name}' is disabled, skipping")
            continue

        try:
            # Create server config
            server_config = _config_to_mcp_server_config(name, cfg)

            # Register with MCP registry (if not already)
            if not mcp_registry.is_registered(server_config.name):
                mcp_registry.register(server_config)
                logger.debug(f"Registered MCP server config: {server_config.name}")

            # Get description from config or SERVER_DESCRIPTIONS fallback
            description = cfg.get("description") or SERVER_DESCRIPTIONS.get(
                server_config.name, f"MCP server: {server_config.name}"
            )

            # Create agent adapter
            adapter = MCPAgentAdapter(
                server_name=server_config.name,
                registry=mcp_registry,
                description=description,
            )

            # Check if already registered in agent registry
            agent_name = f"mcp-{server_config.name}"
            if agent_name in agent_registry:
                logger.debug(f"MCP agent '{agent_name}' already registered, skipping")
                continue

            # Register as agent
            register_agent(adapter)
            registered_count += 1
            logger.info(f"Registered MCP agent: {agent_name}")

        except Exception as e:
            logger.error(f"Failed to register MCP server '{name}' as agent: {e}")
            continue

    return registered_count

def unregister_mcp_agents() -> int:
    """Unregister all MCP agents from the AgentRegistry.

    Used during shutdown or testing to clean up registrations.
    Does NOT stop running MCP servers (that's handled by MCPRegistry.shutdown()).

    Returns:
        Number of agents unregistered.
    """
    from core.adapters.protocol import AgentFramework

    agent_registry = get_agent_registry()
    mcp_agents = agent_registry.find_by_framework(AgentFramework.MCP)

    count = 0
    for agent in mcp_agents:
        card = agent.get_card()
        agent_registry.unregister(card.name)
        count += 1
        logger.debug(f"Unregistered MCP agent: {card.name}")

    return count

def __getattr__(name: str) -> object:
    """Lazy module attribute provider.

    Provides ``DEFAULT_CONFIG_PATH`` on first access so callers can do::

        import core.mcp.autoload as autoload
        path = autoload.DEFAULT_CONFIG_PATH

    or patch it in tests::

        with patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path):
            ...
    """
    if name == "DEFAULT_CONFIG_PATH":
        try:
            return _default_config_path()
        except Exception:
            # Fallback to a safe default path when settings are unavailable
            # (e.g., during import in test environments without DRYADE_JWT_SECRET).
            from pathlib import Path as _Path

            return _Path("config/mcp_servers.yaml")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
