"""Import verification tests for Phase 222 plugin-to-core migration.

Proves all 8 migrated modules are importable from their core.* paths
without the plugin manager or any plugin directories.
"""

import pytest

@pytest.mark.unit
class TestMigrationImports:
    """Verify all Phase 222 migrated symbols import from core paths."""

    def test_safety_imports(self):
        from core.safety.validator import (
            SafetyClassifier,
            SafetyLevel,
            SafetyRule,
            classify_safety,
            safety_classifier,
            sanitize_output,
            validate_input,
        )

        assert SafetyLevel is not None
        assert classify_safety is not None

    def test_message_hygiene_imports(self):
        from core.services.message_hygiene import (
            cleanup_orphaned_tool_results,
            ensure_tool_call_ids,
            validate_message_sequence,
        )

        assert cleanup_orphaned_tool_results is not None

    def test_conversation_branching_imports(self):
        from core.services.conversation_branching import (
            ConversationBranch,
            ConversationCheckpoint,
            delete_branch,
            get_branch,
        )

        assert ConversationBranch is not None

    def test_flow_editor_imports(self):
        from core.flows.editor import (
            FlowDefinition,
            FlowEdge,
            FlowNode,
            apply_change,
            validate_flow,
        )

        assert FlowNode is not None
        assert validate_flow is not None

    def test_reactflow_converter_imports(self):
        from core.flows.reactflow_converter import flow_to_reactflow, get_node_style

        assert flow_to_reactflow is not None

    def test_flow_debugger_imports(self):
        from core.orchestrator.flow_debugger import DebugEvent, DebugEventType, FlowDebugger

        assert FlowDebugger is not None

    def test_replayer_imports(self):
        from core.orchestrator.replayer import (
            ExecutionTrace,
            TimeTravel,
            TraceEvent,
            get_time_travel,
        )

        assert TimeTravel is not None

    def test_mcp_bridge_imports(self):
        from core.mcp.bridge import MCPBridge, get_bridge

        assert MCPBridge is not None
