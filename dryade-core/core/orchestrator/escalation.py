"""Escalation Action System.

Provides a generic mechanism for the orchestrator to propose fixes
that require user approval, then execute them automatically.

Flow:
1. Orchestrator detects a fixable error (e.g., MCP path restriction)
2. LLM proposes a fix action with parameters
3. Escalation is stored with pending status
4. User approves (or rejects)
5. If approved, executor runs the fix and retries original goal
"""

import logging
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

__all__ = [
    "EscalationActionType",
    "EscalationAction",
    "PendingEscalation",
    "EscalationRegistry",
    "EscalationExecutor",
    "get_escalation_registry",
    "is_approval_message",
]

class EscalationActionType(str, Enum):
    """Types of automatic fixes the system can perform.

    .. deprecated:: v1.1
        CREATE_AGENT and CREATE_TOOL will be removed in v1.1.
        Active references exist in orchestrator.py, complex_handler.py, and tests.
        Migration: replace all CREATE_AGENT/CREATE_TOOL usage with FACTORY_CREATE.
    """

    UPDATE_MCP_CONFIG = "update_mcp_config"  # Add path to MCP server allowed dirs
    CREATE_AGENT = "create_agent"  # DEPRECATED (Phase 167): Use FACTORY_CREATE. Remove in v1.1 after migration window.
    CREATE_TOOL = "create_tool"  # DEPRECATED (Phase 167): Use FACTORY_CREATE. Remove in v1.1 after migration window.
    MODIFY_CONFIG = "modify_config"  # Modify orchestrator/agent config (Phase 115.1)
    ADD_MCP_SERVER = "add_mcp_server"  # Add new MCP server (Phase 115.2)
    REMOVE_MCP_SERVER = "remove_mcp_server"  # Remove MCP server (Phase 115.2)
    CONFIGURE_MCP_SERVER = "configure_mcp_server"  # Modify MCP server config (Phase 115.2)
    FACTORY_CREATE = "factory_create"  # Factory artifact creation (Phase 119.4)

class EscalationAction(BaseModel):
    """A proposed fix action that can be executed automatically.

    Attributes:
        action_type: The type of fix to perform
        parameters: Action-specific parameters (e.g., {"path": "/home/user", "server": "filesystem"})
        description: Human-readable description of what will be done
    """

    action_type: EscalationActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    description: str = ""

class PendingEscalation(BaseModel):
    """A pending escalation waiting for user approval.

    Attributes:
        escalation_id: Unique identifier
        conversation_id: The conversation this escalation belongs to
        original_goal: What the user originally asked for
        original_context: Context from the original request
        action: The proposed fix action
        question: The question shown to the user
        created_at: When the escalation was created
    """

    escalation_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    original_goal: str
    original_context: dict[str, Any] = Field(default_factory=dict)
    action: EscalationAction
    question: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    observations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Serialized observations from the orchestration that triggered escalation",
    )
    # Stateful escalation fields (Phase 92, ADR-002 Sub-Decision D)
    orchestration_state: dict[str, Any] | None = Field(
        default=None,
        description="Serialized OrchestrationState for retry continuity",
    )
    observation_history: dict[str, Any] | None = Field(
        default=None,
        description="Serialized ObservationHistory for retry continuity",
    )

