"""Agent Command Handler - Invoke a specific agent by name.

Target: ~60 LOC
"""

import logging
from typing import Any

from core.commands.protocol import Command

logger = logging.getLogger(__name__)

class AgentCommand(Command):
    """Command to invoke a specific agent by name.

    Usage: /agent agent_name task_description
    """

    def get_name(self) -> str:
        """Return command name."""
        return "agent"

    def get_description(self) -> str:
        """Return command description."""
        return "Invoke a specific agent by name"

    def get_schema(self) -> dict[str, Any] | None:
        """Return argument schema."""
        return {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to invoke",
                },
                "task": {
                    "type": "string",
                    "description": "Task description for the agent",
                },
            },
            "required": ["agent_name", "task"],
        }

    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        """Execute agent invocation.

        Args:
            args: Must contain agent_name and task
            context: Execution context with user_id, conversation_id

        Returns:
            Agent execution result

        Raises:
            ValueError: If agent_name or task missing
            RuntimeError: If agent not found or execution fails
        """
        # Import here to avoid circular imports
        from core.adapters.registry import get_agent

        agent_name = args.get("agent_name")
        task = args.get("task")

        if not agent_name:
            raise ValueError("Missing required argument: agent_name")
        if not task:
            raise ValueError("Missing required argument: task")

        logger.info(f"Executing /agent command: agent={agent_name}, user={context.get('user_id')}")

        # Lookup agent in registry
        agent = get_agent(agent_name)
        if agent is None:
            # Try to find similar agents for suggestion
            from core.adapters.registry import list_agents

            available = [a.name for a in list_agents()]
            import difflib

            suggestions = difflib.get_close_matches(agent_name, available, n=3, cutoff=0.6)
            suggestion_msg = ""
            if suggestions:
                suggestion_msg = f" Did you mean: {', '.join(suggestions)}?"
            raise RuntimeError(f"Agent '{agent_name}' not found.{suggestion_msg}")

        # Execute agent
        try:
            result = await agent.execute(task)
            return {
                "status": "ok",
                "agent": agent_name,
                "result": result.model_dump() if hasattr(result, "model_dump") else result,
            }
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise RuntimeError(f"Agent execution failed: {e}") from e
