"""Unit tests for orchestrator context, artifact store, and complexity estimator.

Tests cover:
- OrchestrationContext: scoped state, artifact pass-through, plan tracking,
  memory integration, serialization
- ArtifactStore: memory vs disk storage, retrieval, cleanup
- ComplexityEstimator.estimate(): REACT/PLAN/DEFER classification
- ComplexityEstimator.classify(): INSTANT/SIMPLE/COMPLEX tier classification
"""

from unittest.mock import MagicMock

from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework
from core.orchestrator.complexity import (
    ComplexityEstimator,
    PlanningMode,
)
from core.orchestrator.context import (
    MAX_MEMORY_BYTES,
    ArtifactStore,
    OrchestrationContext,
)
from core.orchestrator.models import OrchestrationObservation, Tier

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(name: str, capabilities: list[str] | None = None) -> AgentCard:
    caps = [AgentCapability(name=c, description=f"does {c}") for c in (capabilities or [])]
    return AgentCard(
        name=name,
        description=f"Agent {name}",
        version="1.0",
        framework=AgentFramework.MCP,
        capabilities=caps,
    )

# ---------------------------------------------------------------------------
# ArtifactStore
# ---------------------------------------------------------------------------

class TestArtifactStore:
    def test_small_artifact_in_memory(self):
        store = ArtifactStore()
        try:
            art = store.add("readme.txt", b"hello world", "text/plain", "agent1")
            assert art.data == b"hello world"
            assert art.path is None
            assert art.size_bytes == 11
        finally:
            store.cleanup()

    def test_large_artifact_on_disk(self, tmp_path):
        store = ArtifactStore(temp_dir=tmp_path)
        big_data = b"x" * (MAX_MEMORY_BYTES + 1)
        art = store.add("big.bin", big_data, "application/octet-stream", "agent1")
        assert art.data is None
        assert art.path is not None
        assert art.path.exists()
        store.cleanup()

    def test_get_and_get_data(self):
        store = ArtifactStore()
        try:
            store.add("file.txt", b"content", "text/plain", "agent1")
            art = store.get("file.txt")
            assert art is not None
            assert art.name == "file.txt"
            data = store.get_data("file.txt")
            assert data == b"content"
        finally:
            store.cleanup()

    def test_get_missing_returns_none(self):
        store = ArtifactStore()
        try:
            assert store.get("nope") is None
            assert store.get_data("nope") is None
        finally:
            store.cleanup()

    def test_list_artifacts(self):
        store = ArtifactStore()
        try:
            store.add("a.txt", b"a", "text/plain", "x")
            store.add("b.txt", b"b", "text/plain", "x")
            names = store.list_artifacts()
            assert set(names) == {"a.txt", "b.txt"}
        finally:
            store.cleanup()

    def test_disk_artifact_read_back(self, tmp_path):
        store = ArtifactStore(temp_dir=tmp_path)
        big_data = b"y" * (MAX_MEMORY_BYTES + 100)
        store.add("big.bin", big_data, "application/octet-stream", "agent1")
        retrieved = store.get_data("big.bin")
        assert retrieved == big_data

    def test_cleanup_removes_owned_temp_dir(self):
        store = ArtifactStore()  # Creates its own temp dir
        temp = store._temp_dir
        assert temp.exists()
        store.cleanup()
        assert not temp.exists()

    def test_cleanup_does_not_remove_external_dir(self, tmp_path):
        store = ArtifactStore(temp_dir=tmp_path)
        store.cleanup()
        # External dir should still exist
        assert tmp_path.exists()

# ---------------------------------------------------------------------------
# OrchestrationContext
# ---------------------------------------------------------------------------

class TestOrchestrationContext:
    def test_scoped_state_step_priority(self):
        ctx = OrchestrationContext()
        ctx.set("key", "orch_val", scope="orchestration")
        ctx.set("key", "step_val", scope="step")
        assert ctx.get("key") == "step_val"

    def test_clear_step_scope(self):
        ctx = OrchestrationContext()
        ctx.set("key", "step_val", scope="step")
        ctx.set("key", "orch_val", scope="orchestration")
        ctx.clear_step_scope()
        assert ctx.get("key") == "orch_val"

    def test_get_with_default(self):
        ctx = OrchestrationContext()
        assert ctx.get("missing", "default") == "default"

    def test_initial_state(self):
        ctx = OrchestrationContext(initial_state={"foo": "bar"})
        assert ctx.get("foo") == "bar"

    def test_artifact_pass_through(self):
        ctx = OrchestrationContext()
        art = ctx.add_artifact("test.txt", b"data", "text/plain", "agent1")
        assert art.name == "test.txt"
        assert ctx.get_artifact("test.txt") is not None
        assert ctx.get_artifact_data("test.txt") == b"data"
        ctx.cleanup()

    def test_observation_history(self):
        ctx = OrchestrationContext()
        obs = OrchestrationObservation(
            agent_name="agent1",
            task="do something",
            result="done",
            success=True,
            duration_ms=100,
        )
        ctx.add_observation(obs)
        all_obs = ctx.get_observations()
        assert len(all_obs) == 1
        assert all_obs[0].agent_name == "agent1"

    def test_format_history_for_llm_empty(self):
        ctx = OrchestrationContext()
        fmt = ctx.format_history_for_llm()
        assert "No actions taken yet" in fmt

    def test_get_facts_empty(self):
        ctx = OrchestrationContext()
        assert ctx.get_facts() == []

    def test_plan_tracking(self):
        ctx = OrchestrationContext()
        assert ctx.get_plan() is None
        mock_plan = MagicMock()
        ctx.set_plan(mock_plan)
        assert ctx.get_plan() is mock_plan

    def test_to_dict_merges_scopes(self):
        ctx = OrchestrationContext(initial_state={"a": 1})
        ctx.set("b", 2, scope="step")
        d = ctx.to_dict()
        assert d["a"] == 1
        assert d["b"] == 2
        assert "artifacts" in d
        assert "facts" in d

    def test_from_dict_roundtrip(self):
        ctx = OrchestrationContext.from_dict({"x": 42})
        assert ctx.get("x") == 42

