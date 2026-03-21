"""Dryade Knowledge Sources.

Native CrewAI knowledge integration with hybrid search (dense + sparse + RRF fusion),
cross-encoder reranking, and decoupled IngestPipeline.
"""

from core.knowledge.chunker import Chunk, ChunkingService
from core.knowledge.config import KnowledgeConfig, get_knowledge_config
from core.knowledge.context import get_knowledge_context
from core.knowledge.embedder import (
    EmbeddingService,
    get_crew_embedder,
    get_crew_storage,
    get_embedding_service,
)
from core.knowledge.parsers import parse_docx, parse_html, parse_xlsx
from core.knowledge.pipeline import IngestPipeline, IngestResult, get_ingest_pipeline
from core.knowledge.sources import (
    KNOWLEDGE_AVAILABLE,
    KnowledgeSourceInfo,
    create_csv_source,
    create_docx_source,
    create_html_source,
    create_pdf_source,
    create_text_source,
    create_xlsx_source,
    delete_knowledge_source,
    get_all_knowledge_sources,
    get_crew_knowledge_sources,
    get_knowledge_source,
    get_knowledge_source_info,
    get_knowledge_sources_for_crew,
    list_knowledge_sources,
    register_knowledge_source,
)
from core.knowledge.storage import HybridVectorStore
from core.knowledge.summary_index import SummaryIndex
from core.knowledge.vector_store import VectorStoreBackend

# Optional backends (imported only if their dependencies are available)
try:
    from core.knowledge.pgvector_store import PgvectorStore
except ImportError:
    PgvectorStore = None  # type: ignore[assignment,misc]

try:
    from core.knowledge.chroma_store import ChromaStore
except ImportError:
    ChromaStore = None  # type: ignore[assignment,misc]

__all__ = [
    # Context
    "get_knowledge_context",
    # Config
    "KnowledgeConfig",
    "get_knowledge_config",
    # Embedder
    "EmbeddingService",
    "get_embedding_service",
    "get_crew_embedder",
    "get_crew_storage",
    # Chunking
    "ChunkingService",
    "Chunk",
    # Pipeline
    "IngestPipeline",
    "IngestResult",
    "get_ingest_pipeline",
    # Parsers
    "parse_docx",
    "parse_xlsx",
    "parse_html",
    # Storage
    "HybridVectorStore",
    "VectorStoreBackend",
    "PgvectorStore",
    "ChromaStore",
    "SummaryIndex",
    # Sources (legacy + current)
    "KnowledgeSourceInfo",
    "KNOWLEDGE_AVAILABLE",
    "register_knowledge_source",
    "get_knowledge_source",
    "list_knowledge_sources",
    "create_pdf_source",
    "create_text_source",
    "create_csv_source",
    "create_docx_source",
    "create_xlsx_source",
    "create_html_source",
    "get_crew_knowledge_sources",
    "get_all_knowledge_sources",
    "delete_knowledge_source",
    "get_knowledge_source_info",
    "get_knowledge_sources_for_crew",
]
