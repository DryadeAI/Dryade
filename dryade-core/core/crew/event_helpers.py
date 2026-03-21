"""Shared event extraction helpers for CrewAI event handling.

Used by both event_bridge.py (SSE streaming) and crewai_tracing.py
(trace storage) to avoid duplicating extraction logic.
"""

from typing import Any


def extract_agent_name(event: Any) -> str | None:
    """Extract agent name from a CrewAI event object.

    Handles both direct string agents and CrewAI Agent objects
    with a .role attribute.

    Args:
        event: CrewAI event with an optional 'agent' attribute.

    Returns:
        Agent name string, or None if not available.
    """
    agent = getattr(event, "agent", None)
    if agent is None:
        return None
    if hasattr(agent, "role"):
        return str(agent.role)
    return str(agent)

def extract_tool_name(event: Any, fallback: str | None = None) -> str | None:
    """Extract tool name from a CrewAI event object.

    Checks 'tool_name' attribute first (used by most CrewAI events),
    then falls back to 'tool' attribute with optional .name resolution.

    Args:
        event: CrewAI event with tool information.
        fallback: Fallback value if no tool name found.

    Returns:
        Tool name string, or fallback if not available.
    """
    # Most CrewAI events use tool_name directly
    tool_name = getattr(event, "tool_name", None)
    if tool_name:
        return str(tool_name)

    # Some events use a tool object with .name
    tool = getattr(event, "tool", None)
    if tool is not None:
        if hasattr(tool, "name"):
            return str(tool.name)
        return str(tool)

    return fallback
