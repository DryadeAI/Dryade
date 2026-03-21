"""Unit tests for finance domain workflow scenarios.

Tests validate workflow structure, config correctness, and routing logic for:
- financial_reporting: Linear 5-step workflow with context accumulation
- invoice_processing: Branching workflow with retry and escalation paths
"""

from pathlib import Path

import pytest
import yaml

from core.workflows.scenarios import ScenarioConfig
from core.workflows.schema import WorkflowSchema

SCENARIOS_DIR = Path("workflows/scenarios")

class TestFinancialReportingWorkflow:
    """Tests for the financial_reporting workflow scenario."""

    @pytest.fixture
    def workflow(self):
        """Load the financial_reporting workflow schema."""
        path = SCENARIOS_DIR / "financial_reporting" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        """Load the financial_reporting scenario config."""
        path = SCENARIOS_DIR / "financial_reporting" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_4_task_nodes(self, workflow):
        """Workflow should have 4 task nodes (extract, analyze, query, generate)."""
        task_nodes = [n for n in workflow.nodes if n.type == "task"]
        assert len(task_nodes) == 4

    def test_workflow_has_5_edges(self, workflow):
        """Workflow should have 5 edges in linear sequence."""
        assert len(workflow.edges) == 5

    def test_workflow_is_linear(self, workflow):
        """Each node (except end) should have exactly one outgoing edge."""
        for node in workflow.nodes:
            if node.type != "end":
                outgoing = [e for e in workflow.edges if e.source == node.id]
                assert len(outgoing) == 1, f"Node {node.id} should have 1 outgoing edge"

    def test_workflow_uses_context_accumulation(self, workflow):
        """Task nodes should reference prior outputs in context."""
        task_nodes = [n for n in workflow.nodes if n.type == "task"]

        # At least one task should have requires in context
        has_requires = False
        for n in task_nodes:
            # node.data can be TaskNodeData model or dict
            if isinstance(n.data, dict):
                context = n.data.get("context", {})
            else:
                # TaskNodeData has context as dict or None
                context = getattr(n.data, "context", None) or {}
            if context.get("requires"):
                has_requires = True
                break
        assert has_requires, "Workflow should use context accumulation pattern"

    def test_config_has_required_triggers(self, config):
        """Config should define chat_command trigger."""
        assert config.triggers.chat_command == "/analyze-report"
        assert config.triggers.api_endpoint is not None

    def test_config_requires_correct_agents(self, config):
        """Config should list required agents."""
        assert "document_processor" in config.required_agents
        assert "excel_analyst" in config.required_agents
        assert "database_analyst" in config.required_agents

    def test_config_has_file_input(self, config):
        """Config should define file input for report."""
        file_inputs = [i for i in config.inputs if i.type == "file"]
        assert len(file_inputs) == 1
        assert file_inputs[0].name == "report_file"

    def test_config_domain_is_finance(self, config):
        """Config domain should be finance."""
        assert config.domain == "finance"

class TestInvoiceProcessingWorkflow:
    """Tests for the invoice_processing workflow scenario."""

    @pytest.fixture
    def workflow(self):
        """Load the invoice_processing workflow schema."""
        path = SCENARIOS_DIR / "invoice_processing" / "workflow.json"
        return WorkflowSchema.model_validate_json(path.read_text())

    @pytest.fixture
    def config(self):
        """Load the invoice_processing scenario config."""
        path = SCENARIOS_DIR / "invoice_processing" / "config.yaml"
        return ScenarioConfig(**yaml.safe_load(path.read_text()))

    def test_workflow_has_router_nodes(self, workflow):
        """Workflow should have 2 router nodes (validate_extraction, retry_check)."""
        router_nodes = [n for n in workflow.nodes if n.type == "router"]
        assert len(router_nodes) == 2

        router_ids = {n.id for n in router_nodes}
        assert "validate_extraction" in router_ids
        assert "retry_check" in router_ids

    def test_workflow_has_retry_path(self, workflow):
        """Workflow should have edge from validate_extraction to retry_extraction."""
        edges = {(e.source, e.target) for e in workflow.edges}
        assert ("validate_extraction", "retry_extraction") in edges

    def test_workflow_has_escalation_path(self, workflow):
        """Workflow should have edge from retry_check to escalate_manual."""
        edges = {(e.source, e.target) for e in workflow.edges}
        assert ("retry_check", "escalate_manual") in edges

    def test_workflow_has_review_path(self, workflow):
        """Workflow should have edge from validate_extraction to flag_for_review."""
        edges = {(e.source, e.target) for e in workflow.edges}
        assert ("validate_extraction", "flag_for_review") in edges

    def test_all_paths_reach_end(self, workflow):
        """All terminal branches should reach the end node."""
        end_edges = [e for e in workflow.edges if e.target == "complete"]
        assert len(end_edges) >= 3  # verify, flag_review, escalate all reach end

        # Verify specific terminal nodes connect to complete
        sources = {e.source for e in end_edges}
        assert "verify_against_db" in sources
        assert "flag_for_review" in sources
        assert "escalate_manual" in sources

    def test_router_nodes_have_multiple_outgoing_edges(self, workflow):
        """Router nodes should have at least 2 outgoing edges."""
        router_ids = {n.id for n in workflow.nodes if n.type == "router"}

        for router_id in router_ids:
            outgoing = [e for e in workflow.edges if e.source == router_id]
            assert len(outgoing) >= 2, f"Router {router_id} should have >= 2 outgoing edges"

    def test_config_has_file_input(self, config):
        """Config should define file input for invoice."""
        file_inputs = [i for i in config.inputs if i.type == "file"]
        assert len(file_inputs) == 1
        assert file_inputs[0].name == "invoice_file"

    def test_config_has_chat_command(self, config):
        """Config should define chat_command trigger."""
        assert config.triggers.chat_command == "/process-invoice"

    def test_config_requires_correct_agents(self, config):
        """Config should list required agents."""
        assert "document_processor" in config.required_agents
        assert "database_analyst" in config.required_agents
        assert "project_manager" in config.required_agents

    def test_config_domain_is_finance(self, config):
        """Config domain should be finance."""
        assert config.domain == "finance"
