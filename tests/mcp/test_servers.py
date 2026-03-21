"""Unit tests for MCP Server Wrappers.

Comprehensive tests for FilesystemServer, GitServer, and MemoryServer
wrappers using mocked MCPRegistry to verify correct delegation and
response handling.

Includes tests for Entity and Relation helper classes.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock

import pytest

from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers import (
    Entity,
    FilesystemServer,
    GitServer,
    MemoryServer,
    Relation,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock()
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
# Entity Tests
# ============================================================================

class TestEntity:
    """Tests for Entity helper class."""

    def test_entity_init_basic(self):
        """Test Entity initialization with required fields."""
        entity = Entity(name="Alice", entity_type="person")

        assert entity.name == "Alice"
        assert entity.entity_type == "person"
        assert entity.observations == []

    def test_entity_init_with_observations(self):
        """Test Entity initialization with observations."""
        entity = Entity(
            name="Project",
            entity_type="project",
            observations=["Python project", "Uses LLM agents"],
        )

        assert entity.name == "Project"
        assert entity.entity_type == "project"
        assert entity.observations == ["Python project", "Uses LLM agents"]

    def test_entity_to_dict(self):
        """Test Entity.to_dict() returns MCP-compatible format."""
        entity = Entity(
            name="ProjectDryade",
            entity_type="project",
            observations=["Python project"],
        )

        result = entity.to_dict()

        assert result == {
            "name": "ProjectDryade",
            "entityType": "project",
            "observations": ["Python project"],
        }

    def test_entity_to_dict_empty_observations(self):
        """Test Entity.to_dict() with no observations."""
        entity = Entity(name="Test", entity_type="test")

        result = entity.to_dict()

        assert result == {
            "name": "Test",
            "entityType": "test",
            "observations": [],
        }

# ============================================================================
# Relation Tests
# ============================================================================

class TestRelation:
    """Tests for Relation helper class."""

    def test_relation_init(self):
        """Test Relation initialization."""
        relation = Relation(
            from_entity="Alice",
            to_entity="ProjectDryade",
            relation_type="works_on",
        )

        assert relation.from_entity == "Alice"
        assert relation.to_entity == "ProjectDryade"
        assert relation.relation_type == "works_on"

    def test_relation_to_dict(self):
        """Test Relation.to_dict() returns MCP-compatible format."""
        relation = Relation(
            from_entity="Alice",
            to_entity="ProjectDryade",
            relation_type="works_on",
        )

        result = relation.to_dict()

        assert result == {
            "from": "Alice",
            "to": "ProjectDryade",
            "relationType": "works_on",
        }

# ============================================================================
# FilesystemServer Tests
# ============================================================================

class TestFilesystemServer:
    """Tests for FilesystemServer wrapper."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'filesystem'."""
        fs = FilesystemServer(mock_registry)

        assert fs._server_name == "filesystem"
        assert fs._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        fs = FilesystemServer(mock_registry, server_name="custom-fs")

        assert fs._server_name == "custom-fs"

    def test_read_text_file_basic(self, mock_registry, mock_result_text):
        """Test read_text_file delegates to registry."""
        mock_registry.call_tool.return_value = mock_result_text("file contents")
        fs = FilesystemServer(mock_registry)

        result = fs.read_text_file("/tmp/test.txt")

        assert result == "file contents"

    def test_read_text_file(self, mock_registry, mock_result_text):
        """Test read_text_file with encoding."""
        mock_registry.call_tool.return_value = mock_result_text("text content")
        fs = FilesystemServer(mock_registry)

        result = fs.read_text_file("/tmp/test.txt", encoding="utf-16")

        assert result == "text content"
        mock_registry.call_tool.assert_called_once_with(
            "filesystem",
            "read_text_file",
            {"path": "/tmp/test.txt", "encoding": "utf-16"},
        )

    def test_read_media_file(self, mock_registry, mock_result_text):
        """Test read_media_file decodes base64."""
        encoded = base64.b64encode(b"binary data").decode()
        mock_registry.call_tool.return_value = mock_result_text(encoded)
        fs = FilesystemServer(mock_registry)

        result = fs.read_media_file("/tmp/image.png")

        assert result == b"binary data"
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "read_media_file", {"path": "/tmp/image.png"}
        )

    def test_read_multiple_files(self, mock_registry, mock_result_text):
        """Test read_multiple_files returns dict."""
        content = json.dumps({"/tmp/a.txt": "content a", "/tmp/b.txt": "content b"})
        mock_registry.call_tool.return_value = mock_result_text(content)
        fs = FilesystemServer(mock_registry)

        result = fs.read_multiple_files(["/tmp/a.txt", "/tmp/b.txt"])

        assert result == {"/tmp/a.txt": "content a", "/tmp/b.txt": "content b"}
        mock_registry.call_tool.assert_called_once_with(
            "filesystem",
            "read_multiple_files",
            {"paths": ["/tmp/a.txt", "/tmp/b.txt"]},
        )

    def test_read_multiple_files_empty(self, mock_registry, mock_result_empty):
        """Test read_multiple_files with empty result."""
        mock_registry.call_tool.return_value = mock_result_empty
        fs = FilesystemServer(mock_registry)

        result = fs.read_multiple_files([])

        assert result == {}

    def test_write_file(self, mock_registry, mock_result_text):
        """Test write_file delegates to registry."""
        mock_registry.call_tool.return_value = mock_result_text("OK")
        fs = FilesystemServer(mock_registry)

        fs.write_file("/tmp/test.txt", "new content")

        mock_registry.call_tool.assert_called_once_with(
            "filesystem",
            "write_file",
            {"path": "/tmp/test.txt", "content": "new content"},
        )

    def test_edit_file(self, mock_registry, mock_result_text):
        """Test edit_file with edits list."""
        mock_registry.call_tool.return_value = mock_result_text("Edited")
        fs = FilesystemServer(mock_registry)
        edits = [{"oldText": "old", "newText": "new"}]

        result = fs.edit_file("/tmp/test.txt", edits)

        assert result == "Edited"
        mock_registry.call_tool.assert_called_once_with(
            "filesystem",
            "edit_file",
            {"path": "/tmp/test.txt", "edits": edits},
        )

    def test_create_directory(self, mock_registry, mock_result_text):
        """Test create_directory delegates to registry."""
        mock_registry.call_tool.return_value = mock_result_text("OK")
        fs = FilesystemServer(mock_registry)

        fs.create_directory("/tmp/newdir")

        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "create_directory", {"path": "/tmp/newdir"}
        )

    def test_list_directory(self, mock_registry, mock_result_text):
        """Test list_directory returns list of entries."""
        mock_registry.call_tool.return_value = mock_result_text("[FILE] test.txt\n[DIR] subdir")
        fs = FilesystemServer(mock_registry)

        result = fs.list_directory("/tmp")

        assert result == ["[FILE] test.txt", "[DIR] subdir"]
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "list_directory", {"path": "/tmp"}
        )

    def test_list_directory_empty(self, mock_registry, mock_result_text):
        """Test list_directory with empty directory."""
        mock_registry.call_tool.return_value = mock_result_text("")
        fs = FilesystemServer(mock_registry)

        result = fs.list_directory("/tmp/empty")

        assert result == []

    def test_list_directory_with_sizes(self, mock_registry, mock_result_text):
        """Test list_directory_with_sizes returns formatted string."""
        mock_registry.call_tool.return_value = mock_result_text("test.txt    1024B\ndir/        -")
        fs = FilesystemServer(mock_registry)

        result = fs.list_directory_with_sizes("/tmp")

        assert result == "test.txt    1024B\ndir/        -"
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "list_directory_with_sizes", {"path": "/tmp"}
        )

    def test_directory_tree(self, mock_registry, mock_result_text):
        """Test directory_tree returns parsed dict."""
        tree = {"name": "root", "children": [{"name": "file.txt", "type": "file"}]}
        mock_registry.call_tool.return_value = mock_result_text(json.dumps(tree))
        fs = FilesystemServer(mock_registry)

        result = fs.directory_tree("/tmp")

        assert result == tree
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "directory_tree", {"path": "/tmp"}
        )

    def test_directory_tree_empty(self, mock_registry, mock_result_empty):
        """Test directory_tree with empty result."""
        mock_registry.call_tool.return_value = mock_result_empty
        fs = FilesystemServer(mock_registry)

        result = fs.directory_tree("/tmp/empty")

        assert result == {}

    def test_move_file(self, mock_registry, mock_result_text):
        """Test move_file delegates to registry."""
        mock_registry.call_tool.return_value = mock_result_text("OK")
        fs = FilesystemServer(mock_registry)

        fs.move_file("/tmp/old.txt", "/tmp/new.txt")

        mock_registry.call_tool.assert_called_once_with(
            "filesystem",
            "move_file",
            {"source": "/tmp/old.txt", "destination": "/tmp/new.txt"},
        )

    def test_search_files(self, mock_registry, mock_result_text):
        """Test search_files returns list of paths."""
        mock_registry.call_tool.return_value = mock_result_text("/tmp/a.py\n/tmp/b.py")
        fs = FilesystemServer(mock_registry)

        result = fs.search_files("/tmp", "*.py")

        assert result == ["/tmp/a.py", "/tmp/b.py"]
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "search_files", {"path": "/tmp", "pattern": "*.py"}
        )

    def test_search_files_no_matches(self, mock_registry, mock_result_text):
        """Test search_files with no matches."""
        mock_registry.call_tool.return_value = mock_result_text("")
        fs = FilesystemServer(mock_registry)

        result = fs.search_files("/tmp", "*.xyz")

        assert result == []

    def test_get_file_info(self, mock_registry, mock_result_text):
        """Test get_file_info returns parsed metadata."""
        info = {"size": 1024, "mtime": "2024-01-01T00:00:00"}
        mock_registry.call_tool.return_value = mock_result_text(json.dumps(info))
        fs = FilesystemServer(mock_registry)

        result = fs.get_file_info("/tmp/test.txt")

        assert result == info
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "get_file_info", {"path": "/tmp/test.txt"}
        )

    def test_get_file_info_empty(self, mock_registry, mock_result_empty):
        """Test get_file_info with empty result."""
        mock_registry.call_tool.return_value = mock_result_empty
        fs = FilesystemServer(mock_registry)

        result = fs.get_file_info("/tmp/missing.txt")

        assert result == {}

    def test_list_allowed_directories(self, mock_registry, mock_result_text):
        """Test list_allowed_directories returns list."""
        mock_registry.call_tool.return_value = mock_result_text("/tmp\n/home")
        fs = FilesystemServer(mock_registry)

        result = fs.list_allowed_directories()

        assert result == ["/tmp", "/home"]
        mock_registry.call_tool.assert_called_once_with(
            "filesystem", "list_allowed_directories", {}
        )

    def test_list_allowed_directories_empty(self, mock_registry, mock_result_text):
        """Test list_allowed_directories with empty result."""
        mock_registry.call_tool.return_value = mock_result_text("")
        fs = FilesystemServer(mock_registry)

        result = fs.list_allowed_directories()

        assert result == []

    def test_extract_text_with_content(self, mock_registry, mock_result_text):
        """Test _extract_text extracts text from result."""
        mock_registry.call_tool.return_value = mock_result_text("extracted")
        fs = FilesystemServer(mock_registry)

        result = fs.read_text_file("/tmp/test.txt")

        assert result == "extracted"

    def test_extract_text_empty_content(self, mock_registry, mock_result_empty):
        """Test _extract_text returns empty string for empty content."""
        mock_registry.call_tool.return_value = mock_result_empty
        fs = FilesystemServer(mock_registry)

        result = fs._extract_text(mock_result_empty)

        assert result == ""

    def test_extract_text_non_text_content(self, mock_registry):
        """Test _extract_text skips non-text content."""
        result = MCPToolCallResult(
            content=[MCPToolCallContent(type="image", data="base64data")],
            isError=False,
        )
        fs = FilesystemServer(mock_registry)

        extracted = fs._extract_text(result)

        assert extracted == ""

