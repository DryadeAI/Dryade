"""Factory regression tests (Phase 119.6, Track 4 Phase D).

Covers 12 categories:
1. Agent creation via unified `create` tool (Phase 167: replaces self_improve)
2. Agent creation via unified `create` tool with artifact_type=agent (Phase 167: replaces create_agent)
3. Tool creation via unified `create` tool with artifact_type=tool (Phase 167: replaces create_tool)
4. Skill creation (API stub)
5. In-flow creation (API stub)
6. Deduplication (API stub)
7. Management tools unbroken
8. Memory tools unbroken
9. Approval flow
10. Autonomy levels
11. Error handling
12. Rollback (archive)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.orchestrator.escalation import (
    EscalationActionType,
    EscalationExecutor,
    PendingEscalation,
)
from core.orchestrator.self_mod_tools import (
    SELF_MOD_TOOL_NAMES,
    execute_self_mod_tool,
    is_self_mod_tool,
)

# ---------------------------------------------------------------------------
# Category 1: Agent creation via unified `create` tool (Phase 167)
# ---------------------------------------------------------------------------

class TestAgentCreationCreate:
    """Unified `create` tool should build FACTORY_CREATE escalation."""

    @pytest.mark.asyncio
    async def test_create_builds_factory_create(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create a websearch agent"},
            conversation_id="test-cat1",
            original_goal="create a websearch agent",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE

    @pytest.mark.asyncio
    async def test_create_includes_goal(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create a data analysis agent"},
            conversation_id="test-cat1b",
            original_goal="create agent",
        )
        assert "data analysis" in result.action.parameters.get("goal", "")

    @pytest.mark.asyncio
    async def test_create_trigger_is_user(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create agent"},
            conversation_id="test-cat1c",
            original_goal="create agent",
        )
        assert result.action.parameters.get("trigger") == "user"

    @pytest.mark.asyncio
    async def test_create_conversation_id_propagated(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create agent"},
            conversation_id="test-cat1d",
            original_goal="create agent",
        )
        assert result.conversation_id == "test-cat1d"
        assert result.action.parameters.get("conversation_id") == "test-cat1d"

# ---------------------------------------------------------------------------
# Category 2: Agent creation via unified `create` with artifact_type=agent
# ---------------------------------------------------------------------------

class TestAgentCreationCreateWithType:
    """Unified `create` tool with artifact_type=agent should build FACTORY_CREATE escalation."""

    @pytest.mark.asyncio
    async def test_create_agent_builds_factory_create(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={
                "name": "code_review",
                "goal": "code review agent",
                "artifact_type": "agent",
            },
            conversation_id="test-cat2",
            original_goal="create code review agent",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE

    @pytest.mark.asyncio
    async def test_create_agent_includes_suggested_name(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={
                "name": "my_agent",
                "goal": "custom agent",
                "artifact_type": "agent",
            },
            conversation_id="test-cat2b",
            original_goal="create agent",
        )
        params = result.action.parameters
        assert params.get("suggested_name") == "my_agent"

    @pytest.mark.asyncio
    async def test_create_agent_without_name(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create something"},
            conversation_id="test-cat2c",
            original_goal="create agent",
        )
        assert isinstance(result, PendingEscalation)
        # No name provided -> suggested_name is None
        assert result.action.parameters.get("suggested_name") is None

# ---------------------------------------------------------------------------
# Category 3: Tool creation via unified `create` with artifact_type=tool
# ---------------------------------------------------------------------------

class TestToolCreation:
    """Unified `create` with artifact_type=tool should build FACTORY_CREATE escalation."""

    @pytest.mark.asyncio
    async def test_create_tool_builds_factory_create(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={
                "name": "json_validator",
                "goal": "Validates JSON schemas",
                "artifact_type": "tool",
            },
            conversation_id="test-cat3",
            original_goal="create validator",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters.get("artifact_type") == "tool"

    @pytest.mark.asyncio
    async def test_create_tool_maps_name_to_suggested_name(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={
                "name": "url_shortener",
                "goal": "Shorten URLs",
                "artifact_type": "tool",
            },
            conversation_id="test-cat3b",
            original_goal="create url shortener",
        )
        assert result.action.parameters.get("suggested_name") == "url_shortener"

    @pytest.mark.asyncio
    async def test_create_tool_maps_goal(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={
                "name": "csv_parser",
                "goal": "Parse CSV files into structured data",
                "artifact_type": "tool",
            },
            conversation_id="test-cat3c",
            original_goal="create parser",
        )
        assert result.action.parameters.get("goal") == "Parse CSV files into structured data"

# ---------------------------------------------------------------------------
# Category 7: Management tools unbroken
# ---------------------------------------------------------------------------

class TestManagementToolsUnbroken:
    """Non-creation self-mod tools must still work after clean break."""

    def test_modify_config_in_tool_names(self):
        assert "modify_config" in SELF_MOD_TOOL_NAMES

    def test_add_mcp_server_in_tool_names(self):
        assert "add_mcp_server" in SELF_MOD_TOOL_NAMES

    def test_remove_mcp_server_in_tool_names(self):
        assert "remove_mcp_server" in SELF_MOD_TOOL_NAMES

    def test_configure_mcp_server_in_tool_names(self):
        assert "configure_mcp_server" in SELF_MOD_TOOL_NAMES

    @pytest.mark.asyncio
    async def test_modify_config_dispatches(self):
        """modify_config returns a PendingEscalation (requires approval)."""
        result = await execute_self_mod_tool(
            tool_name="modify_config",
            arguments={"config_key": "max_iterations", "config_value": "5", "reason": "test"},
            conversation_id="test-cat7",
            original_goal="modify config",
        )
        # modify_config creates a PendingEscalation with MODIFY_CONFIG type
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.MODIFY_CONFIG

    @pytest.mark.asyncio
    async def test_add_mcp_server_dispatches(self):
        """add_mcp_server returns PendingEscalation."""
        result = await execute_self_mod_tool(
            tool_name="add_mcp_server",
            arguments={"name": "test-server", "command": ["echo", "test"]},
            conversation_id="test-cat7b",
            original_goal="add server",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.ADD_MCP_SERVER

    @pytest.mark.asyncio
    async def test_remove_mcp_server_dispatches(self):
        """remove_mcp_server returns PendingEscalation."""
        result = await execute_self_mod_tool(
            tool_name="remove_mcp_server",
            arguments={"name": "test-server"},
            conversation_id="test-cat7c",
            original_goal="remove server",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.REMOVE_MCP_SERVER

    @pytest.mark.asyncio
    async def test_configure_mcp_server_dispatches(self):
        """configure_mcp_server returns PendingEscalation."""
        result = await execute_self_mod_tool(
            tool_name="configure_mcp_server",
            arguments={"name": "test-server", "updates": {"timeout": 30}},
            conversation_id="test-cat7d",
            original_goal="configure server",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.CONFIGURE_MCP_SERVER

# ---------------------------------------------------------------------------
# Category 8: Memory tools unbroken
# ---------------------------------------------------------------------------

class TestMemoryToolsUnbroken:
    """Memory tools should be in SELF_MOD_TOOL_NAMES and dispatch correctly."""

    MEMORY_TOOLS = ["memory_insert", "memory_replace", "memory_rethink", "memory_search"]

    @pytest.mark.parametrize("tool", MEMORY_TOOLS)
    def test_memory_tool_in_names(self, tool):
        assert tool in SELF_MOD_TOOL_NAMES

    @pytest.mark.parametrize("tool", MEMORY_TOOLS)
    def test_memory_tool_is_self_mod(self, tool):
        assert is_self_mod_tool(tool) is True

# ---------------------------------------------------------------------------
# Category 9: Approval flow
# ---------------------------------------------------------------------------

class TestApprovalFlow:
    """FACTORY_CREATE requires user approval via PendingEscalation."""

    @pytest.mark.asyncio
    async def test_factory_create_returns_pending_escalation(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create a test agent"},
            conversation_id="test-cat9",
            original_goal="create agent",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.question  # Must have a question for the user

    @pytest.mark.asyncio
    async def test_factory_create_question_has_approval_prompt(self):
        result = await execute_self_mod_tool(
            tool_name="create",
            arguments={"goal": "create a monitor agent", "name": "monitor"},
            conversation_id="test-cat9b",
            original_goal="create agent",
        )
        # Phase 167: question format is "**Agent Factory** **monitor** -> ..."
        assert "monitor" in result.question
        assert "Agent Factory" in result.question

    @pytest.mark.asyncio
    async def test_factory_create_executor_runs_pipeline(self):
        """When user approves, _factory_create runs FactoryPipeline."""
        executor = EscalationExecutor()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.artifact_type = MagicMock()
        mock_result.artifact_type.value = "agent"
        mock_result.artifact_name = "test-agent"
        mock_result.framework = "mcp"
        mock_result.artifact_path = "/tmp/test"
        mock_result.test_passed = True
        mock_result.test_iterations = 1
        mock_result.deduplication_warnings = []

        with patch("core.factory.orchestrator.FactoryPipeline") as MockPipeline:
            mock_pipeline = AsyncMock()
            mock_pipeline.create.return_value = mock_result
            MockPipeline.return_value = mock_pipeline

            with patch("core.factory.models.FactoryConfig") as MockConfig:
                MockConfig.return_value.enabled = True

                success, msg = await executor._factory_create(
                    {
                        "goal": "create a test agent",
                        "suggested_name": "test-agent",
                        "conversation_id": "test-cat9c",
                    }
                )

        assert success is True
        assert "test-agent" in msg

# ---------------------------------------------------------------------------
# Category 10: Autonomy levels
# ---------------------------------------------------------------------------

class TestAutonomyLevels:
    """Factory respects ActionAutonomy settings."""

    def test_factory_config_has_enabled_field(self):
        """FactoryConfig has enabled field for graceful degradation."""
        try:
            from core.factory.models import FactoryConfig

            config = FactoryConfig()
            assert hasattr(config, "enabled")
        except ImportError:
            pytest.skip("Factory module not installed")

    def test_factory_create_enum_value(self):
        """FACTORY_CREATE has the expected string value."""
        assert EscalationActionType.FACTORY_CREATE.value == "factory_create"

# ---------------------------------------------------------------------------
# Category 11: Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Factory creation failures should be graceful."""

    @pytest.mark.asyncio
    async def test_factory_create_handles_pipeline_failure(self):
        executor = EscalationExecutor()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "Template not found"

        with patch("core.factory.orchestrator.FactoryPipeline") as MockPipeline:
            mock_pipeline = AsyncMock()
            mock_pipeline.create.return_value = mock_result
            MockPipeline.return_value = mock_pipeline

            with patch("core.factory.models.FactoryConfig") as MockConfig:
                MockConfig.return_value.enabled = True

                success, msg = await executor._factory_create(
                    {
                        "goal": "create broken thing",
                        "conversation_id": "test-cat11",
                    }
                )

        assert success is False
        assert "failed" in msg.lower() or "not found" in msg.lower()

    @pytest.mark.asyncio
    async def test_factory_create_handles_exception(self):
        executor = EscalationExecutor()
        with patch(
            "core.factory.orchestrator.FactoryPipeline",
            side_effect=Exception("boom"),
        ):
            with patch("core.factory.models.FactoryConfig") as MockConfig:
                MockConfig.return_value.enabled = True

                success, msg = await executor._factory_create(
                    {
                        "goal": "create thing",
                        "conversation_id": "test-cat11b",
                    }
                )

        assert success is False

    @pytest.mark.asyncio
    async def test_factory_create_no_goal_returns_error(self):
        """_factory_create with empty goal returns error."""
        executor = EscalationExecutor()
        with patch("core.factory.models.FactoryConfig") as MockConfig:
            MockConfig.return_value.enabled = True
            success, msg = await executor._factory_create(
                {
                    "goal": "",
                    "conversation_id": "test-cat11c",
                }
            )
        assert success is False
        assert "goal" in msg.lower() or "no goal" in msg.lower()

    @pytest.mark.asyncio
    async def test_factory_create_disabled_returns_error(self):
        """_factory_create with factory disabled returns clear error."""
        executor = EscalationExecutor()
        with patch("core.factory.models.FactoryConfig") as MockConfig:
            MockConfig.return_value.enabled = False
            success, msg = await executor._factory_create(
                {
                    "goal": "create agent",
                    "conversation_id": "test-cat11d",
                }
            )
        assert success is False
        assert "disabled" in msg.lower()

