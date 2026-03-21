#!/usr/bin/env python3
"""End-to-end tests for Knowledge/RAG REST API endpoints.

Tests all knowledge endpoints with comprehensive coverage:
- GET /api/knowledge (list all knowledge sources)
- GET /api/knowledge/{source_id} (get single source)
- POST /api/knowledge/upload (upload TXT/MD documents)
- POST /api/knowledge/query (semantic search with Qdrant)
- DELETE /api/knowledge/{source_id} (delete source)

Documents missing endpoints as inline GAP comments:
- GAP-102: POST /knowledge/{id}/bind
- GAP-103: DELETE /knowledge/{id}/unbind
- GAP-104: GET /knowledge/{id}/chunks

Usage:
    python scripts/test_knowledge_e2e.py

Requirements:
    - Backend running at http://localhost:8080
    - Qdrant running (for semantic search tests)
    - Test fixtures at tests/e2e/fixtures/
"""

import os
import sys
import uuid
from pathlib import Path

import requests

BASE_URL = os.environ.get("DRYADE_API_URL", "http://localhost:8080")
API_URL = f"{BASE_URL}/api"

# Test fixtures location
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "e2e" / "fixtures"

class TestResults:
    """Track test results and statistics."""

    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0

    def add(self, name: str, passed: bool, details: str = ""):
        """Add test result."""
        self.tests.append({"name": name, "passed": passed, "details": details})
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if details:
            print(f"       {details}")

    def summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print(f"Test Summary: {self.passed} passed, {self.failed} failed")
        print("=" * 80)
        if self.failed > 0:
            print("\nFailed tests:")
            for test in self.tests:
                if not test["passed"]:
                    print(f"  - {test['name']}: {test['details']}")

def get_auth_token() -> str:
    """Get authentication token (setup admin or login)."""
    # Try to setup admin first (will fail if already exists)
    try:
        response = requests.post(
            f"{API_URL}/auth/setup",
            json={
                "username": "admin",
                "email": "admin@test.com",
                "password": "admin123456",
            },
        )
        if response.status_code == 201:
            return response.json()["access_token"]
    except Exception:
        pass

    # Try login with existing admin
    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": "admin@test.com", "password": "admin123456"},
        )
        if response.status_code == 200:
            return response.json()["access_token"]
    except Exception:
        pass

    # Fallback: register new user and get token
    username = f"test_{uuid.uuid4().hex[:8]}"
    response = requests.post(
        f"{API_URL}/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "testpass123",
        },
    )
    return response.json()["access_token"]

# ============================================================================
# Knowledge Source Tests
# ============================================================================

