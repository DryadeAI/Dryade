"""Unit tests for autonomous execution models (Phase 67.1).

Tests:
- ActionType enum values and behavior
- CapabilityNegotiationRequest model validation
- SkillCreationRequest model validation
- CapabilityNegotiationResult model validation
- Thought model with extended fields
- ExecutionState duration property
"""

import pytest
from pydantic import ValidationError

from core.autonomous.models import (
    ActionType,
    CapabilityNegotiationRequest,
    CapabilityNegotiationResult,
    ExecutionResult,
    ExecutionState,
    GoalResult,
    Observation,
    SkillCreationRequest,
    Thought,
)

class TestActionType:
    """Tests for ActionType enum."""

    def test_action_type_values(self):
        """Test all ActionType values exist."""
        assert ActionType.EXECUTE_SKILL.value == "execute_skill"
        assert ActionType.NEGOTIATE_CAPABILITY.value == "negotiate_capability"
        assert ActionType.CREATE_SKILL.value == "create_skill"
        assert ActionType.ASK_HUMAN.value == "ask_human"

    def test_action_type_is_string_enum(self):
        """Test ActionType is a string enum for JSON serialization."""
        assert isinstance(ActionType.EXECUTE_SKILL, str)
        assert ActionType.EXECUTE_SKILL == "execute_skill"

    def test_action_type_from_string(self):
        """Test creating ActionType from string."""
        assert ActionType("execute_skill") == ActionType.EXECUTE_SKILL
        assert ActionType("negotiate_capability") == ActionType.NEGOTIATE_CAPABILITY
        assert ActionType("create_skill") == ActionType.CREATE_SKILL
        assert ActionType("ask_human") == ActionType.ASK_HUMAN

    def test_action_type_invalid_value(self):
        """Test invalid ActionType value raises error."""
        with pytest.raises(ValueError):
            ActionType("invalid_action")

    def test_action_type_count(self):
        """Test we have exactly 4 action types."""
        assert len(ActionType) == 4

class TestCapabilityNegotiationRequest:
    """Tests for CapabilityNegotiationRequest model."""

    def test_minimal_request(self):
        """Test creating request with minimal fields."""
        request = CapabilityNegotiationRequest(request="filesystem access")
        assert request.request == "filesystem access"
        assert request.user_prefs == {"auto_accept": False, "accept_all_session": False}

    def test_request_with_custom_prefs(self):
        """Test request with custom user preferences."""
        request = CapabilityNegotiationRequest(
            request="database access",
            user_prefs={"auto_accept": True, "accept_all_session": True},
        )
        assert request.user_prefs["auto_accept"] is True
        assert request.user_prefs["accept_all_session"] is True

    def test_request_serialization(self):
        """Test request serializes to JSON correctly."""
        request = CapabilityNegotiationRequest(request="api access")
        data = request.model_dump()
        assert data["request"] == "api access"
        assert "user_prefs" in data

    def test_request_empty_string_valid(self):
        """Test that empty string is technically valid (no min length)."""
        request = CapabilityNegotiationRequest(request="")
        assert request.request == ""

class TestSkillCreationRequest:
    """Tests for SkillCreationRequest model."""

    def test_full_request(self):
        """Test creating request with all fields."""
        request = SkillCreationRequest(
            skill_name="excel-analyzer",
            description="Analyze Excel files",
            goal="Extract data from spreadsheets",
            inputs_schema={"file_path": {"type": "string"}},
        )
        assert request.skill_name == "excel-analyzer"
        assert request.description == "Analyze Excel files"
        assert request.goal == "Extract data from spreadsheets"
        assert request.inputs_schema == {"file_path": {"type": "string"}}

    def test_request_without_schema(self):
        """Test request without inputs schema."""
        request = SkillCreationRequest(
            skill_name="simple-skill",
            description="A simple skill",
            goal="Do something simple",
        )
        assert request.inputs_schema is None

    def test_request_requires_all_fields(self):
        """Test that skill_name, description, and goal are required."""
        with pytest.raises(ValidationError):
            SkillCreationRequest(skill_name="test")  # Missing description and goal

        with pytest.raises(ValidationError):
            SkillCreationRequest(skill_name="test", description="desc")  # Missing goal

