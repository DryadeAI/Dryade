"""Tests for MCP Hierarchical Tool Router.

TDD tests for two-stage semantic routing with MCP-Zero style matching.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.mcp.embeddings import EmbeddingResult
from core.mcp.hierarchical_router import (
    HierarchicalToolRouter,
    RouteResult,
    get_hierarchical_router,
)
from core.mcp.tool_index import SearchResult, ToolEntry

class TestRouteResult:
    """Tests for RouteResult dataclass."""

    def test_route_result_creation(self):
        """Test basic RouteResult instantiation."""
        result = RouteResult(
            tool_name="capella_edit",
            server="mcp-capella",
            score=0.689,
            server_score=0.9,
            tool_score=0.85,
            description="Edit Capella model elements",
        )
        assert result.tool_name == "capella_edit"
        assert result.server == "mcp-capella"
        assert result.score == 0.689
        assert result.server_score == 0.9
        assert result.tool_score == 0.85
        assert result.description == "Edit Capella model elements"

    def test_route_result_default_description(self):
        """Test RouteResult with default empty description."""
        result = RouteResult(
            tool_name="test_tool",
            server="test-server",
            score=0.5,
            server_score=0.7,
            tool_score=0.6,
        )
        assert result.description == ""

class TestHierarchicalToolRouter:
    """Tests for HierarchicalToolRouter class."""

    @pytest.fixture
    def mock_embedding_store(self):
        """Create mock embedding store."""
        store = MagicMock()
        store.available = True
        return store

    @pytest.fixture
    def mock_tool_index(self):
        """Create mock tool index."""
        index = MagicMock()
        return index

    @pytest.fixture
    def router(self, mock_embedding_store, mock_tool_index):
        """Create router with mocked dependencies."""
        return HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=mock_tool_index,
            server_top_k=3,
        )

    def test_initialization(self, router):
        """Test router initializes with correct defaults."""
        assert router.server_top_k == 3

    def test_initialization_defaults(self):
        """Test router uses default server_top_k."""
        router = HierarchicalToolRouter()
        assert router.server_top_k == 3

    def test_route_semantic_two_stage(self, router, mock_embedding_store):
        """Test two-stage semantic routing: server filter -> tool rank."""
        # Setup Stage 1: Server filter returns mcp-capella with score 0.9
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(
                id="server-1",
                name="mcp-capella",
                server="mcp-capella",
                score=0.9,
                payload={"description": "MBSE modeling tools"},
            )
        ]

        # Setup Stage 2: Tool search within server returns capella_edit with score 0.85
        mock_embedding_store.search_tools.return_value = [
            EmbeddingResult(
                id="tool-1",
                name="capella_edit",
                server="mcp-capella",
                score=0.85,
                payload={"description": "Edit Capella model elements"},
            )
        ]

        # Route query
        results = router.route("edit capella model", top_k=5)

        # Verify two-stage routing occurred
        mock_embedding_store.search_servers.assert_called_once_with("edit capella model", top_k=3)
        mock_embedding_store.search_tools.assert_called_once_with(
            "edit capella model",
            top_k=5,
            server_filter="mcp-capella",
        )

        # Verify result
        assert len(results) == 1
        result = results[0]
        assert result.tool_name == "capella_edit"
        assert result.server == "mcp-capella"
        assert result.server_score == 0.9
        assert result.tool_score == 0.85

    def test_score_formula(self, router, mock_embedding_store):
        """Test score formula: (Ss x St) x max(Ss, St)."""
        # Server score (Ss) = 0.9, Tool score (St) = 0.85
        # Expected: (0.9 * 0.85) * max(0.9, 0.85) = 0.765 * 0.9 = 0.6885
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(
                id="server-1",
                name="mcp-capella",
                server="mcp-capella",
                score=0.9,
                payload={},
            )
        ]
        mock_embedding_store.search_tools.return_value = [
            EmbeddingResult(
                id="tool-1",
                name="capella_edit",
                server="mcp-capella",
                score=0.85,
                payload={"description": ""},
            )
        ]

        results = router.route("edit capella model")
        assert len(results) == 1

        # Verify score formula
        expected_score = (0.9 * 0.85) * max(0.9, 0.85)
        assert abs(results[0].score - expected_score) < 0.0001

    def test_score_formula_tool_higher(self, router, mock_embedding_store):
        """Test score formula when tool score is higher than server score."""
        # Server score (Ss) = 0.8, Tool score (St) = 0.95
        # Expected: (0.8 * 0.95) * max(0.8, 0.95) = 0.76 * 0.95 = 0.722
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(
                id="server-1",
                name="mcp-memory",
                server="mcp-memory",
                score=0.8,
                payload={},
            )
        ]
        mock_embedding_store.search_tools.return_value = [
            EmbeddingResult(
                id="tool-1",
                name="memory_store",
                server="mcp-memory",
                score=0.95,
                payload={"description": ""},
            )
        ]

        results = router.route("store in memory")
        assert len(results) == 1

        expected_score = (0.8 * 0.95) * max(0.8, 0.95)
        assert abs(results[0].score - expected_score) < 0.0001

    def test_multiple_servers_multiple_tools(self, router, mock_embedding_store):
        """Test routing across multiple servers with multiple tools."""
        # Setup: 2 servers, each with 2 tools
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(
                id="s1",
                name="mcp-capella",
                server="mcp-capella",
                score=0.9,
                payload={},
            ),
            EmbeddingResult(
                id="s2",
                name="mcp-memory",
                server="mcp-memory",
                score=0.7,
                payload={},
            ),
        ]

        # Different tools for each server
        def tool_search(query, top_k, server_filter):
            if server_filter == "mcp-capella":
                return [
                    EmbeddingResult(
                        id="t1",
                        name="capella_edit",
                        server="mcp-capella",
                        score=0.85,
                        payload={"description": "Edit models"},
                    ),
                    EmbeddingResult(
                        id="t2",
                        name="capella_open",
                        server="mcp-capella",
                        score=0.6,
                        payload={"description": "Open models"},
                    ),
                ]
            elif server_filter == "mcp-memory":
                return [
                    EmbeddingResult(
                        id="t3",
                        name="memory_store",
                        server="mcp-memory",
                        score=0.8,
                        payload={"description": "Store data"},
                    ),
                ]
            return []

        mock_embedding_store.search_tools.side_effect = tool_search

        results = router.route("edit model", top_k=10)

        # Should have 3 results total
        assert len(results) == 3

        # Results should be sorted by combined score (highest first)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_no_server_matches(self, router, mock_embedding_store):
        """Test empty results when no servers match."""
        mock_embedding_store.search_servers.return_value = []

        results = router.route("unknown query")
        assert results == []

    def test_no_tool_matches(self, router, mock_embedding_store):
        """Test empty results when servers match but no tools match."""
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(
                id="s1",
                name="mcp-capella",
                server="mcp-capella",
                score=0.9,
                payload={},
            )
        ]
        mock_embedding_store.search_tools.return_value = []

        results = router.route("edit capella model")
        assert results == []

    def test_fallback_to_index_when_embeddings_unavailable(
        self, mock_embedding_store, mock_tool_index
    ):
        """Test graceful fallback to ToolIndex when embeddings unavailable."""
        # Make embeddings unavailable
        mock_embedding_store.available = False

        router = HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=mock_tool_index,
        )

        # Setup index search results
        mock_entry = ToolEntry(
            name="capella_edit",
            server="mcp-capella",
            description_hash="abc123",
            description_preview="Edit Capella models",
            fingerprint="mcp-capella:capella_edit:abc123",
        )
        mock_tool_index.search.return_value = [
            SearchResult(entry=mock_entry, score=0.8, match_type="regex_name")
        ]

        results = router.route("edit capella")

        # Should use index search (no mode parameter -- search uses regex by default)
        mock_tool_index.search.assert_called_once_with(
            "edit capella",
            limit=10,
        )

        # Verify result mapping
        assert len(results) == 1
        assert results[0].tool_name == "capella_edit"
        assert results[0].server == "mcp-capella"
        assert results[0].score == 0.8
        assert results[0].server_score == 1.0  # Fallback uses 1.0 for server score
        assert results[0].tool_score == 0.8

    def test_fallback_when_semantic_returns_empty(self, mock_embedding_store, mock_tool_index):
        """Test fallback to index when semantic search returns no results."""
        # Embeddings available but returns empty
        mock_embedding_store.available = True
        mock_embedding_store.search_servers.return_value = []

        router = HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=mock_tool_index,
        )

        mock_tool_index.search.return_value = []

        results = router.route("unknown query")

        # Should still return empty (index also has no results)
        assert results == []

class TestRouteToServer:
    """Tests for server-specific routing (skip Stage 1)."""

    @pytest.fixture
    def mock_embedding_store(self):
        """Create mock embedding store."""
        store = MagicMock()
        store.available = True
        return store

    @pytest.fixture
    def mock_tool_index(self):
        """Create mock tool index."""
        return MagicMock()

    @pytest.fixture
    def router(self, mock_embedding_store, mock_tool_index):
        """Create router with mocked dependencies."""
        return HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=mock_tool_index,
        )

    def test_route_to_server_semantic(self, router, mock_embedding_store):
        """Test direct server routing skips Stage 1."""
        mock_embedding_store.search_tools.return_value = [
            EmbeddingResult(
                id="t1",
                name="capella_edit",
                server="mcp-capella",
                score=0.85,
                payload={"description": "Edit models"},
            )
        ]

        results = router.route_to_server("edit model", server="mcp-capella", top_k=5)

        # Should call search_tools directly with server filter
        mock_embedding_store.search_tools.assert_called_once_with(
            "edit model",
            top_k=5,
            server_filter="mcp-capella",
        )

        # Should NOT call search_servers (Stage 1 skipped)
        mock_embedding_store.search_servers.assert_not_called()

        # Verify result
        assert len(results) == 1
        assert results[0].tool_name == "capella_edit"
        assert results[0].server_score == 1.0  # No server filtering, score is 1.0
        assert results[0].tool_score == 0.85

    def test_route_to_server_fallback(self, mock_embedding_store, mock_tool_index):
        """Test route_to_server falls back to index when embeddings unavailable."""
        mock_embedding_store.available = False

        router = HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=mock_tool_index,
        )

        mock_entry = ToolEntry(
            name="capella_open",
            server="mcp-capella",
            description_hash="def456",
            description_preview="Open Capella models",
            fingerprint="mcp-capella:capella_open:def456",
        )
        mock_tool_index.search.return_value = [
            SearchResult(entry=mock_entry, score=0.7, match_type="regex_name")
        ]

        results = router.route_to_server("open model", server="mcp-capella")

        # search no longer has mode parameter -- uses regex by default
        mock_tool_index.search.assert_called_once_with(
            "open model",
            server_filter="mcp-capella",
            limit=10,
        )

        assert len(results) == 1
        assert results[0].tool_name == "capella_open"

class TestSingleton:
    """Tests for singleton accessor."""

    def test_get_hierarchical_router_singleton(self):
        """Test get_hierarchical_router returns singleton."""
        # Reset for clean test
        import core.mcp.hierarchical_router as router_module
        from core.mcp.hierarchical_router import get_hierarchical_router

        router_module._router = None

        router1 = get_hierarchical_router()
        router2 = get_hierarchical_router()

        assert router1 is router2

    def test_router_uses_singleton_stores(self):
        """Test router lazy loads singleton stores."""
        import core.mcp.hierarchical_router as router_module

        router_module._router = None

        router = get_hierarchical_router()

        # Access properties to trigger lazy loading
        with patch("core.mcp.hierarchical_router.get_tool_embedding_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.available = False
            mock_get_store.return_value = mock_store

            # Force property access
            router._embedding_store = None
            _ = router.embedding_store

            mock_get_store.assert_called_once()

class TestTopKLimiting:
    """Tests for top-k result limiting."""

    @pytest.fixture
    def mock_embedding_store(self):
        """Create mock embedding store."""
        store = MagicMock()
        store.available = True
        return store

    @pytest.fixture
    def router(self, mock_embedding_store):
        """Create router with mock store."""
        return HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=MagicMock(),
            server_top_k=2,
        )

    def test_top_k_limits_results(self, router, mock_embedding_store):
        """Test top_k parameter limits returned results."""
        # Return more results than requested top_k
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(id="s1", name="server1", server="server1", score=0.9, payload={}),
        ]
        mock_embedding_store.search_tools.return_value = [
            EmbeddingResult(
                id=f"t{i}",
                name=f"tool{i}",
                server="server1",
                score=0.9 - i * 0.1,
                payload={"description": ""},
            )
            for i in range(10)
        ]

        results = router.route("query", top_k=3)

        # Should only return 3 results
        assert len(results) == 3

    def test_server_top_k_limits_servers(self, router, mock_embedding_store):
        """Test server_top_k limits servers queried in Stage 2."""
        # Return 5 servers but router has server_top_k=2
        mock_embedding_store.search_servers.return_value = [
            EmbeddingResult(
                id=f"s{i}", name=f"server{i}", server=f"server{i}", score=0.9 - i * 0.1, payload={}
            )
            for i in range(5)
        ]
        mock_embedding_store.search_tools.return_value = []

        router.route("query")

        # search_servers should be called with server_top_k=2
        mock_embedding_store.search_servers.assert_called_once_with("query", top_k=2)
