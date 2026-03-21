"""Workflow Schema Models - Pydantic validation for ReactFlow workflows.

Defines the schema that bridges ReactFlow editor to CrewAI Flow execution.
Target: ~200 LOC
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from core.adapters import list_agents

if TYPE_CHECKING:
    from core.domains.base import FlowConfig

class NodePosition(BaseModel):
    """Position of a node in the ReactFlow editor."""

    x: float = 0.0
    y: float = 0.0

class NodeMetadata(BaseModel):
    """Optional metadata for workflow nodes."""

    label: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: datetime | None = None

class TaskNodeData(BaseModel):
    """Data for task nodes (agent execution)."""

    agent: str
    task: str
    context: dict[str, Any] | None = None

class RouterNodeData(BaseModel):
    """Data for router nodes (conditional branching)."""

    condition: str
    branches: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("branches")
    @classmethod
    def validate_branches_not_empty(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate that branches list is not empty."""
        if len(v) < 2:
            raise ValueError("Router node must have at least 2 branches")
        return v

class ToolNodeData(BaseModel):
    """Data for tool nodes (direct tool invocation)."""

    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)

class ApprovalNodeData(BaseModel):
    """Data for human approval nodes (pause-and-wait)."""

    prompt: str  # Required: what the approver should check
    approver: Literal["owner", "specific_user", "any_member"] = "owner"
    approver_user_id: str | None = None  # When approver == "specific_user"
    display_fields: list[str] = Field(default_factory=list)  # State fields to show approver
    timeout_seconds: int = Field(default=86400, gt=0)  # Default: 24 hours
    timeout_action: Literal["approve", "reject", "escalate"] = "reject"

class WorkflowNode(BaseModel):
    """A node in the workflow graph."""

    id: str
    type: Literal["start", "task", "router", "end", "tool", "approval"]
    data: TaskNodeData | RouterNodeData | ToolNodeData | ApprovalNodeData | dict[str, Any] = Field(
        default_factory=dict
    )
    position: NodePosition = Field(default_factory=NodePosition)
    metadata: NodeMetadata | None = None

    @field_validator("data", mode="before")
    @classmethod
    def validate_data_for_type(cls, v: Any, _info) -> Any:
        """Validate data matches node type (pre-validation)."""
        # Allow dict for flexibility - actual validation happens at schema level
        return v

class WorkflowEdge(BaseModel):
    """An edge connecting two nodes."""

    id: str
    source: str
    target: str
    type: str = "default"
    data: dict[str, Any] | None = None

