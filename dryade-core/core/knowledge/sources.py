"""Knowledge Sources - CrewAI native knowledge integration.

Target: ~50 LOC
"""

import logging
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

# CrewAI knowledge imports (may not be available in all versions)
try:
    from crewai.knowledge.source import (
        CSVKnowledgeSource,
        PDFKnowledgeSource,
        TextFileKnowledgeSource,
    )

    KNOWLEDGE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_AVAILABLE = False
    PDFKnowledgeSource = None
    TextFileKnowledgeSource = None
    CSVKnowledgeSource = None

logger = logging.getLogger(__name__)

class KnowledgeSourceInfo(BaseModel):
    """Knowledge source metadata."""

    id: str
    name: str
    source_type: str
    file_paths: list[str]
    description: str | None = None
    crew_ids: list[str] = []
    agent_ids: list[str] = []
    chunk_count: int = 0  # GAP-107: Chunk count for display
    created_at: str | None = None  # ISO timestamp from DB

# Registry of available knowledge sources
_knowledge_registry: dict[str, Any] = {}
_knowledge_lock = threading.Lock()

# =============================================================================
# Persistence functions (Phase 94.1)
# =============================================================================

def persist_knowledge_source(
    source_id: str,
    name: str,
    source_type: str,
    file_paths: list[str],
    description: str | None = None,
    crew_ids: list[str] | None = None,
    agent_ids: list[str] | None = None,
    chunk_count: int = 0,
) -> None:
    """Persist knowledge source metadata to the database.

    Uses upsert pattern: updates existing record or inserts new one.
    DB errors are logged but never crash the server -- in-memory registry is primary.
    """
    try:
        from core.database.models import KnowledgeSourceRecord
        from core.database.session import get_session

        with get_session() as session:
            existing = session.get(KnowledgeSourceRecord, source_id)
            if existing:
                existing.name = name
                existing.source_type = source_type
                existing.file_paths = file_paths
                existing.description = description
                existing.crew_ids = crew_ids or []
                existing.agent_ids = agent_ids or []
                existing.chunk_count = chunk_count
            else:
                record = KnowledgeSourceRecord(
                    id=source_id,
                    name=name,
                    source_type=source_type,
                    file_paths=file_paths,
                    description=description,
                    crew_ids=crew_ids or [],
                    agent_ids=agent_ids or [],
                    chunk_count=chunk_count,
                )
                session.add(record)
        logger.info(f"Persisted knowledge source to DB: {source_id}")
    except Exception as e:
        logger.error(f"Failed to persist knowledge source {source_id}: {e}")

def delete_persisted_knowledge_source(source_id: str) -> None:
    """Delete knowledge source metadata from the database.

    DB errors are logged but never crash the server.
    """
    try:
        from core.database.models import KnowledgeSourceRecord
        from core.database.session import get_session

        with get_session() as session:
            record = session.get(KnowledgeSourceRecord, source_id)
            if record:
                session.delete(record)
        logger.info(f"Deleted knowledge source from DB: {source_id}")
    except Exception as e:
        logger.error(f"Failed to delete persisted knowledge source {source_id}: {e}")

def load_knowledge_registry_from_db() -> None:
    """Load knowledge source metadata from DB into in-memory registry.

    Called on startup to restore registry state. Source objects are None since
    CrewAI source objects cannot be reconstructed from metadata alone, but the
    registry presence allows list_knowledge_sources() to return data.
    """
    try:
        from core.database.models import KnowledgeSourceRecord
        from core.database.session import get_session

        with get_session() as session:
            rows = session.query(KnowledgeSourceRecord).all()
            count = 0
            with _knowledge_lock:
                for row in rows:
                    if row.id not in _knowledge_registry:
                        _knowledge_registry[row.id] = {
                            "name": row.name,
                            "source": None,  # Cannot reconstruct CrewAI source from metadata
                            "description": row.description,
                            "metadata": {
                                "source_id": row.id,
                                "crew_ids": row.crew_ids or [],
                                "agent_ids": row.agent_ids or [],
                            },
                            "crew_ids": row.crew_ids or [],
                            "agent_ids": row.agent_ids or [],
                            "source_type": row.source_type,
                            "file_paths": row.file_paths or [],
                            "chunk_count": row.chunk_count or 0,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                        }
                        count += 1
            logger.info(f"Loaded {count} knowledge sources from DB")
    except Exception as e:
        logger.error(f"Failed to load knowledge registry from DB: {e}")

