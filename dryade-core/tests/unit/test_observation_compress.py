"""Tests for ObservationHistory.compress_aggressive() and context_size_chars().

TDD RED phase: All tests should fail with AttributeError until the
methods are implemented on ObservationHistory.

Tests cover:
- context_size_chars: accuracy, growth, empty case
- compress_aggressive: size reduction, recent preservation, fact preservation,
  edge cases (empty, minimal, multiple calls), format validity
"""

from core.orchestrator.models import OrchestrationObservation
from core.orchestrator.observation import ObservationHistory

def _make_obs(
    agent_name: str = "test_agent",
    task: str = "do something",
    success: bool = True,
    result: str = "ok",
) -> OrchestrationObservation:
    """Helper to create OrchestrationObservation instances for testing."""
    return OrchestrationObservation(
        agent_name=agent_name,
        task=task,
        result=result,
        success=success,
        duration_ms=100,
    )

class TestContextSizeChars:
    """Tests for context_size_chars() method."""

    def test_context_size_chars_empty(self):
        """New ObservationHistory returns small positive int (empty placeholder XML)."""
        h = ObservationHistory()
        size = h.context_size_chars()
        assert isinstance(size, int)
        assert size > 0
        # The empty placeholder is short XML
        assert size < 200

    def test_context_size_chars_with_observations(self):
        """After adding 5 observations, context_size_chars() == len(format_for_llm())."""
        h = ObservationHistory()
        for i in range(5):
            h.add(_make_obs(agent_name=f"agent_{i}", task=f"task_{i}", result=f"result_{i}"))

        size = h.context_size_chars()
        expected = len(h.format_for_llm())
        assert size == expected

    def test_context_size_chars_grows_with_more_data(self):
        """Size after 10 observations > size after 5 observations."""
        h = ObservationHistory()
        for i in range(5):
            h.add(_make_obs(agent_name=f"agent_{i}", task=f"task_{i}"))

        size_after_5 = h.context_size_chars()

        for i in range(5, 10):
            h.add(_make_obs(agent_name=f"agent_{i}", task=f"task_{i}"))

        size_after_10 = h.context_size_chars()
        assert size_after_10 > size_after_5

class TestCompressAggressive:
    """Tests for compress_aggressive() method."""

    def test_compress_aggressive_reduces_size(self):
        """After 15 observations, compress_aggressive reduces size to <60% of original."""
        h = ObservationHistory()
        for i in range(15):
            h.add(
                _make_obs(
                    agent_name=f"agent_{i % 3}",
                    task=f"task_{i} with some longer description for size",
                    result=f"result_{i} " * 20,
                )
            )

        original_size = h.context_size_chars()
        h.compress_aggressive(target_reduction=0.5)
        compressed_size = h.context_size_chars()

        assert compressed_size < original_size * 0.6, (
            f"Expected <60% of original ({original_size}), got {compressed_size} "
            f"({compressed_size / original_size:.1%})"
        )

    def test_compress_aggressive_preserves_recent(self):
        """After compress_aggressive, at least 1 recent observation is accessible."""
        h = ObservationHistory()
        for i in range(15):
            h.add(_make_obs(agent_name=f"agent_{i}", task=f"task_{i}"))

        h.compress_aggressive()

        all_obs = h.get_all_observations()
        assert len(all_obs) >= 1, "Must preserve at least 1 observation after aggressive compress"

    def test_compress_aggressive_preserves_facts(self):
        """Facts list is non-empty after compress_aggressive (not wiped entirely)."""
        h = ObservationHistory()
        for i in range(15):
            h.add(
                _make_obs(
                    agent_name=f"agent_{i}",
                    task=f"task_{i}",
                    result=f"Created /tmp/file_{i}.txt successfully",
                )
            )

        # Verify we had facts before
        assert len(h.get_facts()) > 0

        h.compress_aggressive()

        facts = h.get_facts()
        assert len(facts) > 0, "Facts must not be completely wiped by compress_aggressive"

    def test_compress_aggressive_on_empty_history(self):
        """compress_aggressive on empty history is a no-op (no crash)."""
        h = ObservationHistory()
        h.compress_aggressive()
        # Should not raise, and history should still be empty
        assert h.context_size_chars() > 0  # placeholder XML

    def test_compress_aggressive_on_minimal_history(self):
        """compress_aggressive with 1 observation preserves that observation."""
        h = ObservationHistory()
        h.add(_make_obs(agent_name="solo", task="only task"))

        h.compress_aggressive()

        all_obs = h.get_all_observations()
        assert len(all_obs) == 1
        assert all_obs[0].agent_name == "solo"

    def test_compress_aggressive_multiple_calls(self):
        """Calling compress_aggressive twice in a row doesn't crash and preserves last obs."""
        h = ObservationHistory()
        for i in range(15):
            h.add(_make_obs(agent_name=f"agent_{i}", task=f"task_{i}"))

        h.compress_aggressive()
        h.compress_aggressive()

        all_obs = h.get_all_observations()
        assert len(all_obs) >= 1, "Must still have at least 1 observation after double compress"

    def test_compress_aggressive_format_for_llm_still_valid(self):
        """After compress_aggressive, format_for_llm() returns valid XML with <observations> root."""
        h = ObservationHistory()
        for i in range(15):
            h.add(_make_obs(agent_name=f"agent_{i}", task=f"task_{i}"))

        h.compress_aggressive()

        output = h.format_for_llm()
        assert output.startswith("<observations>")
        assert output.rstrip().endswith("</observations>")
        assert "<facts>" in output
        assert "<recent_observations>" in output
        assert "<history>" in output
