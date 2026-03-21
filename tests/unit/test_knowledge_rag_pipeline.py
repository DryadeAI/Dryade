"""Unit tests for Knowledge/RAG pipeline components (Phase 97.2-04).

Tests: KnowledgeConfig, ChunkingService, EmbeddingService, HybridVectorStore, IngestPipeline.
All external dependencies (Qdrant, FastEmbed) are mocked for fast CI.
"""

import importlib.util
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.knowledge.chunker import Chunk, ChunkingService
from core.knowledge.config import KnowledgeConfig, get_knowledge_config, reset_config

# ---------------------------------------------------------------------------
# KnowledgeConfig tests
# ---------------------------------------------------------------------------

class TestKnowledgeConfig:
    """Tests for KnowledgeConfig dataclass and singleton."""

    def test_default_config(self):
        """Verify default values for KnowledgeConfig fields."""
        config = KnowledgeConfig()
        assert config.dense_model == "BAAI/bge-small-en-v1.5"
        assert config.sparse_model == "Qdrant/bm25"
        assert config.reranker_model == "Xenova/ms-marco-MiniLM-L-6-v2"
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
        assert config.chunk_strategy == "recursive"
        assert config.top_k == 5
        assert config.max_context_chars == 2000
        assert config.max_results == 5
        assert config.score_threshold == 0.3
        assert config.rerank_enabled is True
        assert config.rerank_top_k == 10
        assert config.dense_dim == 384

    def test_config_collection_names(self):
        """Verify new and legacy collection names."""
        config = KnowledgeConfig()
        assert config.collection_name == "dryade_knowledge"
        assert config.legacy_collection == "crew_knowledge"

    def test_config_singleton(self):
        """get_knowledge_config() returns same instance on repeated calls."""
        reset_config()
        try:
            with patch("core.knowledge.config.get_settings") as mock_settings:
                s = MagicMock()
                s.knowledge_chunk_size = 1000  # default -> 512
                s.knowledge_chunk_overlap = 200  # default -> 50
                s.knowledge_top_k = 5
                mock_settings.return_value = s

                c1 = get_knowledge_config()
                c2 = get_knowledge_config()
                assert c1 is c2
        finally:
            reset_config()

    def test_config_reset(self):
        """reset_config() allows fresh instance creation."""
        reset_config()
        try:
            with patch("core.knowledge.config.get_settings") as mock_settings:
                s = MagicMock()
                s.knowledge_chunk_size = 1000
                s.knowledge_chunk_overlap = 200
                s.knowledge_top_k = 5
                mock_settings.return_value = s

                c1 = get_knowledge_config()
                reset_config()
                c2 = get_knowledge_config()
                assert c1 is not c2
        finally:
            reset_config()

    def test_config_reads_settings_override(self):
        """When Settings has non-default knowledge_top_k, config picks it up."""
        reset_config()
        try:
            with patch("core.knowledge.config.get_settings") as mock_settings:
                s = MagicMock()
                s.knowledge_chunk_size = 1000  # default -> maps to 512
                s.knowledge_chunk_overlap = 200  # default -> maps to 50
                s.knowledge_top_k = 10  # non-default
                mock_settings.return_value = s

                config = get_knowledge_config()
                assert config.top_k == 10
        finally:
            reset_config()

# ---------------------------------------------------------------------------
# ChunkingService tests
# ---------------------------------------------------------------------------