# ============================================================================
# GitServer Tests
# ============================================================================

class TestGitServer:
    """Tests for GitServer wrapper."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'git'."""
        git = GitServer(mock_registry)

        assert git._server_name == "git"
        assert git._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        git = GitServer(mock_registry, server_name="custom-git")

        assert git._server_name == "custom-git"

    def test_status(self, mock_registry, mock_result_text):
        """Test status returns git status output."""
        mock_registry.call_tool.return_value = mock_result_text("On branch main\nnothing to commit")
        git = GitServer(mock_registry)

        result = git.status("/path/to/repo")

        assert result == "On branch main\nnothing to commit"
        mock_registry.call_tool.assert_called_once_with(
            "git", "git_status", {"repo_path": "/path/to/repo"}
        )

    def test_diff_unstaged(self, mock_registry, mock_result_text):
        """Test diff_unstaged returns unstaged diff."""
        mock_registry.call_tool.return_value = mock_result_text("diff --git a/file...")
        git = GitServer(mock_registry)

        result = git.diff_unstaged("/path/to/repo")

        assert result == "diff --git a/file..."
        mock_registry.call_tool.assert_called_once_with(
            "git", "git_diff_unstaged", {"repo_path": "/path/to/repo"}
        )

    def test_diff_staged(self, mock_registry, mock_result_text):
        """Test diff_staged returns staged diff."""
        mock_registry.call_tool.return_value = mock_result_text("staged changes")
        git = GitServer(mock_registry)

        result = git.diff_staged("/path/to/repo")

        assert result == "staged changes"
        mock_registry.call_tool.assert_called_once_with(
            "git", "git_diff_staged", {"repo_path": "/path/to/repo"}
        )

    def test_diff(self, mock_registry, mock_result_text):
        """Test diff with target branch."""
        mock_registry.call_tool.return_value = mock_result_text("diff against main")
        git = GitServer(mock_registry)

        result = git.diff("/path/to/repo", "main")

        assert result == "diff against main"
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_diff",
            {"repo_path": "/path/to/repo", "target": "main"},
        )

    def test_commit(self, mock_registry, mock_result_text):
        """Test commit with message."""
        mock_registry.call_tool.return_value = mock_result_text("[main abc1234] Message")
        git = GitServer(mock_registry)

        result = git.commit("/path/to/repo", "Commit message")

        assert result == "[main abc1234] Message"
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_commit",
            {"repo_path": "/path/to/repo", "message": "Commit message"},
        )

    def test_add(self, mock_registry, mock_result_text):
        """Test add with file list."""
        mock_registry.call_tool.return_value = mock_result_text("Added")
        git = GitServer(mock_registry)

        result = git.add("/path/to/repo", ["file1.py", "file2.py"])

        assert result == "Added"
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_add",
            {"repo_path": "/path/to/repo", "files": ["file1.py", "file2.py"]},
        )

    def test_reset(self, mock_registry, mock_result_text):
        """Test reset unstages all changes."""
        mock_registry.call_tool.return_value = mock_result_text("Reset")
        git = GitServer(mock_registry)

        result = git.reset("/path/to/repo")

        assert result == "Reset"
        mock_registry.call_tool.assert_called_once_with(
            "git", "git_reset", {"repo_path": "/path/to/repo"}
        )

    def test_log_default_count(self, mock_registry, mock_result_text):
        """Test log with default max_count."""
        mock_registry.call_tool.return_value = mock_result_text("commit abc123\n...")
        git = GitServer(mock_registry)

        result = git.log("/path/to/repo")

        assert result == "commit abc123\n..."
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_log",
            {"repo_path": "/path/to/repo", "max_count": 10},
        )

    def test_log_custom_count(self, mock_registry, mock_result_text):
        """Test log with custom max_count."""
        mock_registry.call_tool.return_value = mock_result_text("commit abc123")
        git = GitServer(mock_registry)

        result = git.log("/path/to/repo", max_count=5)

        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_log",
            {"repo_path": "/path/to/repo", "max_count": 5},
        )

    def test_create_branch_without_base(self, mock_registry, mock_result_text):
        """Test create_branch without base branch."""
        mock_registry.call_tool.return_value = mock_result_text("Created branch")
        git = GitServer(mock_registry)

        result = git.create_branch("/path/to/repo", "feature-branch")

        assert result == "Created branch"
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_create_branch",
            {"repo_path": "/path/to/repo", "branch_name": "feature-branch"},
        )

    def test_create_branch_with_base(self, mock_registry, mock_result_text):
        """Test create_branch with base branch."""
        mock_registry.call_tool.return_value = mock_result_text("Created branch")
        git = GitServer(mock_registry)

        result = git.create_branch("/path/to/repo", "feature", base_branch="develop")

        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_create_branch",
            {
                "repo_path": "/path/to/repo",
                "branch_name": "feature",
                "base_branch": "develop",
            },
        )

    def test_checkout(self, mock_registry, mock_result_text):
        """Test checkout branch."""
        mock_registry.call_tool.return_value = mock_result_text("Switched to branch")
        git = GitServer(mock_registry)

        result = git.checkout("/path/to/repo", "main")

        assert result == "Switched to branch"
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_checkout",
            {"repo_path": "/path/to/repo", "branch_name": "main"},
        )

    def test_show(self, mock_registry, mock_result_text):
        """Test show commit details."""
        mock_registry.call_tool.return_value = mock_result_text("commit details")
        git = GitServer(mock_registry)

        result = git.show("/path/to/repo", "abc123")

        assert result == "commit details"
        mock_registry.call_tool.assert_called_once_with(
            "git",
            "git_show",
            {"repo_path": "/path/to/repo", "revision": "abc123"},
        )

    def test_branches(self, mock_registry, mock_result_text):
        """Test branches returns parsed list."""
        mock_registry.call_tool.return_value = mock_result_text("  main\n* feature\n  develop")
        git = GitServer(mock_registry)

        result = git.branches("/path/to/repo")

        assert result == ["main", "feature", "develop"]
        mock_registry.call_tool.assert_called_once_with(
            "git", "git_branch", {"repo_path": "/path/to/repo"}
        )

    def test_branches_empty(self, mock_registry, mock_result_text):
        """Test branches with empty result."""
        mock_registry.call_tool.return_value = mock_result_text("")
        git = GitServer(mock_registry)

        result = git.branches("/path/to/repo")

        assert result == []

