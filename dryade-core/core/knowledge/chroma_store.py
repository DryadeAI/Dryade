"""ChromaDB Storage Backend for Knowledge/RAG Pipeline.

Lightweight, embedded vector store alternative -- no server required.
Dense-only search (ChromaDB does not support sparse vectors).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from core.knowledge.config import KnowledgeConfig
from core.knowledge.vector_store import VectorStoreBackend

logger = logging.getLogger(__name__)

class ChromaStore(VectorStoreBackend):
    """ChromaDB vector store backend using PersistentClient.

    Dense-only search with cosine distance. Provides an embedded,
    serverless alternative to Qdrant for simple deployments.
    """

    def __init__(self, persist_directory: str, config: KnowledgeConfig):
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb is required for the Chroma backend. Install it with: pip install chromadb"
            )

        self._config = config
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=config.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"Initialized ChromaStore at '{persist_directory}' "
            f"(collection='{config.collection_name}')"
        )

    def add(
        self,
        chunks: list[str],
        metadata: list[dict],
        dense_vectors: list[list[float]],
        sparse_vectors: list,
    ) -> None:
        """Add chunks with dense embeddings. Sparse vectors are ignored."""
        if not chunks:
            return

        if sparse_vectors:
            logger.debug("ChromaStore does not support sparse vectors; ignoring")

        ids = [str(uuid4()) for _ in chunks]
        metadatas = []
        for chunk, meta in zip(chunks, metadata):
            m = {**meta, "content": chunk}
            # ChromaDB requires metadata values to be str, int, float, or bool
            sanitized = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    sanitized[k] = v
                elif isinstance(v, list):
                    sanitized[k] = ",".join(str(i) for i in v)
                elif v is not None:
                    sanitized[k] = str(v)
            metadatas.append(sanitized)

        self._collection.add(
            ids=ids,
            embeddings=dense_vectors,
            documents=chunks,
            metadatas=metadatas,
        )
        logger.info(
            f"Added {len(chunks)} chunks to ChromaDB collection '{self._config.collection_name}'"
        )

    def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse,
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Hybrid search falls back to dense-only (Chroma has no sparse support)."""
        logger.debug("ChromaStore does not support sparse search; using dense-only")
        return self.dense_only_search(
            query_dense=query_dense,
            limit=limit,
            score_threshold=score_threshold,
            metadata_filter=metadata_filter,
        )

    def dense_only_search(
        self,
        query_dense: list[float],
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Dense vector search using cosine distance."""
        where_filter = None
        if metadata_filter:
            # Build Chroma where filter
            conditions = []
            for key, value in metadata_filter.items():
                if isinstance(value, dict) and "$in" in value:
                    conditions.append({key: {"$in": value["$in"]}})
                else:
                    conditions.append({key: value})

            if len(conditions) == 1:
                where_filter = conditions[0]
            elif len(conditions) > 1:
                where_filter = {"$and": conditions}

        kwargs = {"query_embeddings": [query_dense], "n_results": limit}
        if where_filter:
            kwargs["where"] = where_filter

        results = self._collection.query(**kwargs)

        formatted = []
        if results and results.get("documents"):
            documents = results["documents"][0]
            distances = results["distances"][0] if results.get("distances") else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []

            for i, doc in enumerate(documents):
                distance = distances[i] if i < len(distances) else 0.0
                score = 1.0 - distance  # cosine distance -> similarity
                if score >= score_threshold:
                    meta = metadatas[i] if i < len(metadatas) else {}
                    meta_clean = {k: v for k, v in meta.items() if k != "content"}
                    formatted.append({"content": doc, "score": score, "metadata": meta_clean})

        return formatted

    def delete(self, source_id: str) -> None:
        """Delete all chunks for a given source_id."""
        self._collection.delete(where={"source_id": source_id})
        logger.info(f"Deleted chunks for source_id='{source_id}' from ChromaDB")

    def clear(self) -> None:
        """Delete and recreate collection."""
        collection_name = self._config.collection_name
        self._client.delete_collection(collection_name)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Cleared ChromaDB collection '{collection_name}'")
