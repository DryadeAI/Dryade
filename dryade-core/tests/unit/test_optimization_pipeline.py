"""Tests for core.orchestrator.optimization_pipeline -- Phase 115.5.

Covers RoutingOptimizer scoring, synthesis, optimization cycle,
deduplication, eviction, and singleton.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from core.orchestrator.optimization_pipeline import (
    _CATEGORY_MAP,
    OptimizationResult,
    RoutingOptimizer,
    _synthesize_message,
    get_routing_optimizer,
)

# ---- Helpers ----------------------------------------------------------------

def _make_metric(**overrides) -> SimpleNamespace:
    """Build a mock routing metric with sensible defaults."""
    defaults = {
        "timestamp": datetime.now(UTC),
        "message_hash": "abc123",
        "hint_fired": True,
        "hint_type": "meta_action",
        "llm_tool_called": "create",  # Phase 167: unified `create` tool
        "fallback_activated": False,
        "user_approved": True,
        "latency_ms": 100,
        "tool_arguments_hash": "hash_aaa",
        "success_outcome": True,
        "model_tier": "frontier",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)

def _fresh_library():
    """Return a fresh FewShotLibrary instance."""
    from core.orchestrator.few_shot_library import FewShotLibrary

    return FewShotLibrary()

# ---- Synthetic message generation -------------------------------------------

class TestSynthesizeMessage:
    def test_create_tool(self):
        # Phase 167: `create` replaces self_improve/create_agent/create_tool
        result = _synthesize_message("create", "abc")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be a natural language message, not a raw template
        assert "{" not in result

    def test_modify_config(self):
        result = _synthesize_message("modify_config", "xyz")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "{" not in result

    def test_unknown_tool(self):
        result = _synthesize_message("unknown_tool", "xyz")
        assert result == "Perform a unknown_tool operation"

    def test_deterministic(self):
        """Same (tool, hash) inputs produce the same output."""
        r1 = _synthesize_message("create", "abc")
        r2 = _synthesize_message("create", "abc")
        assert r1 == r2

    def test_different_hashes_may_differ(self):
        """Different hashes can produce different messages."""
        r1 = _synthesize_message("create", "aaa")
        r2 = _synthesize_message("create", "zzz")
        # They may or may not differ, but both should be valid strings
        assert isinstance(r1, str) and len(r1) > 0
        assert isinstance(r2, str) and len(r2) > 0

# ---- Scoring ----------------------------------------------------------------

class TestScore:
    def test_perfect(self):
        m = _make_metric(
            hint_fired=True,
            llm_tool_called="create",  # Phase 167: unified tool
            fallback_activated=False,
            user_approved=True,
            success_outcome=True,
        )
        assert RoutingOptimizer._score(m) == 1.0

    def test_unknown_outcome(self):
        m = _make_metric(
            hint_fired=True,
            llm_tool_called="create",  # Phase 167: unified tool
            fallback_activated=False,
            success_outcome=None,
        )
        assert RoutingOptimizer._score(m) == 0.8

    def test_failed_outcome(self):
        m = _make_metric(
            hint_fired=True,
            llm_tool_called="create",  # Phase 167: unified tool
            fallback_activated=False,
            user_approved=True,
            success_outcome=False,
        )
        assert RoutingOptimizer._score(m) == 0.5

    def test_fallback_activated(self):
        m = _make_metric(fallback_activated=True)
        assert RoutingOptimizer._score(m) == 0.0

    def test_no_hint_no_tool(self):
        m = _make_metric(hint_fired=False, llm_tool_called=None)
        assert RoutingOptimizer._score(m) == 0.0

# ---- Optimization cycle -----------------------------------------------------

class TestOptimize:
    @patch("core.orchestrator.few_shot_library.get_few_shot_library")
    def test_empty_metrics(self, mock_get_lib):
        mock_get_lib.return_value = _fresh_library()
        optimizer = RoutingOptimizer()
        optimizer._query_recent_metrics = lambda since, limit=500: []

        result = optimizer.optimize(since=datetime.now(UTC) - timedelta(hours=1))
        assert isinstance(result, OptimizationResult)
        assert result.examples_added == 0
        assert result.total_metrics_analyzed == 0

    @patch("core.orchestrator.few_shot_library.get_few_shot_library")
    def test_adds_examples(self, mock_get_lib):
        lib = _fresh_library()
        mock_get_lib.return_value = lib
        initial_count = len(lib._examples)

        now = datetime.now(UTC)
        metrics = [
            _make_metric(
                timestamp=now - timedelta(minutes=5),
                tool_arguments_hash=f"hash_{i}",
                llm_tool_called="create",  # Phase 167: unified tool
            )
            for i in range(3)
        ]

        optimizer = RoutingOptimizer(max_bootstrapped_demos=4)
        optimizer._query_recent_metrics = lambda since, limit=500: metrics

        result = optimizer.optimize(since=now - timedelta(hours=1))
        assert result.examples_added > 0
        assert len(lib._examples) > initial_count

    @patch("core.orchestrator.few_shot_library.get_few_shot_library")
    def test_deduplicates(self, mock_get_lib):
        lib = _fresh_library()
        mock_get_lib.return_value = lib

        now = datetime.now(UTC)
        # Two metrics with the SAME tool_arguments_hash
        metrics = [
            _make_metric(
                timestamp=now - timedelta(minutes=5),
                tool_arguments_hash="same_hash",
            ),
            _make_metric(
                timestamp=now - timedelta(minutes=4),
                tool_arguments_hash="same_hash",
            ),
        ]

        optimizer = RoutingOptimizer(max_bootstrapped_demos=4)
        optimizer._query_recent_metrics = lambda since, limit=500: metrics

        result = optimizer.optimize(since=now - timedelta(hours=1))
        # Only 1 should be added despite 2 metrics with same hash
        assert result.examples_added == 1

    @patch("core.orchestrator.few_shot_library.get_few_shot_library")
    def test_respects_max_bootstrapped(self, mock_get_lib):
        lib = _fresh_library()
        mock_get_lib.return_value = lib

        now = datetime.now(UTC)
        metrics = [
            _make_metric(
                timestamp=now - timedelta(minutes=5),
                tool_arguments_hash=f"unique_{i}",
            )
            for i in range(10)
        ]

        optimizer = RoutingOptimizer(max_bootstrapped_demos=2)
        optimizer._query_recent_metrics = lambda since, limit=500: metrics

        result = optimizer.optimize(since=now - timedelta(hours=1))
        # Should never add more than max_bootstrapped_demos
        assert result.examples_added <= 2

    @patch("core.orchestrator.few_shot_library.get_few_shot_library")
    def test_evicts_oldest_bootstrapped(self, mock_get_lib):
        lib = _fresh_library()
        # Add extra examples beyond curated (8 curated + 5 bootstrapped = 13)
        for i in range(5):
            lib.add_from_metric(
                user_message=f"test {i}",
                tool_called="create",  # Phase 167: unified tool
                arguments={},
                category="agent_creation",
            )
        mock_get_lib.return_value = lib
        initial_total = len(lib._examples)  # 13

        now = datetime.now(UTC)
        metrics = [
            _make_metric(
                timestamp=now - timedelta(minutes=5),
                tool_arguments_hash=f"new_{i}",
            )
            for i in range(3)
        ]

        # max_total=12 means eviction should occur
        optimizer = RoutingOptimizer(
            max_bootstrapped_demos=10,
            max_total_demos=12,
        )
        optimizer._query_recent_metrics = lambda since, limit=500: metrics

        result = optimizer.optimize(since=now - timedelta(hours=1))
        assert result.examples_evicted > 0
        # Should respect max_total after eviction
        assert len(lib._examples) <= 12

# ---- Category map -----------------------------------------------------------

class TestCategoryMap:
    def test_known_tools(self):
        # Phase 167: "create" replaces "self_improve" and "create_tool"
        assert _CATEGORY_MAP["create"] == "agent_creation"
        assert _CATEGORY_MAP["modify_config"] == "config"

# ---- Singleton ---------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        import core.orchestrator.optimization_pipeline as mod

        mod._optimizer = None
        o1 = get_routing_optimizer()
        o2 = get_routing_optimizer()
        assert o1 is o2
        # Cleanup
        mod._optimizer = None
