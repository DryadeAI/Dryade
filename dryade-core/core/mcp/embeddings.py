"""MCP Tool Embedding Store - Semantic search via Qdrant.

Stores vector embeddings of MCP server and tool descriptions for
semantic similarity search. Powers the hierarchical router's
two-stage semantic matching.

Features:
- Server-level embeddings (coarse filter)
- Tool-level embeddings (fine-grained ranking)
- Local SentenceTransformer embedding generation (no remote API calls)
- Dimension-aware collection management (auto-recreate on model switch)
- Graceful degradation when Qdrant unavailable
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sentence_transformers import SentenceTransformer

from core.config import get_settings

logger = logging.getLogger(__name__)

# Qdrant imports - graceful degradation if not installed
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    QdrantClient = None  # type: ignore
    logger.warning("qdrant-client not installed - semantic search disabled")

# Collection names
TOOL_COLLECTION = "mcp_tools"
SERVER_COLLECTION = "mcp_servers"

# Embedding dimensions fallback (all-MiniLM-L6-v2 default)
EMBEDDING_DIM = 384

@dataclass
class EmbeddingResult:
    """Result from semantic search.

    Attributes:
        id: Unique identifier for the result (UUID from Qdrant)
        name: Tool or server name
        server: Server name (same as name for server results)
        score: Similarity score (0-1, higher is more similar)
        payload: Full payload from Qdrant with additional metadata
    """

    id: str
    name: str
    server: str
    score: float
    payload: dict[str, Any]

class ToolEmbeddingStore:
    """Qdrant-backed embedding store for MCP tools.

    Stores two types of embeddings:
    1. Server embeddings: Coarse-grained server descriptions
    2. Tool embeddings: Fine-grained tool descriptions

    Uses a local SentenceTransformer model for embedding generation
    (no remote API calls). The model is lazy-loaded on first use.

    The store gracefully degrades when Qdrant is unavailable,
    returning empty results rather than raising exceptions.

    Usage:
        store = ToolEmbeddingStore()
        store.index_server("mcp-filesystem", "File system tools for reading and writing")
        store.index_tool(tool_entry)

        # Semantic search
        results = store.search_tools("edit diagram elements", top_k=10)
        server_results = store.search_servers("model editing", top_k=3)

        # Search within specific server
        results = store.search_tools("read file", server_filter="mcp-filesystem")
    """

    def __init__(
        self,
        url: str | None = None,
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        """Initialize embedding store.

        Args:
            url: Qdrant URL. Defaults to settings.qdrant_url or localhost:6333.
            embedding_model: SentenceTransformer model name. Defaults to all-MiniLM-L6-v2.
        """
        settings = get_settings()
        self.url = url or getattr(settings, "qdrant_url", None) or "http://localhost:6333"
        self.embedding_model = embedding_model
        self._model_name = embedding_model
        self._encoder: SentenceTransformer | None = None

        self._client: QdrantClient | None = None
        self._available = False
        self._lock = threading.Lock()

    def _ensure_encoder(self) -> SentenceTransformer:
        """Lazy-load the SentenceTransformer model.

        Returns:
            Loaded SentenceTransformer encoder.
        """
        if self._encoder is None:
            logger.info(f"Loading embedding model: {self._model_name}")
            self._encoder = SentenceTransformer(self._model_name)
        return self._encoder

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension from the loaded model.

        Returns:
            Embedding vector dimension (e.g., 384 for all-MiniLM-L6-v2).
        """
        encoder = self._ensure_encoder()
        dim = encoder.get_sentence_embedding_dimension()
        return dim if dim else EMBEDDING_DIM

    def _ensure_client(self) -> bool:
        """Lazy initialize Qdrant client and collections.

        Returns:
            True if Qdrant is available and initialized.
        """
        if not QDRANT_AVAILABLE:
            return False

        if self._client is not None:
            return self._available

        with self._lock:
            # Double-check after acquiring lock
            if self._client is not None:
                return self._available

            try:
                logger.info(f"Connecting to Qdrant at {self.url}")
                self._client = QdrantClient(url=self.url, timeout=10)

                # Create collections if needed
                self._ensure_collection(TOOL_COLLECTION)
                self._ensure_collection(SERVER_COLLECTION)

                self._available = True
                logger.info("Tool embedding store initialized")

                # Auto-populate empty collections (XR-C02 fix)
                # Called after _available=True so ensure_indexed()'s
                # _ensure_client() short-circuits without recursion.
                self.ensure_indexed()

            except Exception as e:
                logger.warning(
                    f"Qdrant connection failed ({self.url}): {e}. "
                    "Semantic tool routing disabled -- falling back to regex matching."
                )
                self._available = False

        return self._available

    def _ensure_collection(self, name: str) -> None:
        """Create collection if it doesn't exist, or recreate on dimension mismatch.

        Detects when the embedding model has changed (different vector dimension)
        and auto-recreates the collection to match the new model.

        Args:
            name: Collection name to create.
        """
        if self._client is None:
            return

        collections = self._client.get_collections().collections
        collection_names = [c.name for c in collections]
        current_dim = self.embedding_dim

        if name in collection_names:
            info = self._client.get_collection(name)
            existing_dim = info.config.params.vectors.size
            if existing_dim != current_dim:
                logger.warning(
                    f"Collection '{name}' dimension mismatch: "
                    f"existing={existing_dim}, model needs={current_dim}. Recreating."
                )
                self._client.delete_collection(name)
            else:
                return

        logger.info(f"Creating Qdrant collection: {name} (dim={current_dim})")
        self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=current_dim, distance=Distance.COSINE),
        )

    def ensure_indexed(self) -> bool:
        """Ensure Qdrant collections are populated with tool embeddings.

        Detects empty collections (e.g. after dimension-mismatch recreation)
        and triggers re-indexing from the ToolIndex registry. This is the
        XR-C02 fix: without this, Phase 109's dimension migration leaves
        Qdrant empty, disabling Phase 107's router filtering.

        Called automatically from _ensure_client() (safety net) and
        optionally from startup (pre-warm).

        Returns:
            True if collections have data (or were successfully populated).
        """
        if not self._ensure_client():
            return False

        try:
            tool_info = self._client.get_collection(TOOL_COLLECTION)
            server_info = self._client.get_collection(SERVER_COLLECTION)
            tool_count = tool_info.points_count
            server_count = server_info.points_count

            if tool_count > 0 and server_count > 0:
                return True

            logger.warning(
                "[EMBEDDINGS] Empty collections detected: tools=%d, servers=%d. "
                "Triggering re-indexing.",
                tool_count,
                server_count,
            )

            from core.mcp.tool_index import get_tool_index

            tool_index = get_tool_index()
            if not tool_index.is_populated:
                tool_index.populate_from_registry()

            success, failure = self.index_from_tool_index(tool_index)
            logger.info(
                "[EMBEDDINGS] Re-indexing complete: %d succeeded, %d failed",
                success,
                failure,
            )
            return success > 0

        except Exception as e:
            logger.warning("[EMBEDDINGS] ensure_indexed failed: %s", e)
            return False

    def _get_embedding(self, text: str) -> list[float] | None:
        """Get embedding vector using local SentenceTransformer.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector or None on failure.
        """
        try:
            encoder = self._ensure_encoder()
            embedding = encoder.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return embedding.tolist()
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None

    def _generate_point_id(self, identifier: str) -> str:
        """Generate deterministic UUID from identifier.

        Uses SHA256 to create a reproducible UUID from any string,
        ensuring the same tool always maps to the same point ID.

        Args:
            identifier: Unique string identifier (e.g., fingerprint)

        Returns:
            UUID string for Qdrant point ID.
        """
        hash_bytes = hashlib.sha256(identifier.encode()).digest()[:16]
        return str(uuid.UUID(bytes=hash_bytes))

    def index_server(self, server_name: str, description: str) -> bool:
        """Index a server's description.

        Args:
            server_name: Server name (e.g., "mcp-filesystem")
            description: Server description text

        Returns:
            True if indexed successfully.
        """
        if not self._ensure_client():
            return False

        embedding = self._get_embedding(description)
        if embedding is None:
            return False

        point_id = self._generate_point_id(f"server:{server_name}")

        try:
            self._client.upsert(
                collection_name=SERVER_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "name": server_name,
                            "description": description,
                        },
                    )
                ],
            )
            logger.debug(f"Indexed server: {server_name}")
            return True

        except Exception as e:
            logger.warning(f"Failed to index server {server_name}: {e}")
            return False

    def index_tool(self, tool_entry: ToolEntry) -> bool:
        """Index a tool from ToolEntry.

        Args:
            tool_entry: ToolEntry from tool_index

        Returns:
            True if indexed successfully.
        """
        if not self._ensure_client():
            return False

        # Create embedding text from name and description
        text = f"{tool_entry.name}: {tool_entry.description_preview}"
        embedding = self._get_embedding(text)
        if embedding is None:
            return False

        point_id = self._generate_point_id(tool_entry.fingerprint)

        try:
            self._client.upsert(
                collection_name=TOOL_COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "name": tool_entry.name,
                            "server": tool_entry.server,
                            "description": tool_entry.description_preview,
                            "fingerprint": tool_entry.fingerprint,
                            "params": tool_entry.input_schema_keys,
                        },
                    )
                ],
            )
            logger.debug(f"Indexed tool: {tool_entry.name}")
            return True

        except Exception as e:
            logger.warning(f"Failed to index tool {tool_entry.name}: {e}")
            return False

    def index_from_tool_index(self, tool_index: ToolIndex) -> tuple[int, int]:
        """Bulk index all tools from a ToolIndex.

        Indexes both server descriptions (auto-generated from tool names)
        and individual tool entries.

        Args:
            tool_index: ToolIndex instance to index from

        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failure = 0

        # Index by server for better batching
        for server in tool_index.servers:
            entries = tool_index.get_by_server(server)

            # Index server description (use first few tool names as proxy)
            if entries:
                server_desc = f"MCP server {server} providing tools: " + ", ".join(
                    e.name for e in entries[:5]
                )
                if len(entries) > 5:
                    server_desc += f" and {len(entries) - 5} more"
                self.index_server(server, server_desc)

            # Index individual tools
            for entry in entries:
                if self.index_tool(entry):
                    success += 1
                else:
                    failure += 1

        logger.info(f"Indexed {success} tools ({failure} failures)")
        return success, failure

    def search_servers(self, query: str, top_k: int = 5) -> list[EmbeddingResult]:
        """Search servers by semantic similarity.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of EmbeddingResult sorted by score (highest first).
        """
        if not self._ensure_client():
            return []

        embedding = self._get_embedding(query)
        if embedding is None:
            return []

        try:
            response = self._client.query_points(
                collection_name=SERVER_COLLECTION,
                query=embedding,
                limit=top_k,
            )

            return [
                EmbeddingResult(
                    id=str(r.id),
                    name=r.payload.get("name", ""),
                    server=r.payload.get("name", ""),  # Server name is the name
                    score=r.score,
                    payload=r.payload,
                )
                for r in response.points
            ]

        except Exception as e:
            logger.warning(f"Server search failed: {e}")
            return []

    def search_tools(
        self,
        query: str,
        top_k: int = 10,
        server_filter: str | None = None,
    ) -> list[EmbeddingResult]:
        """Search tools by semantic similarity.

        Args:
            query: Search query
            top_k: Number of results
            server_filter: Optional server to restrict search

        Returns:
            List of EmbeddingResult sorted by score (highest first).
        """
        if not self._ensure_client():
            return []

        embedding = self._get_embedding(query)
        if embedding is None:
            return []

        # Build filter if server specified
        query_filter = None
        if server_filter:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="server",
                        match=MatchValue(value=server_filter),
                    )
                ]
            )

        try:
            response = self._client.query_points(
                collection_name=TOOL_COLLECTION,
                query=embedding,
                limit=top_k,
                query_filter=query_filter,
            )

            return [
                EmbeddingResult(
                    id=str(r.id),
                    name=r.payload.get("name", ""),
                    server=r.payload.get("server", ""),
                    score=r.score,
                    payload=r.payload,
                )
                for r in response.points
            ]

        except Exception as e:
            logger.warning(f"Tool search failed: {e}")
            return []

    def delete_tool(self, fingerprint: str) -> bool:
        """Delete a tool from the index.

        Args:
            fingerprint: Tool fingerprint

        Returns:
            True if deleted successfully.
        """
        if not self._ensure_client():
            return False

        point_id = self._generate_point_id(fingerprint)

        try:
            self._client.delete(
                collection_name=TOOL_COLLECTION,
                points_selector=[point_id],
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to delete tool: {e}")
            return False

    def delete_server(self, server_name: str) -> bool:
        """Delete a server from the index.

        Args:
            server_name: Server name

        Returns:
            True if deleted successfully.
        """
        if not self._ensure_client():
            return False

        point_id = self._generate_point_id(f"server:{server_name}")

        try:
            self._client.delete(
                collection_name=SERVER_COLLECTION,
                points_selector=[point_id],
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to delete server: {e}")
            return False

    def clear(self) -> bool:
        """Clear all indexed data.

        Deletes and recreates both collections.

        Returns:
            True if cleared successfully.
        """
        if not self._ensure_client():
            return False

        try:
            # Delete collections if they exist
            try:
                self._client.delete_collection(TOOL_COLLECTION)
            except Exception:
                pass  # Collection might not exist

            try:
                self._client.delete_collection(SERVER_COLLECTION)
            except Exception:
                pass  # Collection might not exist

            # Recreate collections
            self._ensure_collection(TOOL_COLLECTION)
            self._ensure_collection(SERVER_COLLECTION)
            return True

        except Exception as e:
            logger.warning(f"Failed to clear collections: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the embedding store.

        Returns:
            Dictionary with tool_count, server_count, and available status.
        """
        if not self._ensure_client():
            return {"available": False, "tool_count": 0, "server_count": 0}

        try:
            tool_info = self._client.get_collection(TOOL_COLLECTION)
            server_info = self._client.get_collection(SERVER_COLLECTION)

            return {
                "available": True,
                "tool_count": tool_info.points_count,
                "server_count": server_info.points_count,
                "tool_collection": TOOL_COLLECTION,
                "server_collection": SERVER_COLLECTION,
                "embedding_dim": self.embedding_dim,
                "embedding_model": self.embedding_model,
            }

        except Exception as e:
            logger.warning(f"Failed to get stats: {e}")
            return {"available": False, "tool_count": 0, "server_count": 0}

    @property
    def available(self) -> bool:
        """Check if store is available (Qdrant connected).

        Returns:
            True if Qdrant is connected and collections exist.
        """
        return self._ensure_client()

