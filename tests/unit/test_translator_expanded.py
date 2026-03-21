"""Expanded tests for core/workflows/translator.py.

Tests NodeTranslator and WorkflowTranslator covering all node types,
topological sort, FlowConfig generation, and error handling.
"""

from unittest.mock import MagicMock, patch

import pytest

# ===========================================================================
# NodeTranslator
# ===========================================================================

class TestNodeTranslatorStartNode:
    """Tests for NodeTranslator.translate_start_node()."""

    def _make_translator(self):
        """Create NodeTranslator with mocked agent list."""
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import NodeTranslator

            return NodeTranslator()

    def _make_node(self, node_id="n1", node_type="start", data=None):
        """Create a WorkflowNode."""
        from core.workflows.schema import WorkflowNode

        return WorkflowNode(id=node_id, type=node_type, data=data or {})

    def test_translate_start_node_returns_dict(self):
        """translate_start_node returns dict with type=start."""
        translator = self._make_translator()
        node = self._make_node(node_id="start-1", node_type="start")
        result = translator.translate_start_node(node)
        assert result["type"] == "start"
        assert result["id"] == "start-1"

    def test_translate_end_node_returns_dict(self):
        """translate_end_node returns dict with type=end."""
        translator = self._make_translator()
        node = self._make_node(node_id="end-1", node_type="end")
        result = translator.translate_end_node(node)
        assert result["type"] == "end"
        assert result["id"] == "end-1"

    def test_translate_dispatches_by_type(self):
        """translate() dispatches to the correct method based on node type."""
        translator = self._make_translator()

        node = self._make_node(node_id="s1", node_type="start")
        result = translator.translate(node)
        assert result["type"] == "start"

    def test_translate_unknown_type_raises_error(self):
        """translate() raises TranslationError for unknown node type."""
        from core.exceptions import TranslationError
        from core.workflows.schema import WorkflowNode

        translator = self._make_translator()
        # Create node with valid type, then manually change it
        node = WorkflowNode(id="bad-1", type="start", data={})
        node.type = "unknown_type"  # Bypass Pydantic validation by direct assignment

        with pytest.raises((TranslationError, ValueError)):
            translator.translate(node)

class TestNodeTranslatorRouterNode:
    """Tests for NodeTranslator.translate_router_node()."""

    def _make_translator(self):
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import NodeTranslator

            return NodeTranslator()

    def test_translate_router_node_with_dict_data(self):
        """Router node with dict data returns correct structure."""
        translator = self._make_translator()
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(
            id="router-1",
            type="router",
            data={"condition": "score > 0.8", "branches": ["branch-a", "branch-b"]},
        )
        result = translator.translate_router_node(node)
        assert result["type"] == "router"
        assert result["id"] == "router-1"
        assert result["condition"] == "score > 0.8"
        assert result["branches"] == ["branch-a", "branch-b"]

    def test_translate_router_node_with_router_node_data(self):
        """Router node with RouterNodeData returns correct structure."""
        translator = self._make_translator()
        from core.workflows.schema import RouterNodeData, WorkflowNode

        node = WorkflowNode(
            id="router-2",
            type="router",
            data=RouterNodeData(
                condition="status == 'success'",
                branches=[{"id": "a", "label": "yes"}, {"id": "b", "label": "no"}],
            ),
        )
        result = translator.translate_router_node(node)
        assert result["condition"] == "status == 'success'"

    def test_translate_router_defaults_on_missing_condition(self):
        """Router with no condition defaults to empty string."""
        translator = self._make_translator()
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(id="router-3", type="router", data={})
        result = translator.translate_router_node(node)
        assert result["condition"] == ""
        assert result["branches"] == []

