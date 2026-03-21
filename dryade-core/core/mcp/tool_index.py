"""MCP Tool Index - Lightweight manifest for tool discovery.

Provides searchable index of MCP tools without loading full schemas.
Designed for scale: 1000+ tools with minimal context overhead.

Features:
- Lightweight ToolEntry with name, description hash, server, fingerprint
- Regex search on tool name and description
- Detail levels: name_only, summary, full (on-demand schema loading)
- Lazy population from MCPRegistry
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.mcp.protocol import MCPTool

logger = logging.getLogger(__name__)

class SearchMode(str, Enum):
    """Tool search mode."""

    REGEX = "regex"  # Regular expression on name and description

class DetailLevel(str, Enum):
    """Response detail levels for search results."""

    NAME_ONLY = "name_only"  # Just tool names - minimal tokens
    SUMMARY = "summary"  # Name + truncated description (100 chars)
    FULL = "full"  # Complete tool schema - high token cost

@dataclass
class ToolEntry:
    """Lightweight tool manifest entry.

    Designed for minimal memory footprint while enabling fast search.
    Full schema loaded on-demand via get_full_schema().
    """

    name: str
    server: str
    description_hash: str  # SHA256 of description for change detection
    description_preview: str  # First 100 chars of description
    fingerprint: str  # Unique identifier: server:name:hash
    input_schema_keys: list[str] = field(default_factory=list)  # Top-level param names

    @classmethod
    def from_mcp_tool(cls, tool: MCPTool, server: str) -> ToolEntry:
        """Create ToolEntry from MCPTool."""
        desc = tool.description or ""
        desc_hash = hashlib.sha256(desc.encode()).hexdigest()[:16]
        preview = desc[:100] + "..." if len(desc) > 100 else desc

        # Extract top-level input schema keys
        input_keys = []
        if tool.inputSchema and hasattr(tool.inputSchema, "properties"):
            input_keys = list(tool.inputSchema.properties.keys())

        fingerprint = f"{server}:{tool.name}:{desc_hash}"

        return cls(
            name=tool.name,
            server=server,
            description_hash=desc_hash,
            description_preview=preview,
            fingerprint=fingerprint,
            input_schema_keys=input_keys,
        )

    def to_dict(self, detail: DetailLevel) -> dict[str, Any]:
        """Convert to dict at specified detail level."""
        if detail == DetailLevel.NAME_ONLY:
            return {"name": self.name, "server": self.server}
        elif detail == DetailLevel.SUMMARY:
            return {
                "name": self.name,
                "server": self.server,
                "description": self.description_preview,
                "params": self.input_schema_keys,
            }
        else:  # FULL - caller must load schema separately
            return {
                "name": self.name,
                "server": self.server,
                "description": self.description_preview,
                "params": self.input_schema_keys,
                "fingerprint": self.fingerprint,
            }

@dataclass
class SearchResult:
    """Tool search result with relevance score."""

    entry: ToolEntry
    score: float = 1.0  # Relevance score (0-1)
    match_type: str = "exact"  # exact, prefix, regex, semantic

class ToolIndex:
    """Searchable index of MCP tools.

    Maintains lightweight manifest entries for fast discovery.
    Integrates with MCPRegistry for on-demand schema loading.

    Usage:
        index = ToolIndex()
        index.populate_from_registry()  # Load from running servers

        # Search tools
        results = index.search("model.*edit")

        # Get full schema when needed
        full_tool = index.get_full_schema("search_files")
    """

    def __init__(self) -> None:
        """Initialize empty tool index."""
        self._entries: dict[str, ToolEntry] = {}  # fingerprint -> entry
        self._by_name: dict[str, list[str]] = {}  # name -> fingerprints
        self._by_server: dict[str, list[str]] = {}  # server -> fingerprints
        self._lock = threading.RLock()
        self._populated = False

    def add_entry(self, entry: ToolEntry) -> None:
        """Add or update a tool entry."""
        with self._lock:
            self._entries[entry.fingerprint] = entry

            # Index by name
            if entry.name not in self._by_name:
                self._by_name[entry.name] = []
            if entry.fingerprint not in self._by_name[entry.name]:
                self._by_name[entry.name].append(entry.fingerprint)

            # Index by server
            if entry.server not in self._by_server:
                self._by_server[entry.server] = []
            if entry.fingerprint not in self._by_server[entry.server]:
                self._by_server[entry.server].append(entry.fingerprint)

    def remove_entry(self, fingerprint: str) -> bool:
        """Remove entry by fingerprint. Returns True if found."""
        with self._lock:
            if fingerprint not in self._entries:
                return False

            entry = self._entries.pop(fingerprint)

            # Clean up name index
            if entry.name in self._by_name:
                self._by_name[entry.name] = [
                    fp for fp in self._by_name[entry.name] if fp != fingerprint
                ]
                if not self._by_name[entry.name]:
                    del self._by_name[entry.name]

            # Clean up server index
            if entry.server in self._by_server:
                self._by_server[entry.server] = [
                    fp for fp in self._by_server[entry.server] if fp != fingerprint
                ]
                if not self._by_server[entry.server]:
                    del self._by_server[entry.server]

            return True

    def populate_from_registry(self, registry: Any = None) -> int:
        """Populate index from MCPRegistry.

        Args:
            registry: Optional MCPRegistry instance. Uses singleton if None.

        Returns:
            Number of tools indexed.
        """
        if registry is None:
            from core.mcp import get_registry

            registry = get_registry()

        count = 0
        all_tools = registry.list_all_tools()

        for server, tools in all_tools.items():
            for tool in tools:
                entry = ToolEntry.from_mcp_tool(tool, server)
                self.add_entry(entry)
                count += 1

        self._populated = True
        logger.info(f"Tool index populated with {count} tools from {len(all_tools)} servers")
        return count

    def search(
        self,
        query: str,
        server_filter: str | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Search tools by regex on name and description.

        Args:
            query: Regex pattern to match against tool names and descriptions
            server_filter: Optional server name to filter results
            limit: Maximum results to return

        Returns:
            List of SearchResult ordered by relevance.
        """
        with self._lock:
            entries = list(self._entries.values())

        # Apply server filter first
        if server_filter:
            entries = [e for e in entries if e.server == server_filter]

        results = self._search_by_regex(query, entries)

        # Sort by score descending, limit results
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _search_by_regex(self, pattern: str, entries: list[ToolEntry]) -> list[SearchResult]:
        """Search by regex on name and description."""
        results = []

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            return []

        for entry in entries:
            name_match = regex.search(entry.name)
            desc_match = regex.search(entry.description_preview)

            if name_match:
                results.append(SearchResult(entry, score=0.9, match_type="regex_name"))
            elif desc_match:
                results.append(SearchResult(entry, score=0.6, match_type="regex_desc"))

        return results

    def remove_by_server(self, server: str) -> int:
        """Remove all tool entries for a given server atomically.

        Acquires the lock once and removes all entries in a batch to
        prevent partial state during concurrent access.

        Args:
            server: Server name whose tools should be removed.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            fingerprints = list(self._by_server.get(server, []))
            count = 0
            for fp in fingerprints:
                if fp in self._entries:
                    entry = self._entries.pop(fp)

                    # Clean up name index
                    if entry.name in self._by_name:
                        self._by_name[entry.name] = [
                            f for f in self._by_name[entry.name] if f != fp
                        ]
                        if not self._by_name[entry.name]:
                            del self._by_name[entry.name]

                    count += 1

            # Clean up server index
            if server in self._by_server:
                del self._by_server[server]

            return count

    def get_by_name(self, name: str) -> list[ToolEntry]:
        """Get all entries with exact name match."""
        with self._lock:
            fingerprints = self._by_name.get(name, [])
            return [self._entries[fp] for fp in fingerprints if fp in self._entries]

    def get_by_server(self, server: str) -> list[ToolEntry]:
        """Get all entries from a specific server."""
        with self._lock:
            fingerprints = self._by_server.get(server, [])
            return [self._entries[fp] for fp in fingerprints if fp in self._entries]

    def get_full_schema(self, tool_name: str, server: str | None = None) -> MCPTool | None:
        """Load full tool schema on-demand from registry.

        Args:
            tool_name: Tool name to load
            server: Optional server name (auto-detect if None)

        Returns:
            Full MCPTool with schema, or None if not found.
        """
        from core.mcp import get_registry

        registry = get_registry()

        if server:
            tools = registry.list_tools(server)
            for tool in tools:
                if tool.name == tool_name:
                    return tool
        else:
            # Search all running servers
            result = registry.find_tool(tool_name)
            if result:
                _, tool = result
                return tool

        return None

    def to_manifest(self, detail: DetailLevel = DetailLevel.SUMMARY) -> list[dict[str, Any]]:
        """Export index as manifest at specified detail level."""
        with self._lock:
            return [entry.to_dict(detail) for entry in self._entries.values()]

    @property
    def size(self) -> int:
        """Number of tools in index."""
        return len(self._entries)

    @property
    def servers(self) -> list[str]:
        """List of servers with indexed tools."""
        return list(self._by_server.keys())

    @property
    def is_populated(self) -> bool:
        """Whether index has been populated from registry."""
        return self._populated

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
            self._by_name.clear()
            self._by_server.clear()
            self._populated = False

# Singleton pattern
_tool_index: ToolIndex | None = None
_tool_index_lock = threading.Lock()

def get_tool_index() -> ToolIndex:
    """Get or create singleton ToolIndex instance."""
    global _tool_index
    if _tool_index is None:
        with _tool_index_lock:
            if _tool_index is None:
                _tool_index = ToolIndex()
    return _tool_index

def reset_tool_index() -> None:
    """Reset the singleton tool index (for testing)."""
    global _tool_index
    if _tool_index is not None:
        _tool_index.clear()
    _tool_index = None
