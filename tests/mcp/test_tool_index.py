"""Tests for MCP Tool Index."""

from unittest.mock import Mock

from core.mcp.protocol import MCPTool, MCPToolInputSchema
from core.mcp.tool_index import (
    DetailLevel,
    SearchResult,
    ToolEntry,
    ToolIndex,
    get_tool_index,
    reset_tool_index,
)

class TestToolEntry:
    """Test ToolEntry dataclass."""

    def test_from_mcp_tool(self):
        """Create ToolEntry from MCPTool."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool for testing purposes",
            inputSchema=MCPToolInputSchema(
                properties={"arg1": {"type": "string"}, "arg2": {"type": "int"}}
            ),
        )

        entry = ToolEntry.from_mcp_tool(tool, "test_server")

        assert entry.name == "test_tool"
        assert entry.server == "test_server"
        assert len(entry.description_hash) == 16  # SHA256 truncated
        assert entry.description_preview == "A test tool for testing purposes"
        assert "arg1" in entry.input_schema_keys
        assert "arg2" in entry.input_schema_keys
        assert entry.fingerprint.startswith("test_server:test_tool:")

    def test_long_description_preview_truncated(self):
        """Long descriptions should be truncated in preview."""
        long_desc = "x" * 200
        tool = MCPTool(name="long_tool", description=long_desc, inputSchema=MCPToolInputSchema())

        entry = ToolEntry.from_mcp_tool(tool, "server")

        assert len(entry.description_preview) == 103  # 100 + "..."
        assert entry.description_preview.endswith("...")

    def test_to_dict_name_only(self):
        """NAME_ONLY detail level returns minimal data."""
        tool = MCPTool(name="tool", description="desc", inputSchema=MCPToolInputSchema())
        entry = ToolEntry.from_mcp_tool(tool, "server")

        result = entry.to_dict(DetailLevel.NAME_ONLY)

        assert result == {"name": "tool", "server": "server"}

    def test_to_dict_summary(self):
        """SUMMARY detail level includes description and params."""
        tool = MCPTool(
            name="tool",
            description="desc",
            inputSchema=MCPToolInputSchema(properties={"p1": {}}),
        )
        entry = ToolEntry.from_mcp_tool(tool, "server")

        result = entry.to_dict(DetailLevel.SUMMARY)

        assert result["name"] == "tool"
        assert result["description"] == "desc"
        assert "p1" in result["params"]

    def test_to_dict_full(self):
        """FULL detail level includes fingerprint."""
        tool = MCPTool(name="tool", description="desc", inputSchema=MCPToolInputSchema())
        entry = ToolEntry.from_mcp_tool(tool, "server")

        result = entry.to_dict(DetailLevel.FULL)

        assert result["name"] == "tool"
        assert "fingerprint" in result

class TestToolIndex:
    """Test ToolIndex search and management."""

    def setup_method(self):
        """Create fresh index for each test."""
        self.index = ToolIndex()
        self._populate_test_data()

    def _populate_test_data(self):
        """Add test entries to index."""
        tools = [
            ("capella_open", "mcp-capella", "Open a Capella model session"),
            ("capella_close", "mcp-capella", "Close a Capella model session"),
            ("capella_list", "mcp-capella", "List elements in Capella model"),
            ("memory_store", "mcp-memory", "Store data in memory"),
            ("memory_recall", "mcp-memory", "Recall data from memory"),
            ("filesystem_read", "mcp-filesystem", "Read a file from disk"),
        ]

        for name, server, desc in tools:
            tool = MCPTool(name=name, description=desc, inputSchema=MCPToolInputSchema())
            entry = ToolEntry.from_mcp_tool(tool, server)
            self.index.add_entry(entry)

    def test_search_by_regex_name(self):
        """Regex search matches on name."""
        results = self.index.search("capella_.*")

        assert len(results) == 3
        assert all(r.match_type == "regex_name" for r in results)

    def test_search_by_regex_description(self):
        """Regex search matches on description."""
        results = self.index.search("Capella model")

        assert len(results) >= 2  # "Open a Capella model" and "List elements in Capella model"

    def test_search_with_server_filter(self):
        """Server filter restricts results."""
        results = self.index.search(".*", server_filter="mcp-memory")
        assert len(results) == 2
        assert all(r.entry.server == "mcp-memory" for r in results)

        # Server filter with regex search
        results = self.index.search("memory", server_filter="mcp-memory")
        assert len(results) == 2
        assert all(r.entry.server == "mcp-memory" for r in results)

    def test_search_limit(self):
        """Search respects limit parameter."""
        results = self.index.search(".*", limit=2)

        assert len(results) == 2

    def test_search_invalid_regex(self):
        """Invalid regex returns empty results."""
        results = self.index.search("[invalid")

        assert results == []

    def test_get_by_name(self):
        """Get entries by exact name."""
        entries = self.index.get_by_name("capella_open")

        assert len(entries) == 1
        assert entries[0].name == "capella_open"

    def test_get_by_name_not_found(self):
        """Get by name returns empty for unknown name."""
        entries = self.index.get_by_name("nonexistent")

        assert entries == []

    def test_get_by_server(self):
        """Get all entries from a server."""
        entries = self.index.get_by_server("mcp-capella")

        assert len(entries) == 3
        assert all(e.server == "mcp-capella" for e in entries)

    def test_get_by_server_not_found(self):
        """Get by server returns empty for unknown server."""
        entries = self.index.get_by_server("nonexistent")

        assert entries == []

    def test_remove_entry(self):
        """Remove entry by fingerprint."""
        entries = self.index.get_by_name("capella_open")
        fingerprint = entries[0].fingerprint

        result = self.index.remove_entry(fingerprint)

        assert result is True
        assert self.index.get_by_name("capella_open") == []

    def test_remove_nonexistent_entry(self):
        """Remove returns False for missing entry."""
        result = self.index.remove_entry("nonexistent:fingerprint:hash")
        assert result is False

    def test_to_manifest(self):
        """Export as manifest."""
        manifest = self.index.to_manifest(DetailLevel.NAME_ONLY)

        assert len(manifest) == 6
        assert all("name" in entry for entry in manifest)
        assert all("server" in entry for entry in manifest)

    def test_size_property(self):
        """Size returns tool count."""
        assert self.index.size == 6

    def test_servers_property(self):
        """Servers returns unique server list."""
        servers = self.index.servers

        assert len(servers) == 3
        assert "mcp-capella" in servers
        assert "mcp-memory" in servers
        assert "mcp-filesystem" in servers

    def test_is_populated_property(self):
        """Is populated property tracks population status."""
        assert self.index.is_populated is False

    def test_clear(self):
        """Clear empties the index."""
        self.index.clear()

        assert self.index.size == 0
        assert self.index.servers == []

class TestToolIndexPopulation:
    """Test ToolIndex population from registry."""

    def test_populate_from_registry(self):
        """Populate index from MCPRegistry via explicit registry parameter."""
        mock_registry = Mock()
        mock_registry.list_all_tools.return_value = {
            "server1": [
                MCPTool(name="tool1", description="desc1", inputSchema=MCPToolInputSchema()),
                MCPTool(name="tool2", description="desc2", inputSchema=MCPToolInputSchema()),
            ],
            "server2": [
                MCPTool(name="tool3", description="desc3", inputSchema=MCPToolInputSchema()),
            ],
        }

        index = ToolIndex()
        count = index.populate_from_registry(registry=mock_registry)

        assert count == 3
        assert index.size == 3
        assert "server1" in index.servers
        assert "server2" in index.servers
        assert index.is_populated is True

    def test_populate_with_empty_registry(self):
        """Populate with empty registry returns zero count."""
        mock_registry = Mock()
        mock_registry.list_all_tools.return_value = {}

        index = ToolIndex()
        count = index.populate_from_registry(registry=mock_registry)

        assert count == 0
        assert index.size == 0
        assert index.is_populated is True

class TestToolIndexSingleton:
    """Test singleton pattern."""

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_tool_index()

    def test_get_tool_index_returns_singleton(self):
        """get_tool_index returns same instance."""
        # Reset singleton for test
        reset_tool_index()

        index1 = get_tool_index()
        index2 = get_tool_index()

        assert index1 is index2

    def test_reset_tool_index(self):
        """reset_tool_index clears the singleton."""
        index1 = get_tool_index()
        reset_tool_index()
        index2 = get_tool_index()

        assert index1 is not index2

class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_defaults(self):
        """SearchResult has correct defaults."""
        tool = MCPTool(name="test", description="desc", inputSchema=MCPToolInputSchema())
        entry = ToolEntry.from_mcp_tool(tool, "server")

        result = SearchResult(entry=entry)

        assert result.score == 1.0
        assert result.match_type == "exact"

    def test_search_result_custom_values(self):
        """SearchResult accepts custom values."""
        tool = MCPTool(name="test", description="desc", inputSchema=MCPToolInputSchema())
        entry = ToolEntry.from_mcp_tool(tool, "server")

        result = SearchResult(entry=entry, score=0.5, match_type="contains")

        assert result.score == 0.5
        assert result.match_type == "contains"
