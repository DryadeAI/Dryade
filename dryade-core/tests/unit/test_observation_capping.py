"""Tests for ObservationHistory capping and compression behavior.

Validates ADR-002 Sub-Decision A: cap unbounded observation growth at
MAX_OBSERVATIONS=50, automatically compressing the oldest batch of 10
into a single aggregate summary when the cap is exceeded.
"""

from core.orchestrator.models import OrchestrationObservation
from core.orchestrator.observation import ObservationHistory

def make_obs(i: int, success: bool = True, agent: str = "test_agent") -> OrchestrationObservation:
    return OrchestrationObservation(
        agent_name=agent,
        task=f"task_{i}",
        result=f"result_{i}",
        success=success,
        duration_ms=100,
    )

class TestObservationCapping:
    """Tests for MAX_OBSERVATIONS cap and _compress_oldest()."""

    def test_cap_not_triggered_below_threshold(self):
        """Add 49 observations (below MAX_OBSERVATIONS=50). No compression."""
        h = ObservationHistory()
        for i in range(49):
            h.add(make_obs(i))

        total = len(h._older) + len(h._recent)
        assert total == 49

        # No compressed entries should exist
        compressed = [s for s in h._summaries if s.startswith("[COMPRESSED")]
        assert len(compressed) == 0

    def test_cap_triggers_compression_at_threshold(self):
        """Add 51 observations (exceeds cap). Compression should occur."""
        h = ObservationHistory()
        for i in range(51):
            h.add(make_obs(i))

        total = len(h._older) + len(h._recent)
        assert total < 51

        # At least one compressed entry should exist
        compressed = [s for s in h._summaries if s.startswith("[COMPRESSED")]
        assert len(compressed) >= 1

    def test_summaries_length_after_compression(self):
        """After compression, summaries can be longer than _older (aggregate entries)."""
        h = ObservationHistory()
        for i in range(60):
            h.add(make_obs(i))

        # summaries >= _older because aggregate entries add to summaries
        assert len(h._summaries) >= len(h._older)

        # format_for_llm() must work without errors (proves independent iteration)
        output = h.format_for_llm()
        assert isinstance(output, str)
        assert "<observations>" in output

    def test_compress_oldest_aggregates_correctly(self):
        """Manually test _compress_oldest() produces correct aggregate summary."""
        h = ObservationHistory()

        # Manually populate _older with 10 observations (7 success, 3 fail, agents: alpha, beta)
        for i in range(7):
            h._older.append(make_obs(i, success=True, agent="alpha"))
        for i in range(3):
            h._older.append(make_obs(i + 7, success=False, agent="beta"))

        # Add corresponding summaries
        h._summaries = [f"summary_{i}" for i in range(10)]

        h._compress_oldest()

        assert len(h._older) == 0
        assert len(h._summaries) == 1

        aggregate = h._summaries[0]
        assert "7 OK, 3 FAIL" in aggregate
        assert "agents: alpha, beta" in aggregate
        assert "[COMPRESSED 10 steps]" in aggregate

    def test_compress_oldest_noop_below_batch_size(self):
        """_compress_oldest() is a no-op when _older has fewer entries than batch_size."""
        h = ObservationHistory()

        h._older = [make_obs(i) for i in range(5)]
        h._summaries = [f"summary_{i}" for i in range(5)]

        original_older_len = len(h._older)
        original_summaries_len = len(h._summaries)

        h._compress_oldest(batch_size=10)

        assert len(h._older) == original_older_len
        assert len(h._summaries) == original_summaries_len

    def test_format_for_llm_after_compression(self):
        """format_for_llm() includes [COMPRESSED entries in history section."""
        h = ObservationHistory()
        for i in range(55):
            h.add(make_obs(i))

        output = h.format_for_llm()

        assert "<observations>" in output
        assert "<facts>" in output
        assert "<recent_observations>" in output
        assert "<history>" in output
        assert "[COMPRESSED" in output

    def test_multiple_compressions(self):
        """Multiple compressions occur when observations far exceed the cap.

        Use a lower MAX_OBSERVATIONS (20) so that 60 additions trigger
        multiple compression cycles. Each compression consumes the previous
        aggregate entry (since it sits at _summaries[0] and is included in
        the next batch_size slice), so only 1 [COMPRESSED entry is visible
        at a time. We verify multiple compressions by counting them as they
        happen and by checking total stays bounded.
        """
        h = ObservationHistory()
        h.MAX_OBSERVATIONS = 20  # Lower threshold to force multiple compressions

        compression_count = 0
        for i in range(60):
            old_len = len(h._older)
            h.add(make_obs(i))
            # Detect compression: _older shrank (batch removed)
            if len(h._older) < old_len:
                compression_count += 1

        total = len(h._older) + len(h._recent)
        assert total <= 20

        # Multiple compressions occurred
        assert compression_count >= 2, f"Expected >= 2 compressions, got {compression_count}"

        # At least one [COMPRESSED entry visible in summaries
        compressed = [s for s in h._summaries if s.startswith("[COMPRESSED")]
        assert len(compressed) >= 1

        # format_for_llm() still works
        output = h.format_for_llm()
        assert isinstance(output, str)
        assert "<observations>" in output
        assert "[COMPRESSED" in output

    def test_facts_preserved_across_compression(self):
        """Facts extracted during add() survive compression (extracted before compression)."""
        h = ObservationHistory()

        # Add observations where each has a unique result
        for i in range(55):
            h.add(make_obs(i))

        # Facts should still be present (capped at FACTS_MAX_COUNT=20 but non-empty)
        facts = h.get_facts()
        assert len(facts) > 0
        assert len(facts) <= h.FACTS_MAX_COUNT