# ---------------------------------------------------------------------------
# Category 12: Rollback (archive)
# ---------------------------------------------------------------------------

class TestRollback:
    """Factory rollback/archive operations work."""

    def test_factory_registry_has_archive_method(self):
        try:
            from core.factory.registry import FactoryRegistry

            assert hasattr(FactoryRegistry, "archive")
        except ImportError:
            pytest.skip("Factory module not installed")

    def test_factory_artifact_status_enum(self):
        try:
            from core.factory.models import ArtifactStatus

            assert hasattr(ArtifactStatus, "ARCHIVED")
            assert ArtifactStatus.ARCHIVED.value == "archived"
        except ImportError:
            pytest.skip("Factory module not installed")

# ---------------------------------------------------------------------------
# Escalation dispatch still works for all action types
# ---------------------------------------------------------------------------

class TestEscalationDispatchComplete:
    """All EscalationActionType values dispatch correctly."""

    def test_all_action_types_have_handlers(self):
        """Each action type maps to a handler method in EscalationExecutor."""
        executor = EscalationExecutor()
        handler_map = {
            EscalationActionType.UPDATE_MCP_CONFIG: "_update_mcp_config",
            EscalationActionType.CREATE_AGENT: "_create_agent",
            EscalationActionType.CREATE_TOOL: "_create_tool",
            EscalationActionType.MODIFY_CONFIG: "_modify_config",
            EscalationActionType.ADD_MCP_SERVER: "_add_mcp_server",
            EscalationActionType.REMOVE_MCP_SERVER: "_remove_mcp_server",
            EscalationActionType.CONFIGURE_MCP_SERVER: "_configure_mcp_server",
            EscalationActionType.FACTORY_CREATE: "_factory_create",
        }
        for action_type, method_name in handler_map.items():
            assert hasattr(executor, method_name), (
                f"Missing handler {method_name} for {action_type.value}"
            )

    def test_factory_create_enum_exists(self):
        assert EscalationActionType.FACTORY_CREATE.value == "factory_create"

    def test_create_agent_enum_preserved(self):
        """CREATE_AGENT enum value preserved for backward compat."""
        assert EscalationActionType.CREATE_AGENT.value == "create_agent"

    def test_create_tool_enum_preserved(self):
        """CREATE_TOOL enum value preserved for backward compat."""
        assert EscalationActionType.CREATE_TOOL.value == "create_tool"

    def test_all_action_types_enumerated(self):
        """Ensure we have at least 8 action types."""
        assert len(EscalationActionType) >= 8

