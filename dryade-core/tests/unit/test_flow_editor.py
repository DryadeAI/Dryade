# Tests for core.flows.editor (migrated from plugin Phase 222).

"""Unit tests for flow editor business logic."""

import pytest

from core.flows.editor import (
    FlowChange,
    FlowDefinition,
    FlowEdge,
    FlowNode,
    FlowValidationResult,
    NodeType,
    apply_change,
    generate_flow_code,
    validate_flow,
)

def _make_flow(nodes=None, edges=None, name="TestFlow", flow_id="flow-1"):
    """Helper to build a FlowDefinition."""
    if nodes is None:
        nodes = [
            FlowNode(id="start_1", type=NodeType.START),
            FlowNode(id="task_1", type=NodeType.TASK, agent="agent-a", label="Do work"),
            FlowNode(id="end_1", type=NodeType.END),
        ]
    if edges is None:
        edges = [
            FlowEdge(id="e1", source="start_1", target="task_1"),
            FlowEdge(id="e2", source="task_1", target="end_1"),
        ]
    return FlowDefinition(id=flow_id, name=name, nodes=nodes, edges=edges)

@pytest.mark.unit
class TestFlowValidation:
    """Test validate_flow with valid and invalid flow definitions."""

    def test_valid_flow_no_errors(self):
        flow = _make_flow()
        result = validate_flow(flow)
        assert result.valid is True
        assert result.errors == []

    def test_missing_start_node_error(self):
        flow = _make_flow(
            nodes=[
                FlowNode(id="task_1", type=NodeType.TASK, agent="a"),
                FlowNode(id="end_1", type=NodeType.END),
            ],
            edges=[FlowEdge(id="e1", source="task_1", target="end_1")],
        )
        result = validate_flow(flow)
        assert result.valid is False
        assert any("start node" in e for e in result.errors)

    def test_multiple_start_nodes_warning(self):
        flow = _make_flow(
            nodes=[
                FlowNode(id="s1", type=NodeType.START),
                FlowNode(id="s2", type=NodeType.START),
                FlowNode(id="end_1", type=NodeType.END),
            ],
            edges=[],
        )
        result = validate_flow(flow)
        assert result.valid is True  # warning, not error
        assert any("multiple start" in w for w in result.warnings)

    def test_no_end_node_warning(self):
        flow = _make_flow(
            nodes=[
                FlowNode(id="s1", type=NodeType.START),
                FlowNode(id="t1", type=NodeType.TASK, agent="a"),
            ],
            edges=[FlowEdge(id="e1", source="s1", target="t1")],
        )
        result = validate_flow(flow)
        assert result.valid is True
        assert any("no end node" in w for w in result.warnings)

    def test_duplicate_node_ids_error(self):
        flow = _make_flow(
            nodes=[
                FlowNode(id="dup", type=NodeType.START),
                FlowNode(id="dup", type=NodeType.END),
            ],
            edges=[],
        )
        result = validate_flow(flow)
        assert result.valid is False
        assert any("unique" in e for e in result.errors)

    def test_edge_references_unknown_source(self):
        flow = _make_flow(
            nodes=[FlowNode(id="s1", type=NodeType.START)],
            edges=[FlowEdge(id="e1", source="missing", target="s1")],
        )
        result = validate_flow(flow)
        assert result.valid is False
        assert any("unknown source" in e for e in result.errors)

    def test_task_without_agent_warning(self):
        flow = _make_flow(
            nodes=[
                FlowNode(id="s1", type=NodeType.START),
                FlowNode(id="t1", type=NodeType.TASK),  # no agent
                FlowNode(id="end_1", type=NodeType.END),
            ],
            edges=[],
        )
        result = validate_flow(flow)
        assert any("no assigned agent" in w for w in result.warnings)

@pytest.mark.unit
class TestApplyChange:
    """Test apply_change adds/removes/updates nodes and edges."""

    def test_add_node(self):
        flow = _make_flow()
        new_node = FlowNode(id="task_2", type=NodeType.TASK, agent="agent-b")
        change = FlowChange(operation="add_node", node=new_node)
        updated = apply_change(flow, change)
        assert len(updated.nodes) == len(flow.nodes) + 1
        assert any(n.id == "task_2" for n in updated.nodes)

    def test_remove_node_and_connected_edges(self):
        flow = _make_flow()
        change = FlowChange(operation="remove_node", node_id="task_1")
        updated = apply_change(flow, change)
        assert not any(n.id == "task_1" for n in updated.nodes)
        # Edges connected to task_1 should also be removed
        for edge in updated.edges:
            assert edge.source != "task_1"
            assert edge.target != "task_1"

    def test_update_node(self):
        flow = _make_flow()
        updated_node = FlowNode(
            id="task_1", type=NodeType.TASK, agent="agent-updated", label="Updated"
        )
        change = FlowChange(operation="update_node", node=updated_node)
        updated = apply_change(flow, change)
        task = next(n for n in updated.nodes if n.id == "task_1")
        assert task.agent == "agent-updated"
        assert task.label == "Updated"

    def test_add_edge(self):
        flow = _make_flow()
        new_edge = FlowEdge(id="e3", source="start_1", target="end_1")
        change = FlowChange(operation="add_edge", edge=new_edge)
        updated = apply_change(flow, change)
        assert len(updated.edges) == len(flow.edges) + 1

    def test_remove_edge(self):
        flow = _make_flow()
        change = FlowChange(operation="remove_edge", edge_id="e1")
        updated = apply_change(flow, change)
        assert not any(e.id == "e1" for e in updated.edges)

@pytest.mark.unit
class TestPydanticModels:
    """Test FlowNode/FlowEdge pydantic models validate correctly."""

    def test_flow_node_defaults(self):
        node = FlowNode(id="n1", type=NodeType.START)
        assert node.position == {"x": 0, "y": 0}
        assert node.data == {}
        assert node.agent is None

    def test_flow_edge_with_condition(self):
        edge = FlowEdge(id="e1", source="s", target="t", condition="x > 5")
        assert edge.condition == "x > 5"

    def test_flow_validation_result_model(self):
        result = FlowValidationResult(valid=True)
        assert result.errors == []
        assert result.warnings == []

    def test_node_type_enum_values(self):
        assert NodeType.START.value == "start"
        assert NodeType.TASK.value == "task"
        assert NodeType.ROUTER.value == "router"
        assert NodeType.END.value == "end"

@pytest.mark.unit
class TestGenerateFlowCode:
    """Test generate_flow_code produces valid Python template."""

    def test_generates_class_code(self):
        flow = _make_flow(name="MyFlow")
        code = generate_flow_code(flow)
        assert "class MyFlowState(BaseModel):" in code
        assert "class MyFlowFlow(Flow[MyFlowState]):" in code
        assert "@start()" in code

    def test_generates_task_listeners(self):
        flow = _make_flow()
        code = generate_flow_code(flow)
        assert "@listen(" in code
        assert "def task_1(self" in code

    def test_includes_description(self):
        flow = _make_flow(name="Demo")
        flow.description = "A demo flow"
        code = generate_flow_code(flow)
        assert "A demo flow" in code
