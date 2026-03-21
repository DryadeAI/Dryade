"""Unit tests for core.orchestrator.escalation module.

Covers:
- EscalationActionType enum values
- EscalationAction model creation and validation
- PendingEscalation lifecycle (create, fields, defaults)
- EscalationRegistry: register, get_pending, clear, clear_all, singleton
- is_approval_message: approval patterns, rejection patterns, ambiguous
- EscalationExecutor: execute dispatch, unknown action type, error handling
- EscalationExecutor._update_mcp_config: success, missing path, missing server,
  path already exists, security scoping
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from core.orchestrator.escalation import (
    EscalationAction,
    EscalationActionType,
    EscalationExecutor,
    EscalationRegistry,
    PendingEscalation,
    get_escalation_registry,
    is_approval_message,
)

# ---------------------------------------------------------------------------
# Tests: EscalationActionType
# ---------------------------------------------------------------------------

class TestEscalationActionType:
    def test_update_mcp_config_exists(self):
        assert EscalationActionType.UPDATE_MCP_CONFIG == "update_mcp_config"

    def test_enum_values(self):
        # Only one action type currently
        assert len(EscalationActionType) >= 1

# ---------------------------------------------------------------------------
# Tests: EscalationAction
# ---------------------------------------------------------------------------

class TestEscalationAction:
    def test_creation(self):
        action = EscalationAction(
            action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            parameters={"path": "/home/user"},
            description="Add path to MCP config",
        )
        assert action.action_type == EscalationActionType.UPDATE_MCP_CONFIG
        assert action.parameters["path"] == "/home/user"
        assert action.description == "Add path to MCP config"

    def test_default_parameters(self):
        action = EscalationAction(
            action_type=EscalationActionType.UPDATE_MCP_CONFIG,
        )
        assert action.parameters == {}
        assert action.description == ""

# ---------------------------------------------------------------------------
# Tests: PendingEscalation
# ---------------------------------------------------------------------------

class TestPendingEscalation:
    def test_creation_with_defaults(self):
        escalation = PendingEscalation(
            conversation_id="conv-1",
            original_goal="read my file",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            ),
            question="Allow access?",
        )
        assert escalation.conversation_id == "conv-1"
        assert escalation.original_goal == "read my file"
        assert escalation.question == "Allow access?"
        # Auto-generated fields
        assert escalation.escalation_id  # UUID string
        assert isinstance(escalation.created_at, datetime)
        assert escalation.original_context == {}
        assert escalation.observations == []

    def test_creation_with_observations(self):
        escalation = PendingEscalation(
            conversation_id="conv-1",
            original_goal="test",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            ),
            question="Fix?",
            observations=[{"agent_name": "fs", "error": "denied"}],
        )
        assert len(escalation.observations) == 1
        assert escalation.observations[0]["agent_name"] == "fs"

# ---------------------------------------------------------------------------
# Tests: EscalationRegistry
# ---------------------------------------------------------------------------

class TestEscalationRegistry:
    def _make_escalation(self, conv_id: str = "conv-1"):
        return PendingEscalation(
            conversation_id=conv_id,
            original_goal="test",
            action=EscalationAction(
                action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            ),
            question="Proceed?",
        )

    def test_register_and_get_pending(self):
        registry = EscalationRegistry()
        escalation = self._make_escalation()
        registry.register(escalation)
        assert registry.get_pending("conv-1") is escalation

    def test_get_pending_nonexistent(self):
        registry = EscalationRegistry()
        assert registry.get_pending("conv-999") is None

    def test_register_replaces_existing(self):
        registry = EscalationRegistry()
        e1 = self._make_escalation()
        e2 = self._make_escalation()
        registry.register(e1)
        registry.register(e2)
        assert registry.get_pending("conv-1") is e2

    def test_clear(self):
        registry = EscalationRegistry()
        escalation = self._make_escalation()
        registry.register(escalation)
        cleared = registry.clear("conv-1")
        assert cleared is escalation
        assert registry.get_pending("conv-1") is None

    def test_clear_nonexistent(self):
        registry = EscalationRegistry()
        cleared = registry.clear("conv-999")
        assert cleared is None

    def test_clear_all(self):
        registry = EscalationRegistry()
        registry.register(self._make_escalation("conv-1"))
        registry.register(self._make_escalation("conv-2"))
        registry.clear_all()
        assert registry.get_pending("conv-1") is None
        assert registry.get_pending("conv-2") is None

class TestGetEscalationRegistry:
    def test_singleton(self):
        """get_escalation_registry returns the same instance."""
        import core.orchestrator.escalation as mod

        # Reset to force fresh singleton
        mod._registry = None
        r1 = get_escalation_registry()
        r2 = get_escalation_registry()
        assert r1 is r2
        # Clean up
        mod._registry = None

# ---------------------------------------------------------------------------
# Tests: is_approval_message
# ---------------------------------------------------------------------------

class TestIsApprovalMessage:
    @pytest.mark.parametrize(
        "msg",
        [
            "yes",
            "Yes",
            "YES",
            "yes please",
            "yeah",
            "yep",
            "ok",
            "okay",
            "sure",
            "go ahead",
            "do it",
            "please do",
            "update it",
            "fix it",
            "proceed",
            "approve",
            "approved",
            "confirm",
            "y",
        ],
    )
    def test_approval_patterns(self, msg):
        assert is_approval_message(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "no",
            "No",
            "NO",
            "nope",
            "nah",
            "cancel",
            "don't",
            "dont",
            "stop",
            "never mind",
            "nevermind",
            "skip",
            "n",
        ],
    )
    def test_rejection_patterns(self, msg):
        assert is_approval_message(msg) is False

    @pytest.mark.parametrize(
        "msg",
        [
            "what do you mean?",
            "tell me more",
            "how would that work?",
            "explain",
        ],
    )
    def test_ambiguous_returns_none(self, msg):
        assert is_approval_message(msg) is None

    def test_whitespace_stripping(self):
        assert is_approval_message("  yes  ") is True
        assert is_approval_message("  no  ") is False

    def test_case_insensitive(self):
        assert is_approval_message("YES") is True
        assert is_approval_message("Cancel") is False

# ---------------------------------------------------------------------------
# Tests: EscalationExecutor
# ---------------------------------------------------------------------------

class TestEscalationExecutor:
    @pytest.mark.asyncio
    async def test_execute_update_mcp_config(self):
        executor = EscalationExecutor()
        action = EscalationAction(
            action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            parameters={"path": "/home/user/data", "server": "filesystem"},
        )

        with patch.object(
            executor, "_update_mcp_config", new_callable=AsyncMock, return_value=(True, "done")
        ):
            success, msg = await executor.execute(action)

        assert success is True

    @pytest.mark.asyncio
    async def test_execute_unknown_action_type(self):
        """Unknown action type should return failure."""
        executor = EscalationExecutor()
        # Create a mock action with a fake action_type
        action = MagicMock()
        action.action_type = MagicMock()
        action.action_type.value = "unknown_type"
        # Make the equality check fail for UPDATE_MCP_CONFIG
        action.action_type.__eq__ = lambda self, other: False

        success, msg = await executor.execute(action)
        assert success is False
        assert "Unknown action type" in msg

    @pytest.mark.asyncio
    async def test_execute_exception_handling(self):
        executor = EscalationExecutor()
        action = EscalationAction(
            action_type=EscalationActionType.UPDATE_MCP_CONFIG,
            parameters={"path": "/tmp"},
        )

        with patch.object(
            executor, "_update_mcp_config", new_callable=AsyncMock, side_effect=RuntimeError("boom")
        ):
            success, msg = await executor.execute(action)

        assert success is False
        assert "boom" in msg

class TestUpdateMCPConfig:
    """Tests for EscalationExecutor._update_mcp_config."""

    @pytest.mark.asyncio
    async def test_no_path_specified(self):
        executor = EscalationExecutor()
        success, msg = await executor._update_mcp_config({})
        assert success is False
        assert "No path specified" in msg

    @pytest.mark.asyncio
    async def test_config_file_not_found(self):
        executor = EscalationExecutor()
        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path):
            success, msg = await executor._update_mcp_config({"path": "/tmp/data"})

        assert success is False
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_server_not_in_config(self):
        executor = EscalationExecutor()
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        config_yaml = {"servers": {"other_server": {"command": ["npx"]}}}

        with (
            patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path),
            patch("builtins.open", mock_open()),
            patch("yaml.safe_load", return_value=config_yaml),
        ):
            success, msg = await executor._update_mcp_config(
                {"path": "/tmp", "server": "filesystem"}
            )

        assert success is False
        assert "not found" in msg

    @pytest.mark.asyncio
    async def test_path_already_exists(self):
        executor = EscalationExecutor()
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        config_yaml = {
            "servers": {
                "filesystem": {
                    "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                }
            }
        }

        with (
            patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path),
            patch("builtins.open", mock_open()),
            patch("yaml.safe_load", return_value=config_yaml),
        ):
            success, msg = await executor._update_mcp_config(
                {"path": "/tmp", "server": "filesystem"}
            )

        assert success is True
        assert "already in" in msg

    @pytest.mark.asyncio
    async def test_successful_config_update(self):
        executor = EscalationExecutor()
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        config_yaml = {
            "servers": {
                "filesystem": {
                    "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                }
            }
        }

        with (
            patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path),
            patch("builtins.open", mock_open()),
            patch("yaml.safe_load", return_value=config_yaml),
            patch("yaml.safe_dump") as mock_dump,
            patch.object(
                executor, "_restart_mcp_server", new_callable=AsyncMock, return_value=(True, "OK")
            ),
        ):
            success, msg = await executor._update_mcp_config(
                {"path": "/home/user", "server": "filesystem"}
            )

        assert success is True
        mock_dump.assert_called_once()
        # The command should now include /home/user
        updated_command = config_yaml["servers"]["filesystem"]["command"]
        assert "/home/user" in updated_command

    @pytest.mark.asyncio
    async def test_config_update_restart_failure(self):
        """Config saved but restart failed -- partial success."""
        executor = EscalationExecutor()
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        config_yaml = {
            "servers": {
                "filesystem": {
                    "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                }
            }
        }

        with (
            patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path),
            patch("builtins.open", mock_open()),
            patch("yaml.safe_load", return_value=config_yaml),
            patch("yaml.safe_dump"),
            patch.object(
                executor,
                "_restart_mcp_server",
                new_callable=AsyncMock,
                return_value=(False, "restart failed"),
            ),
        ):
            success, msg = await executor._update_mcp_config(
                {"path": "/home/user", "server": "filesystem"}
            )

        # Partial success: config updated but restart failed
        assert success is True
        assert "restart" in msg.lower()

    @pytest.mark.asyncio
    async def test_no_command_configured(self):
        executor = EscalationExecutor()
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        config_yaml = {
            "servers": {
                "filesystem": {"command": []},
            }
        }

        with (
            patch("core.mcp.autoload.DEFAULT_CONFIG_PATH", mock_path),
            patch("builtins.open", mock_open()),
            patch("yaml.safe_load", return_value=config_yaml),
        ):
            success, msg = await executor._update_mcp_config(
                {"path": "/tmp/new", "server": "filesystem"}
            )

        assert success is False
        assert "no command" in msg.lower()

# ---------------------------------------------------------------------------
# Tests: CREATE_AGENT Escalation
# ---------------------------------------------------------------------------

class TestCreateAgentEscalation:
    """Tests for CREATE_AGENT escalation action type."""

    def test_create_agent_type_exists(self):
        """CREATE_AGENT is a valid EscalationActionType member."""
        assert hasattr(EscalationActionType, "CREATE_AGENT")
        assert EscalationActionType.CREATE_AGENT.value == "create_agent"

    @pytest.mark.asyncio
    async def test_create_agent_delegates_to_factory(self):
        """Post-119.6: _create_agent delegates to _factory_create."""
        executor = EscalationExecutor()
        with patch.object(
            executor,
            "_factory_create",
            new_callable=AsyncMock,
            return_value=(True, "Created agent doc-analyzer"),
        ):
            success, msg = await executor._create_agent(
                {"task_description": "analyze documents", "failed_agent": "doc-analyzer"}
            )
        assert success is True

    @pytest.mark.asyncio
    async def test_create_agent_factory_disabled(self):
        """Post-119.6: _create_agent returns error when factory disabled."""
        executor = EscalationExecutor()
        mock_config = MagicMock()
        mock_config.enabled = False
        with patch("core.factory.models.FactoryConfig", return_value=mock_config):
            success, msg = await executor._create_agent(
                {"task_description": "analyze documents", "failed_agent": "doc-analyzer"}
            )
        assert success is False
        assert "disabled" in msg.lower()

    @pytest.mark.asyncio
    async def test_execute_create_agent_dispatches_to_factory(self):
        """Full execute() dispatches CREATE_AGENT to _create_agent which delegates to factory."""
        executor = EscalationExecutor()
        action = EscalationAction(
            action_type=EscalationActionType.CREATE_AGENT,
            parameters={"task_description": "build reports", "failed_agent": "reporter"},
            description="Create a reporter agent",
        )
        with patch.object(
            executor,
            "_factory_create",
            new_callable=AsyncMock,
            return_value=(True, "Created reporter"),
        ):
            success, msg = await executor.execute(action)
        assert success is True
