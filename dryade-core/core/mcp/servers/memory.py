"""Memory MCP Server wrapper.

Provides typed Python interface for @modelcontextprotocol/server-memory
knowledge graph operations for persistent agent memory.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

class Entity:
    """Knowledge graph entity.

    Represents a node in the memory knowledge graph with a name,
    type, and associated observations (facts).

    Example:
        >>> entity = Entity(
        ...     name="ProjectDryade",
        ...     entity_type="project",
        ...     observations=["Python project", "Uses LLM agents"]
        ... )
        >>> entity.to_dict()
        {'name': 'ProjectDryade', 'entityType': 'project',
         'observations': ['Python project', 'Uses LLM agents']}
    """

    def __init__(
        self,
        name: str,
        entity_type: str,
        observations: list[str] | None = None,
    ) -> None:
        """Initialize an Entity.

        Args:
            name: Unique name for the entity.
            entity_type: Type/category of the entity.
            observations: List of facts/observations about the entity.
        """
        self.name = name
        self.entity_type = entity_type
        self.observations = observations or []

    def to_dict(self) -> dict[str, Any]:
        """Convert entity to MCP-compatible dict format.

        Returns:
            Dict with name, entityType, and observations keys.
        """
        return {
            "name": self.name,
            "entityType": self.entity_type,
            "observations": self.observations,
        }

class Relation:
    """Knowledge graph relation.

    Represents a directed edge between two entities in the memory
    knowledge graph.

    Example:
        >>> relation = Relation(
        ...     from_entity="Alice",
        ...     to_entity="ProjectDryade",
        ...     relation_type="works_on"
        ... )
        >>> relation.to_dict()
        {'from': 'Alice', 'to': 'ProjectDryade', 'relationType': 'works_on'}
    """

    def __init__(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
    ) -> None:
        """Initialize a Relation.

        Args:
            from_entity: Name of the source entity.
            to_entity: Name of the target entity.
            relation_type: Type of relationship (in active voice).
        """
        self.from_entity = from_entity
        self.to_entity = to_entity
        self.relation_type = relation_type

    def to_dict(self) -> dict[str, str]:
        """Convert relation to MCP-compatible dict format.

        Returns:
            Dict with from, to, and relationType keys.
        """
        return {
            "from": self.from_entity,
            "to": self.to_entity,
            "relationType": self.relation_type,
        }

class MemoryServer:
    """Typed wrapper for @modelcontextprotocol/server-memory MCP server.

    Provides typed Python methods for all 9 knowledge graph operations.
    Delegates to MCPRegistry for actual MCP communication.

    The Memory server maintains a knowledge graph with:
    - Entities: Named nodes with types and observations
    - Relations: Directed edges between entities
    - Observations: Facts about entities

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="memory",
        ...     command=["npx", "-y", "@modelcontextprotocol/server-memory"]
        ... )
        >>> registry.register(config)
        >>> memory = MemoryServer(registry)
        >>> memory.create_entities([
        ...     Entity("Alice", "person", ["Software engineer"])
        ... ])
    """

    def __init__(self, registry: MCPRegistry, server_name: str = "memory") -> None:
        """Initialize MemoryServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the memory server in registry (default: "memory").
        """
        self._registry = registry
        self._server_name = server_name

    def create_entities(self, entities: list[Entity | dict]) -> str:
        """Create multiple new entities in the knowledge graph.

        Args:
            entities: List of Entity objects or dicts with name, entityType, observations.

        Returns:
            Confirmation message from server.

        Raises:
            MCPTransportError: If entity creation fails.

        Example:
            >>> memory.create_entities([
            ...     Entity("Alice", "person", ["Software engineer"]),
            ...     {"name": "Bob", "entityType": "person", "observations": ["Designer"]}
            ... ])
        """
        entity_dicts = [e.to_dict() if isinstance(e, Entity) else e for e in entities]
        result = self._registry.call_tool(
            self._server_name, "create_entities", {"entities": entity_dicts}
        )
        return self._extract_text(result)

    def create_relations(self, relations: list[Relation | dict]) -> str:
        """Create multiple new relations between entities.

        Relations should be in active voice (e.g., "works_on", "manages", "uses").

        Args:
            relations: List of Relation objects or dicts with from, to, relationType.

        Returns:
            Confirmation message from server.

        Raises:
            MCPTransportError: If relation creation fails.

        Example:
            >>> memory.create_relations([
            ...     Relation("Alice", "ProjectDryade", "works_on"),
            ...     {"from": "Bob", "to": "Alice", "relationType": "collaborates_with"}
            ... ])
        """
        relation_dicts = [r.to_dict() if isinstance(r, Relation) else r for r in relations]
        result = self._registry.call_tool(
            self._server_name, "create_relations", {"relations": relation_dicts}
        )
        return self._extract_text(result)

    def add_observations(self, observations: list[dict]) -> str:
        """Add new observations to existing entities.

        Args:
            observations: List of dicts with entityName and contents (list of strings).

        Returns:
            Confirmation message from server.

        Raises:
            MCPTransportError: If adding observations fails.

        Example:
            >>> memory.add_observations([
            ...     {"entityName": "Alice", "contents": ["Joined team in 2024"]}
            ... ])
        """
        result = self._registry.call_tool(
            self._server_name, "add_observations", {"observations": observations}
        )
        return self._extract_text(result)

    def delete_entities(self, entity_names: list[str]) -> str:
        """Delete entities and their associated relations.

        Args:
            entity_names: Names of entities to delete.

        Returns:
            Confirmation message from server.

        Raises:
            MCPTransportError: If deletion fails.
        """
        result = self._registry.call_tool(
            self._server_name, "delete_entities", {"entityNames": entity_names}
        )
        return self._extract_text(result)

    def delete_observations(self, deletions: list[dict]) -> str:
        """Delete specific observations from entities.

        Args:
            deletions: List of dicts with entityName and observations (list of strings to delete).

        Returns:
            Confirmation message from server.

        Raises:
            MCPTransportError: If deletion fails.

        Example:
            >>> memory.delete_observations([
            ...     {"entityName": "Alice", "observations": ["Outdated fact"]}
            ... ])
        """
        result = self._registry.call_tool(
            self._server_name, "delete_observations", {"deletions": deletions}
        )
        return self._extract_text(result)

    def delete_relations(self, relations: list[Relation | dict]) -> str:
        """Delete multiple relations.

        Args:
            relations: List of Relation objects or dicts with from, to, relationType.

        Returns:
            Confirmation message from server.

        Raises:
            MCPTransportError: If deletion fails.
        """
        relation_dicts = [r.to_dict() if isinstance(r, Relation) else r for r in relations]
        result = self._registry.call_tool(
            self._server_name, "delete_relations", {"relations": relation_dicts}
        )
        return self._extract_text(result)

    def read_graph(self) -> dict[str, Any]:
        """Read the entire knowledge graph.

        Returns:
            Dict with "entities" and "relations" arrays.

        Raises:
            MCPTransportError: If reading fails.

        Example:
            >>> graph = memory.read_graph()
            >>> print(f"Entities: {len(graph['entities'])}")
            >>> print(f"Relations: {len(graph['relations'])}")
        """
        result = self._registry.call_tool(self._server_name, "read_graph", {})
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return {"entities": [], "relations": []}

    def search_nodes(self, query: str) -> list[dict]:
        """Search for nodes based on a query.

        Args:
            query: Search query string (searches names and observations).

        Returns:
            List of matching entity dicts.

        Raises:
            MCPTransportError: If search fails.
        """
        result = self._registry.call_tool(self._server_name, "search_nodes", {"query": query})
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return data.get("entities", [])
        return []

    def open_nodes(self, names: list[str]) -> list[dict]:
        """Open specific nodes by their names.

        Args:
            names: List of entity names to retrieve.

        Returns:
            List of entity dicts with full details.

        Raises:
            MCPTransportError: If retrieval fails.
        """
        result = self._registry.call_tool(self._server_name, "open_nodes", {"names": names})
        text = self._extract_text(result)
        if text:
            data = json.loads(text)
            return data.get("entities", [])
        return []

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
