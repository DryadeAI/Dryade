"""Domain Plugin System.

Provides dynamic loading and registration of domain plugins.
Each domain can define agents, tools, crews, and flows via YAML configuration.

Usage:
    from core.domains import load_domain, register_domain, get_domain

    # Load and register a domain
    domain = load_domain("path/to/my-domain")
    register_domain(domain)

    # Get registered domain
    my_domain = get_domain("my-domain")

Target: ~120 LOC
"""

import os
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from core.domains.base import AgentConfig, DomainConfig, ToolConfig

# Global domain registry
_domains: dict[str, DomainConfig] = {}
_domain_tools: dict[str, list[Callable]] = {}  # domain_name -> tool functions
_domains_lock = threading.Lock()

def _expand_env_vars(value: Any) -> Any:
    """Expand ${ENV_VAR} patterns in configuration values."""
    if isinstance(value, str):
        pattern = r"\$\{([^}]+)\}"

        def replace(match):
            env_var = match.group(1)
            return os.environ.get(env_var, match.group(0))

        return re.sub(pattern, replace, value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value

def load_domain(path: str) -> DomainConfig:
    """Load domain configuration from a directory.

    Args:
        path: Path to domain directory containing domain.yaml

    Returns:
        DomainConfig loaded from YAML

    Raises:
        FileNotFoundError: If domain.yaml not found
        ValueError: If YAML is invalid
    """
    domain_path = Path(path)
    yaml_path = domain_path / "domain.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(f"Domain config not found: {yaml_path}")

    with open(yaml_path) as f:
        raw_config = yaml.safe_load(f)

    # Expand environment variables
    expanded_config = _expand_env_vars(raw_config)

    return DomainConfig(**expanded_config)

def register_domain(config: DomainConfig) -> None:
    """Register a domain and its components.

    This registers:
    - Domain config in global registry
    - All agents in adapter registry
    - All tools as CrewAI tool functions

    Args:
        config: Domain configuration to register
    """
    from core.extensions import MCPBridge, create_tool_wrapper

    # Create MCP bridge if server specified (no lock needed -- local work)
    bridge = None
    if config.mcp_server:
        bridge = MCPBridge(config.mcp_server)

    # Create tool wrappers (no lock needed -- local work)
    tool_map: dict[str, Callable] = {}
    tool_list: list[Callable] = []
    for tool_config in config.tools:
        if bridge:
            tool_func = create_tool_wrapper(bridge, tool_config)
            tool_map[tool_config.name] = tool_func
            tool_list.append(tool_func)

    # Write to shared dicts under lock
    with _domains_lock:
        _domains[config.name] = config
        _domain_tools[config.name] = tool_list

    # Register agents via adapters OUTSIDE lock (they have their own locking)
    for agent_config in config.agents:
        agent_tools = [tool_map[t] for t in agent_config.tools if t in tool_map]
        _register_agent_from_config(config.name, agent_config, agent_tools)

def _register_agent_from_config(
    domain_name: str, agent_config: AgentConfig, tools: list[Callable]
) -> None:
    """Register a CrewAI agent from configuration using lazy creation.

    The actual CrewAI Agent is created on first use, not at registration time.
    This allows registration at startup without requiring LLM env vars,
    and ensures user's LLM config is used when the agent executes.
    """
    from core.adapters import CrewAIAgentAdapter, register_agent

    # Store config for lazy agent creation
    config_dict = {
        "role": agent_config.role,
        "goal": agent_config.goal,
        "backstory": agent_config.backstory or f"Expert in {domain_name} domain",
        "verbose": True,
        "allow_delegation": agent_config.delegation,
    }

    # Create adapter with config (agent created lazily on first use)
    adapter = CrewAIAgentAdapter(
        name=f"{domain_name}.{agent_config.name}",
        agent_config=config_dict,
        tools=tools,
    )
    register_agent(adapter)

def get_domain(name: str) -> DomainConfig | None:
    """Get a registered domain by name."""
    with _domains_lock:
        return _domains.get(name)

def list_domains() -> list[str]:
    """List all registered domain names."""
    with _domains_lock:
        return list(_domains.keys())

def get_domain_tools(name: str) -> list[Callable]:
    """Get all tool functions for a domain."""
    with _domains_lock:
        return list(_domain_tools.get(name, []))

def unregister_domain(name: str) -> bool:
    """Unregister a domain and its components.

    Returns:
        True if domain was registered and removed
    """
    from core.adapters import unregister_agent

    # Atomic check-read-delete under lock
    with _domains_lock:
        if name not in _domains:
            return False
        config = _domains[name]
        del _domains[name]
        _domain_tools.pop(name, None)

    # Agent unregistration OUTSIDE lock (agents have their own locking)
    for agent_config in config.agents:
        unregister_agent(f"{name}.{agent_config.name}")

    return True

def get_enabled_domains(config_string: str) -> list[str]:
    """Parse enabled domains from comma-separated config string.

    Args:
        config_string: Comma-separated domain names, e.g., "github,custom"

    Returns:
        List of domain names (stripped, non-empty)
    """
    if not config_string:
        return []
    return [d.strip() for d in config_string.split(",") if d.strip()]

# Re-export base models
from core.domains.base import (  # noqa: E402
    AgentConfig,
    CrewConfig,
    DomainConfig,
    FlowConfig,
    StateMapping,
)

__all__ = [
    # Loader functions
    "load_domain",
    "register_domain",
    "unregister_domain",
    "get_domain",
    "list_domains",
    "get_domain_tools",
    "get_enabled_domains",
    # Base models
    "DomainConfig",
    "AgentConfig",
    "ToolConfig",
    "CrewConfig",
    "FlowConfig",
    "StateMapping",
]
