"""Knowledge Routes - Knowledge source management endpoints.

Provides endpoints for managing knowledge sources used by agents and crews
for RAG (Retrieval-Augmented Generation). Supports uploading documents,
querying knowledge bases via semantic search, and managing source lifecycle.

Phase 97.2: Upload via IngestPipeline, query via hybrid search + reranking,
chunks via Qdrant scroll, delete from both legacy and new collections.
"""

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from core.api.models.openapi import response_with_errors
from core.config import get_settings
from core.knowledge.sources import (
    KnowledgeSourceInfo,
    delete_knowledge_source,
    get_knowledge_source_info,
    list_knowledge_sources,
    register_knowledge_source,
    update_knowledge_associations,
)

logger = logging.getLogger(__name__)

router = APIRouter()

class UploadResponse(BaseModel):
    """Response after successfully uploading a knowledge document."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "ks_abc123",
                "name": "product_manual",
                "source_type": "pdf",
                "file_path": "./uploads/knowledge/abc123.pdf",
            }
        }
    )

    id: str = Field(
        ..., description="Unique identifier for the knowledge source (prefixed with 'ks_')"
    )
    name: str = Field(..., description="Display name of the knowledge source")
    source_type: str = Field(..., description="Type of source: 'pdf', 'txt', or 'markdown'")
    file_path: str = Field(..., description="Path where the uploaded file is stored")

class QueryRequest(BaseModel):
    """Request body for semantic search queries against knowledge sources."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "How do I configure authentication?",
                "source_ids": ["ks_abc123"],
                "limit": 5,
                "score_threshold": 0.3,
            }
        }
    )

    query: str = Field(
        ...,
        description="Natural language search query to find relevant documents",
        min_length=1,
        max_length=500,
    )
    source_ids: list[str] | None = Field(
        default=None,
        description="Optional list of source IDs to search within; if not provided, searches all sources",
    )
    limit: int = Field(
        default=5, ge=1, le=50, description="Maximum number of results to return (1-50)"
    )
    offset: int = Field(default=0, ge=0, description="Number of results to skip for pagination")
    score_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum relevance score for results (0.0-1.0); default 0.3 for hybrid RRF scores",
    )

class QueryResult(BaseModel):
    """A single result from a knowledge query with content and metadata."""

    content: str = Field(..., description="Document chunk text matching the query")
    score: float = Field(..., description="Relevance score between 0.0 and 1.0")
    metadata: dict = Field(
        default_factory=dict,
        description="Source metadata including file_path, page number, chunk index",
    )
    source_id: str | None = Field(
        default=None, description="ID of the knowledge source this result came from"
    )

