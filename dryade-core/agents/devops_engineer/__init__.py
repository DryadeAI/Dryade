"""DevOps Engineer Agent - MCP-native Implementation.

Demonstrates the MCP-native pattern where agent orchestration is done directly
without framework overhead. Uses MCPToolWrapper for traced MCP calls.

This agent specializes in DevOps tasks:
- Git operations (status, diff, log, etc.)
- File system operations (read, list)
- GitHub operations (when configured)

Usage:
    from agents.devops_engineer import DevOpsEngineerAgent, create_devops_engineer_agent

    # Factory function (recommended)
    agent = create_devops_engineer_agent()
    result = await agent.execute("Check git status")

    # Direct instantiation
    agent = DevOpsEngineerAgent()
    card = agent.get_card()
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.mcp.tool_wrapper import MCPToolWrapper

logger = logging.getLogger(__name__)

# Load agent configuration
def _load_config() -> dict[str, Any]:
    """Load agent configuration from YAML file."""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}

class DevOpsEngineerAgent(UniversalAgent):
    """MCP-native DevOps Engineer agent.

    Demonstrates framework-free agent implementation using direct MCP tool calls.
    All MCP calls are traced via MCPToolWrapper for observability.

    Attributes:
        name: Agent name for identification.
        version: Agent version string.
        description: Human-readable description.

    Example:
        >>> agent = DevOpsEngineerAgent()
        >>> card = agent.get_card()
        >>> print(card.framework)
        AgentFramework.MCP
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the DevOps Engineer agent.

        Args:
            config: Optional configuration override. Loaded from config.yaml if not provided.
        """
        self._config = config or _load_config()

        # Agent metadata
        self.name = self._config.get("name", "devops_engineer")
        self.version = self._config.get("version", "1.0.0")
        self.description = self._config.get(
            "description",
            "DevOps automation via git, filesystem, and GitHub MCP tools",
        )

        # Initialize MCP tool wrappers
        self._tools = self._create_tools()

    def _create_tools(self) -> dict[str, MCPToolWrapper]:
        """Create MCP tool wrappers for available operations."""
        return {
            # Git tools
            "git_status": MCPToolWrapper("git", "git_status", "Get working tree status"),
            "git_diff": MCPToolWrapper("git", "git_diff", "Show changes between commits"),
            "git_log": MCPToolWrapper("git", "git_log", "Show commit history"),
            "git_show": MCPToolWrapper("git", "git_show", "Show commit details"),
            # Filesystem tools
            "read_file": MCPToolWrapper("filesystem", "read_file", "Read file contents"),
            "list_directory": MCPToolWrapper(
                "filesystem", "list_directory", "List directory contents"
            ),
            # GitHub tools (optional - requires authentication)
            "github_get_repo": MCPToolWrapper("github", "get_repo", "Get repository information"),
            "github_list_prs": MCPToolWrapper("github", "list_pull_requests", "List pull requests"),
            "github_list_issues": MCPToolWrapper("github", "list_issues", "List repository issues"),
        }

    def get_card(self) -> AgentCard:
        """Return agent's capability card.

        Returns:
            AgentCard with framework=MCP and DevOps capabilities.
        """
        capabilities = [
            AgentCapability(
                name="git_operations",
                description="Git repository operations (status, diff, log)",
                input_schema={"task": "string"},
                output_schema={"result": "string"},
            ),
            AgentCapability(
                name="file_operations",
                description="File system read operations",
                input_schema={"path": "string"},
                output_schema={"content": "string"},
            ),
            AgentCapability(
                name="github_operations",
                description="GitHub repository operations (requires auth)",
                input_schema={"owner": "string", "repo": "string"},
                output_schema={"data": "object"},
            ),
        ]

        return AgentCard(
            name=self.name,
            description=self.description,
            version=self.version,
            framework=AgentFramework.MCP,
            capabilities=capabilities,
            metadata={
                "required_servers": ["git", "filesystem"],
                "optional_servers": ["github"],
            },
        )

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute a DevOps task by routing to appropriate MCP tools.

        Routes natural language tasks to MCP tool calls based on keyword matching.
        Supports git operations, file operations, and GitHub operations.

        Args:
            task: Natural language task description.
            context: Optional execution context with additional parameters.

        Returns:
            AgentResult with status and result.

        Example:
            >>> result = await agent.execute("Check git status")
            >>> print(result.result)
        """
        context = context or {}
        task_lower = task.lower()

        try:
            # Route based on task keywords
            result = await self._route_task(task_lower, task, context)
            return AgentResult(
                result=result,
                status="ok",
                metadata={"task": task, "agent": self.name},
            )

        except Exception as e:
            logger.error(f"DevOps agent error: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=str(e),
                metadata={"task": task, "agent": self.name},
            )

    async def _route_task(
        self,
        task_lower: str,
        original_task: str,
        context: dict[str, Any],
    ) -> str:
        """Route task to appropriate MCP tool(s).

        Args:
            task_lower: Lowercase task string for matching.
            original_task: Original task string.
            context: Execution context.

        Returns:
            Result string from MCP tool(s).

        Raises:
            ValueError: If task cannot be routed to any tool.
        """
        # Git status
        if "status" in task_lower and ("git" in task_lower or "repo" in task_lower):
            repo_path = context.get("repo_path", ".")
            return self._tools["git_status"].call(repo_path=repo_path)

        # Git diff
        if "diff" in task_lower:
            repo_path = context.get("repo_path", ".")
            target = context.get("target")
            kwargs = {"repo_path": repo_path}
            if target:
                kwargs["target"] = target
            return self._tools["git_diff"].call(**kwargs)

        # Git log
        if "log" in task_lower or "history" in task_lower or "commits" in task_lower:
            repo_path = context.get("repo_path", ".")
            max_count = context.get("max_count", 10)
            return self._tools["git_log"].call(repo_path=repo_path, max_count=max_count)

        # Git show (commit details)
        if "show" in task_lower and "commit" in task_lower:
            repo_path = context.get("repo_path", ".")
            revision = context.get("revision", "HEAD")
            return self._tools["git_show"].call(repo_path=repo_path, revision=revision)

        # Read file
        if "read" in task_lower and "file" in task_lower:
            # Try to extract file path from task
            path = context.get("path")
            if not path:
                # Try to extract from task
                path = self._extract_path(original_task)
            if path:
                return self._tools["read_file"].call(path=path)
            raise ValueError("No file path specified. Provide 'path' in context.")

        # List directory
        if "list" in task_lower and ("dir" in task_lower or "folder" in task_lower):
            path = context.get("path", ".")
            return self._tools["list_directory"].call(path=path)

        # GitHub operations
        if "github" in task_lower or "pull request" in task_lower or "pr" in task_lower:
            owner = context.get("owner")
            repo = context.get("repo")
            if not owner or not repo:
                raise ValueError("GitHub operations require 'owner' and 'repo' in context")

            if "pr" in task_lower or "pull" in task_lower:
                return self._tools["github_list_prs"].call(owner=owner, repo=repo)
            elif "issue" in task_lower:
                return self._tools["github_list_issues"].call(owner=owner, repo=repo)
            else:
                return self._tools["github_get_repo"].call(owner=owner, repo=repo)

        # Multi-step: deployment check
        if "deploy" in task_lower:
            results = []
            repo_path = context.get("repo_path", ".")

            # Check status
            results.append("=== Git Status ===")
            results.append(self._tools["git_status"].call(repo_path=repo_path))

            # Check recent commits
            results.append("\n=== Recent Commits ===")
            results.append(self._tools["git_log"].call(repo_path=repo_path, max_count=5))

            return "\n".join(results)

        # Unknown task
        raise ValueError(
            f"Unknown task: {original_task}. "
            "Supported: git status/diff/log, read file, list directory, "
            "github pr/issues, deploy check"
        )

    def _extract_path(self, task: str) -> str | None:
        """Extract file path from task string.

        Args:
            task: Task string potentially containing a file path.

        Returns:
            Extracted path or None.
        """
        # Look for quoted paths
        quoted_match = re.search(r'["\']([^"\']+)["\']', task)
        if quoted_match:
            return quoted_match.group(1)

        # Look for common file patterns
        path_match = re.search(r"(\S+\.\w+)", task)
        if path_match:
            return path_match.group(1)

        return None

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format.

        Returns:
            List of tool definitions.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": wrapper.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            for name, wrapper in self._tools.items()
        ]

def create_devops_engineer_agent(
    config: dict[str, Any] | None = None,
) -> DevOpsEngineerAgent:
    """Factory function to create a DevOps Engineer agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured DevOpsEngineerAgent instance.

    Example:
        >>> agent = create_devops_engineer_agent()
        >>> result = await agent.execute("Show git status")
    """
    return DevOpsEngineerAgent(config=config)

__all__ = [
    "DevOpsEngineerAgent",
    "create_devops_engineer_agent",
]
