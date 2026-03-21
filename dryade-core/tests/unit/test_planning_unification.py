"""Tests for planning unification (ExecutionPlan, PlanNode, PlanStep, PlanningOrchestrator).

Covers:
- PlanNode model: fields and defaults
- PlanStep model: field defaults and validation
- ExecutionPlan model: construction, compute_execution_order, to_preview_dict
- ExecutionPlan backward compatibility (original fields only)
- ExecutionPlan FlowPlanner fields (name, description, nodes, reasoning, confidence)
- ExecutionPlan.from_nodes() classmethod conversion
- to_preview_dict() with and without FlowPlanner fields
- PlanningOrchestrator.orchestrate() signature
- Import paths from core.orchestrator.models
"""

import inspect
from uuid import uuid4

import pytest

from core.orchestrator.models import (
    ExecutionPlan,
    PlanNode,
    PlanStep,
    StepStatus,
)

# ---------------------------------------------------------------------------
# Test PlanNode model
# ---------------------------------------------------------------------------

class TestPlanNodeModel:
    """Verify PlanNode fields and defaults."""

    def test_plan_node_all_fields(self):
        """Create PlanNode with all fields."""
        node = PlanNode(
            id="node-1",
            agent="mcp-http",
            task="Fetch data from API",
            depends_on=["node-0"],
            expected_output="JSON response",
        )
        assert node.id == "node-1"
        assert node.agent == "mcp-http"
        assert node.task == "Fetch data from API"
        assert node.depends_on == ["node-0"]
        assert node.expected_output == "JSON response"

    def test_plan_node_defaults(self):
        """PlanNode with only required fields uses defaults."""
        node = PlanNode(id="n1", agent="a", task="t")
        assert node.depends_on == []
        assert node.expected_output == ""

    def test_plan_node_multiple_dependencies(self):
        """PlanNode can have multiple dependencies."""
        node = PlanNode(
            id="n3",
            agent="c",
            task="Merge results",
            depends_on=["n1", "n2"],
        )
        assert len(node.depends_on) == 2
        assert "n1" in node.depends_on
        assert "n2" in node.depends_on

# ---------------------------------------------------------------------------
# Test PlanStep model
# ---------------------------------------------------------------------------

class TestPlanStepModel:
    """Verify PlanStep fields, defaults, and validation."""

    def test_plan_step_defaults(self):
        """PlanStep should have sensible defaults."""
        step = PlanStep(id="step-1", agent_name="agent-a", task="Do something")
        assert step.id == "step-1"
        assert step.agent_name == "agent-a"
        assert step.task == "Do something"
        assert step.depends_on == []
        assert step.expected_output == ""
        assert step.is_critical is True
        assert step.estimated_duration_seconds == 30
        assert step.status == StepStatus.PENDING
        assert step.result is None
        assert step.error is None
        assert step.actual_duration_ms == 0

    def test_plan_step_with_dependencies(self):
        """PlanStep with explicit dependencies."""
        step = PlanStep(
            id="step-2",
            agent_name="agent-b",
            task="Process results",
            depends_on=["step-1"],
            is_critical=False,
            estimated_duration_seconds=60,
        )
        assert step.depends_on == ["step-1"]
        assert step.is_critical is False
        assert step.estimated_duration_seconds == 60

    def test_plan_step_status_transitions(self):
        """PlanStep status can be changed after creation."""
        step = PlanStep(id="step-1", agent_name="a", task="t")
        assert step.status == StepStatus.PENDING

        step.status = StepStatus.RUNNING
        assert step.status == StepStatus.RUNNING

        step.status = StepStatus.COMPLETED
        step.result = "done"
        assert step.status == StepStatus.COMPLETED

# ---------------------------------------------------------------------------
# Test ExecutionPlan model (core fields)
# ---------------------------------------------------------------------------

