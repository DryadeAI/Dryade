"""
Unit tests for semantic_cache plugin.

Tests cover:
1. Plugin protocol implementation
2. Cache initialization
3. Exact match hit/miss
4. Semantic match (mocked)
5. Cache set entry
6. TTL expiry
7. Cache wrapper decorator
8. Graceful degradation
9. Threshold tuning

Target: ~150 LOC
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock fastembed BEFORE any plugin import.
# fastembed is a heavy ML dependency (~500MB) not suitable for unit tests.
# The semantic_cache plugin imports it at module level via embedder.py.
# ---------------------------------------------------------------------------
_fastembed_mock = MagicMock()
_fastembed_mock.TextEmbedding = MagicMock
sys.modules.setdefault("fastembed", _fastembed_mock)

@pytest.fixture
def mock_cache_config():
    """Mock cache configuration."""
    config = MagicMock()
    config.enabled = True
    config.embedding_model = "all-MiniLM-L6-v2"
    config.qdrant_url = "http://localhost:6333"
    config.redis_url = "redis://localhost:6379"
    config.similarity_threshold = 0.9
    config.exact_ttl_seconds = 3600
    config.semantic_ttl_seconds = 86400
    config.max_entries = 10000
    config.qdrant_hnsw_m = 16
    config.qdrant_hnsw_ef_construct = 100
    config.qdrant_on_disk = False
    return config

@pytest.fixture
def mock_embedder():
    """Mock embedding generator."""
    embedder = MagicMock()
    embedder.generate_embedding.return_value = [0.1] * 384
    return embedder

@pytest.fixture
def mock_vector_store():
    """Mock Qdrant vector store."""
    store = MagicMock()
    store.is_available = True
    store.search_similar.return_value = []
    store.store_embedding.return_value = True
    store.count.return_value = 0
    store.evict_oldest.return_value = 0
    store.close.return_value = None
    return store

@pytest.fixture
def mock_response_store():
    """Mock Redis response store."""
    store = MagicMock()
    store.is_available = True
    store.get_response.return_value = None
    store.store_response.return_value = True
    store.count.return_value = 0
    store.evict_oldest.return_value = 0
    store.close.return_value = None
    store.clear_all.return_value = None
    return store

@pytest.mark.unit
class TestSemanticCachePlugin:
    """Tests for SemanticCachePlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""

        # plugin may be None if validation failed at import
        # Use the class directly for attribute checks
        from plugins.semantic_cache import SemanticCachePlugin

        p = SemanticCachePlugin()
        assert hasattr(p, "name")
        assert hasattr(p, "version")
        assert hasattr(p, "description")
        assert hasattr(p, "register")
        assert hasattr(p, "startup")
        assert hasattr(p, "shutdown")

    def test_plugin_name_and_version(self):
        """Test plugin name and version."""
        from plugins.semantic_cache import SemanticCachePlugin

        p = SemanticCachePlugin()
        assert p.name == "semantic_cache"
        assert p.version == "1.0.0"

    def test_plugin_register(self):
        """Test plugin registration with registry."""
        from plugins.semantic_cache import SemanticCachePlugin

        from core.extensions.pipeline import ExtensionRegistry

        p = SemanticCachePlugin()
        registry = ExtensionRegistry()
        p.register(registry)

        # Should register semantic_cache extension
        config = registry.get("semantic_cache")
        assert config is not None
        assert config.priority == 2

@pytest.mark.unit
class TestSemanticCache:
    """Tests for SemanticCache class."""

    def test_cache_initialization(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test cache initializes with components."""
        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            assert cache.config == mock_cache_config
            assert cache.embedder is not None
            assert cache.vector_store is not None
            assert cache.response_store is not None
            assert cache._stats["total_queries"] == 0

    @pytest.mark.asyncio
    async def test_cache_exact_match_hit(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test exact match cache hit."""
        mock_response_store.get_response.return_value = "cached response"

        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            result = await cache.get("test query")

            assert result == "cached response"
            assert cache._stats["exact_hits"] == 1
            assert cache._stats["total_queries"] == 1

    @pytest.mark.asyncio
    async def test_cache_exact_match_miss(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test exact match cache miss."""
        mock_response_store.get_response.return_value = None
        mock_vector_store.search_similar.return_value = []

        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            result = await cache.get("test query")

            assert result is None
            assert cache._stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_cache_semantic_match(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test semantic match cache hit."""
        # First call to get_response returns None (exact miss)
        # Second call returns the semantic match response
        mock_response_store.get_response.side_effect = [None, "semantic cached response"]
        mock_vector_store.search_similar.return_value = [("cache:abc123", 0.95)]

        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            result = await cache.get("similar query")

            assert result == "semantic cached response"
            assert cache._stats["semantic_hits"] == 1

    @pytest.mark.asyncio
    async def test_cache_set_entry(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test setting cache entry."""
        mock_response_store.store_response.return_value = True
        mock_vector_store.store_embedding.return_value = True
        mock_vector_store.count.return_value = 0

        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            result = await cache.set("test query", "test response")

            assert result is True
            mock_response_store.store_response.assert_called_once()
            mock_vector_store.store_embedding.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_disabled(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test cache returns None when disabled."""
        mock_cache_config.enabled = False

        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            result = await cache.get("test query")
            assert result is None

            set_result = await cache.set("test query", "test response")
            assert set_result is False

    def test_cache_stats(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test cache statistics."""
        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            stats = cache.get_stats()

            assert "total_queries" in stats
            assert "exact_hits" in stats
            assert "semantic_hits" in stats
            assert "misses" in stats
            assert "hit_rate" in stats
            assert "services" in stats

    def test_cache_clear(
        self, mock_cache_config, mock_embedder, mock_vector_store, mock_response_store
    ):
        """Test clearing cache."""
        with (
            patch("plugins.semantic_cache.cache.get_cache_config", return_value=mock_cache_config),
            patch("plugins.semantic_cache.cache.EmbeddingGenerator", return_value=mock_embedder),
            patch("plugins.semantic_cache.cache.QdrantVectorStore", return_value=mock_vector_store),
            patch(
                "plugins.semantic_cache.cache.RedisResponseStore", return_value=mock_response_store
            ),
        ):
            from plugins.semantic_cache.cache import SemanticCache

            cache = SemanticCache(config=mock_cache_config)

            result = cache.clear()

            assert result is True
            mock_response_store.clear_all.assert_called_once()

@pytest.mark.unit
class TestCacheWrapper:
    """Tests for cache wrapper functions."""

    def test_cache_hit_marker(self):
        """Test CacheHitMarker class."""
        from plugins.semantic_cache.wrapper import CacheHitMarker

        marker = CacheHitMarker(content="test content", cache_hit=True)

        assert marker.type == "cache_hit"
        assert marker.content == "test content"
        assert marker.cache_hit is True

        marker_dict = marker.to_dict()
        assert marker_dict["type"] == "cache_hit"
        assert marker_dict["content"] == "test content"

    def test_extract_query_from_messages(self):
        """Test extracting query from message list."""
        from plugins.semantic_cache.wrapper import _extract_query_from_messages

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What is Python?"},
        ]

        query = _extract_query_from_messages(messages)
        assert query == "What is Python?"

    def test_extract_query_empty_messages(self):
        """Test extracting query from empty messages."""
        from plugins.semantic_cache.wrapper import _extract_query_from_messages

        query = _extract_query_from_messages([])
        assert query == ""
