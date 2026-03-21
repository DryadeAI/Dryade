#!/usr/bin/env python3
"""Run all extension E2E tests and provide aggregate summary.

This script:
1. Tests /extensions/* aggregate endpoints directly (status, metrics, timeline, config)
2. Runs cache, sandbox, healing, and safety tests
3. Provides a single summary of all extension validation

Extensions provide middleware-style composition for:
- Semantic caching (cache hits save ~$0.002 per query)
- Sandbox execution (gVisor > Docker > Process isolation)
- Self-healing (retry with backoff, circuit breakers)
- File safety (ClamAV + YARA scanning)
- Input/output safety (validation + sanitization)

Aggregate Endpoints (4):
- GET /extensions/status - all extension statuses with health
- GET /extensions/metrics - aggregated impact metrics
- GET /extensions/timeline - recent extension activity
- GET /extensions/config - current enable/disable state

Extension-Specific Endpoints (18):
- Cache: stats, tune, clear, evict, health (5)
- Sandbox: stats, config, cache/clear, health, tools (5)
- Healing: stats, circuit-breakers, circuit-breakers/{name}, reset, health (5)
- Safety: violations, stats, sanitization_stats (3)

Total: 22 extension endpoints

Usage:
    python scripts/test_extensions_e2e.py

Requirements:
    - Backend running at http://localhost:8000
    - Valid auth credentials
"""

import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

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

    def summary(self) -> tuple[int, int]:
        """Return pass/total counts."""
        return self.passed, len(self.tests)

    def print_results(self):
        """Print all results."""
        for test in self.tests:
            status = "PASS" if test["passed"] else "FAIL"
            details = f": {test['details']}" if test["details"] else ""
            print(f"  [{status}] {test['name']}{details}")

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
# Extensions Aggregate Endpoint Tests
# ============================================================================

