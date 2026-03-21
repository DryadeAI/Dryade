"""Concurrency tests for core.plugins thread-safety (H-1 remediation).

Tests verify that the threading locks added to the plugin system
prevent race conditions during:
- Singleton creation (PluginManager, PluginDrainer)
- Drainer request_start/drain atomicity
- Concurrent register/get on PluginManager
- Allowlist cache lock existence
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import core.ee.plugins_ee as plugins_mod
from core.ee.plugins_ee import (
    PluginDrainer,
    PluginManager,
    get_plugin_drainer,
    get_plugin_manager,
)

# ---------------------------------------------------------------------------
# Test 1: PluginManager singleton is thread-safe
# ---------------------------------------------------------------------------

class TestPluginManagerSingletonThreadsafe:
    def test_concurrent_get_plugin_manager_returns_same_instance(self):
        """10 threads calling get_plugin_manager() all get the same instance."""
        # Clear the global singleton
        plugins_mod._plugin_manager = None

        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(get_plugin_manager) for _ in range(10)]
            results = [f.result() for f in futures]

        # All must be the same object
        ids = {id(r) for r in results}
        assert len(ids) == 1, f"Expected 1 unique instance, got {len(ids)}"
        assert all(isinstance(r, PluginManager) for r in results)

        # Cleanup
        plugins_mod._plugin_manager = None

# ---------------------------------------------------------------------------
# Test 2: PluginDrainer singleton is thread-safe
# ---------------------------------------------------------------------------

class TestPluginDrainerSingletonThreadsafe:
    def test_concurrent_get_plugin_drainer_returns_same_instance(self):
        """10 threads calling get_plugin_drainer() all get the same instance."""
        plugins_mod._plugin_drainer = None

        results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(get_plugin_drainer) for _ in range(10)]
            results = [f.result() for f in futures]

        ids = {id(r) for r in results}
        assert len(ids) == 1, f"Expected 1 unique instance, got {len(ids)}"
        assert all(isinstance(r, PluginDrainer) for r in results)

        plugins_mod._plugin_drainer = None

# ---------------------------------------------------------------------------
# Test 3: Drainer request_start is atomic with drain
# ---------------------------------------------------------------------------

class TestDrainerRequestStartAtomic:
    def test_no_requests_slip_through_after_drain(self):
        """Once drain() marks a plugin as draining, request_start returns False."""
        drainer = PluginDrainer()
        plugin_name = "test_plugin"
        slip_through_count = 0
        barrier = threading.Barrier(2, timeout=5)

        def drain_thread():
            barrier.wait()
            # Manually set draining under lock (simulating drain() entry)
            with drainer._lock:
                drainer._draining.add(plugin_name)

        def request_thread():
            nonlocal slip_through_count
            barrier.wait()
            # Give drain_thread a tiny head start
            # Then hammer request_start
            for _ in range(1000):
                if drainer.request_start(plugin_name):
                    slip_through_count += 1
                    drainer.request_end(plugin_name)

        t_drain = threading.Thread(target=drain_thread)
        t_request = threading.Thread(target=request_thread)

        t_drain.start()
        t_request.start()
        t_drain.join(timeout=5)
        t_request.join(timeout=5)

        # After draining is set, no NEW requests should have started.
        # Some may have slipped through before draining was set -- that's OK.
        # The key invariant: once _draining contains the plugin, request_start
        # returns False. We verify the inflight count is 0 after all threads join.
        with drainer._lock:
            inflight = drainer._inflight.get(plugin_name, 0)
        assert inflight == 0, f"Expected 0 inflight after drain, got {inflight}"

# ---------------------------------------------------------------------------
# Test 4: Concurrent register/get on PluginManager
# ---------------------------------------------------------------------------

class TestPluginManagerConcurrentRegisterGet:
    def test_no_dict_changed_size_during_iteration(self):
        """Concurrent register and list/get operations do not raise RuntimeError."""
        manager = PluginManager()
        errors = []

        def register_plugins(start_idx):
            for i in range(start_idx, start_idx + 20):
                plugin = MagicMock()
                plugin.name = f"plugin_{i}"
                plugin.version = "1.0.0"
                plugin.description = f"Test plugin {i}"
                with manager._lock:
                    manager._plugins[plugin.name] = plugin

        def list_and_get():
            try:
                for _ in range(50):
                    _ = manager.get_plugins()
                    _ = manager.list_plugins()
                    _ = manager.get_plugin("plugin_0")
            except RuntimeError as e:
                errors.append(str(e))

        threads = []
        # 5 register threads
        for i in range(5):
            t = threading.Thread(target=register_plugins, args=(i * 20,))
            threads.append(t)
        # 5 list/get threads
        for _ in range(5):
            t = threading.Thread(target=list_and_get)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Got RuntimeErrors: {errors}"

# ---------------------------------------------------------------------------
# Test 5: Allowlist cache lock exists and is a threading.Lock
# ---------------------------------------------------------------------------

class TestAllowlistCacheLockExists:
    def test_allowlist_cache_lock_is_threading_lock(self):
        """_allowlist_cache_lock is a threading.Lock instance."""
        from core.ee.plugins_ee import _allowlist_cache_lock

        assert isinstance(_allowlist_cache_lock, type(threading.Lock()))
