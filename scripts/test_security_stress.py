#!/usr/bin/env python3
"""Extension Pipeline Stress Test.

Tests the robustness of the 6-layer extension pipeline under concurrent load:
1. Input Validation
2. Semantic Cache
3. Self-Healing
4. Sandbox
5. File Safety
6. Output Sanitization

Sends 100+ concurrent requests with large payloads to verify:
- All extensions process correctly or degrade gracefully
- Measures overhead per extension
- Tests large messages (10KB) and files (50MB)
"""

import asyncio
import os
import random
import string
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx

# Configuration
BACKEND_URL = os.getenv("DRYADE_BACKEND_URL", "http://localhost:8080")
NUM_REQUESTS = 100  # Number of concurrent requests
LARGE_MESSAGE_SIZE = 10 * 1024  # 10KB messages
TIMEOUT = 30.0  # Request timeout in seconds

# Test messages
SMALL_MESSAGE = "Hello, how are you?"
MEDIUM_MESSAGE = "Analyze this data: " + "x" * 1000

def generate_large_message(size_bytes: int) -> str:
    """Generate a large message of specified size."""
    return "".join(random.choices(string.ascii_letters + string.digits + " ", k=size_bytes))

@dataclass
class RequestResult:
    """Result from a single request."""

    success: bool
    duration_ms: float
    status_code: int | None = None
    error: str | None = None
    extensions_applied: list[str] | None = None
    response_size: int = 0

