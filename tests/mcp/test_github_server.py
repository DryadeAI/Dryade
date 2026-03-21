"""Unit tests for GitHub MCP server wrapper."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.mcp.config import MCPServerTransport
from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.github import (
    GitHubIssue,
    GitHubPR,
    GitHubRepo,
    GitHubServer,
    create_github_server,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock()
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

# ============================================================================
# GitHubServer Config Tests
# ============================================================================

class TestGitHubServerConfig:
    """Tests for configuration generation."""

    def test_stdio_config(self):
        """Test stdio config has correct values."""
        config = GitHubServer.get_stdio_config()

        assert config.name == "github"
        assert config.transport == MCPServerTransport.STDIO
        assert "npx" in config.command
        assert "@modelcontextprotocol/server-github" in config.command[2]
        assert config.env.get("GITHUB_TOKEN") == "${GITHUB_TOKEN}"

    def test_http_config_default(self):
        """Test HTTP config with default URL."""
        config = GitHubServer.get_http_config()

        assert config.name == "github"
        assert config.transport == MCPServerTransport.HTTP
        assert config.auth_type == "bearer"
        assert config.credential_service == "dryade-mcp-github"
        assert config.url is not None

    def test_http_config_custom_url(self):
        """Test HTTP config with custom URL."""
        config = GitHubServer.get_http_config(url="https://custom.github.com/mcp")

        assert config.url == "https://custom.github.com/mcp"

# ============================================================================
# GitHubServer Initialization Tests
# ============================================================================

class TestGitHubServerInit:
    """Tests for GitHubServer initialization."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'github'."""
        server = GitHubServer(mock_registry)

        assert server._server_name == "github"
        assert server._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        server = GitHubServer(mock_registry, server_name="custom-github")

        assert server._server_name == "custom-github"

# ============================================================================
# Dataclass Tests
# ============================================================================

class TestGitHubDataclasses:
    """Tests for GitHub dataclasses."""

    def test_github_repo_from_dict(self):
        """Test GitHubRepo.from_dict parses API response."""
        data = {
            "full_name": "owner/repo",
            "description": "A test repo",
            "default_branch": "main",
            "private": False,
            "html_url": "https://github.com/owner/repo",
        }

        repo = GitHubRepo.from_dict(data)

        assert repo.full_name == "owner/repo"
        assert repo.description == "A test repo"
        assert repo.default_branch == "main"
        assert repo.private is False
        assert repo.url == "https://github.com/owner/repo"

    def test_github_repo_from_dict_minimal(self):
        """Test GitHubRepo.from_dict with minimal data."""
        repo = GitHubRepo.from_dict({})

        assert repo.full_name == ""
        assert repo.description is None
        assert repo.default_branch == "main"
        assert repo.private is False

    def test_github_issue_from_dict(self):
        """Test GitHubIssue.from_dict parses API response."""
        data = {
            "number": 42,
            "title": "Bug report",
            "body": "Something is broken",
            "state": "open",
            "labels": [{"name": "bug"}, {"name": "critical"}],
            "html_url": "https://github.com/owner/repo/issues/42",
        }

        issue = GitHubIssue.from_dict(data)

        assert issue.number == 42
        assert issue.title == "Bug report"
        assert issue.body == "Something is broken"
        assert issue.state == "open"
        assert issue.labels == ["bug", "critical"]
        assert issue.url == "https://github.com/owner/repo/issues/42"

    def test_github_pr_from_dict(self):
        """Test GitHubPR.from_dict parses API response."""
        data = {
            "number": 123,
            "title": "Add feature",
            "body": "This PR adds a feature",
            "state": "open",
            "head": {"ref": "feature-branch"},
            "base": {"ref": "main"},
            "html_url": "https://github.com/owner/repo/pull/123",
        }

        pr = GitHubPR.from_dict(data)

        assert pr.number == 123
        assert pr.title == "Add feature"
        assert pr.body == "This PR adds a feature"
        assert pr.state == "open"
        assert pr.head_ref == "feature-branch"
        assert pr.base_ref == "main"
        assert pr.url == "https://github.com/owner/repo/pull/123"

