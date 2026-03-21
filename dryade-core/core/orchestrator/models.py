"""Pydantic models for native orchestration.

Follows patterns from core/autonomous/models.py.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "OrchestrationMode",
    "Tier",
    "FailureAction",
    "ErrorCategory",
    "ErrorSeverity",
    "ToolError",
    "ErrorClassification",
    "OrchestrationTask",
    "OrchestrationThought",
    "OrchestrationObservation",
    "OrchestrationState",
    "OrchestrationResult",
    "StepStatus",
    "PlanNode",
    "PlanStep",
    "ExecutionPlan",
]

class OrchestrationMode(str, Enum):
    """Orchestration modes for DryadeOrchestrator.

    - SEQUENTIAL: Execute agents one after another
    - PARALLEL: Execute independent agents concurrently
    - HIERARCHICAL: Manager delegates to specialists
    - ADAPTIVE: LLM decides best mode dynamically (default per user decision)
    """

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    ADAPTIVE = "adaptive"

class Tier(str, Enum):
    """Message complexity tier for dispatch routing.

    INSTANT -- Direct LLM response, no agents (greetings, meta-questions)
    SIMPLE  -- Single agent, bypass orchestrate_think()
    COMPLEX -- Full ReAct / Planning pipeline (unchanged)
    """

    INSTANT = "instant"
    SIMPLE = "simple"
    COMPLEX = "complex"

class FailureAction(str, Enum):
    """Actions for failure handling.

    Tier 1 (deterministic via FailureClassifier / graduated escalation):
        RETRY, SKIP, ESCALATE, ABORT, CONTEXT_REDUCE, ROLLBACK
    Tier 2 (LLM-decided via failure_think):
        ALTERNATIVE, DECOMPOSE
    """

    RETRY = "retry"  # Try the same agent again
    ALTERNATIVE = "alternative"  # Find different agent
    SKIP = "skip"  # Skip this task (non-critical only)
    ESCALATE = "escalate"  # Ask user for help
    DECOMPOSE = "decompose"  # Break task into smaller subtasks
    CONTEXT_REDUCE = "context_reduce"  # Reduce context and retry
    ABORT = "abort"  # Abort orchestration (unrecoverable)
    ROLLBACK = "rollback"  # Restore state from checkpoint

class ErrorCategory(str, Enum):
    """Categories of errors for failure classification."""

    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    TOOL_NOT_FOUND = "tool_not_found"
    CONTEXT_OVERFLOW = "context_overflow"
    PARSE_ERROR = "parse_error"
    CONNECTION = "connection"
    PERMISSION = "permission"
    RESOURCE = "resource"
    SEMANTIC = "semantic"
    PERMANENT = "permanent"

class ErrorSeverity(str, Enum):
    """Severity levels for classified errors."""

    FATAL = "fatal"
    RETRIABLE = "retriable"
    DEGRADED = "degraded"
    INFORMATIONAL = "informational"

@dataclass
class ToolError:
    """Structured error captured from tool/agent execution.

    Lightweight dataclass (not Pydantic) for use in failure classification
    and error handling pipelines.
    """

    tool_name: str
    server_name: str
    error_type: str
    message: str
    raw_exception: Optional[str] = None
    http_status: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def message_lower(self) -> str:
        """Return lowercased message for pattern matching."""
        return self.message.lower()

    @property
    def retry_safe(self) -> bool:
        """Return False for client errors (http_status < 500)."""
        if self.http_status and self.http_status < 500:
            return False
        return True

@dataclass
class ErrorClassification:
    """Result of classifying a ToolError.

    Bundles the category, severity, and suggested recovery action
    with confidence and reasoning metadata.
    """

    category: ErrorCategory
    severity: ErrorSeverity
    suggested_action: FailureAction
    confidence: float = 1.0
    reason: str = ""
    metadata: dict = field(default_factory=dict)

class OrchestrationTask(BaseModel):
    """A single task to be executed by an agent."""

    agent_name: str
    description: str
    context: dict[str, Any] = Field(default_factory=dict)
    parent_task: str | None = None  # For hierarchical tracking
    expected_output: str | None = None  # What we expect
    is_critical: bool = False  # Per user decision: criticality-based failure handling
    required_capabilities: list[str] = Field(default_factory=list)  # Capabilities needed
    # MCP tool execution fields
    tool: str | None = None  # Explicit tool name for MCP agents
    arguments: dict[str, Any] = Field(default_factory=dict)  # Arguments for MCP tools

class OrchestrationThought(BaseModel):
    """LLM reasoning step in orchestration loop.

    Similar to Thought in autonomous/models.py but orchestration-specific.
    """

    reasoning: str  # Why this decision
    is_final: bool = False  # Goal achieved?
    needs_clarification: bool = False  # LLM wants to ask user a clarifying question
    answer: str | None = None  # Final answer if is_final

    # For non-final thoughts - what to do next
    task: OrchestrationTask | None = None  # Single task
    parallel_tasks: list[OrchestrationTask] | None = None  # Multiple parallel tasks

    # Hierarchical mode fields
    delegate_to: str | None = None  # Agent to delegate to
    subtask: str | None = None  # What to delegate

    # Failure handling (per user decision: intelligent fallback)
    failure_action: FailureAction | None = None  # How to handle failure
    alternative_agent: str | None = None  # If failure_action=ALTERNATIVE
    escalation_question: str | None = None  # If failure_action=ESCALATE

    # Reasoning visibility (per user decision: configurable)
    reasoning_summary: str | None = None  # Short summary for default view

class OrchestrationObservation(BaseModel):
    """Result of agent execution in orchestration."""

    agent_name: str
    task: str
    result: Any
    success: bool
    error: str | None = None
    duration_ms: int = 0
    validation: str | None = None  # "passed", "failed" for hierarchical
    retry_count: int = 0  # How many times this task was retried
    reasoning: str | None = None  # LLM reasoning that led to this action
    reasoning_summary: str | None = None  # Short summary for UI display
    failure_thought: "OrchestrationThought | None" = None  # LLM decision on failure handling
    error_classification: "ErrorClassification | None" = None  # Tier 1/2 classification result

class OrchestrationState(BaseModel):
    """Tracks state during orchestration execution."""

    execution_id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: OrchestrationMode = OrchestrationMode.ADAPTIVE

    # Resource tracking
    actions_taken: int = 0

    # User preferences (per user decision: configurable)
    memory_enabled: bool = True  # User can disable memory usage
    reasoning_visibility: str = "summary"  # "summary" | "detailed" | "hidden"

    @property
    def duration_seconds(self) -> float:
        """Calculate elapsed time since execution started."""
        return (datetime.now(UTC) - self.started_at).total_seconds()

class OrchestrationResult(BaseModel):
    """Final result of orchestration."""

    success: bool
    output: Any = None
    reason: str | None = None
    reasoning: str | None = None  # LLM reasoning for direct answers (is_final=true)
    reasoning_summary: str | None = None  # Short summary for UI display
    partial_results: list[OrchestrationObservation] = Field(default_factory=list)
    state: OrchestrationState | None = None
    needs_escalation: bool = False  # Per user decision: inline escalation
    escalation_question: str | None = None  # Question for user if needs_escalation
    escalation_action: dict[str, Any] | None = None  # Proposed fix action if needs_escalation
    original_goal: str | None = None  # Original user goal for retry after escalation fix
    # Track alternative agent usage for observability
    alternative_agent_used: str | None = None  # Name of alternative agent if one was used
    # Track user-initiated cancellation
    cancelled: bool = False  # True when user cancelled the orchestration
    # Track whether the response was streamed token-by-token
    streamed: bool = False  # True when on_token streaming was used for the final answer
    # Serialized ObservationHistory for escalation state preservation
    observation_history_data: dict[str, Any] | None = None

# ---------------------------------------------------------------------------
# Execution Plan (DAG-based planning layer)
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    """Status of a plan step during execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPLANNED = "replanned"

