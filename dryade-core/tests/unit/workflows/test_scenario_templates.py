"""Unit tests for scenario template_ref resolution and registry filtering.

Tests:
  - ScenarioConfig.template_ref field loading from config.yaml
  - ScenarioRegistry.get_scenario() resolves template_ref to template workflow
  - All template_ref values point to valid template directories
  - Internal scenarios (underscore-prefixed) are filtered from list_scenarios()
  - Distinct scenarios (sprint_planning, etc.) have no template_ref
"""

from pathlib import Path

import pytest

from core.workflows.scenarios import ScenarioRegistry

# Resolve the real scenarios directory — same pattern as scenarios/conftest.py
SCENARIOS_DIR = Path(__file__).resolve().parents[4] / "workflows" / "scenarios"

# Skip all tests in this module if the scenarios dir is not available
# (standalone dryade-core checkout in CI without parent monorepo)
pytestmark = pytest.mark.skipif(
    not SCENARIOS_DIR.is_dir(),
    reason=f"Workflow scenarios not available at {SCENARIOS_DIR} (standalone checkout)",
)

@pytest.fixture
def registry() -> ScenarioRegistry:
    """Create a ScenarioRegistry pointing at the real scenarios directory."""
    return ScenarioRegistry(SCENARIOS_DIR)

class TestTemplateRefFieldInConfig:
    """Tests that template_ref values are correctly loaded from config.yaml files."""

    def test_document_qa_template_ref(self, registry: ScenarioRegistry) -> None:
        """document_qa should reference the linear-2task template."""
        config, _ = registry.get_scenario("document_qa")
        assert config.template_ref == "_templates/linear-2task"

    def test_email_summarizer_template_ref(self, registry: ScenarioRegistry) -> None:
        """email_summarizer should reference the linear-2task template."""
        config, _ = registry.get_scenario("email_summarizer")
        assert config.template_ref == "_templates/linear-2task"

    def test_rag_pipeline_template_ref(self, registry: ScenarioRegistry) -> None:
        """rag_pipeline should reference the linear-3task template."""
        config, _ = registry.get_scenario("rag_pipeline")
        assert config.template_ref == "_templates/linear-3task"

    def test_skills_example_template_ref(self, registry: ScenarioRegistry) -> None:
        """skills_example should reference the linear-3task template."""
        config, _ = registry.get_scenario("skills_example")
        assert config.template_ref == "_templates/linear-3task"

    def test_mcp_integration_demo_template_ref(self, registry: ScenarioRegistry) -> None:
        """mcp_integration_demo should reference the linear-3task template."""
        config, _ = registry.get_scenario("mcp_integration_demo")
        assert config.template_ref == "_templates/linear-3task"

    def test_multi_agent_research_template_ref(self, registry: ScenarioRegistry) -> None:
        """multi_agent_research should reference the linear-3task template."""
        config, _ = registry.get_scenario("multi_agent_research")
        assert config.template_ref == "_templates/linear-3task"

    def test_customer_support_bot_template_ref(self, registry: ScenarioRegistry) -> None:
        """customer_support_bot should reference the linear-support template."""
        config, _ = registry.get_scenario("customer_support_bot")
        assert config.template_ref == "_templates/linear-support"

    def test_discord_support_bot_template_ref(self, registry: ScenarioRegistry) -> None:
        """discord_support_bot should reference the linear-support template."""
        config, _ = registry.get_scenario("discord_support_bot")
        assert config.template_ref == "_templates/linear-support"

    def test_workflow_example_template_ref(self, registry: ScenarioRegistry) -> None:
        """workflow_example should reference the linear-support template."""
        config, _ = registry.get_scenario("workflow_example")
        assert config.template_ref == "_templates/linear-support"

class TestTemplateResolution:
    """Tests that ScenarioRegistry resolves template_ref to load template workflow.json."""

    def test_document_qa_loads_linear_2task_workflow(self, registry: ScenarioRegistry) -> None:
        """document_qa with template_ref should use linear-2task workflow (4 nodes)."""
        _, workflow = registry.get_scenario("document_qa")
        # linear-2task template has 4 nodes: start, task_1, task_2, end
        assert len(workflow.nodes) == 4
        node_ids = {n.id for n in workflow.nodes}
        assert "start" in node_ids
        assert "end" in node_ids

    def test_email_summarizer_loads_linear_2task_workflow(self, registry: ScenarioRegistry) -> None:
        """email_summarizer with template_ref should use linear-2task workflow (4 nodes)."""
        _, workflow = registry.get_scenario("email_summarizer")
        assert len(workflow.nodes) == 4

    def test_rag_pipeline_loads_linear_3task_workflow(self, registry: ScenarioRegistry) -> None:
        """rag_pipeline with template_ref should use linear-3task workflow (5 nodes)."""
        _, workflow = registry.get_scenario("rag_pipeline")
        # linear-3task template has 5 nodes: start, task_1, task_2, task_3, end
        assert len(workflow.nodes) == 5

    def test_customer_support_bot_loads_linear_support_workflow(
        self, registry: ScenarioRegistry
    ) -> None:
        """customer_support_bot with template_ref should use linear-support workflow (6 nodes)."""
        _, workflow = registry.get_scenario("customer_support_bot")
        # linear-support template has 6 nodes: start, intake, process, resolve, followup, end
        assert len(workflow.nodes) == 6

    def test_resolved_workflow_matches_template_directly(self, registry: ScenarioRegistry) -> None:
        """document_qa workflow node count should match linear-2task template directly loaded."""
        _, doc_workflow = registry.get_scenario("document_qa")
        # Clear cache to reload template independently
        fresh_reg = ScenarioRegistry(SCENARIOS_DIR)
        _, template_workflow = fresh_reg.get_scenario("_templates/linear-2task")
        assert len(doc_workflow.nodes) == len(template_workflow.nodes)
        assert len(doc_workflow.edges) == len(template_workflow.edges)

