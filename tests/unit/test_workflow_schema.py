"""Unit tests for workflow schema validation."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from core.workflows.schema import (
    RouterNodeData,
    WorkflowSchema,
)

# Mock agent registry for tests
@pytest.fixture
def mock_agents():
    """Mock the list_agents function to return test agents."""
    mock_cards = [
        MagicMock(name="summarizer"),
        MagicMock(name="code_analyst"),
        MagicMock(name="security_expert"),
    ]
    # Set the name attribute properly for MagicMock
    mock_cards[0].name = "summarizer"
    mock_cards[1].name = "code_analyst"
    mock_cards[2].name = "security_expert"

    with patch("core.workflows.schema.list_agents", return_value=mock_cards):
        yield mock_cards

@pytest.fixture
def simple_workflow():
    """Create a simple valid workflow: start -> task -> end."""
    return {
        "version": "1.0.0",
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}, "position": {"x": 0, "y": 0}},
            {
                "id": "task_1",
                "type": "task",
                "data": {"agent": "summarizer", "task": "Summarize the document"},
                "position": {"x": 0, "y": 100},
            },
            {"id": "end_1", "type": "end", "data": {}, "position": {"x": 0, "y": 200}},
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "task_1"},
            {"id": "e2", "source": "task_1", "target": "end_1"},
        ],
    }

@pytest.fixture
def complex_workflow():
    """Create a workflow with routing: start -> task -> router -> [task, task] -> end."""
    return {
        "version": "1.0.0",
        "nodes": [
            {"id": "start_1", "type": "start", "data": {}, "position": {"x": 250, "y": 0}},
            {
                "id": "task_analyze",
                "type": "task",
                "data": {"agent": "code_analyst", "task": "Analyze code"},
                "position": {"x": 250, "y": 100},
            },
            {
                "id": "router_1",
                "type": "router",
                "data": {
                    "condition": "Check severity",
                    "branches": [
                        {"name": "critical", "condition": "Critical issues"},
                        {"name": "minor", "condition": "Minor issues"},
                    ],
                },
                "position": {"x": 250, "y": 200},
            },
            {
                "id": "task_critical",
                "type": "task",
                "data": {"agent": "security_expert", "task": "Fix critical issues"},
                "position": {"x": 100, "y": 300},
            },
            {
                "id": "task_minor",
                "type": "task",
                "data": {"agent": "code_analyst", "task": "Fix minor issues"},
                "position": {"x": 400, "y": 300},
            },
            {"id": "end_1", "type": "end", "data": {}, "position": {"x": 250, "y": 400}},
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "task_analyze"},
            {"id": "e2", "source": "task_analyze", "target": "router_1"},
            {"id": "e3", "source": "router_1", "target": "task_critical", "type": "conditional"},
            {"id": "e4", "source": "router_1", "target": "task_minor", "type": "conditional"},
            {"id": "e5", "source": "task_critical", "target": "end_1"},
            {"id": "e6", "source": "task_minor", "target": "end_1"},
        ],
    }

class TestValidWorkflows:
    """Tests for valid workflow schemas."""

    def test_valid_simple_workflow(self, simple_workflow, mock_agents):
        """Single task workflow validates successfully."""
        schema = WorkflowSchema(**simple_workflow)
        assert len(schema.nodes) == 3
        assert len(schema.edges) == 2
        assert schema.version == "1.0.0"

    def test_valid_complex_workflow(self, complex_workflow, mock_agents):
        """Multi-task with router validates successfully."""
        schema = WorkflowSchema(**complex_workflow)
        assert len(schema.nodes) == 6
        assert len(schema.edges) == 6
        # Check router has 2 branches
        router = next(n for n in schema.nodes if n.type == "router")
        # Data may be dict or RouterNodeData depending on validation
        if isinstance(router.data, dict):
            assert router.data.get("condition") == "Check severity"
        else:
            assert router.data.condition == "Check severity"

class TestInvalidStartNodes:
    """Tests for start node validation."""

    def test_missing_start_node(self, mock_agents):
        """Workflow without start node fails validation."""
        workflow = {
            "nodes": [
                {"id": "task_1", "type": "task", "data": {"agent": "summarizer", "task": "Test"}},
                {"id": "end_1", "type": "end", "data": {}},
            ],
            "edges": [{"id": "e1", "source": "task_1", "target": "end_1"}],
        }
        with pytest.raises(ValidationError) as exc_info:
            WorkflowSchema(**workflow)
        assert "start node" in str(exc_info.value).lower()

    def test_multiple_start_nodes(self, mock_agents):
        """Workflow with 2+ start nodes fails validation."""
        workflow = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {"id": "start_2", "type": "start", "data": {}},
                {"id": "end_1", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start_1", "target": "end_1"},
                {"id": "e2", "source": "start_2", "target": "end_1"},
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            WorkflowSchema(**workflow)
        assert "start node" in str(exc_info.value).lower()

class TestGraphStructure:
    """Tests for graph structure validation."""

    def test_unreachable_nodes(self, mock_agents):
        """Node not connected to start fails validation."""
        workflow = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {"id": "task_1", "type": "task", "data": {"agent": "summarizer", "task": "Test"}},
                {
                    "id": "orphan_task",
                    "type": "task",
                    "data": {"agent": "summarizer", "task": "Orphan"},
                },
                {"id": "end_1", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start_1", "target": "task_1"},
                {"id": "e2", "source": "task_1", "target": "end_1"},
                # orphan_task has no incoming edge from reachable nodes
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            WorkflowSchema(**workflow)
        assert "reachable" in str(exc_info.value).lower() or "orphan_task" in str(exc_info.value)

    def test_cyclic_graph(self, mock_agents):
        """Circular dependencies fail validation."""
        workflow = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {"id": "task_1", "type": "task", "data": {"agent": "summarizer", "task": "Test 1"}},
                {"id": "task_2", "type": "task", "data": {"agent": "summarizer", "task": "Test 2"}},
                {"id": "end_1", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start_1", "target": "task_1"},
                {"id": "e2", "source": "task_1", "target": "task_2"},
                {"id": "e3", "source": "task_2", "target": "task_1"},  # Creates cycle
                {"id": "e4", "source": "task_2", "target": "end_1"},
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            WorkflowSchema(**workflow)
        assert "cycle" in str(exc_info.value).lower()

class TestAgentValidation:
    """Tests for agent registry validation."""

    def test_invalid_agent_name(self, mock_agents):
        """Non-existent agent fails validation via validate_agents()."""
        workflow = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {
                    "id": "task_1",
                    "type": "task",
                    "data": {"agent": "nonexistent_agent", "task": "Test"},
                },
                {"id": "end_1", "type": "end", "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start_1", "target": "task_1"},
                {"id": "e2", "source": "task_1", "target": "end_1"},
            ],
        }
        schema = WorkflowSchema(**workflow)
        invalid_agents = schema.validate_agents()
        assert "nonexistent_agent" in invalid_agents

class TestRouterValidation:
    """Tests for router node validation."""

    def test_router_single_branch(self, mock_agents):
        """Router with <2 branches fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            RouterNodeData(
                condition="Test condition",
                branches=[{"name": "only_one", "condition": "Single branch"}],
            )
        assert "2 branches" in str(exc_info.value).lower()

class TestEndNodeValidation:
    """Tests for end node validation."""

    def test_end_node_with_edges(self, mock_agents):
        """End node with outgoing edges fails validation."""
        workflow = {
            "nodes": [
                {"id": "start_1", "type": "start", "data": {}},
                {"id": "end_1", "type": "end", "data": {}},
                {
                    "id": "task_after_end",
                    "type": "task",
                    "data": {"agent": "summarizer", "task": "Test"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start_1", "target": "end_1"},
                {"id": "e2", "source": "end_1", "target": "task_after_end"},  # Invalid
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            WorkflowSchema(**workflow)
        assert "end node" in str(exc_info.value).lower()

class TestSchemaVersion:
    """Tests for schema versioning."""

    def test_schema_version(self, simple_workflow, mock_agents):
        """Version field defaults to '1.0.0'."""
        # Remove version to test default
        del simple_workflow["version"]
        schema = WorkflowSchema(**simple_workflow)
        assert schema.version == "1.0.0"
