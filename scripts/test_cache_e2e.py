#!/usr/bin/env python3
"""End-to-end tests for Cache REST API endpoints.

Tests all cache endpoints with comprehensive coverage:
- GET /api/cache/stats (cache statistics)
- POST /api/cache/tune (dynamic configuration)
- DELETE /api/cache/clear (clear all entries)
- POST /api/cache/evict (evict oldest entries)
- GET /api/cache/health (health check)

Usage:
    python scripts/test_cache_e2e.py

Requirements:
    - Backend running at http://localhost:8000
    - Redis running at localhost:6379 (optional but recommended)
    - Qdrant running at localhost:6333 (optional but recommended)
    - Valid auth credentials
"""

import uuid

import requests

BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"

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

def check_dependencies():
    """Check if Redis and Qdrant are available."""
    redis_ok = False
    qdrant_ok = False

    # Redis check
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        print("[OK] Redis available")
        redis_ok = True
    except Exception as e:
        print(f"[WARN] Redis unavailable: {e}")

    # Qdrant check
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host="localhost", port=6333, timeout=2)
        client.get_collections()
        print("[OK] Qdrant available")
        qdrant_ok = True
    except Exception as e:
        print(f"[WARN] Qdrant unavailable: {e}")

    return redis_ok, qdrant_ok

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

