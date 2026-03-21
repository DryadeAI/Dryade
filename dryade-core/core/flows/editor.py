# Migrated from plugins/starter/flow_editor/editor.py into core (Phase 222).

"""Visual Flow Editor Protocol.

JSON protocol for bidirectional flow editing between frontend and backend.
Target: ~100 LOC
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

class NodeType(str, Enum):
    """Flow node types."""

    START = "start"
    TASK = "task"
    ROUTER = "router"
    END = "end"

class FlowNode(BaseModel):
    """A node in the visual flow."""

    id: str
    type: NodeType
    agent: str | None = None
    tool: str | None = None
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    data: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None

class FlowEdge(BaseModel):
    """An edge connecting two nodes."""

    id: str
    source: str
    target: str
    label: str | None = None
    condition: str | None = None  # For router edges

class FlowDefinition(BaseModel):
    """Complete flow definition for visual editor."""

    id: str
    name: str
    description: str | None = None
    nodes: list[FlowNode]
    edges: list[FlowEdge]
    viewport: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0, "zoom": 1})

class FlowChange(BaseModel):
    """A change operation from the visual editor."""

    operation: Literal["add_node", "remove_node", "update_node", "add_edge", "remove_edge"]
    node: FlowNode | None = None
    edge: FlowEdge | None = None
    node_id: str | None = None
    edge_id: str | None = None

class FlowValidationResult(BaseModel):
    """Result of flow validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

def validate_flow(flow: FlowDefinition) -> FlowValidationResult:
    """Validate a flow definition."""
    errors = []
    warnings = []

    # Check for start node
    start_nodes = [n for n in flow.nodes if n.type == NodeType.START]
    if len(start_nodes) == 0:
        errors.append("Flow must have at least one start node")
    elif len(start_nodes) > 1:
        warnings.append("Flow has multiple start nodes")

    # Check for end node
    end_nodes = [n for n in flow.nodes if n.type == NodeType.END]
    if len(end_nodes) == 0:
        warnings.append("Flow has no end node")

    # Check node IDs are unique
    node_ids = [n.id for n in flow.nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("Node IDs must be unique")

    # Check edge references
    for edge in flow.edges:
        if edge.source not in node_ids:
            errors.append(f"Edge '{edge.id}' references unknown source '{edge.source}'")
        if edge.target not in node_ids:
            errors.append(f"Edge '{edge.id}' references unknown target '{edge.target}'")

    # Check task nodes have agents
    for node in flow.nodes:
        if node.type == NodeType.TASK and not node.agent:
            warnings.append(f"Task node '{node.id}' has no assigned agent")

    return FlowValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )

def apply_change(flow: FlowDefinition, change: FlowChange) -> FlowDefinition:
    """Apply a change to a flow definition."""
    nodes = list(flow.nodes)
    edges = list(flow.edges)

    if change.operation == "add_node" and change.node:
        nodes.append(change.node)

    elif change.operation == "remove_node" and change.node_id:
        nodes = [n for n in nodes if n.id != change.node_id]
        # Also remove connected edges
        edges = [e for e in edges if e.source != change.node_id and e.target != change.node_id]

    elif change.operation == "update_node" and change.node:
        nodes = [change.node if n.id == change.node.id else n for n in nodes]

    elif change.operation == "add_edge" and change.edge:
        edges.append(change.edge)

    elif change.operation == "remove_edge" and change.edge_id:
        edges = [e for e in edges if e.id != change.edge_id]

    return FlowDefinition(
        id=flow.id,
        name=flow.name,
        description=flow.description,
        nodes=nodes,
        edges=edges,
        viewport=flow.viewport,
    )

def generate_flow_code(flow: FlowDefinition) -> str:
    """Generate Python Flow class code from visual definition."""
    code = f'''"""Auto-generated flow: {flow.name}"""
from crewai.flow.flow import Flow, start, listen, router
from pydantic import BaseModel

class {flow.name.replace(" ", "")}State(BaseModel):
    """Flow state."""
    result: str = ""

class {flow.name.replace(" ", "")}Flow(Flow[{flow.name.replace(" ", "")}State]):
    """{flow.description or flow.name}"""
'''

    for node in flow.nodes:
        if node.type == NodeType.START:
            code += f'''
    @start()
    def {node.id}(self):
        """Start node."""
        return "{node.id} completed"
'''
        elif node.type == NodeType.TASK:
            sources = [e.source for e in flow.edges if e.target == node.id]
            if sources:
                code += f'''
    @listen({", ".join(sources)})
    def {node.id}(self, prev_result):
        """Task: {node.label or node.id}"""
        # Agent: {node.agent or "unassigned"}
        return f"{node.id} completed: {{prev_result}}"
'''

    return code
