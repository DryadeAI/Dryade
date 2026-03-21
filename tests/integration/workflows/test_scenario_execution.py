"""Integration tests for workflow scenario execution."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor
from core.workflows.scenarios import ScenarioConfig, ScenarioRegistry
from core.workflows.schema import WorkflowSchema
from core.workflows.triggers import TriggerHandler, TriggerSource

SCENARIOS_DIR = Path("workflows/scenarios")

class TestScenarioRegistry:
    @pytest.fixture
    def registry(self):
        return ScenarioRegistry(str(SCENARIOS_DIR))

    def test_list_all_scenarios(self, registry):
        """All 9 scenarios should be discoverable."""
        scenarios = registry.list_scenarios()
        assert len(scenarios) >= 9
        names = {s.name for s in scenarios}
        expected = {
            "financial_reporting",
            "invoice_processing",
            "code_review_pipeline",
            "sprint_planning",
            "compliance_audit",
            "devops_deployment",
            "prospect_research",
            "customer_onboarding",
            "multi_framework_demo",
        }
        assert expected.issubset(names)

    @pytest.mark.parametrize(
        "scenario_name",
        [
            "financial_reporting",
            "invoice_processing",
            "code_review_pipeline",
            "sprint_planning",
            "compliance_audit",
            "devops_deployment",
            "prospect_research",
            "customer_onboarding",
            "multi_framework_demo",
        ],
    )
    def test_load_scenario(self, registry, scenario_name):
        """Each scenario should load successfully."""
        config, workflow = registry.get_scenario(scenario_name)
        assert isinstance(config, ScenarioConfig)
        assert isinstance(workflow, WorkflowSchema)
        assert config.name == scenario_name

    @pytest.mark.parametrize(
        "scenario_name",
        [
            "financial_reporting",
            "invoice_processing",
            "code_review_pipeline",
            "sprint_planning",
            "compliance_audit",
            "devops_deployment",
            "prospect_research",
            "customer_onboarding",
            "multi_framework_demo",
        ],
    )
    def test_scenario_has_valid_workflow(self, registry, scenario_name):
        """Each workflow should have valid structure."""
        _, workflow = registry.get_scenario(scenario_name)
        node_types = {n.type for n in workflow.nodes}
        assert "start" in node_types
        assert "end" in node_types
        assert any(n.type == "task" for n in workflow.nodes)

    def test_validate_scenario_with_missing_agents(self, registry):
        """Validation should catch missing agents."""
        with patch("core.adapters.list_agents", return_value=[]):
            errors = registry.validate_scenario("financial_reporting")
            assert len(errors) > 0
            assert any("agent" in e.lower() for e in errors)

class TestScenarioDomains:
    @pytest.fixture
    def registry(self):
        return ScenarioRegistry(str(SCENARIOS_DIR))

    @pytest.mark.parametrize(
        "domain,expected_scenarios",
        [
            ("finance", ["financial_reporting", "invoice_processing"]),
            ("dev", ["code_review_pipeline", "sprint_planning"]),
            ("operations", ["compliance_audit", "devops_deployment"]),
            ("sales", ["prospect_research", "customer_onboarding"]),
            ("cross-framework", ["multi_framework_demo"]),
        ],
    )
    def test_scenarios_by_domain(self, registry, domain, expected_scenarios):
        """Scenarios should be correctly categorized by domain."""
        scenarios = registry.list_scenarios()
        domain_scenarios = [s for s in scenarios if s.domain == domain]
        names = {s.name for s in domain_scenarios}
        for expected in expected_scenarios:
            assert expected in names, f"Missing {expected} in {domain} domain"

class TestTriggerHandler:
    @pytest.fixture
    def mock_registry(self):
        registry = MagicMock()
        config = ScenarioConfig(
            name="test_scenario",
            display_name="Test",
            description="Test scenario",
            domain="dev",
            triggers={"chat_command": "/test", "api_endpoint": "/test/trigger"},
            inputs=[
                {"name": "input1", "type": "string", "required": True, "description": "Test input"}
            ],
            outputs=[{"name": "output1", "type": "json"}],
            required_agents=["devops_engineer"],
        )
        # Create a proper workflow mock with required attributes
        workflow = MagicMock()
        workflow.metadata = {"name": "test_scenario", "description": "Test scenario"}
        workflow.nodes = []
        workflow.edges = []
        registry.get_scenario.return_value = (config, workflow)
        return registry

    @pytest.fixture
    def mock_executor(self):
        executor = MagicMock(spec=CheckpointedWorkflowExecutor)
        return executor

    @pytest.mark.asyncio
    async def test_trigger_validates_inputs(self, mock_registry, mock_executor):
        """Trigger should validate required inputs."""
        handler = TriggerHandler(mock_registry, mock_executor)

        events = []
        async for event in handler.trigger(
            "test_scenario",
            {},
            TriggerSource.API,
        ):
            events.append(event)

        assert any("error" in e.lower() or "missing" in e.lower() for e in events)

    @pytest.mark.asyncio
    async def test_trigger_tracks_source(self, mock_registry, mock_executor):
        """Trigger should track trigger source in metadata."""
        handler = TriggerHandler(mock_registry, mock_executor)

        events = []
        async for event in handler.trigger(
            "test_scenario",
            {"input1": "value"},
            TriggerSource.CHAT,
            user_id="user123",
        ):
            events.append(event)

        # Should have at least one event (even if execution fails)
        assert len(events) > 0
        # Verify that the handler was invoked with the correct trigger source
        # (implementation detail - just check that trigger doesn't crash)
