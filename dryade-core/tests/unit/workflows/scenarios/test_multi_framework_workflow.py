from pathlib import Path

import pytest

from core.workflows.scenarios import ScenarioConfig
from core.workflows.schema import WorkflowSchema

SCENARIOS_DIR = Path(__file__).resolve().parents[5] / "workflows" / "scenarios"

class TestMultiFrameworkDemoWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "multi_framework_demo" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "multi_framework_demo" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_uses_crewai_agent(self, workflow):
        """Excel Analyst is CrewAI framework."""
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        agents = [n.data.agent for n in task_nodes if hasattr(n.data, "agent")]
        assert "excel_analyst" in agents

    def test_workflow_uses_langchain_agent(self, workflow):
        """KPI Monitor is LangChain framework."""
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        agents = [n.data.agent for n in task_nodes if hasattr(n.data, "agent")]
        assert "kpi_monitor" in agents

    def test_workflow_uses_adk_agent(self, workflow):
        """Project Manager is ADK framework."""
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        agents = [n.data.agent for n in task_nodes if hasattr(n.data, "agent")]
        assert "project_manager" in agents

    def test_workflow_has_framework_transitions(self, workflow):
        """Verify there are transitions between different framework agents."""
        edges = {(e.source, e.target) for e in workflow.edges}
        assert ("analyze_data_crewai", "monitor_metrics_langchain") in edges
        assert ("monitor_metrics_langchain", "assess_impact") in edges

    def test_workflow_has_all_three_frameworks(self, workflow):
        """Verify all three frameworks are represented."""
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        agents = {n.data.agent for n in task_nodes if hasattr(n.data, "agent")}
        assert len(agents) >= 3

    def test_config_has_four_required_agents(self, config):
        assert len(config.required_agents) >= 4
