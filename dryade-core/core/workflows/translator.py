"""ReactFlow to CrewAI Translator - Convert visual workflows to executable flows.

Bridges ReactFlow JSON designs to CrewAI Flow execution format.
Target: ~250 LOC
"""

import logging
from typing import Any

from core.adapters import list_agents
from core.domains.base import FlowConfig

# Import from unified exception hierarchy
from core.exceptions import TranslationError
from core.workflows.schema import (
    RouterNodeData,
    TaskNodeData,
    ToolNodeData,
    WorkflowNode,
    WorkflowSchema,
)

logger = logging.getLogger("dryade.translator")

# TranslationError is imported from core.exceptions for backward compatibility

class NodeTranslator:
    """Translates individual workflow nodes to execution format.

    Handles 5 node types: start, task, router, end, tool
    """

    def __init__(self):
        """Initialize node translator with available agents."""
        self._available_agents: set[str] = set()
        self._refresh_agents()

    def _refresh_agents(self):
        """Refresh the list of available agents."""
        self._available_agents = {card.name for card in list_agents()}
        logger.debug(f"[TRANSLATOR] Available agents: {self._available_agents}")

    def translate(self, node: WorkflowNode) -> dict[str, Any]:
        """Translate a workflow node to execution format.

        Args:
            node: WorkflowNode to translate

        Returns:
            Dict with translated node data

        Raises:
            TranslationError: If translation fails (invalid node type, missing agent, etc.)
        """
        logger.debug(f"[TRANSLATOR] Translating node: {node.id} (type: {node.type})")

        translator_map = {
            "start": self.translate_start_node,
            "task": self.translate_task_node,
            "router": self.translate_router_node,
            "end": self.translate_end_node,
            "tool": self.translate_tool_node,
        }

        translator = translator_map.get(node.type)
        if not translator:
            raise TranslationError(f"Unknown node type: {node.type}")

        return translator(node)

    def translate_start_node(self, node: WorkflowNode) -> dict[str, Any]:
        """Translate start node.

        Start node marks entry point - no agent/task, just marks beginning.

        Args:
            node: Start node

        Returns:
            {"type": "start", "id": node.id}
        """
        logger.debug(f"[TRANSLATOR] Translating start node: {node.id}")
        return {
            "type": "start",
            "id": node.id,
        }

    def translate_task_node(self, node: WorkflowNode) -> dict[str, Any]:
        """Translate task node (agent execution).

        Extracts agent name, task description, and context from node data.
        Validates that the agent exists in the registry.

        Args:
            node: Task node

        Returns:
            {"type": "task", "id": node.id, "agent": agent, "task": task, "context": context}

        Raises:
            TranslationError: If agent not found in registry
        """
        logger.debug(f"[TRANSLATOR] Translating task node: {node.id}")

        # Extract data from node
        if isinstance(node.data, TaskNodeData):
            agent = node.data.agent
            task = node.data.task
            context = node.data.context or {}
        elif isinstance(node.data, dict):
            agent = node.data.get("agent", "")
            task = node.data.get("task", "")
            context = node.data.get("context", {})
        else:
            raise TranslationError(f"Invalid data format for task node {node.id}")

        # Validate agent exists
        self._refresh_agents()
        if agent and agent not in self._available_agents:
            raise TranslationError(f"Agent '{agent}' not found in registry")

        return {
            "type": "task",
            "id": node.id,
            "agent": agent,
            "task": task,
            "context": context,
        }

    def translate_router_node(self, node: WorkflowNode) -> dict[str, Any]:
        """Translate router node (conditional branching).

        Extracts condition and branches from node data.
        Condition is LLM-evaluated expression at runtime.

        Args:
            node: Router node

        Returns:
            {"type": "router", "id": node.id, "condition": condition, "branches": branches}
        """
        logger.debug(f"[TRANSLATOR] Translating router node: {node.id}")

        # Extract data from node
        if isinstance(node.data, RouterNodeData):
            condition = node.data.condition
            branches = node.data.branches
        elif isinstance(node.data, dict):
            condition = node.data.get("condition", "")
            branches = node.data.get("branches", [])
        else:
            raise TranslationError(f"Invalid data format for router node {node.id}")

        return {
            "type": "router",
            "id": node.id,
            "condition": condition,
            "branches": branches,
        }

    def translate_end_node(self, node: WorkflowNode) -> dict[str, Any]:
        """Translate end node (terminal state).

        End node marks workflow completion - no outputs.

        Args:
            node: End node

        Returns:
            {"type": "end", "id": node.id}
        """
        logger.debug(f"[TRANSLATOR] Translating end node: {node.id}")
        return {
            "type": "end",
            "id": node.id,
        }

    def translate_tool_node(self, node: WorkflowNode) -> dict[str, Any]:
        """Translate tool node (direct tool invocation).

        Extracts tool name and parameters from node data.
        Direct tool invocation without agent wrapper.

        Args:
            node: Tool node

        Returns:
            {"type": "tool", "id": node.id, "tool": tool, "parameters": parameters}

        Note:
            Tool existence validation is deferred to post-v0.2. The translator
            passes tool names through without validation. Tool validation happens
            at execution time in executor.py when the tool is invoked through
            the MCP bridge, which will raise an error if the tool doesn't exist.
        """
        logger.debug(f"[TRANSLATOR] Translating tool node: {node.id}")

        # Extract data from node
        if isinstance(node.data, ToolNodeData):
            tool = node.data.tool
            parameters = node.data.parameters
        elif isinstance(node.data, dict):
            tool = node.data.get("tool", "")
            parameters = node.data.get("parameters", {})
        else:
            raise TranslationError(f"Invalid data format for tool node {node.id}")

        return {
            "type": "tool",
            "id": node.id,
            "tool": tool,
            "parameters": parameters,
        }

