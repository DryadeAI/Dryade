"""Tests for MCP Tool Embedding Store."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from core.mcp.embeddings import (
    EMBEDDING_DIM,
    QDRANT_AVAILABLE,
    EmbeddingResult,
    ToolEmbeddingStore,
    get_tool_embedding_store,
    reset_tool_embedding_store,
)
from core.mcp.protocol import MCPTool
from core.mcp.tool_index import ToolEntry

class TestEmbeddingResult:
    """Test EmbeddingResult dataclass."""

    def test_embedding_result_fields(self):
        """EmbeddingResult has expected fields."""
        result = EmbeddingResult(
            id="123",
            name="test_tool",
            server="test_server",
            score=0.95,
            payload={"key": "value"},
        )

        assert result.id == "123"
        assert result.name == "test_tool"
        assert result.server == "test_server"
        assert result.score == 0.95
        assert result.payload == {"key": "value"}

    def test_embedding_result_equality(self):
        """EmbeddingResults with same values are equal."""
        result1 = EmbeddingResult(
            id="123",
            name="tool",
            server="server",
            score=0.9,
            payload={},
        )
        result2 = EmbeddingResult(
            id="123",
            name="tool",
            server="server",
            score=0.9,
            payload={},
        )

        assert result1 == result2

class TestToolEmbeddingStoreInit:
    """Test ToolEmbeddingStore initialization."""

    def test_init_default_values(self):
        """Store initializes with default values."""
        store = ToolEmbeddingStore()

        assert store.embedding_model == "all-MiniLM-L6-v2"
        assert store._client is None
        assert store._available is False

    def test_init_custom_url(self):
        """Store accepts custom Qdrant URL."""
        store = ToolEmbeddingStore(url="http://custom:6333")

        assert store.url == "http://custom:6333"

    def test_init_custom_embedding_model(self):
        """Store accepts custom embedding model."""
        store = ToolEmbeddingStore(embedding_model="text-embedding-ada-002")

        assert store.embedding_model == "text-embedding-ada-002"

class TestToolEmbeddingStoreGracefulDegradation:
    """Test graceful degradation when Qdrant unavailable."""

    def test_search_tools_returns_empty_when_unavailable(self):
        """Search returns empty list when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        # Should not raise, just return empty
        results = store.search_tools("test query")

        assert results == []

    def test_search_servers_returns_empty_when_unavailable(self):
        """Server search returns empty list when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        results = store.search_servers("test query")

        assert results == []

    def test_index_tool_returns_false_when_unavailable(self):
        """Index returns False when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")
        tool = MCPTool(name="test", description="test", inputSchema={})
        entry = ToolEntry.from_mcp_tool(tool, "server")

        # Should not raise, just return False
        result = store.index_tool(entry)

        assert result is False

    def test_index_server_returns_false_when_unavailable(self):
        """Index server returns False when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        result = store.index_server("test_server", "Test description")

        assert result is False

    def test_delete_tool_returns_false_when_unavailable(self):
        """Delete returns False when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        result = store.delete_tool("fingerprint")

        assert result is False

    def test_clear_returns_false_when_unavailable(self):
        """Clear returns False when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        result = store.clear()

        assert result is False

    def test_available_property_returns_false_when_unavailable(self):
        """Available property returns False when Qdrant unavailable."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        assert store.available is False

    def test_get_stats_returns_unavailable_when_qdrant_down(self):
        """get_stats returns unavailable=False when Qdrant is down."""
        store = ToolEmbeddingStore(url="http://nonexistent:6333")

        stats = store.get_stats()

        assert stats["available"] is False
        assert stats["tool_count"] == 0
        assert stats["server_count"] == 0

class TestEmbeddingStoreSingleton:
    """Test singleton pattern."""

    def test_get_tool_embedding_store_returns_singleton(self):
        """get_tool_embedding_store returns same instance."""
        # Clear singleton for test
        reset_tool_embedding_store()

        store1 = get_tool_embedding_store()
        store2 = get_tool_embedding_store()

        assert store1 is store2

    def test_reset_tool_embedding_store_clears_singleton(self):
        """reset_tool_embedding_store clears the singleton."""
        # Get initial instance
        store1 = get_tool_embedding_store()

        # Reset singleton
        reset_tool_embedding_store()

        # Get new instance
        store2 = get_tool_embedding_store()

        # Should be different instances
        assert store1 is not store2

class TestPointIdGeneration:
    """Test deterministic point ID generation."""

    def test_generate_point_id_is_deterministic(self):
        """Same identifier produces same point ID."""
        store = ToolEmbeddingStore()

        id1 = store._generate_point_id("test:identifier")
        id2 = store._generate_point_id("test:identifier")

        assert id1 == id2

    def test_generate_point_id_is_valid_uuid(self):
        """Generated point ID is a valid UUID string."""
        import uuid

        store = ToolEmbeddingStore()

        point_id = store._generate_point_id("test")

        # Should not raise
        parsed = uuid.UUID(point_id)
        assert str(parsed) == point_id

    def test_different_identifiers_produce_different_ids(self):
        """Different identifiers produce different point IDs."""
        store = ToolEmbeddingStore()

        id1 = store._generate_point_id("server:capella")
        id2 = store._generate_point_id("server:github")

        assert id1 != id2