# =============================================================================
# Registry functions
# =============================================================================

def register_knowledge_source(
    name: str,
    source: Any,
    description: str = "",
    metadata: dict | None = None,
    crew_ids: list[str] | None = None,
    agent_ids: list[str] | None = None,
    chunk_count: int | None = None,
    source_type: str | None = None,
    file_paths: list[str] | None = None,
) -> str:
    """Register a knowledge source with optional crew/agent associations.

    Args:
        name: Display name.
        source: CrewAI source object (or None for pipeline-based uploads).
        description: Human-readable description.
        metadata: Metadata dict (must include source_id).
        crew_ids: Associated crew IDs.
        agent_ids: Associated agent IDs.
        chunk_count: Override chunk count (used by IngestPipeline).
        source_type: Override source type string (used when source is None).
        file_paths: Override file paths list (used when source is None).
    """
    # Generate source_id from metadata or default
    source_id = metadata.get("source_id") if metadata else f"ks_{name}"

    # Build full metadata
    full_metadata = metadata or {}
    if crew_ids:
        full_metadata["crew_ids"] = crew_ids
    if agent_ids:
        full_metadata["agent_ids"] = agent_ids

    # Determine source type and file paths for persistence
    # Use explicit overrides first, then derive from source object
    _source_type = source_type or (type(source).__name__ if source is not None else "Unknown")
    _file_paths: list[str] = file_paths if file_paths is not None else []
    if not _file_paths and hasattr(source, "file_paths"):
        _file_paths = source.file_paths
    _chunk_count = chunk_count if chunk_count is not None else 0
    if _chunk_count == 0 and hasattr(source, "chunks") and source is not None:
        _chunk_count = len(source.chunks)

    with _knowledge_lock:
        _knowledge_registry[source_id] = {
            "name": name,
            "source": source,
            "description": description,
            "metadata": full_metadata,
            "crew_ids": crew_ids or [],
            "agent_ids": agent_ids or [],
            "source_type": _source_type,
            "file_paths": _file_paths,
            "chunk_count": _chunk_count,
        }

        # Set created_at for newly registered sources
        try:
            from datetime import UTC, datetime

            _knowledge_registry[source_id]["created_at"] = datetime.now(UTC).isoformat()
        except Exception:
            pass

    logger.info(
        f"Registered knowledge source: {source_id} (crews: {crew_ids}, agents: {agent_ids})"
    )

    # Persist to database OUTSIDE the lock (DB has its own locking)
    persist_knowledge_source(
        source_id=source_id,
        name=name,
        source_type=_source_type,
        file_paths=_file_paths,
        description=description,
        crew_ids=crew_ids,
        agent_ids=agent_ids,
        chunk_count=_chunk_count,
    )

    return source_id

def get_knowledge_source(source_id: str) -> Any | None:
    """Get a registered knowledge source."""
    with _knowledge_lock:
        entry = _knowledge_registry.get(source_id)
    return entry["source"] if entry else None

