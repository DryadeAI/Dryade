"""Embedding generation for preference matching.

Uses sentence-transformers with lightweight model for fast startup and low memory.
Model: all-MiniLM-L6-v2 (384 dimensions, ~80MB)
"""

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Model constants
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

class EmbeddingGenerator:
    """Generates embeddings for semantic question matching.

    Lazy-loads model on first use to avoid slow startup.
    """

    def __init__(self):
        """Initialize generator without loading model."""
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> "SentenceTransformer":
        """Get or load the embedding model (lazy-loaded on first access)."""
        if self._model is None:
            logger.info(f"[EMBEDDINGS] Loading model: {MODEL_NAME}")
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(MODEL_NAME)
                logger.info(f"[EMBEDDINGS] Model loaded ({EMBEDDING_DIM} dimensions)")
            except ImportError:
                logger.error("[EMBEDDINGS] sentence-transformers not installed")
                raise ImportError(
                    "sentence-transformers required for preference matching. "
                    "Install with: pip install sentence-transformers"
                )
        return self._model

    def encode(self, text: str) -> list[float]:
        """Generate embedding for text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts (batch, more efficient)."""
        if not texts:
            return []
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [e.tolist() for e in embeddings]

# Global singleton - lazy loaded
_generator: EmbeddingGenerator | None = None

def get_embedding_generator() -> EmbeddingGenerator:
    """Get or create global embedding generator."""
    global _generator
    if _generator is None:
        _generator = EmbeddingGenerator()
    return _generator

def generate_embedding(text: str) -> list[float]:
    """Convenience function to generate embedding for text."""
    generator = get_embedding_generator()
    return generator.encode(text)

def compute_cosine_similarity(embedding1: list[float], embedding2: list[float]) -> float:
    """Compute cosine similarity between two embeddings."""
    a = np.array(embedding1)
    b = np.array(embedding2)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))
