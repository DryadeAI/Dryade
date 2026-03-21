"""Flow Command Handler - Execute a registered flow.

Target: ~60 LOC
"""

import asyncio
import concurrent.futures
import logging
from typing import Any

from core.commands.protocol import Command

logger = logging.getLogger(__name__)

class FlowCommand(Command):
    """Command to execute a registered flow.

    Usage: /flow flow_name inputs_json
    """

    def get_name(self) -> str:
        """Return command name."""
        return "flow"

    def get_description(self) -> str:
        """Return command description."""
        return "Execute a registered flow"

    def get_schema(self) -> dict[str, Any] | None:
        """Return argument schema."""
        return {
            "type": "object",
            "properties": {
                "flow_name": {
                    "type": "string",
                    "description": "Name of the flow to execute",
                },
                "inputs": {
                    "type": "object",
                    "description": "Input values for flow state",
                },
            },
            "required": ["flow_name"],
        }

    async def execute(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        """Execute flow invocation.

        Args:
            args: Must contain flow_name, optionally inputs
            context: Execution context with user_id, conversation_id

        Returns:
            Flow execution result

        Raises:
            ValueError: If flow_name missing
            RuntimeError: If flow not found or execution fails
        """
        # Import here to avoid circular imports
        from core.flows import FLOW_REGISTRY, list_flows

        flow_name = args.get("flow_name")
        inputs = args.get("inputs", {})

        if not flow_name:
            raise ValueError("Missing required argument: flow_name")

        logger.info(f"Executing /flow command: flow={flow_name}, user={context.get('user_id')}")

        # Lookup flow in registry
        if flow_name not in FLOW_REGISTRY:
            available = list_flows()
            import difflib

            suggestions = difflib.get_close_matches(flow_name, available, n=3, cutoff=0.6)
            suggestion_msg = ""
            if suggestions:
                suggestion_msg = f" Did you mean: {', '.join(suggestions)}?"
            raise RuntimeError(f"Flow '{flow_name}' not found.{suggestion_msg}")

        # Execute flow
        try:
            flow_info = FLOW_REGISTRY[flow_name]
            flow_class = flow_info["class"]
            flow = flow_class()

            # Set inputs on flow state
            for key, value in inputs.items():
                if hasattr(flow.state, key):
                    setattr(flow.state, key, value)

            # Execute flow in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(pool, flow.kickoff)

            return {
                "status": "ok",
                "flow": flow_name,
                "result": result if isinstance(result, dict) else {"output": str(result)},
            }
        except Exception as e:
            logger.error(f"Flow execution failed: {e}")
            raise RuntimeError(f"Flow execution failed: {e}") from e
