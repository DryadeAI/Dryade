"""Pydantic models for autonomous skill execution."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions the ReAct executor can take.

    These determine how the executor routes and handles each thought.
    """

    EXECUTE_SKILL = "execute_skill"
    NEGOTIATE_CAPABILITY = "negotiate_capability"
    CREATE_SKILL = "create_skill"
    ASK_HUMAN = "ask_human"

class CapabilityNegotiationRequest(BaseModel):
    """Request for capability negotiation in ReAct loop.

    Used when the executor needs to acquire new tools/capabilities
    mid-execution to accomplish a goal.
    """

    request: str  # Natural language capability request
    user_prefs: dict[str, Any] = Field(
        default_factory=lambda: {"auto_accept": False, "accept_all_session": False}
    )

class SkillCreationRequest(BaseModel):
    """Request for autonomous skill creation.

    Used when the executor determines a new skill is needed
    and triggers the self-dev sandbox to create it.
    """

    skill_name: str
    description: str
    goal: str  # What the skill should accomplish
    inputs_schema: dict[str, Any] | None = None

class CapabilityNegotiationResult(BaseModel):
    """Result of capability negotiation.

    Tracks what tools were bound and whether skill generation
    should be offered as an alternative.
    """

    status: str  # auto_bound, pending_approval, no_match, degraded
    bound_tools: list[str] = Field(default_factory=list)
    offer_generate: bool = False

class ExecutionState(BaseModel):
    """Tracks state during autonomous execution."""

    execution_id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Resource tracking
    tokens_used: int = 0
    cost_usd: float = 0.0
    actions_taken: int = 0
    tool_calls: int = 0

    # Duration tracking (computed)
    @property
    def duration_seconds(self) -> float:
        """Calculate elapsed time since execution started."""
        return (datetime.now(UTC) - self.started_at).total_seconds()

class Thought(BaseModel):
    """LLM reasoning step in ReAct loop.

    Extended to support multiple action types beyond skill execution:
    - EXECUTE_SKILL: Standard skill invocation (default)
    - NEGOTIATE_CAPABILITY: Request new tools/capabilities
    - CREATE_SKILL: Trigger autonomous skill creation
    - ASK_HUMAN: Escalate to human for decision/input
    """

    reasoning: str
    skill_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    is_final: bool = False
    answer: str | None = None

    # Extended action routing fields
    action_type: ActionType | None = None  # Defaults to EXECUTE_SKILL behavior if None
    capability_request: str | None = None  # For NEGOTIATE_CAPABILITY action
    skill_creation_goal: str | None = None  # For CREATE_SKILL action

class Observation(BaseModel):
    """Result of skill/tool execution."""

    skill_name: str
    inputs: dict[str, Any]
    result: Any
    success: bool
    error: str | None = None
    duration_ms: int = 0

class ExecutionResult(BaseModel):
    """Final result of autonomous execution."""

    success: bool
    output: Any = None
    reason: str | None = None
    partial_results: list[Observation] = Field(default_factory=list)
    state: ExecutionState | None = None

class GoalResult(BaseModel):
    """Result of goal-driven plan-and-execute."""

    success: bool
    completed_steps: list[tuple[str, ExecutionResult]] = Field(default_factory=list)
    failed_step: str | None = None