class EscalationRegistry:
    """Registry for pending escalations.

    Stores escalations in memory, keyed by conversation_id.
    Only one pending escalation per conversation at a time.
    """

    def __init__(self):
        self._pending: dict[str, PendingEscalation] = {}

    def register(self, escalation: PendingEscalation) -> None:
        """Register a new pending escalation.

        Replaces any existing escalation for the same conversation.
        """
        self._pending[escalation.conversation_id] = escalation

        # Persist to factory registry for Signal 2 analysis (best-effort)
        try:
            from core.factory.registry import get_factory_registry

            registry = get_factory_registry()
            registry.record_escalation(
                action_type=escalation.action.action_type.value,
                description=escalation.action.description,
                conversation_id=escalation.conversation_id,
                suggested_name=escalation.action.parameters.get("suggested_name", ""),
            )
        except Exception:
            logger.debug(
                "[ESCALATION] Failed to persist to factory registry",
                exc_info=True,
            )

        logger.info(
            f"[ESCALATION] Registered pending escalation {escalation.escalation_id} "
            f"for conversation {escalation.conversation_id}: {escalation.action.action_type.value}"
        )

    def get_pending(self, conversation_id: str) -> PendingEscalation | None:
        """Get pending escalation for a conversation, if any."""
        return self._pending.get(conversation_id)

    def clear(self, conversation_id: str) -> PendingEscalation | None:
        """Clear and return the pending escalation for a conversation."""
        escalation = self._pending.pop(conversation_id, None)

        # Update escalation status in factory registry (best-effort)
        try:
            from core.factory.registry import get_factory_registry

            registry = get_factory_registry()
            status = "resolved" if escalation else "rejected"
            registry.update_escalation_status(conversation_id, status)
        except Exception:
            logger.debug(
                "[ESCALATION] Failed to update factory registry status",
                exc_info=True,
            )

        if escalation:
            logger.info(
                f"[ESCALATION] Cleared escalation {escalation.escalation_id} "
                f"for conversation {conversation_id}"
            )
        return escalation

    def clear_all(self) -> None:
        """Clear all pending escalations."""
        self._pending.clear()

# Global registry instance
_registry: EscalationRegistry | None = None

def get_escalation_registry() -> EscalationRegistry:
    """Get the global escalation registry."""
    global _registry
    if _registry is None:
        _registry = EscalationRegistry()
    return _registry

# Approval detection patterns
APPROVAL_PATTERNS = [
    r"^yes\b",
    r"^yeah\b",
    r"^yep\b",
    r"^ok\b",
    r"^okay\b",
    r"^sure\b",
    r"^go ahead\b",
    r"^do it\b",
    r"^please do\b",
    r"^update it\b",
    r"^fix it\b",
    r"^proceed\b",
    r"^approved?\b",
    r"^confirm\b",
    r"^y\b",
    # BUG-001: Expanded approval patterns for common user confirmations
    r"^create\s+(it|one|that|the\s+\w+)\b",
    r"^make\s+(it|one|that)\b",
    r"^let'?s\s+(do|go|try)\b",
    r"^go\s+for\s+it\b",
    r"^sounds?\s+good\b",
    r"^that'?s?\s+(fine|good|great|perfect|ok|okay)\b",
    r"^absolutely\b",
    r"^definitely\b",
    r"^of\s+course\b",
    r"^right\b",
    r"^correct\b",
    r"^affirmative\b",
    r"^exactly\b",
    r"^perfect\b",
    r"^great\b",
    r"^fine\b",
    r"^alright\b",
    r"^works?\s+for\s+me\b",
    # French approval
    r"^oui\b",
    r"^ouais\b",
    r"^d'accord\b",
    r"^bien\s+s[uû]r\b",
    r"^[eé]videmment\b",
    r"^absolument\b",
    r"^parfait\b",
    r"^c'est\s+bon\b",
    r"^vas-y\b",
    r"^fais-le\b",
    # Spanish approval
    r"^s[ií]\b",
    r"^claro\b",
    r"^por\s+supuesto\b",
    r"^adelante\b",
    r"^hazlo\b",
    r"^perfecto\b",
    r"^de\s+acuerdo\b",
    # German approval
    r"^ja\b",
    r"^jawohl\b",
    r"^nat[uü]rlich\b",
    r"^klar\b",
    r"^selbstverst[aä]ndlich\b",
    r"^mach\s+es\b",
    r"^genau\b",
    r"^richtig\b",
    # Italian approval
    r"^s[iì]\b",
    r"^certo\b",
    r"^certamente\b",
    r"^ovviamente\b",
    r"^perfetto\b",
    r"^vai\b",
    r"^fallo\b",
    # Portuguese approval
    r"^sim\b",
    r"^com\s+certeza\b",
    r"^pode\s+fazer\b",
    r"^perfeito\b",
]