# ============================================================================
# Repository Operations Tests
# ============================================================================

class TestGitHubServerRepoOperations:
    """Tests for repository operations."""

    @pytest.fixture
    def server(self, mock_registry):
        mock_registry.is_registered.return_value = True
        return GitHubServer(mock_registry)

    @pytest.mark.asyncio
    async def test_list_repos(self, server, mock_registry, mock_result_text):
        """Test list_repos returns parsed repos."""
        repos_data = json.dumps(
            [
                {"full_name": "owner/repo1", "default_branch": "main", "private": False},
                {"full_name": "owner/repo2", "default_branch": "develop", "private": True},
            ]
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(repos_data))

        repos = await server.list_repos("owner")

        assert len(repos) == 2
        assert repos[0].full_name == "owner/repo1"
        assert repos[1].full_name == "owner/repo2"
        mock_registry.acall_tool.assert_called_once_with("github", "list_repos", {"owner": "owner"})

    @pytest.mark.asyncio
    async def test_list_repos_empty(self, server, mock_registry, mock_result_text):
        """Test list_repos with empty result."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("[]"))

        repos = await server.list_repos("owner")

        assert repos == []

    @pytest.mark.asyncio
    async def test_get_repo(self, server, mock_registry, mock_result_text):
        """Test get_repo returns parsed repo."""
        repo_data = json.dumps(
            {
                "full_name": "owner/repo",
                "description": "Test repo",
                "default_branch": "main",
                "private": False,
            }
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(repo_data))

        repo = await server.get_repo("owner", "repo")

        assert repo is not None
        assert repo.full_name == "owner/repo"
        mock_registry.acall_tool.assert_called_once_with(
            "github", "get_repo", {"owner": "owner", "repo": "repo"}
        )

    @pytest.mark.asyncio
    async def test_get_repo_not_found(self, server, mock_registry, mock_result_empty):
        """Test get_repo returns None when not found."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_empty)

        repo = await server.get_repo("owner", "nonexistent")

        assert repo is None

# ============================================================================
# Issue Operations Tests
# ============================================================================

class TestGitHubServerIssueOperations:
    """Tests for issue operations."""

    @pytest.fixture
    def server(self, mock_registry):
        mock_registry.is_registered.return_value = True
        return GitHubServer(mock_registry)

    @pytest.mark.asyncio
    async def test_list_issues(self, server, mock_registry, mock_result_text):
        """Test list_issues returns parsed issues."""
        issues_data = json.dumps(
            [
                {"number": 1, "title": "Bug 1", "state": "open"},
                {"number": 2, "title": "Bug 2", "state": "closed"},
            ]
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(issues_data))

        issues = await server.list_issues("owner", "repo")

        assert len(issues) == 2
        assert issues[0].number == 1
        assert issues[1].number == 2
        mock_registry.acall_tool.assert_called_once_with(
            "github", "list_issues", {"owner": "owner", "repo": "repo", "state": "open"}
        )

    @pytest.mark.asyncio
    async def test_create_issue(self, server, mock_registry, mock_result_text):
        """Test create_issue returns created issue."""
        issue_data = json.dumps(
            {
                "number": 42,
                "title": "New Bug",
                "body": "Bug description",
                "state": "open",
            }
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(issue_data))

        issue = await server.create_issue("owner", "repo", "New Bug", "Bug description")

        assert issue is not None
        assert issue.number == 42
        assert issue.title == "New Bug"
        mock_registry.acall_tool.assert_called_once_with(
            "github",
            "create_issue",
            {"owner": "owner", "repo": "repo", "title": "New Bug", "body": "Bug description"},
        )

    @pytest.mark.asyncio
    async def test_update_issue(self, server, mock_registry, mock_result_text):
        """Test update_issue returns updated issue."""
        issue_data = json.dumps(
            {
                "number": 42,
                "title": "Updated Title",
                "state": "closed",
            }
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(issue_data))

        issue = await server.update_issue("owner", "repo", 42, state="closed")

        assert issue is not None
        assert issue.state == "closed"
        mock_registry.acall_tool.assert_called_once_with(
            "github",
            "update_issue",
            {"owner": "owner", "repo": "repo", "issue_number": 42, "state": "closed"},
        )