class TestExecutionPlanModel:
    """Verify ExecutionPlan construction and methods."""

    def test_basic_construction(self):
        """ExecutionPlan with minimal fields."""
        plan = ExecutionPlan(
            id="plan-1",
            goal="Test goal",
            steps=[PlanStep(id="s1", agent_name="a", task="t")],
        )
        assert plan.id == "plan-1"
        assert plan.goal == "Test goal"
        assert len(plan.steps) == 1
        assert plan.execution_order == []
        assert plan.total_estimated_seconds == 0
        assert plan.status == "pending"
        assert plan.replan_count == 0

    def test_execution_plan_has_flow_planner_fields(self):
        """ExecutionPlan should have FlowPlanner fields with defaults."""
        plan = ExecutionPlan(id="p1", goal="g", steps=[])
        assert plan.name == ""
        assert plan.description == ""
        assert plan.nodes == []
        assert plan.reasoning == ""
        assert plan.confidence == 0.0

    def test_execution_plan_backward_compat(self):
        """ExecutionPlan with only original fields (no FlowPlanner additions)."""
        plan = ExecutionPlan(
            id=str(uuid4()),
            goal="Analyze code",
            steps=[
                PlanStep(id="step-1", agent_name="mcp-fs", task="Read files"),
                PlanStep(id="step-2", agent_name="mcp-fs", task="Process", depends_on=["step-1"]),
            ],
        )
        plan.compute_execution_order()

        # All original fields work without FlowPlanner fields
        assert plan.goal == "Analyze code"
        assert len(plan.steps) == 2
        assert len(plan.execution_order) == 2
        assert plan.total_estimated_seconds > 0

    def test_compute_execution_order_single_step(self):
        """Single step produces one wave."""
        plan = ExecutionPlan(
            id="p1",
            goal="Simple",
            steps=[PlanStep(id="s1", agent_name="a", task="t")],
        )
        plan.compute_execution_order()

        assert plan.execution_order == [["s1"]]
        assert plan.total_estimated_seconds == 30  # default est

    def test_compute_execution_order_parallel_steps(self):
        """Two independent steps should be in the same wave."""
        plan = ExecutionPlan(
            id="p1",
            goal="Parallel",
            steps=[
                PlanStep(id="s1", agent_name="a", task="t1"),
                PlanStep(id="s2", agent_name="b", task="t2"),
            ],
        )
        plan.compute_execution_order()

        assert len(plan.execution_order) == 1
        assert sorted(plan.execution_order[0]) == ["s1", "s2"]
        # Critical path = max of single wave = 30
        assert plan.total_estimated_seconds == 30

    def test_compute_execution_order_with_dependencies(self):
        """Dependencies create sequential waves."""
        plan = ExecutionPlan(
            id="p1",
            goal="Sequential",
            steps=[
                PlanStep(id="s1", agent_name="a", task="t1"),
                PlanStep(id="s2", agent_name="b", task="t2"),
                PlanStep(id="s3", agent_name="c", task="t3", depends_on=["s1", "s2"]),
            ],
        )
        plan.compute_execution_order()

        assert len(plan.execution_order) == 2
        assert sorted(plan.execution_order[0]) == ["s1", "s2"]
        assert plan.execution_order[1] == ["s3"]
        # Critical path: max(wave1) + max(wave2) = 30 + 30 = 60
        assert plan.total_estimated_seconds == 60

    def test_compute_execution_order_empty(self):
        """Empty steps produce empty execution order."""
        plan = ExecutionPlan(id="p1", goal="Empty", steps=[])
        plan.compute_execution_order()
        assert plan.execution_order == []
        assert plan.total_estimated_seconds == 0

    def test_get_step_found(self):
        """get_step returns the correct step."""
        step = PlanStep(id="target", agent_name="a", task="t")
        plan = ExecutionPlan(id="p1", goal="g", steps=[step])
        assert plan.get_step("target") is step

    def test_get_step_not_found(self):
        """get_step raises ValueError for unknown step."""
        plan = ExecutionPlan(id="p1", goal="g", steps=[])
        with pytest.raises(ValueError, match="not found"):
            plan.get_step("nonexistent")

