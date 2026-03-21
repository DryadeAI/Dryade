"""Workflow Command Handler - Chat commands for workflow scenario triggers.

Dynamically registers chat commands based on scenario configurations,
allowing workflows to be triggered via commands like /analyze-report.
Target: ~150 LOC
"""

import logging
from typing import Any

from core.commands.protocol import Command
from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor
from core.workflows.scenarios import ScenarioConfig, ScenarioRegistry, get_registry
from core.workflows.triggers import TriggerHandler, TriggerSource

logger = logging.getLogger("dryade.commands.workflow")

class WorkflowCommand(Command):
    """Dynamic command that triggers a workflow scenario.

    Created for each scenario that has a chat_command trigger configured.
    Example: /analyze-report, /generate-sprint-plan
    """

    def __init__(self, scenario: ScenarioConfig):
        """Initialize command from scenario config.

        Args:
            scenario: ScenarioConfig with chat_command trigger.
        """
        self._scenario = scenario
        self._name = scenario.triggers.chat_command.lstrip("/")
        self._registry = get_registry()
        self._executor = CheckpointedWorkflowExecutor()
        self._handler = TriggerHandler(self._registry, self._executor)

    def get_name(self) -> str:
        """Get command name without / prefix."""
        return self._name

    def get_description(self) -> str:
        """Get command description from scenario."""
        return self._scenario.description[:80]

    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        """Execute workflow scenario via chat command.

        Args:
            args: Command arguments matching scenario inputs.
            context: Execution context with user_id, conversation_id.

        Returns:
            AsyncGenerator yielding SSE events, or final result string.
        """
        user_id = context.get("user_id")

        logger.info(f"[WORKFLOW_CMD] Executing /{self._name} for user {user_id}")

        # Collect all events and return as formatted string
        events = []
        async for event in self._handler.trigger(
            self._scenario.name,
            args,
            TriggerSource.CHAT,
            user_id=user_id,
        ):
            events.append(event)

        # Parse and format results for chat display
        return self._format_for_chat(events)

    def _format_for_chat(self, events: list[str]) -> str:
        """Format SSE events for chat display.

        Args:
            events: List of SSE event strings.

        Returns:
            Formatted string for chat response.
        """
        import json

        lines = [f"**Workflow: {self._scenario.display_name}**\n"]
        result_data = None
        error_msg = None

        for event_str in events:
            if event_str.startswith("data: "):
                try:
                    data = json.loads(event_str[6:].strip())
                    event_type = data.get("type")

                    if event_type == "workflow_start":
                        lines.append(
                            f"Started execution: `{data.get('execution_id', '')[:8]}...`\n"
                        )
                    elif event_type == "node_complete":
                        node_id = data.get("node_id", "")
                        lines.append(f"- Completed: {node_id}")
                    elif event_type == "workflow_complete":
                        result_data = data.get("result")
                    elif event_type == "error":
                        error_msg = data.get("error")
                except json.JSONDecodeError:
                    continue

        if error_msg:
            lines.append(f"\n**Error:** {error_msg}")
        elif result_data:
            if isinstance(result_data, dict):
                output = result_data.get("output", str(result_data))
            else:
                output = str(result_data)
            lines.append(f"\n**Result:**\n{output[:1000]}")

        return "\n".join(lines)

    def get_schema(self) -> dict[str, Any] | None:
        """Get JSON schema for command arguments."""
        if not self._scenario.inputs:
            return None

        properties = {}
        required = []

        for inp in self._scenario.inputs:
            prop = {
                "type": self._map_type(inp.type),
                "description": inp.description,
            }
            if inp.default is not None:
                prop["default"] = inp.default
            properties[inp.name] = prop
            if inp.required:
                required.append(inp.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _map_type(self, scenario_type: str) -> str:
        """Map scenario input types to JSON schema types."""
        type_map = {
            "string": "string",
            "number": "number",
            "boolean": "boolean",
            "json": "object",
            "file": "string",
        }
        return type_map.get(scenario_type, "string")

class WorkflowCommandHandler:
    """Handler that generates and registers workflow commands.

    Discovers scenarios with chat_command triggers and creates
    corresponding Command instances for registration.

    Usage:
        handler = WorkflowCommandHandler()
        commands = handler.get_commands()
        for cmd in commands:
            register_command(cmd)
    """

    def __init__(self, scenarios_dir: str = "workflows/scenarios"):
        """Initialize handler.

        Args:
            scenarios_dir: Path to scenarios directory.
        """
        self._registry = ScenarioRegistry(scenarios_dir)

    def get_commands(self) -> list[Command]:
        """Get list of workflow commands from scenarios.

        Returns:
            List of WorkflowCommand instances for scenarios with chat triggers.
        """
        commands = []

        try:
            scenarios = self._registry.list_scenarios()

            for scenario in scenarios:
                if scenario.triggers.chat_command:
                    cmd = WorkflowCommand(scenario)
                    commands.append(cmd)
                    logger.debug(f"[WORKFLOW_CMD] Generated command: /{cmd.get_name()}")

            logger.info(f"[WORKFLOW_CMD] Generated {len(commands)} workflow commands")

        except Exception as e:
            logger.warning(f"[WORKFLOW_CMD] Failed to load workflow commands: {e}")

        return commands

def register_workflow_commands() -> None:
    """Register all workflow commands from scenarios.

    Called during command system initialization to add workflow
    commands to the global registry.
    """
    from core.commands import register_command

    handler = WorkflowCommandHandler()
    for cmd in handler.get_commands():
        register_command(cmd)
        logger.debug(f"[WORKFLOW_CMD] Registered: /{cmd.get_name()}")

# Export WorkflowCommandHandler for COMMAND_HANDLERS registration
__all__ = [
    "WorkflowCommand",
    "WorkflowCommandHandler",
    "register_workflow_commands",
]