class QueryResponse(BaseModel):
    """Response from a semantic search query with matching documents."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "results": [
                    {
                        "content": "To configure auth, set the API_KEY...",
                        "score": 0.89,
                        "metadata": {"page": 1},
                        "source_id": "ks_abc123",
                    }
                ],
                "sources_used": ["ks_abc123"],
                "query": "How do I configure authentication?",
                "total_results": 1,
            }
        }
    )

    results: list[QueryResult] = Field(
        ..., description="List of matching document chunks sorted by relevance"
    )
    sources_used: list[str] = Field(
        ..., description="List of source IDs that contributed to the results"
    )
    query: str = Field(..., description="The original search query")
    total_results: int = Field(..., description="Total number of matching results returned")

class KnowledgeListResponse(BaseModel):
    """Response containing list of all registered knowledge sources."""

    sources: list[KnowledgeSourceInfo] = Field(
        ..., description="List of all registered knowledge sources"
    )
    total: int = Field(..., description="Total number of knowledge sources")  # GAP-108

class BindRequest(BaseModel):
    """Request body for binding crew/agent associations to a knowledge source."""

    crew_ids: list[str] | None = Field(
        default=None,
        description="Crew IDs to associate (None = don't change, [] = clear)",
    )
    agent_ids: list[str] | None = Field(
        default=None,
        description="Agent IDs to associate (None = don't change, [] = clear)",
    )

class ChunksResponse(BaseModel):
    """Response containing indexed chunks for a knowledge source."""

    source_id: str = Field(..., description="Knowledge source ID")
    chunks: list[str] = Field(..., description="List of chunk content strings")
    total: int = Field(..., description="Total number of chunks")

@router.get(
    "",
    response_model=KnowledgeListResponse,
    responses=response_with_errors(500),
)
async def list_sources() -> KnowledgeListResponse:
    """List all registered knowledge sources.

    Returns all knowledge sources that have been uploaded and indexed,
    including their metadata, status, and associated crews/agents.
    """
    sources = list_knowledge_sources()
    return KnowledgeListResponse(sources=sources, total=len(sources))  # GAP-108

@router.get(
    "/{source_id}",
    response_model=KnowledgeSourceInfo,
    responses=response_with_errors(404, 500),
)
async def get_source(source_id: str) -> KnowledgeSourceInfo:
    """Get details for a specific knowledge source.

    Returns metadata, status, file paths, and associations for the
    requested knowledge source.
    """
    sources = list_knowledge_sources()
    for source in sources:
        if source.id == source_id:
            return source
    raise HTTPException(status_code=404, detail="Knowledge source not found")

@router.post(
    "/upload",
    response_model=UploadResponse,
    responses=response_with_errors(400, 500, 503),
)
async def upload_knowledge(
    file: UploadFile = File(..., description="PDF, TXT, or MD file to upload"),
    name: str | None = None,
    description: str | None = None,
    crew_ids: str | None = None,
    agent_ids: str | None = None,
):
    """Upload and index a knowledge document.

    Accepts PDF, TXT, or MD files. The document is chunked, embedded using
    dense + sparse models, and stored in Qdrant for hybrid semantic search.

    Optionally associate the source with specific crews or agents by passing
    comma-separated IDs (e.g., crew_ids="crew1,crew2").
    """
    settings = get_settings()

    # Check that Qdrant URL is configured (pipeline needs it)
    if not settings.qdrant_url:
        raise HTTPException(
            status_code=503,
            detail="Knowledge service unavailable. DRYADE_QDRANT_URL not configured.",
        )

    try:
        from core.knowledge.pipeline import get_ingest_pipeline

        # Create upload directory
        upload_dir = Path("./uploads/knowledge")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_id = str(uuid.uuid4())[:8]
        file_ext = Path(file.filename).suffix
        file_path = upload_dir / f"{file_id}{file_ext}"

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        logger.info(f"File saved: {file_path}")

        # Determine source type
        source_name = name or Path(file.filename).stem
        source_id = f"ks_{file_id}"

        if file_ext.lower() == ".pdf":
            source_type = "pdf"
        elif file_ext.lower() == ".txt":
            source_type = "txt"
        elif file_ext.lower() == ".md":
            source_type = "markdown"
        else:
            file_path.unlink()  # Clean up uploaded file
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

        # Ingest via pipeline (parse -> chunk -> embed dense+sparse -> store)
        pipeline = get_ingest_pipeline()
        result = await pipeline.ingest(
            file_path=str(file_path),
            source_id=source_id,
            metadata={"file_path": str(file_path), "source_name": source_name},
        )

        chunk_count = result.chunk_count
        logger.info(f"Indexed {chunk_count} chunks for source: {source_id}")

        # Parse crew/agent IDs
        parsed_crew_ids = crew_ids.split(",") if crew_ids else []
        parsed_agent_ids = agent_ids.split(",") if agent_ids else []

        # Register in registry with metadata and associations
        # source=None since pipeline handles ingestion directly (no CrewAI source object)
        register_knowledge_source(
            source_name,
            source=None,
            description=description or "",
            metadata={"source_id": source_id, "file_path": str(file_path)},
            crew_ids=parsed_crew_ids,
            agent_ids=parsed_agent_ids,
            chunk_count=chunk_count,
            source_type=source_type,
            file_paths=[str(file_path)],
        )

        logger.info(
            f"Uploaded and indexed knowledge source: {source_id} "
            f"(crews: {parsed_crew_ids}, agents: {parsed_agent_ids})"
        )

        return UploadResponse(
            id=source_id,
            name=source_name,
            source_type=source_type,
            file_path=str(file_path),
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.exception(f"Configuration error during upload: {e}")
        raise HTTPException(
            status_code=503,
            detail="Knowledge service unavailable. Check embedding model configuration.",
        ) from e
    except Exception as e:
        logger.exception(f"Error uploading knowledge: {e}")
        # Clean up file on failure (only if file_path was defined)
        if "file_path" in locals() and file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=500,
            detail="Failed to process document. Supported formats: PDF, TXT, MD.",
        ) from e

@router.delete(
    "/{source_id}",
    status_code=204,
    responses=response_with_errors(404, 500, 503),
)
async def delete_source(source_id: str):
    """Delete a knowledge source and all associated data.

    Removes the knowledge source from:
    - Qdrant vector store (both new hybrid and legacy collections)
    - Knowledge registry (metadata)
    - File system (uploaded files)

    This operation is irreversible. Returns 204 No Content on success.
    """
    # Check if source exists
    source_info = get_knowledge_source_info(source_id)
    if not source_info:
        raise HTTPException(status_code=404, detail=f"Knowledge source '{source_id}' not found")

    try:
        # 1. Delete from new hybrid collection
        try:
            from qdrant_client import QdrantClient

            from core.knowledge.config import get_knowledge_config
            from core.knowledge.storage import HybridVectorStore

            settings = get_settings()
            config = get_knowledge_config()
            client = QdrantClient(url=settings.qdrant_url)
            store = HybridVectorStore(client=client, config=config)
            store.delete(source_id)
            logger.info(f"Deleted vectors from hybrid collection for source: {source_id}")
        except Exception as e:
            logger.warning(f"Could not delete from hybrid collection: {e}")

        # 2. Delete from legacy collection (if it exists)
        try:
            from core.knowledge.embedder import get_crew_storage

            storage = get_crew_storage()
            storage.delete(source_id)
            logger.info(f"Deleted vectors from legacy collection for source: {source_id}")
        except Exception as e:
            logger.warning(f"Could not delete from legacy collection: {e}")

        # 3. Delete from registry
        delete_knowledge_source(source_id)
        logger.info(f"Removed from registry: {source_id}")

        # 4. Delete uploaded file(s)
        for file_path_str in source_info.file_paths:
            file_path = Path(file_path_str)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted file: {file_path_str}")
            else:
                logger.warning(f"File not found (already deleted?): {file_path_str}")

        logger.info(f"Knowledge source deleted: {source_id}")

    except ValueError as e:
        # Configuration error (e.g., Qdrant URL not set)
        logger.exception(f"Configuration error during deletion: {e}")
        raise HTTPException(
            status_code=503,
            detail="Knowledge service unavailable. Check vector store configuration.",
        ) from e
    except Exception as e:
        logger.exception(f"Error deleting knowledge source {source_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete knowledge source. Please try again.",
        ) from e

@router.post(
    "/query",
    response_model=QueryResponse,
    responses=response_with_errors(400, 500, 503),
)
async def query_knowledge(request: QueryRequest) -> QueryResponse:
    """Query knowledge sources using hybrid search with reranking.

    Performs hybrid vector similarity search (dense + sparse with RRF fusion)
    against indexed documents, then reranks results with a cross-encoder.
    Returns document chunks above the score_threshold.

    The default score_threshold of 0.3 is calibrated for RRF fusion scores
    (lower than cosine similarity thresholds).
    """
    settings = get_settings()
    if not settings.qdrant_url:
        raise HTTPException(
            status_code=503,
            detail="Knowledge service unavailable. DRYADE_QDRANT_URL not configured.",
        )

    try:
        from qdrant_client import QdrantClient

        from core.knowledge.config import get_knowledge_config
        from core.knowledge.embedder import get_embedding_service
        from core.knowledge.storage import HybridVectorStore

        service = get_embedding_service()
        config = get_knowledge_config()
        client = QdrantClient(url=settings.qdrant_url)
        store = HybridVectorStore(client=client, config=config)

        # Build metadata filter if source_ids provided
        metadata_filter = None
        if request.source_ids:
            metadata_filter = {"source_id": {"$in": request.source_ids}}

        # Generate query embeddings
        query_dense = service.embed_dense_single(request.query)
        query_sparse = service.embed_sparse_single(request.query)

        # Hybrid search with over-retrieval for reranking
        # Over-retrieve enough to cover offset + limit after reranking
        over_retrieve_count = (request.offset + request.limit) * 2
        raw_results = store.hybrid_search(
            query_dense=query_dense,
            query_sparse=query_sparse,
            limit=over_retrieve_count,
            score_threshold=request.score_threshold,
            metadata_filter=metadata_filter,
        )

        # Rerank with cross-encoder (rerank all candidates, then slice)
        rerank_top_k = request.offset + request.limit
        if raw_results and len(raw_results) > 1:
            all_reranked = service.rerank(request.query, raw_results, top_k=rerank_top_k)
        else:
            all_reranked = raw_results[:rerank_top_k]

        # Total is the full reranked set size (before offset slicing)
        total_count = len(all_reranked)

        # Apply offset: slice to the requested page
        paged_results = all_reranked[request.offset : request.offset + request.limit]

        # Format results
        formatted_results = [
            QueryResult(
                content=r["content"],
                score=r.get("rerank_score", r.get("score", 0.0)),
                metadata=r.get("metadata", {}),
                source_id=r.get("metadata", {}).get("source_id"),
            )
            for r in paged_results
        ]

        # Extract unique source IDs from results
        sources_used = list({r.source_id for r in formatted_results if r.source_id})

        logger.info(
            f"Knowledge query: '{request.query}' returned {len(formatted_results)} results "
            f"(offset={request.offset}, total={total_count})"
        )

        return QueryResponse(
            results=formatted_results,
            sources_used=sources_used,
            query=request.query,
            total_results=total_count,
        )

    except ValueError as e:
        # Configuration error (e.g., Qdrant URL not set)
        logger.exception(f"Configuration error during query: {e}")
        raise HTTPException(
            status_code=503,
            detail="Knowledge service unavailable. Check embedding model configuration.",
        ) from e
    except Exception as e:
        logger.exception(f"Error querying knowledge: {e}")
        raise HTTPException(
            status_code=500,
            detail="Knowledge search failed. Try rephrasing your query or checking index status.",
        ) from e

@router.post(
    "/{source_id}/bind",
    response_model=KnowledgeSourceInfo,
    responses=response_with_errors(404, 500),
)
async def bind_source(source_id: str, request: BindRequest) -> KnowledgeSourceInfo:
    """Bind crew/agent associations to a knowledge source.

    Updates the crew and/or agent associations for an existing knowledge source.
    Pass None to leave a field unchanged, or an empty list to clear associations.

    GAP-102: POST /knowledge/{id}/bind accepts crew_ids and agent_ids arrays
    """
    # Update associations
    success = update_knowledge_associations(
        source_id,
        crew_ids=request.crew_ids,
        agent_ids=request.agent_ids,
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Knowledge source '{source_id}' not found")

    # Return updated source info
    source_info = get_knowledge_source_info(source_id)
    if not source_info:
        raise HTTPException(status_code=404, detail=f"Knowledge source '{source_id}' not found")

    logger.info(
        f"Bound associations for source {source_id}: crews={request.crew_ids}, agents={request.agent_ids}"
    )
    return source_info

@router.delete(
    "/{source_id}/unbind",
    status_code=204,
    responses=response_with_errors(404, 500),
)
async def unbind_source(source_id: str):
    """Unbind all crew/agent associations from a knowledge source.

    Clears all crew and agent associations without deleting the source itself.
    The source remains in the registry and can be re-bound later.

    GAP-103: DELETE /knowledge/{id}/unbind removes crew/agent associations
    """
    # Clear all associations
    success = update_knowledge_associations(
        source_id,
        crew_ids=[],
        agent_ids=[],
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Knowledge source '{source_id}' not found")

    logger.info(f"Unbound all associations for source {source_id}")
    # Returns 204 No Content

@router.get(
    "/{source_id}/chunks",
    response_model=ChunksResponse,
    responses=response_with_errors(404, 500),
)
async def get_chunks(source_id: str) -> ChunksResponse:
    """Get indexed chunks for a knowledge source.

    Returns the text content of all chunks indexed for this knowledge source
    by querying Qdrant directly (works even after server restart).

    GAP-104: GET /knowledge/{id}/chunks returns indexed chunks for preview
    """
    # Verify the source exists in registry
    source_info = get_knowledge_source_info(source_id)
    if source_info is None:
        raise HTTPException(status_code=404, detail=f"Knowledge source '{source_id}' not found")

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from core.knowledge.config import get_knowledge_config

        settings = get_settings()
        config = get_knowledge_config()
        client = QdrantClient(url=settings.qdrant_url)

        # Scroll through Qdrant to get all chunks for this source_id
        chunks: list[str] = []
        offset = None

        # Try new hybrid collection first
        try:
            while True:
                scroll_result = client.scroll(
                    collection_name=config.collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="source_id",
                                match=MatchValue(value=source_id),
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = scroll_result
                for point in points:
                    content = point.payload.get("content", "") if point.payload else ""
                    if content:
                        chunks.append(content)
                if next_offset is None:
                    break
                offset = next_offset
        except Exception as e:
            logger.warning(f"Could not read from hybrid collection: {e}")

        # Also try legacy collection if no results from new one
        if not chunks:
            try:
                offset = None
                while True:
                    scroll_result = client.scroll(
                        collection_name=config.legacy_collection,
                        scroll_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="source_id",
                                    match=MatchValue(value=source_id),
                                )
                            ]
                        ),
                        limit=100,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    points, next_offset = scroll_result
                    for point in points:
                        content = point.payload.get("content", "") if point.payload else ""
                        if content:
                            chunks.append(content)
                    if next_offset is None:
                        break
                    offset = next_offset
            except Exception as e:
                logger.warning(f"Could not read from legacy collection: {e}")

        # Sort by chunk_index if available in payload
        logger.info(f"Retrieved {len(chunks)} chunks for source {source_id}")
        return ChunksResponse(
            source_id=source_id,
            chunks=chunks,
            total=len(chunks),
        )

    except Exception as e:
        logger.exception(f"Error retrieving chunks for {source_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chunks. Check vector store connection.",
        ) from e