class TestCapabilityNegotiationResult:
    """Tests for CapabilityNegotiationResult model."""

    def test_auto_bound_result(self):
        """Test auto_bound result."""
        result = CapabilityNegotiationResult(
            status="auto_bound",
            bound_tools=["tool1", "tool2"],
            offer_generate=False,
        )
        assert result.status == "auto_bound"
        assert len(result.bound_tools) == 2
        assert result.offer_generate is False

    def test_no_match_result(self):
        """Test no_match result with offer to generate."""
        result = CapabilityNegotiationResult(
            status="no_match",
            bound_tools=[],
            offer_generate=True,
        )
        assert result.status == "no_match"
        assert len(result.bound_tools) == 0
        assert result.offer_generate is True

    def test_degraded_result(self):
        """Test degraded capability result."""
        result = CapabilityNegotiationResult(
            status="degraded",
            bound_tools=["fallback-tool"],
            offer_generate=True,
        )
        assert result.status == "degraded"
        assert result.bound_tools == ["fallback-tool"]

    def test_default_values(self):
        """Test default values for optional fields."""
        result = CapabilityNegotiationResult(status="pending_approval")
        assert result.bound_tools == []
        assert result.offer_generate is False

class TestThoughtExtended:
    """Tests for extended Thought model with action_type fields."""

    def test_basic_thought(self):
        """Test basic thought without new fields."""
        thought = Thought(
            reasoning="I should do X",
            confidence=0.8,
        )
        assert thought.reasoning == "I should do X"
        assert thought.confidence == 0.8
        assert thought.action_type is None
        assert thought.capability_request is None
        assert thought.skill_creation_goal is None

    def test_execute_skill_thought(self):
        """Test thought with EXECUTE_SKILL action type."""
        thought = Thought(
            reasoning="I'll use the data-processor skill",
            action_type=ActionType.EXECUTE_SKILL,
            skill_name="data-processor",
            inputs={"data": [1, 2, 3]},
            confidence=0.9,
        )
        assert thought.action_type == ActionType.EXECUTE_SKILL
        assert thought.skill_name == "data-processor"

    def test_negotiate_capability_thought(self):
        """Test thought with NEGOTIATE_CAPABILITY action type."""
        thought = Thought(
            reasoning="I need database access",
            action_type=ActionType.NEGOTIATE_CAPABILITY,
            capability_request="database read/write operations",
            confidence=0.85,
        )
        assert thought.action_type == ActionType.NEGOTIATE_CAPABILITY
        assert thought.capability_request == "database read/write operations"

    def test_create_skill_thought(self):
        """Test thought with CREATE_SKILL action type."""
        thought = Thought(
            reasoning="No Excel skill exists, I'll create one",
            action_type=ActionType.CREATE_SKILL,
            skill_creation_goal="Parse and analyze Excel spreadsheets",
            inputs={"skill_name": "excel-parser"},
            confidence=0.75,
        )
        assert thought.action_type == ActionType.CREATE_SKILL
        assert thought.skill_creation_goal == "Parse and analyze Excel spreadsheets"
        assert thought.inputs.get("skill_name") == "excel-parser"

    def test_ask_human_thought(self):
        """Test thought with ASK_HUMAN action type."""
        thought = Thought(
            reasoning="I need clarification on the data format",
            action_type=ActionType.ASK_HUMAN,
            confidence=0.5,
        )
        assert thought.action_type == ActionType.ASK_HUMAN

    def test_final_thought(self):
        """Test final thought with answer."""
        thought = Thought(
            reasoning="Task complete",
            confidence=1.0,
            is_final=True,
            answer="Successfully processed all files",
        )
        assert thought.is_final is True
        assert thought.answer == "Successfully processed all files"

    def test_confidence_validation(self):
        """Test confidence must be between 0 and 1."""
        with pytest.raises(ValidationError):
            Thought(reasoning="test", confidence=1.5)

        with pytest.raises(ValidationError):
            Thought(reasoning="test", confidence=-0.1)

    def test_thought_serialization(self):
        """Test thought serializes correctly."""
        thought = Thought(
            reasoning="test",
            action_type=ActionType.CREATE_SKILL,
            skill_creation_goal="create something",
            confidence=0.9,
        )
        data = thought.model_dump()
        assert data["action_type"] == "create_skill"
        assert data["skill_creation_goal"] == "create something"