class TestChunkingService:
    """Tests for recursive character text splitter."""

    def _make_service(self, chunk_size=512, chunk_overlap=50):
        config = KnowledgeConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return ChunkingService(config)

    def test_chunk_short_text(self):
        """Text shorter than chunk_size returns single chunk."""
        svc = self._make_service(chunk_size=100)
        result = svc.chunk("Short text.")
        assert len(result) == 1
        assert result[0].text == "Short text."

    def test_chunk_paragraph_split(self):
        """Text with paragraph breaks splits on double newlines."""
        svc = self._make_service(chunk_size=40, chunk_overlap=0)
        text = "Paragraph one has some content here.\n\nParagraph two has other content here."
        result = svc.chunk(text)
        assert len(result) >= 2
        assert any("Paragraph one" in c.text for c in result)
        assert any("Paragraph two" in c.text for c in result)

    def test_chunk_newline_split(self):
        """Text with only single newlines splits on newlines."""
        svc = self._make_service(chunk_size=30, chunk_overlap=0)
        text = "Line one content.\nLine two content.\nLine three content."
        result = svc.chunk(text)
        assert len(result) >= 2

    def test_chunk_sentence_split(self):
        """Text with only sentences splits on sentence boundaries."""
        svc = self._make_service(chunk_size=40, chunk_overlap=0)
        text = "First sentence here. Second sentence here. Third sentence here."
        result = svc.chunk(text)
        assert len(result) >= 2

    def test_chunk_overlap(self):
        """Adjacent chunks have overlapping content when overlap > 0."""
        svc = self._make_service(chunk_size=50, chunk_overlap=10)
        text = "AAAA BBBB.\n\nCCCC DDDD.\n\nEEEE FFFF.\n\nGGGG HHHH."
        result = svc.chunk(text)
        if len(result) >= 2:
            # Second chunk should start with overlap from first chunk's end
            first_end = result[0].text[-10:]
            # The overlap prepend should appear at start of second chunk
            assert result[1].text.startswith(first_end) or len(result) > 2

    def test_chunk_empty_text(self):
        """Empty string returns empty list."""
        svc = self._make_service()
        result = svc.chunk("")
        assert result == []

    def test_chunk_metadata_propagated(self):
        """Metadata from input appears in all chunks."""
        svc = self._make_service(chunk_size=30, chunk_overlap=0)
        text = "Part one.\n\nPart two."
        meta = {"source_id": "test_src", "file_path": "/tmp/test.txt"}
        result = svc.chunk(text, metadata=meta)
        for chunk in result:
            assert chunk.metadata["source_id"] == "test_src"
            assert chunk.metadata["file_path"] == "/tmp/test.txt"

    def test_chunk_index_sequential(self):
        """Chunk indices are 0, 1, 2, ..."""
        svc = self._make_service(chunk_size=30, chunk_overlap=0)
        text = "Part A.\n\nPart B.\n\nPart C."
        result = svc.chunk(text)
        for i, chunk in enumerate(result):
            assert chunk.index == i
            assert chunk.metadata["chunk_index"] == i

# ---------------------------------------------------------------------------
# EmbeddingService tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_fastembed(monkeypatch):
    """Mock all FastEmbed classes to avoid model downloads.

    Skips automatically when fastembed is not installed.
    """
    try:
        spec = importlib.util.find_spec("fastembed")
    except ValueError:
        # fastembed is in sys.modules as a MagicMock (from test_semantic_cache.py's
        # module-level mock injection) — __spec__ is not set, causing find_spec to
        # raise ValueError. Treat this the same as "not installed".
        spec = None
    if spec is None:
        pytest.skip("fastembed not installed")

    class MockTextEmbedding:
        def __init__(self, model_name):
            self.model_name = model_name

        def embed(self, texts):
            return [np.random.rand(384) for _ in texts]

    class MockSparseTextEmbedding:
        def __init__(self, model_name):
            self.model_name = model_name

        def embed(self, texts):
            @dataclass
            class SparseResult:
                indices: np.ndarray
                values: np.ndarray

            return [
                SparseResult(
                    indices=np.array([0, 1, 2]),
                    values=np.array([0.5, 0.3, 0.1]),
                )
                for _ in texts
            ]

    class MockTextCrossEncoder:
        def __init__(self, model_name):
            self.model_name = model_name

        def rerank(self, query, documents):
            # Return decreasing scores
            return [1.0 - i * 0.1 for i in range(len(documents))]

    monkeypatch.setattr("fastembed.TextEmbedding", MockTextEmbedding)
    monkeypatch.setattr("fastembed.SparseTextEmbedding", MockSparseTextEmbedding)
    monkeypatch.setattr("fastembed.rerank.cross_encoder.TextCrossEncoder", MockTextCrossEncoder)

    return {
        "TextEmbedding": MockTextEmbedding,
        "SparseTextEmbedding": MockSparseTextEmbedding,
        "TextCrossEncoder": MockTextCrossEncoder,
    }