def test_get_cache_stats(results: TestResults, headers: dict) -> dict | None:
    """Test GET /api/cache/stats endpoint."""
    print("\n--- Testing GET /api/cache/stats ---")

    response = requests.get(f"{API_URL}/cache/stats", headers=headers)

    # Test: Response is 200
    results.add(
        "GET /cache/stats returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code != 200:
        return None

    data = response.json()

    # Test: Required stat fields present
    required_fields = [
        "total_queries",
        "exact_hits",
        "semantic_hits",
        "fallback_hits",
        "misses",
        "hit_rate",
    ]
    missing = [f for f in required_fields if f not in data]
    results.add(
        "Stats response has required count fields",
        len(missing) == 0,
        f"Missing: {missing}" if missing else f"All present: {required_fields}",
    )

    # Test: Performance metrics present
    perf_fields = ["avg_lookup_time_ms", "avg_embedding_time_ms", "memory_cache_size"]
    missing_perf = [f for f in perf_fields if f not in data]
    results.add(
        "Stats response has performance metrics",
        len(missing_perf) == 0,
        f"Missing: {missing_perf}" if missing_perf else "All present",
    )

    # Test: hit_rate is float 0.0-1.0
    hit_rate = data.get("hit_rate")
    results.add(
        "hit_rate is float between 0.0 and 1.0",
        isinstance(hit_rate, (int, float)) and 0.0 <= hit_rate <= 1.0,
        f"hit_rate: {hit_rate} (type: {type(hit_rate).__name__})",
    )

    # Test: services dict present with redis and qdrant keys
    services = data.get("services")
    results.add(
        "services dict has redis and qdrant keys",
        isinstance(services, dict) and "redis" in services and "qdrant" in services,
        f"services: {services}",
    )

    # Test: config dict present with enabled and similarity_threshold
    config = data.get("config")
    results.add(
        "config dict has enabled and similarity_threshold",
        isinstance(config, dict) and "enabled" in config and "similarity_threshold" in config,
        f"config: {config}",
    )

    # Test: timestamp is ISO 8601
    timestamp = data.get("timestamp")
    results.add(
        "timestamp is ISO 8601 format",
        isinstance(timestamp, str) and "T" in timestamp,
        f"timestamp: {timestamp}",
    )

    # Test: streaming stats present (backend extension)
    streaming_fields = ["streaming_hits", "streaming_misses", "streaming_hit_rate"]
    missing_streaming = [f for f in streaming_fields if f not in data]
    results.add(
        "Streaming stats present (backend extension)",
        len(missing_streaming) == 0,
        f"Missing: {missing_streaming}" if missing_streaming else "All present",
    )

    # Test: cache_size info present
    cache_size = data.get("cache_size")
    results.add("cache_size info present", cache_size is not None, f"cache_size: {cache_size}")

    if cache_size:
        # Verify cache_size structure
        size_fields = [
            "qdrant_vectors",
            "redis_keys",
            "memory_entries",
            "max_entries",
            "utilization_pct",
        ]
        missing_size = [f for f in size_fields if f not in cache_size]
        results.add(
            "cache_size has required fields",
            len(missing_size) == 0,
            f"Missing: {missing_size}" if missing_size else "All present",
        )

    total_queries = data.get("total_queries", 0)
    hit_rate_pct = data.get("hit_rate", 0)
    print(f"\nStats summary: {total_queries} queries, {hit_rate_pct:.1%} hit rate")

    return data

def test_tune_similarity_threshold(results: TestResults, headers: dict):
    """Test POST /api/cache/tune with similarity_threshold."""
    print("\n--- Testing POST /api/cache/tune (similarity_threshold) ---")

    request_data = {"similarity_threshold": 0.9}
    response = requests.post(f"{API_URL}/cache/tune", headers=headers, json=request_data)

    # Test: Response is 200
    results.add(
        "POST /cache/tune returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: Response has required fields
    required = ["message", "updates", "current_config", "note"]
    missing = [f for f in required if f not in data]
    results.add(
        "Tune response has required fields",
        len(missing) == 0,
        f"Missing: {missing}" if missing else "All present",
    )

    # Test: current_config.similarity_threshold == 0.9
    current_config = data.get("current_config", {})
    results.add(
        "similarity_threshold updated to 0.9",
        current_config.get("similarity_threshold") == 0.9,
        f"Got: {current_config.get('similarity_threshold')}",
    )

    # Test: note contains "not persisted" warning
    note = data.get("note", "")
    results.add(
        "Note contains persistence warning",
        "not persisted" in note.lower() or "persist" in note.lower(),
        f"Note: {note}",
    )

def test_tune_ttl_values(results: TestResults, headers: dict):
    """Test POST /api/cache/tune with TTL values."""
    print("\n--- Testing POST /api/cache/tune (TTL values) ---")

    request_data = {"exact_ttl_seconds": 1800, "semantic_ttl_seconds": 43200}
    response = requests.post(f"{API_URL}/cache/tune", headers=headers, json=request_data)

    # Test: Response is 200
    results.add(
        "POST /cache/tune (TTL) returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return

    data = response.json()
    current_config = data.get("current_config", {})

    # Test: Both TTL values updated
    results.add(
        "exact_ttl_seconds updated to 1800",
        current_config.get("exact_ttl_seconds") == 1800,
        f"Got: {current_config.get('exact_ttl_seconds')}",
    )

    results.add(
        "semantic_ttl_seconds updated to 43200",
        current_config.get("semantic_ttl_seconds") == 43200,
        f"Got: {current_config.get('semantic_ttl_seconds')}",
    )

def test_tune_enabled_toggle(results: TestResults, headers: dict):
    """Test POST /api/cache/tune with enabled flag toggle."""
    print("\n--- Testing POST /api/cache/tune (enabled toggle) ---")

    # Disable cache
    response = requests.post(f"{API_URL}/cache/tune", headers=headers, json={"enabled": False})

    results.add(
        "Disable cache returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code == 200:
        data = response.json()
        current_config = data.get("current_config", {})
        results.add(
            "Cache disabled (enabled=false)",
            current_config.get("enabled") is False,
            f"Got: {current_config.get('enabled')}",
        )

    # Re-enable cache
    response = requests.post(f"{API_URL}/cache/tune", headers=headers, json={"enabled": True})

    results.add(
        "Re-enable cache returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code == 200:
        data = response.json()
        current_config = data.get("current_config", {})
        results.add(
            "Cache re-enabled (enabled=true)",
            current_config.get("enabled") is True,
            f"Got: {current_config.get('enabled')}",
        )

def test_tune_invalid_threshold(results: TestResults, headers: dict):
    """Test POST /api/cache/tune with invalid similarity_threshold."""
    print("\n--- Testing POST /api/cache/tune (invalid threshold) ---")

    # Test: Value > 1.0 should be rejected
    response = requests.post(
        f"{API_URL}/cache/tune", headers=headers, json={"similarity_threshold": 1.5}
    )

    # Pydantic validation should reject this with 422, but backend also validates with 400
    results.add(
        "Invalid threshold (1.5) returns 400 or 422",
        response.status_code in [400, 422],
        f"Got {response.status_code}",
    )

    # Test: Negative value should be rejected
    response = requests.post(
        f"{API_URL}/cache/tune", headers=headers, json={"similarity_threshold": -0.5}
    )

    results.add(
        "Invalid threshold (-0.5) returns 400 or 422",
        response.status_code in [400, 422],
        f"Got {response.status_code}",
    )

def test_clear_cache(results: TestResults, headers: dict):
    """Test DELETE /api/cache/clear endpoint."""
    print("\n--- Testing DELETE /api/cache/clear ---")

    response = requests.delete(f"{API_URL}/cache/clear", headers=headers)

    # Test: Response is 200
    results.add(
        "DELETE /cache/clear returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: Response has required fields
    required = ["message", "entries_cleared", "timestamp"]
    missing = [f for f in required if f not in data]
    results.add(
        "Clear response has required fields",
        len(missing) == 0,
        f"Missing: {missing}" if missing else "All present",
    )

    # Test: entries_cleared is int >= 0
    entries_cleared = data.get("entries_cleared")
    results.add(
        "entries_cleared is non-negative int",
        isinstance(entries_cleared, int) and entries_cleared >= 0,
        f"entries_cleared: {entries_cleared}",
    )

    # Test: message confirms clear
    message = data.get("message", "")
    results.add(
        "Message confirms cache cleared",
        "clear" in message.lower() or "success" in message.lower(),
        f"Message: {message}",
    )

    # Test: timestamp is ISO 8601
    timestamp = data.get("timestamp")
    results.add(
        "Clear timestamp is ISO 8601",
        isinstance(timestamp, str) and "T" in timestamp,
        f"timestamp: {timestamp}",
    )

def test_evict_cache(results: TestResults, headers: dict):
    """Test POST /api/cache/evict endpoint."""
    print("\n--- Testing POST /api/cache/evict ---")

    # Note: Backend uses query parameter, not body
    response = requests.post(f"{API_URL}/cache/evict?count=50", headers=headers)

    # Test: Response is 200
    results.add(
        "POST /cache/evict?count=50 returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: Response has required fields
    required = ["message", "requested", "evicted", "size_before", "size_after", "timestamp"]
    missing = [f for f in required if f not in data]
    results.add(
        "Evict response has required fields",
        len(missing) == 0,
        f"Missing: {missing}" if missing else "All present",
    )

    # Test: requested == 50
    results.add("requested == 50", data.get("requested") == 50, f"Got: {data.get('requested')}")

    # Test: evicted <= requested
    evicted = data.get("evicted", 0)
    requested = data.get("requested", 0)
    results.add(
        "evicted <= requested", evicted <= requested, f"evicted: {evicted}, requested: {requested}"
    )

    # Test: size_before and size_after are dicts
    results.add(
        "size_before is dict",
        isinstance(data.get("size_before"), dict),
        f"type: {type(data.get('size_before')).__name__}",
    )

    results.add(
        "size_after is dict",
        isinstance(data.get("size_after"), dict),
        f"type: {type(data.get('size_after')).__name__}",
    )

    # Test: timestamp is ISO 8601
    timestamp = data.get("timestamp")
    results.add(
        "Evict timestamp is ISO 8601",
        isinstance(timestamp, str) and "T" in timestamp,
        f"timestamp: {timestamp}",
    )

def test_cache_health(results: TestResults, headers: dict):
    """Test GET /api/cache/health endpoint."""
    print("\n--- Testing GET /api/cache/health ---")

    response = requests.get(f"{API_URL}/cache/health", headers=headers)

    # Test: Response is 200
    results.add(
        "GET /cache/health returns 200", response.status_code == 200, f"Got {response.status_code}"
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: healthy is bool
    results.add(
        "healthy is bool",
        isinstance(data.get("healthy"), bool),
        f"healthy: {data.get('healthy')} (type: {type(data.get('healthy')).__name__})",
    )

    # Test: degraded is bool
    results.add(
        "degraded is bool",
        isinstance(data.get("degraded"), bool),
        f"degraded: {data.get('degraded')} (type: {type(data.get('degraded')).__name__})",
    )

    # Test: services has redis, qdrant, memory_fallback keys
    services = data.get("services", {})
    expected_services = ["redis", "qdrant", "memory_fallback"]
    missing_services = [s for s in expected_services if s not in services]
    results.add(
        "services has redis, qdrant, memory_fallback keys",
        len(missing_services) == 0,
        f"Missing: {missing_services}" if missing_services else f"services: {services}",
    )

    # Test: enabled is bool
    results.add(
        "enabled is bool", isinstance(data.get("enabled"), bool), f"enabled: {data.get('enabled')}"
    )

    # Test: hit_rate is float 0.0-1.0
    hit_rate = data.get("hit_rate")
    results.add("hit_rate is float", isinstance(hit_rate, (int, float)), f"hit_rate: {hit_rate}")

    # Test: total_queries is int
    total_queries = data.get("total_queries")
    results.add(
        "total_queries is int", isinstance(total_queries, int), f"total_queries: {total_queries}"
    )

    # Test: timestamp is ISO 8601
    timestamp = data.get("timestamp")
    results.add(
        "Health timestamp is ISO 8601",
        isinstance(timestamp, str) and "T" in timestamp,
        f"timestamp: {timestamp}",
    )

    # GAP-102: Frontend expects {status: string, message?: string} but backend returns full CacheHealthResponse
    # The frontend cacheApi.getHealth() expects a simpler response shape
    # This is a contract mismatch - frontend type is too narrow
    results.add(
        "GAP-102: Backend returns full health response (frontend type too narrow)",
        "healthy" in data and "degraded" in data,
        "Frontend expects {status, message?} but backend returns CacheHealthResponse",
    )

    healthy_str = "healthy" if data.get("healthy") else "unhealthy"
    degraded_str = "degraded" if data.get("degraded") else "fully operational"
    print(f"\nHealth: {healthy_str}, {degraded_str}")

def test_response_types(results: TestResults, headers: dict):
    """Verify all response types match frontend expectations."""
    print("\n--- Testing Response Type Validation ---")

    # Get fresh stats to verify all types
    response = requests.get(f"{API_URL}/cache/stats", headers=headers)
    if response.status_code != 200:
        results.add("Stats fetch for type validation", False, f"Got {response.status_code}")
        return

    data = response.json()

    # CacheStatsResponse type validation
    # Required: total_queries, exact_hits, semantic_hits, misses, hit_rate (from frontend CacheStats interface)
    int_fields = ["total_queries", "exact_hits", "semantic_hits", "misses"]
    for field in int_fields:
        value = data.get(field)
        results.add(
            f"CacheStats.{field} is int",
            isinstance(value, int),
            f"Got: {value} ({type(value).__name__})",
        )

    # hit_rate should be float
    hit_rate = data.get("hit_rate")
    results.add(
        "CacheStats.hit_rate is float",
        isinstance(hit_rate, (int, float)),
        f"Got: {hit_rate} ({type(hit_rate).__name__})",
    )

    # config should be dict with specific keys
    config = data.get("config")
    if config:
        results.add(
            "CacheStats.config.enabled is bool",
            isinstance(config.get("enabled"), bool),
            f"Got: {config.get('enabled')}",
        )
        results.add(
            "CacheStats.config.similarity_threshold is float",
            isinstance(config.get("similarity_threshold"), (int, float)),
            f"Got: {config.get('similarity_threshold')}",
        )

    # Test CacheTuneResponse type (via actual call)
    response = requests.post(
        f"{API_URL}/cache/tune",
        headers=headers,
        json={"similarity_threshold": 0.85},  # Reset to reasonable default
    )
    if response.status_code == 200:
        tune_data = response.json()
        results.add(
            "CacheTuneResponse.message is string",
            isinstance(tune_data.get("message"), str),
            f"Got: {tune_data.get('message')}",
        )
        results.add(
            "CacheTuneResponse.updates is dict",
            isinstance(tune_data.get("updates"), dict),
            f"Got: {type(tune_data.get('updates')).__name__}",
        )
        results.add(
            "CacheTuneResponse.current_config is dict",
            isinstance(tune_data.get("current_config"), dict),
            f"Got: {type(tune_data.get('current_config')).__name__}",
        )
        results.add(
            "CacheTuneResponse.note is string",
            isinstance(tune_data.get("note"), str),
            f"Got: {tune_data.get('note')}",
        )

def test_frontend_evict_contract(results: TestResults, headers: dict):
    """Test that evict endpoint works with frontend's expected call pattern."""
    print("\n--- Testing Frontend Evict Contract ---")

    # GAP-103: Frontend cacheApi.evict() sends body with {count: N}, but backend expects query param
    # Frontend code: body: JSON.stringify({ count: count || 100 })
    # Backend code: count: int = Query(100, ge=1, le=10000, ...)

    # Test: Frontend pattern (body) should work or be documented as gap
    response = requests.post(f"{API_URL}/cache/evict", headers=headers, json={"count": 25})

    # Backend uses query param, so body is ignored - count will be default 100
    if response.status_code == 200:
        data = response.json()
        # If backend ignored body and used default, requested will be 100
        if data.get("requested") == 100:
            results.add(
                "GAP-103: Frontend sends body but backend expects query param",
                False,
                "Frontend sends JSON body {count: N}, backend uses query param ?count=N",
            )
        elif data.get("requested") == 25:
            results.add(
                "Evict accepts body (frontend compatible)", True, "Backend accepts body parameter"
            )
        else:
            results.add(
                "Evict count parsing", False, f"Unexpected requested value: {data.get('requested')}"
            )
    else:
        results.add("Frontend evict pattern returns 200", False, f"Got {response.status_code}")

def main():
    """Run all cache E2E tests."""
    print("=" * 80)
    print("Cache REST API E2E Tests")
    print("=" * 80)

    results = TestResults()

    # Check dependencies
    print("\n--- Checking Dependencies ---")
    redis_ok, qdrant_ok = check_dependencies()

    if not redis_ok and not qdrant_ok:
        print("\n[WARN] Neither Redis nor Qdrant available - cache will use memory fallback")

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
        print("Please start backend with: python -m core.main")
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

    # Run tests
    # 1. Stats endpoint
    test_get_cache_stats(results, headers)

    # 2. Tune endpoint tests
    test_tune_similarity_threshold(results, headers)
    test_tune_ttl_values(results, headers)
    test_tune_enabled_toggle(results, headers)
    test_tune_invalid_threshold(results, headers)

    # 3. Clear endpoint
    test_clear_cache(results, headers)

    # 4. Evict endpoint
    test_evict_cache(results, headers)
    test_frontend_evict_contract(results, headers)

    # 5. Health endpoint
    test_cache_health(results, headers)

    # 6. Type validation
    test_response_types(results, headers)

    # Summary
    results.summary()

    # Dependency status summary
    print("\n--- Dependency Status ---")
    print(f"Redis: {'available' if redis_ok else 'unavailable (using fallback)'}")
    print(f"Qdrant: {'available' if qdrant_ok else 'unavailable (using fallback)'}")

    # Return exit code based on results
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    import sys

    sys.exit(main() or 0)
