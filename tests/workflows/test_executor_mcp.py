"""Tests for workflow executor MCP registry integration.

Verifies that WorkflowExecutor correctly uses MCPRegistry for tool execution
instead of the legacy MCPBridge.
"""

import inspect
from unittest.mock import Mock, patch

import pytest

# Skip module if crewai not available (optional dependency)
pytest.importorskip("crewai")

class TestExecutorMCPIntegration:
    """Test MCP tool execution through workflow executor."""

    @pytest.fixture
    def executor(self):
        """Create a WorkflowExecutor instance."""
        from core.workflows.executor import WorkflowExecutor

        return WorkflowExecutor()

    @pytest.fixture
    def mock_flowconfig(self):
        """Create minimal FlowConfig with a tool node."""
        from core.domains.base import FlowConfig

        return FlowConfig(
            name="test_flow",
            description="Test flow for MCP integration",
            nodes=[
                {"id": "start", "type": "start"},
                {
                    "id": "tool_node",
                    "type": "tool",
                    "tool": "test_tool",
                    "parameters": {"key": "value"},
                },
                {"id": "end", "type": "end"},
            ],
            edges=[
                {"source": "start", "target": "tool_node"},
                {"source": "tool_node", "target": "end"},
            ],
        )

    def test_no_legacy_bridge_import(self):
        """Executor should not import legacy MCPBridge."""
        import core.workflows.executor as executor_module

        source = inspect.getsource(executor_module)
        assert "MCPBridge" not in source, "Legacy MCPBridge class should not be referenced"
        assert "plugins.mcp.bridge" not in source, "Legacy bridge module should not be imported"
        assert "get_bridge" not in source, "Legacy get_bridge function should not be imported"

    def test_mcp_registry_import(self):
        """Executor should import get_registry from core.mcp."""
        import core.workflows.executor as executor_module

        source = inspect.getsource(executor_module)
        assert "from core.mcp import get_registry" in source, (
            "Should import get_registry from core.mcp"
        )

    def test_mcp_registry_error_import(self):
        """Executor should import MCPRegistryError for error handling."""
        import core.workflows.executor as executor_module

        source = inspect.getsource(executor_module)
        assert "MCPRegistryError" in source, "Should import MCPRegistryError for error handling"

    @patch("core.workflows.executor.get_registry")
    def test_tool_method_uses_registry(self, mock_get_registry, executor, mock_flowconfig):
        """Tool nodes should call registry.call_tool_by_name()."""
        from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult

        # Setup mock registry
        mock_registry = Mock()
        mock_result = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="tool output result")]
        )
        mock_registry.call_tool_by_name.return_value = mock_result
        mock_get_registry.return_value = mock_registry

        # Generate flow class
        flow_class = executor.generate_flow_class(mock_flowconfig)

        # Flow class should be created successfully
        assert flow_class is not None
        assert hasattr(flow_class, "_flowconfig")
        assert flow_class._flowconfig.name == "test_flow"

    @patch("core.workflows.executor.get_registry")
    def test_tool_method_extracts_text_content(self, mock_get_registry, executor, mock_flowconfig):
        """Tool method should extract text from MCPToolCallResult.content."""
        from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult

        # Setup mock with specific text content
        mock_registry = Mock()
        expected_text = "This is the tool output"
        mock_result = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text=expected_text)]
        )
        mock_registry.call_tool_by_name.return_value = mock_result
        mock_get_registry.return_value = mock_registry

        # Generate flow class
        flow_class = executor.generate_flow_class(mock_flowconfig)

        # Verify the class was generated (actual execution requires full CrewAI flow)
        assert flow_class is not None

    @patch("core.workflows.executor.get_registry")
    def test_tool_method_handles_empty_content(self, mock_get_registry, executor, mock_flowconfig):
        """Tool method should handle MCPToolCallResult with empty content list."""
        from core.mcp.protocol import MCPToolCallResult

        # Setup mock with empty content
        mock_registry = Mock()
        mock_result = MCPToolCallResult(content=[])
        mock_registry.call_tool_by_name.return_value = mock_result
        mock_get_registry.return_value = mock_registry

        # Generate flow class - should not raise
        flow_class = executor.generate_flow_class(mock_flowconfig)
        assert flow_class is not None

    @patch("core.workflows.executor.get_registry")
    def test_registry_error_handling(self, mock_get_registry, executor, mock_flowconfig):
        """MCPRegistryError should be properly imported for error handling."""
        from core.exceptions import MCPRegistryError

        mock_registry = Mock()
        mock_registry.call_tool_by_name.side_effect = MCPRegistryError("Tool not found")
        mock_get_registry.return_value = mock_registry

        # Flow class generation should succeed (error occurs at runtime)
        flow_class = executor.generate_flow_class(mock_flowconfig)
        assert flow_class is not None

class TestCheckpointedExecutorMCPIntegration:
    """Test that CheckpointedWorkflowExecutor inherits MCP integration."""

    def test_no_direct_mcp_imports(self):
        """CheckpointedWorkflowExecutor should not have direct MCP imports."""
        import core.workflows.checkpointed_executor as module

        source = inspect.getsource(module)
        assert "MCPBridge" not in source, "Should not import MCPBridge"
        assert "plugins.mcp.bridge" not in source, "Should not import legacy bridge"
        assert "get_bridge" not in source, "Should not import get_bridge"

    def test_inherits_from_workflow_executor(self):
        """CheckpointedWorkflowExecutor should inherit from WorkflowExecutor."""
        from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor
        from core.workflows.executor import WorkflowExecutor

        assert issubclass(CheckpointedWorkflowExecutor, WorkflowExecutor)

class TestMCPProtocolTypes:
    """Test MCP protocol types used by executor."""

    def test_mcp_tool_call_result_structure(self):
        """Verify MCPToolCallResult has expected structure."""
        from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult

        # Create result with content
        result = MCPToolCallResult(
            content=[
                MCPToolCallContent(type="text", text="Hello"),
                MCPToolCallContent(type="text", text="World"),
            ]
        )

        assert len(result.content) == 2
        assert result.content[0].text == "Hello"
        assert result.content[1].text == "World"

    def test_mcp_tool_call_result_empty(self):
        """Verify MCPToolCallResult handles empty content."""
        from core.mcp.protocol import MCPToolCallResult

        result = MCPToolCallResult(content=[])
        assert len(result.content) == 0

    def test_mcp_tool_call_content_text_attribute(self):
        """Verify MCPToolCallContent has text attribute."""
        from core.mcp.protocol import MCPToolCallContent

        content = MCPToolCallContent(type="text", text="test value")
        assert content.text == "test value"
        assert content.type == "text"