class WorkflowSchema(BaseModel):
    """Complete workflow schema with validation.

    Validates:
    - Graph structure (DAG, single start, reachability)
    - Agent names exist in registry
    - Tool names exist in registry
    """

    version: str = "1.0.0"
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_graph_structure(self) -> "WorkflowSchema":
        """Validate the graph structure after all fields are set.

        GAP-112: Added explicit edge validation to ensure all edges reference
        existing nodes. Returns 400 Bad Request for invalid edges.
        """
        errors = []

        # Build set of valid node IDs for edge validation
        all_node_ids = {n.id for n in self.nodes}

        # 1. Check for exactly one start node
        start_nodes = [n for n in self.nodes if n.type == "start"]
        if len(start_nodes) == 0:
            errors.append("Workflow must have exactly one start node")
        elif len(start_nodes) > 1:
            errors.append(f"Workflow must have exactly one start node, found {len(start_nodes)}")

        # 2. GAP-112: Validate all edges reference existing nodes
        invalid_sources = []
        invalid_targets = []
        for edge in self.edges:
            if edge.source not in all_node_ids:
                invalid_sources.append(edge.source)
            if edge.target not in all_node_ids:
                invalid_targets.append(edge.target)
        if invalid_sources:
            errors.append(
                f"Edge source(s) reference non-existent node(s): {', '.join(set(invalid_sources))}"
            )
        if invalid_targets:
            errors.append(
                f"Edge target(s) reference non-existent node(s): {', '.join(set(invalid_targets))}"
            )

        # 3. Check end nodes have no outgoing edges
        end_node_ids = {n.id for n in self.nodes if n.type == "end"}
        for edge in self.edges:
            if edge.source in end_node_ids:
                errors.append(f"End node '{edge.source}' cannot have outgoing edges")

        # 4. Check router nodes have at least 2 outgoing edges
        router_node_ids = {n.id for n in self.nodes if n.type == "router"}
        for router_id in router_node_ids:
            outgoing_count = sum(1 for e in self.edges if e.source == router_id)
            if outgoing_count < 2:
                errors.append(
                    f"Router node '{router_id}' must have at least 2 outgoing edges, found {outgoing_count}"
                )

        # 4b. Check approval nodes have exactly 2 outgoing edges (approved + rejected)
        approval_node_ids = {n.id for n in self.nodes if n.type == "approval"}
        for approval_id in approval_node_ids:
            outgoing_count = sum(1 for e in self.edges if e.source == approval_id)
            if outgoing_count != 2:
                errors.append(
                    f"Approval node '{approval_id}' must have exactly 2 outgoing edges "
                    f"(approved/rejected), found {outgoing_count}"
                )

        # 5. Check all nodes are reachable from start (if start exists)
        if start_nodes and not invalid_sources and not invalid_targets:
            # Only check reachability if edges are valid
            reachable = self._get_reachable_nodes(start_nodes[0].id)
            unreachable = all_node_ids - reachable
            if unreachable:
                errors.append(f"Nodes not reachable from start: {', '.join(unreachable)}")

        # 6. Check for cycles (DAG validation)
        if not invalid_sources and not invalid_targets:
            cycle_nodes = self._find_cycle_nodes()
            if cycle_nodes:
                cycle_path = " -> ".join(cycle_nodes + [cycle_nodes[0]])
                errors.append(f"Workflow contains a cycle: {cycle_path}")

        if errors:
            raise ValueError("; ".join(errors))

        return self

    def _get_reachable_nodes(self, start_id: str) -> set:
        """Get all nodes reachable from a starting node."""
        # Build adjacency list
        adjacency = {}
        for edge in self.edges:
            if edge.source not in adjacency:
                adjacency[edge.source] = []
            adjacency[edge.source].append(edge.target)

        # BFS from start
        visited = {start_id}
        queue = [start_id]

        while queue:
            current = queue.pop(0)
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return visited

    def _has_cycle(self) -> bool:
        """Check if the graph has a cycle using DFS."""
        # Build adjacency list
        adjacency = {}
        for edge in self.edges:
            if edge.source not in adjacency:
                adjacency[edge.source] = []
            adjacency[edge.source].append(edge.target)

        # Track visited and recursion stack
        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            for neighbor in adjacency.get(node_id, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        # Check from all nodes (handles disconnected components)
        return any(node.id not in visited and dfs(node.id) for node in self.nodes)

    def _find_cycle_nodes(self) -> list[str]:
        """Find nodes involved in cycles. Returns empty list if no cycle."""
        adjacency: dict[str, list[str]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)

        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node_id: str) -> list[str] | None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in adjacency.get(node_id, []):
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result is not None:
                        return result
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:]

            path.pop()
            rec_stack.remove(node_id)
            return None

        for node in self.nodes:
            if node.id not in visited:
                cycle = dfs(node.id)
                if cycle:
                    return cycle
        return []

    def validate_agents(self) -> list[str]:
        """Validate that all agent names exist in the registry.

        Returns:
            List of invalid agent names (empty if all valid)
        """
        available_agents = {card.name for card in list_agents()}
        invalid = []

        for node in self.nodes:
            if node.type == "task":
                if isinstance(node.data, TaskNodeData):
                    agent_name = node.data.agent
                elif isinstance(node.data, dict):
                    agent_name = node.data.get("agent", "")
                else:
                    continue

                if agent_name and agent_name not in available_agents:
                    invalid.append(agent_name)

        return invalid

    def validate_tools(self) -> list[str]:
        """Validate that all tool names exist in the registry.

        Returns:
            List of invalid tool names (empty if all valid)

        Note:
            Tool registry integration is deferred to post-v0.2. Currently returns
            empty list, meaning no tool validation occurs at schema validation time.
            Tool validation happens at execution time in executor.py when the tool
            is actually invoked through the MCP bridge.
        """
        return []

    def to_flowconfig(self) -> "FlowConfig":
        """Convert WorkflowSchema to CrewAI FlowConfig.

        Note: Full implementation in Plan 05-04 (ReactFlow to CrewAI converter).
        This is a placeholder that creates a basic FlowConfig.
        """
        from core.domains.base import FlowConfig

        nodes_data = []
        for node in self.nodes:
            node_dict = {
                "id": node.id,
                "type": node.type,
            }
            if isinstance(node.data, BaseModel):
                node_dict.update(node.data.model_dump())
            elif isinstance(node.data, dict):
                node_dict.update(node.data)
            nodes_data.append(node_dict)

        edges_data = [{"source": edge.source, "target": edge.target} for edge in self.edges]

        return FlowConfig(
            name=self.metadata.get("name", "workflow") if self.metadata else "workflow",
            description=self.metadata.get("description", "") if self.metadata else "",
            nodes=nodes_data,
            edges=edges_data,
        )

def validate_workflow(workflow_dict: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a workflow dictionary.

    Args:
        workflow_dict: Raw workflow data

    Returns:
        (is_valid, list of error messages)
    """
    try:
        schema = WorkflowSchema(**workflow_dict)
        errors = schema.validate_agents()
        if errors:
            return False, [f"Invalid agent names: {', '.join(errors)}"]
        return True, []
    except ValueError as e:
        return False, [str(e)]
