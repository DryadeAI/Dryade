"""Tests for stateful escalation -- round-trip serialization and backward compat.

Validates ADR-002 Sub-Decision D: ObservationHistory serialization,
PendingEscalation new fields, OrchestrationResult observation_history_data,
and the full escalation-retry pipeline.
"""

import json

from core.orchestrator.escalation import (
    EscalationAction,
    EscalationActionType,
    PendingEscalation,
)
from core.orchestrator.models import (
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationResult,
    OrchestrationState,
)
from core.orchestrator.observation import ObservationHistory

def make_obs(i: int, success: bool = True, agent: str = "agent_a") -> OrchestrationObservation:
    """Create a test observation with distinctive content."""
    return OrchestrationObservation(
        agent_name=agent,
        task=f"task_{i}",
        result=f"result_{i} with /path/to/file_{i}.txt",
        success=success,
        duration_ms=100 + i,
    )

def _make_action() -> EscalationAction:
    """Create a minimal EscalationAction for test PendingEscalation instances."""
    return EscalationAction(
        action_type=EscalationActionType.UPDATE_MCP_CONFIG,
        description="test action",
    )

# -------------------------------------------------------------------------
# ObservationHistory serialization tests
# -------------------------------------------------------------------------

class TestObservationHistoryRoundTrip:
    """Tests for ObservationHistory.to_dict() / from_dict() round-trip."""

    def test_observation_history_round_trip(self):
        """Populated history survives to_dict/from_dict with identical state."""
        history = ObservationHistory()
        for i in range(10):
            history.add(make_obs(i, success=(i % 3 != 0), agent=f"agent_{i % 2}"))

        serialized = history.to_dict()
        restored = ObservationHistory.from_dict(serialized)

        # Internal lists match
        assert list(restored._recent) == list(history._recent)
        assert restored._older == history._older
        assert restored._summaries == history._summaries
        assert restored._facts == history._facts

        # format_for_llm output is identical
        assert restored.format_for_llm() == history.format_for_llm()

    def test_observation_history_empty_round_trip(self):
        """Empty history survives round-trip and produces placeholder output."""
        history = ObservationHistory()

        serialized = history.to_dict()
        restored = ObservationHistory.from_dict(serialized)

        assert list(restored._recent) == []
        assert restored._older == []
        assert restored._summaries == []
        assert restored._facts == []
        assert restored.format_for_llm() == "<observations>No actions taken yet</observations>"

    def test_observation_history_to_dict_is_json_safe(self):
        """Serialized dict survives JSON encode/decode round-trip."""
        history = ObservationHistory()
        for i in range(5):
            history.add(make_obs(i))

        serialized = history.to_dict()

        # Must survive JSON round-trip
        json_str = json.dumps(serialized)
        parsed = json.loads(json_str)
        restored = ObservationHistory.from_dict(parsed)

        assert restored.format_for_llm() == history.format_for_llm()
        assert restored._facts == history._facts

# -------------------------------------------------------------------------
# PendingEscalation backward compatibility tests
# -------------------------------------------------------------------------

class TestPendingEscalationBackwardCompat:
    """Tests for PendingEscalation new fields with backward compatibility."""

    def test_pending_escalation_backward_compat(self):
        """PendingEscalation without new fields defaults to None."""
        escalation = PendingEscalation(
            conversation_id="conv-1",
            original_goal="do something",
            action=_make_action(),
            question="How should I proceed?",
        )

        assert escalation.orchestration_state is None
        assert escalation.observation_history is None

    def test_pending_escalation_with_state(self):
        """PendingEscalation accepts and stores new fields."""
        state_data = {
            "execution_id": "12345678-1234-1234-1234-123456789abc",
            "started_at": "2026-01-01T00:00:00",
            "mode": "adaptive",
            "actions_taken": 5,
            "memory_enabled": True,
            "reasoning_visibility": "summary",
        }
        history_data = {
            "recent": [],
            "older": [],
            "summaries": ["[agent_a] task_0 -> OK"],
            "facts": ["fact1", "fact2"],
        }

        escalation = PendingEscalation(
            conversation_id="conv-1",
            original_goal="do something",
            action=_make_action(),
            question="How?",
            orchestration_state=state_data,
            observation_history=history_data,
        )

        assert escalation.orchestration_state == state_data
        assert escalation.observation_history == history_data
        assert escalation.observation_history["facts"] == ["fact1", "fact2"]

