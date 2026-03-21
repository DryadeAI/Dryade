"""Git MCP Server wrapper.

Provides typed Python interface for mcp-server-git
repository operations including status, diff, commit, and branch management.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

class GitServer:
    """Typed wrapper for mcp-server-git MCP server.

    Provides typed Python methods for all 12 git operations.
    Delegates to MCPRegistry for actual MCP communication.

    The Git server provides read, search, and manipulation of Git repositories
    through a fully local Python-based MCP server (installed via uvx).

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="git",
        ...     command=["uvx", "mcp-server-git"]
        ... )
        >>> registry.register(config)
        >>> git = GitServer(registry)
        >>> status = git.status("/path/to/repo")
    """

    def __init__(self, registry: MCPRegistry, server_name: str = "git") -> None:
        """Initialize GitServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the git server in registry (default: "git").
        """
        self._registry = registry
        self._server_name = server_name

    def status(self, repo_path: str) -> str:
        """Show the working tree status.

        Args:
            repo_path: Absolute path to the git repository.

        Returns:
            Git status output including branch info and file status.

        Raises:
            MCPTransportError: If the status cannot be retrieved.
        """
        result = self._registry.call_tool(self._server_name, "git_status", {"repo_path": repo_path})
        return self._extract_text(result)

    def diff_unstaged(self, repo_path: str) -> str:
        """Show unstaged changes in the working directory.

        Args:
            repo_path: Absolute path to the git repository.

        Returns:
            Diff output for unstaged changes.

        Raises:
            MCPTransportError: If the diff cannot be retrieved.
        """
        result = self._registry.call_tool(
            self._server_name, "git_diff_unstaged", {"repo_path": repo_path}
        )
        return self._extract_text(result)

    def diff_staged(self, repo_path: str) -> str:
        """Show staged changes (changes in the index).

        Args:
            repo_path: Absolute path to the git repository.

        Returns:
            Diff output for staged changes.

        Raises:
            MCPTransportError: If the diff cannot be retrieved.
        """
        result = self._registry.call_tool(
            self._server_name, "git_diff_staged", {"repo_path": repo_path}
        )
        return self._extract_text(result)

    def diff(self, repo_path: str, target: str) -> str:
        """Show diff between current state and a branch/commit.

        Args:
            repo_path: Absolute path to the git repository.
            target: Branch name, commit hash, or ref to diff against.

        Returns:
            Diff output comparing current state to target.

        Raises:
            MCPTransportError: If the diff cannot be retrieved.
        """
        result = self._registry.call_tool(
            self._server_name,
            "git_diff",
            {"repo_path": repo_path, "target": target},
        )
        return self._extract_text(result)

    def commit(self, repo_path: str, message: str) -> str:
        """Record changes to the repository.

        Args:
            repo_path: Absolute path to the git repository.
            message: Commit message.

        Returns:
            Commit result message with hash.

        Raises:
            MCPTransportError: If the commit fails.
        """
        result = self._registry.call_tool(
            self._server_name,
            "git_commit",
            {"repo_path": repo_path, "message": message},
        )
        return self._extract_text(result)

    def add(self, repo_path: str, files: list[str]) -> str:
        """Add file contents to the staging area.

        Args:
            repo_path: Absolute path to the git repository.
            files: List of file paths (relative to repo) to stage.

        Returns:
            Add result message.

        Raises:
            MCPTransportError: If the add fails.
        """
        result = self._registry.call_tool(
            self._server_name,
            "git_add",
            {"repo_path": repo_path, "files": files},
        )
        return self._extract_text(result)

    def reset(self, repo_path: str) -> str:
        """Unstage all staged changes.

        Args:
            repo_path: Absolute path to the git repository.

        Returns:
            Reset result message.

        Raises:
            MCPTransportError: If the reset fails.
        """
        result = self._registry.call_tool(self._server_name, "git_reset", {"repo_path": repo_path})
        return self._extract_text(result)

    def log(self, repo_path: str, max_count: int = 10) -> str:
        """Show the commit logs.

        Args:
            repo_path: Absolute path to the git repository.
            max_count: Maximum number of commits to show (default: 10).

        Returns:
            Commit log with hash, author, date, and message for each commit.

        Raises:
            MCPTransportError: If the log cannot be retrieved.
        """
        result = self._registry.call_tool(
            self._server_name,
            "git_log",
            {"repo_path": repo_path, "max_count": max_count},
        )
        return self._extract_text(result)

    def create_branch(
        self,
        repo_path: str,
        branch_name: str,
        base_branch: str | None = None,
    ) -> str:
        """Create a new branch.

        Args:
            repo_path: Absolute path to the git repository.
            branch_name: Name for the new branch.
            base_branch: Optional base branch to create from (default: current HEAD).

        Returns:
            Branch creation result message.

        Raises:
            MCPTransportError: If the branch creation fails.
        """
        args: dict = {"repo_path": repo_path, "branch_name": branch_name}
        if base_branch:
            args["base_branch"] = base_branch
        result = self._registry.call_tool(self._server_name, "git_create_branch", args)
        return self._extract_text(result)

    def checkout(self, repo_path: str, branch_name: str) -> str:
        """Switch branches.

        Args:
            repo_path: Absolute path to the git repository.
            branch_name: Name of the branch to switch to.

        Returns:
            Checkout result message.

        Raises:
            MCPTransportError: If the checkout fails.
        """
        result = self._registry.call_tool(
            self._server_name,
            "git_checkout",
            {"repo_path": repo_path, "branch_name": branch_name},
        )
        return self._extract_text(result)

    def show(self, repo_path: str, revision: str) -> str:
        """Show the contents of a commit.

        Args:
            repo_path: Absolute path to the git repository.
            revision: Commit hash, branch, or ref to show.

        Returns:
            Commit details including diff.

        Raises:
            MCPTransportError: If the show fails.
        """
        result = self._registry.call_tool(
            self._server_name,
            "git_show",
            {"repo_path": repo_path, "revision": revision},
        )
        return self._extract_text(result)

    def branches(self, repo_path: str) -> list[str]:
        """List all Git branches.

        Args:
            repo_path: Absolute path to the git repository.

        Returns:
            List of branch names (current branch marked with * in raw output).

        Raises:
            MCPTransportError: If the branch list cannot be retrieved.
        """
        result = self._registry.call_tool(self._server_name, "git_branch", {"repo_path": repo_path})
        text = self._extract_text(result)
        # Parse branch list, stripping * markers and whitespace
        branches = []
        for line in text.strip().split("\n"):
            if line.strip():
                # Remove leading * and whitespace
                branch = line.strip().lstrip("* ").strip()
                if branch:
                    branches.append(branch)
        return branches

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""