class TestExecutionState:
    """Tests for ExecutionState model."""

    def test_default_values(self):
        """Test default values are set correctly."""
        state = ExecutionState()
        assert state.tokens_used == 0
        assert state.cost_usd == 0.0
        assert state.actions_taken == 0
        assert state.tool_calls == 0
        assert state.execution_id is not None
        assert state.started_at is not None

    def test_duration_property(self):
        """Test duration_seconds property calculates correctly."""
        state = ExecutionState()
        # Duration should be very small but positive
        assert state.duration_seconds >= 0

    def test_state_mutation(self):
        """Test state can be mutated during execution."""
        state = ExecutionState()
        state.tokens_used = 100
        state.cost_usd = 0.001
        state.actions_taken = 5
        state.tool_calls = 3

        assert state.tokens_used == 100
        assert state.cost_usd == 0.001
        assert state.actions_taken == 5
        assert state.tool_calls == 3

    def test_unique_execution_ids(self):
        """Test each state gets a unique execution ID."""
        state1 = ExecutionState()
        state2 = ExecutionState()
        assert state1.execution_id != state2.execution_id

class TestObservation:
    """Tests for Observation model."""

    def test_successful_observation(self):
        """Test successful skill execution observation."""
        obs = Observation(
            skill_name="test-skill",
            inputs={"param": "value"},
            result={"output": "data"},
            success=True,
            duration_ms=150,
        )
        assert obs.success is True
        assert obs.error is None
        assert obs.duration_ms == 150

    def test_failed_observation(self):
        """Test failed skill execution observation."""
        obs = Observation(
            skill_name="test-skill",
            inputs={},
            result=None,
            success=False,
            error="Skill not found",
        )
        assert obs.success is False
        assert obs.error == "Skill not found"

    def test_negotiate_capability_observation(self):
        """Test observation from capability negotiation."""
        obs = Observation(
            skill_name="negotiate_capability",
            inputs={"request": "filesystem access"},
            result={
                "status": "auto_bound",
                "bound_tools": ["fs-reader", "fs-writer"],
                "offer_generate": False,
            },
            success=True,
        )
        assert obs.skill_name == "negotiate_capability"
        assert obs.result["bound_tools"] == ["fs-reader", "fs-writer"]

    def test_create_skill_observation(self):
        """Test observation from skill creation."""
        obs = Observation(
            skill_name="create_skill",
            inputs={"goal": "parse JSON files"},
            result={
                "status": "created",
                "skill_name": "json-parser",
                "signed": True,
            },
            success=True,
        )
        assert obs.skill_name == "create_skill"
        assert obs.result["skill_name"] == "json-parser"

class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_successful_result(self):
        """Test successful execution result."""
        result = ExecutionResult(
            success=True,
            output="Task completed successfully",
            partial_results=[
                Observation(
                    skill_name="test",
                    inputs={},
                    result="ok",
                    success=True,
                )
            ],
        )
        assert result.success is True
        assert len(result.partial_results) == 1

    def test_failed_result(self):
        """Test failed execution result."""
        result = ExecutionResult(
            success=False,
            reason="Leash exceeded: max actions reached",
        )
        assert result.success is False
        assert "Leash exceeded" in result.reason

class TestGoalResult:
    """Tests for GoalResult model."""

    def test_successful_goal(self):
        """Test successful goal completion."""
        result = GoalResult(
            success=True,
            completed_steps=[
                ("step1", ExecutionResult(success=True)),
                ("step2", ExecutionResult(success=True)),
            ],
        )
        assert result.success is True
        assert len(result.completed_steps) == 2

    def test_failed_goal(self):
        """Test failed goal with failed step info."""
        result = GoalResult(
            success=False,
            completed_steps=[("step1", ExecutionResult(success=True))],
            failed_step="step2",
        )
        assert result.success is False
        assert result.failed_step == "step2"
