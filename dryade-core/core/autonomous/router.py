"""Intelligent skill router using semantic similarity.

MoltBot approach: Inject all eligible skills, let LLM decide.
Dryade enhancement: Pre-filter using semantic similarity to reduce token overhead.

The router:
1. Indexes skill descriptions using sentence embeddings
2. Routes queries to top-k relevant skills
3. Supports configurable similarity threshold
4. Caches embeddings for fast routing
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from core.skills import Skill, SkillSnapshot

logger = logging.getLogger(__name__)

class IntelligentSkillRouter:
    """Route user requests to relevant skills using semantic similarity.

    MoltBot injects all eligible skills (~24 tokens/skill overhead).
    This router pre-filters to top-k skills, reducing token usage
    while maintaining relevance.

    Usage:
        router = IntelligentSkillRouter()
        skills = registry.get_eligible_skills()
        router.index_skills(skills)

        # Later, during execution:
        relevant = router.route("deploy my code to production", skills)
        # Returns [(skill, 0.87), (skill2, 0.72), ...]
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    DEFAULT_TOP_K = 5
    DEFAULT_THRESHOLD = 0.3

    def __init__(
        self,
        embedding_model: str = DEFAULT_MODEL,
        device: str | None = None,
    ):
        """Initialize skill router.

        Args:
            embedding_model: Sentence transformer model name
            device: Device for embeddings (None = auto-detect)
        """
        self._model_name = embedding_model
        self._device = device
        self._encoder: SentenceTransformer | None = None
        self._skill_embeddings: dict[str, np.ndarray] = {}
        self._skill_texts: dict[str, str] = {}

    def _ensure_encoder(self) -> SentenceTransformer:
        """Lazy-load encoder on first use."""
        if self._encoder is None:
            logger.info(f"Loading embedding model: {self._model_name}")
            self._encoder = SentenceTransformer(self._model_name, device=self._device)
        return self._encoder

    def index_skills(self, skills: list[Skill]) -> int:
        """Pre-compute embeddings for skill descriptions.

        Call this when skills change (hot reload) or at startup.

        Args:
            skills: List of skills to index

        Returns:
            Number of skills indexed
        """
        encoder = self._ensure_encoder()

        # Clear existing index
        self._skill_embeddings.clear()
        self._skill_texts.clear()

        for skill in skills:
            # Combine name and description for richer embedding
            text = f"{skill.name}: {skill.description}"
            self._skill_texts[skill.name] = text
            self._skill_embeddings[skill.name] = encoder.encode(
                text,
                convert_to_numpy=True,
                normalize_embeddings=True,  # For cosine similarity via dot product
            )

        logger.info(f"Indexed {len(skills)} skills for semantic routing")
        return len(skills)

    def route(
        self,
        query: str,
        skills: SkillSnapshot | list[Skill],
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> list[tuple[Skill, float]]:
        """Find most relevant skills for query.

        Args:
            query: User request or context
            skills: Skill snapshot or list to route from
            top_k: Maximum skills to return
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of (skill, similarity_score) tuples, sorted by relevance
        """
        encoder = self._ensure_encoder()

        # Encode query
        query_embedding = encoder.encode(query, convert_to_numpy=True, normalize_embeddings=True)

        # Score each skill
        scored: list[tuple[Any, float]] = []

        # Handle both SkillSnapshot and list
        skill_list = list(skills) if hasattr(skills, "__iter__") else skills.skills

        for skill in skill_list:
            if skill.name not in self._skill_embeddings:
                # Skill not indexed - index it now
                text = f"{skill.name}: {skill.description}"
                self._skill_texts[skill.name] = text
                self._skill_embeddings[skill.name] = encoder.encode(
                    text, convert_to_numpy=True, normalize_embeddings=True
                )

            # Cosine similarity via dot product (embeddings are normalized)
            similarity = float(np.dot(query_embedding, self._skill_embeddings[skill.name]))

            if similarity >= threshold:
                scored.append((skill, similarity))

        # Sort by similarity descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_k]

    def register_skill(self, skill: Skill) -> bool:
        """Register a single skill at runtime.

        Computes embedding for the skill and adds it to the index.
        Use for hot-reload of newly created skills.

        Args:
            skill: Skill to register

        Returns:
            True if registered successfully, False if skill already exists
        """
        if skill.name in self._skill_embeddings:
            logger.debug(f"Skill {skill.name} already indexed, updating...")

        encoder = self._ensure_encoder()

        # Compute embedding for this skill
        text = f"{skill.name}: {skill.description}"
        self._skill_texts[skill.name] = text
        self._skill_embeddings[skill.name] = encoder.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        logger.info(f"Registered skill for routing: {skill.name}")
        return True

    def unregister_skill(self, skill_name: str) -> bool:
        """Remove a skill from the routing index.

        Args:
            skill_name: Name of skill to remove

        Returns:
            True if removed, False if not found
        """
        if skill_name not in self._skill_embeddings:
            return False

        del self._skill_embeddings[skill_name]
        del self._skill_texts[skill_name]
        logger.info(f"Unregistered skill from routing: {skill_name}")
        return True

    def clear_index(self) -> None:
        """Clear skill index (for hot reload)."""
        self._skill_embeddings.clear()
        self._skill_texts.clear()
        logger.info("Cleared skill embedding index")

    @property
    def indexed_count(self) -> int:
        """Number of skills currently indexed."""
        return len(self._skill_embeddings)

# Singleton router instance
_router: IntelligentSkillRouter | None = None

def get_skill_router() -> IntelligentSkillRouter:
    """Get or create singleton IntelligentSkillRouter instance."""
    global _router
    if _router is None:
        from core.config import get_settings

        settings = get_settings()
        _router = IntelligentSkillRouter(embedding_model=settings.mcp_tool_embedding_model)
    return _router

def reset_skill_router() -> None:
    """Reset global skill router (for testing)."""
    global _router
    _router = None