# ============================================================================
# MemoryServer Tests
# ============================================================================

class TestMemoryServer:
    """Tests for MemoryServer wrapper."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'memory'."""
        memory = MemoryServer(mock_registry)

        assert memory._server_name == "memory"
        assert memory._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        memory = MemoryServer(mock_registry, server_name="custom-memory")

        assert memory._server_name == "custom-memory"

    def test_create_entities_with_objects(self, mock_registry, mock_result_text):
        """Test create_entities with Entity objects."""
        mock_registry.call_tool.return_value = mock_result_text("Created")
        memory = MemoryServer(mock_registry)
        entities = [
            Entity("Alice", "person", ["Engineer"]),
            Entity("Bob", "person"),
        ]

        result = memory.create_entities(entities)

        assert result == "Created"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "create_entities",
            {
                "entities": [
                    {"name": "Alice", "entityType": "person", "observations": ["Engineer"]},
                    {"name": "Bob", "entityType": "person", "observations": []},
                ]
            },
        )

    def test_create_entities_with_dicts(self, mock_registry, mock_result_text):
        """Test create_entities with raw dicts."""
        mock_registry.call_tool.return_value = mock_result_text("Created")
        memory = MemoryServer(mock_registry)
        entities = [
            {"name": "Test", "entityType": "test", "observations": []},
        ]

        result = memory.create_entities(entities)

        assert result == "Created"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "create_entities",
            {"entities": entities},
        )

    def test_create_relations_with_objects(self, mock_registry, mock_result_text):
        """Test create_relations with Relation objects."""
        mock_registry.call_tool.return_value = mock_result_text("Created")
        memory = MemoryServer(mock_registry)
        relations = [
            Relation("Alice", "Project", "works_on"),
        ]

        result = memory.create_relations(relations)

        assert result == "Created"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "create_relations",
            {
                "relations": [
                    {"from": "Alice", "to": "Project", "relationType": "works_on"},
                ]
            },
        )

    def test_create_relations_with_dicts(self, mock_registry, mock_result_text):
        """Test create_relations with raw dicts."""
        mock_registry.call_tool.return_value = mock_result_text("Created")
        memory = MemoryServer(mock_registry)
        relations = [
            {"from": "A", "to": "B", "relationType": "knows"},
        ]

        result = memory.create_relations(relations)

        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "create_relations",
            {"relations": relations},
        )

    def test_add_observations(self, mock_registry, mock_result_text):
        """Test add_observations delegates correctly."""
        mock_registry.call_tool.return_value = mock_result_text("Added")
        memory = MemoryServer(mock_registry)
        observations = [
            {"entityName": "Alice", "contents": ["New fact"]},
        ]

        result = memory.add_observations(observations)

        assert result == "Added"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "add_observations",
            {"observations": observations},
        )

    def test_delete_entities(self, mock_registry, mock_result_text):
        """Test delete_entities delegates correctly."""
        mock_registry.call_tool.return_value = mock_result_text("Deleted")
        memory = MemoryServer(mock_registry)

        result = memory.delete_entities(["Alice", "Bob"])

        assert result == "Deleted"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "delete_entities",
            {"entityNames": ["Alice", "Bob"]},
        )

    def test_delete_observations(self, mock_registry, mock_result_text):
        """Test delete_observations delegates correctly."""
        mock_registry.call_tool.return_value = mock_result_text("Deleted")
        memory = MemoryServer(mock_registry)
        deletions = [
            {"entityName": "Alice", "observations": ["Old fact"]},
        ]

        result = memory.delete_observations(deletions)

        assert result == "Deleted"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "delete_observations",
            {"deletions": deletions},
        )

    def test_delete_relations_with_objects(self, mock_registry, mock_result_text):
        """Test delete_relations with Relation objects."""
        mock_registry.call_tool.return_value = mock_result_text("Deleted")
        memory = MemoryServer(mock_registry)
        relations = [Relation("A", "B", "knows")]

        result = memory.delete_relations(relations)

        assert result == "Deleted"
        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "delete_relations",
            {"relations": [{"from": "A", "to": "B", "relationType": "knows"}]},
        )

    def test_delete_relations_with_dicts(self, mock_registry, mock_result_text):
        """Test delete_relations with raw dicts."""
        mock_registry.call_tool.return_value = mock_result_text("Deleted")
        memory = MemoryServer(mock_registry)
        relations = [{"from": "A", "to": "B", "relationType": "knows"}]

        result = memory.delete_relations(relations)

        mock_registry.call_tool.assert_called_once_with(
            "memory",
            "delete_relations",
            {"relations": relations},
        )

    def test_read_graph(self, mock_registry, mock_result_text):
        """Test read_graph returns parsed graph."""
        graph = {"entities": [{"name": "Alice"}], "relations": []}
        mock_registry.call_tool.return_value = mock_result_text(json.dumps(graph))
        memory = MemoryServer(mock_registry)

        result = memory.read_graph()

        assert result == graph
        mock_registry.call_tool.assert_called_once_with("memory", "read_graph", {})

    def test_read_graph_empty(self, mock_registry, mock_result_empty):
        """Test read_graph with empty result."""
        mock_registry.call_tool.return_value = mock_result_empty
        memory = MemoryServer(mock_registry)

        result = memory.read_graph()

        assert result == {"entities": [], "relations": []}

    def test_search_nodes(self, mock_registry, mock_result_text):
        """Test search_nodes returns entity list."""
        data = {"entities": [{"name": "Alice"}, {"name": "Bob"}]}
        mock_registry.call_tool.return_value = mock_result_text(json.dumps(data))
        memory = MemoryServer(mock_registry)

        result = memory.search_nodes("Alice")

        assert result == [{"name": "Alice"}, {"name": "Bob"}]
        mock_registry.call_tool.assert_called_once_with(
            "memory", "search_nodes", {"query": "Alice"}
        )

    def test_search_nodes_empty(self, mock_registry, mock_result_empty):
        """Test search_nodes with no matches."""
        mock_registry.call_tool.return_value = mock_result_empty
        memory = MemoryServer(mock_registry)

        result = memory.search_nodes("nonexistent")

        assert result == []

    def test_open_nodes(self, mock_registry, mock_result_text):
        """Test open_nodes returns entity details."""
        data = {"entities": [{"name": "Alice", "entityType": "person"}]}
        mock_registry.call_tool.return_value = mock_result_text(json.dumps(data))
        memory = MemoryServer(mock_registry)

        result = memory.open_nodes(["Alice"])

        assert result == [{"name": "Alice", "entityType": "person"}]
        mock_registry.call_tool.assert_called_once_with(
            "memory", "open_nodes", {"names": ["Alice"]}
        )

    def test_open_nodes_empty(self, mock_registry, mock_result_empty):
        """Test open_nodes with no matches."""
        mock_registry.call_tool.return_value = mock_result_empty
        memory = MemoryServer(mock_registry)

        result = memory.open_nodes(["nonexistent"])

        assert result == []