def list_knowledge_sources() -> list[KnowledgeSourceInfo]:
    """List all registered knowledge sources.

    Handles entries where source is None (loaded from DB without CrewAI object)
    by using stored metadata fields directly from the registry entry.

    Takes a snapshot inside the lock, processes outside to minimize lock hold time.
    """
    with _knowledge_lock:
        snapshot = list(_knowledge_registry.items())

    sources = []
    for source_id, entry in snapshot:
        source = entry.get("source")

        # Get file_paths: from source object if available, else from stored metadata
        if source is not None and hasattr(source, "file_paths"):
            file_paths = source.file_paths
        else:
            file_paths = entry.get("file_paths", [])

        # Get chunk_count: from source object if available, else from stored metadata
        if source is not None and hasattr(source, "chunks"):
            chunk_count = len(source.chunks)
        else:
            chunk_count = entry.get("chunk_count", 0)

        # Get source_type: from source object if available, else from stored metadata
        if source is not None:
            source_type = type(source).__name__
        else:
            source_type = entry.get("source_type", "Unknown")

        created_at = entry.get("created_at")

        sources.append(
            KnowledgeSourceInfo(
                id=source_id,
                name=entry["name"],
                source_type=source_type,
                file_paths=file_paths,
                description=entry.get("description"),
                crew_ids=entry.get("crew_ids", []),
                agent_ids=entry.get("agent_ids", []),
                chunk_count=chunk_count,
                created_at=created_at,
            )
        )
    return sources

def create_pdf_source(name: str, file_paths: list[str], description: str = "") -> str | None:
    """Create and register a PDF knowledge source."""
    if not KNOWLEDGE_AVAILABLE or not PDFKnowledgeSource:
        return None

    # Validate paths exist
    valid_paths = [p for p in file_paths if Path(p).exists()]
    if not valid_paths:
        return None

    source = PDFKnowledgeSource(file_paths=valid_paths)
    return register_knowledge_source(name, source, description)

def create_text_source(name: str, file_paths: list[str], description: str = "") -> str | None:
    """Create and register a text file knowledge source."""
    if not KNOWLEDGE_AVAILABLE or not TextFileKnowledgeSource:
        return None

    valid_paths = [p for p in file_paths if Path(p).exists()]
    if not valid_paths:
        return None

    source = TextFileKnowledgeSource(file_paths=valid_paths)
    return register_knowledge_source(name, source, description)

def create_csv_source(name: str, file_paths: list[str], description: str = "") -> str | None:
    """Create and register a CSV knowledge source."""
    if not KNOWLEDGE_AVAILABLE or not CSVKnowledgeSource:
        return None

    valid_paths = [p for p in file_paths if Path(p).exists()]
    if not valid_paths:
        return None

    source = CSVKnowledgeSource(file_paths=valid_paths)
    return register_knowledge_source(name, source, description)

def create_docx_source(name: str, file_paths: list[str], description: str = "") -> str | None:
    """Create and register a DOCX knowledge source.

    Uses IngestPipeline for parsing (not CrewAI), so source object is None.
    """
    valid_paths = [p for p in file_paths if Path(p).exists()]
    if not valid_paths:
        return None

    return register_knowledge_source(
        name,
        source=None,
        description=description,
        source_type="DocxSource",
        file_paths=valid_paths,
    )

def create_xlsx_source(name: str, file_paths: list[str], description: str = "") -> str | None:
    """Create and register an XLSX knowledge source.

    Uses IngestPipeline for parsing (not CrewAI), so source object is None.
    """
    valid_paths = [p for p in file_paths if Path(p).exists()]
    if not valid_paths:
        return None

    return register_knowledge_source(
        name,
        source=None,
        description=description,
        source_type="XlsxSource",
        file_paths=valid_paths,
    )

def create_html_source(name: str, file_paths: list[str], description: str = "") -> str | None:
    """Create and register an HTML knowledge source.

    Uses IngestPipeline for parsing (not CrewAI), so source object is None.
    """
    valid_paths = [p for p in file_paths if Path(p).exists()]
    if not valid_paths:
        return None

    return register_knowledge_source(
        name,
        source=None,
        description=description,
        source_type="HtmlSource",
        file_paths=valid_paths,
    )

def get_crew_knowledge_sources() -> list[Any]:
    """Get all knowledge sources for crew configuration."""
    with _knowledge_lock:
        snapshot = list(_knowledge_registry.values())
    return [entry["source"] for entry in snapshot if entry["source"] is not None]

