"""Command Handlers - Dynamic slash commands from agent tools.

Automatically registers commands for each tool from registered agents.
Commands are named as: /{agent_name}_{tool_name}
"""

import logging
from typing import Any

from core.commands.protocol import Command

logger = logging.getLogger(__name__)

class AgentToolCommand(Command):
    """Dynamic command that wraps an agent tool.

    Created for each tool from each registered agent.
    Example: /audio_transcribe, /filesystem_search
    """

    def __init__(
        self,
        agent_name: str,
        tool_name: str,
        tool_description: str,
        tool_schema: dict[str, Any] | None = None,
    ):
        self._agent_name = agent_name
        self._tool_name = tool_name
        self._description = tool_description
        self._schema = tool_schema

    def get_name(self) -> str:
        return f"{self._agent_name}_{self._tool_name}"

    def get_description(self) -> str:
        return self._description

    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        from core.adapters import get_agent

        logger.info(
            f"Executing /{self._agent_name}_{self._tool_name} for user {context.get('user_id')}"
        )

        agent = get_agent(self._agent_name)
        if agent is None:
            raise RuntimeError(f"Agent '{self._agent_name}' not found")

        # Build task that invokes the specific tool
        task = f"Use the {self._tool_name} tool"
        if args:
            task += f" with parameters: {args}"

        result = await agent.execute(task, context)

        if result.status == "error":
            raise RuntimeError(result.error or "Tool execution failed")

        return result.result

    def get_schema(self) -> dict[str, Any] | None:
        return self._schema

class AgentCommand(Command):
    """Generic agent execution command.

    Usage: /agent <agent_name> <task>
    """

    def get_name(self) -> str:
        return "agent"

    def get_description(self) -> str:
        return "Run any agent with a task"

    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        from core.adapters import get_agent

        agent_name = args.get("agent") or args.get("name")
        task = args.get("task") or args.get("query", "")

        if not agent_name:
            raise ValueError("Agent name required. Usage: /agent <name> <task>")
        if not task:
            raise ValueError("Task required. Usage: /agent <name> <task>")

        agent = get_agent(agent_name)
        if agent is None:
            raise RuntimeError(f"Agent '{agent_name}' not found")

        result = await agent.execute(task, context)
        if result.status == "error":
            raise RuntimeError(result.error or "Agent execution failed")

        return result.result

class HelpCommand(Command):
    """List available commands and agents."""

    def get_name(self) -> str:
        return "help"

    def get_description(self) -> str:
        return "Show available commands and agents"

    async def execute(self, _args: dict[str, Any], _context: dict[str, Any]) -> Any:
        from core.adapters import list_agents
        from core.commands import list_commands

        commands = list_commands()
        agents = list_agents()

        lines = ["**Available Commands:**"]
        for cmd in commands[:20]:  # Limit to first 20
            lines.append(f"- `/{cmd['name']}` - {cmd['description']}")

        if len(commands) > 20:
            lines.append(f"... and {len(commands) - 20} more commands")

        lines.append("\n**Registered Agents:**")
        for card in agents:
            tool_count = len(card.capabilities) if card.capabilities else 0
            lines.append(f"- `{card.name}` ({tool_count} tools) - {card.description[:50]}...")

        return "\n".join(lines)

def get_agent_tool_commands() -> list[Command]:
    """Generate commands from all registered agent tools.

    Returns list of AgentToolCommand instances for each tool.
    """
    from core.adapters import list_agents

    commands = []

    try:
        agents = list_agents()
        for card in agents:
            if not card.capabilities:
                continue

            for capability in card.capabilities:
                cmd = AgentToolCommand(
                    agent_name=card.name,
                    tool_name=capability.name,
                    tool_description=capability.description
                    or f"{card.name} {capability.name} tool",
                    tool_schema=capability.input_schema,
                )
                commands.append(cmd)
                logger.debug(f"Generated command: /{card.name}_{capability.name}")

    except Exception as e:
        logger.warning(f"Failed to load agent tool commands: {e}")

    return commands

def register_all_commands() -> None:
    """Register all built-in and agent tool commands."""
    from core.commands import register_command
    from core.commands.handlers.workflow import WorkflowCommandHandler

    # Built-in commands
    register_command(AgentCommand())
    register_command(HelpCommand())

    # Dynamic commands from agent tools
    for cmd in get_agent_tool_commands():
        register_command(cmd)

    # Workflow commands from scenarios
    workflow_handler = WorkflowCommandHandler()
    for cmd in workflow_handler.get_commands():
        register_command(cmd)

    logger.info("Registered slash commands")

# COMMAND_HANDLERS list for compatibility with plan requirements
# WorkflowCommandHandler is included here for registration
from core.commands.handlers.workflow import WorkflowCommandHandler

COMMAND_HANDLERS = [
    AgentCommand,
    HelpCommand,
    WorkflowCommandHandler,
]

__all__ = [
    "AgentCommand",
    "AgentToolCommand",
    "HelpCommand",
    "WorkflowCommandHandler",
    "COMMAND_HANDLERS",
    "get_agent_tool_commands",
    "register_all_commands",
]