# ---------------------------------------------------------------------------
# Test ExecutionPlan.from_nodes()
# ---------------------------------------------------------------------------

class TestFromNodes:
    """Tests for ExecutionPlan.from_nodes() classmethod."""

    def test_from_nodes_basic(self):
        """from_nodes creates plan with steps, execution order, and metadata."""
        nodes = [
            PlanNode(id="n1", agent="agent-a", task="First task"),
            PlanNode(id="n2", agent="agent-b", task="Second task"),
        ]
        plan = ExecutionPlan.from_nodes(
            name="test-plan",
            description="A test plan",
            nodes=nodes,
        )
        # Auto-generated ID
        assert plan.id
        assert len(plan.id) > 0

        # Steps created from nodes
        assert len(plan.steps) == 2
        assert plan.steps[0].id == "n1"
        assert plan.steps[0].agent_name == "agent-a"
        assert plan.steps[0].task == "First task"
        assert plan.steps[1].id == "n2"
        assert plan.steps[1].agent_name == "agent-b"

        # Execution order computed
        assert len(plan.execution_order) >= 1

        # goal = description
        assert plan.goal == "A test plan"

        # FlowPlanner fields preserved
        assert plan.name == "test-plan"
        assert plan.description == "A test plan"
        assert plan.nodes == nodes

    def test_from_nodes_with_dependencies(self):
        """from_nodes respects node dependencies in execution order."""
        nodes = [
            PlanNode(id="n1", agent="a", task="First"),
            PlanNode(id="n2", agent="b", task="Second"),
            PlanNode(id="n3", agent="c", task="Third", depends_on=["n1", "n2"]),
        ]
        plan = ExecutionPlan.from_nodes(
            name="dep-plan",
            description="Plan with deps",
            nodes=nodes,
        )
        assert len(plan.execution_order) == 2
        assert sorted(plan.execution_order[0]) == ["n1", "n2"]
        assert plan.execution_order[1] == ["n3"]

    def test_from_nodes_empty(self):
        """from_nodes with empty nodes list."""
        plan = ExecutionPlan.from_nodes(
            name="empty",
            description="Nothing",
            nodes=[],
        )
        assert plan.steps == []
        assert plan.execution_order == []
        assert plan.nodes == []

    def test_from_nodes_with_reasoning_and_confidence(self):
        """from_nodes preserves reasoning and confidence."""
        nodes = [PlanNode(id="n1", agent="a", task="t")]
        plan = ExecutionPlan.from_nodes(
            name="confident-plan",
            description="Desc",
            nodes=nodes,
            reasoning="Selected optimal agent",
            confidence=0.95,
        )
        assert plan.reasoning == "Selected optimal agent"
        assert plan.confidence == 0.95

    def test_from_nodes_preserves_expected_output(self):
        """from_nodes carries expected_output from PlanNode to PlanStep."""
        nodes = [
            PlanNode(id="n1", agent="a", task="t", expected_output="JSON data"),
        ]
        plan = ExecutionPlan.from_nodes(name="p", description="d", nodes=nodes)
        assert plan.steps[0].expected_output == "JSON data"

# ---------------------------------------------------------------------------
# Test to_preview_dict (FlowPlanner field inclusion)
# ---------------------------------------------------------------------------