REJECTION_PATTERNS = [
    r"^no\b",
    r"^nope\b",
    r"^nah\b",
    r"^cancel\b",
    r"^don'?t\b",
    r"^stop\b",
    r"^never\s*mind\b",
    r"^skip\b",
    r"^n\b",
    # French rejection
    r"^non\b",
    r"^pas\s+du\s+tout\b",
    r"^annuler\b",
    r"^arr[eê]te\b",
    # Spanish rejection
    r"^para\b",
    r"^cancelar\b",
    r"^detente\b",
    # German rejection
    r"^nein\b",
    r"^stopp\b",
    r"^abbrechen\b",
    r"^halt\b",
    # Italian rejection
    r"^ferma\b",
    r"^annulla\b",
    r"^basta\b",
    # Portuguese rejection
    r"^n[aã]o\b",
    r"^parar\b",
]

def is_approval_message(message: str) -> bool | None:
    """Check if a message indicates approval of a pending escalation.

    Returns:
        True if approval, False if rejection, None if neither
    """
    msg_lower = message.strip().lower()

    for pattern in APPROVAL_PATTERNS:
        if re.match(pattern, msg_lower, re.IGNORECASE):
            return True

    for pattern in REJECTION_PATTERNS:
        if re.match(pattern, msg_lower, re.IGNORECASE):
            return False

    return None