class PlanNode(BaseModel):
    """A node in an LLM-generated execution plan (FlowPlanner output).

    Used by FlowPlanner for frontend-facing plan generation.
    Can be converted to PlanStep for execution by PlanningOrchestrator.
    """

    id: str
    agent: str
    task: str
    depends_on: list[str] = Field(default_factory=list)
    expected_output: str = ""
    tool: str | None = None  # Explicit MCP tool name (required for mcp-* agents)
    arguments: dict[str, Any] | None = Field(default=None)  # Tool arguments for MCP agents

    @field_validator("arguments", mode="before")
    @classmethod
    def _coerce_arguments(cls, v: Any) -> dict[str, Any] | None:
        """Accept None from LLM JSON output."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        return None

class PlanStep(BaseModel):
    """A single step in an execution plan DAG."""

    id: str
    agent_name: str
    task: str
    depends_on: list[str] = Field(default_factory=list)
    expected_output: str = ""
    is_critical: bool = True
    estimated_duration_seconds: int = 30
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    actual_duration_ms: int = 0

class ExecutionPlan(BaseModel):
    """Unified execution plan for both FlowPlanner and PlanningOrchestrator.

    Core fields (used by PlanningOrchestrator):
      id, goal, steps, execution_order, total_estimated_seconds, created_at,
      status, replan_count

    FlowPlanner fields (optional, used for frontend plan display):
      name, description, nodes, reasoning, confidence

    Steps form a directed acyclic graph via depends_on references.
    compute_execution_order() uses Kahn's algorithm to produce waves
    of steps that can run in parallel within each wave.
    """

    id: str
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    execution_order: list[list[str]] = Field(default_factory=list)
    total_estimated_seconds: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "pending"  # pending|executing|completed|failed|cancelled
    replan_count: int = 0

    # FlowPlanner fields (optional -- populated when plan comes from FlowPlanner)
    name: str = ""
    description: str = ""
    nodes: list[PlanNode] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0

    @classmethod
    def from_nodes(
        cls,
        name: str,
        description: str,
        nodes: list[PlanNode],
        reasoning: str = "",
        confidence: float = 0.0,
    ) -> "ExecutionPlan":
        """Create an ExecutionPlan from FlowPlanner's PlanNode output.

        Converts PlanNodes to PlanSteps and computes execution order.
        Preserves the original nodes for frontend display.
        """
        from uuid import uuid4

        steps = [
            PlanStep(
                id=node.id,
                agent_name=node.agent,
                task=node.task,
                depends_on=node.depends_on,
                expected_output=node.expected_output,
            )
            for node in nodes
        ]
        plan = cls(
            id=str(uuid4()),
            goal=description,
            steps=steps,
            name=name,
            description=description,
            nodes=nodes,
            reasoning=reasoning,
            confidence=confidence,
        )
        plan.compute_execution_order()
        return plan

    def compute_execution_order(self) -> None:
        """Topological sort via Kahn's algorithm into parallel waves.

        Each wave contains step IDs whose dependencies are all satisfied
        by prior waves.  Also computes total_estimated_seconds as the sum
        of the max estimated duration in each wave (critical-path estimate).
        """
        step_ids = {s.id for s in self.steps}
        in_degree: dict[str, int] = dict.fromkeys(step_ids, 0)
        dependents: dict[str, list[str]] = {sid: [] for sid in step_ids}

        for step in self.steps:
            for dep in step.depends_on:
                if dep in step_ids:
                    in_degree[step.id] += 1
                    dependents[dep].append(step.id)

        # Seed with zero-in-degree nodes
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        waves: list[list[str]] = []

        while queue:
            # Sort for deterministic ordering within each wave
            wave = sorted(queue)
            waves.append(wave)
            next_queue: list[str] = []
            for sid in wave:
                for dep_id in dependents[sid]:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        next_queue.append(dep_id)
            queue = next_queue

        self.execution_order = waves

        # Critical-path estimate: sum of max duration per wave
        step_map = {s.id: s for s in self.steps}
        self.total_estimated_seconds = sum(
            max((step_map[sid].estimated_duration_seconds for sid in wave), default=0)
            for wave in waves
        )

    def get_step(self, step_id: str) -> PlanStep:
        """Look up a step by ID.

        Raises:
            ValueError: If step_id is not found.
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        raise ValueError(f"Step '{step_id}' not found in plan '{self.id}'")

    def to_preview_dict(self) -> dict:
        """Return a frontend-friendly dictionary representation."""
        result = {
            "id": self.id,
            "goal": self.goal,
            "steps": [
                {
                    "id": s.id,
                    "agent": s.agent_name,
                    "task": s.task,
                    "depends_on": s.depends_on,
                    "estimated_seconds": s.estimated_duration_seconds,
                    "is_critical": s.is_critical,
                    "status": s.status.value,
                }
                for s in self.steps
            ],
            "waves": self.execution_order,
            "total_estimated_seconds": self.total_estimated_seconds,
            "status": self.status,
        }
        if self.name:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.reasoning:
            result["reasoning"] = self.reasoning
        if self.confidence > 0:
            result["confidence"] = self.confidence
        if self.nodes:
            result["nodes"] = [
                {
                    "id": n.id,
                    "agent": n.agent,
                    "task": n.task,
                    "depends_on": n.depends_on,
                    "expected_output": n.expected_output,
                    **({"tool": n.tool} if n.tool else {}),
                    **({"arguments": n.arguments} if n.arguments else {}),
                }
                for n in self.nodes
            ]
        return result
