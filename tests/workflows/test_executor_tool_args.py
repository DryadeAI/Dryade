"""Tests for workflow executor tool argument merging from state.

Verifies that _create_tool_method correctly merges runtime state (user inputs
and previous node outputs) into tool call parameters before invoking
registry.call_tool_by_name().
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

# Skip module if crewai not available (optional dependency)
pytest.importorskip("crewai")

from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.workflows.executor import WorkflowExecutor

def _make_flow_class(executor, tool_name="test_tool", parameters=None):
    """Helper: generate a Flow class with a single tool node."""
    from core.domains.base import FlowConfig

    node_params = parameters if parameters is not None else {}
    config = FlowConfig(
        name="test_tool_args",
        description="Test flow for tool argument merging",
        nodes=[
            {"id": "start", "type": "start"},
            {"id": "tool_node", "type": "tool", "tool": tool_name, "parameters": node_params},
            {"id": "end", "type": "end"},
        ],
        edges=[
            {"source": "start", "target": "tool_node"},
            {"source": "tool_node", "target": "end"},
        ],
    )
    return executor.generate_flow_class(config)

def _mock_mcp_result(text="ok"):
    """Helper: create a mock MCPToolCallResult."""
    return MCPToolCallResult(content=[MCPToolCallContent(type="text", text=text)])

class TestToolMethodMergesState:
    """Test that tool_method merges runtime state into tool call parameters."""

    @pytest.fixture
    def executor(self):
        return WorkflowExecutor()

    @pytest.mark.asyncio
    @patch("core.workflows.executor.get_registry")
    async def test_tool_method_merges_state_into_empty_params(self, mock_get_registry, executor):
        """Tool node with parameters: {} should populate params from state."""
        mock_registry = Mock()
        mock_registry.call_tool_by_name.return_value = _mock_mcp_result()
        mock_get_registry.return_value = mock_registry

        flow_class = _make_flow_class(executor, parameters={})
        flow = flow_class()

        # Set state values simulating user input and previous node output
        flow.state.start_output = "started"
        # Use model's extra="allow" to set dynamic state fields
        flow.state.__dict__["user_input"] = "hello"
        # Pydantic v2: use model_extra or setattr for extra fields
        flow.state.__pydantic_extra__["user_input"] = "hello"
        flow.state.__pydantic_extra__["prev_data"] = "some data"

        # Get the tool method and call it
        tool_method = flow.tool_node
        await tool_method()

        # Verify call_tool_by_name was called with merged parameters
        mock_registry.call_tool_by_name.assert_called_once()
        call_args = mock_registry.call_tool_by_name.call_args
        passed_params = call_args[0][1]  # second positional arg

        assert "user_input" in passed_params
        assert passed_params["user_input"] == "hello"
        assert "prev_data" in passed_params
        assert passed_params["prev_data"] == "some data"
        # _output suffix should be stripped: start_output -> start
        assert "start" in passed_params
        assert "start_output" not in passed_params

    @pytest.mark.asyncio
    @patch("core.workflows.executor.get_registry")
    async def test_tool_method_preserves_static_params(self, mock_get_registry, executor):
        """Static parameters from node definition should take precedence over state."""
        mock_registry = Mock()
        mock_registry.call_tool_by_name.return_value = _mock_mcp_result()
        mock_get_registry.return_value = mock_registry

        flow_class = _make_flow_class(executor, parameters={"key": "static_value"})
        flow = flow_class()

        # State has conflicting key and an extra key
        flow.state.__pydantic_extra__["key"] = "override_attempt"
        flow.state.__pydantic_extra__["other"] = "extra"

        tool_method = flow.tool_node
        await tool_method()

        mock_registry.call_tool_by_name.assert_called_once()
        call_args = mock_registry.call_tool_by_name.call_args
        passed_params = call_args[0][1]

        # Static params win
        assert passed_params["key"] == "static_value"
        # State fills gaps
        assert passed_params["other"] == "extra"

    @pytest.mark.asyncio
    @patch("core.workflows.executor.get_registry")
    async def test_tool_method_strips_output_suffix(self, mock_get_registry, executor):
        """State fields ending in _output should have suffix stripped in params."""
        mock_registry = Mock()
        mock_registry.call_tool_by_name.return_value = _mock_mcp_result()
        mock_get_registry.return_value = mock_registry

        flow_class = _make_flow_class(executor, parameters={})
        flow = flow_class()

        # Simulate a previous node's output field in state
        # tool_node_output is a defined field, so set it directly
        flow.state.tool_node_output = "review result"

        tool_method = flow.tool_node
        await tool_method()

        mock_registry.call_tool_by_name.assert_called_once()
        call_args = mock_registry.call_tool_by_name.call_args
        passed_params = call_args[0][1]

        # _output suffix stripped: tool_node_output -> tool_node
        assert "tool_node" in passed_params
        assert passed_params["tool_node"] == "review result"
        assert "tool_node_output" not in passed_params

    @pytest.mark.asyncio
    @patch("core.workflows.executor.get_registry")
    async def test_tool_method_skips_internal_fields(self, mock_get_registry, executor):
        """Internal state fields (id, error, started_at, completed_at, final_result) excluded."""
        mock_registry = Mock()
        mock_registry.call_tool_by_name.return_value = _mock_mcp_result()
        mock_get_registry.return_value = mock_registry

        flow_class = _make_flow_class(executor, parameters={})
        flow = flow_class()

        # Set internal fields
        flow.state.error = "some error"
        flow.state.started_at = datetime.now()
        flow.state.completed_at = datetime.now()
        flow.state.final_result = {"some": "result"}
        # id is always set by default

        # Set a useful field
        flow.state.__pydantic_extra__["useful_param"] = "value"

        tool_method = flow.tool_node
        await tool_method()

        mock_registry.call_tool_by_name.assert_called_once()
        call_args = mock_registry.call_tool_by_name.call_args
        passed_params = call_args[0][1]

        # Internal fields excluded
        assert "id" not in passed_params
        assert "error" not in passed_params
        assert "started_at" not in passed_params
        assert "completed_at" not in passed_params
        assert "final_result" not in passed_params

        # Useful param included
        assert "useful_param" in passed_params
        assert passed_params["useful_param"] == "value"

    @pytest.mark.asyncio
    @patch("core.workflows.executor.get_registry")
    async def test_tool_method_skips_none_values(self, mock_get_registry, executor):
        """None values from state should not be added to parameters."""
        mock_registry = Mock()
        mock_registry.call_tool_by_name.return_value = _mock_mcp_result()
        mock_get_registry.return_value = mock_registry

        flow_class = _make_flow_class(executor, parameters={})
        flow = flow_class()

        # Set one real value and one None value
        flow.state.__pydantic_extra__["good_param"] = "value"
        flow.state.__pydantic_extra__["null_param"] = None

        tool_method = flow.tool_node
        await tool_method()

        mock_registry.call_tool_by_name.assert_called_once()
        call_args = mock_registry.call_tool_by_name.call_args
        passed_params = call_args[0][1]

        assert "good_param" in passed_params
        assert passed_params["good_param"] == "value"
        assert "null_param" not in passed_params
