"""Unit tests for Linear MCP server wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.mcp import MCPRegistry, MCPServerTransport
from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.linear import (
    LinearIssue,
    LinearProject,
    LinearServer,
    LinearTeam,
    create_linear_server,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock(spec=MCPRegistry)
    registry.is_registered.return_value = False
    return registry

@pytest.fixture
def mock_result_text():
    """Create a factory for MCPToolCallResult with text content."""

    def _make_result(text: str, is_error: bool = False) -> MCPToolCallResult:
        return MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text=text)],
            isError=is_error,
        )

    return _make_result

@pytest.fixture
def mock_result_empty():
    """Create an empty MCPToolCallResult."""
    return MCPToolCallResult(content=[], isError=False)

@pytest.fixture
def server(mock_registry):
    """Create a LinearServer with mocked registry."""
    mock_registry.is_registered.return_value = True
    return LinearServer(mock_registry)

# ============================================================================
# Configuration Tests
# ============================================================================

class TestLinearServerConfig:
    """Tests for configuration generation."""

    def test_config_with_env_var(self):
        """Test config has LINEAR_API_TOKEN environment variable."""
        config = LinearServer.get_config()
        assert config.name == "linear"
        assert config.transport == MCPServerTransport.STDIO
        assert "LINEAR_API_TOKEN" in config.env

    def test_config_command(self):
        """Test config has correct command."""
        config = LinearServer.get_config()
        assert "npx" in config.command
        assert "@tacticlaunch/mcp-linear" in " ".join(config.command)

    def test_config_timeout(self):
        """Test config has appropriate timeout."""
        config = LinearServer.get_config()
        assert config.timeout == 30.0

    def test_config_credential_service(self):
        """Test config has credential service."""
        config = LinearServer.get_config()
        assert config.credential_service == "dryade-mcp-linear"

# ============================================================================
# Factory Function Tests
# ============================================================================

class TestCreateLinearServer:
    """Tests for factory function."""

    def test_creates_server(self, mock_registry):
        """Test factory creates LinearServer instance."""
        server = create_linear_server(mock_registry)
        assert isinstance(server, LinearServer)
        assert server._server_name == "linear"

    def test_auto_register(self, mock_registry):
        """Test factory auto-registers with registry."""
        mock_registry.is_registered.return_value = False
        create_linear_server(mock_registry)
        mock_registry.register.assert_called_once()

    def test_skip_register_if_exists(self, mock_registry):
        """Test factory skips registration if already registered."""
        mock_registry.is_registered.return_value = True
        create_linear_server(mock_registry)
        mock_registry.register.assert_not_called()

    def test_auto_register_false(self, mock_registry):
        """Test factory respects auto_register=False."""
        create_linear_server(mock_registry, auto_register=False)
        mock_registry.register.assert_not_called()

# ============================================================================
# Team Operations Tests
# ============================================================================

class TestLinearServerTeams:
    """Tests for team operations."""

    @pytest.mark.asyncio
    async def test_list_teams(self, server, mock_registry, mock_result_text):
        """Test list_teams returns parsed teams."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text('[{"id": "team1", "name": "Engineering", "key": "ENG"}]')
        )
        teams = await server.list_teams()
        assert len(teams) == 1
        assert isinstance(teams[0], LinearTeam)
        assert teams[0].id == "team1"
        assert teams[0].name == "Engineering"
        assert teams[0].key == "ENG"

    @pytest.mark.asyncio
    async def test_list_teams_nested(self, server, mock_registry, mock_result_text):
        """Test list_teams handles nested teams field."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '{"teams": [{"id": "team1", "name": "Team", "key": "TM"}]}'
            )
        )
        teams = await server.list_teams()
        assert len(teams) == 1
        assert teams[0].id == "team1"

    @pytest.mark.asyncio
    async def test_list_teams_empty(self, server, mock_registry, mock_result_empty):
        """Test list_teams with empty result."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_empty)
        teams = await server.list_teams()
        assert teams == []

# ============================================================================
# Issue Operations Tests
# ============================================================================

