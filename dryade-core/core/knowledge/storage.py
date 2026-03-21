"""Qdrant Storage Backend for Knowledge/RAG Pipeline.

Provides HybridVectorStore with dense + sparse named vectors and RRF fusion.
"""

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient, models
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
)

from core.knowledge.config import KnowledgeConfig
from core.knowledge.vector_store import VectorStoreBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HybridVectorStore -- new standard storage with named vectors + RRF fusion
# ---------------------------------------------------------------------------

class HybridVectorStore(VectorStoreBackend):
    """Qdrant storage with dense + sparse named vectors and RRF hybrid search.

    Uses the Qdrant Query API (query_points) with prefetch and FusionQuery
    for Reciprocal Rank Fusion of dense and sparse retrieval results.

    Named vectors:
        text-dense  -- BGE-small-en-v1.5 (384d, cosine)
        text-sparse -- BM25/SPLADE with IDF modifier
    """

    def __init__(self, client: QdrantClient, config: KnowledgeConfig):
        self.client = client
        self.config = config
        self.collection_name = config.collection_name
        self._ensure_collection()

    # -- Collection management -----------------------------------------------

    def _ensure_collection(self):
        """Create collection with named vectors if it does not exist."""
        collections = self.client.get_collections().collections
        if self.collection_name in [c.name for c in collections]:
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "text-dense": models.VectorParams(
                    size=self.config.dense_dim,  # 384
                    distance=models.Distance.COSINE,
                    hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100),
                ),
            },
            sparse_vectors_config={
                "text-sparse": models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                ),
            },
        )
        logger.info(
            f"Created hybrid collection '{self.collection_name}' "
            f"(dense={self.config.dense_dim}d, sparse=BM25/IDF)"
        )

    # -- Add -----------------------------------------------------------------

    def add(
        self,
        chunks: list[str],
        metadata: list[dict],
        dense_vectors: list[list[float]],
        sparse_vectors: list,
    ) -> None:
        """Add chunks with both dense and sparse vectors.

        Args:
            chunks: List of text chunks.
            metadata: Per-chunk metadata dicts.
            dense_vectors: Dense embedding vectors (one per chunk).
            sparse_vectors: Sparse embedding objects with .indices/.values
                            (one per chunk, may be None for individual items).
        """
        if not chunks:
            return

        points = []
        for chunk, meta, dense, sparse in zip(chunks, metadata, dense_vectors, sparse_vectors):
            point_id = str(uuid.uuid4())
            payload = {**meta, "content": chunk}

            vectors: dict[str, Any] = {"text-dense": dense}
            if sparse is not None:
                vectors["text-sparse"] = models.SparseVector(
                    indices=sparse.indices.tolist(),
                    values=sparse.values.tolist(),
                )

            points.append(models.PointStruct(id=point_id, vector=vectors, payload=payload))

        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(f"Added {len(points)} chunks to '{self.collection_name}'")

    # -- Hybrid search (dense + sparse with RRF) -----------------------------

    def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse,
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Hybrid search with RRF fusion of dense + sparse results.

        Uses Qdrant Query API with two prefetch branches (sparse, dense)
        fused via Reciprocal Rank Fusion.

        Args:
            query_dense: Dense query vector.
            query_sparse: Sparse query object with .indices/.values.
            limit: Max results to return.
            score_threshold: Minimum score (applied post-fusion).
            metadata_filter: Optional metadata filter dict.

        Returns:
            List of result dicts: {content, score, metadata}.
        """
        qdrant_filter = self._build_filter(metadata_filter)

        prefetch = [
            models.Prefetch(
                query=models.SparseVector(
                    indices=query_sparse.indices.tolist(),
                    values=query_sparse.values.tolist(),
                ),
                using="text-sparse",
                limit=limit * 2,
            ),
            models.Prefetch(
                query=query_dense,
                using="text-dense",
                limit=limit * 2,
            ),
        ]

        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            query_filter=qdrant_filter,
        )

        return [
            {
                "content": p.payload.get("content", ""),
                "score": p.score,
                "metadata": {k: v for k, v in (p.payload or {}).items() if k != "content"},
            }
            for p in results.points
            if p.score >= score_threshold
        ]

    # -- Dense-only search (fallback) ----------------------------------------

    def dense_only_search(
        self,
        query_dense: list[float],
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Dense-only search fallback when sparse embeddings are unavailable.

        Uses Qdrant Query API on text-dense named vector only.

        Args:
            query_dense: Dense query vector.
            limit: Max results.
            score_threshold: Minimum score.
            metadata_filter: Optional metadata filter dict.

        Returns:
            List of result dicts: {content, score, metadata}.
        """
        qdrant_filter = self._build_filter(metadata_filter)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_dense,
            using="text-dense",
            limit=limit,
            query_filter=qdrant_filter,
        )

        return [
            {
                "content": p.payload.get("content", ""),
                "score": p.score,
                "metadata": {k: v for k, v in (p.payload or {}).items() if k != "content"},
            }
            for p in results.points
            if p.score >= score_threshold
        ]

    # -- Delete / Clear ------------------------------------------------------

    def delete(self, source_id: str) -> None:
        """Delete all chunks associated with a knowledge source.

        Args:
            source_id: Knowledge source identifier (stored in metadata).
        """
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_id",
                        match=MatchValue(value=source_id),
                    )
                ]
            ),
        )
        logger.info(f"Deleted chunks for source_id='{source_id}'")

    def clear(self) -> None:
        """Delete and recreate collection (for testing/admin)."""
        self.client.delete_collection(collection_name=self.collection_name)
        logger.info(f"Deleted collection '{self.collection_name}'")
        self._ensure_collection()

    # -- Filter helper -------------------------------------------------------

    @staticmethod
    def _build_filter(metadata_filter: dict | None) -> Filter | None:
        """Convert metadata dict to Qdrant Filter.

        Handles:
            - Simple key=value -> MatchValue
            - {"$in": [...]} -> MatchAny
              which only matched the first value)
        """
        if not metadata_filter:
            return None

        conditions = []
        for key, value in metadata_filter.items():
            if isinstance(value, dict) and "$in" in value:
                values = value["$in"]
                if values:
                    conditions.append(FieldCondition(key=key, match=MatchAny(any=values)))
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

        return Filter(must=conditions) if conditions else None
