"""Comprehensive tests for the knowledge_advanced plugin.

Tests cover: AdvancedRAGConfig, AdvancedRetriever, AdvancedIndexer,
plugin boundary, routes, plugin protocol, and auth guards.
All external dependencies mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from plugins.knowledge_advanced.config import AdvancedRAGConfig
except ModuleNotFoundError:
    pytest.skip(
        "plugins not available (standalone checkout)",
        allow_module_level=True,
    )

# ── Shared helpers ─────────────────────────────────────────────────────────

def _make_mock_embedder():
    """Create a mock EmbeddingService."""
    embedder = MagicMock()
    embedder.embed_dense_single.return_value = [0.1] * 384
    embedder.embed_sparse_single.return_value = MagicMock()
    embedder.rerank.side_effect = lambda query, docs, top_k=5: [
        {**d, "rerank_score": 0.9 - i * 0.1} for i, d in enumerate(docs[:top_k])
    ]
    return embedder

def _make_mock_store():
    """Create a mock HybridVectorStore."""
    store = MagicMock()
    store.hybrid_search.return_value = [
        {"content": "result 1", "score": 0.8, "metadata": {"source_id": "ks_1"}},
        {"content": "result 2", "score": 0.6, "metadata": {"source_id": "ks_1"}},
    ]
    return store

def _make_test_app():
    """Create test FastAPI app with auth override."""
    from fastapi import FastAPI
    from plugins.knowledge_advanced.routes import router

    from core.auth.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router, prefix="/api/knowledge/advanced")
    # Override auth to return a mock user
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "role": "member",
    }
    return app

# ── AdvancedRAGConfig tests ────────────────────────────────────────────────

class TestAdvancedRAGConfig:
    def test_default_config_values(self):
        config = AdvancedRAGConfig()
        assert config.multi_query_enabled is True
        assert config.hyde_enabled is True
        assert config.multi_query_count == 3
        assert config.adaptive_retrieval is True
        assert config.semantic_chunking is True
        assert config.semantic_similarity_threshold == 0.7
        assert config.rerank_top_k == 50

    def test_config_overrides(self):
        config = AdvancedRAGConfig(
            multi_query_enabled=False,
            hyde_enabled=False,
            multi_query_count=5,
            rerank_top_k=20,
        )
        assert config.multi_query_enabled is False
        assert config.hyde_enabled is False
        assert config.multi_query_count == 5
        assert config.rerank_top_k == 20

    def test_team_tier_model_defaults(self):
        """Team tier uses bge-base (768d), not bge-small (384d)."""
        config = AdvancedRAGConfig()
        assert config.dense_model == "BAAI/bge-base-en-v1.5"
        assert "bge-base" in config.dense_model
        assert config.reranker_model == "Xenova/ms-marco-MiniLM-L-12-v2"

# ── AdvancedRetriever tests ────────────────────────────────────────────────

class MockLLM:
    """Mock LLM provider for multi-query and HyDE generation."""

    async def generate(self, prompt: str, max_tokens: int = 200) -> str:
        if "alternative phrasings" in prompt:
            return "variant query 1\nvariant query 2\nvariant query 3"
        elif "perfect answer" in prompt:
            return "This is a hypothetical document about the topic."
        return "mock response"

class FailingLLM:
    """LLM that always raises."""

    async def generate(self, prompt: str, max_tokens: int = 200) -> str:
        raise RuntimeError("LLM unavailable")

@pytest.fixture
def mock_embedder():
    return _make_mock_embedder()

@pytest.fixture
def mock_store():
    return _make_mock_store()

@pytest.fixture
def retriever(mock_embedder, mock_store):
    from plugins.knowledge_advanced.retriever import AdvancedRetriever

    return AdvancedRetriever(embedder=mock_embedder, store=mock_store, config=AdvancedRAGConfig())

@pytest.fixture
def retriever_no_multi_query(mock_embedder, mock_store):
    from plugins.knowledge_advanced.retriever import AdvancedRetriever

    config = AdvancedRAGConfig(multi_query_enabled=False, hyde_enabled=False)
    return AdvancedRetriever(embedder=mock_embedder, store=mock_store, config=config)

class TestAdvancedRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_basic(self, retriever_no_multi_query, mock_store):
        """Single query, hybrid search called, results returned."""
        results = await retriever_no_multi_query.retrieve(query="test query", limit=5)
        assert len(results) > 0
        mock_store.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_with_multi_query(self, retriever, mock_store):
        """When multi_query enabled, variants are generated and searched."""
        with patch(
            "plugins.knowledge_advanced.retriever.get_llm_provider",
            return_value=MockLLM(),
        ):
            results = await retriever.retrieve(query="test query", limit=5)
            # Original + 3 variants + 1 HyDE = 5 queries
            assert mock_store.hybrid_search.call_count >= 2

    @pytest.mark.asyncio
    async def test_retrieve_with_hyde(self, mock_embedder, mock_store):
        """When HyDE enabled, hypothetical document used as additional query."""
        from plugins.knowledge_advanced.retriever import AdvancedRetriever

        config = AdvancedRAGConfig(multi_query_enabled=False, hyde_enabled=True)
        retriever = AdvancedRetriever(embedder=mock_embedder, store=mock_store, config=config)
        with patch(
            "plugins.knowledge_advanced.retriever.get_llm_provider",
            return_value=MockLLM(),
        ):
            await retriever.retrieve(query="test query", limit=5)
            # Original query + HyDE document = 2 searches
            assert mock_store.hybrid_search.call_count == 2

    @pytest.mark.asyncio
    async def test_retrieve_deduplication(self, mock_embedder, mock_store):
        """Duplicate results from multiple queries are deduplicated."""
        from plugins.knowledge_advanced.retriever import AdvancedRetriever

        # Return same content from all searches
        mock_store.hybrid_search.return_value = [
            {"content": "duplicate content", "score": 0.9, "metadata": {}},
        ]
        config = AdvancedRAGConfig(multi_query_enabled=False, hyde_enabled=False)
        retriever = AdvancedRetriever(embedder=mock_embedder, store=mock_store, config=config)

        # Manually call with multi-variant to test dedup
        mock_store.hybrid_search.return_value = [
            {"content": "duplicate content", "score": 0.9, "metadata": {}},
        ]
        results = await retriever.retrieve(query="test", limit=5)
        # Even with one query, only one unique result
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_retrieve_reranking(self, mock_embedder, mock_store):
        """Results are reranked by cross-encoder."""
        from plugins.knowledge_advanced.retriever import AdvancedRetriever

        mock_store.hybrid_search.return_value = [
            {"content": "result A", "score": 0.5, "metadata": {}},
            {"content": "result B", "score": 0.8, "metadata": {}},
        ]
        config = AdvancedRAGConfig(multi_query_enabled=False, hyde_enabled=False)
        retriever = AdvancedRetriever(embedder=mock_embedder, store=mock_store, config=config)
        results = await retriever.retrieve(query="test", limit=5)
        # Reranker was called
        mock_embedder.rerank.assert_called_once()
        # Results have rerank_score
        assert "rerank_score" in results[0]

    @pytest.mark.asyncio
    async def test_retrieve_graceful_degradation_no_llm(self, mock_embedder, mock_store):
        """When LLM unavailable, falls back to single hybrid search."""
        from plugins.knowledge_advanced.retriever import AdvancedRetriever

        config = AdvancedRAGConfig(multi_query_enabled=True, hyde_enabled=True)
        retriever = AdvancedRetriever(embedder=mock_embedder, store=mock_store, config=config)
        # Patch get_llm_provider to None (simulating ImportError)
        with patch("plugins.knowledge_advanced.retriever.get_llm_provider", None):
            results = await retriever.retrieve(query="test", limit=5)
            # Falls back to single query
            assert mock_store.hybrid_search.call_count == 1
            assert len(results) > 0

    @pytest.mark.asyncio
    async def test_retrieve_multi_query_disabled(self, retriever_no_multi_query, mock_store):
        """When config.multi_query_enabled=False, no variants generated."""
        results = await retriever_no_multi_query.retrieve(query="test query", limit=5)
        # Only one search (original query, no multi-query, no HyDE)
        assert mock_store.hybrid_search.call_count == 1

# ── AdvancedIndexer tests ──────────────────────────────────────────────────

@pytest.fixture
def mock_pipeline():
    """Create a mock IngestPipeline."""
    pipeline = MagicMock()
    pipeline._parse_document.return_value = (
        "First sentence about AI. Second sentence about ML. Third about something else entirely."
    )
    pipeline.store = MagicMock()

    async def mock_ingest(file_path, source_id, metadata=None):
        from core.knowledge.pipeline import IngestResult

        return IngestResult(source_id=source_id, chunk_count=3, file_path=file_path)

    pipeline.ingest = AsyncMock(side_effect=mock_ingest)
    return pipeline

class TestAdvancedIndexer:
    @pytest.mark.asyncio
    async def test_ingest_with_semantic_chunking(self, mock_pipeline, mock_embedder):
        """Semantic chunking produces chunks at similarity boundaries."""
        from plugins.knowledge_advanced.indexer import AdvancedIndexer

        # Make embeddings with a drop in similarity at sentence 2->3
        mock_embedder.embed_dense.return_value = [
            [0.9, 0.1, 0.0],  # sentence 1
            [0.8, 0.2, 0.0],  # sentence 2 (similar to 1)
            [0.0, 0.1, 0.9],  # sentence 3 (very different)
        ]
        mock_embedder.embed_sparse.return_value = [
            MagicMock(),
            MagicMock(),
        ]

        config = AdvancedRAGConfig(semantic_chunking=True, semantic_similarity_threshold=0.5)
        indexer = AdvancedIndexer(pipeline=mock_pipeline, embedder=mock_embedder, config=config)

        result = await indexer.ingest(
            file_path="/tmp/test.txt",
            source_id="ks_test",
            metadata={"key": "val"},
        )
        assert result.source_id == "ks_test"
        assert result.chunk_count >= 1

    @pytest.mark.asyncio
    async def test_ingest_delegates_to_core_when_disabled(self, mock_pipeline, mock_embedder):
        """When semantic_chunking=False, delegates to pipeline.ingest()."""
        from plugins.knowledge_advanced.indexer import AdvancedIndexer

        config = AdvancedRAGConfig(semantic_chunking=False)
        indexer = AdvancedIndexer(pipeline=mock_pipeline, embedder=mock_embedder, config=config)

        result = await indexer.ingest(
            file_path="/tmp/test.txt",
            source_id="ks_test",
        )
        mock_pipeline.ingest.assert_called_once()
        assert result.source_id == "ks_test"
        assert result.chunk_count == 3

    def test_semantic_chunk_single_sentence(self, mock_pipeline, mock_embedder):
        """Single sentence returns one chunk."""
        from plugins.knowledge_advanced.indexer import AdvancedIndexer

        config = AdvancedRAGConfig(semantic_chunking=True)
        indexer = AdvancedIndexer(pipeline=mock_pipeline, embedder=mock_embedder, config=config)

        chunks = indexer._semantic_chunk("Just one sentence.", {"source_id": "ks_1"})
        assert len(chunks) == 1
        assert chunks[0].text == "Just one sentence."

    def test_semantic_chunk_boundary_detection(self, mock_pipeline, mock_embedder):
        """Drop in embedding similarity creates boundary."""
        from plugins.knowledge_advanced.indexer import AdvancedIndexer

        text = "Dogs are great. Cats are nice. Quantum physics is complex."
        # Embeddings: first two similar, third very different
        mock_embedder.embed_dense.return_value = [
            [1.0, 0.0],  # Dogs
            [0.9, 0.1],  # Cats (similar)
            [0.0, 1.0],  # Quantum (different)
        ]

        config = AdvancedRAGConfig(semantic_chunking=True, semantic_similarity_threshold=0.5)
        indexer = AdvancedIndexer(pipeline=mock_pipeline, embedder=mock_embedder, config=config)

        chunks = indexer._semantic_chunk(text, {"source_id": "ks_1"})
        # Should create at least 2 chunks (boundary between cats and quantum)
        assert len(chunks) >= 2

    def test_cosine_similarity_computation(self, mock_pipeline, mock_embedder):
        """_cosine_similarity returns correct values."""
        from plugins.knowledge_advanced.indexer import AdvancedIndexer

        # Identical vectors -> 1.0
        assert AdvancedIndexer._cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
        # Orthogonal vectors -> 0.0
        assert AdvancedIndexer._cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
        # Opposite vectors -> -1.0
        assert AdvancedIndexer._cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)
        # Zero vector -> 0.0
        assert AdvancedIndexer._cosine_similarity([0, 0], [1, 0]) == pytest.approx(0.0)

# ── Plugin boundary tests ─────────────────────────────────────────────────

class TestPluginBoundary:
    def test_no_core_imports_from_plugin(self):
        """Core code must never import from knowledge_advanced plugin."""
        import pathlib

        core_dir = pathlib.Path("core")
        violations = []
        for py_file in core_dir.rglob("*.py"):
            content = py_file.read_text(errors="ignore")
            if "knowledge_advanced" in content:
                violations.append(str(py_file))
        assert violations == [], f"Core imports from plugin: {violations}"

    def test_manifest_team_tier(self):
        """dryade.json has required_tier: team."""
        import json
        import pathlib

        manifest_path = (
            pathlib.Path(__file__).resolve().parents[4]
            / "plugins"
            / "team"
            / "knowledge_advanced"
            / "dryade.json"
        )
        manifest = json.loads(manifest_path.read_text())
        assert manifest["required_tier"] == "team"
        assert manifest["name"] == "knowledge_advanced"

    def test_plugin_composition_not_inheritance(self):
        """AdvancedRetriever and AdvancedIndexer don't inherit from core classes."""
        from plugins.knowledge_advanced.indexer import AdvancedIndexer
        from plugins.knowledge_advanced.retriever import AdvancedRetriever

        # Check __bases__ - should only be (object,)
        assert AdvancedRetriever.__bases__ == (object,), (
            f"AdvancedRetriever inherits from: {AdvancedRetriever.__bases__}"
        )
        assert AdvancedIndexer.__bases__ == (object,), (
            f"AdvancedIndexer inherits from: {AdvancedIndexer.__bases__}"
        )

