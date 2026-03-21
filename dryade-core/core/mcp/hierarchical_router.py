"""Hierarchical Tool Router - MCP-Zero style two-stage semantic routing.

Implements efficient tool discovery for massive-scale MCP deployments (1000+ tools)
using hierarchical semantic matching.

Algorithm:
1. Stage 1 (Coarse): Filter to top-k servers by semantic similarity
2. Stage 2 (Fine): Rank tools within filtered servers
3. Combine scores: (Ss x St) x max(Ss, St)

This prevents context flooding by limiting tool search to relevant servers.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.mcp.embeddings import get_tool_embedding_store
from core.mcp.tool_index import get_tool_index

if TYPE_CHECKING:
    from core.mcp.embeddings import ToolEmbeddingStore
    from core.mcp.tool_index import ToolIndex

logger = logging.getLogger(__name__)

@dataclass
class RouteResult:
    """Result from hierarchical routing.

    Attributes:
        tool_name: Name of the matched tool.
        server: Server providing the tool.
        score: Combined relevance score using formula (Ss x St) x max(Ss, St).
        server_score: Server-level semantic similarity (Ss).
        tool_score: Tool-level semantic similarity (St).
        description: Tool description text.
    """

    tool_name: str
    server: str
    score: float
    server_score: float
    tool_score: float
    description: str = ""

class HierarchicalToolRouter:
    """Two-stage semantic router for MCP tool discovery.

    Implements MCP-Zero style hierarchical routing:
    - Stage 1: Server filter (embeddings) - coarse-grained
    - Stage 2: Tool rank within servers (embeddings) - fine-grained
    - Fallback: ToolIndex regex search when embeddings unavailable

    The score formula (Ss x St) x max(Ss, St) amplifies results where
    both server and tool match well, while still allowing high tool
    scores to surface even with moderate server matches.

    Usage:
        router = HierarchicalToolRouter()
        results = router.route("edit diagram elements", top_k=5)

        for result in results:
            print(f"{result.tool_name} ({result.server}): {result.score:.3f}")

    For server-specific routing (skip Stage 1):
        results = router.route_to_server("edit model", server="mcp-server")
    """

    def __init__(
        self,
        embedding_store: ToolEmbeddingStore | None = None,
        tool_index: ToolIndex | None = None,
        server_top_k: int = 3,
    ):
        """Initialize router.

        Args:
            embedding_store: Optional ToolEmbeddingStore instance.
                If None, singleton is loaded lazily.
            tool_index: Optional ToolIndex instance.
                If None, singleton is loaded lazily.
            server_top_k: Number of servers to consider in Stage 1 filter.
                Default 3 balances precision vs recall.
        """
        self._embedding_store = embedding_store
        self._tool_index = tool_index
        self.server_top_k = server_top_k

    @property
    def embedding_store(self) -> ToolEmbeddingStore:
        """Lazy load embedding store singleton."""
        if self._embedding_store is None:
            self._embedding_store = get_tool_embedding_store()
        return self._embedding_store

    @property
    def tool_index(self) -> ToolIndex:
        """Lazy load tool index singleton."""
        if self._tool_index is None:
            self._tool_index = get_tool_index()
        return self._tool_index

    def route(self, query: str, top_k: int = 10) -> list[RouteResult]:
        """Route query to relevant tools using hierarchical matching.

        Two-stage routing process:
        1. Filter to top-k servers by semantic similarity
        2. Rank tools within those servers
        3. Combine scores using (Ss x St) x max(Ss, St)

        Falls back to ToolIndex regex search when embeddings unavailable.

        Args:
            query: Natural language query describing desired tool
            top_k: Maximum number of results to return

        Returns:
            List of RouteResult sorted by combined score (highest first).
        """
        # Try semantic routing first
        if self.embedding_store.available:
            results = self._semantic_route(query, top_k)
            if results:
                return results
        else:
            if not getattr(self, "_fallback_warned", False):
                logger.warning(
                    "[ROUTER] Semantic routing unavailable (Qdrant not connected). "
                    "Using regex-based tool matching. Quality may be reduced for ambiguous queries."
                )
                self._fallback_warned = True

        # Fallback to index-based search
        results = self._index_route(query, top_k)
        if not results:
            logger.debug(
                "[ROUTER] No results from semantic or index search for query: %s",
                query[:80],
            )
        return results

    def _semantic_route(self, query: str, top_k: int) -> list[RouteResult]:
        """Two-stage semantic routing.

        Stage 1: Filter to top servers by semantic similarity
        Stage 2: Rank tools within those servers, combine scores

        Args:
            query: Natural language query
            top_k: Maximum results to return

        Returns:
            List of RouteResult sorted by combined score.
        """
        # Stage 1: Server filter
        server_results = self.embedding_store.search_servers(query, top_k=self.server_top_k)

        if not server_results:
            logger.debug("No servers matched query")
            return []

        # Build server score map
        server_scores: dict[str, float] = {r.name: r.score for r in server_results}
        server_names = list(server_scores.keys())

        logger.debug(f"Stage 1: Filtered to servers {server_names}")

        # Stage 2: Tool rank within filtered servers
        all_tool_results: list[RouteResult] = []

        for server_name in server_names:
            Ss = server_scores[server_name]

            tool_results = self.embedding_store.search_tools(
                query,
                top_k=top_k,
                server_filter=server_name,
            )

            for tool_result in tool_results:
                St = tool_result.score

                # Combined score formula: (Ss x St) x max(Ss, St)
                # This amplifies when both match well
                combined_score = (Ss * St) * max(Ss, St)

                all_tool_results.append(
                    RouteResult(
                        tool_name=tool_result.name,
                        server=tool_result.server,
                        score=combined_score,
                        server_score=Ss,
                        tool_score=St,
                        description=tool_result.payload.get("description", ""),
                    )
                )

        # Sort by combined score, limit results
        all_tool_results.sort(key=lambda r: r.score, reverse=True)
        return all_tool_results[:top_k]

    def _index_route(self, query: str, top_k: int) -> list[RouteResult]:
        """Fallback routing using ToolIndex regex search.

        Used when embeddings are unavailable or return no results.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            List of RouteResult from index search.
        """
        search_results = self.tool_index.search(
            query,
            limit=top_k,
        )

        return [
            RouteResult(
                tool_name=r.entry.name,
                server=r.entry.server,
                score=r.score,
                server_score=1.0,  # No server-level filtering in fallback
                tool_score=r.score,
                description=r.entry.description_preview,
            )
            for r in search_results
        ]

    def route_to_server(self, query: str, server: str, top_k: int = 10) -> list[RouteResult]:
        """Route within a specific server (skip Stage 1).

        Useful when you already know the target server and just need
        tool ranking within that server.

        Args:
            query: Natural language query
            server: Server name to search within
            top_k: Maximum results

        Returns:
            List of RouteResult from specified server only.
        """
        if self.embedding_store.available:
            tool_results = self.embedding_store.search_tools(
                query,
                top_k=top_k,
                server_filter=server,
            )

            return [
                RouteResult(
                    tool_name=r.name,
                    server=r.server,
                    score=r.score,
                    server_score=1.0,  # No server filtering, score is 1.0
                    tool_score=r.score,
                    description=r.payload.get("description", ""),
                )
                for r in tool_results
            ]

        # Fallback to index search with server filter
        search_results = self.tool_index.search(
            query,
            server_filter=server,
            limit=top_k,
        )

        return [
            RouteResult(
                tool_name=r.entry.name,
                server=r.entry.server,
                score=r.score,
                server_score=1.0,
                tool_score=r.score,
                description=r.entry.description_preview,
            )
            for r in search_results
        ]

# Singleton pattern
_router: HierarchicalToolRouter | None = None
_router_lock = threading.Lock()

def get_hierarchical_router() -> HierarchicalToolRouter:
    """Get or create singleton HierarchicalToolRouter instance.

    Returns:
        Shared HierarchicalToolRouter instance.
    """
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = HierarchicalToolRouter()
    return _router

def reset_hierarchical_router() -> None:
    """Reset the singleton router (for testing).

    Clears the singleton so the next call to get_hierarchical_router()
    creates a fresh instance.
    """
    global _router
    _router = None