class TestLinearServerIssues:
    """Tests for issue operations."""

    @pytest.mark.asyncio
    async def test_list_issues(self, server, mock_registry, mock_result_text):
        """Test list_issues returns parsed issues."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '[{"id": "issue1", "identifier": "ENG-1", "title": "Bug", '
                '"description": "Description", "priority": 2, "url": "https://linear.app/issue"}]'
            )
        )
        issues = await server.list_issues(team_id="team1")
        mock_registry.acall_tool.assert_called_once()
        assert len(issues) == 1
        assert isinstance(issues[0], LinearIssue)
        assert issues[0].id == "issue1"
        assert issues[0].identifier == "ENG-1"
        assert issues[0].title == "Bug"
        assert issues[0].description == "Description"
        assert issues[0].priority == 2

    @pytest.mark.asyncio
    async def test_list_issues_with_state(self, server, mock_registry, mock_result_text):
        """Test list_issues with state filter."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("[]"))
        await server.list_issues(team_id="team1", state="In Progress")
        call_args = mock_registry.acall_tool.call_args[0]
        assert call_args[2] == {"teamId": "team1", "state": "In Progress"}

    @pytest.mark.asyncio
    async def test_list_issues_nested(self, server, mock_registry, mock_result_text):
        """Test list_issues handles nested issues field."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '{"issues": [{"id": "issue1", "identifier": "TM-1", "title": "Test"}]}'
            )
        )
        issues = await server.list_issues()
        assert len(issues) == 1
        assert issues[0].title == "Test"

    @pytest.mark.asyncio
    async def test_list_issues_with_state_object(self, server, mock_registry, mock_result_text):
        """Test list_issues handles state as object with name field."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '[{"id": "issue1", "identifier": "TM-1", "title": "Bug", '
                '"state": {"name": "In Progress"}, "priority": 2, "url": ""}]'
            )
        )
        issues = await server.list_issues()
        assert len(issues) == 1
        assert issues[0].state == "In Progress"

    @pytest.mark.asyncio
    async def test_search_issues(self, server, mock_registry, mock_result_text):
        """Test search_issues returns matching issues."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '{"issues": [{"id": "issue1", "identifier": "TM-1", "title": "Search result"}]}'
            )
        )
        issues = await server.search_issues("bug")
        mock_registry.acall_tool.assert_called_once_with(
            "linear", "linear_search_issues", {"query": "bug"}
        )
        assert len(issues) == 1
        assert issues[0].title == "Search result"

    @pytest.mark.asyncio
    async def test_create_issue(self, server, mock_registry, mock_result_text):
        """Test create_issue creates and returns issue."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '{"issue": {"id": "issue1", "identifier": "TM-1", "title": "Bug", "priority": 2}}'
            )
        )
        issue = await server.create_issue("team1", "Bug", "Description")
        mock_registry.acall_tool.assert_called_once()
        call_args = mock_registry.acall_tool.call_args[0]
        assert call_args[2] == {
            "teamId": "team1",
            "title": "Bug",
            "description": "Description",
            "priority": 2,
        }
        assert issue.title == "Bug"
        assert issue.id == "issue1"

    @pytest.mark.asyncio
    async def test_create_issue_fallback(self, server, mock_registry, mock_result_empty):
        """Test create_issue fallback when response cannot be parsed."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_empty)
        issue = await server.create_issue("team1", "Bug", "Desc", priority=1)
        # Should return minimal issue with provided values
        assert issue.title == "Bug"
        assert issue.description == "Desc"
        assert issue.priority == 1

    @pytest.mark.asyncio
    async def test_update_issue(self, server, mock_registry, mock_result_text):
        """Test update_issue updates and returns issue."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '{"issue": {"id": "issue1", "identifier": "TM-1", '
                '"title": "Updated Bug", "priority": 1}}'
            )
        )
        issue = await server.update_issue("issue1", title="Updated Bug", priority=1)
        mock_registry.acall_tool.assert_called_once()
        call_args = mock_registry.acall_tool.call_args[0]
        assert call_args[2] == {"issueId": "issue1", "title": "Updated Bug", "priority": 1}
        assert issue.title == "Updated Bug"

    @pytest.mark.asyncio
    async def test_update_issue_fallback(self, server, mock_registry, mock_result_empty):
        """Test update_issue fallback when response cannot be parsed."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_empty)
        issue = await server.update_issue("issue1", title="Updated", state="Done")
        # Should return minimal issue with provided values
        assert issue.id == "issue1"
        assert issue.title == "Updated"
        assert issue.state == "Done"

# ============================================================================
# Comment Operations Tests
# ============================================================================

class TestLinearServerComments:
    """Tests for comment operations."""

    @pytest.mark.asyncio
    async def test_add_comment(self, server, mock_registry, mock_result_text):
        """Test add_comment sends correct parameters."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text('{"success": true}'))
        await server.add_comment("issue1", "This is a comment")
        mock_registry.acall_tool.assert_called_once_with(
            "linear",
            "linear_create_comment",
            {"issueId": "issue1", "body": "This is a comment"},
        )