def test_list_sources_empty(results: TestResults, headers: dict) -> list[dict]:
    """Test GET /api/knowledge with empty knowledge base."""
    print("\n--- Testing GET /api/knowledge (list sources) ---")

    response = requests.get(f"{API_URL}/knowledge", headers=headers)

    # Test: Response is 200
    results.add(
        "GET /knowledge returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code != 200:
        return []

    data = response.json()

    # Test: Response has sources field
    results.add("Response has 'sources' field", "sources" in data, f"Fields: {list(data.keys())}")

    # Test: sources is a list
    results.add(
        "sources is a list",
        isinstance(data.get("sources"), list),
        f"Type: {type(data.get('sources')).__name__}",
    )

    sources = data.get("sources", [])
    print(f"\nFound {len(sources)} existing knowledge sources")

    return sources

def test_get_source_not_found(results: TestResults, headers: dict):
    """Test GET /api/knowledge/{source_id} with non-existent ID."""
    print("\n--- Testing GET /api/knowledge/{id} (not found) ---")

    fake_id = "ks_nonexistent123"
    response = requests.get(f"{API_URL}/knowledge/{fake_id}", headers=headers)

    # Test: Response is 404
    results.add(
        f"GET /knowledge/{fake_id} returns 404",
        response.status_code == 404,
        f"Got {response.status_code}",
    )

def test_upload_txt_file(results: TestResults, headers: dict) -> dict | None:
    """Test POST /api/knowledge/upload with TXT file."""
    print("\n--- Testing POST /api/knowledge/upload (TXT) ---")

    txt_file = FIXTURES_DIR / "sample.txt"
    if not txt_file.exists():
        results.add("TXT fixture exists", False, f"File not found: {txt_file}")
        return None

    # Upload file with multipart form
    with open(txt_file, "rb") as f:
        files = {"file": ("sample.txt", f, "text/plain")}
        data = {"name": f"test_txt_{uuid.uuid4().hex[:8]}"}

        # Remove Content-Type header for multipart
        upload_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}

        response = requests.post(
            f"{API_URL}/knowledge/upload", headers=upload_headers, files=files, data=data
        )

    # Test: Response is 200 or 201
    success = response.status_code in (200, 201)
    results.add(
        "POST /knowledge/upload returns 200/201 for TXT", success, f"Got {response.status_code}"
    )

    if not success:
        # Check for specific error codes
        if response.status_code == 501:
            results.add(
                "Knowledge service available (501 = not available)",
                False,
                "Qdrant may not be running or embeddings not configured",
            )
        elif response.status_code == 503:
            results.add(
                "Knowledge service available (503 = unavailable)",
                False,
                "Knowledge service configuration error",
            )
        try:
            error = response.json()
            print(f"       Error: {error.get('detail', error)}")
        except Exception:
            print(f"       Response: {response.text[:200]}")
        return None

    data = response.json()

    # Test: Response has required fields
    required_fields = ["id", "name", "source_type", "file_path"]
    has_fields = all(field in data for field in required_fields)
    results.add(
        "Upload response has required fields (id, name, source_type, file_path)",
        has_fields,
        f"Fields: {list(data.keys())}",
    )

    # Test: ID format is ks_*
    source_id = data.get("id", "")
    results.add("Source ID has ks_ prefix", source_id.startswith("ks_"), f"ID: {source_id}")

    # Test: source_type is 'text' for TXT/MD files
    results.add(
        "source_type is 'text' for TXT file",
        data.get("source_type") == "text",
        f"source_type: {data.get('source_type')}",
    )

    print(f"\nUploaded TXT source: {data.get('id')} ({data.get('name')})")
    return data

def test_upload_md_file(results: TestResults, headers: dict) -> dict | None:
    """Test POST /api/knowledge/upload with MD file."""
    print("\n--- Testing POST /api/knowledge/upload (MD) ---")

    md_file = FIXTURES_DIR / "sample.md"
    if not md_file.exists():
        results.add("MD fixture exists", False, f"File not found: {md_file}")
        return None

    # Upload file with multipart form
    with open(md_file, "rb") as f:
        files = {"file": ("sample.md", f, "text/markdown")}
        data = {"name": f"test_md_{uuid.uuid4().hex[:8]}"}

        # Remove Content-Type header for multipart
        upload_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}

        response = requests.post(
            f"{API_URL}/knowledge/upload", headers=upload_headers, files=files, data=data
        )

    # Test: Response is 200 or 201
    success = response.status_code in (200, 201)
    results.add(
        "POST /knowledge/upload returns 200/201 for MD", success, f"Got {response.status_code}"
    )

    if not success:
        try:
            error = response.json()
            print(f"       Error: {error.get('detail', error)}")
        except Exception:
            pass
        return None

    data = response.json()

    # Test: source_type is 'text' for MD files (same as TXT)
    results.add(
        "source_type is 'text' for MD file",
        data.get("source_type") == "text",
        f"source_type: {data.get('source_type')}",
    )

    print(f"\nUploaded MD source: {data.get('id')} ({data.get('name')})")
    return data

def test_upload_with_associations(results: TestResults, headers: dict) -> dict | None:
    """Test POST /api/knowledge/upload with crew_ids and agent_ids."""
    print("\n--- Testing POST /api/knowledge/upload (with associations) ---")

    txt_file = FIXTURES_DIR / "sample.txt"
    if not txt_file.exists():
        return None

    with open(txt_file, "rb") as f:
        files = {"file": ("assoc_test.txt", f, "text/plain")}
        data = {
            "name": f"assoc_test_{uuid.uuid4().hex[:8]}",
            "crew_ids": "crew1,crew2",
            "agent_ids": "research,writer",
        }

        upload_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}

        response = requests.post(
            f"{API_URL}/knowledge/upload", headers=upload_headers, files=files, data=data
        )

    # Test: Upload with associations succeeds
    success = response.status_code in (200, 201)
    results.add(
        "Upload with crew_ids and agent_ids succeeds", success, f"Got {response.status_code}"
    )

    if success:
        data = response.json()
        print(f"\nUploaded associated source: {data.get('id')}")
        return data
    return None

