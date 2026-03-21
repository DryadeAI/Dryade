"""Summary Index for document-level coarse retrieval.

Provides two-stage retrieval: find relevant documents by summary first,
then search within them at chunk level.
"""

from __future__ import annotations

import logging

from core.knowledge.embedder import EmbeddingService
from core.knowledge.vector_store import VectorStoreBackend

logger = logging.getLogger(__name__)

class SummaryIndex:
    """Document-level summary index for coarse retrieval.

    Stores one embedding per document (the document's summary) for fast
    document-level filtering before chunk-level search.
    """

    def __init__(self, store: VectorStoreBackend, embedder: EmbeddingService):
        self.store = store
        self.embedder = embedder

    def add_summary(self, source_id: str, summary: str, metadata: dict | None = None) -> None:
        """Add a document summary to the index.

        Args:
            source_id: Unique identifier for the document.
            summary: Summary text to index.
            metadata: Optional additional metadata.
        """
        meta = metadata or {}
        meta["source_id"] = source_id
        meta["is_summary"] = True
        dense = self.embedder.embed_dense([summary])
        # No sparse vectors for summaries (dense-only for simplicity)
        self.store.add(
            chunks=[summary],
            metadata=[meta],
            dense_vectors=dense,
            sparse_vectors=[None],
        )
        logger.info(f"Added summary for source_id='{source_id}' to index")

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Find documents relevant to query by searching summaries.

        Args:
            query: Search query text.
            limit: Max number of document summaries to return.

        Returns:
            List of result dicts with content, score, metadata.
        """
        query_dense = self.embedder.embed_dense_single(query)
        return self.store.dense_only_search(
            query_dense=query_dense,
            limit=limit,
            metadata_filter={"is_summary": True},
        )

    @staticmethod
    def generate_summary(text: str, max_length: int = 500) -> str:
        """Generate a simple extractive summary (first N characters).

        For LLM-based abstractive summaries, callers should use their own
        LLM and pass the result to add_summary() directly.

        Args:
            text: Full document text.
            max_length: Maximum summary length in characters.

        Returns:
            Extractive summary string.
        """
        if len(text) <= max_length:
            return text
        # Find sentence boundary near max_length
        truncated = text[:max_length]
        last_period = truncated.rfind(". ")
        if last_period > max_length // 2:
            return truncated[: last_period + 1]
        return truncated + "..."
