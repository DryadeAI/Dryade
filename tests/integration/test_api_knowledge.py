"""
Integration tests for knowledge API routes.

Tests cover:
1. List knowledge sources (empty, with sources)
2. Get knowledge source by ID
3. Upload knowledge (PDF, text, unsupported)
4. Delete knowledge source
5. Query knowledge
6. Knowledge unavailable (501)

Target: ~150 LOC
"""

import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="module")
def knowledge_client():
    """Create test FastAPI app with mocked knowledge sources."""
    os.environ["DRYADE_AUTH_ENABLED"] = "false"
    os.environ["DRYADE_REDIS_ENABLED"] = "false"
    os.environ["DRYADE_RATE_LIMIT_ENABLED"] = "false"
    os.environ["DRYADE_ENV"] = "development"
    os.environ["DRYADE_LLM_BASE_URL"] = "http://localhost:8000/v1"
    os.environ["DRYADE_DATABASE_URL"] = os.environ.get(
        "DRYADE_TEST_DATABASE_URL",
        "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
    )

    from core.config import get_settings

    get_settings.cache_clear()

    from core.database.session import get_engine, init_db

    get_engine.cache_clear()
    init_db()

    from core.api.main import app
    from core.auth.dependencies import get_current_user

    def override_get_current_user():
        return {"sub": "test-user-knowledge", "email": "test@example.com", "role": "user"}

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()
    if os.path.exists("./test_knowledge.db"):
        os.remove("./test_knowledge.db")

@pytest.fixture
def mock_knowledge_source_info():
    """Mock knowledge source info."""
    from core.knowledge.sources import KnowledgeSourceInfo

    return KnowledgeSourceInfo(
        id="ks_abc123",
        name="test_manual",
        source_type="pdf",
        description="Test PDF document",
        file_paths=["./uploads/knowledge/abc123.pdf"],
        crew_ids=[],
        agent_ids=[],
        chunk_count=0,
        created_at=None,
    )

@pytest.mark.integration
class TestKnowledgeListEndpoint:
    """Tests for GET /api/knowledge endpoint."""

    def test_list_sources_empty(self, knowledge_client):
        """Test listing sources when none exist."""
        with patch("core.api.routes.knowledge.list_knowledge_sources", return_value=[]):
            response = knowledge_client.get("/api/knowledge")
            assert response.status_code == 200
            data = response.json()
            assert "sources" in data
            assert data["sources"] == []

    def test_list_sources_with_sources(self, knowledge_client):
        """Test listing sources returns registered sources."""
        from core.knowledge.sources import KnowledgeSourceInfo

        # Create actual KnowledgeSourceInfo instance
        mock_info = KnowledgeSourceInfo(
            id="ks_abc123",
            name="test_manual",
            source_type="pdf",
            description="Test PDF document",
            file_paths=["./uploads/knowledge/abc123.pdf"],
            crew_ids=[],
            agent_ids=[],
        )
        mock_list = [mock_info]

        with patch("core.api.routes.knowledge.list_knowledge_sources", return_value=mock_list):
            response = knowledge_client.get("/api/knowledge")
            assert response.status_code == 200
            data = response.json()
            assert "sources" in data
            assert len(data["sources"]) == 1
            assert data["sources"][0]["id"] == "ks_abc123"
            assert data["sources"][0]["name"] == "test_manual"

@pytest.mark.integration
class TestKnowledgeGetEndpoint:
    """Tests for GET /api/knowledge/{source_id} endpoint."""

    def test_get_source_not_found(self, knowledge_client):
        """Test 404 when source not found."""
        with patch("core.api.routes.knowledge.list_knowledge_sources", return_value=[]):
            response = knowledge_client.get("/api/knowledge/ks_nonexistent")
            assert response.status_code == 404

    def test_get_source_by_id(self, knowledge_client, mock_knowledge_source_info):
        """Test getting source details."""
        with patch(
            "core.api.routes.knowledge.list_knowledge_sources",
            return_value=[mock_knowledge_source_info],
        ):
            response = knowledge_client.get("/api/knowledge/ks_abc123")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "ks_abc123"
            assert data["name"] == "test_manual"