class TestAllTemplateRefsValid:
    """Tests that all scenarios with template_ref point to valid template directories."""

    def test_all_template_refs_resolve(self, registry: ScenarioRegistry) -> None:
        """Every scenario with template_ref should have a valid template workflow.json."""
        configs = registry.list_scenarios()
        for config in configs:
            if config.template_ref is None:
                continue
            template_dir = SCENARIOS_DIR / config.template_ref
            assert template_dir.is_dir(), (
                f"Scenario '{config.name}' has template_ref '{config.template_ref}' "
                f"but template directory does not exist: {template_dir}"
            )
            template_workflow = template_dir / "workflow.json"
            assert template_workflow.exists(), (
                f"Scenario '{config.name}' has template_ref '{config.template_ref}' "
                f"but template workflow.json not found: {template_workflow}"
            )

    def test_linear_2task_template_valid(self, registry: ScenarioRegistry) -> None:
        """linear-2task template should load as a valid WorkflowSchema."""
        config, workflow = registry.get_scenario("_templates/linear-2task")
        assert config.name == "_templates/linear-2task"
        assert len(workflow.nodes) == 4
        assert len(workflow.edges) == 3

    def test_linear_3task_template_valid(self, registry: ScenarioRegistry) -> None:
        """linear-3task template should load as a valid WorkflowSchema."""
        config, workflow = registry.get_scenario("_templates/linear-3task")
        assert config.name == "_templates/linear-3task"
        assert len(workflow.nodes) == 5
        assert len(workflow.edges) == 4

    def test_linear_support_template_valid(self, registry: ScenarioRegistry) -> None:
        """linear-support template should load as a valid WorkflowSchema."""
        config, workflow = registry.get_scenario("_templates/linear-support")
        assert config.name == "_templates/linear-support"
        assert len(workflow.nodes) == 6
        assert len(workflow.edges) == 5

class TestInternalScenariosFilteredFromList:
    """Tests that underscore-prefixed internal scenarios are excluded from list_scenarios()."""

    def test_no_underscore_names_in_list(self, registry: ScenarioRegistry) -> None:
        """list_scenarios() should not return any scenario whose name starts with '_'."""
        configs = registry.list_scenarios()
        internal = [c.name for c in configs if c.name.startswith("_")]
        assert internal == [], f"list_scenarios() returned internal scenario(s): {internal}"

    def test_templates_not_in_list(self, registry: ScenarioRegistry) -> None:
        """Template scenarios (_templates/*) should not appear in list_scenarios()."""
        configs = registry.list_scenarios()
        names = {c.name for c in configs}
        assert "_templates/linear-2task" not in names
        assert "_templates/linear-3task" not in names
        assert "_templates/linear-support" not in names

    def test_regular_scenarios_present_in_list(self, registry: ScenarioRegistry) -> None:
        """Regular scenarios should still appear in list_scenarios()."""
        configs = registry.list_scenarios()
        names = {c.name for c in configs}
        # A sample of well-known scenarios that must be present
        assert "document_qa" in names
        assert "sprint_planning" in names
        assert "customer_support_bot" in names

class TestDistinctScenariosNoTemplateRef:
    """Tests that structurally distinct scenarios do NOT have template_ref set."""

    DISTINCT_SCENARIOS = [
        "sprint_planning",
        "financial_reporting",
        "invoice_processing",
        "data_pipeline",
        "devops_deployment",
        "prospect_research",
        "multi_framework_demo",
        "compliance_audit",
        "customer_onboarding",
        "code_review_pipeline",
    ]

    @pytest.mark.parametrize("scenario_name", DISTINCT_SCENARIOS)
    def test_distinct_scenario_has_no_template_ref(
        self, registry: ScenarioRegistry, scenario_name: str
    ) -> None:
        """Distinct scenarios should have template_ref=None (they own their workflow.json)."""
        config, _ = registry.get_scenario(scenario_name)
        assert config.template_ref is None, (
            f"Scenario '{scenario_name}' should not have a template_ref, "
            f"but got: {config.template_ref}"
        )
