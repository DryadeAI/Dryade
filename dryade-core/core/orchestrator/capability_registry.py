"""Unified capability registry for self-modification, MCP, and agent capabilities.

Phase 115.2: Provides a searchable catalog of all capabilities the orchestrator
can invoke or propose. Distinct from core/plugin_capabilities/ which handles
inter-plugin discovery -- this registry is for orchestrator self-modification
and agency capabilities.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = [
    "CapabilityEntry",
    "CapabilityRegistry",
    "get_capability_registry",
]

@dataclass
class CapabilityEntry:
    """A single capability that can be searched and invoked."""

    name: str
    source: str  # "self_mod" | "mcp" | "agent" | "factory"
    category: (
        str  # "server_management" | "tool_creation" | "config" | "search" | "agent_management"
    )
    description: str
    description_short: str  # Compact version for 7B models
    server: str | None = None  # MCP server name if source=mcp
    parameters: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

class CapabilityRegistry:
    """Unified searchable catalog of all self-modification capabilities.

    Distinct from core/plugin_capabilities/ which handles inter-plugin discovery.
    This registry is for orchestrator self-modification and agency capabilities.
    """

    def __init__(self):
        self._entries: dict[str, CapabilityEntry] = {}  # name -> entry
        self._by_source: dict[str, list[str]] = {}  # source -> names
        self._by_category: dict[str, list[str]] = {}  # category -> names
        self._lock = threading.RLock()
        # Phase 167: TTL cache to prevent repeated full rebuilds within ReAct loops
        self._last_refresh_time: float = 0.0
        self._refresh_ttl_seconds: float = 30.0

    def register(self, entry: CapabilityEntry) -> None:
        """Register a capability entry.

        If an entry with the same name exists, it is replaced.
        """
        with self._lock:
            # Clean up old entry if replacing
            if entry.name in self._entries:
                self._remove_from_indexes(entry.name)

            self._entries[entry.name] = entry

            # Index by source
            if entry.source not in self._by_source:
                self._by_source[entry.source] = []
            if entry.name not in self._by_source[entry.source]:
                self._by_source[entry.source].append(entry.name)

            # Index by category
            if entry.category not in self._by_category:
                self._by_category[entry.category] = []
            if entry.name not in self._by_category[entry.category]:
                self._by_category[entry.category].append(entry.name)

    def unregister(self, name: str) -> None:
        """Remove a capability entry by name."""
        with self._lock:
            if name not in self._entries:
                return
            self._remove_from_indexes(name)
            del self._entries[name]

    def _remove_from_indexes(self, name: str) -> None:
        """Remove a name from source and category indexes. Must hold lock."""
        entry = self._entries.get(name)
        if not entry:
            return
        if entry.source in self._by_source:
            self._by_source[entry.source] = [n for n in self._by_source[entry.source] if n != name]
        if entry.category in self._by_category:
            self._by_category[entry.category] = [
                n for n in self._by_category[entry.category] if n != name
            ]

    def search(
        self,
        query: str,
        source_filter: str | None = None,
        category_filter: str | None = None,
        limit: int = 20,
    ) -> list[CapabilityEntry]:
        """Search capabilities by regex on name + description + tags.

        Args:
            query: Regex pattern to match against name, description, and tags.
            source_filter: Optional filter by source ("self_mod", "mcp", "agent").
            category_filter: Optional filter by category.
            limit: Maximum number of results.

        Returns:
            List of matching CapabilityEntry objects.
        """
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            # Invalid regex, treat as literal
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        with self._lock:
            candidates = list(self._entries.values())

        # Apply filters
        if source_filter:
            candidates = [e for e in candidates if e.source == source_filter]
        if category_filter:
            candidates = [e for e in candidates if e.category == category_filter]

        # Match against name, description, and tags
        results = []
        for entry in candidates:
            if pattern.search(entry.name):
                results.append(entry)
            elif pattern.search(entry.description):
                results.append(entry)
            elif any(pattern.search(tag) for tag in entry.tags):
                results.append(entry)

        return results[:limit]

    def list_all(self, category: str | None = None) -> list[CapabilityEntry]:
        """List all registered capabilities, optionally filtered by category.

        Args:
            category: Optional category filter.

        Returns:
            List of all matching CapabilityEntry objects.
        """
        with self._lock:
            if category:
                names = self._by_category.get(category, [])
                return [self._entries[n] for n in names if n in self._entries]
            return list(self._entries.values())

    def refresh_from_sources(self, force: bool = False) -> int:
        """Refresh registry from all known capability sources.

        Phase 167: Added 30s TTL cache to prevent expensive full-registry rebuilds
        within ReAct loops. Use force=True to bypass TTL for tests or explicit refresh.

        Sources:
        - Self-mod tools from SELF_MOD_TOOL_NAMES
        - MCP tools from ToolIndex
        - Agents from AgentRegistry

        Returns:
            Total number of registered capabilities.
        """
        # TTL cache: skip rebuild if refreshed recently (within 30s)
        now = time.monotonic()
        if not force and now - self._last_refresh_time < self._refresh_ttl_seconds:
            return len(self._entries)  # Return cached count without rebuilding

        count = 0

        # 1. Register self-mod tools
        try:
            from core.orchestrator.self_mod_tools import SELF_MOD_TOOL_NAMES

            # Phase 167: Updated for consolidated tool names (create replaces
            # self_improve/create_agent/create_tool; memory_delete added)
            _SELF_MOD_CATEGORIES = {
                "create": "agent_management",
                "modify_config": "config",
                "add_mcp_server": "server_management",
                "remove_mcp_server": "server_management",
                "configure_mcp_server": "server_management",
                "search_capabilities": "search",
                "memory_insert": "memory_management",
                "memory_replace": "memory_management",
                "memory_rethink": "memory_management",
                "memory_search": "memory_management",
                "memory_delete": "memory_management",
            }
            for name in SELF_MOD_TOOL_NAMES:
                self.register(
                    CapabilityEntry(
                        name=name,
                        source="self_mod",
                        category=_SELF_MOD_CATEGORIES.get(name, "config"),
                        description=f"Self-modification tool: {name}",
                        description_short=name,
                        tags=["self-mod", name.replace("_", " ")],
                    )
                )
                count += 1
        except ImportError:
            logger.warning("[CAPABILITY_REGISTRY] Could not import self_mod_tools")

        # 2. Register MCP tools from ToolIndex
        try:
            from core.mcp.tool_index import get_tool_index

            tool_index = get_tool_index()
            with tool_index._lock:
                for entry in tool_index._entries.values():
                    self.register(
                        CapabilityEntry(
                            name=f"mcp:{entry.server}:{entry.name}",
                            source="mcp",
                            category="tool_creation",
                            description=entry.description_preview,
                            description_short=entry.description_preview[:80],
                            server=entry.server,
                            parameters={"input_schema_keys": entry.input_schema_keys},
                            tags=["mcp", entry.server, entry.name],
                        )
                    )
                    count += 1
        except ImportError:
            logger.warning("[CAPABILITY_REGISTRY] Could not import tool_index")

        # 3. Register agents from AgentRegistry
        try:
            from core.adapters.registry import get_registry

            registry = get_registry()
            for card in registry.list_agents():
                self.register(
                    CapabilityEntry(
                        name=f"agent:{card.name}",
                        source="agent",
                        category="agent_management",
                        description=card.description,
                        description_short=card.description[:80] if card.description else card.name,
                        parameters={"framework": str(card.framework)},
                        tags=["agent", card.name] + card.skills,
                    )
                )
                count += 1
        except ImportError:
            logger.warning("[CAPABILITY_REGISTRY] Could not import agent registry")

        # 4. Register factory-created artifacts (Phase 119.4)
        try:
            from core.factory.models import ArtifactStatus
            from core.factory.registry import FactoryRegistry

            factory_reg = FactoryRegistry()
            for artifact in factory_reg.list_all(status=ArtifactStatus.ACTIVE):
                desc = (
                    artifact.config_json.get("description", artifact.name)
                    if artifact.config_json
                    else artifact.name
                )
                self.register(
                    CapabilityEntry(
                        name=f"factory:{artifact.name}",
                        source="factory",
                        category=artifact.artifact_type.value
                        if artifact.artifact_type
                        else "agent",
                        description=desc,
                        description_short=desc[:80],
                        tags=list(artifact.tags or []) + ["factory-created"],
                    )
                )
                count += 1
        except ImportError:
            logger.debug("[CAPABILITY_REGISTRY] Factory registry not available")
        except Exception:
            logger.warning("[CAPABILITY_REGISTRY] Error loading factory artifacts", exc_info=True)

        # Update TTL timestamp after successful rebuild
        self._last_refresh_time = time.monotonic()

        logger.info(f"[CAPABILITY_REGISTRY] Refreshed: {count} capabilities registered")
        return count

# Singleton pattern with double-checked locking
_capability_registry: CapabilityRegistry | None = None
_capability_registry_lock = threading.Lock()

def get_capability_registry() -> CapabilityRegistry:
    """Get or create singleton CapabilityRegistry instance."""
    global _capability_registry
    if _capability_registry is None:
        with _capability_registry_lock:
            if _capability_registry is None:
                _capability_registry = CapabilityRegistry()
    return _capability_registry

def reset_capability_registry() -> None:
    """Reset the singleton capability registry (for testing)."""
    global _capability_registry
    _capability_registry = None