@pytest.mark.skipif(not QDRANT_AVAILABLE, reason="qdrant-client not installed")
@patch.object(ToolEmbeddingStore, "ensure_indexed", return_value=True)
class TestToolEmbeddingStoreWithMocks:
    """Test embedding store with mocked Qdrant client."""

    def _make_store(self, mock_st_class, mock_qdrant_class):
        """Helper: create a ToolEmbeddingStore with properly configured mocks.

        Must be called within a patch.object(ToolEmbeddingStore, "ensure_indexed")
        context, or from a test that doesn't trigger _ensure_client.
        """
        mock_qdrant = Mock()
        mock_qdrant.get_collections.return_value.collections = []
        mock_qdrant_class.return_value = mock_qdrant

        mock_encoder = Mock()
        mock_embedding = Mock()
        mock_embedding.tolist.return_value = [0.1] * EMBEDDING_DIM
        mock_encoder.encode.return_value = mock_embedding
        mock_encoder.get_sentence_embedding_dimension.return_value = EMBEDDING_DIM
        mock_st_class.return_value = mock_encoder

        store = ToolEmbeddingStore()
        return store, mock_qdrant

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_index_tool_creates_point(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """Indexing a tool creates a Qdrant point."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)
        tool = MCPTool(name="test_tool", description="Test description", inputSchema={})
        entry = ToolEntry.from_mcp_tool(tool, "test_server")

        result = store.index_tool(entry)

        assert result is True
        mock_qdrant.upsert.assert_called_once()

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_index_server_creates_point(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """Indexing a server creates a Qdrant point."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)

        result = store.index_server("mcp-capella", "MBSE modeling tools")

        assert result is True
        mock_qdrant.upsert.assert_called_once()

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_search_tools_queries_qdrant(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """Search queries Qdrant with embedding."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)
        mock_response = Mock()
        mock_response.points = [
            Mock(
                id="123",
                score=0.95,
                payload={
                    "name": "capella_open",
                    "server": "mcp-capella",
                    "description": "Open model",
                },
            )
        ]
        mock_qdrant.query_points.return_value = mock_response

        results = store.search_tools("open capella model")

        assert len(results) == 1
        assert results[0].name == "capella_open"
        assert results[0].server == "mcp-capella"
        assert results[0].score == 0.95

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_search_servers_queries_qdrant(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """Server search queries Qdrant with embedding."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)
        mock_response = Mock()
        mock_response.points = [
            Mock(
                id="456",
                score=0.88,
                payload={
                    "name": "mcp-capella",
                    "description": "MBSE modeling tools",
                },
            )
        ]
        mock_qdrant.query_points.return_value = mock_response

        results = store.search_servers("MBSE modeling")

        assert len(results) == 1
        assert results[0].name == "mcp-capella"
        assert results[0].score == 0.88

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_search_with_server_filter(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """Search with server filter adds Qdrant filter."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)
        mock_response = Mock()
        mock_response.points = []
        mock_qdrant.query_points.return_value = mock_response

        store.search_tools("query", server_filter="mcp-capella")

        # Verify filter was passed
        call_args = mock_qdrant.query_points.call_args
        assert call_args.kwargs.get("query_filter") is not None

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_delete_tool_calls_qdrant_delete(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """Delete tool calls Qdrant delete."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)

        result = store.delete_tool("server:tool:hash")

        assert result is True
        mock_qdrant.delete.assert_called_once()

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_get_stats_returns_counts(self, mock_st_class, mock_qdrant_class, _mock_ensure):
        """get_stats returns collection counts."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)

        tool_info = Mock()
        tool_info.points_count = 100
        server_info = Mock()
        server_info.points_count = 5

        mock_qdrant.get_collection.side_effect = [tool_info, server_info]
        stats = store.get_stats()

        assert stats["available"] is True
        assert stats["tool_count"] == 100
        assert stats["server_count"] == 5
        assert stats["embedding_dim"] == EMBEDDING_DIM

    @patch("core.mcp.embeddings.QdrantClient")
    @patch("core.mcp.embeddings.SentenceTransformer")
    def test_clear_deletes_and_recreates_collections(
        self, mock_st_class, mock_qdrant_class, _mock_ensure
    ):
        """Clear deletes and recreates both collections."""
        store, mock_qdrant = self._make_store(mock_st_class, mock_qdrant_class)
        result = store.clear()

        assert result is True
        # Should have called delete_collection for both
        assert mock_qdrant.delete_collection.call_count >= 1

class TestToolEntryCompatibility:
    """Test compatibility with ToolEntry from tool_index."""

    def test_tool_entry_from_mcp_tool_has_required_fields(self):
        """ToolEntry has fields needed for indexing."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool for testing",
            inputSchema={"type": "object", "properties": {"arg1": {"type": "string"}}},
        )
        entry = ToolEntry.from_mcp_tool(tool, "test_server")

        # Verify required fields exist
        assert hasattr(entry, "name")
        assert hasattr(entry, "server")
        assert hasattr(entry, "description_preview")
        assert hasattr(entry, "fingerprint")
        assert hasattr(entry, "input_schema_keys")

        assert entry.name == "test_tool"
        assert entry.server == "test_server"
        assert "A test tool" in entry.description_preview
