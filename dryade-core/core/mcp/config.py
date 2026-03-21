"""MCP Server Configuration.

Pydantic models and loading utilities for MCP server configuration.
Provides type-safe configuration for MCP servers including command,
environment variables, transport settings, and lifecycle options.
"""

from __future__ import annotations

import json
import logging
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ============================================================================
# Transport Types
# ============================================================================

class MCPServerTransport(str, Enum):
    """Transport protocol for MCP server communication.

    STDIO is the standard transport using stdin/stdout with subprocesses.
    HTTP is for HTTP/SSE transport connecting to remote MCP servers.
    """

    STDIO = "stdio"
    HTTP = "http"

# ============================================================================
# Server Configuration
# ============================================================================

class MCPServerConfig(BaseModel):
    """Configuration for an MCP server.

    Defines all settings needed to start and manage an MCP server process,
    including the command to run, environment variables, timeouts, and
    lifecycle management options.

    Attributes:
        name: Unique server identifier (lowercase alphanumeric with hyphens).
        command: Command to start the server as a list of strings.
        transport: Transport type (default: STDIO).
        timeout: Request timeout in seconds (default: 30.0).
        startup_delay: Wait time after starting in seconds (default: 2.0).
        env: Environment variables to pass to the server process.
        auto_restart: Whether to restart the server on crash (default: True).
        max_restarts: Maximum restart attempts (default: 3).
        health_check_interval: Seconds between health checks (default: 30.0).
        enabled: Whether the server is enabled (default: True).

    Example:
        >>> config = MCPServerConfig(
        ...     name="memory",
        ...     command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        ...     env={"MEMORY_PATH": "/tmp/memory"},
        ... )
        >>> config.transport
        <MCPServerTransport.STDIO: 'stdio'>
    """

    name: str = Field(..., description="Unique server identifier")
    command: list[str] = Field(..., description="Command to start the server")
    transport: MCPServerTransport = Field(
        default=MCPServerTransport.STDIO,
        description="Transport type for server communication",
    )
    timeout: float = Field(
        default=60.0,
        gt=0,
        description="Request timeout in seconds",
    )
    startup_delay: float = Field(
        default=2.0,
        ge=0,
        description="Wait time after starting the server in seconds",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for the server process",
    )
    auto_restart: bool = Field(
        default=True,
        description="Whether to restart the server on crash",
    )
    max_restarts: int = Field(
        default=3,
        ge=0,
        description="Maximum number of restart attempts",
    )
    health_check_interval: float = Field(
        default=30.0,
        gt=0,
        description="Seconds between health checks",
    )
    enabled: bool = Field(
        default=True,
        description="Whether the server is enabled",
    )

    # HTTP transport fields
    url: str | None = Field(
        default=None,
        description="Server URL for HTTP/SSE transport",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Custom headers for HTTP transport",
    )
    auth_type: Literal["none", "api_key", "oauth", "bearer"] = Field(
        default="none",
        description="Authentication type for HTTP transport",
    )
    oauth_scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes if auth_type is oauth",
    )
    credential_service: str | None = Field(
        default=None,
        description="Keyring service name for credential lookup",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is non-empty, lowercase alphanumeric with hyphens."""
        if not v:
            raise ValueError("name must be non-empty")

        # Must be lowercase alphanumeric with hyphens
        pattern = r"^[a-z][a-z0-9-]*$"
        if not re.match(pattern, v):
            raise ValueError(
                "name must be lowercase, start with a letter, and contain only "
                "letters, numbers, and hyphens"
            )

        return v

    @model_validator(mode="after")
    def validate_transport_settings(self) -> MCPServerConfig:
        """Validate transport-specific settings.

        STDIO transport requires a non-empty command.
        HTTP transport requires a valid URL (http:// or https://).
        """
        if self.transport == MCPServerTransport.STDIO:
            if not self.command:
                raise ValueError("STDIO transport requires a non-empty command")
        elif self.transport == MCPServerTransport.HTTP:
            if not self.url:
                raise ValueError("HTTP transport requires a url to be specified")
            if not self.url.startswith(("http://", "https://")):
                raise ValueError(
                    f"HTTP transport url must start with http:// or https://, got: {self.url}"
                )
        return self

    def get_auth_headers(self, credentials: dict | None = None) -> dict[str, str]:
        """Get authentication headers for HTTP transport.

        Merges custom headers with authentication headers based on auth_type.

        Args:
            credentials: Dictionary containing authentication credentials.
                - For bearer auth: {"token": "..."}
                - For api_key auth: {"api_key": "..."}

        Returns:
            Dictionary of headers including authentication headers.

        Example:
            >>> config = MCPServerConfig(
            ...     name="test",
            ...     command=[],
            ...     transport=MCPServerTransport.HTTP,
            ...     url="https://api.example.com/mcp",
            ...     auth_type="bearer",
            ... )
            >>> config.get_auth_headers({"token": "secret123"})
            {'Authorization': 'Bearer secret123'}
        """
        result = dict(self.headers)
        if credentials is None:
            return result

        if self.auth_type == "bearer":
            token = credentials.get("token")
            if token:
                result["Authorization"] = f"Bearer {token}"
        elif self.auth_type == "api_key":
            api_key = credentials.get("api_key")
            if api_key:
                # Standard X-API-Key header
                result["X-API-Key"] = api_key
        elif self.auth_type == "oauth":
            # OAuth uses bearer tokens after authentication
            token = credentials.get("access_token") or credentials.get("token")
            if token:
                result["Authorization"] = f"Bearer {token}"

        return result

    def expand_env_vars(self) -> dict[str, str]:
        """Expand environment variable references in env dict values.

        Replaces ${VAR_NAME} patterns with values from os.environ.
        If a variable is not found in the environment, the literal
        ${VAR_NAME} is preserved.

        Returns:
            New dict with expanded environment variable values.

        Example:
            >>> import os
            >>> os.environ["MY_TOKEN"] = "secret123"
            >>> config = MCPServerConfig(
            ...     name="test",
            ...     command=["echo"],
            ...     env={"TOKEN": "${MY_TOKEN}", "LITERAL": "no-var"},
            ... )
            >>> expanded = config.expand_env_vars()
            >>> expanded["TOKEN"]
            'secret123'
            >>> expanded["LITERAL"]
            'no-var'
        """
        pattern = re.compile(r"\$\{([^}]+)\}")
        result = {}

        for key, value in self.env.items():

            def replace_var(match: re.Match[str]) -> str:
                var_name = match.group(1)
                env_value = os.environ.get(var_name)
                if env_value is not None:
                    return env_value
                # Keep literal if not found
                return match.group(0)

            result[key] = pattern.sub(replace_var, value)

        return result

    def get_full_env(self) -> dict[str, str]:
        """Get complete environment for the server process.

        Merges current environment with server-specific variables,
        expanding any ${VAR} references in the process.

        Returns:
            Complete environment dict for subprocess.
        """
        full_env = os.environ.copy()
        full_env.update(self.expand_env_vars())
        return full_env

# ============================================================================
# Configuration Loading Functions
# ============================================================================

def load_config(data: dict[str, Any]) -> MCPServerConfig:
    """Parse a dictionary into an MCPServerConfig.

    Args:
        data: Dictionary containing server configuration.

    Returns:
        Validated MCPServerConfig instance.

    Raises:
        pydantic.ValidationError: If the data is invalid.

    Example:
        >>> config = load_config({
        ...     "name": "test",
        ...     "command": ["echo", "hello"],
        ... })
        >>> config.name
        'test'
    """
    return MCPServerConfig.model_validate(data)

def load_config_from_file(path: Path | str) -> MCPServerConfig:
    """Load an MCP server configuration from a JSON file.

    Args:
        path: Path to the JSON configuration file.

    Returns:
        Validated MCPServerConfig instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        pydantic.ValidationError: If the configuration is invalid.

    Example:
        >>> # Assuming config.json contains valid config
        >>> config = load_config_from_file("config.json")
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path) as f:
        data = json.load(f)

    return load_config(data)

def load_configs_from_directory(
    directory: Path | str,
) -> dict[str, MCPServerConfig]:
    """Load all MCP server configurations from a directory.

    Loads all *.json files from the directory and optional 'servers/'
    subdirectory. Invalid files are logged and skipped.

    Args:
        directory: Path to directory containing configuration files.

    Returns:
        Dictionary mapping server names to their configurations.

    Example:
        >>> configs = load_configs_from_directory("/etc/mcp/")
        >>> for name, config in configs.items():
        ...     print(f"Loaded: {name}")
    """
    directory = Path(directory)
    configs: dict[str, MCPServerConfig] = {}

    # Collect all JSON files from directory and servers/ subdirectory
    json_files: list[Path] = []

    if directory.is_dir():
        json_files.extend(directory.glob("*.json"))

        servers_dir = directory / "servers"
        if servers_dir.is_dir():
            json_files.extend(servers_dir.glob("*.json"))

    for json_file in json_files:
        try:
            config = load_config_from_file(json_file)
            if config.name in configs:
                logger.warning(
                    "Duplicate server name '%s' in %s, skipping",
                    config.name,
                    json_file,
                )
                continue
            configs[config.name] = config
        except FileNotFoundError:
            logger.warning("Configuration file not found: %s", json_file)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in %s: %s", json_file, e)
        except Exception as e:
            logger.warning("Failed to load config from %s: %s", json_file, e)

    return configs

def get_default_servers() -> list[MCPServerConfig]:
    """Get pre-configured default MCP servers.

    Returns a list of commonly used MCP servers with sensible defaults.
    All servers are disabled by default (enabled=False) to require
    explicit opt-in.

    The default servers are:
    - memory: In-memory key-value store
    - filesystem: File system access with path restrictions
    - git: Git repository operations

    Returns:
        List of pre-configured MCPServerConfig instances.

    Example:
        >>> defaults = get_default_servers()
        >>> for server in defaults:
        ...     print(f"{server.name}: enabled={server.enabled}")
        memory: enabled=False
        filesystem: enabled=False
        git: enabled=False
    """
    return [
        MCPServerConfig(
            name="memory",
            command=["npx", "-y", "@modelcontextprotocol/server-memory"],
            enabled=False,
            env={},
        ),
        MCPServerConfig(
            name="filesystem",
            command=[
                "npx",
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "${MCP_ALLOWED_PATHS}",
            ],
            enabled=False,
            env={"MCP_ALLOWED_PATHS": "/tmp"},
        ),
        MCPServerConfig(
            name="git",
            command=["uvx", "mcp-server-git"],
            enabled=False,
            env={},
        ),
        # HTTP transport servers
        MCPServerConfig(
            name="context7",
            command=[],
            transport=MCPServerTransport.HTTP,
            url="https://mcp.context7.com/mcp",
            auth_type="api_key",
            credential_service="dryade-mcp-context7",
            timeout=30.0,
            enabled=False,
        ),
    ]
