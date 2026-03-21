"""Knowledge Context Builder for Chat Integration.

Retrieves relevant knowledge snippets from Qdrant and formats them
for injection into LLM prompts across all orchestrator tiers.

Phase 94.1: Automatic knowledge context in INSTANT, SIMPLE, and COMPLEX tiers.
Phase 97.2: Upgraded to hybrid search (dense+sparse) with RRF fusion + cross-encoder reranking.
"""

import logging

logger = logging.getLogger(__name__)

def _get_hybrid_store():
    """Get HybridVectorStore instance for hybrid search.

    Returns:
        HybridVectorStore connected to Qdrant with knowledge config.
    """
    from qdrant_client import QdrantClient

    from core.config import get_settings
    from core.knowledge.config import get_knowledge_config
    from core.knowledge.storage import HybridVectorStore

    config = get_knowledge_config()
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url)
    return HybridVectorStore(client=client, config=config)

async def get_knowledge_context(
    query: str,
    max_chars: int = 2000,
    max_results: int = 5,
    score_threshold: float = 0.5,
    rerank: bool = True,
    source_ids: list[str] | None = None,
) -> str | None:
    """Retrieve relevant knowledge context for a user query.

    Uses hybrid search (dense + sparse embeddings with RRF fusion)
    and optional cross-encoder reranking for high-quality retrieval.

    Returns None immediately (zero latency) when no knowledge sources
    are registered or when no relevant results are found.

    Args:
        query: User message to search against.
        max_chars: Maximum total characters for all results combined.
        max_results: Maximum number of results to return.
        score_threshold: Minimum score (0.0-1.0, lowered for RRF scores).
        rerank: Whether to apply cross-encoder reranking (default: True).
        source_ids: Optional list of source IDs to filter results by.

    Returns:
        Formatted string of knowledge snippets with source attribution,
        or None if no relevant knowledge is found or no sources are registered.
    """
    try:
        # Fast check: skip entirely if no knowledge sources registered
        from core.knowledge.sources import _knowledge_registry

        if not _knowledge_registry:
            return None

        # Lazy import to avoid startup cost
        from core.knowledge.embedder import get_embedding_service

        service = get_embedding_service()
        store = _get_hybrid_store()

        # Build metadata filter for source_ids filtering
        metadata_filter = None
        if source_ids:
            metadata_filter = {"source_id": {"$in": source_ids}}

        # Generate dense + sparse query embeddings
        query_dense = service.embed_dense_single(query)
        try:
            query_sparse = service.embed_sparse_single(query)
        except Exception:
            # Fall back to dense-only if sparse fails
            logger.warning("Sparse embedding failed, falling back to dense-only search")
            results = store.dense_only_search(
                query_dense=query_dense,
                limit=max_results,
                score_threshold=score_threshold,
                metadata_filter=metadata_filter,
            )
            return _format_results(results, max_chars) if results else None

        # Hybrid search: over-retrieve for reranking, else exact limit
        retrieve_limit = max_results * 2 if rerank else max_results
        results = store.hybrid_search(
            query_dense=query_dense,
            query_sparse=query_sparse,
            limit=retrieve_limit,
            score_threshold=score_threshold,
            metadata_filter=metadata_filter,
        )

        if not results:
            return None

        # Rerank with cross-encoder if enabled and multiple results
        if rerank and len(results) > 1:
            results = service.rerank(query, results, top_k=max_results)
        else:
            results = results[:max_results]

        return _format_results(results, max_chars)

    except Exception:
        logger.warning(
            "Knowledge context retrieval failed, continuing without knowledge",
            exc_info=True,
        )
        return None

def _format_results(results: list[dict], max_chars: int) -> str | None:
    """Format search results grouped by source for clearer LLM reasoning.

    Groups results by source name/id so the LLM can see which documents
    contributed which information, enabling better multi-source reasoning.

    Args:
        results: List of result dicts with content, score, metadata keys.
        max_chars: Maximum total characters for all results combined.

    Returns:
        Formatted string or None if no results.
    """
    if not results:
        return None

    per_result_chars = max_chars // max(len(results), 1)

    # Group results by source
    from collections import OrderedDict

    grouped: OrderedDict[str, list[str]] = OrderedDict()

    for i, result in enumerate(results, 1):
        content = result.get("content", "")
        if len(content) > per_result_chars:
            content = content[:per_result_chars] + "..."
        score = result.get("rerank_score", result.get("score", 0.0))
        source_id = result.get("metadata", {}).get("source_id", "unknown")
        source_name = result.get("metadata", {}).get("source_name", "")
        source_label = f"{source_name} ({source_id})" if source_name else source_id

        if source_label not in grouped:
            grouped[source_label] = []
        grouped[source_label].append(f"  [{i}] (relevance: {score:.2f}) {content}")

    # Format as grouped output
    lines = []
    for source_label, entries in grouped.items():
        lines.append(f"Source: {source_label}")
        lines.extend(entries)

    return "\n".join(lines)
