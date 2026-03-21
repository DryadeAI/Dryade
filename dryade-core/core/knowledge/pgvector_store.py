"""Pgvector Storage Backend for Knowledge/RAG Pipeline.

Uses PostgreSQL with the pgvector extension for dense vector search.
Reuses the existing PostgreSQL database -- no additional infrastructure needed.
"""

from __future__ import annotations

import json
import logging
import uuid

from core.knowledge.config import KnowledgeConfig
from core.knowledge.vector_store import VectorStoreBackend

logger = logging.getLogger(__name__)

class PgvectorStore(VectorStoreBackend):
    """PostgreSQL/pgvector vector store backend.

    Dense-only search (pgvector does not support sparse vectors natively).
    hybrid_search falls back to dense_only_search with a debug log.

    Uses psycopg2 for synchronous database access, matching the
    synchronous pattern of the Qdrant client.
    """

    def __init__(self, connection_string: str, config: KnowledgeConfig):
        import psycopg2

        self._connection_string = connection_string
        self._table_name = config.collection_name.replace("-", "_")
        self._dim = config.dense_dim
        self._conn = psycopg2.connect(connection_string)
        self._conn.autocommit = True
        self._ensure_table()

    def _get_connection(self):
        """Get database connection, reconnecting if closed."""
        import psycopg2

        if self._conn.closed:
            self._conn = psycopg2.connect(self._connection_string)
            self._conn.autocommit = True
        return self._conn

    def _ensure_table(self):
        """Create pgvector extension and table if they do not exist."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""CREATE TABLE IF NOT EXISTS {self._table_name} (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    embedding vector({self._dim})
                );"""
            )
            cur.execute(
                f"""CREATE INDEX IF NOT EXISTS idx_{self._table_name}_embedding
                    ON {self._table_name}
                    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"""
            )
            logger.info(f"Ensured pgvector table '{self._table_name}' exists (dim={self._dim})")
        finally:
            cur.close()

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

        conn = self._get_connection()
        cur = conn.cursor()
        try:
            values = []
            for chunk, meta, dense in zip(chunks, metadata, dense_vectors):
                point_id = str(uuid.uuid4())
                meta_json = json.dumps({**meta, "content": chunk})
                embedding_str = "[" + ",".join(str(v) for v in dense) + "]"
                values.append(
                    cur.mogrify(
                        "(%s, %s, %s::jsonb, %s::vector)",
                        (point_id, chunk, meta_json, embedding_str),
                    )
                )

            query = (
                f"INSERT INTO {self._table_name} (id, content, metadata, embedding) VALUES "
                + b",".join(values).decode()
            )
            cur.execute(query)
            logger.info(f"Added {len(chunks)} chunks to pgvector table '{self._table_name}'")
        finally:
            cur.close()

    def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse,
        limit: int = 10,
        score_threshold: float = 0.0,
        metadata_filter: dict | None = None,
    ) -> list[dict]:
        """Hybrid search falls back to dense-only (pgvector has no sparse support)."""
        logger.debug("Pgvector does not support sparse search; using dense-only")
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
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            embedding_str = "[" + ",".join(str(v) for v in query_dense) + "]"

            where_clauses = []
            params: list = [embedding_str, embedding_str]

            if metadata_filter:
                for key, value in metadata_filter.items():
                    if isinstance(value, dict) and "$in" in value:
                        in_values = value["$in"]
                        if in_values:
                            placeholders = ",".join(["%s"] * len(in_values))
                            where_clauses.append(f"metadata->>'{key}' IN ({placeholders})")
                            params.extend(str(v) for v in in_values)
                    else:
                        where_clauses.append(f"metadata->>'{key}' = %s")
                        params.append(str(value))

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            params.append(limit)

            query = f"""
                SELECT content, metadata,
                       1 - (embedding <=> %s::vector) as score
                FROM {self._table_name}
                {where_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """

            cur.execute(query, params)
            rows = cur.fetchall()

            results = []
            for content, meta, score in rows:
                if score >= score_threshold:
                    meta_dict = meta if isinstance(meta, dict) else json.loads(meta)
                    meta_dict.pop("content", None)
                    results.append(
                        {"content": content, "score": float(score), "metadata": meta_dict}
                    )

            return results
        finally:
            cur.close()

    def delete(self, source_id: str) -> None:
        """Delete all chunks for a given source_id."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                f"DELETE FROM {self._table_name} WHERE metadata->>'source_id' = %s",
                (source_id,),
            )
            logger.info(f"Deleted chunks for source_id='{source_id}' from pgvector")
        finally:
            cur.close()

    def clear(self) -> None:
        """Drop and recreate the table."""
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(f"DROP TABLE IF EXISTS {self._table_name};")
            logger.info(f"Dropped pgvector table '{self._table_name}'")
        finally:
            cur.close()
        self._ensure_table()
