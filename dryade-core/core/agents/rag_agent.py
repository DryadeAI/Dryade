"""RAG Agent - Retrieval-Augmented Generation with hybrid search.

Implements UniversalAgent protocol for query-time knowledge retrieval
using Qdrant vector database with hybrid search (dense + sparse + RRF fusion)
and optional cross-encoder reranking via the EmbeddingService.

Target: ~150 LOC
"""

import structlog

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = structlog.get_logger(__name__)

class RAGAgent(UniversalAgent):
    """RAG Agent for hybrid knowledge retrieval.

    Provides query-time hybrid search (dense + sparse with RRF fusion)
    over Qdrant-stored documents with optional cross-encoder reranking.
    Falls back to dense-only search if sparse embedding fails.

    Implements UniversalAgent protocol for integration with command system.
    """

    def __init__(
        self,
        collection_name: str = "dryade_knowledge",
        top_k: int = 5,
        score_threshold: float = 0.3,
        rerank: bool = True,
    ):
        """Initialize RAG Agent.

        Args:
            collection_name: Qdrant collection to search (default: dryade_knowledge)
            top_k: Default number of results to return (default: 5)
            score_threshold: Minimum similarity score (0.0-1.0, default: 0.3 for RRF)
            rerank: Whether to apply cross-encoder reranking (default: True)
        """
        self.collection_name = collection_name
        self.default_top_k = top_k
        self.score_threshold = score_threshold
        self.rerank = rerank
        self._store = None  # Lazy initialization
        self._service = None  # Lazy initialization

    def _get_store(self):
        """Get or create HybridVectorStore instance lazily.

        Returns:
            HybridVectorStore instance

        Raises:
            RuntimeError: If Qdrant connection fails
        """
        if self._store is None:
            try:
                from qdrant_client import QdrantClient

                from core.config import get_settings
                from core.knowledge.config import get_knowledge_config
                from core.knowledge.storage import HybridVectorStore

                settings = get_settings()
                config = get_knowledge_config()
                client = QdrantClient(url=settings.qdrant_url)

                self._store = HybridVectorStore(client=client, config=config)
                logger.info(
                    "RAG hybrid store initialized",
                    collection=config.collection_name,
                    qdrant_url=settings.qdrant_url,
                )
            except Exception as e:
                logger.error("Failed to initialize RAG hybrid store", error=str(e))
                raise RuntimeError(f"Qdrant connection failed: {e}") from e

        return self._store

    def _get_service(self):
        """Get or create EmbeddingService instance lazily.

        Returns:
            EmbeddingService instance
        """
        if self._service is None:
            from core.knowledge.embedder import get_embedding_service

            self._service = get_embedding_service()
        return self._service

    def get_card(self) -> AgentCard:
        """Return agent capability card.

        Returns:
            AgentCard with RAG capabilities
        """
        return AgentCard(
            name="rag_assistant",
            description="Retrieval-augmented generation with hybrid search (dense + sparse + RRF fusion) and cross-encoder reranking",
            version="2.0",
            framework=AgentFramework.CUSTOM,
            capabilities=[
                AgentCapability(
                    name="semantic_search",
                    description="Search knowledge base using hybrid semantic + keyword similarity with reranking",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language search query",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                    output_schema={
                        "type": "object",
                        "properties": {
                            "documents": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "content": {"type": "string"},
                                        "score": {"type": "number"},
                                        "metadata": {"type": "object"},
                                    },
                                },
                            },
                            "retrieved_count": {"type": "integer"},
                        },
                    },
                )
            ],
            metadata={
                "default_collection": self.collection_name,
                "default_top_k": self.default_top_k,
                "score_threshold": self.score_threshold,
                "search_mode": "hybrid",
                "reranking": self.rerank,
            },
        )

    async def execute(self, task: str, context: dict | None = None) -> AgentResult:
        """Execute hybrid search query with optional reranking.

        Args:
            task: Natural language search query
            context: Optional context with:
                - top_k: Override default result count
                - score_threshold: Override default threshold
                - rerank: Override default reranking behavior

        Returns:
            AgentResult with documents or fallback message
        """
        context = context or {}

        # Extract parameters from context
        top_k = context.get("top_k", self.default_top_k)
        threshold = context.get("score_threshold", self.score_threshold)
        do_rerank = context.get("rerank", self.rerank)

        logger.info(
            "RAG hybrid search started",
            query=task[:50] + "..." if len(task) > 50 else task,
            top_k=top_k,
            rerank=do_rerank,
        )

        try:
            store = self._get_store()
            service = self._get_service()

            # Generate dense query embedding
            query_dense = service.embed_dense_single(task)

            # Try hybrid search (dense + sparse)
            try:
                query_sparse = service.embed_sparse_single(task)
                retrieve_limit = top_k * 2 if do_rerank else top_k
                results = store.hybrid_search(
                    query_dense=query_dense,
                    query_sparse=query_sparse,
                    limit=retrieve_limit,
                    score_threshold=threshold,
                )
            except Exception:
                # Fall back to dense-only search if sparse fails
                logger.warning("Sparse embedding failed, falling back to dense-only search")
                results = store.dense_only_search(
                    query_dense=query_dense,
                    limit=top_k,
                    score_threshold=threshold,
                )

            # Rerank results if enabled and multiple results
            if do_rerank and results and len(results) > 1:
                results = service.rerank(task, results, top_k=top_k)
            elif results:
                results = results[:top_k]

            # Handle empty results
            if not results:
                logger.info("RAG search returned no results", query=task[:30])
                return AgentResult(
                    result={
                        "fallback": True,
                        "message": "No matches found in knowledge base for this query.",
                        "query": task,
                    },
                    status="ok",
                    metadata={
                        "collection": self.collection_name,
                        "top_k": top_k,
                        "retrieved_count": 0,
                    },
                )

            # Format results
            documents = [
                {
                    "content": r["content"],
                    "score": r.get("rerank_score", r.get("score", 0.0)),
                    "metadata": r.get("metadata", {}),
                }
                for r in results
            ]

            logger.info(
                "RAG hybrid search completed",
                retrieved_count=len(documents),
                top_score=documents[0]["score"] if documents else 0,
            )

            return AgentResult(
                result={
                    "documents": documents,
                    "retrieved_count": len(documents),
                },
                status="ok",
                metadata={
                    "collection": self.collection_name,
                    "top_k": top_k,
                    "score_threshold": threshold,
                    "search_mode": "hybrid",
                    "reranked": do_rerank,
                },
            )

        except RuntimeError as e:
            # Qdrant connection error
            logger.error("RAG search failed - connection error", error=str(e))
            return AgentResult(
                result=None,
                status="error",
                error=f"Knowledge base unavailable: {e}",
                metadata={"collection": self.collection_name},
            )
        except Exception as e:
            # Unexpected error
            logger.exception("RAG search failed with unexpected error", error=str(e))
            return AgentResult(
                result=None,
                status="error",
                error=f"Search failed: {e}",
                metadata={"collection": self.collection_name},
            )

    def get_tools(self) -> list[dict]:
        """Return available tools in OpenAI function format.

        Returns:
            List with semantic_search tool definition
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "semantic_search",
                    "description": "Search knowledge base using hybrid semantic + keyword similarity with reranking",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language search query",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results (default: 5)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        ]
