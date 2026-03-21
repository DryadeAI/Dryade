from pathlib import Path

import pytest

from core.workflows.scenarios import ScenarioConfig
from core.workflows.schema import WorkflowSchema

SCENARIOS_DIR = Path("workflows/scenarios")

class TestComplianceAuditWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "compliance_audit" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "compliance_audit" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_8_steps(self, workflow):
        # start, load, scan, gather, assess, check, escalate/report, store, end
        assert len(workflow.nodes) >= 8

    def test_workflow_uses_compliance_auditor(self, workflow):
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        agents = [n.data.agent for n in task_nodes if hasattr(n.data, "agent")]
        assert "compliance_auditor" in agents

    def test_workflow_has_critical_finding_branch(self, workflow):
        # Router should branch to escalate_critical
        router_edges = [e for e in workflow.edges if e.source == "check_findings"]
        targets = {e.target for e in router_edges}
        assert "escalate_critical" in targets

    def test_config_has_framework_input(self, config):
        inputs = {i.name: i for i in config.inputs}
        assert "framework" in inputs
        assert inputs["framework"].required is True

class TestDevOpsDeploymentWorkflow:
    @pytest.fixture
    def workflow(self):
        path = SCENARIOS_DIR / "devops_deployment" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        import yaml

        path = SCENARIOS_DIR / "devops_deployment" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_preflight_checks(self, workflow):
        nodes = {n.id for n in workflow.nodes}
        assert "preflight_checks" in nodes

    def test_workflow_has_canary_deployment(self, workflow):
        nodes = {n.id for n in workflow.nodes}
        assert "deploy_canary" in nodes
        assert "verify_canary" in nodes

    def test_workflow_has_rollback_path(self, workflow):
        # verify_canary router should branch to rollback
        verify_edges = [e for e in workflow.edges if e.source == "verify_canary"]
        targets = {e.target for e in verify_edges}
        assert "rollback" in targets

    def test_workflow_has_post_deploy_monitoring(self, workflow):
        nodes = {n.id for n in workflow.nodes}
        assert "post_deploy_monitoring" in nodes

    def test_config_has_environment_input(self, config):
        inputs = {i.name: i for i in config.inputs}
        assert "environment" in inputs
        assert inputs["environment"].required is True

    def test_config_uses_kpi_monitor(self, config):
        assert "kpi_monitor" in config.required_agents