# ============================================================================
# PR Operations Tests
# ============================================================================

class TestGitHubServerPROperations:
    """Tests for pull request operations."""

    @pytest.fixture
    def server(self, mock_registry):
        mock_registry.is_registered.return_value = True
        return GitHubServer(mock_registry)

    @pytest.mark.asyncio
    async def test_list_prs(self, server, mock_registry, mock_result_text):
        """Test list_prs returns parsed PRs."""
        prs_data = json.dumps(
            [
                {
                    "number": 1,
                    "title": "PR 1",
                    "state": "open",
                    "head": {"ref": "feature"},
                    "base": {"ref": "main"},
                },
            ]
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(prs_data))

        prs = await server.list_prs("owner", "repo")

        assert len(prs) == 1
        assert prs[0].number == 1
        mock_registry.acall_tool.assert_called_once_with(
            "github", "list_pull_requests", {"owner": "owner", "repo": "repo", "state": "open"}
        )

    @pytest.mark.asyncio
    async def test_create_pr(self, server, mock_registry, mock_result_text):
        """Test create_pr returns created PR."""
        pr_data = json.dumps(
            {
                "number": 123,
                "title": "New Feature",
                "state": "open",
                "head": {"ref": "feature"},
                "base": {"ref": "main"},
            }
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(pr_data))

        pr = await server.create_pr("owner", "repo", "New Feature", "feature", "main")

        assert pr is not None
        assert pr.number == 123
        mock_registry.acall_tool.assert_called_once()

# ============================================================================
# Search Operations Tests
# ============================================================================

class TestGitHubServerSearchOperations:
    """Tests for search operations."""

    @pytest.fixture
    def server(self, mock_registry):
        mock_registry.is_registered.return_value = True
        return GitHubServer(mock_registry)

    @pytest.mark.asyncio
    async def test_search_code(self, server, mock_registry, mock_result_text):
        """Test search_code returns results."""
        search_data = json.dumps(
            {"items": [{"path": "file.py", "repository": {"full_name": "owner/repo"}}]}
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(search_data))

        results = await server.search_code("def function")

        assert len(results) == 1
        assert results[0]["path"] == "file.py"
        mock_registry.acall_tool.assert_called_once_with(
            "github", "search_code", {"query": "def function"}
        )

    @pytest.mark.asyncio
    async def test_search_issues(self, server, mock_registry, mock_result_text):
        """Test search_issues returns results."""
        search_data = json.dumps({"items": [{"number": 42, "title": "Found issue"}]})
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(search_data))

        results = await server.search_issues("bug label:critical")

        assert len(results) == 1
        assert results[0]["number"] == 42

# ============================================================================
# Factory Function Tests
# ============================================================================

class TestCreateGitHubServer:
    """Tests for factory function."""

    def test_create_github_server_stdio(self, mock_registry):
        """Test factory creates server with stdio config."""
        server = create_github_server(mock_registry, use_http=False)

        assert isinstance(server, GitHubServer)
        mock_registry.register.assert_called_once()
        config = mock_registry.register.call_args[0][0]
        assert config.transport == MCPServerTransport.STDIO

    def test_create_github_server_http(self, mock_registry):
        """Test factory creates server with HTTP config."""
        server = create_github_server(mock_registry, use_http=True)

        assert isinstance(server, GitHubServer)
        mock_registry.register.assert_called_once()
        config = mock_registry.register.call_args[0][0]
        assert config.transport == MCPServerTransport.HTTP

    def test_create_github_server_skip_registration(self, mock_registry):
        """Test factory skips registration when already registered."""
        mock_registry.is_registered.return_value = True

        server = create_github_server(mock_registry)

        assert isinstance(server, GitHubServer)
        mock_registry.register.assert_not_called()

    def test_create_github_server_no_auto_register(self, mock_registry):
        """Test factory skips registration when auto_register=False."""
        server = create_github_server(mock_registry, auto_register=False)

        assert isinstance(server, GitHubServer)
        mock_registry.register.assert_not_called()
