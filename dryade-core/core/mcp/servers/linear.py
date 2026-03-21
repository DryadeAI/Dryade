"""Linear MCP Server Wrapper.

Provides typed Python API for Linear issue tracking via MCP.
Uses stdio transport with tacticlaunch's Linear MCP server.

Tools provided by Linear MCP:
- Issues: create, update, list, search
- Projects: list, create
- Teams: list
- Comments: add
- Status changes
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.registry import MCPRegistry

from core.mcp.config import MCPServerConfig, MCPServerTransport
from core.mcp.protocol import MCPToolCallResult

logger = logging.getLogger(__name__)

@dataclass
class LinearIssue:
    """Linear issue information."""

    id: str
    identifier: str  # e.g., "PRJ-123"
    title: str
    description: str | None
    state: str
    priority: int
    url: str

@dataclass
class LinearProject:
    """Linear project information."""

    id: str
    name: str
    description: str | None
    state: str

@dataclass
class LinearTeam:
    """Linear team information."""

    id: str
    name: str
    key: str  # e.g., "PRJ"

class LinearServer:
    """Typed wrapper for Linear MCP server.

    Provides issue tracking integration for developer workflows.
    Requires LINEAR_API_TOKEN environment variable.

    Usage:
        server = LinearServer(registry)
        teams = await server.list_teams()
        issue = await server.create_issue(teams[0].id, "Bug", "Description")
    """

    SERVER_NAME = "linear"

    def __init__(self, registry: MCPRegistry, server_name: str | None = None):
        """Initialize LinearServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the linear server in registry (default: "linear").
        """
        self._registry = registry
        self._server_name = server_name or self.SERVER_NAME

    @classmethod
    def get_config(cls) -> MCPServerConfig:
        """Get Linear server configuration.

        Requires LINEAR_API_TOKEN environment variable.

        Returns:
            MCPServerConfig for the Linear MCP server.
        """
        return MCPServerConfig(
            name=cls.SERVER_NAME,
            command=["npx", "-y", "@tacticlaunch/mcp-linear"],
            transport=MCPServerTransport.STDIO,
            env={"LINEAR_API_TOKEN": "${LINEAR_API_TOKEN}"},
            credential_service="dryade-mcp-linear",
            timeout=30.0,
        )

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from tool call result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if not result.content:
            return ""
        for item in result.content:
            if item.type == "text" and item.text:
                return item.text
        return ""

    def _parse_json(self, text: str) -> Any:
        """Parse JSON from text, handling potential wrapper text.

        Args:
            text: Text that may contain JSON data.

        Returns:
            Parsed JSON data, or None if parsing fails.
        """
        if not text:
            return None
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON in text (may have prefix/suffix text)
        start = text.find("[")
        if start == -1:
            start = text.find("{")
        if start == -1:
            return None
        end = text.rfind("]")
        if end == -1:
            end = text.rfind("}")
        if end == -1 or end < start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from response: {text[:100]}...")
            return None

    def _parse_team(self, data: dict[str, Any]) -> LinearTeam:
        """Parse team data into LinearTeam object.

        Args:
            data: Dictionary containing team data from Linear API.

        Returns:
            LinearTeam object with parsed fields.
        """
        return LinearTeam(
            id=data.get("id", ""),
            name=data.get("name", ""),
            key=data.get("key", ""),
        )

    def _parse_issue(self, data: dict[str, Any]) -> LinearIssue:
        """Parse issue data into LinearIssue object.

        Args:
            data: Dictionary containing issue data from Linear API.

        Returns:
            LinearIssue object with parsed fields.
        """
        # Handle state which can be a dict with name or a string
        state_data = data.get("state")
        if isinstance(state_data, dict):
            state = state_data.get("name", "")
        else:
            state = str(state_data) if state_data else ""

        return LinearIssue(
            id=data.get("id", ""),
            identifier=data.get("identifier", ""),
            title=data.get("title", ""),
            description=data.get("description"),
            state=state,
            priority=data.get("priority", 0),
            url=data.get("url", ""),
        )

    def _parse_project(self, data: dict[str, Any]) -> LinearProject:
        """Parse project data into LinearProject object.

        Args:
            data: Dictionary containing project data from Linear API.

        Returns:
            LinearProject object with parsed fields.
        """
        return LinearProject(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            state=data.get("state", ""),
        )

    # Team operations
    async def list_teams(self) -> list[LinearTeam]:
        """List all teams in workspace.

        Returns:
            List of LinearTeam objects.
        """
        result = await self._registry.acall_tool(self._server_name, "linear_list_teams", {})
        text = self._extract_text(result)
        data = self._parse_json(text)

        if data is None:
            logger.warning("No teams data returned from Linear")
            return []

        # Handle both array and object with teams field
        teams_data = data if isinstance(data, list) else data.get("teams", [])
        return [self._parse_team(t) for t in teams_data]

    # Issue operations
    async def list_issues(
        self,
        team_id: str | None = None,
        state: str | None = None,
    ) -> list[LinearIssue]:
        """List issues, optionally filtered by team and state.

        Args:
            team_id: Optional team ID to filter by.
            state: Optional state to filter by.

        Returns:
            List of LinearIssue objects.
        """
        args: dict[str, Any] = {}
        if team_id:
            args["teamId"] = team_id
        if state:
            args["state"] = state

        result = await self._registry.acall_tool(self._server_name, "linear_list_issues", args)
        text = self._extract_text(result)
        data = self._parse_json(text)

        if data is None:
            logger.warning("No issues data returned from Linear")
            return []

        # Handle both array and object with issues field
        issues_data = data if isinstance(data, list) else data.get("issues", [])
        return [self._parse_issue(i) for i in issues_data]

    async def create_issue(
        self,
        team_id: str,
        title: str,
        description: str | None = None,
        priority: int = 2,  # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    ) -> LinearIssue:
        """Create a new issue.

        Args:
            team_id: Team ID to create issue in.
            title: Issue title.
            description: Optional issue description.
            priority: Issue priority (0=none, 1=urgent, 2=high, 3=medium, 4=low).

        Returns:
            Created LinearIssue object.
        """
        args: dict[str, Any] = {
            "teamId": team_id,
            "title": title,
            "priority": priority,
        }
        if description:
            args["description"] = description

        result = await self._registry.acall_tool(self._server_name, "linear_create_issue", args)
        text = self._extract_text(result)
        data = self._parse_json(text)

        if data is None:
            # Return minimal issue with what we know
            logger.warning("Could not parse created issue response")
            return LinearIssue(
                id="",
                identifier="",
                title=title,
                description=description,
                state="",
                priority=priority,
                url="",
            )

        # Handle nested issue field
        issue_data = data.get("issue", data) if isinstance(data, dict) else data
        return self._parse_issue(issue_data)

    async def update_issue(
        self,
        issue_id: str,
        **kwargs: Any,
    ) -> LinearIssue:
        """Update an existing issue.

        Args:
            issue_id: Issue ID to update.
            **kwargs: Fields to update (title, description, state, priority).

        Returns:
            Updated LinearIssue object.
        """
        args: dict[str, Any] = {"issueId": issue_id, **kwargs}
        result = await self._registry.acall_tool(self._server_name, "linear_update_issue", args)
        text = self._extract_text(result)
        data = self._parse_json(text)

        if data is None:
            logger.warning("Could not parse updated issue response")
            return LinearIssue(
                id=issue_id,
                identifier="",
                title=kwargs.get("title", ""),
                description=kwargs.get("description"),
                state=kwargs.get("state", ""),
                priority=kwargs.get("priority", 0),
                url="",
            )

        # Handle nested issue field
        issue_data = data.get("issue", data) if isinstance(data, dict) else data
        return self._parse_issue(issue_data)

    async def search_issues(self, query: str) -> list[LinearIssue]:
        """Search issues by query.

        Args:
            query: Search query string.

        Returns:
            List of matching LinearIssue objects.
        """
        result = await self._registry.acall_tool(
            self._server_name, "linear_search_issues", {"query": query}
        )
        text = self._extract_text(result)
        data = self._parse_json(text)

        if data is None:
            logger.warning("No search results returned from Linear")
            return []

        # Handle both array and object with issues field
        issues_data = data if isinstance(data, list) else data.get("issues", [])
        return [self._parse_issue(i) for i in issues_data]

    # Comment operations
    async def add_comment(self, issue_id: str, body: str) -> None:
        """Add comment to an issue.

        Args:
            issue_id: Issue ID to add comment to.
            body: Comment body text.
        """
        await self._registry.acall_tool(
            self._server_name,
            "linear_create_comment",
            {"issueId": issue_id, "body": body},
        )

    # Project operations
    async def list_projects(self, team_id: str | None = None) -> list[LinearProject]:
        """List projects, optionally filtered by team.

        Args:
            team_id: Optional team ID to filter by.

        Returns:
            List of LinearProject objects.
        """
        args: dict[str, Any] = {}
        if team_id:
            args["teamId"] = team_id

        result = await self._registry.acall_tool(self._server_name, "linear_list_projects", args)
        text = self._extract_text(result)
        data = self._parse_json(text)

        if data is None:
            logger.warning("No projects data returned from Linear")
            return []

        # Handle both array and object with projects field
        projects_data = data if isinstance(data, list) else data.get("projects", [])
        return [self._parse_project(p) for p in projects_data]

def create_linear_server(
    registry: MCPRegistry,
    auto_register: bool = True,
) -> LinearServer:
    """Factory function to create LinearServer.

    Args:
        registry: MCP registry instance.
        auto_register: Automatically register config with registry.

    Returns:
        Configured LinearServer instance.
    """
    config = LinearServer.get_config()
    if auto_register and not registry.is_registered(config.name):
        registry.register(config)
    return LinearServer(registry)