class TestNodeTranslatorToolNode:
    """Tests for NodeTranslator.translate_tool_node()."""

    def _make_translator(self):
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import NodeTranslator

            return NodeTranslator()

    def test_translate_tool_node_with_dict_data(self):
        """Tool node with dict data returns correct structure."""
        translator = self._make_translator()
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(
            id="tool-1",
            type="tool",
            data={"tool": "web_search", "parameters": {"query": "test"}},
        )
        result = translator.translate_tool_node(node)
        assert result["type"] == "tool"
        assert result["id"] == "tool-1"
        assert result["tool"] == "web_search"
        assert result["parameters"] == {"query": "test"}

    def test_translate_tool_node_with_tool_node_data(self):
        """Tool node with ToolNodeData returns correct structure."""
        translator = self._make_translator()
        from core.workflows.schema import ToolNodeData, WorkflowNode

        node = WorkflowNode(
            id="tool-2",
            type="tool",
            data=ToolNodeData(tool="calculator", parameters={"input": "2+2"}),
        )
        result = translator.translate_tool_node(node)
        assert result["tool"] == "calculator"
        assert result["parameters"]["input"] == "2+2"

    def test_translate_tool_defaults_on_missing_tool(self):
        """Tool with no tool name defaults to empty string."""
        translator = self._make_translator()
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(id="tool-3", type="tool", data={})
        result = translator.translate_tool_node(node)
        assert result["tool"] == ""
        assert result["parameters"] == {}

class TestNodeTranslatorTaskNode:
    """Tests for NodeTranslator.translate_task_node()."""

    def _make_translator_with_agents(self, agent_names=None):
        """Create NodeTranslator with specific available agents."""
        if agent_names is None:
            agent_names = []
        mock_agents = []
        for name in agent_names:
            agent = MagicMock()
            agent.name = name
            mock_agents.append(agent)
        with patch("core.workflows.translator.list_agents", return_value=mock_agents):
            from core.workflows.translator import NodeTranslator

            return NodeTranslator()

    def test_translate_task_node_with_valid_agent(self):
        """Task node translates correctly when agent exists."""
        translator = self._make_translator_with_agents(["research_agent"])
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(
            id="task-1",
            type="task",
            data={
                "agent": "research_agent",
                "task": "Do research",
                "context": {"topic": "AI"},
            },
        )
        with patch.object(
            translator,
            "_refresh_agents",
            side_effect=lambda: setattr(translator, "_available_agents", {"research_agent"}),
        ):
            result = translator.translate_task_node(node)
        assert result["type"] == "task"
        assert result["agent"] == "research_agent"
        assert result["task"] == "Do research"
        assert result["context"] == {"topic": "AI"}

    def test_translate_task_node_with_empty_agent_passes(self):
        """Task node with empty agent string passes (no validation needed)."""
        translator = self._make_translator_with_agents([])
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(
            id="task-2",
            type="task",
            data={"agent": "", "task": "Some task", "context": {}},
        )
        with patch.object(translator, "_refresh_agents"):
            translator._available_agents = {"any_agent"}
            result = translator.translate_task_node(node)
        assert result["type"] == "task"
        assert result["agent"] == ""

    def test_translate_task_node_with_unknown_agent_raises(self):
        """Task node with unknown agent raises TranslationError."""
        from core.exceptions import TranslationError

        translator = self._make_translator_with_agents([])
        from core.workflows.schema import WorkflowNode

        node = WorkflowNode(
            id="task-3",
            type="task",
            data={"agent": "nonexistent_agent", "task": "Do stuff", "context": {}},
        )
        with patch.object(translator, "_refresh_agents"):
            translator._available_agents = set()  # No agents available
            with pytest.raises(TranslationError, match="Agent.*not found"):
                translator.translate_task_node(node)

    def test_translate_task_node_with_task_node_data(self):
        """Task node with TaskNodeData dataclass works correctly."""
        translator = self._make_translator_with_agents(["my_agent"])
        from core.workflows.schema import TaskNodeData, WorkflowNode

        node = WorkflowNode(
            id="task-4",
            type="task",
            data=TaskNodeData(agent="my_agent", task="Run task", context={"key": "val"}),
        )
        with patch.object(translator, "_refresh_agents"):
            translator._available_agents = {"my_agent"}
            result = translator.translate_task_node(node)
        assert result["agent"] == "my_agent"
        assert result["context"] == {"key": "val"}