# ============================================================================
# Project Operations Tests
# ============================================================================

class TestLinearServerProjects:
    """Tests for project operations."""

    @pytest.mark.asyncio
    async def test_list_projects(self, server, mock_registry, mock_result_text):
        """Test list_projects returns parsed projects."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '[{"id": "proj1", "name": "Project Alpha", '
                '"description": "Description", "state": "active"}]'
            )
        )
        projects = await server.list_projects()
        mock_registry.acall_tool.assert_called_once()
        assert len(projects) == 1
        assert isinstance(projects[0], LinearProject)
        assert projects[0].id == "proj1"
        assert projects[0].name == "Project Alpha"
        assert projects[0].state == "active"

    @pytest.mark.asyncio
    async def test_list_projects_with_team(self, server, mock_registry, mock_result_text):
        """Test list_projects with team filter."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("[]"))
        await server.list_projects(team_id="team1")
        call_args = mock_registry.acall_tool.call_args[0]
        assert call_args[2] == {"teamId": "team1"}

    @pytest.mark.asyncio
    async def test_list_projects_nested(self, server, mock_registry, mock_result_text):
        """Test list_projects handles nested projects field."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '{"projects": [{"id": "proj1", "name": "Project", "state": "active"}]}'
            )
        )
        projects = await server.list_projects()
        assert len(projects) == 1
        assert projects[0].name == "Project"

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, server, mock_registry, mock_result_empty):
        """Test list_projects with empty result."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_empty)
        projects = await server.list_projects()
        assert projects == []

# ============================================================================
# JSON Parsing Tests
# ============================================================================

class TestLinearServerJsonParsing:
    """Tests for JSON parsing helper methods."""

    def test_parse_json_valid(self, server):
        """Test _parse_json with valid JSON."""
        result = server._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_array(self, server):
        """Test _parse_json with JSON array."""
        result = server._parse_json('[{"id": 1}]')
        assert result == [{"id": 1}]

    def test_parse_json_with_prefix(self, server):
        """Test _parse_json with prefix text."""
        result = server._parse_json('Response: {"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_suffix(self, server):
        """Test _parse_json with suffix text."""
        result = server._parse_json('{"key": "value"} extra text')
        assert result == {"key": "value"}

    def test_parse_json_empty(self, server):
        """Test _parse_json with empty string."""
        result = server._parse_json("")
        assert result is None

    def test_parse_json_invalid(self, server):
        """Test _parse_json with invalid JSON."""
        result = server._parse_json("not json at all")
        assert result is None

# ============================================================================
# Edge Case Tests
# ============================================================================

class TestLinearServerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_custom_server_name(self, mock_registry):
        """Test LinearServer with custom server name."""
        server = LinearServer(mock_registry, server_name="custom-linear")
        assert server._server_name == "custom-linear"

    @pytest.mark.asyncio
    async def test_issue_with_null_description(self, server, mock_registry, mock_result_text):
        """Test parsing issue with null description."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text(
                '[{"id": "issue1", "identifier": "TM-1", "title": "Bug", '
                '"description": null, "priority": 2, "url": ""}]'
            )
        )
        issues = await server.list_issues()
        assert len(issues) == 1
        assert issues[0].description is None

    @pytest.mark.asyncio
    async def test_issue_with_missing_fields(self, server, mock_registry, mock_result_text):
        """Test parsing issue with missing optional fields."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text('[{"id": "issue1", "title": "Bug"}]')
        )
        issues = await server.list_issues()
        assert len(issues) == 1
        assert issues[0].id == "issue1"
        assert issues[0].identifier == ""  # Missing field defaults to empty
        assert issues[0].priority == 0  # Missing field defaults to 0
