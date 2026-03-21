"""Vector Store Backend abstraction for Knowledge/RAG Pipeline.

Defines the abstract interface that all vector store implementations
(Qdrant, Pgvector, Chroma) must satisfy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class VectorStoreBackend(ABC):
    """Abstract base class for vector store backends.

    All vector store implementations must implement these 5 methods.
    Method signatures match the existing HybridVectorStore interface.
    """

    @abstractmethod
    def add(
        self,
        chunks: list[str],
        metadata: list[dict],
        dense_vectors: list[list[float]],
        sparse_vectors: list,
    ) -> None:
        """Add chunks with embeddings to the store.

        Args:
            chunks: List of text chunks.
            metadata: Per-chunk metadata dicts.
            dense_vectors: Dense embedding vectors (one per chunk).
            sparse_vectors: Sparse embedding objects (one per chunk, may be None).
        """
        ...

    @abstractmethod
    def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse,
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Search using both dense and sparse vectors with fusion.

        Args:
            query_dense: Dense query vector.
            query_sparse: Sparse query object.
            limit: Max results to return.
            score_threshold: Minimum score threshold.
            metadata_filter: Optional metadata filter dict.

        Returns:
            List of result dicts: {content, score, metadata}.
        """
        ...

    @abstractmethod
    def dense_only_search(
        self,
        query_dense: list[float],
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Search using only dense vectors.

        Args:
            query_dense: Dense query vector.
            limit: Max results to return.
            score_threshold: Minimum score threshold.
            metadata_filter: Optional metadata filter dict.

        Returns:
            List of result dicts: {content, score, metadata}.
        """
        ...

    @abstractmethod
    def delete(self, source_id: str) -> None:
        """Delete all chunks associated with a knowledge source.

        Args:
            source_id: Knowledge source identifier.
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Delete all data and recreate the store."""
        ...