# ===========================================================================
# WorkflowTranslator
# ===========================================================================

class TestWorkflowTranslatorTopologicalSort:
    """Tests for WorkflowTranslator._topological_sort()."""

    def _make_translator(self):
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import WorkflowTranslator

            return WorkflowTranslator()

    def test_simple_linear_order(self):
        """Linear a->b->c produces [a, b, c]."""
        translator = self._make_translator()
        node_ids = ["a", "b", "c"]
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
        result = translator._topological_sort(node_ids, edges)
        # Check order: a before b, b before c
        assert result.index("a") < result.index("b")
        assert result.index("b") < result.index("c")

    def test_all_nodes_present_in_result(self):
        """All node IDs appear in sorted result."""
        translator = self._make_translator()
        node_ids = ["n1", "n2", "n3"]
        edges = [{"source": "n1", "target": "n2"}, {"source": "n1", "target": "n3"}]
        result = translator._topological_sort(node_ids, edges)
        assert set(result) == {"n1", "n2", "n3"}

    def test_no_edges_returns_any_order(self):
        """No edges — any valid order of nodes is acceptable."""
        translator = self._make_translator()
        node_ids = ["x", "y", "z"]
        result = translator._topological_sort(node_ids, [])
        assert set(result) == {"x", "y", "z"}

    def test_cycle_raises_translation_error(self):
        """Cycle in nodes raises TranslationError."""
        from core.exceptions import TranslationError

        translator = self._make_translator()
        node_ids = ["a", "b"]
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]
        with pytest.raises(TranslationError, match="cycle"):
            translator._topological_sort(node_ids, edges)

    def test_single_node_no_edges(self):
        """Single node returns [node]."""
        translator = self._make_translator()
        result = translator._topological_sort(["only"], [])
        assert result == ["only"]

class TestWorkflowTranslatorValidateExecOrder:
    """Tests for WorkflowTranslator.validate_execution_order()."""

    def _make_translator(self):
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import WorkflowTranslator

            return WorkflowTranslator()

    def test_valid_dag_returns_true(self):
        """Valid DAG returns True."""
        translator = self._make_translator()
        assert translator.validate_execution_order(["a", "b"], [{"source": "a", "target": "b"}])

    def test_cyclic_graph_returns_false(self):
        """Cyclic graph returns False."""
        translator = self._make_translator()
        result = translator.validate_execution_order(
            ["a", "b"], [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]
        )
        assert result is False

class TestWorkflowTranslatorResolveDependencies:
    """Tests for WorkflowTranslator.resolve_dependencies()."""

    def _make_translator(self):
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import WorkflowTranslator

            return WorkflowTranslator()

    def test_resolve_direct_dependency(self):
        """Node with one incoming edge gets that source as dependency."""
        translator = self._make_translator()
        edges = [{"source": "a", "target": "b"}]
        deps = translator.resolve_dependencies("b", edges)
        assert "a" in deps

    def test_resolve_no_dependency(self):
        """Node with no incoming edges returns empty list."""
        translator = self._make_translator()
        edges = [{"source": "a", "target": "b"}]
        deps = translator.resolve_dependencies("a", edges)
        assert deps == []

    def test_resolve_multiple_dependencies(self):
        """Node with multiple incoming edges gets all sources."""
        translator = self._make_translator()
        edges = [{"source": "a", "target": "c"}, {"source": "b", "target": "c"}]
        deps = translator.resolve_dependencies("c", edges)
        assert set(deps) == {"a", "b"}

