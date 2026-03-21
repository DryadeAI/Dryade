"""Concurrency tests for knowledge and agent registries.

Verifies thread-safety of:
- Knowledge registry: concurrent register/list, delete/list, atomic delete
- Agent registry: singleton thread-safety, concurrent register/list

Phase 105-03: H-2 and H-3 remediation from Phase 102 audit.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Knowledge registry concurrency tests
# ---------------------------------------------------------------------------

class TestKnowledgeConcurrentRegisterList:
    """Test concurrent register + list on knowledge registry."""

    @patch("core.knowledge.sources.persist_knowledge_source")
    def test_knowledge_concurrent_register_list(self, mock_persist):
        """5 threads registering + 5 threads listing simultaneously.

        Assert no RuntimeError: dictionary changed size during iteration.
        """
        from core.knowledge.sources import (
            _knowledge_lock,
            _knowledge_registry,
            list_knowledge_sources,
            register_knowledge_source,
        )

        # Clean state
        with _knowledge_lock:
            _knowledge_registry.clear()

        errors = []

        def register_worker(thread_id):
            try:
                for i in range(20):
                    register_knowledge_source(
                        name=f"source-t{thread_id}-{i}",
                        source=None,
                        description=f"Thread {thread_id} source {i}",
                        metadata={"source_id": f"ks_t{thread_id}_{i}"},
                        source_type="test",
                        file_paths=[],
                    )
            except Exception as e:
                errors.append(("register", thread_id, e))

        def list_worker(thread_id):
            try:
                for _ in range(20):
                    sources = list_knowledge_sources()
                    # Just access the list to force iteration
                    _ = len(sources)
            except Exception as e:
                errors.append(("list", thread_id, e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for t in range(5):
                futures.append(pool.submit(register_worker, t))
            for t in range(5):
                futures.append(pool.submit(list_worker, t + 5))

            for f in as_completed(futures):
                f.result()  # re-raise if any

        assert errors == [], f"Concurrency errors: {errors}"

        # Cleanup
        with _knowledge_lock:
            _knowledge_registry.clear()

class TestKnowledgeConcurrentDeleteList:
    """Test concurrent delete + list on knowledge registry."""

    @patch("core.knowledge.sources.persist_knowledge_source")
    @patch("core.knowledge.sources.delete_persisted_knowledge_source")
    def test_knowledge_concurrent_delete_list(self, mock_delete_db, mock_persist):
        """Register 10 sources, then delete and list concurrently.

        Assert no RuntimeError and no KeyError.
        """
        from core.knowledge.sources import (
            _knowledge_lock,
            _knowledge_registry,
            delete_knowledge_source,
            list_knowledge_sources,
            register_knowledge_source,
        )

        # Clean state and register 10 sources
        with _knowledge_lock:
            _knowledge_registry.clear()

        source_ids = []
        for i in range(10):
            sid = register_knowledge_source(
                name=f"del-source-{i}",
                source=None,
                metadata={"source_id": f"ks_del_{i}"},
                source_type="test",
                file_paths=[],
            )
            source_ids.append(sid)

        errors = []

        def delete_worker():
            try:
                for sid in source_ids:
                    delete_knowledge_source(sid)
            except Exception as e:
                errors.append(("delete", e))

        def list_worker():
            try:
                for _ in range(20):
                    sources = list_knowledge_sources()
                    _ = len(sources)
            except Exception as e:
                errors.append(("list", e))

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(delete_worker),
                pool.submit(delete_worker),
                pool.submit(list_worker),
                pool.submit(list_worker),
            ]
            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Concurrency errors: {errors}"

        # Cleanup
        with _knowledge_lock:
            _knowledge_registry.clear()

class TestKnowledgeDeleteAtomicity:
    """Test atomic check-then-act on delete."""

    @patch("core.knowledge.sources.persist_knowledge_source")
    @patch("core.knowledge.sources.delete_persisted_knowledge_source")
    def test_knowledge_delete_check_then_act_atomic(self, mock_delete_db, mock_persist):
        """Two threads try to delete the same source simultaneously.

        Exactly one should return True and the other False.
        DB delete should be called exactly once.
        """
        from core.knowledge.sources import (
            _knowledge_lock,
            _knowledge_registry,
            delete_knowledge_source,
            register_knowledge_source,
        )

        # Clean state
        with _knowledge_lock:
            _knowledge_registry.clear()

        register_knowledge_source(
            name="contested-source",
            source=None,
            metadata={"source_id": "ks_contested"},
            source_type="test",
            file_paths=[],
        )

        barrier = threading.Barrier(2)
        results = []

        def delete_worker():
            barrier.wait()  # Synchronize both threads
            result = delete_knowledge_source("ks_contested")
            results.append(result)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(delete_worker), pool.submit(delete_worker)]
            for f in as_completed(futures):
                f.result()

        # Exactly one True and one False
        assert sorted(results) == [False, True], f"Expected [False, True], got {sorted(results)}"

        # DB delete called exactly once
        assert mock_delete_db.call_count == 1

        # Cleanup
        with _knowledge_lock:
            _knowledge_registry.clear()

# ---------------------------------------------------------------------------
# Agent registry concurrency tests
# ---------------------------------------------------------------------------

def _make_mock_agent(name: str) -> MagicMock:
    """Create a mock UniversalAgent with a proper AgentCard."""
    agent = MagicMock()
    card = MagicMock()
    card.name = name
    card.capabilities = []
    agent.get_card.return_value = card
    return agent

class TestAgentRegistrySingletonThreadsafe:
    """Test double-checked locking on get_registry singleton."""

    def test_agent_registry_singleton_threadsafe(self):
        """10 threads calling get_registry() all get the same instance."""
        import core.adapters.registry as reg_module

        # Reset singleton
        original = reg_module._registry
        reg_module._registry = None

        instances = []

        def get_worker():
            r = reg_module.get_registry()
            instances.append(id(r))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(get_worker) for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        # All instances should be the same object
        assert len(set(instances)) == 1, f"Got {len(set(instances))} different instances"

        # Restore original
        reg_module._registry = original

class TestAgentRegistryConcurrentRegisterList:
    """Test concurrent register + list on agent registry."""

    def test_agent_registry_concurrent_register_list(self):
        """5 threads registering + 5 threads listing simultaneously.

        Assert no RuntimeError.
        """
        from core.adapters.registry import AgentRegistry

        registry = AgentRegistry()
        errors = []

        def register_worker(thread_id):
            try:
                for i in range(20):
                    agent = _make_mock_agent(f"agent-t{thread_id}-{i}")
                    registry.register(agent)
            except Exception as e:
                errors.append(("register", thread_id, e))

        def list_worker(thread_id):
            try:
                for _ in range(20):
                    cards = registry.list_agents()
                    _ = len(cards)
            except Exception as e:
                errors.append(("list", thread_id, e))

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            for t in range(5):
                futures.append(pool.submit(register_worker, t))
            for t in range(5):
                futures.append(pool.submit(list_worker, t + 5))

            for f in as_completed(futures):
                f.result()

        assert errors == [], f"Concurrency errors: {errors}"
