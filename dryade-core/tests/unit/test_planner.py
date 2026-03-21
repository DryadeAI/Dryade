"""Unit tests for FlowPlanner module."""

import json
from unittest.mock import Mock, patch

import pytest

class TestPlanNode:
    """Tests for PlanNode model."""

    def test_plan_node_defaults(self):
        """Test PlanNode with default values."""
        from core.orchestrator.models import PlanNode

        node = PlanNode(id="step_1", agent="TestAgent", task="Do something")
        assert node.id == "step_1"
        assert node.agent == "TestAgent"
        assert node.task == "Do something"
        assert node.depends_on == []
        assert node.expected_output == ""

    def test_plan_node_all_fields(self):
        """Test PlanNode with all fields."""
        from core.orchestrator.models import PlanNode

        node = PlanNode(
            id="step_2",
            agent="AnalysisAgent",
            task="Analyze data",
            depends_on=["step_1"],
            expected_output="Analysis report",
        )
        assert node.id == "step_2"
        assert node.agent == "AnalysisAgent"
        assert node.task == "Analyze data"
        assert node.depends_on == ["step_1"]
        assert node.expected_output == "Analysis report"

class TestExecutionPlan:
    """Tests for ExecutionPlan model."""

    def test_execution_plan_defaults(self):
        """Test ExecutionPlan with default values via from_nodes."""
        from core.orchestrator.models import ExecutionPlan, PlanNode

        plan = ExecutionPlan.from_nodes(
            name="test_plan",
            description="Test plan",
            nodes=[PlanNode(id="step_1", agent="Agent1", task="Task 1")],
        )
        assert plan.name == "test_plan"
        assert plan.description == "Test plan"
        assert len(plan.nodes) == 1
        assert len(plan.steps) == 1
        assert plan.reasoning == ""
        assert plan.confidence == 0.0

    def test_execution_plan_all_fields(self):
        """Test ExecutionPlan with all fields via from_nodes."""
        from core.orchestrator.models import ExecutionPlan, PlanNode

        plan = ExecutionPlan.from_nodes(
            name="analysis_plan",
            description="Analyze the model",
            nodes=[
                PlanNode(id="step_1", agent="Agent1", task="Task 1"),
                PlanNode(id="step_2", agent="Agent2", task="Task 2", depends_on=["step_1"]),
            ],
            reasoning="Two-step analysis is optimal",
            confidence=0.85,
        )
        assert plan.name == "analysis_plan"
        assert plan.description == "Analyze the model"
        assert len(plan.nodes) == 2
        assert len(plan.steps) == 2
        assert plan.reasoning == "Two-step analysis is optimal"
        assert plan.confidence == 0.85

class TestFlowPlannerInitialization:
    """Tests for FlowPlanner initialization."""

    def test_planner_initialization_default(self):
        """Test FlowPlanner initializes with no LLM."""
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()
        assert planner._llm is None

    def test_planner_initialization_with_llm(self):
        """Test FlowPlanner initializes with provided LLM."""
        from core.orchestrator.planner import FlowPlanner

        mock_llm = Mock()
        planner = FlowPlanner(llm=mock_llm)
        assert planner._llm == mock_llm

    def test_planner_llm_property_lazy_init(self):
        """Test LLM property lazy initialization."""
        from core.orchestrator.planner import FlowPlanner

        # When LLM is provided, it is used directly
        mock_llm = Mock()
        planner = FlowPlanner(llm=mock_llm)

        # Accessing llm property should return the provided LLM
        llm = planner.llm
        assert llm is mock_llm

class TestFlowPlannerCapabilities:
    """Tests for get_available_capabilities method."""

    def test_get_available_capabilities_empty(self):
        """Test get_available_capabilities with no agents."""
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        with patch("core.orchestrator.planner.list_agents", return_value=[]):
            capabilities = planner.get_available_capabilities()
            assert capabilities == []

    def test_get_available_capabilities_with_agents(self):
        """Test get_available_capabilities returns agent info."""
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        mock_card = Mock()
        mock_card.name = "TestAgent"
        mock_card.description = "Test agent description"
        mock_cap = Mock()
        mock_cap.name = "test_tool"
        mock_cap.description = "Test tool"
        mock_card.capabilities = [mock_cap]
        mock_card.framework = Mock(value="crewai")

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            capabilities = planner.get_available_capabilities()
            assert len(capabilities) == 1
            assert capabilities[0]["agent"] == "TestAgent"
            assert capabilities[0]["description"] == "Test agent description"
            assert capabilities[0]["framework"] == "crewai"

