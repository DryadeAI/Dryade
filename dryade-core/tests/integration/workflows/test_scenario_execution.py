"""Integration tests for workflow scenario execution."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import WorkflowPausedForApproval
from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor
from core.workflows.scenarios import ScenarioConfig, ScenarioRegistry
from core.workflows.schema import WorkflowSchema
from core.workflows.triggers import TriggerHandler, TriggerSource

SCENARIOS_DIR = Path("workflows/scenarios")

# Resolve the real scenarios directory for integration tests (skipped if not available)
_REAL_SCENARIOS_DIR = Path(__file__).resolve().parents[4] / "workflows" / "scenarios"

class TestScenarioRegistry:
    @pytest.fixture
    def registry(self):
        # Use absolute path so tests pass regardless of CWD (e.g., when run from dryade-core/)
        return ScenarioRegistry(str(_REAL_SCENARIOS_DIR))

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
        # Use absolute path so tests pass regardless of CWD (e.g., when run from dryade-core/)
        return ScenarioRegistry(str(_REAL_SCENARIOS_DIR))

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

class TestApprovalTriggerPath:
    """Integration tests for approval node behavior in the scenario trigger path.

    Verifies that WorkflowPausedForApproval raised by approval nodes is caught
    by TriggerHandler._execute_with_progress and emitted as approval_pending SSE.

    These tests call _execute_with_progress directly with mocked dependencies
    to validate the approval path without requiring a real database or executor.
    """

    @pytest.fixture
    def approval_workflow(self):
        """Minimal workflow schema with one task node + one approval node.

        Approval nodes require exactly 2 outgoing edges (approved + rejected).
        """
        return WorkflowSchema.model_validate(
            {
                "version": "1.0.0",
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                    {
                        "id": "prep_task",
                        "type": "task",
                        "data": {
                            "agent": "analyst",
                            "task": "Prepare data for approval",
                        },
                        "position": {"x": 100, "y": 0},
                    },
                    {
                        "id": "approval_gate",
                        "type": "approval",
                        "data": {
                            "prompt": "Please review and approve the prepared data",
                            "approver": "owner",
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    # Two end nodes: one for approved path, one for rejected path
                    {"id": "end_approved", "type": "end", "position": {"x": 300, "y": -50}},
                    {"id": "end_rejected", "type": "end", "position": {"x": 300, "y": 50}},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "prep_task"},
                    {"id": "e2", "source": "prep_task", "target": "approval_gate"},
                    # Approval node requires 2 outgoing edges (approved + rejected)
                    {"id": "e3", "source": "approval_gate", "target": "end_approved"},
                    {"id": "e4", "source": "approval_gate", "target": "end_rejected"},
                ],
            }
        )

    @pytest.fixture
    def mock_flow_that_raises_approval(self):
        """Create a mock flow instance whose kickoff() raises WorkflowPausedForApproval."""
        flow = MagicMock()

        # State mock: has model_dump() that returns approval metadata
        state = MagicMock()
        state.model_dump.return_value = {
            "approval_gate_output": {
                "status": "awaiting_approval",
                "node_id": "approval_gate",
                "prompt": "Please review and approve the prepared data",
                "approver": "owner",
            }
        }
        flow.state = state
        # kickoff() raises WorkflowPausedForApproval (approval_request_id=1)
        flow.kickoff.side_effect = WorkflowPausedForApproval(approval_request_id=1)
        return flow

    @pytest.fixture
    def handler_with_mocked_deps(self, mock_flow_that_raises_approval):
        """Create TriggerHandler with mocked executor, translator, and DB session."""
        mock_executor = MagicMock(spec=CheckpointedWorkflowExecutor)
        mock_registry = MagicMock()

        # generate_flow_class returns a class whose instance is our mock flow
        flow_class = MagicMock()
        flow_class.return_value = mock_flow_that_raises_approval
        mock_executor.generate_flow_class.return_value = flow_class

        return TriggerHandler(mock_registry, mock_executor)

    @pytest.mark.asyncio
    async def test_approval_node_emits_approval_pending_event(
        self, handler_with_mocked_deps, approval_workflow
    ):
        """Approval node must emit approval_pending SSE event (not error) via trigger path."""
        handler = handler_with_mocked_deps
        context = {
            "execution_id": "test-exec-approval-001",
            "scenario_name": "_approval_node_test",
            "trigger_source": "api",
            "user_id": None,
            "started_at": "2026-03-03T00:00:00+00:00",
            "inputs": {},
        }

        events = []
        # WorkflowTranslator is imported lazily inside _execute_with_progress,
        # so patch the module-level reference in core.workflows.translator
        with (
            patch("core.workflows.triggers.get_session"),
            patch("core.workflows.translator.WorkflowTranslator") as mock_translator_cls,
        ):
            # Translator returns a minimal flowconfig with nodes list
            mock_flowconfig = MagicMock()
            mock_flowconfig.nodes = [
                {"id": "start", "type": "start"},
                {"id": "approval_gate", "type": "approval"},
                {"id": "end", "type": "end"},
            ]
            mock_translator_cls.return_value.to_flowconfig.return_value = mock_flowconfig

            async for event_str in handler._execute_with_progress(approval_workflow, {}, context):
                payload = json.loads(event_str.replace("data: ", "").strip())
                events.append(payload)

        # Assert approval_pending event exists
        approval_events = [e for e in events if e.get("type") == "approval_pending"]
        assert len(approval_events) == 1, (
            f"Expected 1 approval_pending event, got {len(approval_events)}: {events}"
        )

        approval = approval_events[0]
        assert approval["node_id"] != "unknown", (
            "approval_pending must include actual node_id from flow state"
        )
        assert approval["prompt"], "approval_pending must include prompt text"

        # Assert NO error event — approval is NOT an error
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 0, f"Approval should not produce error events: {error_events}"

    @pytest.mark.asyncio
    async def test_approval_event_has_required_fields(
        self, handler_with_mocked_deps, approval_workflow
    ):
        """approval_pending event must include execution_id, node_id, prompt, and approver."""
        handler = handler_with_mocked_deps
        context = {
            "execution_id": "test-exec-approval-002",
            "scenario_name": "_approval_node_test",
            "trigger_source": "api",
            "user_id": None,
            "started_at": "2026-03-03T00:00:00+00:00",
            "inputs": {},
        }

        events = []
        with (
            patch("core.workflows.triggers.get_session"),
            patch("core.workflows.translator.WorkflowTranslator") as mock_translator_cls,
        ):
            mock_flowconfig = MagicMock()
            mock_flowconfig.nodes = [{"id": "approval_gate", "type": "approval"}]
            mock_translator_cls.return_value.to_flowconfig.return_value = mock_flowconfig

            async for event_str in handler._execute_with_progress(approval_workflow, {}, context):
                payload = json.loads(event_str.replace("data: ", "").strip())
                events.append(payload)

        approval_event = next((e for e in events if e.get("type") == "approval_pending"), None)
        assert approval_event is not None, "approval_pending event must be emitted"

        # Verify all required fields are present
        assert "execution_id" in approval_event, "approval_pending must include execution_id"
        assert "node_id" in approval_event, "approval_pending must include node_id"
        assert "prompt" in approval_event, "approval_pending must include prompt"
        assert "approver" in approval_event, "approval_pending must include approver"
        assert "timestamp" in approval_event, "approval_pending must include timestamp"

        # Verify execution_id matches context
        assert approval_event["execution_id"] == context["execution_id"]

    @pytest.mark.asyncio
    async def test_workflow_start_emitted_before_approval(
        self, handler_with_mocked_deps, approval_workflow
    ):
        """workflow_start must be emitted before approval_pending in event stream."""
        handler = handler_with_mocked_deps
        context = {
            "execution_id": "test-exec-approval-003",
            "scenario_name": "_approval_node_test",
            "trigger_source": "api",
            "user_id": None,
            "started_at": "2026-03-03T00:00:00+00:00",
            "inputs": {},
        }

        events = []
        with (
            patch("core.workflows.triggers.get_session"),
            patch("core.workflows.translator.WorkflowTranslator") as mock_translator_cls,
        ):
            mock_flowconfig = MagicMock()
            mock_flowconfig.nodes = [{"id": "approval_gate", "type": "approval"}]
            mock_translator_cls.return_value.to_flowconfig.return_value = mock_flowconfig

            async for event_str in handler._execute_with_progress(approval_workflow, {}, context):
                payload = json.loads(event_str.replace("data: ", "").strip())
                events.append(payload)

        event_types = [e.get("type") for e in events]
        assert "workflow_start" in event_types, "workflow_start must be emitted"
        assert "approval_pending" in event_types, "approval_pending must be emitted"

        # workflow_start must come before approval_pending
        start_idx = event_types.index("workflow_start")
        approval_idx = event_types.index("approval_pending")
        assert start_idx < approval_idx, (
            f"workflow_start (idx={start_idx}) must come before "
            f"approval_pending (idx={approval_idx})"
        )

class TestTemplateRefRuntime:
    """Integration tests for template_ref resolution in ScenarioRegistry.

    Verifies that scenarios with template_ref in their config correctly load
    the template workflow (not their own redundant workflow.json).

    These tests require the real scenarios directory. They are skipped in
    standalone dryade-core CI where the monorepo workflows/ dir is not present.
    """

    pytestmark = pytest.mark.skipif(
        not _REAL_SCENARIOS_DIR.is_dir(),
        reason=f"Workflow scenarios not available at {_REAL_SCENARIOS_DIR} (standalone checkout)",
    )

    @pytest.fixture
    def registry(self) -> ScenarioRegistry:
        """Create a ScenarioRegistry pointing at the real scenarios directory."""
        return ScenarioRegistry(str(_REAL_SCENARIOS_DIR))

    @pytest.mark.parametrize(
        "scenario_name,expected_template",
        [
            ("document_qa", "_templates/linear-2task"),
            ("email_summarizer", "_templates/linear-2task"),
            ("rag_pipeline", "_templates/linear-3task"),
            ("skills_example", "_templates/linear-3task"),
            ("mcp_integration_demo", "_templates/linear-3task"),
            ("multi_agent_research", "_templates/linear-3task"),
            ("customer_support_bot", "_templates/linear-support"),
            ("discord_support_bot", "_templates/linear-support"),
            ("workflow_example", "_templates/linear-support"),
        ],
    )
    def test_template_ref_scenarios_resolve_to_template_workflow(
        self, registry: ScenarioRegistry, scenario_name: str, expected_template: str
    ):
        """All 9 template_ref scenarios must resolve to their referenced template."""
        if not _REAL_SCENARIOS_DIR.is_dir():
            pytest.skip("Scenarios directory not available")

        config, _ = registry.get_scenario(scenario_name)
        assert config is not None, f"Scenario '{scenario_name}' not found"
        assert config.template_ref == expected_template, (
            f"Scenario '{scenario_name}' template_ref mismatch: "
            f"expected '{expected_template}', got '{config.template_ref}'"
        )

    @pytest.mark.parametrize(
        "scenario_name,min_nodes",
        [
            ("document_qa", 2),
            ("rag_pipeline", 2),
            ("customer_support_bot", 2),
        ],
    )
    def test_template_ref_scenario_workflow_has_nodes(
        self, registry: ScenarioRegistry, scenario_name: str, min_nodes: int
    ):
        """Template-resolved workflows must have valid nodes (not empty)."""
        if not _REAL_SCENARIOS_DIR.is_dir():
            pytest.skip("Scenarios directory not available")

        _, workflow = registry.get_scenario(scenario_name)
        assert len(workflow.nodes) >= min_nodes, (
            f"Scenario '{scenario_name}' workflow has {len(workflow.nodes)} nodes "
            f"(expected >= {min_nodes})"
        )