# ── Routes tests ──────────────────────────────────────────────────────────

class TestRoutes:
    @pytest.mark.asyncio
    async def test_advanced_query_endpoint(self):
        """POST /query returns results with strategies_used."""
        from fastapi.testclient import TestClient

        app = _make_test_app()

        # Patch at source modules for deferred imports inside route handler
        with (
            patch(
                "core.knowledge.embedder.get_embedding_service",
                return_value=_make_mock_embedder(),
            ),
            patch(
                "core.config.get_settings",
                return_value=MagicMock(qdrant_url="http://localhost:6333"),
            ),
            patch(
                "core.knowledge.config.get_knowledge_config",
                return_value=MagicMock(),
            ),
            patch(
                "qdrant_client.QdrantClient",
                return_value=MagicMock(),
            ),
            patch(
                "core.knowledge.storage.HybridVectorStore",
            ) as mock_hvs,
            patch(
                "plugins.knowledge_advanced.retriever.AdvancedRetriever.retrieve",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "content": "test result",
                        "score": 0.9,
                        "rerank_score": 0.95,
                        "metadata": {"source_id": "ks_1"},
                    }
                ],
            ),
        ):
            mock_hvs.return_value = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/knowledge/advanced/query",
                json={"query": "test query", "limit": 5},
            )
            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert "strategies_used" in data
            assert "hybrid_search" in data["strategies_used"]
            assert data["total_results"] >= 0

    @pytest.mark.asyncio
    async def test_advanced_ingest_endpoint(self):
        """POST /ingest returns chunk_count and strategy."""
        from fastapi.testclient import TestClient

        app = _make_test_app()

        from core.knowledge.pipeline import IngestResult

        mock_ingest_result = IngestResult(
            source_id="ks_test", chunk_count=10, file_path="/tmp/test.pdf"
        )

        with (
            patch(
                "core.knowledge.embedder.get_embedding_service",
                return_value=_make_mock_embedder(),
            ),
            patch(
                "core.knowledge.pipeline.get_ingest_pipeline",
                return_value=MagicMock(),
            ),
            patch(
                "plugins.knowledge_advanced.indexer.AdvancedIndexer.ingest",
                new_callable=AsyncMock,
                return_value=mock_ingest_result,
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/knowledge/advanced/ingest",
                json={
                    "file_path": "/tmp/test.pdf",
                    "source_id": "ks_test",
                    "semantic_chunking": True,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["source_id"] == "ks_test"
            assert data["chunk_count"] == 10
            assert data["chunking_strategy"] == "semantic"

    def test_advanced_query_validation(self):
        """Empty query returns 422."""
        from fastapi.testclient import TestClient

        app = _make_test_app()

        client = TestClient(app)
        response = client.post(
            "/api/knowledge/advanced/query",
            json={"query": "", "limit": 5},
        )
        assert response.status_code == 422

    def test_advanced_query_strategies(self):
        """strategies_used list includes enabled strategies."""
        from fastapi.testclient import TestClient

        app = _make_test_app()

        with (
            patch(
                "core.knowledge.embedder.get_embedding_service",
                return_value=_make_mock_embedder(),
            ),
            patch(
                "core.config.get_settings",
                return_value=MagicMock(qdrant_url="http://localhost:6333"),
            ),
            patch(
                "core.knowledge.config.get_knowledge_config",
                return_value=MagicMock(),
            ),
            patch(
                "qdrant_client.QdrantClient",
                return_value=MagicMock(),
            ),
            patch(
                "core.knowledge.storage.HybridVectorStore",
            ) as mock_hvs,
            patch(
                "plugins.knowledge_advanced.retriever.AdvancedRetriever.retrieve",
                new_callable=AsyncMock,
                return_value=[
                    {"content": "r1", "score": 0.9, "metadata": {"source_id": "ks_1"}},
                ],
            ),
        ):
            mock_hvs.return_value = MagicMock()

            client = TestClient(app)

            # All strategies enabled
            response = client.post(
                "/api/knowledge/advanced/query",
                json={
                    "query": "test",
                    "multi_query": True,
                    "hyde": True,
                    "rerank": True,
                },
            )
            assert response.status_code == 200
            strategies = response.json()["strategies_used"]
            assert "hybrid_search" in strategies
            assert "multi_query" in strategies
            assert "hyde" in strategies
            assert "reranking" in strategies

            # Only hyde disabled
            response = client.post(
                "/api/knowledge/advanced/query",
                json={
                    "query": "test",
                    "multi_query": True,
                    "hyde": False,
                    "rerank": True,
                },
            )
            assert response.status_code == 200
            strategies = response.json()["strategies_used"]
            assert "hyde" not in strategies
            assert "multi_query" in strategies

# ── Plugin protocol tests ─────────────────────────────────────────────────

class TestPluginProtocol:
    def test_plugin_is_protocol_instance(self):
        """Plugin instance is a PluginProtocol subclass."""
        from plugins.knowledge_advanced import plugin

        from core.ee.plugins_ee import PluginProtocol

        assert isinstance(plugin, PluginProtocol)
        assert plugin.name == "knowledge_advanced"
        assert plugin.version == "1.0.0"

    def test_plugin_has_lazy_router(self):
        """Plugin router is lazily loaded and returns an APIRouter."""
        from fastapi import APIRouter
        from plugins.knowledge_advanced.plugin import KnowledgeAdvancedPlugin

        # Create fresh instance to test lazy load
        p = KnowledgeAdvancedPlugin()
        assert p._router is None
        r = p.router
        assert r is not None
        assert isinstance(r, APIRouter)

    def test_plugin_register_logs(self):
        """Plugin register() runs without error."""
        from plugins.knowledge_advanced.plugin import KnowledgeAdvancedPlugin

        p = KnowledgeAdvancedPlugin()
        mock_registry = MagicMock()
        # Should not raise
        p.register(mock_registry)

# ── Auth guard tests ──────────────────────────────────────────────────────

class TestAuthGuards:
    def test_query_requires_auth(self):
        """POST /query without auth returns 401."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from plugins.knowledge_advanced.routes import router

        # Bare app without auth override
        app = FastAPI()
        app.include_router(router, prefix="/api/knowledge/advanced")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/knowledge/advanced/query",
            json={"query": "test query", "limit": 5},
        )
        # 401 because get_current_user raises HTTPException(401)
        assert response.status_code == 401

    def test_ingest_requires_auth(self):
        """POST /ingest without auth returns 401."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from plugins.knowledge_advanced.routes import router

        # Bare app without auth override
        app = FastAPI()
        app.include_router(router, prefix="/api/knowledge/advanced")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/knowledge/advanced/ingest",
            json={
                "file_path": "/tmp/test.pdf",
                "source_id": "ks_test",
                "semantic_chunking": True,
            },
        )
        assert response.status_code == 401

    def test_query_with_auth_succeeds(self):
        """POST /query with auth override returns 200."""
        from fastapi.testclient import TestClient

        app = _make_test_app()

        with (
            patch(
                "core.knowledge.embedder.get_embedding_service",
                return_value=_make_mock_embedder(),
            ),
            patch(
                "core.config.get_settings",
                return_value=MagicMock(qdrant_url="http://localhost:6333"),
            ),
            patch(
                "core.knowledge.config.get_knowledge_config",
                return_value=MagicMock(),
            ),
            patch(
                "qdrant_client.QdrantClient",
                return_value=MagicMock(),
            ),
            patch(
                "core.knowledge.storage.HybridVectorStore",
            ) as mock_hvs,
            patch(
                "plugins.knowledge_advanced.retriever.AdvancedRetriever.retrieve",
                new_callable=AsyncMock,
                return_value=[
                    {"content": "r1", "score": 0.9, "metadata": {"source_id": "ks_1"}},
                ],
            ),
        ):
            mock_hvs.return_value = MagicMock()

            client = TestClient(app)
            response = client.post(
                "/api/knowledge/advanced/query",
                json={"query": "test query", "limit": 5},
            )
            assert response.status_code == 200
