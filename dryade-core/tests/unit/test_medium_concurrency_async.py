"""Concurrency tests for medium-severity findings from Phase 102 audit.

Verifies thread-safety and async-safety of:
- Flows: _executions_lock exists and is threading.Lock, TTL eviction works
- Health: asyncio.Lock prevents thundering herd on get_cached_health()
- Cancellation: singleton is thread-safe, get_or_create is atomic

Phase 105-05: M-1, M-2, and M-3 remediation from Phase 102 audit.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Flows _executions concurrency tests (M-1)
# ---------------------------------------------------------------------------

class TestFlowsExecutionsLock:
    """Test that flows _executions dict is protected by threading.Lock."""

    def test_flows_executions_lock_exists(self):
        """_executions_lock must be a threading.Lock instance."""
        from core.api.routes.flows import _executions_lock

        assert isinstance(_executions_lock, type(threading.Lock()))

    def test_flows_ttl_eviction(self):
        """Expired entries (>TTL) are evicted by _evict_expired_executions()."""
        from core.api.routes.flows import (
            _evict_expired_executions,
            _executions,
            _executions_lock,
        )

        # Insert an expired entry (2 hours old)
        with _executions_lock:
            _executions["expired-test-id"] = {
                "status": "complete",
                "result": {},
                "flow_name": "test",
                "_created_at": time.time() - 7200,
            }
            # Insert a fresh entry
            _executions["fresh-test-id"] = {
                "status": "complete",
                "result": {},
                "flow_name": "test",
                "_created_at": time.time(),
            }

        try:
            with _executions_lock:
                _evict_expired_executions()
                assert "expired-test-id" not in _executions, "Expired entry should be evicted"
                assert "fresh-test-id" in _executions, "Fresh entry should remain"
        finally:
            # Clean up
            with _executions_lock:
                _executions.pop("expired-test-id", None)
                _executions.pop("fresh-test-id", None)

# ---------------------------------------------------------------------------
# Health cache thundering herd test (M-2)
# ---------------------------------------------------------------------------

class TestHealthCacheThunderingHerd:
    """Test that health cache uses asyncio.Lock to prevent thundering herd."""

    @pytest.mark.asyncio
    async def test_health_cache_no_thundering_herd(self):
        """Concurrent get_cached_health() calls should only invoke
        check_all_dependencies() once (not once per caller)."""
        import core.api.routes.health as health_mod

        # Reset cache to force a fresh check
        health_mod._health_cache = {}
        health_mod._health_cache_time = None

        call_count = 0

        async def slow_check():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate slow health check
            from core.health_checks import HealthStatus

            return {
                "database": HealthStatus(healthy=True, message="OK"),
            }

        with patch.object(health_mod, "check_all_dependencies", side_effect=slow_check):
            # Launch 5 concurrent calls
            results = await asyncio.gather(
                health_mod.get_cached_health(),
                health_mod.get_cached_health(),
                health_mod.get_cached_health(),
                health_mod.get_cached_health(),
                health_mod.get_cached_health(),
            )

        # Only one call should have gone through (the rest hit cache after lock)
        assert call_count == 1, (
            f"check_all_dependencies called {call_count} times, expected 1 "
            f"(thundering herd not prevented)"
        )

        # All results should be identical
        for r in results:
            assert "database" in r

# ---------------------------------------------------------------------------
# Cancellation registry concurrency tests (M-3)
# ---------------------------------------------------------------------------

class TestCancellationSingletonThreadSafe:
    """Test that get_cancellation_registry() is thread-safe."""

    def test_cancellation_singleton_threadsafe(self):
        """10 threads calling get_cancellation_registry() all get the same instance."""
        import core.orchestrator.cancellation as cancel_mod

        # Reset singleton to force creation
        cancel_mod._registry = None

        instances = []

        def get_registry():
            registry = cancel_mod.get_cancellation_registry()
            instances.append(id(registry))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(get_registry) for _ in range(10)]
            for f in futures:
                f.result()

        # All instances should be the same object
        assert len(set(instances)) == 1, (
            f"Expected 1 unique instance, got {len(set(instances))} (singleton not thread-safe)"
        )

class TestCancellationGetOrCreateAtomic:
    """Test that CancellationRegistry.get_or_create() is atomic."""

    def test_cancellation_get_or_create_atomic(self):
        """5 threads calling get_or_create('conv_abc') all get the same Event."""
        from core.orchestrator.cancellation import CancellationRegistry

        registry = CancellationRegistry()
        events = []

        def worker():
            event = registry.get_or_create("conv_abc")
            events.append(id(event))

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker) for _ in range(5)]
            for f in futures:
                f.result()

        # All events should be the same object
        assert len(set(events)) == 1, (
            f"Expected 1 unique Event, got {len(set(events))} (get_or_create not atomic)"
        )