class TestFlowPlannerPlanGeneration:
    """Tests for plan generation."""

    @pytest.mark.asyncio
    async def test_generate_plan_no_agents(self):
        """Test generate_plan returns empty plan when no agents available."""
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        with patch("core.orchestrator.planner.list_agents", return_value=[]):
            plan = await planner.generate_plan("Test request")
            assert plan.name == "empty_plan"
            assert plan.nodes == []
            assert plan.confidence == 0.0

    @pytest.mark.asyncio
    async def test_generate_plan_llm_timeout(self):
        """Test generate_plan raises LLMUnavailableError on timeout."""
        from core.orchestrator.planner import FlowPlanner, LLMUnavailableError

        mock_llm = Mock()
        mock_llm.call.side_effect = TimeoutError("LLM timeout")

        planner = FlowPlanner(llm=mock_llm)

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.description = "Agent 1"
        mock_card.capabilities = []
        mock_card.framework = Mock(value="crewai")

        with (
            patch("core.orchestrator.planner.list_agents", return_value=[mock_card]),
            patch("core.config.get_settings") as mock_settings,
        ):
            mock_settings.return_value.llm_planner_timeout = 60

            with pytest.raises(LLMUnavailableError, match="timed out"):
                await planner.generate_plan("Test request")

    @pytest.mark.asyncio
    async def test_generate_plan_llm_connect_error(self):
        """Test generate_plan raises LLMUnavailableError on connection error."""
        import httpx

        from core.orchestrator.planner import FlowPlanner, LLMUnavailableError

        mock_llm = Mock()
        mock_llm.call.side_effect = httpx.ConnectError("No route to host")

        planner = FlowPlanner(llm=mock_llm)

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.description = "Agent 1"
        mock_card.capabilities = []
        mock_card.framework = Mock(value="crewai")

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            with pytest.raises(LLMUnavailableError, match="unavailable"):
                await planner.generate_plan("Test request")

    @pytest.mark.asyncio
    async def test_generate_plan_llm_unexpected_error(self):
        """Test generate_plan raises LLMUnavailableError on unexpected LLM errors."""
        from core.orchestrator.planner import FlowPlanner, LLMUnavailableError

        mock_llm = Mock()
        mock_llm.call.side_effect = RuntimeError("Unexpected LLM error")

        planner = FlowPlanner(llm=mock_llm)

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.description = "Agent 1"
        mock_card.capabilities = []
        mock_card.framework = Mock(value="crewai")

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            with pytest.raises(LLMUnavailableError, match="failed unexpectedly"):
                await planner.generate_plan("Test request")

    @pytest.mark.asyncio
    async def test_generate_plan_success(self):
        """Test generate_plan with successful LLM response."""
        from core.orchestrator.planner import FlowPlanner

        mock_llm = Mock()
        mock_llm.call.return_value = json.dumps(
            {
                "name": "analysis_plan",
                "description": "Analyze the model",
                "reasoning": "Best approach",
                "confidence": 0.9,
                "nodes": [
                    {
                        "id": "step_1",
                        "agent": "Agent1",
                        "task": "Analyze",
                        "depends_on": [],
                        "expected_output": "Results",
                    }
                ],
            }
        )

        planner = FlowPlanner(llm=mock_llm)

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.description = "Agent 1"
        mock_card.capabilities = []
        mock_card.framework = Mock(value="crewai")

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            plan = await planner.generate_plan("Analyze the model")
            assert plan.name == "analysis_plan"
            assert len(plan.nodes) == 1
            assert plan.confidence == 0.9

    @pytest.mark.asyncio
    async def test_generate_plan_json_in_markdown(self):
        """Test generate_plan handles JSON wrapped in markdown."""
        from core.orchestrator.planner import FlowPlanner

        mock_llm = Mock()
        mock_llm.call.return_value = """```json
{
    "name": "markdown_plan",
    "description": "Plan in markdown",
    "reasoning": "Extracted from markdown",
    "confidence": 0.8,
    "nodes": [
        {"id": "step_1", "agent": "Agent1", "task": "Task", "depends_on": [], "expected_output": "Output"}
    ]
}
```"""

        planner = FlowPlanner(llm=mock_llm)

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.description = "Agent 1"
        mock_card.capabilities = []
        mock_card.framework = Mock(value="crewai")

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            plan = await planner.generate_plan("Test")
            assert plan.name == "markdown_plan"

    @pytest.mark.asyncio
    async def test_generate_plan_malformed_json(self):
        """Test generate_plan handles malformed JSON response."""
        from core.orchestrator.planner import FlowPlanner

        mock_llm = Mock()
        mock_llm.call.return_value = "This is not valid JSON at all"

        planner = FlowPlanner(llm=mock_llm)

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.description = "Agent 1"
        mock_card.capabilities = []
        mock_card.framework = Mock(value="crewai")

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            plan = await planner.generate_plan("Test")
            assert plan.name == "fallback_plan"
            assert plan.confidence == 0.3