# ============================================================================
# Cross-Wrapper Tests
# ============================================================================

class TestCrossWrapperBehavior:
    """Tests for behavior common across all wrappers."""

    def test_wrappers_share_registry(self, mock_registry):
        """Test multiple wrappers can share same registry."""
        fs = FilesystemServer(mock_registry)
        git = GitServer(mock_registry)
        memory = MemoryServer(mock_registry)

        assert fs._registry is mock_registry
        assert git._registry is mock_registry
        assert memory._registry is mock_registry

    def test_wrappers_different_server_names(self, mock_registry):
        """Test wrappers use correct server names."""
        fs = FilesystemServer(mock_registry, server_name="fs1")
        git = GitServer(mock_registry, server_name="git1")
        memory = MemoryServer(mock_registry, server_name="mem1")

        assert fs._server_name == "fs1"
        assert git._server_name == "git1"
        assert memory._server_name == "mem1"

    def test_error_propagation(self, mock_registry):
        """Test errors from registry propagate through wrappers."""
        mock_registry.call_tool.side_effect = Exception("Connection failed")
        fs = FilesystemServer(mock_registry)

        with pytest.raises(Exception) as exc_info:
            fs.read_text_file("/tmp/test.txt")

        assert "Connection failed" in str(exc_info.value)

    def test_result_with_error_flag(self, mock_registry):
        """Test handling of result with isError=True."""
        error_result = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Error message")],
            isError=True,
        )
        mock_registry.call_tool.return_value = error_result
        fs = FilesystemServer(mock_registry)

        # Wrapper extracts text regardless of error flag
        result = fs.read_text_file("/tmp/test.txt")

        assert result == "Error message"
