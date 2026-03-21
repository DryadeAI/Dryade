"""
Unit tests for cost_tracker (core module, migrated from plugin in Phase 191).

Tests cover:
1. CostTracker record and aggregation
2. Cost calculation with static and prefix-based pricing
3. Summary generation
4. Records retrieval and limits
5. Global singleton and convenience functions
"""

from unittest.mock import patch

import pytest

@pytest.mark.unit
class TestCostTracker:
    """Tests for CostTracker class."""

    def test_init_empty(self):
        """Test CostTracker initializes with empty records."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        assert len(tracker.records) == 0

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_record_basic(self, mock_persist):
        """Test recording a basic cost entry."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        tracker.record(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            agent="test-agent",
        )
        assert len(tracker.records) == 1
        record = tracker.records[0]
        assert record.model == "gpt-4o"
        assert record.input_tokens == 1000
        assert record.output_tokens == 500
        assert record.agent == "test-agent"
        mock_persist.assert_called_once()

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    @patch.dict("sys.modules", {"litellm": None})
    def test_record_cost_calculation(self, mock_persist):
        """Test cost is calculated correctly from static pricing.

        Patches sys.modules["litellm"] to None so the tracker falls back to
        DEFAULT_COSTS. This prevents test_stream_llm.py's module-level
        MagicMock litellm injection from making model_cost.get() return a
        MagicMock instead of None/float.
        """
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        # gpt-4o: input=2.50/1M, output=10.00/1M
        tracker.record(model="gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
        record = tracker.records[0]
        assert record.cost_usd == pytest.approx(12.50, rel=1e-4)

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    @patch.dict("sys.modules", {"litellm": None})
    def test_record_prefix_cost_lookup(self, mock_persist):
        """Test prefix-based cost lookup for provider/model format.

        Patches sys.modules["litellm"] to None to prevent MagicMock litellm
        injection from contaminating the cost lookup fallback to DEFAULT_COSTS.
        """
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        tracker.record(model="ollama/llama3.1", input_tokens=1000, output_tokens=1000)
        record = tracker.records[0]
        # Ollama is free
        assert record.cost_usd == 0.0

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    @patch.dict("sys.modules", {"litellm": None})
    def test_record_unknown_model_defaults_free(self, mock_persist):
        """Test unknown model defaults to free pricing.

        Patches sys.modules["litellm"] to None to prevent MagicMock litellm
        injection from returning a truthy MagicMock for unknown models.
        """
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        tracker.record(model="completely-unknown-model", input_tokens=1000, output_tokens=1000)
        record = tracker.records[0]
        assert record.cost_usd == 0.0

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_get_summary_empty(self, mock_persist):
        """Test summary with no records."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        summary = tracker.get_summary()
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_input_tokens"] == 0
        assert summary["total_output_tokens"] == 0
        assert summary["by_agent"] == {}
        assert summary["by_model"] == {}

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_get_summary_with_records(self, mock_persist):
        """Test summary aggregation with multiple records."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        tracker.record(model="gpt-4o", input_tokens=1000, output_tokens=500, agent="agent-a")
        tracker.record(model="gpt-4o-mini", input_tokens=2000, output_tokens=1000, agent="agent-b")
        summary = tracker.get_summary()
        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500
        assert "agent-a" in summary["by_agent"]
        assert "agent-b" in summary["by_agent"]
        assert "gpt-4o" in summary["by_model"]
        assert "gpt-4o-mini" in summary["by_model"]
        assert summary["record_count"] == 2

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_get_records_limit(self, mock_persist):
        """Test records retrieval with limit."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        for i in range(10):
            tracker.record(model="gpt-4o", input_tokens=100, output_tokens=50, agent=f"agent-{i}")
        records = tracker.get_records(limit=3)
        assert len(records) == 3

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_clear(self, mock_persist):
        """Test clearing all records."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        tracker.record(model="gpt-4o", input_tokens=100, output_tokens=50)
        assert len(tracker.records) == 1
        tracker.clear()
        assert len(tracker.records) == 0

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_template_id_in_record(self, mock_persist):
        """Test template_id is tracked in records."""
        from core.cost_tracker.tracker import CostTracker

        tracker = CostTracker()
        tracker.record(
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            template_id=42,
            template_version_id=7,
        )
        record = tracker.records[0]
        assert record.template_id == 42
        assert record.template_version_id == 7

@pytest.mark.unit
class TestCostTrackerGlobals:
    """Tests for global singleton and convenience functions."""

    def test_get_cost_tracker_singleton(self):
        """Test get_cost_tracker returns same instance."""
        import core.cost_tracker.tracker as tracker_mod
        from core.cost_tracker.tracker import CostTracker, get_cost_tracker

        # Reset global for test isolation
        tracker_mod._cost_tracker = None
        t1 = get_cost_tracker()
        t2 = get_cost_tracker()
        assert t1 is t2
        assert isinstance(t1, CostTracker)
        # Clean up
        tracker_mod._cost_tracker = None

    @patch("core.cost_tracker.tracker.CostTracker._persist_to_db")
    def test_record_cost_convenience(self, mock_persist):
        """Test record_cost convenience function."""
        import core.cost_tracker.tracker as tracker_mod
        from core.cost_tracker.tracker import record_cost

        tracker_mod._cost_tracker = None
        record_cost(model="gpt-4o", input_tokens=100, output_tokens=50)
        tracker = tracker_mod._cost_tracker
        assert tracker is not None
        assert len(tracker.records) == 1
        # Clean up
        tracker_mod._cost_tracker = None

@pytest.mark.unit
class TestCostRecordItemModel:
    """Tests for CostRecordItem Pydantic model validation."""

    def test_costrecorditem_validates_from_dict(self):
        """CostRecordItem validates a dict matching DBCostRecord.to_dict() output."""
        from core.api.routes.cost_tracker import CostRecordItem

        data = {
            "id": 1,
            "timestamp": "2025-01-01T00:00:00+00:00",
            "model": "gpt-4o",
            "agent": "research_agent",
            "task_id": "task-001",
            "conversation_id": "conv-001",
            "user_id": "user-001",
            "input_tokens": 1000,
            "output_tokens": 200,
            "cost_usd": 0.05,
            "template_id": 42,
            "template_version_id": 7,
        }
        item = CostRecordItem.model_validate(data)
        assert item.id == 1
        assert item.model == "gpt-4o"
        assert item.task_id == "task-001"
        assert item.template_id == 42
        assert item.template_version_id == 7

    def test_costrecorditem_optional_fields_default_none(self):
        """Optional fields default to None when not provided."""
        from core.api.routes.cost_tracker import CostRecordItem

        data = {
            "id": 2,
            "timestamp": "2025-01-01T00:00:00+00:00",
            "model": "gpt-4o",
            "input_tokens": 500,
            "output_tokens": 100,
            "cost_usd": 0.02,
        }
        item = CostRecordItem.model_validate(data)
        assert item.agent is None
        assert item.task_id is None
        assert item.template_id is None
        assert item.template_version_id is None

    def test_costrecordsresponse_coerces_dicts_to_items(self):
        """CostRecordsResponse coerces list of dicts into CostRecordItem instances."""
        from core.api.routes.cost_tracker import CostRecordsResponse

        response = CostRecordsResponse.model_validate(
            {
                "items": [
                    {
                        "id": 1,
                        "timestamp": "2025-01-01T00:00:00+00:00",
                        "model": "gpt-4o",
                        "agent": "test",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cost_usd": 0.01,
                    }
                ],
                "total": 1,
                "has_more": False,
            }
        )
        assert len(response.items) == 1
        assert response.items[0].model == "gpt-4o"
        assert response.items[0].cost_usd == 0.01
