"""Preference memory for clarification questions.

Provides:
- Embeddings: Semantic encoding using sentence-transformers
- Matcher: Find matching preferences using cosine similarity
"""

from .embeddings import (
    EMBEDDING_DIM,
    EmbeddingGenerator,
    compute_cosine_similarity,
    generate_embedding,
    get_embedding_generator,
)

__all__ = [
    # Embeddings
    "generate_embedding",
    "compute_cosine_similarity",
    "get_embedding_generator",
    "EmbeddingGenerator",
    "EMBEDDING_DIM",
]