# ---------------------------------------------------------------------------
# Categories 4-6: Factory pipeline API stubs (full tests in factory suite)
# ---------------------------------------------------------------------------

class TestFactoryPipelineApi:
    """Verify factory pipeline API is accessible."""

    def test_factory_pipeline_importable(self):
        try:
            from core.factory.orchestrator import FactoryPipeline

            assert hasattr(FactoryPipeline, "create")
        except ImportError:
            pytest.skip("Factory module not installed")

    def test_creation_request_importable(self):
        try:
            from core.factory.models import ArtifactType, CreationRequest

            assert hasattr(ArtifactType, "AGENT")
            assert hasattr(ArtifactType, "TOOL")
            assert hasattr(ArtifactType, "SKILL")
        except ImportError:
            pytest.skip("Factory module not installed")

    def test_relevance_module_importable(self):
        try:
            from core.factory.relevance import check_existing_capabilities

            assert callable(check_existing_capabilities)
        except ImportError:
            pytest.skip("Factory module not installed")

    def test_factory_init_exports(self):
        """Factory __init__.py exports expected names."""
        try:
            from core.factory import (
                ArtifactStatus,
                ArtifactType,
                CreationRequest,
                FactoryArtifact,
                FactoryConfig,
            )

            assert FactoryArtifact is not None
            assert FactoryConfig is not None
            assert CreationRequest is not None
            assert ArtifactType is not None
            assert ArtifactStatus is not None
        except ImportError:
            pytest.skip("Factory module not installed")