class TestFlowPlannerValidation:
    """Tests for plan validation."""

    @pytest.mark.asyncio
    async def test_validate_plan_valid(self):
        """Test validate_plan with valid plan."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.capabilities = []

        plan = ExecutionPlan.from_nodes(
            name="valid_plan",
            description="Valid plan",
            nodes=[PlanNode(id="step_1", agent="Agent1", task="Task")],
        )

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            is_valid, issues = await planner.validate_plan(plan)
            assert is_valid is True
            assert issues == []

    @pytest.mark.asyncio
    async def test_validate_plan_agent_not_found(self):
        """Test validate_plan detects missing agent."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        plan = ExecutionPlan.from_nodes(
            name="invalid_plan",
            description="Invalid plan",
            nodes=[PlanNode(id="step_1", agent="NonExistent", task="Task")],
        )

        with patch("core.orchestrator.planner.list_agents", return_value=[]):
            is_valid, issues = await planner.validate_plan(plan)
            assert is_valid is False
            assert any("not found" in issue.lower() for issue in issues)

    @pytest.mark.asyncio
    async def test_validate_plan_too_many_nodes(self):
        """Test validate_plan rejects plan with too many nodes."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        # Create plan with 21 nodes (exceeds max of 20)
        nodes = [PlanNode(id=f"step_{i}", agent="Agent1", task=f"Task {i}") for i in range(21)]

        plan = ExecutionPlan.from_nodes(
            name="large_plan",
            description="Plan with too many nodes",
            nodes=nodes,
        )

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.capabilities = []

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            is_valid, issues = await planner.validate_plan(plan)
            assert is_valid is False
            assert any("exceeds maximum" in issue.lower() for issue in issues)

    @pytest.mark.asyncio
    async def test_validate_plan_missing_dependency(self):
        """Test validate_plan detects missing dependency."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        plan = ExecutionPlan.from_nodes(
            name="dep_plan",
            description="Plan with missing dependency",
            nodes=[
                PlanNode(id="step_2", agent="Agent1", task="Task", depends_on=["step_1"]),
            ],
        )

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.capabilities = []

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            is_valid, issues = await planner.validate_plan(plan)
            assert is_valid is False
            assert any(
                "dependency" in issue.lower() and "not found" in issue.lower() for issue in issues
            )

    @pytest.mark.asyncio
    async def test_validate_plan_circular_dependency(self):
        """Test validate_plan detects circular dependencies."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        plan = ExecutionPlan.from_nodes(
            name="circular_plan",
            description="Plan with circular dependency",
            nodes=[
                PlanNode(id="step_1", agent="Agent1", task="Task 1", depends_on=["step_2"]),
                PlanNode(id="step_2", agent="Agent1", task="Task 2", depends_on=["step_1"]),
            ],
        )

        mock_card = Mock()
        mock_card.name = "Agent1"
        mock_card.capabilities = []

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            is_valid, issues = await planner.validate_plan(plan)
            assert is_valid is False
            assert any("circular" in issue.lower() for issue in issues)

class TestFlowPlannerPlanToFlow:
    """Tests for plan_to_flow conversion."""

    def test_plan_to_flow_basic(self):
        """Test plan_to_flow with basic plan."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        plan = ExecutionPlan.from_nodes(
            name="test_plan",
            description="Test plan",
            nodes=[PlanNode(id="step_1", agent="Agent1", task="Task 1")],
        )

        flow = planner.plan_to_flow(plan)

        assert flow.name == "test_plan"
        assert flow.description == "Test plan"
        assert len(flow.nodes) == 1
        assert flow.nodes[0]["id"] == "step_1"
        assert flow.nodes[0]["agent"] == "Agent1"
        assert len(flow.edges) == 0

    def test_plan_to_flow_with_dependencies(self):
        """Test plan_to_flow creates edges from dependencies."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        plan = ExecutionPlan.from_nodes(
            name="dep_plan",
            description="Plan with dependencies",
            nodes=[
                PlanNode(id="step_1", agent="Agent1", task="Task 1"),
                PlanNode(id="step_2", agent="Agent2", task="Task 2", depends_on=["step_1"]),
            ],
        )

        flow = planner.plan_to_flow(plan)

        assert len(flow.nodes) == 2
        assert len(flow.edges) == 1
        assert flow.edges[0]["source"] == "step_1"
        assert flow.edges[0]["target"] == "step_2"

class TestFlowPlannerRetry:
    """Tests for retry and recovery methods."""

    @pytest.mark.asyncio
    async def test_retry_node_transient_error(self):
        """Test retry_node for transient errors."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        node = PlanNode(id="step_1", agent="Agent1", task="Task 1")
        plan = ExecutionPlan.from_nodes(name="test", description="Test", nodes=[node])

        retry_result = await planner.retry_node(node, "Connection timeout error", plan)

        assert retry_result is not None
        assert retry_result.id == node.id

    @pytest.mark.asyncio
    async def test_retry_node_agent_not_found(self):
        """Test retry_node suggests alternative agent."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        node = PlanNode(id="step_1", agent="MissingAgent", task="Task 1")
        plan = ExecutionPlan.from_nodes(name="test", description="Test", nodes=[node])

        mock_card = Mock()
        mock_card.name = "AlternativeAgent"

        with patch("core.orchestrator.planner.list_agents", return_value=[mock_card]):
            retry_result = await planner.retry_node(node, "Agent not found", plan)

            assert retry_result is not None
            assert retry_result.agent == "AlternativeAgent"

    @pytest.mark.asyncio
    async def test_retry_node_tool_error_returns_none(self):
        """Test retry_node returns None for tool errors."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        node = PlanNode(id="step_1", agent="Agent1", task="Task 1")
        plan = ExecutionPlan.from_nodes(name="test", description="Test", nodes=[node])

        retry_result = await planner.retry_node(node, "Tool capability error", plan)

        assert retry_result is None

