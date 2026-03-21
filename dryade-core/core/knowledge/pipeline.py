"""Ingest Pipeline for Knowledge/RAG System.

Decoupled document ingestion: parse -> chunk -> embed (dense+sparse) -> store.
No dependency on CrewAI source objects.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from core.knowledge.chunker import ChunkingService
from core.knowledge.embedder import EmbeddingService
from core.knowledge.vector_store import VectorStoreBackend

logger = logging.getLogger(__name__)

@dataclass
class IngestResult:
    """Result of a document ingestion operation."""

    source_id: str
    chunk_count: int
    file_path: str

class IngestPipeline:
    """Document ingestion: parse -> chunk -> embed (dense+sparse) -> store.

    Fully decoupled from CrewAI source objects. Accepts raw file paths
    and processes them through the full RAG pipeline into Qdrant.
    """

    def __init__(
        self,
        chunker: ChunkingService,
        embedder: EmbeddingService,
        store: VectorStoreBackend,
    ):
        self.chunker = chunker
        self.embedder = embedder
        self.store = store

    async def ingest(
        self,
        file_path: str,
        source_id: str,
        metadata: dict | None = None,
    ) -> IngestResult:
        """Ingest a document file into the vector store.

        Steps:
            1. Parse document to plain text (file extension dispatch).
            2. Chunk with configurable recursive splitting.
            3. Generate dense + sparse embeddings.
            4. Store in Qdrant with named vectors.

        Args:
            file_path: Path to the document file.
            source_id: Unique identifier for this knowledge source.
            metadata: Optional metadata dict to attach to every chunk.

        Returns:
            IngestResult with source_id, chunk_count, file_path.
        """
        metadata = metadata or {}
        metadata["source_id"] = source_id
        metadata["file_path"] = file_path

        # 1. Parse document to text
        text = await asyncio.to_thread(self._parse_document, file_path)

        # 2. Chunk with configurable strategy
        chunks = self.chunker.chunk(text, metadata)

        if not chunks:
            logger.info(f"No chunks produced for '{file_path}' (source={source_id})")
            return IngestResult(source_id=source_id, chunk_count=0, file_path=file_path)

        # 3. Generate dense + sparse embeddings
        texts = [c.text for c in chunks]
        dense_vectors = await asyncio.to_thread(self.embedder.embed_dense, texts)
        sparse_vectors = await asyncio.to_thread(self.embedder.embed_sparse, texts)

        # 4. Build metadata per chunk
        chunk_metadata = [c.metadata for c in chunks]

        # 5. Store in Qdrant with named vectors
        await asyncio.to_thread(
            self.store.add, texts, chunk_metadata, dense_vectors, sparse_vectors
        )

        logger.info(f"Ingested '{file_path}' (source={source_id}): {len(chunks)} chunks stored")
        return IngestResult(
            source_id=source_id,
            chunk_count=len(chunks),
            file_path=file_path,
        )

    # -- Document parsing ----------------------------------------------------

    def _parse_document(self, file_path: str) -> str:
        """Parse document to plain text based on file extension.

        Supported formats:
            .txt, .md  -- read as-is
            .csv       -- read as-is (rows become text)
            .pdf       -- multi-strategy parsing (pdfplumber > CrewAI)
            other      -- attempt as plain text

        Args:
            file_path: Path to the document file.

        Returns:
            Extracted plain text content.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in (".txt", ".md"):
            return path.read_text(encoding="utf-8")
        elif ext == ".csv":
            return path.read_text(encoding="utf-8")
        elif ext == ".pdf":
            return self._parse_pdf(path)
        elif ext == ".docx":
            from core.knowledge.parsers import parse_docx

            return parse_docx(path)
        elif ext in (".xlsx", ".xls"):
            from core.knowledge.parsers import parse_xlsx

            return parse_xlsx(path)
        elif ext in (".html", ".htm"):
            from core.knowledge.parsers import parse_html

            return parse_html(path)
        else:
            # Try as text
            return path.read_text(encoding="utf-8")

    def _parse_pdf(self, path: Path) -> str:
        """Parse PDF to text with multi-strategy fallback.

        Tries in order:
            1. pdfplumber -- primary parser (good for tables/structured PDFs)
            2. CrewAI PDFKnowledgeSource -- last resort fallback

        Args:
            path: Path to PDF file.

        Returns:
            Extracted text.

        Raises:
            ImportError: If no PDF parser is available.
        """
        # Strategy 1: pdfplumber (primary)
        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            pass

        # Strategy 2: Try CrewAI PDF source as fallback
        try:
            from crewai.knowledge.source import PDFKnowledgeSource

            source = PDFKnowledgeSource(file_paths=[str(path)])
            # Access raw content before chunking
            if hasattr(source, "content"):
                return source.content
        except (ImportError, Exception):
            pass

        raise ImportError("No PDF parser available. Install pdfplumber: pip install pdfplumber")

# ---------------------------------------------------------------------------
# Factory / Singleton
# ---------------------------------------------------------------------------

_pipeline_instance: IngestPipeline | None = None

def get_ingest_pipeline() -> IngestPipeline:
    """Get or create singleton IngestPipeline.

    Wires together ChunkingService, EmbeddingService, and HybridVectorStore
    from their respective singletons/factories.
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        from core.config import get_settings
        from core.knowledge.config import get_knowledge_config
        from core.knowledge.embedder import get_embedding_service

        config = get_knowledge_config()
        settings = get_settings()

        backend = getattr(config, "vector_backend", "qdrant")

        if backend == "pgvector":
            from core.knowledge.pgvector_store import PgvectorStore

            store = PgvectorStore(connection_string=settings.database_url, config=config)
        elif backend == "chroma":
            from core.knowledge.chroma_store import ChromaStore

            persist_dir = getattr(settings, "chroma_persist_dir", None)
            if not persist_dir:
                import os

                persist_dir = os.path.join(os.path.expanduser("~"), ".dryade", "chroma_data")
            store = ChromaStore(persist_directory=persist_dir, config=config)
        else:
            # Default: Qdrant
            from qdrant_client import QdrantClient

            from core.knowledge.storage import HybridVectorStore

            client = QdrantClient(url=settings.qdrant_url)
            store = HybridVectorStore(client=client, config=config)

        embedder = get_embedding_service()
        chunker = ChunkingService(config)

        _pipeline_instance = IngestPipeline(chunker=chunker, embedder=embedder, store=store)
        logger.info("Initialized IngestPipeline singleton")
    return _pipeline_instance

def reset_pipeline():
    """Reset singleton (for testing)."""
    global _pipeline_instance
    _pipeline_instance = None
