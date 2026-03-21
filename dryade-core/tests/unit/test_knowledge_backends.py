"""Unit tests for PgvectorStore and ChromaStore backends.

All external dependencies (psycopg2, chromadb) are mocked -- no services needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.knowledge.config import KnowledgeConfig
from core.knowledge.vector_store import VectorStoreBackend

# =============================================================================
# PgvectorStore tests
# =============================================================================

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed")

class TestPgvectorStore:
    """Tests for PgvectorStore with mocked psycopg2."""

    @pytest.fixture
    def config(self):
        return KnowledgeConfig(collection_name="test_knowledge", dense_dim=384)

    @patch("psycopg2.connect")
    def test_is_subclass_of_backend(self, mock_connect, config):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from core.knowledge.pgvector_store import PgvectorStore

        assert issubclass(PgvectorStore, VectorStoreBackend)

    @patch("psycopg2.connect")
    def test_ensure_table_creates_extension_and_table(self, mock_connect, config):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from core.knowledge.pgvector_store import PgvectorStore

        PgvectorStore(connection_string="postgresql://test", config=config)

        # Verify CREATE EXTENSION and CREATE TABLE were called
        calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("CREATE EXTENSION" in c for c in calls)
        assert any("CREATE TABLE" in c for c in calls)

    @patch("psycopg2.connect")
    def test_add_inserts_rows(self, mock_connect, config):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.mogrify.side_effect = lambda fmt, args: (
            f"('{args[0]}','{args[1]}','{args[2]}','{args[3]}')".encode()
        )

        from core.knowledge.pgvector_store import PgvectorStore

        store = PgvectorStore(connection_string="postgresql://test", config=config)
        store.add(
            chunks=["chunk1", "chunk2"],
            metadata=[{"key": "val1"}, {"key": "val2"}],
            dense_vectors=[[0.1] * 384, [0.2] * 384],
            sparse_vectors=[None, None],
        )

        # Verify INSERT was called (after the CREATE TABLE calls)
        insert_calls = [c for c in mock_cursor.execute.call_args_list if "INSERT" in str(c)]
        assert len(insert_calls) >= 1

    @patch("psycopg2.connect")
    def test_dense_only_search_returns_results(self, mock_connect, config):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("test content", {"source_id": "src1"}, 0.95),
        ]

        from core.knowledge.pgvector_store import PgvectorStore

        store = PgvectorStore(connection_string="postgresql://test", config=config)
        results = store.dense_only_search(query_dense=[0.1] * 384, limit=5, score_threshold=0.0)

        assert len(results) == 1
        assert results[0]["content"] == "test content"
        assert results[0]["score"] == 0.95
        assert "metadata" in results[0]

    @patch("psycopg2.connect")
    def test_delete_by_source_id(self, mock_connect, config):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.closed = False
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        from core.knowledge.pgvector_store import PgvectorStore

        store = PgvectorStore(connection_string="postgresql://test", config=config)
        store.delete("src1")

        delete_calls = [c for c in mock_cursor.execute.call_args_list if "DELETE" in str(c)]
        assert len(delete_calls) >= 1
        assert "source_id" in str(delete_calls[0])

# =============================================================================
# ChromaStore tests
# =============================================================================

class TestChromaStore:
    """Tests for ChromaStore with mocked chromadb."""

    @pytest.fixture
    def config(self):
        return KnowledgeConfig(collection_name="test_knowledge", dense_dim=384)

    @patch("chromadb.PersistentClient")
    def test_is_subclass_of_backend(self, mock_client_cls, config):
        from core.knowledge.chroma_store import ChromaStore

        assert issubclass(ChromaStore, VectorStoreBackend)

    @patch("chromadb.PersistentClient")
    def test_creates_collection_with_cosine(self, mock_client_cls, config):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        from core.knowledge.chroma_store import ChromaStore

        ChromaStore(persist_directory="/tmp/chroma", config=config)

        mock_client.get_or_create_collection.assert_called_once_with(
            name="test_knowledge",
            metadata={"hnsw:space": "cosine"},
        )

    @patch("chromadb.PersistentClient")
    def test_add_calls_collection_add(self, mock_client_cls, config):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        from core.knowledge.chroma_store import ChromaStore

        store = ChromaStore(persist_directory="/tmp/chroma", config=config)
        store.add(
            chunks=["chunk1", "chunk2"],
            metadata=[{"key": "val1"}, {"key": "val2"}],
            dense_vectors=[[0.1] * 384, [0.2] * 384],
            sparse_vectors=[None, None],
        )

        mock_collection.add.assert_called_once()
        call_kwargs = mock_collection.add.call_args
        assert len(call_kwargs.kwargs.get("documents", call_kwargs[1].get("documents", []))) == 2

    @patch("chromadb.PersistentClient")
    def test_dense_only_search_returns_formatted(self, mock_client_cls, config):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "distances": [[0.1, 0.3]],
            "metadatas": [
                [{"source_id": "s1", "content": "doc1"}, {"source_id": "s2", "content": "doc2"}]
            ],
        }

        from core.knowledge.chroma_store import ChromaStore

        store = ChromaStore(persist_directory="/tmp/chroma", config=config)
        results = store.dense_only_search(query_dense=[0.1] * 384, limit=5, score_threshold=0.0)

        assert len(results) == 2
        assert results[0]["content"] == "doc1"
        assert results[0]["score"] == pytest.approx(0.9, abs=0.01)
        assert "content" not in results[0]["metadata"]

    @patch("chromadb.PersistentClient")
    def test_delete_by_source_id(self, mock_client_cls, config):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_collection = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        from core.knowledge.chroma_store import ChromaStore

        store = ChromaStore(persist_directory="/tmp/chroma", config=config)
        store.delete("src1")

        mock_collection.delete.assert_called_once_with(where={"source_id": "src1"})
