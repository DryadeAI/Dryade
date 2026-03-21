"""MCP Setup Wizard Helpers.

Provides helpers for agent setup verification and user-facing setup instructions.
Used to check if required MCP servers and credentials are configured.

Usage:
    from core.mcp.setup_wizard import check_agent_setup, get_setup_instructions

    # Check if agent is ready to run
    status = check_agent_setup("devops_engineer", ["git", "filesystem"])
    if not status["ready"]:
        for missing in status["missing"]:
            print(f"Missing: {missing['server']} - {missing['reason']}")

    # Get setup instructions for a server
    instructions = get_setup_instructions("github")
    print(instructions["name"])
    print(instructions["env_vars"])
"""

from __future__ import annotations

from typing import Any

from core.mcp.credentials import get_credential_manager
from core.mcp.registry import get_registry

# Server setup instruction registry
_SERVER_SETUP_INSTRUCTIONS: dict[str, dict[str, Any]] = {
    "github": {
        "name": "GitHub",
        "description": "GitHub repository operations (repos, PRs, issues)",
        "package": "@modelcontextprotocol/server-github",
        "env_vars": ["GITHUB_TOKEN"],
        "setup_steps": [
            "Create a GitHub Personal Access Token at https://github.com/settings/tokens",
            "Select 'repo' scope for full repository access",
            "Set GITHUB_TOKEN environment variable or use credential manager",
        ],
        "verification_command": "gh auth status",
        "docs_url": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
    },
    "git": {
        "name": "Git",
        "description": "Local git repository operations",
        "package": "@anthropic/mcp-git",
        "env_vars": [],
        "setup_steps": [
            "Git CLI must be installed on the system",
            "No additional credentials required for local operations",
        ],
        "verification_command": "git --version",
        "docs_url": "https://git-scm.com/downloads",
    },
    "filesystem": {
        "name": "Filesystem",
        "description": "File system read/write operations",
        "package": "@modelcontextprotocol/server-filesystem",
        "env_vars": [],
        "setup_steps": [
            "No additional setup required",
            "Access is limited to configured paths",
        ],
        "verification_command": None,
        "docs_url": None,
    },
    "grafana": {
        "name": "Grafana",
        "description": "Grafana dashboards, alerts, and Prometheus queries",
        "package": "grafana-mcp",
        "env_vars": ["GRAFANA_URL", "GRAFANA_API_KEY"],
        "setup_steps": [
            "Create a Grafana API key in your Grafana instance",
            "Set GRAFANA_URL to your Grafana server URL",
            "Set GRAFANA_API_KEY environment variable",
        ],
        "verification_command": None,
        "docs_url": "https://grafana.com/docs/grafana/latest/administration/api-keys/",
    },
    "dbhub": {
        "name": "DBHub",
        "description": "Multi-database queries (PostgreSQL, MySQL, SQLite)",
        "package": "@bytebase/dbhub",
        "env_vars": ["DATABASE_URL"],
        "setup_steps": [
            "Set DATABASE_URL with your database connection string",
            "Format: postgresql://user:pass@host:port/dbname",
        ],
        "verification_command": None,
        "docs_url": "https://github.com/bytebase/dbhub",
    },
    "linear": {
        "name": "Linear",
        "description": "Linear issue tracking",
        "package": "@tacticlaunch/mcp-linear",
        "env_vars": ["LINEAR_API_KEY"],
        "setup_steps": [
            "Create a Linear API key in your workspace settings",
            "Set LINEAR_API_KEY environment variable",
        ],
        "verification_command": None,
        "docs_url": "https://linear.app/docs/api",
    },
    "memory": {
        "name": "Memory",
        "description": "Knowledge graph for persistent memory",
        "package": "@modelcontextprotocol/server-memory",
        "env_vars": [],
        "setup_steps": [
            "No additional setup required",
            "Memory persists in-memory by default",
            "Configure --persist-path for file-based persistence",
        ],
        "verification_command": None,
        "docs_url": None,
    },
    "playwright": {
        "name": "Playwright",
        "description": "Browser automation and web scraping",
        "package": "@playwright/mcp",
        "env_vars": [],
        "setup_steps": [
            "Run: npx playwright install",
            "This installs browser binaries for Chromium, Firefox, and WebKit",
        ],
        "verification_command": "npx playwright --version",
        "docs_url": "https://playwright.dev/docs/intro",
    },
    "pdf-reader": {
        "name": "PDF Reader",
        "description": "PDF document extraction",
        "package": "@shtse8/pdf-reader-mcp",
        "env_vars": [],
        "setup_steps": [
            "No additional setup required",
        ],
        "verification_command": None,
        "docs_url": "https://github.com/shtse8/pdf-reader-mcp",
    },
    "document-ops": {
        "name": "Excel/Document Operations",
        "description": "Excel file operations (read, write, create sheets)",
        "package": "@negokaz/excel-mcp-server",
        "env_vars": [],
        "setup_steps": [
            "No additional setup required",
        ],
        "verification_command": None,
        "docs_url": "https://github.com/negokaz/excel-mcp-server",
    },
    "context7": {
        "name": "Context7",
        "description": "Library documentation lookup",
        "package": "context7-mcp",
        "env_vars": ["CONTEXT7_API_KEY"],
        "setup_steps": [
            "Sign up at context7.com to get an API key",
            "Set CONTEXT7_API_KEY environment variable",
        ],
        "verification_command": None,
        "docs_url": "https://context7.com",
    },
}

