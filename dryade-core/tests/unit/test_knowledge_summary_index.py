"""Unit tests for SummaryIndex.

VectorStoreBackend and EmbeddingService are mocked -- no services needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from core.knowledge.summary_index import SummaryIndex

class TestSummaryIndex:
    """Tests for SummaryIndex document-level retrieval."""

    def test_add_summary_stores_with_is_summary_flag(self):
        mock_store = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_dense.return_value = [[0.1] * 384]

        index = SummaryIndex(store=mock_store, embedder=mock_embedder)
        index.add_summary("doc1", "This is a summary", metadata={"title": "Doc 1"})

        mock_store.add.assert_called_once()
        call_kwargs = mock_store.add.call_args
        metadata = (
            call_kwargs.kwargs.get("metadata")
            or call_kwargs[1].get("metadata")
            or call_kwargs[0][1]
        )
        assert metadata[0]["is_summary"] is True
        assert metadata[0]["source_id"] == "doc1"
        assert metadata[0]["title"] == "Doc 1"

    def test_search_filters_by_is_summary(self):
        mock_store = MagicMock()
        mock_store.dense_only_search.return_value = [
            {"content": "Summary text", "score": 0.9, "metadata": {"source_id": "doc1"}}
        ]
        mock_embedder = MagicMock()
        mock_embedder.embed_dense_single.return_value = [0.1] * 384

        index = SummaryIndex(store=mock_store, embedder=mock_embedder)
        results = index.search("query text", limit=5)

        mock_store.dense_only_search.assert_called_once()
        call_kwargs = mock_store.dense_only_search.call_args
        metadata_filter = call_kwargs.kwargs.get("metadata_filter")
        assert metadata_filter == {"is_summary": True}
        assert len(results) == 1

    def test_generate_summary_short_text(self):
        text = "Short text."
        result = SummaryIndex.generate_summary(text, max_length=500)
        assert result == text

    def test_generate_summary_truncates_at_sentence(self):
        text = "First sentence. Second sentence. Third sentence is much longer and goes beyond the limit."
        result = SummaryIndex.generate_summary(text, max_length=50)
        assert result.endswith(".")
        assert len(result) <= 51  # 50 + potential period

    def test_generate_summary_ellipsis_fallback(self):
        text = "A" * 600  # No sentence boundaries
        result = SummaryIndex.generate_summary(text, max_length=500)
        assert result.endswith("...")
        assert len(result) <= 503  # 500 + "..."
