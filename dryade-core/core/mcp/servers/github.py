"""GitHub MCP Server Wrapper.

Provides typed Python API for GitHub operations via MCP.
Supports both stdio (npx) and HTTP (remote) transports.

Tools provided by GitHub MCP:
- Repository: create, fork, list, get
- Files: read, write, commit
- Issues: create, update, close, comment, list
- Pull Requests: create, merge, review, list
- Search: code, issues, repos
- Actions: list runs, trigger workflow
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

from core.mcp.config import MCPServerConfig, MCPServerTransport

logger = logging.getLogger(__name__)

@dataclass
class GitHubRepo:
    """GitHub repository information."""

    full_name: str
    description: str | None
    default_branch: str
    private: bool
    url: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubRepo:
        """Create GitHubRepo from API response dict."""
        return cls(
            full_name=data.get("full_name", ""),
            description=data.get("description"),
            default_branch=data.get("default_branch", "main"),
            private=data.get("private", False),
            url=data.get("html_url", data.get("url", "")),
        )

@dataclass
class GitHubIssue:
    """GitHub issue information."""

    number: int
    title: str
    body: str | None
    state: str
    labels: list[str] = field(default_factory=list)
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubIssue:
        """Create GitHubIssue from API response dict."""
        labels = [
            lbl.get("name", lbl) if isinstance(lbl, dict) else str(lbl)
            for lbl in data.get("labels", [])
        ]
        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body"),
            state=data.get("state", "open"),
            labels=labels,
            url=data.get("html_url", data.get("url", "")),
        )

@dataclass
class GitHubPR:
    """GitHub pull request information."""

    number: int
    title: str
    body: str | None
    state: str
    head_ref: str
    base_ref: str
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubPR:
        """Create GitHubPR from API response dict."""
        head = data.get("head", {})
        base = data.get("base", {})
        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body"),
            state=data.get("state", "open"),
            head_ref=head.get("ref", "") if isinstance(head, dict) else str(head),
            base_ref=base.get("ref", "") if isinstance(base, dict) else str(base),
            url=data.get("html_url", data.get("url", "")),
        )

class GitHubServer:
    """Typed wrapper for GitHub MCP server.

    Provides Python methods for GitHub operations. Can use either
    stdio transport (local npx) or HTTP transport (remote server).

    Usage:
        server = GitHubServer(registry)
        repos = await server.list_repos("owner")
        issue = await server.create_issue("owner/repo", "Bug", "Description")
    """

    SERVER_NAME = "github"

    def __init__(self, registry: MCPRegistry, server_name: str | None = None) -> None:
        """Initialize GitHubServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the GitHub server in registry (default: "github").
        """
        self._registry = registry
        self._server_name = server_name or self.SERVER_NAME

    @classmethod
    def get_stdio_config(cls) -> MCPServerConfig:
        """Get config for stdio transport (local npx).

        Returns:
            MCPServerConfig for GitHub MCP using npx.
        """
        return MCPServerConfig(
            name=cls.SERVER_NAME,
            command=["npx", "-y", "@modelcontextprotocol/server-github"],
            transport=MCPServerTransport.STDIO,
            env={"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            timeout=60.0,
        )

    @classmethod
    def get_http_config(cls, url: str | None = None) -> MCPServerConfig:
        """Get config for HTTP transport (remote server).

        Args:
            url: Remote server URL. Defaults to placeholder.

        Returns:
            MCPServerConfig for GitHub MCP using HTTP.
        """
        return MCPServerConfig(
            name=cls.SERVER_NAME,
            command=[],
            transport=MCPServerTransport.HTTP,
            url=url or "https://mcp.github.com/sse",
            auth_type="bearer",
            credential_service="dryade-mcp-github",
            timeout=60.0,
        )

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

    def _parse_json_list(self, text: str) -> list[dict[str, Any]]:
        """Parse JSON array from text response.

        Args:
            text: JSON text to parse.

        Returns:
            List of dicts, or empty list on error.
        """
        if not text:
            return []
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON list: %s", text[:100])
            return []

    def _parse_json_dict(self, text: str) -> dict[str, Any]:
        """Parse JSON object from text response.

        Args:
            text: JSON text to parse.

        Returns:
            Dict, or empty dict on error.
        """
        if not text:
            return {}
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON dict: %s", text[:100])
            return {}

    # ========================================================================
    # Repository Operations
    # ========================================================================

    async def list_repos(self, owner: str) -> list[GitHubRepo]:
        """List repositories for owner.

        Args:
            owner: GitHub username or organization name.

        Returns:
            List of GitHubRepo objects.
        """
        result = await self._registry.acall_tool(self._server_name, "list_repos", {"owner": owner})
        text = self._extract_text(result)
        items = self._parse_json_list(text)
        return [GitHubRepo.from_dict(item) for item in items]

    async def get_repo(self, owner: str, repo: str) -> GitHubRepo | None:
        """Get repository details.

        Args:
            owner: Repository owner.
            repo: Repository name.

        Returns:
            GitHubRepo or None if not found.
        """
        result = await self._registry.acall_tool(
            self._server_name, "get_repo", {"owner": owner, "repo": repo}
        )
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        if data:
            return GitHubRepo.from_dict(data)
        return None

    async def create_repo(
        self,
        name: str,
        description: str | None = None,
        private: bool = False,
    ) -> GitHubRepo | None:
        """Create a new repository.

        Args:
            name: Repository name.
            description: Optional description.
            private: Whether repository is private.

        Returns:
            Created GitHubRepo or None on error.
        """
        params: dict[str, Any] = {"name": name, "private": private}
        if description:
            params["description"] = description
        result = await self._registry.acall_tool(self._server_name, "create_repo", params)
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        if data:
            return GitHubRepo.from_dict(data)
        return None

    async def fork_repo(self, owner: str, repo: str) -> GitHubRepo | None:
        """Fork a repository.

        Args:
            owner: Original repository owner.
            repo: Original repository name.

        Returns:
            Forked GitHubRepo or None on error.
        """
        result = await self._registry.acall_tool(
            self._server_name, "fork_repo", {"owner": owner, "repo": repo}
        )
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        if data:
            return GitHubRepo.from_dict(data)
        return None

    # ========================================================================
    # Issue Operations
    # ========================================================================

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
    ) -> list[GitHubIssue]:
        """List issues in repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: Issue state filter ("open", "closed", "all").

        Returns:
            List of GitHubIssue objects.
        """
        result = await self._registry.acall_tool(
            self._server_name,
            "list_issues",
            {"owner": owner, "repo": repo, "state": state},
        )
        text = self._extract_text(result)
        items = self._parse_json_list(text)
        return [GitHubIssue.from_dict(item) for item in items]

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
    ) -> GitHubIssue | None:
        """Create a new issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            title: Issue title.
            body: Optional issue body.

        Returns:
            Created GitHubIssue or None on error.
        """
        params: dict[str, Any] = {"owner": owner, "repo": repo, "title": title}
        if body:
            params["body"] = body
        result = await self._registry.acall_tool(self._server_name, "create_issue", params)
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        if data:
            return GitHubIssue.from_dict(data)
        return None

    async def update_issue(
        self,
        owner: str,
        repo: str,
        number: int,
        **kwargs: Any,
    ) -> GitHubIssue | None:
        """Update an existing issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            number: Issue number.
            **kwargs: Fields to update (title, body, state, labels).

        Returns:
            Updated GitHubIssue or None on error.
        """
        params: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "issue_number": number,
            **kwargs,
        }
        result = await self._registry.acall_tool(self._server_name, "update_issue", params)
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        if data:
            return GitHubIssue.from_dict(data)
        return None

    async def add_issue_comment(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
    ) -> str:
        """Add a comment to an issue.

        Args:
            owner: Repository owner.
            repo: Repository name.
            number: Issue number.
            body: Comment body.

        Returns:
            Result message.
        """
        result = await self._registry.acall_tool(
            self._server_name,
            "add_issue_comment",
            {"owner": owner, "repo": repo, "issue_number": number, "body": body},
        )
        return self._extract_text(result)

    # ========================================================================
    # Pull Request Operations
    # ========================================================================

    async def list_prs(
        self,
        owner: str,
        repo: str,
        state: str = "open",
    ) -> list[GitHubPR]:
        """List pull requests.

        Args:
            owner: Repository owner.
            repo: Repository name.
            state: PR state filter ("open", "closed", "all").

        Returns:
            List of GitHubPR objects.
        """
        result = await self._registry.acall_tool(
            self._server_name,
            "list_pull_requests",
            {"owner": owner, "repo": repo, "state": state},
        )
        text = self._extract_text(result)
        items = self._parse_json_list(text)
        return [GitHubPR.from_dict(item) for item in items]

    async def create_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str = "",
    ) -> GitHubPR | None:
        """Create a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            title: PR title.
            head: Head branch name.
            base: Base branch name.
            body: PR body/description.

        Returns:
            Created GitHubPR or None on error.
        """
        params: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "title": title,
            "head": head,
            "base": base,
        }
        if body:
            params["body"] = body
        result = await self._registry.acall_tool(self._server_name, "create_pull_request", params)
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        if data:
            return GitHubPR.from_dict(data)
        return None

    async def merge_pr(
        self,
        owner: str,
        repo: str,
        number: int,
        commit_message: str | None = None,
    ) -> str:
        """Merge a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            number: PR number.
            commit_message: Optional merge commit message.

        Returns:
            Result message.
        """
        params: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "pull_number": number,
        }
        if commit_message:
            params["commit_message"] = commit_message
        result = await self._registry.acall_tool(self._server_name, "merge_pull_request", params)
        return self._extract_text(result)

    # ========================================================================
    # Search Operations
    # ========================================================================

    async def search_code(self, query: str) -> list[dict[str, Any]]:
        """Search code across GitHub.

        Args:
            query: Search query string.

        Returns:
            List of search result dicts.
        """
        result = await self._registry.acall_tool(self._server_name, "search_code", {"query": query})
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        return data.get("items", [])

    async def search_issues(self, query: str) -> list[dict[str, Any]]:
        """Search issues and PRs.

        Args:
            query: Search query string.

        Returns:
            List of search result dicts.
        """
        result = await self._registry.acall_tool(
            self._server_name, "search_issues", {"query": query}
        )
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        return data.get("items", [])

    async def search_repos(self, query: str) -> list[dict[str, Any]]:
        """Search repositories.

        Args:
            query: Search query string.

        Returns:
            List of search result dicts.
        """
        result = await self._registry.acall_tool(
            self._server_name, "search_repos", {"query": query}
        )
        text = self._extract_text(result)
        data = self._parse_json_dict(text)
        return data.get("items", [])

    # ========================================================================
    # File Operations
    # ========================================================================

    async def get_file_contents(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str | None = None,
    ) -> str:
        """Get file contents from repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path in repository.
            branch: Optional branch name.

        Returns:
            File contents as string.
        """
        params: dict[str, Any] = {"owner": owner, "repo": repo, "path": path}
        if branch:
            params["branch"] = branch
        result = await self._registry.acall_tool(self._server_name, "get_file_contents", params)
        return self._extract_text(result)

    async def push_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        """Push files to repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            branch: Target branch name.
            files: List of file dicts with "path" and "content" keys.
            message: Commit message.

        Returns:
            Result message.
        """
        result = await self._registry.acall_tool(
            self._server_name,
            "push_files",
            {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "files": files,
                "message": message,
            },
        )
        return self._extract_text(result)

def create_github_server(
    registry: MCPRegistry,
    use_http: bool = False,
    auto_register: bool = True,
) -> GitHubServer:
    """Factory function to create GitHubServer.

    Args:
        registry: MCP registry instance.
        use_http: Use HTTP transport instead of stdio.
        auto_register: Automatically register config with registry.

    Returns:
        Configured GitHubServer instance.
    """
    config = GitHubServer.get_http_config() if use_http else GitHubServer.get_stdio_config()
    if auto_register and not registry.is_registered(config.name):
        registry.register(config)
    return GitHubServer(registry)
