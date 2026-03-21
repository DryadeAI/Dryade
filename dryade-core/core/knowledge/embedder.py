"""Embedding Service for Knowledge/RAG Pipeline.

Provides EmbeddingService with dense (BGE-small), sparse (BM25), and
cross-encoder reranking via FastEmbed. Backward-compatible wrappers
for get_crew_embedder() and get_crew_storage().
"""

from __future__ import annotations

import logging
from typing import Any

from core.config import get_settings
from core.knowledge.config import KnowledgeConfig, get_knowledge_config

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Unified embedding service for dense, sparse, and reranking.

    Models are lazy-loaded on first use to avoid startup cost.
    """

    def __init__(self, config: KnowledgeConfig | None = None):
        self._config = config or get_knowledge_config()
        self._dense = None
        self._sparse = None
        self._reranker = None

    def _ensure_dense(self):
        if self._dense is None:
            from fastembed import TextEmbedding

            self._dense = TextEmbedding(model_name=self._config.dense_model)

    def _ensure_sparse(self):
        if self._sparse is None:
            from fastembed import SparseTextEmbedding

            self._sparse = SparseTextEmbedding(model_name=self._config.sparse_model)

    def _ensure_reranker(self):
        if self._reranker is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._reranker = TextCrossEncoder(model_name=self._config.reranker_model)

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Generate dense embeddings (BGE-small, 384d)."""
        self._ensure_dense()
        return [e.tolist() for e in self._dense.embed(texts)]

    def embed_dense_single(self, text: str) -> list[float]:
        """Generate dense embedding for a single text."""
        return self.embed_dense([text])[0]

    def embed_sparse(self, texts: list[str]) -> list:
        """Generate sparse embeddings (BM25/SPLADE)."""
        self._ensure_sparse()
        return list(self._sparse.embed(texts))

    def embed_sparse_single(self, text: str):
        """Generate sparse embedding for a single text."""
        return self.embed_sparse([text])[0]

    def rerank(self, query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
        """Rerank documents by cross-encoder relevance.

        Args:
            query: Search query
            documents: List of result dicts with 'content' key
            top_k: Number of results to return

        Returns:
            Reranked list of result dicts with added 'rerank_score' key
        """
        if not documents:
            return []
        self._ensure_reranker()
        contents = [d.get("content", "") for d in documents]
        scores = list(self._reranker.rerank(query, contents))
        # Pair with original documents, sort by score descending
        paired = list(zip(documents, scores))
        paired.sort(key=lambda x: x[1], reverse=True)
        return [{**doc, "rerank_score": score} for doc, score in paired[:top_k]]

class _LegacyEmbedderAdapter:
    """Adapts EmbeddingService to old EmbeddingGenerator interface.

    Provides generate_embedding() and generate_embeddings_batch()
    for backward compatibility with code expecting the old API.
    """

    def __init__(self, service: EmbeddingService):
        self._service = service

    def generate_embedding(self, text: str) -> list[float]:
        return self._service.embed_dense_single(text)

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        return self._service.embed_dense(texts)

    @property
    def embedding_dim(self) -> int:
        return self._service._config.dense_dim

# Singleton instances
_service_instance: EmbeddingService | None = None
_embedder_instance: Any | None = None
_storage_instance: Any | None = None

def get_embedding_service() -> EmbeddingService:
    """Get or create singleton EmbeddingService (preferred API)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EmbeddingService()
        logger.info(f"Initialized EmbeddingService: dense={_service_instance._config.dense_model}")
    return _service_instance

def get_crew_embedder():
    """Get or create singleton embedder with legacy EmbeddingGenerator interface.

    Returns:
        _LegacyEmbedderAdapter wrapping EmbeddingService
        - generate_embedding(text) -> list[float]
        - generate_embeddings_batch(texts) -> list[list[float]]
        - embedding_dim -> int (384)

    Note: Uses BGE-small-en-v1.5 via EmbeddingService (upgraded from MiniLM).
    """
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = _LegacyEmbedderAdapter(get_embedding_service())
        logger.info("Initialized legacy embedder adapter (BGE-small via EmbeddingService)")
    return _embedder_instance

def get_crew_storage():
    """Get or create singleton Qdrant storage for crew knowledge.

    Returns:
        HybridVectorStore instance connected to Qdrant
        - Collection: crew_knowledge
        - Dense vectors: 384-dim, Cosine distance
        - Sparse vectors: BM25/SPLADE with IDF modifier

    Raises:
        ValueError: If qdrant_url not configured
        Exception: If Qdrant connection fails
    """
    global _storage_instance

    if _storage_instance is None:
        try:
            from qdrant_client import QdrantClient

            from core.knowledge.config import KnowledgeConfig
            from core.knowledge.storage import HybridVectorStore

            settings = get_settings()

            if not settings.qdrant_url:
                error_msg = (
                    "DRYADE_QDRANT_URL not configured. "
                    "Set it in .env or environment variables. "
                    "Example: DRYADE_QDRANT_URL=http://localhost:6333"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            client = QdrantClient(url=settings.qdrant_url)
            config = KnowledgeConfig(collection_name="crew_knowledge")

            _storage_instance = HybridVectorStore(client=client, config=config)

            logger.info(f"Initialized Qdrant storage for crew knowledge at {settings.qdrant_url}")

        except Exception as e:
            logger.error(f"Failed to initialize crew storage: {e}")
            raise

    return _storage_instance

def reset_singletons():
    """Reset all singleton instances (for testing only)."""
    global _service_instance, _embedder_instance, _storage_instance
    _service_instance = None
    _embedder_instance = None
    _storage_instance = None
    logger.debug("Reset knowledge singletons")
