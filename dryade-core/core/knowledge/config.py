"""Knowledge/RAG Configuration.

Centralizes all RAG pipeline parameters with sane defaults.
Reads overrides from core.config.Settings when available.
"""

from dataclasses import dataclass

from core.config import get_settings


@dataclass
class KnowledgeConfig:
    """Configuration for knowledge/RAG pipeline components."""

    # Embedding models
    dense_model: str = "BAAI/bge-small-en-v1.5"  # 384d, better than MiniLM
    sparse_model: str = "Qdrant/bm25"  # BM25 for hybrid search
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"  # Cross-encoder reranker

    # Chunking
    chunk_size: int = 512  # characters (~128 tokens), configurable via Settings
    chunk_overlap: int = 50  # characters, configurable via Settings
    chunk_strategy: str = "recursive"  # "recursive" only in core

    # Retrieval
    top_k: int = 5  # configurable via Settings
    max_context_chars: int = 2000  # increased from 600
    max_results: int = 5  # increased from 3
    score_threshold: float = 0.3  # lowered for hybrid (RRF scores differ from cosine)
    rerank_enabled: bool = True
    rerank_top_k: int = 10  # retrieve 2x, rerank to top_k

    # Collection
    collection_name: str = "dryade_knowledge"  # new collection for new model
    legacy_collection: str = "crew_knowledge"  # old collection for migration

    # Vector dimensions
    dense_dim: int = 384  # BGE-small-en-v1.5

    # Backend selection: "qdrant" (default), "pgvector", "chroma"
    vector_backend: str = "qdrant"

_config_instance: KnowledgeConfig | None = None

def get_knowledge_config() -> KnowledgeConfig:
    """Get or create singleton KnowledgeConfig, reading overrides from Settings."""
    global _config_instance
    if _config_instance is None:
        settings = get_settings()
        # Read vector_backend from env or settings
        import os

        vector_backend = os.environ.get(
            "DRYADE_VECTOR_BACKEND",
            getattr(settings, "vector_backend", "qdrant"),
        )

        _config_instance = KnowledgeConfig(
            chunk_size=(
                settings.knowledge_chunk_size if settings.knowledge_chunk_size != 1000 else 512
            ),
            chunk_overlap=(
                settings.knowledge_chunk_overlap if settings.knowledge_chunk_overlap != 200 else 50
            ),
            top_k=settings.knowledge_top_k,
            vector_backend=vector_backend,
        )
    return _config_instance

def reset_config():
    """Reset singleton (for testing)."""
    global _config_instance
    _config_instance = None