class WorkflowTranslator:
    """Orchestrates workflow translation from WorkflowSchema to FlowConfig.

    Handles:
    - Node translation (via NodeTranslator)
    - Edge processing
    - Topological sort for execution order
    - FlowConfig generation
    """

    def __init__(self):
        """Initialize workflow translator with node translator."""
        self._node_translator = NodeTranslator()

    def translate(self, workflow: WorkflowSchema) -> FlowConfig:
        """Translate a WorkflowSchema to FlowConfig.

        Alias for to_flowconfig() for consistency with plan naming.

        Args:
            workflow: Validated WorkflowSchema

        Returns:
            FlowConfig for execution
        """
        return self.to_flowconfig(workflow)

    def to_flowconfig(self, workflow: WorkflowSchema) -> FlowConfig:
        """Convert WorkflowSchema to CrewAI FlowConfig.

        Steps:
        1. Translate all nodes using NodeTranslator
        2. Build execution DAG from edges
        3. Topological sort for execution order
        4. Generate FlowConfig

        Args:
            workflow: Validated WorkflowSchema

        Returns:
            FlowConfig ready for execution

        Raises:
            TranslationError: If translation fails
        """
        logger.info("[TRANSLATOR] Starting translation of workflow")

        # 1. Translate all nodes
        translated_nodes = []
        for node in workflow.nodes:
            try:
                translated = self._node_translator.translate(node)
                translated_nodes.append(translated)
            except TranslationError as e:
                logger.error(f"[TRANSLATOR] Failed to translate node {node.id}: {e}")
                raise

        logger.info(f"[TRANSLATOR] Translated {len(translated_nodes)} nodes")

        # 2. Build edge list
        edges_data = []
        for edge in workflow.edges:
            edge_dict = {
                "source": edge.source,
                "target": edge.target,
            }
            # Include edge data if present (for router conditions)
            if edge.data:
                edge_dict["data"] = edge.data
            edges_data.append(edge_dict)

        logger.info(f"[TRANSLATOR] Processed {len(edges_data)} edges")

        # 3. Topological sort for execution order
        node_ids = [n["id"] for n in translated_nodes]
        sorted_ids = self._topological_sort(node_ids, edges_data)
        logger.info(f"[TRANSLATOR] Execution order: {sorted_ids}")

        # 4. Reorder nodes by execution order
        node_by_id = {n["id"]: n for n in translated_nodes}
        ordered_nodes = [node_by_id[id] for id in sorted_ids]

        # 5. Generate FlowConfig
        name = "workflow"
        description = ""
        if workflow.metadata:
            name = workflow.metadata.get("name", "workflow")
            description = workflow.metadata.get("description", "")

        flow_config = FlowConfig(
            name=name,
            description=description,
            nodes=ordered_nodes,
            edges=edges_data,
        )

        logger.info(
            f"[TRANSLATOR] Translated workflow '{name}' to FlowConfig "
            f"with {len(ordered_nodes)} nodes, {len(edges_data)} edges"
        )

        return flow_config

    def _topological_sort(self, node_ids: list[str], edges: list[dict[str, Any]]) -> list[str]:
        """Topological sort using Kahn's algorithm.

        Determines execution order respecting dependencies.

        Args:
            node_ids: List of node IDs
            edges: List of edges (source -> target)

        Returns:
            List of node IDs in execution order

        Raises:
            TranslationError: If cycle detected or unreachable nodes
        """
        # Build adjacency list and in-degree count
        adjacency: dict[str, list[str]] = {id: [] for id in node_ids}
        in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)

        for edge in edges:
            source = edge["source"]
            target = edge["target"]
            if source in adjacency:
                adjacency[source].append(target)
            if target in in_degree:
                in_degree[target] += 1

        # Kahn's algorithm
        # Start with nodes that have no incoming edges
        queue = [id for id in node_ids if in_degree[id] == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in adjacency.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles
        if len(result) != len(node_ids):
            remaining = set(node_ids) - set(result)
            raise TranslationError(f"Workflow contains cycles involving nodes: {remaining}")

        return result

    def validate_execution_order(self, node_ids: list[str], edges: list[dict[str, Any]]) -> bool:
        """Validate that execution order is valid (no cycles).

        Args:
            node_ids: List of node IDs
            edges: List of edges

        Returns:
            True if valid DAG, False if contains cycles
        """
        try:
            self._topological_sort(node_ids, edges)
            return True
        except TranslationError:
            return False

    def resolve_dependencies(self, node_id: str, edges: list[dict[str, Any]]) -> list[str]:
        """Get prerequisite node IDs for a given node.

        Args:
            node_id: Node to get dependencies for
            edges: List of edges

        Returns:
            List of node IDs that must complete before this node
        """
        dependencies = []
        for edge in edges:
            if edge["target"] == node_id:
                dependencies.append(edge["source"])
        return dependencies