class TestToPreviewDict:
    """Verify to_preview_dict behavior with and without FlowPlanner fields."""

    def test_to_preview_dict_base_structure(self):
        """Base preview dict always includes core fields."""
        plan = ExecutionPlan(
            id="p1",
            goal="Test",
            steps=[
                PlanStep(id="s1", agent_name="agent-a", task="Do A", is_critical=True),
                PlanStep(id="s2", agent_name="agent-b", task="Do B", depends_on=["s1"]),
            ],
        )
        plan.compute_execution_order()

        preview = plan.to_preview_dict()

        assert preview["id"] == "p1"
        assert preview["goal"] == "Test"
        assert len(preview["steps"]) == 2
        assert preview["steps"][0]["id"] == "s1"
        assert preview["steps"][0]["agent"] == "agent-a"
        assert preview["steps"][0]["task"] == "Do A"
        assert preview["steps"][0]["is_critical"] is True
        assert preview["steps"][0]["status"] == "pending"
        assert preview["steps"][1]["depends_on"] == ["s1"]
        assert preview["waves"] == [["s1"], ["s2"]]
        assert preview["total_estimated_seconds"] == 60
        assert preview["status"] == "pending"

    def test_to_preview_dict_includes_flow_planner_fields(self):
        """Plans created via from_nodes() include FlowPlanner fields in preview."""
        nodes = [
            PlanNode(id="n1", agent="a", task="t1"),
            PlanNode(id="n2", agent="b", task="t2", depends_on=["n1"]),
        ]
        plan = ExecutionPlan.from_nodes(
            name="my-plan",
            description="My plan description",
            nodes=nodes,
            reasoning="Agent routing analysis",
            confidence=0.85,
        )
        preview = plan.to_preview_dict()

        assert preview["name"] == "my-plan"
        assert preview["description"] == "My plan description"
        assert preview["reasoning"] == "Agent routing analysis"
        assert preview["confidence"] == 0.85
        assert "nodes" in preview
        assert len(preview["nodes"]) == 2
        assert preview["nodes"][0]["id"] == "n1"
        assert preview["nodes"][0]["agent"] == "a"

    def test_to_preview_dict_omits_empty_flow_fields(self):
        """Plans without FlowPlanner fields should NOT include them in preview."""
        plan = ExecutionPlan(
            id="p1",
            goal="Basic plan",
            steps=[PlanStep(id="s1", agent_name="a", task="t")],
        )
        plan.compute_execution_order()
        preview = plan.to_preview_dict()

        # FlowPlanner fields should NOT be in the dict (empty defaults excluded)
        assert "name" not in preview
        assert "description" not in preview
        assert "reasoning" not in preview
        assert "confidence" not in preview
        assert "nodes" not in preview

# ---------------------------------------------------------------------------
# Test imports and signatures
# ---------------------------------------------------------------------------

class TestImportsAndSignatures:
    """Verify import paths and function signatures."""

    def test_execution_plan_importable_from_models(self):
        """ExecutionPlan can be imported from core.orchestrator.models."""
        from core.orchestrator.models import ExecutionPlan as EP

        assert EP is ExecutionPlan

    def test_plan_step_importable_from_models(self):
        """PlanStep can be imported from core.orchestrator.models."""
        from core.orchestrator.models import PlanStep as PS

        assert PS is PlanStep

    def test_plan_node_importable_from_models(self):
        """PlanNode can be imported from core.orchestrator.models."""
        from core.orchestrator.models import PlanNode as PN

        assert PN is PlanNode

    def test_step_status_importable_from_models(self):
        """StepStatus can be imported from core.orchestrator.models."""
        from core.orchestrator.models import StepStatus as SS

        assert SS is StepStatus

    def test_planning_orchestrator_orchestrate_signature(self):
        """PlanningOrchestrator.orchestrate() should accept standard params."""
        from core.orchestrator.planning import PlanningOrchestrator

        sig = inspect.signature(PlanningOrchestrator.orchestrate)
        param_names = list(sig.parameters.keys())

        # Core required params
        assert "self" in param_names
        assert "goal" in param_names
        assert "context" in param_names

        # Optional callback params
        assert "on_thinking" in param_names
        assert "on_agent_event" in param_names
        assert "on_plan_event" in param_names
        assert "cancel_event" in param_names
        assert "on_token" in param_names

    def test_planning_orchestrator_max_replans(self):
        """PlanningOrchestrator has MAX_REPLANS constant."""
        from core.orchestrator.planning import PlanningOrchestrator

        assert hasattr(PlanningOrchestrator, "MAX_REPLANS")
        assert PlanningOrchestrator.MAX_REPLANS == 3

    def test_plan_node_in_models_all(self):
        """PlanNode should be in __all__ export list."""
        from core.orchestrator import models

        assert "PlanNode" in models.__all__