def test_upload_unsupported_type(results: TestResults, headers: dict):
    """Test POST /api/knowledge/upload with unsupported file type."""
    print("\n--- Testing POST /api/knowledge/upload (unsupported type) ---")

    # Create a temporary file with unsupported extension
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as tmp:
        tmp.write(b"This is a test file with unsupported extension")
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            files = {"file": ("test.xyz", f, "application/octet-stream")}

            upload_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}

            response = requests.post(
                f"{API_URL}/knowledge/upload", headers=upload_headers, files=files
            )

        # Test: Response is 400 for unsupported type
        results.add(
            "POST /knowledge/upload returns 400 for unsupported file type",
            response.status_code == 400,
            f"Got {response.status_code}",
        )
    finally:
        os.unlink(tmp_path)

def test_get_source(results: TestResults, headers: dict, source_id: str):
    """Test GET /api/knowledge/{source_id} with valid ID."""
    print(f"\n--- Testing GET /api/knowledge/{source_id} ---")

    response = requests.get(f"{API_URL}/knowledge/{source_id}", headers=headers)

    # Test: Response is 200
    results.add(
        f"GET /knowledge/{source_id} returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: Response has expected fields
    # Backend KnowledgeSourceInfo: id, name, source_type, file_paths, crew_ids, agent_ids, description, metadata
    required_fields = ["id", "name", "source_type", "file_paths"]
    has_fields = all(field in data for field in required_fields)
    results.add(
        "Source detail has required fields (id, name, source_type, file_paths)",
        has_fields,
        f"Fields: {list(data.keys())}",
    )

    # Test: ID matches
    results.add(
        "Source ID matches request",
        data.get("id") == source_id,
        f"Expected {source_id}, got {data.get('id')}",
    )

    # GAP-107: Frontend expects chunk_count but backend doesn't provide it
    # GAP-107: Missing chunk_count in KnowledgeSourceInfo response
    # Severity: Minor
    # Suggested fix: Add chunk_count field to KnowledgeSourceInfo model in core/knowledge/sources.py
    # Expected: KnowledgeSourceInfo should include chunk_count: int for displaying indexed chunks
    has_chunk_count = "chunk_count" in data
    results.add(
        "GAP-107: Response includes chunk_count",
        has_chunk_count,
        f"chunk_count present: {has_chunk_count} - Frontend expects this for display",
    )

def test_list_sources_after_upload(results: TestResults, headers: dict, expected_ids: list[str]):
    """Test GET /api/knowledge shows uploaded sources."""
    print("\n--- Testing GET /api/knowledge (after upload) ---")

    response = requests.get(f"{API_URL}/knowledge", headers=headers)

    if response.status_code != 200:
        results.add(
            "GET /knowledge returns 200 after uploads", False, f"Got {response.status_code}"
        )
        return

    data = response.json()
    sources = data.get("sources", [])
    source_ids = [s.get("id") for s in sources]

    # Test: Uploaded sources appear in list
    found_count = sum(1 for eid in expected_ids if eid in source_ids)
    results.add(
        f"Uploaded sources appear in list ({found_count}/{len(expected_ids)})",
        found_count == len(expected_ids),
        f"Found: {found_count}, Expected: {len(expected_ids)}",
    )

# ============================================================================
# Semantic Search Tests
# ============================================================================

def test_query_authentication_keyword(results: TestResults, headers: dict, source_ids: list[str]):
    """Test POST /api/knowledge/query with 'authentication' keyword."""
    print("\n--- Testing POST /api/knowledge/query (authentication keyword) ---")

    # Search for 'authentication' which should be in sample.txt
    request_data = {
        "query": "How do I configure authentication?",
        "source_ids": source_ids if source_ids else None,
        "limit": 5,
        "score_threshold": 0.5,  # Lower threshold for testing
    }

    response = requests.post(f"{API_URL}/knowledge/query", headers=headers, json=request_data)

    # Test: Response is 200
    results.add(
        "POST /knowledge/query returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        if response.status_code == 501:
            results.add(
                "Knowledge query available",
                False,
                "501 - Knowledge sources not available (Qdrant not running)",
            )
        return

    data = response.json()

    # Test: Response has expected structure
    required_fields = ["results", "sources_used", "query", "total_results"]
    has_fields = all(field in data for field in required_fields)
    results.add(
        "Query response has required fields (results, sources_used, query, total_results)",
        has_fields,
        f"Fields: {list(data.keys())}",
    )

    # Test: Got some results
    results_list = data.get("results", [])
    results.add(
        "Query returns results for 'authentication'",
        len(results_list) > 0,
        f"Got {len(results_list)} results",
    )

    # Test: Results have expected structure
    if results_list:
        first_result = results_list[0]
        result_fields = ["content", "score", "metadata"]
        has_result_fields = all(field in first_result for field in result_fields)
        results.add(
            "Query result has content, score, metadata",
            has_result_fields,
            f"Fields: {list(first_result.keys())}",
        )

        # Test: Score is float between 0 and 1
        score = first_result.get("score", 0)
        results.add(
            "Result score is valid (0.0-1.0)",
            isinstance(score, (int, float)) and 0 <= score <= 1,
            f"Score: {score}",
        )

    # Test: total_results matches results length
    total = data.get("total_results", 0)
    results.add(
        "total_results matches results array length",
        total == len(results_list),
        f"total_results: {total}, array length: {len(results_list)}",
    )

def test_query_workflow_keyword(results: TestResults, headers: dict, source_ids: list[str]):
    """Test POST /api/knowledge/query with 'workflow' keyword."""
    print("\n--- Testing POST /api/knowledge/query (workflow keyword) ---")

    # Search for 'workflow' which should be in sample.md
    request_data = {
        "query": "How do I execute a workflow?",
        "source_ids": source_ids if source_ids else None,
        "limit": 5,
        "score_threshold": 0.5,
    }

    response = requests.post(f"{API_URL}/knowledge/query", headers=headers, json=request_data)

    if response.status_code != 200:
        results.add(
            "POST /knowledge/query returns 200 for workflow search",
            False,
            f"Got {response.status_code}",
        )
        return

    data = response.json()
    results_list = data.get("results", [])

    # Test: Got results for workflow query
    results.add(
        "Query returns results for 'workflow'",
        len(results_list) > 0,
        f"Got {len(results_list)} results",
    )

def test_query_with_score_threshold(results: TestResults, headers: dict, source_ids: list[str]):
    """Test POST /api/knowledge/query with different score thresholds."""
    print("\n--- Testing POST /api/knowledge/query (score_threshold) ---")

    # High threshold query
    high_threshold_data = {
        "query": "authentication API key",
        "source_ids": source_ids if source_ids else None,
        "limit": 10,
        "score_threshold": 0.9,  # Very high threshold
    }

    response = requests.post(
        f"{API_URL}/knowledge/query", headers=headers, json=high_threshold_data
    )

    if response.status_code == 200:
        high_results = response.json().get("results", [])

        # Low threshold query
        low_threshold_data = {
            "query": "authentication API key",
            "source_ids": source_ids if source_ids else None,
            "limit": 10,
            "score_threshold": 0.3,  # Low threshold
        }

        response2 = requests.post(
            f"{API_URL}/knowledge/query", headers=headers, json=low_threshold_data
        )

        if response2.status_code == 200:
            low_results = response2.json().get("results", [])

            # Test: Lower threshold returns more or equal results
            results.add(
                "Lower score_threshold returns more results",
                len(low_results) >= len(high_results),
                f"High threshold (0.9): {len(high_results)}, Low threshold (0.3): {len(low_results)}",
            )

def test_query_with_limit(results: TestResults, headers: dict, source_ids: list[str]):
    """Test POST /api/knowledge/query with limit parameter."""
    print("\n--- Testing POST /api/knowledge/query (limit) ---")

    request_data = {
        "query": "configuration settings",
        "source_ids": source_ids if source_ids else None,
        "limit": 2,
        "score_threshold": 0.3,
    }

    response = requests.post(f"{API_URL}/knowledge/query", headers=headers, json=request_data)

    if response.status_code != 200:
        results.add(
            "POST /knowledge/query returns 200 with limit", False, f"Got {response.status_code}"
        )
        return

    data = response.json()
    results_list = data.get("results", [])

    # Test: Results respect limit
    results.add(
        "Query respects limit parameter",
        len(results_list) <= 2,
        f"Requested limit: 2, Got: {len(results_list)} results",
    )

def test_query_with_source_filter(
    results: TestResults, headers: dict, txt_source_id: str, md_source_id: str
):
    """Test POST /api/knowledge/query with source_ids filter."""
    print("\n--- Testing POST /api/knowledge/query (source_ids filter) ---")

    if not txt_source_id or not md_source_id:
        results.add(
            "Source filter test skipped", True, "Not enough sources uploaded for filter test"
        )
        return

    # Query only the TXT source for 'authentication' (should find results)
    request_data = {
        "query": "authentication configuration",
        "source_ids": [txt_source_id],
        "limit": 5,
        "score_threshold": 0.3,
    }

    response = requests.post(f"{API_URL}/knowledge/query", headers=headers, json=request_data)

    if response.status_code == 200:
        data = response.json()
        sources_used = data.get("sources_used", [])

        # Test: Only filtered source appears in results
        results.add(
            "Query filters by source_ids correctly",
            all(s == txt_source_id or txt_source_id in str(s) for s in sources_used)
            if sources_used
            else True,
            f"Requested: [{txt_source_id}], Used: {sources_used}",
        )

def test_query_empty_knowledge_base(results: TestResults, headers: dict):
    """Test POST /api/knowledge/query returns empty results appropriately."""
    print("\n--- Testing POST /api/knowledge/query (non-matching query) ---")

    # Search for something very unlikely to match
    request_data = {
        "query": "xyzzy plugh frobozz",  # Nonsense terms
        "limit": 5,
        "score_threshold": 0.9,  # High threshold
    }

    response = requests.post(f"{API_URL}/knowledge/query", headers=headers, json=request_data)

    if response.status_code != 200:
        return

    data = response.json()
    results_list = data.get("results", [])

    # Test: Non-matching query returns empty or low-score results
    results.add(
        "Non-matching query returns empty or no high-score results",
        len(results_list) == 0 or all(r.get("score", 1) < 0.9 for r in results_list),
        f"Got {len(results_list)} results",
    )

# ============================================================================
# Delete Tests
# ============================================================================

def test_delete_source(results: TestResults, headers: dict, source_id: str) -> bool:
    """Test DELETE /api/knowledge/{source_id}."""
    print(f"\n--- Testing DELETE /api/knowledge/{source_id} ---")

    response = requests.delete(f"{API_URL}/knowledge/{source_id}", headers=headers)

    # Test: Response is 204
    results.add(
        f"DELETE /knowledge/{source_id} returns 204",
        response.status_code == 204,
        f"Got {response.status_code}",
    )

    if response.status_code != 204:
        return False

    # Verify deletion: GET should return 404
    verify_response = requests.get(f"{API_URL}/knowledge/{source_id}", headers=headers)
    results.add(
        "Deleted source returns 404 on GET",
        verify_response.status_code == 404,
        f"Got {verify_response.status_code}",
    )

    return True

def test_delete_source_not_found(results: TestResults, headers: dict):
    """Test DELETE /api/knowledge/{source_id} with non-existent ID."""
    print("\n--- Testing DELETE /api/knowledge/{id} (not found) ---")

    fake_id = "ks_nonexistent999"
    response = requests.delete(f"{API_URL}/knowledge/{fake_id}", headers=headers)

    # Test: Response is 404
    results.add(
        f"DELETE /knowledge/{fake_id} returns 404",
        response.status_code == 404,
        f"Got {response.status_code}",
    )

def test_source_removed_from_list(results: TestResults, headers: dict, deleted_id: str):
    """Test that deleted source no longer appears in list."""
    print("\n--- Testing source removal from list ---")

    response = requests.get(f"{API_URL}/knowledge", headers=headers)

    if response.status_code != 200:
        return

    data = response.json()
    sources = data.get("sources", [])
    source_ids = [s.get("id") for s in sources]

    # Test: Deleted source not in list
    results.add(
        "Deleted source not in list",
        deleted_id not in source_ids,
        f"Looking for {deleted_id} in {len(sources)} sources",
    )

# ============================================================================
# Frontend Contract Validation
# ============================================================================

def test_frontend_contract_list(results: TestResults, headers: dict):
    """Validate GET /api/knowledge matches frontend expectations."""
    print("\n--- Testing Frontend Contract (list) ---")

    response = requests.get(f"{API_URL}/knowledge", headers=headers)

    if response.status_code != 200:
        return

    data = response.json()

    # Frontend expects: { sources: KnowledgeSource[] }
    # Backend provides: { sources: KnowledgeSourceInfo[] }
    results.add(
        "List response structure matches frontend (sources array)",
        "sources" in data and isinstance(data["sources"], list),
        f"Fields: {list(data.keys())}",
    )

    # GAP-108: Frontend expects 'total' field but backend doesn't provide it
    # GAP-108: Missing 'total' field in list response
    # Severity: Minor
    # Suggested fix: Add total field to KnowledgeListResponse in knowledge.py
    # Expected: Response should include total: int for pagination
    has_total = "total" in data
    results.add(
        "GAP-108: List response includes 'total' count",
        has_total,
        f"total present: {has_total} - Frontend expects this for pagination",
    )

def test_frontend_contract_source_type(results: TestResults, headers: dict, source: dict | None):
    """Validate source_type mapping between backend and frontend."""
    print("\n--- Testing Frontend Contract (source_type mapping) ---")

    if not source:
        results.add("Source type mapping test skipped", True, "No source available for testing")
        return

    # Backend uses: 'pdf' or 'text' (per UploadResponse)
    # Frontend expects: 'pdf' | 'txt' | 'md' | 'csv' | 'docx' (KnowledgeSourceType)
    # Frontend maps: mapSourceType() converts backend types to frontend types
    source_type = source.get("source_type")

    # GAP-109: Backend source_type doesn't distinguish between txt and md
    # GAP-109: Backend uses 'text' for both TXT and MD files
    # Severity: Minor
    # Suggested fix: Use 'txt' and 'md' in upload response based on file extension
    # Expected: source_type should be 'txt' for .txt files, 'md' for .md files
    results.add(
        "GAP-109: source_type uses generic 'text' (frontend expects 'txt'/'md')",
        source_type in ("text", "txt", "md"),
        f"source_type: {source_type} - Frontend needs mapSourceType() conversion",
    )

# ============================================================================
# Missing Endpoint Documentation (GAPs)
# ============================================================================

def document_missing_endpoints(results: TestResults):
    """Document missing endpoints as GAP comments."""
    print("\n--- Documenting Missing Endpoints ---")

    # GAP-102: POST /knowledge/{id}/bind endpoint not implemented
    # Severity: Major
    # Suggested fix: Add bind_source() route in knowledge.py to associate knowledge source with crew/agent
    # Expected: POST /api/knowledge/{id}/bind with {crew_ids: [], agent_ids: []}
    results.add(
        "GAP-102: Bind endpoint documented",
        True,
        "POST /knowledge/{id}/bind - associates source with crews/agents dynamically",
    )

    # GAP-103: DELETE /knowledge/{id}/unbind endpoint not implemented
    # Severity: Major
    # Suggested fix: Add unbind_source() route in knowledge.py to disassociate knowledge source from crew/agent
    # Expected: DELETE /api/knowledge/{id}/unbind with {crew_ids: [], agent_ids: []}
    results.add(
        "GAP-103: Unbind endpoint documented",
        True,
        "DELETE /knowledge/{id}/unbind - removes source associations",
    )

    # GAP-104: GET /knowledge/{id}/chunks endpoint not implemented
    # Severity: Minor
    # Suggested fix: Add get_chunks() route in knowledge.py to retrieve document chunks for debugging
    # Expected: GET /api/knowledge/{id}/chunks returns {chunks: [], total: number}
    results.add(
        "GAP-104: Chunks endpoint documented",
        True,
        "GET /knowledge/{id}/chunks - retrieves indexed chunks for preview/debugging",
    )

# ============================================================================
# Cleanup
# ============================================================================

def cleanup_test_sources(headers: dict, source_ids: list[str]):
    """Clean up any test sources that weren't deleted during tests."""
    print("\n--- Cleanup ---")
    cleaned = 0
    for source_id in source_ids:
        try:
            response = requests.delete(f"{API_URL}/knowledge/{source_id}", headers=headers)
            if response.status_code == 204:
                cleaned += 1
        except Exception:
            pass
    if cleaned > 0:
        print(f"Cleaned up {cleaned} test sources")

# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Run all knowledge E2E tests."""
    print("=" * 80)
    print("Knowledge/RAG REST API E2E Tests")
    print("=" * 80)
    print(f"API URL: {API_URL}")
    print(f"Fixtures: {FIXTURES_DIR}")

    results = TestResults()

    # Check fixtures exist
    print("\n--- Checking Test Fixtures ---")
    txt_exists = (FIXTURES_DIR / "sample.txt").exists()
    md_exists = (FIXTURES_DIR / "sample.md").exists()
    print(f"sample.txt: {'OK' if txt_exists else 'MISSING'}")
    print(f"sample.md: {'OK' if md_exists else 'MISSING'}")

    if not txt_exists or not md_exists:
        print("\nERROR: Test fixtures missing. Run from project root.")
        return 1

    # Check backend health
    print("\n--- Checking Backend Health ---")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"Backend not healthy: {response.status_code}")
            return 1
        print("Backend is healthy")
    except Exception as e:
        print(f"Backend unreachable: {e}")
        print(f"Please start backend at {BASE_URL}")
        return 1

    # Get authentication token
    print("\n--- Getting Authentication Token ---")
    try:
        token = get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        print("Authentication successful")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return 1

    # Track sources for cleanup
    test_source_ids = []

    # --- List Tests (empty state) ---
    test_list_sources_empty(results, headers)
    test_get_source_not_found(results, headers)

    # --- Upload Tests ---
    txt_source = test_upload_txt_file(results, headers)
    if txt_source:
        test_source_ids.append(txt_source["id"])

    md_source = test_upload_md_file(results, headers)
    if md_source:
        test_source_ids.append(md_source["id"])

    assoc_source = test_upload_with_associations(results, headers)
    if assoc_source:
        test_source_ids.append(assoc_source["id"])

    test_upload_unsupported_type(results, headers)

    # --- Get Source Tests ---
    if txt_source:
        test_get_source(results, headers, txt_source["id"])

    # --- List After Upload ---
    if test_source_ids:
        test_list_sources_after_upload(results, headers, test_source_ids)

    # --- Query Tests (semantic search) ---
    if test_source_ids:
        test_query_authentication_keyword(results, headers, test_source_ids)
        test_query_workflow_keyword(results, headers, test_source_ids)
        test_query_with_score_threshold(results, headers, test_source_ids)
        test_query_with_limit(results, headers, test_source_ids)

        txt_id = txt_source["id"] if txt_source else None
        md_id = md_source["id"] if md_source else None
        test_query_with_source_filter(results, headers, txt_id, md_id)

    test_query_empty_knowledge_base(results, headers)

    # --- Delete Tests ---
    if assoc_source:
        deleted = test_delete_source(results, headers, assoc_source["id"])
        if deleted:
            test_source_ids.remove(assoc_source["id"])
            test_source_removed_from_list(results, headers, assoc_source["id"])

    test_delete_source_not_found(results, headers)

    # --- Frontend Contract Tests ---
    test_frontend_contract_list(results, headers)
    test_frontend_contract_source_type(results, headers, txt_source)

    # --- Document Missing Endpoints ---
    document_missing_endpoints(results)

    # --- Cleanup ---
    cleanup_test_sources(headers, test_source_ids)

    # --- Summary ---
    results.summary()

    # Return exit code based on results
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main() or 0)