def get_all_knowledge_sources() -> list:
    """Get all registered knowledge sources for crew configuration."""
    from crewai.knowledge.source import BaseKnowledgeSource

    with _knowledge_lock:
        snapshot = list(_knowledge_registry.values())

    sources = []
    for entry in snapshot:
        source = entry["source"]
        # Only return actual CrewAI knowledge sources
        if source is not None and isinstance(source, BaseKnowledgeSource):
            sources.append(source)

    logger.info(f"Retrieved {len(sources)} knowledge sources for crew")
    return sources

def delete_knowledge_source(source_id: str) -> bool:
    """Delete a knowledge source from registry and database.

    Uses atomic check-then-act inside the lock to prevent double-delete races.
    DB deletion happens outside the lock (DB has its own locking).
    """
    with _knowledge_lock:
        if source_id in _knowledge_registry:
            del _knowledge_registry[source_id]
            deleted = True
        else:
            deleted = False

    if deleted:
        logger.info(f"Deleted knowledge source from registry: {source_id}")
        # Remove from database OUTSIDE the lock (non-blocking, errors logged)
        delete_persisted_knowledge_source(source_id)

    return deleted

def get_knowledge_source_info(source_id: str) -> KnowledgeSourceInfo | None:
    """Get metadata for a knowledge source."""
    with _knowledge_lock:
        entry = _knowledge_registry.get(source_id)
    if not entry:
        return None

    source = entry.get("source")

    # Get file_paths: from source object if available, else from stored metadata
    if source is not None and hasattr(source, "file_paths"):
        file_paths = source.file_paths
    else:
        file_paths = entry.get("file_paths", [])

    # Get chunk_count: from source object if available, else from stored metadata
    if source is not None and hasattr(source, "chunks"):
        chunk_count = len(source.chunks)
    else:
        chunk_count = entry.get("chunk_count", 0)

    # Get source_type
    if source is not None:
        source_type = type(source).__name__
    else:
        source_type = entry.get("source_type", "Unknown")

    created_at = entry.get("created_at")

    return KnowledgeSourceInfo(
        id=source_id,
        name=entry["name"],
        source_type=source_type,
        file_paths=file_paths,
        description=entry.get("description"),
        crew_ids=entry.get("crew_ids", []),
        agent_ids=entry.get("agent_ids", []),
        chunk_count=chunk_count,
        created_at=created_at,
    )

def update_knowledge_associations(
    source_id: str,
    crew_ids: list[str] | None = None,
    agent_ids: list[str] | None = None,
) -> bool:
    """Update crew/agent associations for a knowledge source.

    Args:
        source_id: The knowledge source ID to update.
        crew_ids: List of crew IDs to associate (None = don't change, [] = clear).
        agent_ids: List of agent IDs to associate (None = don't change, [] = clear).

    Returns:
        True if source was found and updated, False if not found.
    """
    with _knowledge_lock:
        entry = _knowledge_registry.get(source_id)
        if not entry:
            return False

        # Update crew_ids if provided (None means don't change)
        if crew_ids is not None:
            entry["crew_ids"] = crew_ids
            entry["metadata"]["crew_ids"] = crew_ids

        # Update agent_ids if provided (None means don't change)
        if agent_ids is not None:
            entry["agent_ids"] = agent_ids
            entry["metadata"]["agent_ids"] = agent_ids

        updated_crews = entry.get("crew_ids")
        updated_agents = entry.get("agent_ids")

    logger.info(
        f"Updated knowledge source associations: {source_id} "
        f"(crews: {updated_crews}, agents: {updated_agents})"
    )
    return True

def get_knowledge_sources_for_crew(crew_id: str) -> list:
    """Get knowledge sources associated with a specific crew."""
    from crewai.knowledge.source import BaseKnowledgeSource

    with _knowledge_lock:
        snapshot = list(_knowledge_registry.values())

    sources = []
    for entry in snapshot:
        # Check if crew_id matches
        crew_ids = entry.get("crew_ids", [])
        if not crew_ids or crew_id in crew_ids:
            # Empty crew_ids = available to all crews
            source = entry["source"]
            if source is not None and isinstance(source, BaseKnowledgeSource):
                sources.append(source)

    logger.info(f"Found {len(sources)} knowledge sources for crew '{crew_id}'")
    return sources