@pytest.mark.integration
class TestKnowledgeUploadEndpoint:
    """Tests for POST /api/knowledge/upload endpoint."""

    def test_upload_knowledge_unavailable(self, knowledge_client):
        """Test 503 when qdrant not configured."""
        with patch("core.api.routes.knowledge.get_settings") as mock_settings:
            mock_settings.return_value.qdrant_url = None
            files = {"file": ("test.pdf", BytesIO(b"%PDF-1.4 test content"), "application/pdf")}
            response = knowledge_client.post("/api/knowledge/upload", files=files)
            assert response.status_code == 503

    def test_upload_unsupported_format(self, knowledge_client):
        """Test 400 for unsupported file format."""
        with patch("core.api.routes.knowledge.get_settings") as mock_settings:
            mock_settings.return_value.qdrant_url = "http://localhost:6333"

            # Mock the ingest pipeline import to avoid actual qdrant dependency
            mock_pipeline = MagicMock()
            with patch("core.knowledge.pipeline.get_ingest_pipeline", return_value=mock_pipeline):
                files = {"file": ("test.jpg", BytesIO(b"image data"), "image/jpeg")}
                response = knowledge_client.post("/api/knowledge/upload", files=files)
                # Should fail with 400 because .jpg is not supported
                assert response.status_code == 400

@pytest.mark.integration
class TestKnowledgeDeleteEndpoint:
    """Tests for DELETE /api/knowledge/{source_id} endpoint."""

    def test_delete_source_unavailable(self, knowledge_client):
        """Test 404 when source not found (qdrant not needed for delete lookup)."""
        with patch("core.api.routes.knowledge.get_knowledge_source_info", return_value=None):
            response = knowledge_client.delete("/api/knowledge/ks_test")
            assert response.status_code == 404

    def test_delete_source_not_found_explicit(self, knowledge_client):
        """Test 404 when source not found with explicit ID."""
        with patch("core.api.routes.knowledge.get_knowledge_source_info", return_value=None):
            response = knowledge_client.delete("/api/knowledge/ks_nonexistent")
            assert response.status_code == 404

@pytest.mark.integration
class TestKnowledgeQueryEndpoint:
    """Tests for POST /api/knowledge/query endpoint."""

    def test_query_knowledge_unavailable(self, knowledge_client):
        """Test 503 when qdrant not configured."""
        with patch("core.api.routes.knowledge.get_settings") as mock_settings:
            mock_settings.return_value.qdrant_url = None
            query_data = {"query": "How do I configure auth?"}
            response = knowledge_client.post("/api/knowledge/query", json=query_data)
            assert response.status_code == 503

    def test_query_knowledge_success(self, knowledge_client):
        """Test successful knowledge query returns results."""
        mock_search_results = [
            {
                "content": "To configure auth, set API_KEY...",
                "score": 0.92,
                "rerank_score": 0.95,
                "metadata": {"source_id": "ks_abc123"},
            }
        ]

        mock_embedding_service = MagicMock()
        mock_embedding_service.embed_dense_single.return_value = [0.1] * 128
        mock_embedding_service.embed_sparse_single.return_value = {"indices": [1], "values": [0.5]}
        mock_embedding_service.rerank.return_value = mock_search_results

        mock_store = MagicMock()
        mock_store.hybrid_search.return_value = mock_search_results

        with (
            patch("core.api.routes.knowledge.get_settings") as mock_settings,
            patch(
                "core.knowledge.embedder.get_embedding_service", return_value=mock_embedding_service
            ),
            patch("core.knowledge.storage.HybridVectorStore", return_value=mock_store),
            patch("qdrant_client.QdrantClient"),
        ):
            mock_settings.return_value.qdrant_url = "http://localhost:6333"

            query_data = {"query": "How do I configure auth?", "limit": 5}
            response = knowledge_client.post("/api/knowledge/query", json=query_data)
            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert "query" in data
            assert data["query"] == "How do I configure auth?"

    def test_query_knowledge_validation_error(self, knowledge_client):
        """Test validation error for empty query."""
        query_data = {"query": ""}  # Empty query should fail validation
        response = knowledge_client.post("/api/knowledge/query", json=query_data)
        assert response.status_code == 422

    def test_query_knowledge_with_source_filter(self, knowledge_client):
        """Test query with source_ids filter returns empty when no matches."""
        mock_embedding_service = MagicMock()
        mock_embedding_service.embed_dense_single.return_value = [0.1] * 128
        mock_embedding_service.embed_sparse_single.return_value = {"indices": [1], "values": [0.5]}

        mock_store = MagicMock()
        mock_store.hybrid_search.return_value = []

        with (
            patch("core.api.routes.knowledge.get_settings") as mock_settings,
            patch(
                "core.knowledge.embedder.get_embedding_service", return_value=mock_embedding_service
            ),
            patch("core.knowledge.storage.HybridVectorStore", return_value=mock_store),
            patch("qdrant_client.QdrantClient"),
        ):
            mock_settings.return_value.qdrant_url = "http://localhost:6333"

            query_data = {
                "query": "test query",
                "source_ids": ["ks_specific"],
                "limit": 10,
                "score_threshold": 0.8,
            }
            response = knowledge_client.post("/api/knowledge/query", json=query_data)
            assert response.status_code == 200
            data = response.json()
            assert data["total_results"] == 0
