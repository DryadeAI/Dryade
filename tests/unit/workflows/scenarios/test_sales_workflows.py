from pathlib import Path

import pytest

from core.workflows.scenarios import ScenarioConfig
from core.workflows.schema import WorkflowSchema

SCENARIOS_DIR = Path("workflows/scenarios")

class TestProspectResearchWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "prospect_research" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "prospect_research" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_parallel_research(self, workflow):
        # plan_research should fan out to multiple research tasks
        plan_edges = [e for e in workflow.edges if e.source == "plan_research"]
        assert len(plan_edges) >= 3

    def test_workflow_has_fan_in_to_synthesize(self, workflow):
        # synthesize_findings should have multiple inputs
        synth_edges = [e for e in workflow.edges if e.target == "synthesize_findings"]
        assert len(synth_edges) >= 3

    def test_workflow_uses_sales_intelligence(self, workflow):
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        agents = [n.data.agent for n in task_nodes if hasattr(n.data, "agent")]
        assert agents.count("sales_intelligence") >= 3

    def test_config_has_company_input(self, config):
        inputs = {i.name: i for i in config.inputs}
        assert "company_name" in inputs

class TestCustomerOnboardingWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "customer_onboarding" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "customer_onboarding" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_8_steps(self, workflow):
        # 8 task/router nodes plus start and end
        non_terminal = [n for n in workflow.nodes if n.type not in ["start", "end"]]
        assert len(non_terminal) >= 8

    def test_workflow_is_mostly_sequential(self, workflow):
        # Most nodes should have exactly one incoming edge (sequential)
        for node in workflow.nodes:
            if node.type not in ["start", "router"]:
                incoming = [e for e in workflow.edges if e.target == node.id]
                # Allow up to 2 (for nodes after router merge)
                assert len(incoming) <= 2

    def test_workflow_has_verification_gate(self, workflow):
        routers = [n for n in workflow.nodes if n.type == "router"]
        assert len(routers) >= 1
        assert any("verify" in r.id for r in routers)

    def test_workflow_has_escalation_path(self, workflow):
        edges = {(e.source, e.target) for e in workflow.edges}
        assert ("verify_setup", "escalate_technical") in edges

    def test_config_has_contract_file_input(self, config):
        inputs = {i.name: i for i in config.inputs}
        assert "contract_file" in inputs
        assert inputs["contract_file"].type == "file"

    def test_config_uses_four_agents(self, config):
        assert len(config.required_agents) >= 4
