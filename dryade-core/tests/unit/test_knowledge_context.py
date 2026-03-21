"""Tests for knowledge context builder (Phase 94.1, updated Phase 97.2-04).

Tests get_knowledge_context() with hybrid search (dense+sparse+RRF fusion)
and cross-encoder reranking. All external dependencies mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

def _mock_embedding_service():
    """Create a mock EmbeddingService for hybrid search."""
    svc = MagicMock()
    svc.embed_dense_single.return_value = [0.1] * 384
    sparse = MagicMock()
    sparse.indices = [0, 1, 2]
    sparse.values = [0.5, 0.3, 0.1]
    svc.embed_sparse_single.return_value = sparse
    return svc

def _mock_hybrid_store(results=None):
    """Create a mock HybridVectorStore."""
    store = MagicMock()
    store.hybrid_search.return_value = results or []
    store.dense_only_search.return_value = results or []
    return store

# ---------------------------------------------------------------------------
# Core behavior tests (updated from Phase 94.1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_knowledge_context_empty_registry():
    """Returns None when no knowledge sources are registered."""
    with patch("core.knowledge.sources._knowledge_registry", {}):
        from core.knowledge.context import get_knowledge_context

        result = await get_knowledge_context("test query")
        assert result is None

@pytest.mark.asyncio
async def test_get_knowledge_context_formats_results():
    """Returns formatted string with source attribution and scores."""
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store(
        [
            {
                "content": "Python is a programming language.",
                "score": 0.92,
                "metadata": {"source_id": "src1"},
            },
            {
                "content": "FastAPI is a web framework.",
                "score": 0.85,
                "metadata": {"source_id": "src2"},
            },
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("What is Python?", rerank=False)

    assert result is not None
    assert "[1]" in result
    assert "[2]" in result
    assert "0.92" in result
    assert "0.85" in result
    assert "Python is a programming language." in result
    assert "FastAPI is a web framework." in result
    # Source attribution format
    assert "Source: src1" in result
    assert "relevance:" in result

@pytest.mark.asyncio
async def test_get_knowledge_context_respects_max_chars():
    """Truncates content to stay within max_chars total."""
    long_content = "A" * 500
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store(
        [
            {"content": long_content, "score": 0.90, "metadata": {"source_id": "s1"}},
            {"content": long_content, "score": 0.80, "metadata": {"source_id": "s2"}},
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("query", max_chars=200, rerank=False)

    assert result is not None
    # Format: "Source: s1\n  [1] (relevance: 0.90) ...\nSource: s2\n  [2] ..."
    # Each result has a Source header + content line = 2 lines per result
    lines = result.strip().split("\n")
    assert len(lines) == 4  # 2 results x 2 lines each (Source header + content)
    content_lines = [l for l in lines if l.startswith("  [")]
    for line in content_lines:
        assert "..." in line  # Content was truncated

@pytest.mark.asyncio
async def test_get_knowledge_context_handles_qdrant_error():
    """Returns None on storage error (no crash)."""
    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch(
            "core.knowledge.embedder.get_embedding_service",
            side_effect=Exception("Qdrant connection failed"),
        ):
            from core.knowledge.context import get_knowledge_context

            result = await get_knowledge_context("test query")

    assert result is None

@pytest.mark.asyncio
async def test_get_knowledge_context_handles_no_results():
    """Returns None when hybrid search returns empty results."""
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store([])  # empty results

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("obscure query")

    assert result is None

@pytest.mark.asyncio
async def test_get_knowledge_context_single_result():
    """Formats correctly with a single result (no rerank since <= 1 result)."""
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store(
        [
            {"content": "Single relevant chunk.", "score": 0.95, "metadata": {"source_id": "s1"}},
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("query")

    assert result is not None
    assert "[1]" in result
    assert "0.95" in result
    assert "Single relevant chunk." in result
    assert "[2]" not in result
    # Single result -- reranker should NOT be called
    mock_svc.rerank.assert_not_called()

# ---------------------------------------------------------------------------
# New hybrid search + reranking tests (Phase 97.2-04)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hybrid_search_with_reranking():
    """Verify rerank is called when enabled and results > 1."""
    mock_svc = _mock_embedding_service()
    mock_svc.rerank.return_value = [
        {
            "content": "Reranked A",
            "score": 0.9,
            "rerank_score": 0.99,
            "metadata": {"source_id": "s1"},
        },
        {
            "content": "Reranked B",
            "score": 0.7,
            "rerank_score": 0.85,
            "metadata": {"source_id": "s2"},
        },
    ]

    mock_store = _mock_hybrid_store(
        [
            {"content": "Result A", "score": 0.9, "metadata": {"source_id": "s1"}},
            {"content": "Result B", "score": 0.7, "metadata": {"source_id": "s2"}},
            {"content": "Result C", "score": 0.5, "metadata": {"source_id": "s3"}},
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("query", rerank=True)

    # Rerank should have been called with 3 results
    mock_svc.rerank.assert_called_once()
    call_args = mock_svc.rerank.call_args
    assert call_args[0][0] == "query"  # query string
    assert len(call_args[0][1]) == 3  # all 3 results passed to reranker

    # Result should contain reranked content
    assert result is not None
    assert "Reranked A" in result
    assert "0.99" in result  # rerank_score used in formatting

@pytest.mark.asyncio
async def test_hybrid_search_without_reranking():
    """Verify rerank not called when rerank=False."""
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store(
        [
            {"content": "Doc A", "score": 0.9, "metadata": {"source_id": "s1"}},
            {"content": "Doc B", "score": 0.7, "metadata": {"source_id": "s2"}},
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("query", rerank=False)

    mock_svc.rerank.assert_not_called()
    assert result is not None
    assert "Doc A" in result

@pytest.mark.asyncio
async def test_source_attribution_format():
    """Verify output includes source and relevance in format."""
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store(
        [
            {
                "content": "Knowledge content.",
                "score": 0.88,
                "metadata": {"source_id": "ks_report"},
            },
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("query")

    assert result is not None
    # Format: "Source: ks_report\n  [1] (relevance: 0.88) Knowledge content."
    assert "[1]" in result
    assert "Source: ks_report" in result
    assert "(relevance: 0.88)" in result
    assert "Knowledge content." in result

@pytest.mark.asyncio
async def test_max_chars_default_is_2000():
    """Verify default max_chars is 2000 (not old 600)."""
    mock_svc = _mock_embedding_service()
    mock_store = _mock_hybrid_store(
        [
            {"content": "X" * 1500, "score": 0.8, "metadata": {"source_id": "s1"}},
        ]
    )

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                # Call with default args -- max_chars should be 2000
                result = await get_knowledge_context("query", rerank=False)

    assert result is not None
    # With 2000 char budget and 1 result, the 1500-char content should NOT be truncated
    assert "..." not in result
    assert "X" * 1500 in result

@pytest.mark.asyncio
async def test_dense_only_fallback_on_sparse_error():
    """Falls back to dense-only search when sparse embedding fails."""
    mock_svc = _mock_embedding_service()
    mock_svc.embed_sparse_single.side_effect = Exception("Sparse model failed")

    mock_store = _mock_hybrid_store()
    mock_store.dense_only_search.return_value = [
        {"content": "Fallback result.", "score": 0.75, "metadata": {"source_id": "s1"}},
    ]

    with patch("core.knowledge.sources._knowledge_registry", {"src1": {"name": "test"}}):
        with patch("core.knowledge.embedder.get_embedding_service", return_value=mock_svc):
            with patch("core.knowledge.context._get_hybrid_store", return_value=mock_store):
                from core.knowledge.context import get_knowledge_context

                result = await get_knowledge_context("query")

    assert result is not None
    assert "Fallback result." in result
    mock_store.dense_only_search.assert_called_once()
    mock_store.hybrid_search.assert_not_called()
