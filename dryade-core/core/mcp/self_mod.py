"""MCP Server Self-Modification -- Runtime Lifecycle Operations.

Provides coordinated add/remove/configure operations for MCP servers,
atomically updating all three stores (MCPRegistry, ToolIndex, ToolEmbeddingStore)
and the AgentRegistry.  Persists changes to the YAML config file so they
survive restarts.

These functions are called by EscalationExecutor when users approve
ADD_MCP_SERVER / REMOVE_MCP_SERVER / CONFIGURE_MCP_SERVER actions.

Phase 115.2 -- first framework with MCP-native self-modification.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Module-level lock for config file I/O (Pitfall 2: concurrent YAML writes)
_config_lock = threading.Lock()

# Valid server name pattern: lowercase, starts with letter, alphanumeric + hyphens
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# ---------------------------------------------------------------------------
# Config file helpers (private)
# ---------------------------------------------------------------------------

def _get_config_path() -> Path:
    """Get the default MCP config path (lazy import to avoid circular deps)."""
    import core.mcp.autoload as _autoload

    return _autoload.DEFAULT_CONFIG_PATH

def _read_config_file(config_path: Path | None = None) -> dict[str, Any]:
    """Read mcp_servers.yaml and return parsed dict."""
    path = config_path or _get_config_path()
    if not path.exists():
        return {"servers": {}}
    with open(path) as f:
        return yaml.safe_load(f) or {"servers": {}}

def _write_config_file(data: dict[str, Any], config_path: Path | None = None) -> None:
    """Write dict back to mcp_servers.yaml."""
    path = config_path or _get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

def _persist_server_config(
    name: str,
    config: Any,
    description: str | None = None,
    config_path: Path | None = None,
) -> None:
    """Add or update a server entry in the YAML config file.

    Thread-safe via ``_config_lock``.
    """
    with _config_lock:
        data = _read_config_file(config_path)
        servers = data.setdefault("servers", {})

        entry: dict[str, Any] = {
            "command": list(config.command) if config.command else [],
            "transport": config.transport.value,
            "enabled": config.enabled,
            "env": dict(config.env) if config.env else {},
            "timeout": config.timeout,
        }
        if config.url:
            entry["url"] = config.url
        if description:
            entry["description"] = description

        servers[name] = entry
        _write_config_file(data, config_path)
        logger.info("[SELF-MOD] Persisted server config for '%s'", name)

def _remove_from_config_file(name: str, config_path: Path | None = None) -> None:
    """Remove a server entry from the YAML config file.

    Thread-safe via ``_config_lock``.
    """
    with _config_lock:
        data = _read_config_file(config_path)
        servers = data.get("servers", {})
        if name in servers:
            del servers[name]
            _write_config_file(data, config_path)
            logger.info("[SELF-MOD] Removed server '%s' from config file", name)

# ---------------------------------------------------------------------------
# Public lifecycle operations
# ---------------------------------------------------------------------------

async def add_mcp_server(
    name: str,
    command: list[str],
    transport: str = "stdio",
    env: dict[str, str] | None = None,
    url: str | None = None,
    description: str | None = None,
) -> tuple[bool, str]:
    """Add a new MCP server at runtime.

    Coordinates MCPRegistry, ToolIndex, ToolEmbeddingStore, AgentRegistry,
    and YAML config file in a single operation.

    Args:
        name: Server name (lowercase, alphanumeric + hyphens).
        command: Command to start the server process.
        transport: Transport type ("stdio" or "http").
        env: Optional environment variables.
        url: URL for HTTP transport.
        description: Human-readable description.

    Returns:
        (success, message) tuple.
    """
    # -- Lazy imports (avoid circular deps) --------------------------------
    from core.adapters.registry import register_agent
    from core.mcp.adapter import MCPAgentAdapter
    from core.mcp.config import MCPServerConfig, MCPServerTransport
    from core.mcp.embeddings import get_tool_embedding_store
    from core.mcp.registry import get_registry
    from core.mcp.tool_index import ToolEntry, get_tool_index

    # -- Validate ----------------------------------------------------------
    if not _NAME_PATTERN.match(name):
        return False, (
            f"Invalid server name '{name}': must be lowercase, start with a "
            "letter, and contain only letters, numbers, and hyphens."
        )

    registry = get_registry()
    if registry.is_registered(name):
        return False, f"Server '{name}' is already registered."

    # -- Build config ------------------------------------------------------
    transport_enum = (
        MCPServerTransport.HTTP if transport.lower() == "http" else MCPServerTransport.STDIO
    )
    config = MCPServerConfig(
        name=name,
        command=command,
        transport=transport_enum,
        env=env or {},
        url=url,
        enabled=True,
    )

    try:
        # -- Register + start ---------------------------------------------
        registry.register(config)
        registry.start(name)

        # -- Discover tools ------------------------------------------------
        tools = registry.list_tools(name)
        tool_index = get_tool_index()
        embedding_store = get_tool_embedding_store()

        for mcp_tool in tools:
            entry = ToolEntry.from_mcp_tool(mcp_tool, name)
            tool_index.add_entry(entry)
            try:
                embedding_store.index_tool(entry)
            except Exception as e:
                logger.warning(
                    "[SELF-MOD] Embedding indexing failed for tool '%s': %s",
                    entry.name,
                    e,
                )

        # -- Index server description in embeddings ------------------------
        desc = description or f"MCP server {name} providing {len(tools)} tools"
        try:
            embedding_store.index_server(name, desc)
        except Exception as e:
            logger.warning("[SELF-MOD] Server embedding indexing failed: %s", e)

        # -- Persist to config file ----------------------------------------
        _persist_server_config(name, config, description)

        # -- Register as agent ---------------------------------------------
        adapter = MCPAgentAdapter(
            server_name=name,
            registry=registry,
            description=desc,
        )
        register_agent(adapter)

        msg = f"Added MCP server '{name}' with {len(tools)} tools"
        logger.info("[SELF-MOD] %s", msg)
        return True, msg

    except Exception as e:
        # Rollback: try to unregister if partially registered
        try:
            if registry.is_registered(name):
                registry.unregister(name)
        except Exception:
            pass
        logger.exception("[SELF-MOD] Failed to add MCP server '%s'", name)
        return False, f"Failed to add MCP server '{name}': {e}"

async def remove_mcp_server(name: str) -> tuple[bool, str]:
    """Remove an MCP server at runtime.

    Cleans up MCPRegistry, ToolIndex, ToolEmbeddingStore, AgentRegistry,
    and YAML config file.

    Args:
        name: Server name to remove.

    Returns:
        (success, message) tuple.
    """
    from core.adapters.registry import unregister_agent
    from core.mcp.embeddings import get_tool_embedding_store
    from core.mcp.registry import get_registry
    from core.mcp.tool_index import get_tool_index

    registry = get_registry()

    if not registry.is_registered(name):
        return False, f"Server '{name}' is not registered."

    try:
        tool_index = get_tool_index()
        embedding_store = get_tool_embedding_store()

        # -- Get tools BEFORE removal (for cleanup) ------------------------
        entries = tool_index.get_by_server(name)

        # -- Clean embeddings per-tool -------------------------------------
        for entry in entries:
            try:
                embedding_store.delete_tool(entry.fingerprint)
            except Exception as e:
                logger.warning(
                    "[SELF-MOD] Failed to delete embedding for tool '%s': %s",
                    entry.name,
                    e,
                )

        # -- Batch remove from tool index ----------------------------------
        removed_count = tool_index.remove_by_server(name)

        # -- Delete server embedding ---------------------------------------
        try:
            embedding_store.delete_server(name)
        except Exception as e:
            logger.warning("[SELF-MOD] Failed to delete server embedding: %s", e)

        # -- Unregister from MCPRegistry (stops + removes config) ----------
        registry.unregister(name)

        # -- Unregister agent ----------------------------------------------
        unregister_agent(f"mcp-{name}")

        # -- Remove from config file ---------------------------------------
        _remove_from_config_file(name)

        msg = f"Removed MCP server '{name}' and {removed_count} tools"
        logger.info("[SELF-MOD] %s", msg)
        return True, msg

    except Exception as e:
        logger.exception("[SELF-MOD] Failed to remove MCP server '%s'", name)
        return False, f"Failed to remove MCP server '{name}': {e}"

async def configure_mcp_server(
    name: str,
    updates: dict[str, Any],
) -> tuple[bool, str]:
    """Modify an MCP server's configuration at runtime.

    Stops the server, applies updates, restarts, and re-indexes tools.

    Supported update keys:
        - env (dict): Environment variables to merge.
        - command (list): New command (replaces existing).
        - enabled (bool): Enable/disable.
        - timeout (float): Request timeout.
        - description (str): Human-readable description.

    Args:
        name: Server name to configure.
        updates: Dict of configuration updates.

    Returns:
        (success, message) tuple.
    """
    from core.adapters.registry import register_agent, unregister_agent
    from core.mcp.adapter import MCPAgentAdapter
    from core.mcp.autoload import _config_to_mcp_server_config
    from core.mcp.embeddings import get_tool_embedding_store
    from core.mcp.registry import get_registry
    from core.mcp.tool_index import ToolEntry, get_tool_index

    registry = get_registry()

    if not registry.is_registered(name):
        return False, f"Server '{name}' is not registered."

    try:
        tool_index = get_tool_index()
        embedding_store = get_tool_embedding_store()

        # -- Stop if running -----------------------------------------------
        if registry.is_running(name):
            registry.stop(name)

        # -- Clean up old tools --------------------------------------------
        old_entries = tool_index.get_by_server(name)
        for entry in old_entries:
            try:
                embedding_store.delete_tool(entry.fingerprint)
            except Exception as e:
                logger.warning("[SELF-MOD] Embedding delete failed for '%s': %s", entry.name, e)
        tool_index.remove_by_server(name)
        try:
            embedding_store.delete_server(name)
        except Exception as e:
            logger.warning("[SELF-MOD] Server embedding delete failed: %s", e)

        # -- Read current config from YAML ---------------------------------
        config_data = _read_config_file()
        servers = config_data.get("servers", {})
        current_cfg = servers.get(name, {})

        # -- Merge updates -------------------------------------------------
        if "env" in updates and isinstance(updates["env"], dict):
            existing_env = current_cfg.get("env", {})
            existing_env.update(updates["env"])
            current_cfg["env"] = existing_env
        if "command" in updates:
            current_cfg["command"] = updates["command"]
        if "enabled" in updates:
            current_cfg["enabled"] = updates["enabled"]
        if "timeout" in updates:
            current_cfg["timeout"] = updates["timeout"]
        if "description" in updates:
            current_cfg["description"] = updates["description"]

        # -- Unregister old config + register new --------------------------
        registry.unregister(name)
        new_config = _config_to_mcp_server_config(name, current_cfg)
        registry.register(new_config)
        registry.start(name)

        # -- Re-discover tools and re-index --------------------------------
        tools = registry.list_tools(name)
        for mcp_tool in tools:
            entry = ToolEntry.from_mcp_tool(mcp_tool, name)
            tool_index.add_entry(entry)
            try:
                embedding_store.index_tool(entry)
            except Exception as e:
                logger.warning("[SELF-MOD] Embedding indexing failed for '%s': %s", entry.name, e)

        desc = updates.get("description") or current_cfg.get(
            "description", f"MCP server {name} providing {len(tools)} tools"
        )
        try:
            embedding_store.index_server(name, desc)
        except Exception as e:
            logger.warning("[SELF-MOD] Server embedding indexing failed: %s", e)

        # -- Update config file --------------------------------------------
        _persist_server_config(name, new_config, desc)

        # -- Re-register agent if description changed ----------------------
        agent_name = f"mcp-{name}"
        unregister_agent(agent_name)
        adapter = MCPAgentAdapter(
            server_name=name,
            registry=registry,
            description=desc,
        )
        register_agent(adapter)

        msg = f"Updated MCP server '{name}' configuration"
        logger.info("[SELF-MOD] %s", msg)
        return True, msg

    except Exception as e:
        logger.exception("[SELF-MOD] Failed to configure MCP server '%s'", name)
        return False, f"Failed to configure MCP server '{name}': {e}"