class EscalationExecutor:
    """Executes approved escalation actions.

    Each action type has a dedicated handler method.
    """

    async def execute(self, action: EscalationAction) -> tuple[bool, str]:
        """Execute an escalation action.

        Args:
            action: The action to execute

        Returns:
            (success, message) tuple
        """
        logger.info(f"[ESCALATION] Executing action: {action.action_type.value}")

        from core.auth.audit import log_audit_sync
        try:
            log_audit_sync(None, "", f"escalation_{action.action_type.value}", "escalation", "",
                           metadata={"action_type": action.action_type.value,
                                     "description": str(getattr(action, "description", ""))[:200]})
        except Exception:
            pass

        try:
            if action.action_type == EscalationActionType.UPDATE_MCP_CONFIG:
                return await self._update_mcp_config(action.parameters)
            elif action.action_type == EscalationActionType.CREATE_AGENT:
                return await self._create_agent(action.parameters)
            elif action.action_type == EscalationActionType.CREATE_TOOL:
                return await self._create_tool(action.parameters)
            elif action.action_type == EscalationActionType.MODIFY_CONFIG:
                return await self._modify_config(action.parameters)
            elif action.action_type == EscalationActionType.ADD_MCP_SERVER:
                return await self._add_mcp_server(action.parameters)
            elif action.action_type == EscalationActionType.REMOVE_MCP_SERVER:
                return await self._remove_mcp_server(action.parameters)
            elif action.action_type == EscalationActionType.CONFIGURE_MCP_SERVER:
                return await self._configure_mcp_server(action.parameters)
            elif action.action_type == EscalationActionType.FACTORY_CREATE:
                return await self._factory_create(action.parameters)
            else:
                return False, f"Unknown action type: {action.action_type}"
        except Exception as e:
            logger.exception(f"[ESCALATION] Action execution failed: {e}")
            return False, f"Failed to execute action: {str(e)}"

    async def _update_mcp_config(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Update MCP server configuration to add an allowed path.

        Parameters:
            - path: The path to add to allowed directories
            - server: The MCP server name (default: "filesystem")
        """
        path_to_add = parameters.get("path")
        server_name = parameters.get("server", "filesystem")

        if not path_to_add:
            return False, "No path specified for MCP config update"

        # Find the config file
        import core.mcp.autoload as _autoload

        config_path = _autoload.DEFAULT_CONFIG_PATH

        if not config_path.exists():
            return False, f"MCP config file not found at {config_path}"

        try:
            # Read current config
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            servers = config.get("servers", {})
            if server_name not in servers:
                return False, f"Server '{server_name}' not found in MCP config"

            server_config = servers[server_name]
            command = server_config.get("command", [])

            if not command:
                return False, f"Server '{server_name}' has no command configured"

            # The filesystem server command format is:
            # ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path1", "/path2", ...]
            # We need to add our path to the allowed paths

            # Check if path already exists
            if path_to_add in command:
                return True, f"Path '{path_to_add}' is already in the allowed directories"

            # Find where to insert (after the server package name)
            # Look for the @modelcontextprotocol/server-filesystem entry
            insert_index = len(command)
            for i, arg in enumerate(command):
                if "@modelcontextprotocol/server-filesystem" in arg:
                    insert_index = i + 1
                    break

            # Insert the new path
            command.insert(insert_index, path_to_add)
            server_config["command"] = command

            # Write updated config
            with open(config_path, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"[ESCALATION] Added '{path_to_add}' to {server_name} allowed paths")

            # Restart the MCP server to apply changes
            logger.info("[ESCALATION] Config updated, attempting restart...")

            restart_success, restart_message = await self._restart_mcp_server(server_name)

            if restart_success:
                return True, (
                    f"Updated '{path_to_add}' in {server_name} config and verified server restart."
                )
            else:
                # Config saved but restart failed
                # This is partial success - config is correct but server needs manual restart
                logger.warning(f"[ESCALATION] Config updated but restart failed: {restart_message}")
                return True, (
                    f"Config updated to allow '{path_to_add}' in {server_name}. "
                    f"However, the server restart could not be verified: {restart_message}. "
                    f"Please try the operation again (server may have started late), "
                    f"restart the MCP server manually via CLI, or restart Dryade."
                )

        except Exception as e:
            logger.exception(f"[ESCALATION] Failed to update MCP config: {e}")
            return False, f"Failed to update MCP config: {str(e)}"

    async def _verify_mcp_restart(
        self,
        server_name: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> tuple[bool, str]:
        """Verify MCP server restarted successfully.

        Checks server health with retries to handle startup delay.

        Args:
            server_name: Name of the MCP server to verify.
            max_retries: Number of verification attempts.
            retry_delay: Delay between retries in seconds.

        Returns:
            (success, message) tuple indicating verification result.
        """
        import asyncio

        from core.mcp.registry import get_registry

        registry = get_registry()

        for attempt in range(max_retries):
            try:
                # Check if server is running
                if not registry.is_running(server_name):
                    logger.warning(
                        f"[ESCALATION] Server {server_name} not running after restart "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(retry_delay)
                    continue

                # Try to list tools as health check
                tools = registry.list_tools(server_name)
                if tools is not None:
                    logger.info(
                        f"[ESCALATION] Server {server_name} verified - {len(tools)} tools available"
                    )
                    return True, f"Server {server_name} restarted successfully"

            except Exception as e:
                logger.warning(
                    f"[ESCALATION] Verification attempt {attempt + 1}/{max_retries} failed: {e}"
                )

            await asyncio.sleep(retry_delay)

        return (
            False,
            f"Server {server_name} restart could not be verified after {max_retries} attempts",
        )

    async def _restart_mcp_server(self, server_name: str) -> tuple[bool, str]:
        """Restart an MCP server to apply config changes with verification.

        Stops the server, re-registers with updated config, starts it,
        and verifies the restart succeeded via health check.

        Args:
            server_name: Name of the MCP server to restart.

        Returns:
            (success, message) tuple indicating restart and verification result.
        """
        try:
            from core.mcp.registry import get_registry

            registry = get_registry()

            if registry.is_running(server_name):
                logger.info(f"[ESCALATION] Stopping MCP server: {server_name}")
                registry.stop(server_name)

            # Re-register with updated config
            from core.mcp.autoload import _config_to_mcp_server_config, load_mcp_config

            config = load_mcp_config()
            servers = config.get("servers", {})

            if server_name in servers:
                server_cfg = servers[server_name]
                mcp_config = _config_to_mcp_server_config(server_name, server_cfg)

                # Unregister old config and register new
                if registry.is_registered(server_name):
                    registry.unregister(server_name)

                registry.register(mcp_config)
                logger.info(f"[ESCALATION] Re-registered MCP server: {server_name}")

                # Start the server
                registry.start(server_name)
                logger.info(f"[ESCALATION] Started MCP server: {server_name}")

                # Verify restart succeeded
                success, message = await self._verify_mcp_restart(server_name)
                if not success:
                    logger.error(f"[ESCALATION] Restart verification failed: {message}")
                    return False, message

                return True, message

            return False, f"Server {server_name} not found in config"

        except Exception as e:
            logger.warning(f"[ESCALATION] Failed to restart MCP server: {e}")
            return False, f"Failed to restart MCP server: {str(e)}"

    async def _create_agent(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Create a new agent -- delegates to Agent Factory.

        Post-119.6: Legacy agent_resolver logic removed. All creation
        goes through the factory pipeline via _factory_create().
        When factory is disabled, returns a clear error message.
        """
        try:
            from core.factory.models import FactoryConfig

            if not FactoryConfig().enabled:
                return False, (
                    "The Agent Factory is currently disabled. "
                    "Enable it in Settings to create agents."
                )
        except ImportError:
            return False, "Factory module is not installed."

        # Map CREATE_AGENT parameters to FACTORY_CREATE parameters
        goal = parameters.get("task_description", parameters.get("goal", ""))
        suggested_name = parameters.get("suggested_name") or parameters.get("failed_agent")
        # Normalize name to lowercase kebab-case (Factory validation: ^[a-z][a-z0-9_-]*$)
        if suggested_name:
            import re as _re

            suggested_name = _re.sub(r"[^a-z0-9_-]", "-", suggested_name.lower()).strip("-")
            if suggested_name and not suggested_name[0].isalpha():
                suggested_name = "agent-" + suggested_name
        factory_params = {
            "goal": goal,
            "suggested_name": suggested_name,
            "trigger": "escalation",
            "conversation_id": parameters.get("conversation_id"),
        }
        return await self._factory_create(factory_params)

    async def _create_tool(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Create a new tool -- delegates to Agent Factory.

        Post-119.6: Legacy placeholder tool logic removed. All creation
        goes through the factory pipeline via _factory_create().
        When factory is disabled, returns a clear error message.
        """
        try:
            from core.factory.models import FactoryConfig

            if not FactoryConfig().enabled:
                return False, (
                    "The Agent Factory is currently disabled. "
                    "Enable it in Settings to create tools."
                )
        except ImportError:
            return False, "Factory module is not installed."

        tool_name = parameters.get("tool_name", "unnamed_tool")
        description = parameters.get("description") or parameters.get("task_description", "")
        factory_params = {
            "goal": description or f"Create tool: {tool_name}",
            "suggested_name": tool_name,
            "artifact_type": "tool",
            "trigger": "escalation",
            "conversation_id": parameters.get("conversation_id"),
        }
        return await self._factory_create(factory_params)

    async def _modify_config(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Modify orchestration configuration at runtime.

        Only allows modification of keys in MUTABLE_CONFIG_KEYS allowlist.
        Changes are applied to the singleton OrchestrationConfig instance.
        """
        from core.orchestrator.config import MUTABLE_CONFIG_KEYS, get_orchestration_config

        config_key = parameters.get("config_key", "")
        config_value = parameters.get("config_value", "")
        reason = parameters.get("reason", "")

        logger.info(f"[ESCALATION] Modifying config: {config_key}={config_value} ({reason})")

        if config_key not in MUTABLE_CONFIG_KEYS:
            return False, (
                f"Config key '{config_key}' is not in the mutable allowlist. "
                f"Allowed keys: {', '.join(sorted(MUTABLE_CONFIG_KEYS))}"
            )

        cfg = get_orchestration_config()

        # Validate the key exists on the config object
        if not hasattr(cfg, config_key):
            return False, f"Config key '{config_key}' does not exist on OrchestrationConfig"

        # Coerce value to the field's type
        current = getattr(cfg, config_key)
        try:
            if isinstance(current, bool):
                coerced = str(config_value).lower() in ("true", "1", "yes")
            elif isinstance(current, int):
                coerced = int(config_value)
            elif isinstance(current, float):
                coerced = float(config_value)
            else:
                coerced = config_value

            object.__setattr__(cfg, config_key, coerced)
            return True, (
                f"Config '{config_key}' updated to '{coerced}'"
                + (f" (reason: {reason})" if reason else "")
            )
        except (ValueError, TypeError) as e:
            return False, f"Cannot set '{config_key}' to '{config_value}': {e}"

    async def _add_mcp_server(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Add a new MCP server at runtime.

        Parameters:
            - name: Server name (required)
            - command: Command list (required for stdio)
            - transport: "stdio" or "http" (default: "stdio")
            - env: Environment variables dict
            - url: URL for HTTP transport
            - description: Human-readable description
        """
        try:
            from core.mcp.self_mod import add_mcp_server

            name = parameters.get("name")
            if not name:
                return False, "No server name specified"

            command = parameters.get("command", [])
            transport = parameters.get("transport", "stdio")
            env = parameters.get("env")
            url = parameters.get("url")
            description = parameters.get("description")

            return await add_mcp_server(
                name=name,
                command=command,
                transport=transport,
                env=env,
                url=url,
                description=description,
            )
        except Exception as e:
            logger.exception("[ESCALATION] Failed to add MCP server: %s", e)
            return False, f"Failed to add MCP server: {e}"

    async def _remove_mcp_server(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Remove an MCP server at runtime.

        Parameters:
            - name: Server name to remove (required)
        """
        try:
            from core.mcp.self_mod import remove_mcp_server

            name = parameters.get("name")
            if not name:
                return False, "No server name specified"

            return await remove_mcp_server(name)
        except Exception as e:
            logger.exception("[ESCALATION] Failed to remove MCP server: %s", e)
            return False, f"Failed to remove MCP server: {e}"

    async def _configure_mcp_server(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Configure an existing MCP server at runtime.

        Parameters:
            - name: Server name (required)
            - updates: Dict of configuration changes (env, command, enabled, timeout, description)
        """
        try:
            from core.mcp.self_mod import configure_mcp_server

            name = parameters.get("name")
            if not name:
                return False, "No server name specified"

            updates = parameters.get("updates", {})
            if not updates:
                return False, "No updates specified"

            return await configure_mcp_server(name, updates)
        except Exception as e:
            logger.exception("[ESCALATION] Failed to configure MCP server: %s", e)
            return False, f"Failed to configure MCP server: {e}"

    async def _factory_create(self, parameters: dict[str, Any]) -> tuple[bool, str]:
        """Execute factory creation after user approval.

        Runs full TCST pipeline (config + scaffold + test + register).
        Called by the escalation executor when user approves FACTORY_CREATE.
        """
        try:
            from core.factory.models import ArtifactType, CreationRequest, FactoryConfig
            from core.factory.orchestrator import FactoryPipeline

            # Graceful degradation (Q9)
            if not FactoryConfig().enabled:
                return (
                    False,
                    "The Agent Factory is currently disabled. Enable it in Settings to create artifacts.",
                )

            goal = parameters.get("goal", "")
            if not goal:
                return False, "No goal specified for factory creation"

            from core.auth.audit import log_audit_sync
            try:
                log_audit_sync(None, "", "factory_create_initiated", "factory", "",
                               metadata={"goal": str(goal)[:200]})
            except Exception:
                pass

            artifact_type = None
            if parameters.get("artifact_type"):
                artifact_type = ArtifactType(parameters["artifact_type"])

            raw_name = parameters.get("suggested_name")
            if raw_name:
                import re as _re

                raw_name = _re.sub(r"[^a-z0-9_-]", "-", raw_name.lower()).strip("-")
                if raw_name and not raw_name[0].isalpha():
                    raw_name = "agent-" + raw_name

            request = CreationRequest(
                goal=goal,
                suggested_name=raw_name,
                artifact_type=artifact_type,
                framework=parameters.get("framework"),
                trigger=parameters.get("trigger", "user"),
                conversation_id=parameters.get("conversation_id"),
            )

            pipeline = FactoryPipeline(conversation_id=parameters.get("conversation_id"))
            # skip_autonomy=True: user already approved via escalation — don't ask again
            result = await pipeline.create(request, fast_path=False, skip_autonomy=True)

            if result.success:
                msg_parts = [
                    f"Created {result.artifact_type.value} **{result.artifact_name}**",
                    f"Framework: {result.framework}",
                    f"Path: `{result.artifact_path}`",
                ]
                if result.test_passed:
                    msg_parts.append(f"Tests passed ({result.test_iterations} iteration(s))")
                if result.deduplication_warnings:
                    msg_parts.append(
                        f"Note: Similar capabilities exist: {', '.join(result.deduplication_warnings[:3])}"
                    )
                return True, "\n".join(msg_parts)

            return False, f"Factory creation failed: {result.message}"

        except ImportError as e:
            logger.warning("[ESCALATION] Factory module not available: %s", e)
            return False, "Factory module is not installed"
        except ValueError as e:
            logger.warning("[ESCALATION] Factory creation rejected: %s", e)
            return False, str(e)
        except Exception as e:
            logger.exception("[ESCALATION] Factory creation failed: %s", e)
            return False, f"Factory creation error: {e}"