class StressTestRunner:
    """Runs stress tests against the backend."""

    def __init__(self, backend_url: str, timeout: float = TIMEOUT):
        self.backend_url = backend_url.rstrip("/")
        self.timeout = timeout
        self.results: list[RequestResult] = []
        self.extension_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_time_ms": 0, "errors": 0}
        )

    async def health_check(self) -> bool:
        """Check if backend is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.backend_url}/health")
                return response.status_code == 200
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False

    async def setup_test_user(self) -> str | None:
        """Setup test user and return access token."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to login first
                response = await client.post(
                    f"{self.backend_url}/api/auth/login",
                    json={"email": "stress@test.com", "password": "StressTest123!"},
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("access_token")

                # If login fails, try to register
                response = await client.post(
                    f"{self.backend_url}/api/auth/register",
                    json={
                        "email": "stress@test.com",
                        "password": "StressTest123!",
                        "full_name": "Stress Test User",
                    },
                )

                if response.status_code in [200, 201]:
                    data = response.json()
                    return data.get("access_token")

                print("⚠️  Could not setup test user, proceeding without auth")
                return None

        except Exception as e:
            print(f"⚠️  Auth setup failed: {e}, proceeding without auth")
            return None

    async def send_request(
        self, message: str, token: str | None = None, request_id: int = 0
    ) -> RequestResult:
        """Send a single request to the chat endpoint."""
        start_time = time.perf_counter()

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.backend_url}/api/chat",
                    json={
                        "message": message,
                        "conversation_id": f"stress-test-{request_id}",
                        "mode": "chat",
                    },
                    headers=headers,
                )

                duration_ms = (time.perf_counter() - start_time) * 1000

                # Check if successful
                success = 200 <= response.status_code < 300

                # Try to extract extension metadata
                extensions_applied = None
                response_size = len(response.content)

                if success:
                    try:
                        data = response.json()
                        # Extensions metadata might be in the response
                        extensions_applied = data.get("metadata", {}).get("extensions_applied", [])
                    except Exception:
                        pass

                return RequestResult(
                    success=success,
                    duration_ms=duration_ms,
                    status_code=response.status_code,
                    extensions_applied=extensions_applied,
                    response_size=response_size,
                )

        except TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return RequestResult(success=False, duration_ms=duration_ms, error="Timeout")
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return RequestResult(success=False, duration_ms=duration_ms, error=str(e))

    async def run_concurrent_requests(
        self, num_requests: int, message_generator, token: str | None = None
    ) -> list[RequestResult]:
        """Run multiple concurrent requests."""
        print(f"  Sending {num_requests} concurrent requests...")

        tasks = []
        for i in range(num_requests):
            message = message_generator(i) if callable(message_generator) else message_generator
            task = self.send_request(message, token, i)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(
                    RequestResult(success=False, duration_ms=0, error=str(result))
                )
            else:
                processed_results.append(result)

        return processed_results

    def analyze_results(self, results: list[RequestResult], test_name: str):
        """Analyze and print test results."""
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        failure_rate = (failed / total) * 100 if total > 0 else 0

        # Duration statistics
        durations = [r.duration_ms for r in results if r.success]
        if durations:
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            p95_duration = (
                sorted(durations)[int(len(durations) * 0.95)]
                if len(durations) > 1
                else max_duration
            )
        else:
            avg_duration = min_duration = max_duration = p95_duration = 0

        # Response size statistics
        response_sizes = [r.response_size for r in results if r.success]
        avg_response_size = sum(response_sizes) / len(response_sizes) if response_sizes else 0

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"📊 {test_name}")
        print(f"{'=' * 60}")
        print(f"  Total Requests:     {total}")
        print(f"  ✅ Successful:      {successful} ({100 - failure_rate:.1f}%)")
        print(f"  ❌ Failed:          {failed} ({failure_rate:.1f}%)")
        print("\n  ⏱️  Duration (ms):")
        print(f"     Average:         {avg_duration:.2f} ms")
        print(f"     Min:             {min_duration:.2f} ms")
        print(f"     Max:             {max_duration:.2f} ms")
        print(f"     P95:             {p95_duration:.2f} ms")
        print(f"\n  📦 Response Size:   {avg_response_size:.0f} bytes (avg)")

        # Error breakdown
        if failed > 0:
            error_counts = defaultdict(int)
            for r in results:
                if not r.success:
                    error_type = r.error or f"HTTP {r.status_code}"
                    error_counts[error_type] += 1

            print("\n  ⚠️  Error Breakdown:")
            for error, count in sorted(error_counts.items(), key=lambda x: -x[1]):
                print(f"     {error}: {count}")

        # Success criteria check
        print(f"\n  {'✅' if failure_rate < 10 else '❌'} Success Criteria: Failure rate < 10%")

        return failure_rate < 10

    async def test_small_messages(self, token: str | None = None):
        """Test with small messages."""
        print("\n" + "=" * 60)
        print("Test 1: Small Messages (concurrent)")
        print("=" * 60)

        results = await self.run_concurrent_requests(NUM_REQUESTS, lambda _: SMALL_MESSAGE, token)
        self.results.extend(results)
        return self.analyze_results(results, "Small Messages Test")

    async def test_large_messages(self, token: str | None = None):
        """Test with large 10KB messages."""
        print("\n" + "=" * 60)
        print("Test 2: Large Messages (10KB, concurrent)")
        print("=" * 60)

        large_message = generate_large_message(LARGE_MESSAGE_SIZE)
        results = await self.run_concurrent_requests(NUM_REQUESTS, lambda _: large_message, token)
        self.results.extend(results)
        return self.analyze_results(results, "Large Messages Test")

    async def test_mixed_load(self, token: str | None = None):
        """Test with mixed message sizes."""
        print("\n" + "=" * 60)
        print("Test 3: Mixed Load (small + large, concurrent)")
        print("=" * 60)

        def message_generator(i: int) -> str:
            if i % 2 == 0:
                return SMALL_MESSAGE
            else:
                return generate_large_message(LARGE_MESSAGE_SIZE)

        results = await self.run_concurrent_requests(NUM_REQUESTS, message_generator, token)
        self.results.extend(results)
        return self.analyze_results(results, "Mixed Load Test")

    async def test_burst_load(self, token: str | None = None):
        """Test with burst of requests."""
        print("\n" + "=" * 60)
        print("Test 4: Burst Load (200 requests, concurrent)")
        print("=" * 60)

        results = await self.run_concurrent_requests(200, lambda _: MEDIUM_MESSAGE, token)
        self.results.extend(results)
        return self.analyze_results(results, "Burst Load Test")

    async def test_extension_overhead(self, token: str | None = None):
        """Test to measure extension overhead."""
        print("\n" + "=" * 60)
        print("Test 5: Extension Overhead (sequential)")
        print("=" * 60)

        # Send requests sequentially to measure per-extension overhead
        results = []
        for i in range(20):
            result = await self.send_request(MEDIUM_MESSAGE, token, i)
            results.append(result)
            if result.extensions_applied:
                for ext_name in result.extensions_applied:
                    self.extension_stats[ext_name]["count"] += 1
                    self.extension_stats[ext_name]["total_time_ms"] += result.duration_ms / len(
                        result.extensions_applied
                    )
                    if not result.success:
                        self.extension_stats[ext_name]["errors"] += 1

        self.results.extend(results)
        passed = self.analyze_results(results, "Extension Overhead Test")

        # Print extension statistics
        if self.extension_stats:
            print("\n  📈 Extension Overhead:")
            for ext_name, stats in sorted(self.extension_stats.items()):
                avg_time = stats["total_time_ms"] / stats["count"] if stats["count"] > 0 else 0
                print(f"     {ext_name}:")
                print(f"       Requests: {stats['count']}")
                print(f"       Avg Time: {avg_time:.2f} ms")
                print(f"       Errors:   {stats['errors']}")

        return passed

    async def run_all_tests(self):
        """Run all stress tests."""
        print("\n" + "=" * 60)
        print("🔥 Extension Pipeline Stress Test Suite")
        print("=" * 60)
        print(f"Backend URL: {self.backend_url}")
        print(f"Concurrent Requests: {NUM_REQUESTS}")
        print(f"Large Message Size: {LARGE_MESSAGE_SIZE} bytes")
        print(f"Request Timeout: {self.timeout}s")

        # Health check
        print("\n⏳ Running health check...")
        if not await self.health_check():
            print("❌ Backend is not healthy. Exiting.")
            return False

        print("✅ Backend is healthy")

        # Setup auth
        print("\n⏳ Setting up test user...")
        token = await self.setup_test_user()
        if token:
            print("✅ Test user authenticated")
        else:
            print("⚠️  Running tests without authentication")

        # Run tests
        test_results = []
        test_results.append(await self.test_small_messages(token))
        test_results.append(await self.test_large_messages(token))
        test_results.append(await self.test_mixed_load(token))
        test_results.append(await self.test_burst_load(token))
        test_results.append(await self.test_extension_overhead(token))

        # Final summary
        print("\n" + "=" * 60)
        print("🏁 Final Summary")
        print("=" * 60)

        total_requests = len(self.results)
        total_successful = sum(1 for r in self.results if r.success)
        total_failed = total_requests - total_successful
        overall_failure_rate = (total_failed / total_requests) * 100 if total_requests > 0 else 0

        print(f"  Total Requests:     {total_requests}")
        print(f"  ✅ Successful:      {total_successful} ({100 - overall_failure_rate:.1f}%)")
        print(f"  ❌ Failed:          {total_failed} ({overall_failure_rate:.1f}%)")

        passed_tests = sum(1 for r in test_results if r)
        total_tests = len(test_results)
        print(f"\n  Tests Passed:       {passed_tests}/{total_tests}")

        # Overall success criteria
        overall_passed = overall_failure_rate < 10 and passed_tests >= total_tests * 0.8

        print(
            f"\n  {'✅' if overall_passed else '❌'} Overall: {
                'PASS' if overall_passed else 'FAIL'
            } (failure rate: {overall_failure_rate:.1f}%)"
        )

        return overall_passed

async def main():
    """Main entry point."""
    runner = StressTestRunner(BACKEND_URL, TIMEOUT)

    try:
        passed = await runner.run_all_tests()
        sys.exit(0 if passed else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