# Singleton pattern
_embedding_store: ToolEmbeddingStore | None = None
_embedding_store_lock = threading.Lock()

def get_tool_embedding_store(embedding_model: str | None = None) -> ToolEmbeddingStore:
    """Get or create singleton ToolEmbeddingStore instance.

    Args:
        embedding_model: Optional SentenceTransformer model name.
            Defaults to all-MiniLM-L6-v2. Callers can pass the user's
            preferred embedding model from their DB configuration.

    Returns:
        Shared ToolEmbeddingStore instance.
    """
    global _embedding_store
    if _embedding_store is None:
        with _embedding_store_lock:
            if _embedding_store is None:
                if not embedding_model:
                    from core.config import get_settings

                    embedding_model = get_settings().mcp_tool_embedding_model
                model = embedding_model
                _embedding_store = ToolEmbeddingStore(embedding_model=model)
    return _embedding_store

def reset_tool_embedding_store() -> None:
    """Reset the singleton embedding store (for testing).

    Clears the singleton so the next call to get_tool_embedding_store()
    creates a fresh instance.
    """
    global _embedding_store
    _embedding_store = None

# Type imports for runtime (avoid circular import)
if TYPE_CHECKING:
    from core.mcp.tool_index import ToolEntry, ToolIndex
else:
    # Lazy import at runtime when needed
    ToolEntry = None
    ToolIndex = None

def _get_tool_entry_class():
    """Lazy import ToolEntry to avoid circular import."""
    global ToolEntry
    if ToolEntry is None:
        from core.mcp.tool_index import ToolEntry as _ToolEntry

        ToolEntry = _ToolEntry
    return ToolEntry

def _get_tool_index_class():
    """Lazy import ToolIndex to avoid circular import."""
    global ToolIndex
    if ToolIndex is None:
        from core.mcp.tool_index import ToolIndex as _ToolIndex

        ToolIndex = _ToolIndex
    return ToolIndex