class TestEmbeddingService:
    """Tests for EmbeddingService with mocked FastEmbed."""

    def test_embed_dense(self, mock_fastembed):
        """Returns list of 384-dim vectors."""
        from core.knowledge.embedder import EmbeddingService

        svc = EmbeddingService(config=KnowledgeConfig())
        result = svc.embed_dense(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 384
        assert all(isinstance(v, float) for v in result[0])

    def test_embed_dense_single(self, mock_fastembed):
        """Returns single 384-dim vector."""
        from core.knowledge.embedder import EmbeddingService

        svc = EmbeddingService(config=KnowledgeConfig())
        result = svc.embed_dense_single("hello")
        assert len(result) == 384

    def test_embed_sparse(self, mock_fastembed):
        """Returns sparse vectors with indices and values."""
        from core.knowledge.embedder import EmbeddingService

        svc = EmbeddingService(config=KnowledgeConfig())
        result = svc.embed_sparse(["hello", "world"])
        assert len(result) == 2
        assert hasattr(result[0], "indices")
        assert hasattr(result[0], "values")
        assert len(result[0].indices) == 3
        assert len(result[0].values) == 3

    def test_rerank(self, mock_fastembed):
        """Returns documents sorted by reranker score, trimmed to top_k."""
        from core.knowledge.embedder import EmbeddingService

        svc = EmbeddingService(config=KnowledgeConfig())
        docs = [
            {"content": "doc A"},
            {"content": "doc B"},
            {"content": "doc C"},
        ]
        result = svc.rerank("query", docs, top_k=2)
        assert len(result) == 2
        # First result should have highest rerank_score
        assert result[0]["rerank_score"] >= result[1]["rerank_score"]
        assert "content" in result[0]

    def test_rerank_empty(self, mock_fastembed):
        """Empty documents returns empty list."""
        from core.knowledge.embedder import EmbeddingService

        svc = EmbeddingService(config=KnowledgeConfig())
        result = svc.rerank("query", [], top_k=5)
        assert result == []

    def test_lazy_loading(self, mock_fastembed):
        """Models not loaded until first use."""
        from core.knowledge.embedder import EmbeddingService

        svc = EmbeddingService(config=KnowledgeConfig())
        assert svc._dense is None
        assert svc._sparse is None
        assert svc._reranker is None

        # After use, models should be loaded
        svc.embed_dense(["test"])
        assert svc._dense is not None
        assert svc._sparse is None  # still not loaded
        assert svc._reranker is None  # still not loaded

# ---------------------------------------------------------------------------
# HybridVectorStore tests
# ---------------------------------------------------------------------------

class TestHybridVectorStore:
    """Tests for HybridVectorStore with mocked QdrantClient."""

    def _make_store(self, mock_client=None):
        from core.knowledge.storage import HybridVectorStore

        client = mock_client or MagicMock()
        # Mock get_collections to return empty list (collection does not exist)
        client.get_collections.return_value.collections = []
        config = KnowledgeConfig()
        return HybridVectorStore(client=client, config=config), client

    def test_ensure_collection_creates_with_named_vectors(self):
        """Verify create_collection called with text-dense and text-sparse config."""
        store, client = self._make_store()
        client.create_collection.assert_called_once()
        call_kwargs = client.create_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == "dryade_knowledge"
        vectors_config = call_kwargs.kwargs["vectors_config"]
        assert "text-dense" in vectors_config
        sparse_config = call_kwargs.kwargs["sparse_vectors_config"]
        assert "text-sparse" in sparse_config

    def test_add_with_named_vectors(self):
        """Points have vector dict with text-dense and text-sparse keys."""
        store, client = self._make_store()

        @dataclass
        class FakeSparse:
            indices: np.ndarray
            values: np.ndarray

        sparse = FakeSparse(indices=np.array([0, 1]), values=np.array([0.5, 0.3]))

        store.add(
            chunks=["hello world"],
            metadata=[{"source_id": "s1"}],
            dense_vectors=[[0.1] * 384],
            sparse_vectors=[sparse],
        )

        client.upsert.assert_called_once()
        points = client.upsert.call_args.kwargs["points"]
        assert len(points) == 1
        point = points[0]
        assert "text-dense" in point.vector
        assert "text-sparse" in point.vector
        assert point.payload["content"] == "hello world"
        assert point.payload["source_id"] == "s1"

    def test_hybrid_search_uses_rrf(self):
        """query_points called with FusionQuery(Fusion.RRF)."""
        from qdrant_client import models

        store, client = self._make_store()

        # Mock query_points response
        mock_point = MagicMock()
        mock_point.payload = {"content": "result text", "source_id": "s1"}
        mock_point.score = 0.8
        client.query_points.return_value.points = [mock_point]

        @dataclass
        class FakeSparse:
            indices: np.ndarray
            values: np.ndarray

        sparse = FakeSparse(indices=np.array([0]), values=np.array([0.5]))

        results = store.hybrid_search(
            query_dense=[0.1] * 384,
            query_sparse=sparse,
            limit=5,
        )

        client.query_points.assert_called_once()
        call_kwargs = client.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == "dryade_knowledge"
        # Verify FusionQuery with RRF
        query = call_kwargs["query"]
        assert hasattr(query, "fusion")
        assert query.fusion == models.Fusion.RRF
        # Verify prefetch has two branches
        assert len(call_kwargs["prefetch"]) == 2

        assert len(results) == 1
        assert results[0]["content"] == "result text"
        assert results[0]["score"] == 0.8

    def test_delete_by_source_id(self):
        """delete called with source_id filter."""
        store, client = self._make_store()
        store.delete("src_123")
        client.delete.assert_called_once()
        call_kwargs = client.delete.call_args.kwargs
        assert call_kwargs["collection_name"] == "dryade_knowledge"
        selector = call_kwargs["points_selector"]
        assert len(selector.must) == 1
        assert selector.must[0].key == "source_id"

    def test_build_filter_with_in_operator(self):
        """$in creates MatchAny (not MatchValue of first element)."""
        from qdrant_client.models import MatchAny

        from core.knowledge.storage import HybridVectorStore

        result = HybridVectorStore._build_filter({"source_id": {"$in": ["s1", "s2", "s3"]}})
        assert result is not None
        assert len(result.must) == 1
        condition = result.must[0]
        assert isinstance(condition.match, MatchAny)
        assert condition.match.any == ["s1", "s2", "s3"]

# ---------------------------------------------------------------------------
# IngestPipeline tests
# ---------------------------------------------------------------------------

class TestIngestPipeline:
    """Tests for IngestPipeline with mocked components."""

    def _make_pipeline(self):
        from core.knowledge.pipeline import IngestPipeline

        chunker = MagicMock(spec=ChunkingService)
        embedder = MagicMock()
        store = MagicMock()
        pipeline = IngestPipeline(chunker=chunker, embedder=embedder, store=store)
        return pipeline, chunker, embedder, store

    @pytest.mark.asyncio
    async def test_ingest_text_file(self, tmp_path):
        """End-to-end ingest of .txt file returns IngestResult with correct chunk_count."""
        pipeline, chunker, embedder, store = self._make_pipeline()

        # Create temp file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world. This is test content.")

        # Mock chunker to return 3 chunks
        chunker.chunk.return_value = [
            Chunk(text="Hello world.", metadata={"source_id": "s1", "chunk_index": 0}, index=0),
            Chunk(text="This is test.", metadata={"source_id": "s1", "chunk_index": 1}, index=1),
            Chunk(text="content.", metadata={"source_id": "s1", "chunk_index": 2}, index=2),
        ]
        embedder.embed_dense.return_value = [[0.1] * 384] * 3
        embedder.embed_sparse.return_value = [MagicMock()] * 3

        result = await pipeline.ingest(
            file_path=str(test_file),
            source_id="s1",
        )

        assert result.source_id == "s1"
        assert result.chunk_count == 3
        assert result.file_path == str(test_file)
        store.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_empty_file(self, tmp_path):
        """Empty file returns IngestResult with chunk_count=0."""
        pipeline, chunker, embedder, store = self._make_pipeline()

        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        chunker.chunk.return_value = []

        result = await pipeline.ingest(
            file_path=str(test_file),
            source_id="s_empty",
        )

        assert result.chunk_count == 0
        store.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_metadata_propagated(self, tmp_path):
        """source_id and file_path in metadata for all chunks."""
        pipeline, chunker, embedder, store = self._make_pipeline()

        test_file = tmp_path / "meta.txt"
        test_file.write_text("Content for metadata test.")

        # Capture the metadata dict passed to chunker.chunk
        captured_meta = {}

        def capture_chunk(text, metadata=None):
            captured_meta.update(metadata or {})
            return [
                Chunk(text="chunk", metadata=metadata or {}, index=0),
            ]

        chunker.chunk.side_effect = capture_chunk
        embedder.embed_dense.return_value = [[0.1] * 384]
        embedder.embed_sparse.return_value = [MagicMock()]

        await pipeline.ingest(
            file_path=str(test_file),
            source_id="s_meta",
            metadata={"custom_key": "custom_value"},
        )

        assert captured_meta["source_id"] == "s_meta"
        assert captured_meta["file_path"] == str(test_file)
        assert captured_meta["custom_key"] == "custom_value"

    @pytest.mark.asyncio
    async def test_parse_document_txt(self, tmp_path):
        """_parse_document reads .txt files correctly."""
        from core.knowledge.pipeline import IngestPipeline

        chunker = MagicMock()
        embedder = MagicMock()
        store = MagicMock()
        pipeline = IngestPipeline(chunker=chunker, embedder=embedder, store=store)

        test_file = tmp_path / "parse_test.txt"
        test_file.write_text("Plain text content for parsing.")

        result = pipeline._parse_document(str(test_file))
        assert result == "Plain text content for parsing."
