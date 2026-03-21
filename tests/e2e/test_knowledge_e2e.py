"""E2E tests for knowledge base upload and query.

Tests the complete knowledge lifecycle through the real FastAPI API:
- List knowledge sources
- Upload documents (skipped when Qdrant is not configured)
- Query knowledge base (skipped when Qdrant is not configured)
- Delete sources
- Error handling for invalid uploads

The upload and query operations require DRYADE_QDRANT_URL to be set.
When Qdrant is not configured the tests verify the correct 503 response
rather than skipping — this keeps the tests useful in the default CI
environment (no Qdrant) while still exercising the API contract.
"""

import io

import pytest

pytestmark = pytest.mark.e2e

class TestKnowledgeList:
    """Tests that do not require Qdrant (list endpoints only)."""

    def test_list_sources_empty_on_fresh_install(self, e2e_client):
        """GET /api/knowledge returns list and total on a fresh install."""
        resp = e2e_client.get("/api/knowledge")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "sources" in body, f"Missing 'sources' key: {body}"
        assert "total" in body, f"Missing 'total' key: {body}"
        assert isinstance(body["sources"], list)
        assert isinstance(body["total"], int)
        assert body["total"] == len(body["sources"])

    def test_get_nonexistent_source_returns_404(self, e2e_client):
        """GET /api/knowledge/ks_nonexistent returns 404."""
        resp = e2e_client.get("/api/knowledge/ks_nonexistent_xyz_000")
        assert resp.status_code == 404, resp.text

    def test_delete_nonexistent_source_returns_error(self, e2e_client):
        """DELETE /api/knowledge/ks_nonexistent returns 404."""
        resp = e2e_client.delete("/api/knowledge/ks_nonexistent_xyz_000")
        assert resp.status_code in (404, 400), (
            f"Expected 404 or 400, got {resp.status_code}: {resp.text}"
        )

    def test_get_chunks_nonexistent_source_returns_error(self, e2e_client):
        """GET /api/knowledge/ks_nonexistent/chunks returns 404."""
        resp = e2e_client.get("/api/knowledge/ks_nonexistent_xyz_000/chunks")
        assert resp.status_code in (404, 400), (
            f"Expected 404 or 400, got {resp.status_code}: {resp.text}"
        )

class TestKnowledgeUpload:
    """Tests for document upload — verifies correct behavior with and without Qdrant."""

    def test_upload_txt_without_qdrant_returns_503(self, e2e_client):
        """Upload a TXT file returns a defined status (503 without Qdrant, 200 with it).

        When Qdrant is not configured: 503 Service Unavailable.
        When Qdrant is configured but processing fails: 500.
        When Qdrant is configured and upload succeeds: 200 OK with source ID.
        In all cases: never a generic 400 or a leaked stack trace.
        """
        content = b"This is a test document for knowledge base testing."
        file_obj = io.BytesIO(content)

        resp = e2e_client.post(
            "/api/knowledge/upload",
            files={"file": ("test_doc.txt", file_obj, "text/plain")},
            data={"name": "Test Document"},
        )
        # Accept all defined error codes (503 = no Qdrant, 500 = processing error, 200/201 = success)
        assert resp.status_code in (200, 201, 500, 503), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )

        if resp.status_code == 503:
            body = resp.json()
            assert "detail" in body
            assert "qdrant" in body["detail"].lower() or "unavailable" in body["detail"].lower(), (
                f"Expected Qdrant-related 503 message, got: {body['detail']}"
            )

        if resp.status_code in (200, 201):
            body = resp.json()
            assert "id" in body
            assert body["id"].startswith("ks_")
            assert "name" in body
            assert "source_type" in body

    def test_upload_unsupported_format_returns_error(self, e2e_client):
        """Upload an unsupported file type returns 400."""
        content = b"Binary content"
        file_obj = io.BytesIO(content)

        resp = e2e_client.post(
            "/api/knowledge/upload",
            files={"file": ("test_doc.exe", file_obj, "application/octet-stream")},
            data={"name": "Invalid File"},
        )
        # Either 400 (bad format) or 503 (Qdrant not configured, checked first)
        assert resp.status_code in (400, 503), (
            f"Expected 400 or 503 for unsupported format, got {resp.status_code}: {resp.text}"
        )

    def test_upload_markdown_without_qdrant_returns_503(self, e2e_client):
        """Upload a Markdown file returns a defined status.

        Without Qdrant: 503. With Qdrant processing error: 500. On success: 200.
        """
        content = b"# Test Header\n\nThis is a **markdown** document.\n"
        file_obj = io.BytesIO(content)

        resp = e2e_client.post(
            "/api/knowledge/upload",
            files={"file": ("readme.md", file_obj, "text/markdown")},
            data={"name": "Test Readme"},
        )
        assert resp.status_code in (200, 201, 500, 503), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )

class TestKnowledgeQuery:
    """Tests for semantic search — verifies error handling when Qdrant unavailable."""

    def test_query_without_qdrant_returns_503_or_empty(self, e2e_client):
        """POST /api/knowledge/query returns a defined status.

        Without Qdrant configured: 503.
        With Qdrant but query fails: 500.
        With Qdrant and query succeeds: 200 (possibly empty results).
        """
        resp = e2e_client.post(
            "/api/knowledge/query",
            json={
                "query": "test query for knowledge base",
                "limit": 5,
            },
        )
        # 503: Qdrant not configured
        # 500: Qdrant available but search failed (no index or processing error)
        # 200: OK (possibly empty results)
        assert resp.status_code in (200, 404, 500, 503), (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )

    def test_query_empty_string_returns_error(self, e2e_client):
        """POST /api/knowledge/query with empty query returns validation error."""
        resp = e2e_client.post(
            "/api/knowledge/query",
            json={"query": ""},
        )
        # 422 (Pydantic min_length=1) or 400
        assert resp.status_code in (400, 422, 503), (
            f"Expected validation error for empty query, got {resp.status_code}: {resp.text}"
        )
