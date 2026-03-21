from pathlib import Path

import pytest

from core.workflows.scenarios import ScenarioConfig
from core.workflows.schema import WorkflowSchema

SCENARIOS_DIR = Path(__file__).resolve().parents[5] / "workflows" / "scenarios"

class TestCodeReviewPipelineWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "code_review_pipeline" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "code_review_pipeline" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_quality_gate_router(self, workflow):
        routers = [n for n in workflow.nodes if n.type == "router"]
        assert len(routers) == 1
        assert routers[0].id == "quality_check"

    def test_workflow_has_three_outcome_branches(self, workflow):
        router_edges = [e for e in workflow.edges if e.source == "quality_check"]
        assert len(router_edges) == 3

    def test_all_outcomes_reach_end(self, workflow):
        # auto_approve, request_changes, escalate_review all reach end
        end_edges = [e for e in workflow.edges if e.target == "end"]
        assert len(end_edges) == 3

    def test_config_has_pr_url_input(self, config):
        inputs = {i.name: i for i in config.inputs}
        assert "pr_url" in inputs
        assert inputs["pr_url"].type == "string"

class TestSprintPlanningWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "sprint_planning" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "sprint_planning" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_10_plus_nodes(self, workflow):
        assert len(workflow.nodes) >= 10

    def test_workflow_has_parallel_fan_out(self, workflow):
        # load_context should have multiple outgoing edges (fan-out)
        load_context_edges = [e for e in workflow.edges if e.source == "load_context"]
        assert len(load_context_edges) >= 3

    def test_workflow_has_fan_in_to_draft_plan(self, workflow):
        # draft_sprint_plan should have multiple incoming edges (fan-in)
        draft_plan_edges = [e for e in workflow.edges if e.target == "draft_sprint_plan"]
        assert len(draft_plan_edges) >= 3

    def test_workflow_has_validation_retry_pattern(self, workflow):
        # adjust_plan should have retry router pattern (no cycle)
        adjust_to_check = [
            e for e in workflow.edges if e.source == "adjust_plan" and e.target == "adjust_check"
        ]
        assert len(adjust_to_check) == 1
        # adjust_check router should route to success or escalate
        check_edges = [e for e in workflow.edges if e.source == "adjust_check"]
        assert len(check_edges) == 2

    def test_config_has_team_id_input(self, config):
        inputs = {i.name: i for i in config.inputs}
        assert "team_id" in inputs
        assert inputs["team_id"].required is True

    def test_config_uses_four_agents(self, config):
        assert len(config.required_agents) == 4
        assert "project_manager" in config.required_agents