# -------------------------------------------------------------------------
# OrchestrationResult observation_history_data test
# -------------------------------------------------------------------------

class TestOrchestrationResultHistoryData:
    """Tests for OrchestrationResult.observation_history_data field."""

    def test_orchestration_result_carries_history_data(self):
        """OrchestrationResult stores and returns observation_history_data."""
        history_data = {
            "recent": [],
            "older": [],
            "summaries": [],
            "facts": ["fact1"],
        }
        result = OrchestrationResult(
            success=False,
            observation_history_data=history_data,
        )

        assert result.observation_history_data is not None
        assert result.observation_history_data["facts"] == ["fact1"]

    def test_orchestration_result_default_none(self):
        """OrchestrationResult defaults observation_history_data to None."""
        result = OrchestrationResult(success=True)
        assert result.observation_history_data is None

# -------------------------------------------------------------------------
# Integration-style round-trip test
# -------------------------------------------------------------------------

class TestFullEscalationRoundTrip:
    """End-to-end test simulating the full escalation pipeline."""

    def test_full_escalation_round_trip(self):
        """Full pipeline: serialize -> PendingEscalation -> extract -> restore."""
        # 1. Create ObservationHistory with observations
        history = ObservationHistory()
        for i in range(5):
            history.add(make_obs(i, success=(i != 2)))

        # 2. Create OrchestrationState with specific values
        state = OrchestrationState(
            mode=OrchestrationMode.ADAPTIVE,
            actions_taken=5,
            memory_enabled=True,
            reasoning_visibility="detailed",
        )

        # 3. Serialize both
        obs_dict = history.to_dict()
        state_dict = state.model_dump(mode="json")

        # 4. Create PendingEscalation with both dicts
        escalation = PendingEscalation(
            conversation_id="conv-test",
            original_goal="analyze document",
            action=_make_action(),
            question="How?",
            orchestration_state=state_dict,
            observation_history=obs_dict,
        )

        # 5. Simulate router extracting
        prior_state = escalation.orchestration_state
        prior_history = escalation.observation_history

        # 6. Restore
        restored_state = OrchestrationState(**prior_state)
        restored_history = ObservationHistory.from_dict(prior_history)

        # 7. Verify restored state
        assert restored_state.actions_taken == 5
        assert restored_state.mode == OrchestrationMode.ADAPTIVE
        assert restored_state.reasoning_visibility == "detailed"

        # 8. Verify restored history
        assert restored_history._facts == history._facts
        assert restored_history._summaries == history._summaries
        assert restored_history.format_for_llm() == history.format_for_llm()

    def test_retry_metadata_with_none_state(self):
        """None state/history in PendingEscalation -> fresh state on retry."""
        escalation = PendingEscalation(
            conversation_id="conv-none",
            original_goal="goal",
            action=_make_action(),
            question="How?",
            orchestration_state=None,
            observation_history=None,
        )

        # Simulate router building retry_metadata
        retry_metadata = {
            **(escalation.original_context or {}),
            "_prior_observations": escalation.observations,
            "_prior_state": escalation.orchestration_state,
            "_prior_observation_history": escalation.observation_history,
        }

        assert retry_metadata["_prior_state"] is None
        assert retry_metadata["_prior_observation_history"] is None

        # Simulate orchestrator deserialization path
        prior_state_dict = retry_metadata.get("_prior_state")
        if prior_state_dict:
            state = OrchestrationState(**prior_state_dict)
        else:
            state = OrchestrationState(
                mode=OrchestrationMode.ADAPTIVE,
                memory_enabled=True,
                reasoning_visibility="summary",
            )

        prior_history_dict = retry_metadata.get("_prior_observation_history")
        if prior_history_dict:
            observation_history = ObservationHistory.from_dict(prior_history_dict)
        else:
            observation_history = ObservationHistory()

        # Fresh state created
        assert state.actions_taken == 0
        assert state.mode == OrchestrationMode.ADAPTIVE

        # Fresh empty history
        assert (
            observation_history.format_for_llm()
            == "<observations>No actions taken yet</observations>"
        )