# ---------------------------------------------------------------------------
# ComplexityEstimator.estimate()
# ---------------------------------------------------------------------------

class TestComplexityEstimatorEstimate:
    def setup_method(self):
        self.estimator = ComplexityEstimator()
        self.agents = [_make_agent("agent1"), _make_agent("agent2")]

    def test_question_returns_react(self):
        d = self.estimator.estimate("What is the weather?", self.agents)
        assert d.mode == PlanningMode.REACT
        assert d.confidence >= 0.8

    def test_single_action_returns_react(self):
        d = self.estimator.estimate("List all users", self.agents)
        assert d.mode == PlanningMode.REACT

    def test_multi_step_signals_return_plan(self):
        d = self.estimator.estimate(
            "First analyze the code, and then deploy it, followed by running tests",
            self.agents,
        )
        assert d.mode == PlanningMode.PLAN

    def test_conditional_logic_returns_plan(self):
        d = self.estimator.estimate("If the tests pass then deploy to production", self.agents)
        assert d.mode == PlanningMode.PLAN

    def test_long_goal_returns_plan(self):
        long_goal = " ".join(["word"] * 120)
        d = self.estimator.estimate(long_goal, self.agents)
        assert d.mode == PlanningMode.PLAN

    def test_short_goal_no_signals_returns_react(self):
        d = self.estimator.estimate("hello there", self.agents)
        assert d.mode == PlanningMode.REACT

    def test_ambiguous_returns_defer(self):
        # Single multi-step signal + moderate length
        d = self.estimator.estimate(
            "after that we should check " + " ".join(["context"] * 25),
            self.agents,
        )
        assert d.mode == PlanningMode.DEFER

    def test_multiple_agent_mentions_returns_plan(self):
        d = self.estimator.estimate("use agent1 to read and agent2 to write", self.agents)
        assert d.mode == PlanningMode.PLAN

    def test_comma_separated_actions_returns_plan(self):
        d = self.estimator.estimate("analyze repo, find issues, fix them, run tests", self.agents)
        assert d.mode == PlanningMode.PLAN

# ---------------------------------------------------------------------------
# ComplexityEstimator.classify() - tier classification
# ---------------------------------------------------------------------------

class TestComplexityEstimatorClassify:
    def setup_method(self):
        self.estimator = ComplexityEstimator()
        self.agents = [
            _make_agent("filesystem", capabilities=["read_file", "write_file"]),
            _make_agent("search", capabilities=["web_search"]),
        ]

    def test_greeting_instant(self):
        d = self.estimator.classify("Hello!", self.agents)
        assert d.tier == Tier.INSTANT
        assert d.confidence >= 0.9

    def test_meta_question_instant(self):
        d = self.estimator.classify("What can you do?", self.agents)
        assert d.tier == Tier.INSTANT

    def test_short_factual_question_instant(self):
        d = self.estimator.classify("Who wrote Python?", self.agents)
        assert d.tier == Tier.INSTANT

    def test_agent_plus_tool_match_simple(self):
        d = self.estimator.classify("use filesystem to read_file config.json", self.agents)
        assert d.tier == Tier.SIMPLE
        assert d.confidence >= 0.9
        assert d.target_agent is not None
        assert d.target_tool is not None

    def test_agent_name_match_simple(self):
        d = self.estimator.classify("ask search for recent news", self.agents)
        assert d.tier == Tier.SIMPLE
        assert d.target_agent is not None

    def test_tool_name_match_simple(self):
        d = self.estimator.classify("web_search for Python tutorials", self.agents)
        assert d.tier == Tier.SIMPLE
        assert d.target_tool == "web_search"

    def test_complex_fallback(self):
        d = self.estimator.classify(
            "First analyze the repo then deploy to staging",
            [_make_agent("ci_agent")],  # no match in message
        )
        assert d.tier == Tier.COMPLEX
        assert d.sub_mode is not None

    def test_greeting_with_action_verb_not_instant(self):
        """Greeting + action verb should not be INSTANT."""
        d = self.estimator.classify("hello, list all users", self.agents)
        # Has action verb "list" -> not INSTANT
        assert d.tier != Tier.INSTANT