def get_setup_instructions(server_name: str) -> dict[str, Any]:
    """Get setup instructions for an MCP server.

    Args:
        server_name: Name of the MCP server (e.g., "github", "git").

    Returns:
        Dictionary with setup instructions:
        - name: Display name
        - description: What the server does
        - package: NPM package name
        - env_vars: Required environment variables
        - setup_steps: List of setup instructions
        - verification_command: Command to verify setup (if applicable)
        - docs_url: Link to documentation

    Example:
        >>> instructions = get_setup_instructions("github")
        >>> print(instructions["name"])
        GitHub
    """
    if server_name in _SERVER_SETUP_INSTRUCTIONS:
        return _SERVER_SETUP_INSTRUCTIONS[server_name].copy()

    # Return generic instructions for unknown servers
    return {
        "name": server_name.title(),
        "description": f"{server_name} MCP server",
        "package": f"@unknown/{server_name}",
        "env_vars": [],
        "setup_steps": [
            "Check the server documentation for setup instructions",
        ],
        "verification_command": None,
        "docs_url": None,
    }

def check_agent_setup(
    agent_name: str,
    required_servers: list[str],
) -> dict[str, Any]:
    """Check if an agent has all required MCP servers configured.

    Verifies that:
    1. Each required server is registered in the MCP registry
    2. Required credentials are configured for servers that need them

    Args:
        agent_name: Name of the agent (for URL generation).
        required_servers: List of required MCP server names.

    Returns:
        Dictionary with:
        - ready: True if all servers are configured, False otherwise
        - missing: List of missing items with server name and reason
        - setup_url: URL to the agent setup page

    Example:
        >>> status = check_agent_setup("devops_engineer", ["git", "filesystem"])
        >>> if not status["ready"]:
        ...     for item in status["missing"]:
        ...         print(f"Missing: {item['server']} - {item['reason']}")
    """
    manager = get_credential_manager()
    registry = get_registry()

    missing: list[dict[str, str]] = []

    for server in required_servers:
        # Check if server is registered
        if not registry.is_registered(server):
            missing.append(
                {
                    "server": server,
                    "reason": "not_registered",
                    "message": f"Server '{server}' is not registered in the MCP registry",
                }
            )
            continue

        # Check if credentials are needed and configured
        try:
            config = registry.get_config(server)
            if config.credential_service:
                if manager.needs_setup(config.credential_service):
                    missing.append(
                        {
                            "server": server,
                            "reason": "needs_credentials",
                            "message": f"Credentials required for '{config.credential_service}'",
                        }
                    )
        except Exception:
            # Config retrieval failed, server may have issues
            pass

        # Also check env vars from setup instructions
        instructions = get_setup_instructions(server)
        for env_var in instructions.get("env_vars", []):
            import os

            if not os.getenv(env_var):
                # Only add if not already marked as needing credentials
                already_missing = any(
                    m["server"] == server and m["reason"] == "needs_credentials" for m in missing
                )
                if not already_missing:
                    missing.append(
                        {
                            "server": server,
                            "reason": "missing_env_var",
                            "message": f"Environment variable '{env_var}' not set",
                        }
                    )
                break  # Only report first missing env var per server

    if missing:
        return {
            "ready": False,
            "missing": missing,
            "setup_url": f"/settings/agents/{agent_name}/setup",
        }

    return {"ready": True, "missing": [], "setup_url": None}

def get_all_server_instructions() -> dict[str, dict[str, Any]]:
    """Get setup instructions for all known MCP servers.

    Returns:
        Dictionary mapping server name to setup instructions.

    Example:
        >>> all_instructions = get_all_server_instructions()
        >>> for name, info in all_instructions.items():
        ...     print(f"{name}: {info['description']}")
    """
    return {name: info.copy() for name, info in _SERVER_SETUP_INSTRUCTIONS.items()}