class TestFlowPlannerSimplify:
    """Tests for plan simplification."""

    @pytest.mark.asyncio
    async def test_simplify_plan_small_plan_unchanged(self):
        """Test simplify_plan leaves small plans unchanged."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        plan = ExecutionPlan.from_nodes(
            name="small_plan",
            description="Small plan",
            nodes=[
                PlanNode(id="step_1", agent="Agent1", task="Task 1"),
                PlanNode(id="step_2", agent="Agent2", task="Task 2"),
            ],
        )

        simplified = await planner.simplify_plan(plan, "test reason")

        # Should return unchanged
        assert simplified.name == "small_plan"
        assert len(simplified.nodes) == 2

    @pytest.mark.asyncio
    async def test_simplify_plan_large_plan(self):
        """Test simplify_plan reduces large plans."""
        from core.orchestrator.models import ExecutionPlan, PlanNode
        from core.orchestrator.planner import FlowPlanner

        planner = FlowPlanner()

        # Create plan with 10 nodes
        nodes = [PlanNode(id=f"step_{i}", agent="Agent1", task=f"Task {i}") for i in range(10)]

        plan = ExecutionPlan.from_nodes(
            name="large_plan",
            description="Large plan",
            nodes=nodes,
            confidence=0.9,
        )

        simplified = await planner.simplify_plan(plan, "too many nodes")

        assert simplified.name == "large_plan_simplified"
        assert len(simplified.nodes) <= 5
        assert simplified.confidence < plan.confidence

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_planner_singleton(self):
        """Test get_planner returns singleton."""
        from core.orchestrator import planner as planner_module

        # Reset global state
        planner_module._planner = None

        planner1 = planner_module.get_planner()
        planner2 = planner_module.get_planner()

        assert planner1 is planner2

    @pytest.mark.asyncio
    async def test_generate_execution_plan(self):
        """Test generate_execution_plan convenience function."""
        from core.orchestrator import planner as planner_module

        # Reset global state
        planner_module._planner = None

        with patch("core.orchestrator.planner.list_agents", return_value=[]):
            plan = await planner_module.generate_execution_plan("Test request")
            assert plan.name == "empty_plan"