def test_get_extensions_status(results: TestResults, headers: dict) -> list | None:
    """Test GET /api/extensions/status endpoint."""
    print("\n--- Testing GET /api/extensions/status ---")

    response = requests.get(f"{API_URL}/extensions/status", headers=headers)

    # Test: Response is 200
    results.add(
        "GET /extensions/status returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return None

    data = response.json()

    # Test: Response is a list
    results.add("Response is list", isinstance(data, list), f"Type: {type(data).__name__}")

    if not isinstance(data, list):
        return None

    # If extensions exist, validate structure
    for item in data:
        # Required fields per ExtensionStatus model
        required = ["name", "type", "enabled", "priority", "health"]
        missing = [f for f in required if f not in item]
        if missing:
            results.add("Extension status has required fields", False, f"Missing: {missing}")
            return data

        # Validate types
        if not isinstance(item["name"], str):
            results.add("name is string", False, f"Type: {type(item['name']).__name__}")
            return data

        if not isinstance(item["enabled"], bool):
            results.add("enabled is bool", False, f"Type: {type(item['enabled']).__name__}")
            return data

        if not isinstance(item["priority"], int):
            results.add("priority is int", False, f"Type: {type(item['priority']).__name__}")
            return data

        # Validate health enum
        valid_health = ["healthy", "degraded", "down"]
        if item["health"] not in valid_health:
            results.add(
                "health is valid enum", False, f"Got: {item['health']}, expected: {valid_health}"
            )
            return data

    results.add("All extension statuses have valid structure", True, f"{len(data)} extensions")

    print(f"\nExtensions: {len(data)}")
    for ext in data[:5]:  # Show first 5
        print(f"  - {ext['name']}: {ext['health']} (priority {ext['priority']})")

    return data

def test_get_extensions_metrics(results: TestResults, headers: dict) -> dict | None:
    """Test GET /api/extensions/metrics endpoint."""
    print("\n--- Testing GET /api/extensions/metrics ---")

    response = requests.get(f"{API_URL}/extensions/metrics", headers=headers)

    # Test: Response is 200
    # BACKEND-BUG: extensions.py uses async with get_session() but get_session() is sync generator
    # This causes 500 error until the route is fixed to use sync session or async session is added
    if response.status_code == 500:
        results.add(
            "GET /extensions/metrics returns 200 (BACKEND-BUG: async/sync session mismatch)",
            False,
            "500 error - route uses 'async with get_session()' but get_session() is sync",
        )
        return None

    results.add(
        "GET /extensions/metrics returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return None

    data = response.json()

    # Test: Required fields present
    required_fields = [
        "cache_hit_rate",
        "cache_savings_usd",
        "sandbox_overhead_ms",
        "healing_success_rate",
        "threats_blocked",
        "validation_failures",
        "total_requests",
    ]
    missing = [f for f in required_fields if f not in data]
    results.add(
        "Metrics response has required fields",
        len(missing) == 0,
        f"Missing: {missing}" if missing else f"Fields: {list(data.keys())}",
    )

    # Test: cache_hit_rate is float 0.0-1.0
    hit_rate = data.get("cache_hit_rate")
    results.add(
        "cache_hit_rate is float 0.0-1.0",
        isinstance(hit_rate, (int, float)) and 0.0 <= hit_rate <= 1.0,
        f"cache_hit_rate: {hit_rate}",
    )

    # Test: cache_savings_usd is float >= 0.0
    savings = data.get("cache_savings_usd")
    results.add(
        "cache_savings_usd is non-negative float",
        isinstance(savings, (int, float)) and savings >= 0.0,
        f"cache_savings_usd: {savings}",
    )

    # Test: threats_blocked is int >= 0
    threats = data.get("threats_blocked")
    results.add(
        "threats_blocked is non-negative int",
        isinstance(threats, int) and threats >= 0,
        f"threats_blocked: {threats}",
    )

    # Test: total_requests is int >= 0
    total = data.get("total_requests")
    results.add(
        "total_requests is non-negative int",
        isinstance(total, int) and total >= 0,
        f"total_requests: {total}",
    )

    print(f"\nMetrics: hit rate {hit_rate:.2%}, {total} requests, ${savings:.4f} saved")

    return data

def test_get_extensions_metrics_with_hours(results: TestResults, headers: dict):
    """Test GET /api/extensions/metrics?hours=48 endpoint."""
    print("\n--- Testing GET /api/extensions/metrics?hours=48 ---")

    response = requests.get(f"{API_URL}/extensions/metrics?hours=48", headers=headers)

    # BACKEND-BUG: Same async/sync issue as /metrics
    if response.status_code == 500:
        results.add(
            "GET /extensions/metrics?hours=48 returns 200 (BACKEND-BUG)",
            False,
            "500 error - async/sync session mismatch",
        )
        return

    results.add(
        "GET /extensions/metrics?hours=48 returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: total_requests field exists
    results.add(
        "hours parameter accepted (response has total_requests)",
        "total_requests" in data,
        f"Fields: {list(data.keys())}",
    )

def test_get_extensions_timeline(results: TestResults, headers: dict) -> list | None:
    """Test GET /api/extensions/timeline endpoint."""
    print("\n--- Testing GET /api/extensions/timeline ---")

    response = requests.get(f"{API_URL}/extensions/timeline", headers=headers)

    # BACKEND-BUG: Same async/sync session mismatch
    if response.status_code == 500:
        results.add(
            "GET /extensions/timeline returns 200 (BACKEND-BUG)",
            False,
            "500 error - async/sync session mismatch",
        )
        return None

    results.add(
        "GET /extensions/timeline returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return None

    data = response.json()

    # Test: Response is list
    results.add("Response is list", isinstance(data, list), f"Type: {type(data).__name__}")

    if not isinstance(data, list):
        return None

    # If entries exist, validate structure
    for item in data:
        required = [
            "request_id",
            "operation",
            "extensions_applied",
            "total_duration_ms",
            "outcomes",
            "timestamp",
        ]
        missing = [f for f in required if f not in item]
        if missing:
            results.add("Timeline entry has required fields", False, f"Missing: {missing}")
            return data

        # Validate types
        if not isinstance(item["extensions_applied"], list):
            results.add(
                "extensions_applied is list",
                False,
                f"Type: {type(item['extensions_applied']).__name__}",
            )
            return data

        if not isinstance(item["outcomes"], dict):
            results.add("outcomes is dict", False, f"Type: {type(item['outcomes']).__name__}")
            return data

    results.add("All timeline entries have valid structure", True, f"{len(data)} entries")

    print(f"\nTimeline: {len(data)} entries")

    return data

def test_get_extensions_timeline_with_limit(results: TestResults, headers: dict):
    """Test GET /api/extensions/timeline?limit=10 endpoint."""
    print("\n--- Testing GET /api/extensions/timeline?limit=10 ---")

    response = requests.get(f"{API_URL}/extensions/timeline?limit=10", headers=headers)

    # BACKEND-BUG: Same async/sync session mismatch
    if response.status_code == 500:
        results.add(
            "GET /extensions/timeline?limit=10 returns 200 (BACKEND-BUG)",
            False,
            "500 error - async/sync session mismatch",
        )
        return

    results.add(
        "GET /extensions/timeline?limit=10 returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return

    data = response.json()

    # Test: Response is list
    results.add(
        "Response with limit is list", isinstance(data, list), f"Type: {type(data).__name__}"
    )

    # Test: Limit respected
    if isinstance(data, list):
        results.add("limit=10 respected", len(data) <= 10, f"Got {len(data)} entries")

def test_get_extensions_config(results: TestResults, headers: dict) -> dict | None:
    """Test GET /api/extensions/config endpoint."""
    print("\n--- Testing GET /api/extensions/config ---")

    response = requests.get(f"{API_URL}/extensions/config", headers=headers)

    # Test: Response is 200
    results.add(
        "GET /extensions/config returns 200",
        response.status_code == 200,
        f"Got {response.status_code}",
    )

    if response.status_code != 200:
        return None

    data = response.json()

    # Test: Required fields present
    required_fields = [
        "extensions_enabled",
        "input_validation_enabled",
        "semantic_cache_enabled",
        "self_healing_enabled",
        "sandbox_enabled",
        "file_safety_enabled",
        "output_sanitization_enabled",
    ]
    missing = [f for f in required_fields if f not in data]
    results.add(
        "Config response has required fields",
        len(missing) == 0,
        f"Missing: {missing}" if missing else f"Fields: {list(data.keys())}",
    )

    # Test: All fields are booleans
    all_bools = all(isinstance(data.get(f), bool) for f in required_fields)
    results.add(
        "All config fields are booleans",
        all_bools,
        f"Types: {[type(data.get(f)).__name__ for f in required_fields]}",
    )

    # Count enabled features
    enabled_count = sum(1 for f in required_fields if data.get(f))
    print(f"\nConfig: {enabled_count}/{len(required_fields)} features enabled")

    return data

# ============================================================================
# Extension-Specific Test Runners
# ============================================================================

def run_test_script(script_name: str) -> tuple[bool, str, int, int]:
    """Run a test script and capture results.

    Returns: (success, output, passed, total)
    """
    try:
        result = subprocess.run(
            [sys.executable, f"scripts/{script_name}"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        output = result.stdout + result.stderr

        # Parse pass/fail from output
        # Look for "Test Summary: X passed, Y failed"
        passed = 0
        total = 0
        for line in output.split("\n"):
            if "Test Summary:" in line and "passed" in line:
                parts = line.split()
                try:
                    passed_idx = parts.index("passed,") - 1
                    failed_idx = parts.index("failed") - 1
                    passed = int(parts[passed_idx])
                    failed = int(parts[failed_idx])
                    total = passed + failed
                except (ValueError, IndexError):
                    pass

        # Success if no "FAIL" in output or returncode is 0
        success = result.returncode == 0

        return success, output, passed, total

    except subprocess.TimeoutExpired:
        return False, "Test timed out after 120s", 0, 0
    except FileNotFoundError:
        return False, f"Script not found: scripts/{script_name}", 0, 0
    except Exception as e:
        return False, str(e), 0, 0

def main():
    """Run all extension E2E tests."""
    print("=" * 80)
    print("Extensions E2E Validation Suite")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 80)

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

    # ========================================================================
    # Phase 1: Test aggregate endpoints
    # ========================================================================
    print("\n" + "=" * 60)
    print("Phase 1: Extensions Aggregate Endpoints (/extensions/*)")
    print("=" * 60)

    aggregate_results = TestResults()

    test_get_extensions_status(aggregate_results, headers)
    test_get_extensions_metrics(aggregate_results, headers)
    test_get_extensions_metrics_with_hours(aggregate_results, headers)
    test_get_extensions_timeline(aggregate_results, headers)
    test_get_extensions_timeline_with_limit(aggregate_results, headers)
    test_get_extensions_config(aggregate_results, headers)

    agg_passed, agg_total = aggregate_results.summary()
    print(f"\n--- Aggregate Endpoints: {agg_passed}/{agg_total} passed ---")

    # ========================================================================
    # Phase 2: Run extension-specific tests
    # ========================================================================
    print("\n" + "=" * 60)
    print("Phase 2: Extension-Specific Tests")
    print("=" * 60)

    extension_tests = [
        ("test_cache_e2e.py", "Semantic Cache", 5),
        ("test_sandbox_e2e.py", "Sandbox", 5),
        ("test_healing_e2e.py", "Self-Healing", 5),
        ("test_safety_e2e.py", "Safety", 3),
    ]

    ext_results = []
    ext_total_passed = 0
    ext_total_tests = 0

    for script, name, endpoint_count in extension_tests:
        print(f"\n--- Running {name} tests ({script}) ---")
        success, output, passed, total = run_test_script(script)
        ext_results.append((name, success, passed, total, endpoint_count))
        ext_total_passed += passed
        ext_total_tests += total

        # Print truncated output
        lines = output.strip().split("\n")
        if len(lines) > 30:
            print("\n".join(lines[:15]))
            print(f"... ({len(lines) - 30} lines omitted) ...")
            print("\n".join(lines[-15:]))
        else:
            print(output)

    # ========================================================================
    # Final Summary
    # ========================================================================
    print("\n" + "=" * 80)
    print("AGGREGATE SUMMARY")
    print("=" * 80)

    print(f"\nPhase 1 - Extensions Aggregate Endpoints: {agg_passed}/{agg_total}")
    print(f"Phase 2 - Extension-Specific Tests: {ext_total_passed}/{ext_total_tests}")

    print("\nBreakdown by Extension:")
    print(
        f"  [{'PASS' if agg_passed == agg_total else 'FAIL'}] /extensions/* aggregate (4 endpoints, {agg_total} tests)"
    )
    for name, success, passed, total, endpoints in ext_results:
        status = "PASS" if success else "FAIL"
        print(f"  [{status}] {name} ({endpoints} endpoints, {passed}/{total} tests)")

    print("\nEndpoint Coverage:")
    print("  - Cache: 5 endpoints (stats, tune, clear, evict, health)")
    print("  - Sandbox: 5 endpoints (stats, config, cache/clear, health, tools)")
    print("  - Healing: 5 endpoints (stats, circuit-breakers, {name}, reset, health)")
    print("  - Safety: 3 endpoints (violations, stats, sanitization_stats)")
    print("  - Extensions: 4 endpoints (status, metrics, timeline, config)")
    print("  ----------------------------------------")
    print("  Total: 22 endpoints")

    # Calculate overall success
    all_ext_passed = all(success for _, success, _, _, _ in ext_results)
    total_pass = (agg_passed == agg_total) and all_ext_passed

    print(f"\nOverall: {'PASS' if total_pass else 'FAIL'}")

    return 0 if total_pass else 1

if __name__ == "__main__":
    sys.exit(main())
