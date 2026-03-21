"""Workflow Executor - Dynamic Flow class generation and execution.

Generates executable CrewAI Flow classes from FlowConfig at runtime.
Target: ~300 LOC
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from crewai.flow.flow import Flow, listen, or_, router, start
from pydantic import BaseModel, ConfigDict, Field, create_model

from core.adapters import get_agent
from core.domains.base import FlowConfig

# Import from unified exception hierarchy (using alias for backward compatibility)
from core.exceptions import MCPRegistryError
from core.exceptions import WorkflowExecutionError as ExecutionError

# Import MCP registry for tool execution
from core.mcp import get_registry

# Import expression-based condition parser
from core.workflows.condition_parser import ConditionParseError, evaluate_condition

logger = logging.getLogger("dryade.workflows.executor")

def _parse_github_url(url: str) -> dict[str, str] | None:
    """Parse GitHub URL to extract owner, repo, and PR number.

    Supports formats:
    - https://github.com/owner/repo/pull/123
    - https://github.com/owner/repo

    Returns:
        Dict with 'owner', 'repo', and optionally 'pr_number', or None if invalid.
    """
    import re

    if not url:
        return None

    # Match GitHub PR URL: https://github.com/owner/repo/pull/123
    pr_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if pr_match:
        return {
            "owner": pr_match.group(1),
            "repo": pr_match.group(2),
            "pr_number": pr_match.group(3),
        }

    # Match GitHub repo URL: https://github.com/owner/repo
    repo_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?", url)
    if repo_match:
        return {
            "owner": repo_match.group(1),
            "repo": repo_match.group(2),
        }

    return None

# Reserved Flow method names that cannot be used as node IDs
# These would override Flow's built-in methods and break functionality
RESERVED_FLOW_METHODS = frozenset(
    {
        "state",
        "initial_state",
        "kickoff",
        "kickoff_async",
        "flow_id",
        "from_pending",
        "resume",
        "resume_async",
        "method_outputs",
        "_start",
        "_end",
        "_route",
        "_execute",
        "_run",
        "_init",
        "model_dump",
        "model_validate",
        "model_copy",
        "model_fields",
    }
)

class WorkflowExecutor:
    """Generates executable Flow classes from FlowConfig.

    Strategy:
    1. Create State dataclass with fields for intermediate results
    2. Generate methods for each node type (start, task, router, end, tool)
    3. Apply @start, @listen, @router decorators dynamically
    4. Return generated Flow class ready for execution
    """

    def generate_flow_class(self, flowconfig: FlowConfig) -> type[Flow]:
        """Generate a Flow subclass from FlowConfig.

        Args:
            flowconfig: FlowConfig with nodes and edges

        Returns:
            Generated Flow class ready for instantiation

        Raises:
            ExecutionError: If FlowConfig is invalid
        """
        logger.info(f"[EXECUTOR] Generating Flow class '{flowconfig.name}'")

        if not flowconfig.nodes:
            raise ExecutionError("FlowConfig has no nodes")

        # Build adjacency map for edge dependencies
        adjacency = self._build_adjacency(flowconfig.edges)
        reverse_adjacency = self._build_reverse_adjacency(flowconfig.edges)

        # Find start node
        start_node = next((n for n in flowconfig.nodes if n.get("type") == "start"), None)
        if not start_node:
            raise ExecutionError("FlowConfig has no start node")

        # Create State model dynamically with collision detection
        state_fields = self._create_state_fields(flowconfig.nodes)

        # Create base class with model config (Pydantic v2 requires config at creation)
        class StateBase(BaseModel):
            model_config = ConfigDict(
                arbitrary_types_allowed=True,
                extra="allow",  # Allow dynamic input fields
            )

        StateModel = create_model(
            f"{flowconfig.name.replace(' ', '')}State",
            __base__=StateBase,
            __module__=__name__,
            **state_fields,
        )

        # Build maps for router exclusive branching FIRST (needed for method creation):
        # 1. router_nodes: set of router node IDs
        # 2. edge_route_labels: (router_id, target_id) -> route_label (from edge.data.condition)
        router_nodes = {n["id"] for n in flowconfig.nodes if n.get("type") == "router"}
        edge_route_labels: dict[tuple[str, str], str] = {}  # (router_id, target_id) -> label

        for edge in flowconfig.edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            if source in router_nodes:
                # Use edge condition as route label if available, otherwise use target ID
                edge_data = edge.get("data", {})
                if isinstance(edge_data, dict):
                    route_label = edge_data.get("condition", target)
                else:
                    route_label = target
                edge_route_labels[(source, target)] = route_label

        # Create methods for each node
        methods = {}
        node_methods = {}  # Track method names by node ID

        for node in flowconfig.nodes:
            node_id = node["id"]
            node_type = node.get("type", "task")
            method_name = self._sanitize_method_name(node_id)
            node_methods[node_id] = method_name

            # Create method based on node type
            if node_type == "start":
                method = self._create_start_method(node, StateModel)
                method = start()(method)
            elif node_type == "task":
                method = self._create_task_method(node, StateModel)
            elif node_type == "router":
                # Pass edge route labels so router returns labels, not node IDs
                method = self._create_router_method(node, StateModel, adjacency, edge_route_labels)
            elif node_type == "end":
                method = self._create_end_method(node, StateModel)
            elif node_type == "tool":
                method = self._create_tool_method(node, StateModel)
            elif node_type == "approval":
                method = self._create_approval_method(node, StateModel)
            else:
                logger.warning(f"[EXECUTOR] Unknown node type: {node_type}")
                continue

            methods[method_name] = method

        # Build listener routing maps from edge_route_labels (computed earlier):
        # - router_targets: target_node_id -> router_node_id
        # - route_labels: target_node_id -> route_label
        router_targets: dict[str, str] = {}  # target_node_id -> router_node_id
        route_labels: dict[str, str] = {}  # target_node_id -> route_label

        for (router_id, target_id), label in edge_route_labels.items():
            router_targets[target_id] = router_id
            route_labels[target_id] = label
            logger.debug(
                f"[EXECUTOR] Listener setup: '{target_id}' listens for '{label}' from router '{router_id}'"
            )

        # Apply @listen decorators based on edges
        # Skip start node (already has @start decorator)
        for node in flowconfig.nodes:
            node_id = node["id"]
            node_type = node.get("type", "task")

            if node_type == "start":
                continue  # Start node already decorated

            method_name = node_methods[node_id]
            method = methods[method_name]

            # Get predecessors (nodes that feed into this node)
            predecessors = reverse_adjacency.get(node_id, [])

            if predecessors:
                # For router nodes, use @router(pred_method) instead of @listen
                # The @router decorator already implies listening to the predecessor
                if node_type == "router":
                    # Apply @router decorator with predecessor method
                    # Router uses return value to determine downstream routing
                    pred_id = predecessors[0]  # Router typically has one predecessor
                    pred_method_name = node_methods.get(pred_id)
                    if pred_method_name:
                        pred_method = methods.get(pred_method_name)
                        if pred_method:
                            method = router(pred_method)(method)
                elif node_id in router_targets:
                    # This node is a target of a router - use string-based @listen
                    # for exclusive branching. The router returns the route_label,
                    # and only the matching @listen(route_label) will execute.
                    # See: https://docs.crewai.com/en/concepts/flows
                    route_label = route_labels.get(node_id, node_id)
                    method = listen(route_label)(method)
                    logger.debug(
                        f"[EXECUTOR] Node '{node_id}' uses @listen('{route_label}') for "
                        f"exclusive routing from router '{router_targets[node_id]}'"
                    )
                else:
                    # Collect all predecessor methods for @listen
                    # Using single @listen with multiple methods is more reliable
                    # than chaining multiple @listen decorators
                    pred_methods = []
                    for pred_id in predecessors:
                        pred_method_name = node_methods.get(pred_id)
                        if pred_method_name:
                            pred_method = methods.get(pred_method_name)
                            if pred_method:
                                pred_methods.append(pred_method)

                    # Apply @listen decorator with predecessors
                    if len(pred_methods) == 1:
                        method = listen(pred_methods[0])(method)
                    elif len(pred_methods) > 1:
                        # CrewAI listen takes single condition - use or_() for multiple
                        method = listen(or_(*pred_methods))(method)

            methods[method_name] = method

        # Store config in class attribute for runtime access
        class_attrs = {
            "__module__": __name__,
            "_flowconfig": flowconfig,
            "_node_methods": node_methods,
            **methods,
        }

        # Create initial_state property
        def make_initial_state(_self):
            return StateModel()

        class_attrs["initial_state"] = property(make_initial_state)

        # Generate Flow class dynamically
        flow_class = type(f"Generated{flowconfig.name.replace(' ', '')}Flow", (Flow,), class_attrs)

        # Set generic type for state
        flow_class.__state_model = StateModel

        logger.info(
            f"[EXECUTOR] Generated Flow class '{flow_class.__name__}' with {len(methods)} methods"
        )

        return flow_class

    def _build_adjacency(self, edges: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Build adjacency map from edges (source -> targets)."""
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            if source not in adjacency:
                adjacency[source] = []
            adjacency[source].append(target)
        return adjacency

    def _build_reverse_adjacency(self, edges: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Build reverse adjacency map from edges (target -> sources)."""
        reverse: dict[str, list[str]] = {}
        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            if target not in reverse:
                reverse[target] = []
            reverse[target].append(source)
        return reverse

    def _create_state_fields(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        """Create Pydantic field definitions for State model.

        Includes collision detection to prevent multiple node IDs from
        mapping to the same field name after sanitization.
        """
        fields = {}
        seen_fields: dict[str, str] = {}  # field_name -> original_node_id

        # Add required 'id' field for CrewAI Flow compatibility
        # CrewAI validates that all BaseModel states have an 'id' field
        fields["id"] = (str, Field(default_factory=lambda: str(uuid.uuid4())))
        seen_fields["id"] = "__builtin__"

        for node in nodes:
            node_id = node["id"]
            base_field_name = self._sanitize_field_name(f"{node_id}_output")

            # Check for collision
            if base_field_name in seen_fields:
                original_id = seen_fields[base_field_name]
                # Add unique suffix to avoid collision
                suffix = 1
                field_name = f"{base_field_name}_{suffix}"
                while field_name in seen_fields:
                    suffix += 1
                    field_name = f"{base_field_name}_{suffix}"
                logger.warning(
                    f"[EXECUTOR] State field collision detected: '{node_id}' and '{original_id}' "
                    f"both map to '{base_field_name}'. Using '{field_name}' for '{node_id}'."
                )
            else:
                field_name = base_field_name

            seen_fields[field_name] = node_id
            # All fields optional with None default
            fields[field_name] = (Any | None, None)

        # Add standard fields with collision checking
        for std_field in ["final_result", "error", "started_at", "completed_at"]:
            if std_field in seen_fields:
                logger.warning(
                    f"[EXECUTOR] Standard field '{std_field}' collides with node output field"
                )
            seen_fields[std_field] = "__standard__"

        fields["final_result"] = (Any | None, None)
        fields["error"] = (str | None, None)
        fields["started_at"] = (datetime | None, None)
        fields["completed_at"] = (datetime | None, None)

        return fields

    def _sanitize_method_name(self, node_id: str) -> str:
        """Convert node ID to valid Python method name.

        Checks for collisions with Flow's reserved method names and
        prefixes with 'node_' if necessary.
        """
        # Replace invalid characters with underscore
        name = node_id.replace("-", "_").replace(".", "_").replace(" ", "_")
        # Ensure starts with letter
        if name[0].isdigit():
            name = f"node_{name}"

        # Check for reserved Flow method names
        if name in RESERVED_FLOW_METHODS:
            logger.warning(
                f"[EXECUTOR] Node ID '{node_id}' conflicts with reserved Flow method '{name}'. "
                f"Prefixing with 'node_'."
            )
            name = f"node_{name}"

        return name

    def _sanitize_field_name(self, name: str) -> str:
        """Convert name to valid Pydantic field name."""
        return name.replace("-", "_").replace(".", "_").replace(" ", "_")

    def _create_start_method(self, node: dict[str, Any], __state_model: type[BaseModel]):
        """Create start node method."""
        node_id = node["id"]
        field_name = self._sanitize_field_name(f"{node_id}_output")

        def start_method(self):
            logger.debug(f"[EXECUTOR] Start node '{node_id}' executing")
            self.state.started_at = datetime.now()
            setattr(self.state, field_name, "started")
            return "started"

        start_method.__name__ = self._sanitize_method_name(node_id)
        return start_method

    def _create_task_method(self, node: dict[str, Any], _state_model: type[BaseModel]):
        """Create task node method (agent execution)."""
        node_id = node["id"]
        # Phase 174.5: node data may be nested under "data" key (workflow schema)
        # or flat at the top level (legacy/planner format). Support both.
        node_data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}
        agent_name = node_data.get("agent", node.get("agent", ""))
        task_description = node_data.get("task", node.get("task", ""))
        static_context = node_data.get("context", node.get("context", {}))
        # Forward tool + arguments for MCP agents
        explicit_tool = node_data.get("tool", node.get("tool"))
        explicit_args = node_data.get("arguments", node.get("arguments"))
        field_name = self._sanitize_field_name(f"{node_id}_output")

        async def task_method(self, *args, **kwargs):  # noqa: ARG001
            logger.debug(f"[EXECUTOR] Task node '{node_id}' executing with agent '{agent_name}'")
            try:
                # Get agent from registry
                agent = get_agent(agent_name)
                if not agent:
                    error_msg = f"Agent '{agent_name}' not found in registry"
                    logger.error(f"[EXECUTOR] {error_msg}")
                    self.state.error = error_msg
                    setattr(self.state, field_name, {"error": error_msg})
                    return {"error": error_msg}

                # Build runtime context by merging:
                # 1. Static context from node definition
                # 2. Workflow state values (includes inputs and previous node outputs)
                runtime_context = dict(static_context) if static_context else {}

                # Add state values to context for agent access
                state_dict = self.state.model_dump() if hasattr(self.state, "model_dump") else {}
                for key, value in state_dict.items():
                    # Skip internal fields and None values
                    if key not in ("id", "error", "started_at", "completed_at", "final_result"):
                        if value is not None:
                            # For output fields, use the node name without _output suffix
                            if key.endswith("_output"):
                                clean_key = key.replace("_output", "")
                                runtime_context[clean_key] = value
                            else:
                                runtime_context[key] = value

                # Parse pr_url if present to extract owner/repo for GitHub operations
                if "pr_url" in runtime_context and "owner" not in runtime_context:
                    pr_url = runtime_context.get("pr_url", "")
                    parsed = (
                        self._parse_github_url(pr_url)
                        if hasattr(self, "_parse_github_url")
                        else None
                    )
                    if not parsed:
                        parsed = _parse_github_url(pr_url)
                    if parsed:
                        runtime_context.update(parsed)

                # Forward explicit tool + arguments for MCP agents
                if explicit_tool:
                    runtime_context["tool"] = explicit_tool
                if explicit_args and isinstance(explicit_args, dict):
                    runtime_context["arguments"] = explicit_args

                logger.debug(
                    f"[EXECUTOR] Task '{node_id}' context keys: {list(runtime_context.keys())}"
                )

                # Execute agent with task (await the async method)
                result = await agent.execute(task=task_description, context=runtime_context)

                # Store result in state
                output = result.output if hasattr(result, "output") else str(result)
                setattr(self.state, field_name, output)
                logger.debug(f"[EXECUTOR] Task node '{node_id}' completed")
                return output

            except Exception as e:
                error_msg = f"Task execution failed: {str(e)}"
                logger.error(f"[EXECUTOR] {error_msg}")
                self.state.error = error_msg
                setattr(self.state, field_name, {"error": error_msg})
                return {"error": error_msg}

        task_method.__name__ = self._sanitize_method_name(node_id)
        return task_method

    def _create_router_method(
        self,
        node: dict[str, Any],
        _state_model: type[BaseModel],
        adjacency: dict[str, list[str]],
        edge_route_labels: dict[tuple[str, str], str],
    ):
        """Create router node method (conditional branching).

        Returns route labels (from edge.data.condition) for exclusive branching.
        Listeners use @listen(route_label) to trigger on matching routes.

        Args:
            node: Router node configuration
            _state_model: State model class (unused)
            adjacency: Node adjacency map (source -> targets)
            edge_route_labels: Map of (router_id, target_id) -> route_label
        """
        node_id = node["id"]
        node.get("condition", "")
        branches = node.get("branches", [])
        field_name = self._sanitize_field_name(f"{node_id}_output")

        # Get target node IDs for branching
        targets = adjacency.get(node_id, [])

        # Build target_id -> route_label map for this router
        target_to_label: dict[str, str] = {}
        for target_id in targets:
            label = edge_route_labels.get((node_id, target_id), target_id)
            target_to_label[target_id] = label

        def _check_condition(state, condition: str) -> bool:
            """Evaluate condition expression against state.

            Uses expression-based condition parser for complex conditions like:
            - status == 'success' AND score > 0.8
            - error == null OR message contains 'retry'

            Falls back to legacy substring matching for simple conditions
            to maintain backward compatibility.
            """
            if not condition:
                return True

            # Get state as dict for evaluation
            state_dict = state.model_dump() if hasattr(state, "model_dump") else {}

            # Try expression parser first
            try:
                return evaluate_condition(condition, state_dict)
            except ConditionParseError:
                # Fall back to legacy substring matching for backward compatibility
                logger.debug(f"Falling back to substring matching for condition: {condition}")
                for _key, value in state_dict.items():
                    if value and isinstance(value, str) and condition.lower() in value.lower():
                        return True
                return False

        def router_method(self, *args, **kwargs):  # noqa: ARG001
            logger.debug(f"[EXECUTOR] Router node '{node_id}' evaluating condition")
            try:
                # Default: return first target's route label
                if targets:
                    selected_target = targets[0]

                    # Check branches for matching conditions
                    for branch in branches:
                        branch_condition = branch.get("condition", "")
                        branch_target = branch.get("target", "")

                        logger.debug(
                            f"[EXECUTOR] Evaluating condition '{branch_condition}' against state"
                        )

                        # Use local helper to avoid collision with Flow._evaluate_condition
                        if branch_target in targets and _check_condition(
                            self.state, branch_condition
                        ):
                            selected_target = branch_target
                            break

                    # Return the ROUTE LABEL, not the target node ID
                    # This enables exclusive branching via @listen(route_label)
                    route_label = target_to_label.get(selected_target, selected_target)
                    setattr(self.state, field_name, route_label)
                    logger.info(
                        f"[EXECUTOR] Router '{node_id}' selected target '{selected_target}', "
                        f"returning route label '{route_label}'"
                    )
                    return route_label
                else:
                    logger.warning(f"[EXECUTOR] Router '{node_id}' has no targets")
                    return None

            except Exception as e:
                error_msg = f"Router evaluation failed: {str(e)}"
                logger.error(f"[EXECUTOR] {error_msg}")
                self.state.error = error_msg
                # Log explicit fallback warning
                if targets:
                    fallback_label = target_to_label.get(targets[0], targets[0])
                    logger.warning(
                        f"[EXECUTOR] Router '{node_id}' falling back to route label '{fallback_label}' "
                        f"due to error. This may not be the intended routing."
                    )
                    return fallback_label
                return None

        router_method.__name__ = self._sanitize_method_name(node_id)
        return router_method

    def _create_end_method(self, node: dict[str, Any], _state_model: type[BaseModel]):
        """Create end node method (terminal state)."""
        node_id = node["id"]
        field_name = self._sanitize_field_name(f"{node_id}_output")

        def end_method(self, *args, **kwargs):  # noqa: ARG001
            logger.debug(f"[EXECUTOR] End node '{node_id}' executing")
            self.state.completed_at = datetime.now()

            # Gather final result from all non-None outputs
            state_dict = self.state.model_dump() if hasattr(self.state, "model_dump") else {}
            results = {k: v for k, v in state_dict.items() if v is not None and "_output" in k}

            self.state.final_result = results
            setattr(self.state, field_name, "completed")

            logger.info("[EXECUTOR] Workflow completed")
            return results

        end_method.__name__ = self._sanitize_method_name(node_id)
        return end_method

    def _create_tool_method(self, node: dict[str, Any], _state_model: type[BaseModel]):
        """Create tool node method (direct tool invocation via MCPRegistry)."""
        node_id = node["id"]
        tool_name = node.get("tool", "")
        static_parameters = node.get("parameters", {})
        field_name = self._sanitize_field_name(f"{node_id}_output")

        async def tool_method(self, *args, **kwargs):  # noqa: ARG001
            import json as _json  # local import to avoid shadowing module-level names

            # Mock mode for CI — mirrors MCPToolWrapper._mock_mode pattern
            from core.config import get_settings

            if get_settings().mock_mode:
                mock_result = _json.dumps(
                    {
                        "mock": True,
                        "tool": tool_name,
                        "parameters": static_parameters,
                        "result": f"Mock output for tool '{tool_name}'",
                    }
                )
                setattr(self.state, field_name, mock_result)
                logger.debug(
                    f"[EXECUTOR] Tool node '{node_id}' returning mock response (DRYADE_MOCK_MODE)"
                )
                return mock_result

            logger.debug(f"[EXECUTOR] Tool node '{node_id}' invoking tool '{tool_name}'")
            try:
                # Build merged parameters:
                # 1. Start with static parameters from node definition (preserve any explicit params)
                # 2. Add workflow state values (user inputs + previous node outputs)
                parameters = dict(static_parameters) if static_parameters else {}

                # Add state values as available parameters (same pattern as _create_task_method)
                state_dict = self.state.model_dump() if hasattr(self.state, "model_dump") else {}
                for key, value in state_dict.items():
                    # Skip internal fields and None values
                    if key not in ("id", "error", "started_at", "completed_at", "final_result"):
                        if value is not None and key not in parameters:
                            # For output fields, use the node name without _output suffix
                            if key.endswith("_output"):
                                clean_key = key.replace("_output", "")
                                parameters[clean_key] = value
                            else:
                                parameters[key] = value

                logger.debug(f"[EXECUTOR] Tool '{tool_name}' parameters: {list(parameters.keys())}")

                # Tool invocation through MCPRegistry (lazy start, auto-routing)
                registry = get_registry()
                mcp_result = registry.call_tool_by_name(tool_name, parameters)

                # Extract text content from MCPToolCallResult
                if mcp_result.content:
                    result = mcp_result.content[0].text or ""
                else:
                    result = ""

                setattr(self.state, field_name, result)
                logger.debug(f"[EXECUTOR] Tool node '{node_id}' completed")
                return result

            except MCPRegistryError as e:
                error_msg = f"MCP tool '{tool_name}' not found in registry: {e}"
                logger.warning(f"[EXECUTOR] {error_msg}")
                self.state.error = error_msg
                setattr(self.state, field_name, {"error": error_msg})
                raise ExecutionError(f"Tool execution failed: {e}")

            except Exception as e:
                error_msg = f"Tool invocation failed: {str(e)}"
                logger.error(f"[EXECUTOR] {error_msg}")
                self.state.error = error_msg
                setattr(self.state, field_name, {"error": error_msg})
                return {"error": error_msg}

        tool_method.__name__ = self._sanitize_method_name(node_id)
        return tool_method

    def _create_approval_method(self, node: dict[str, Any], _state_model: type[BaseModel]):
        """Create approval node method — pauses execution by raising sentinel exception.

        The WorkflowPausedForApproval exception is caught by the workflow route handler,
        NOT by CrewAI Flow. State is serialized to DB via ApprovalService.
        """
        node_id = node["id"]
        prompt = node.get("prompt", "")
        approver = node.get("approver", "owner")
        approver_user_id = node.get("approver_user_id")
        display_fields = node.get("display_fields", [])
        timeout_seconds = node.get("timeout_seconds", 86400)
        timeout_action = node.get("timeout_action", "reject")
        field_name = self._sanitize_field_name(f"{node_id}_output")

        async def approval_method(self, *args, **kwargs):  # noqa: ARG001
            logger.info(f"[EXECUTOR] Approval node '{node_id}' — pausing workflow for human review")
            # Store approval metadata in state for the route handler to access
            approval_meta = {
                "status": "awaiting_approval",
                "node_id": node_id,
                "prompt": prompt,
                "approver": approver,
                "approver_user_id": approver_user_id,
                "display_fields": display_fields,
                "timeout_seconds": timeout_seconds,
                "timeout_action": timeout_action,
                "state_snapshot": (
                    self.state.model_dump() if hasattr(self.state, "model_dump") else {}
                ),
            }
            setattr(self.state, field_name, approval_meta)
            from core.exceptions import WorkflowPausedForApproval

            raise WorkflowPausedForApproval(approval_request_id=-1)  # ID assigned by route handler

        approval_method.__name__ = self._sanitize_method_name(node_id)
        return approval_method