class TestWorkflowTranslatorToFlowConfig:
    """Tests for WorkflowTranslator.to_flowconfig() / translate()."""

    def _make_translator(self):
        with patch("core.workflows.translator.list_agents", return_value=[]):
            from core.workflows.translator import WorkflowTranslator

            return WorkflowTranslator()

    def _make_simple_schema(self, with_metadata=False):
        """Create minimal WorkflowSchema: start -> end."""
        from core.workflows.schema import WorkflowSchema

        data = {
            "nodes": [
                {"id": "n-start", "type": "start", "data": {}},
                {"id": "n-end", "type": "end", "data": {}},
            ],
            "edges": [{"id": "e1", "source": "n-start", "target": "n-end"}],
        }
        if with_metadata:
            data["metadata"] = {"name": "My Workflow", "description": "Test description"}
        return WorkflowSchema.model_validate(data)

    def test_to_flowconfig_returns_flow_config(self):
        """to_flowconfig returns a FlowConfig object."""
        from core.domains.base import FlowConfig

        translator = self._make_translator()
        schema = self._make_simple_schema()
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        assert isinstance(result, FlowConfig)

    def test_translate_is_alias_for_to_flowconfig(self):
        """translate() is an alias for to_flowconfig()."""
        translator = self._make_translator()
        schema = self._make_simple_schema()
        with patch.object(translator._node_translator, "_refresh_agents"):
            result1 = translator.translate(schema)
            result2 = translator.to_flowconfig(schema)
        # Both should produce equivalent structures
        assert result1.name == result2.name
        assert len(result1.nodes) == len(result2.nodes)

    def test_to_flowconfig_uses_metadata_name(self):
        """FlowConfig name comes from workflow metadata."""
        translator = self._make_translator()
        schema = self._make_simple_schema(with_metadata=True)
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        assert result.name == "My Workflow"

    def test_to_flowconfig_includes_all_nodes(self):
        """FlowConfig contains all translated nodes."""
        translator = self._make_translator()
        schema = self._make_simple_schema()
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        assert len(result.nodes) == 2

    def test_to_flowconfig_includes_edges(self):
        """FlowConfig contains all edges."""
        translator = self._make_translator()
        schema = self._make_simple_schema()
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        assert len(result.edges) == 1

    def test_to_flowconfig_nodes_in_topological_order(self):
        """Nodes in FlowConfig are in topological execution order."""
        translator = self._make_translator()
        schema = self._make_simple_schema()
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        # Start node should come before end node
        node_ids = [n["id"] for n in result.nodes]
        assert node_ids.index("n-start") < node_ids.index("n-end")

    def test_to_flowconfig_default_name(self):
        """FlowConfig defaults to 'workflow' when no metadata."""
        translator = self._make_translator()
        schema = self._make_simple_schema(with_metadata=False)
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        assert result.name == "workflow"

    def test_to_flowconfig_with_edge_data(self):
        """Edge data is passed through to FlowConfig."""
        from core.workflows.schema import WorkflowSchema

        translator = self._make_translator()
        # Router node needs 2+ outgoing edges and branches must be dicts
        schema = WorkflowSchema.model_validate(
            {
                "nodes": [
                    {"id": "n-start", "type": "start", "data": {}},
                    {
                        "id": "n-router",
                        "type": "router",
                        "data": {
                            "condition": "x > 1",
                            "branches": [{"id": "b1", "label": "yes"}, {"id": "b2", "label": "no"}],
                        },
                    },
                    {"id": "n-end1", "type": "end", "data": {}},
                    {"id": "n-end2", "type": "end", "data": {}},
                ],
                "edges": [
                    {"id": "e1", "source": "n-start", "target": "n-router"},
                    {
                        "id": "e2",
                        "source": "n-router",
                        "target": "n-end1",
                        "data": {"label": "yes"},
                    },
                    {"id": "e3", "source": "n-router", "target": "n-end2", "data": {"label": "no"}},
                ],
            }
        )
        with patch.object(translator._node_translator, "_refresh_agents"):
            result = translator.to_flowconfig(schema)
        # Edge with data should have 'data' key
        edges_with_data = [e for e in result.edges if "data" in e]
        assert len(edges_with_data) >= 1
