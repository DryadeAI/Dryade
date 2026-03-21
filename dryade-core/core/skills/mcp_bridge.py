"""Bridge between MCP @tool decorated functions and Skill system.

Converts CrewAI @tool decorated functions into Skill objects for autonomous mode.
This enables tools defined in core/mcp/bridge.py to be discoverable and
executable by the autonomous executor.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.skills.models import Skill

logger = logging.getLogger(__name__)

def bridge_mcp_tool_to_skill(tool_obj: Any) -> "Skill":
    """Convert a CrewAI Tool object to a Skill object.

    CrewAI's @tool decorator creates a Tool object with:
    - name: The tool name
    - description: Full description (may include schema JSON)
    - func: The underlying Python function
    - run(): Method to invoke the tool

    Args:
        tool_obj: A CrewAI Tool object (result of @tool decorator)

    Returns:
        A Skill object representing the tool
    """
    # Import here to avoid circular imports at module level
    from core.skills.models import Skill, SkillMetadata

    # Extract tool name from Tool object
    tool_name = tool_obj.name

    # Get the underlying function for docstring extraction
    underlying_func = getattr(tool_obj, "func", None)
    docstring = underlying_func.__doc__ if underlying_func else None

    # Extract description - prefer docstring over Tool.description
    # (Tool.description includes schema JSON which is too verbose)
    if docstring:
        description = docstring.strip().split("\n\n")[0].strip()
    else:
        description = f"MCP tool: {tool_name}"

    # Create instructions from full docstring
    instructions = f"""## {tool_name}

{docstring or "No documentation available."}

## Execution

This skill is backed by an MCP tool function. When invoked, it will execute
the underlying tool directly via CrewAI's Tool.run() method.
"""

    # Create metadata with callable reference for execution
    # Store both the Tool object (for run()) and the underlying func
    metadata = SkillMetadata(
        extra={
            "source": "mcp_bridge",
            "run": {
                "type": "callable",
                "callable": tool_obj,  # Store the Tool object for run()
                "func": underlying_func,  # Store raw function for introspection
            },
        }
    )

    skill = Skill(
        name=tool_name,
        description=description,
        instructions=instructions,
        metadata=metadata,
        skill_dir="<synthetic>",
    )

    logger.debug(f"Bridged MCP tool '{tool_name}' to Skill")
    return skill

def discover_mcp_tools_as_skills() -> list["Skill"]:
    """Discover all MCP tools and convert them to Skill objects.

    Attempts to import domain tools from core.mcp.bridge.
    This is an optional plugin, so import failures are handled gracefully.

    Returns:
        List of Skill objects representing MCP tools.
        Returns empty list if MCP plugin is not available.
    """
    skills: list[Skill] = []

    try:
        # Import inside function - core.mcp.bridge provides generic bridge
        import core.mcp.bridge as _bridge

        _tools = getattr(_bridge, "DOMAIN_TOOLS", None) or getattr(_bridge, "MCP_TOOLS", [])
        logger.debug(f"Found {len(_tools)} MCP tools to bridge")

        for tool_func in _tools:
            try:
                skill = bridge_mcp_tool_to_skill(tool_func)
                skills.append(skill)
            except Exception as e:
                tool_name = getattr(tool_func, "name", getattr(tool_func, "__name__", "unknown"))
                logger.warning(f"Failed to bridge MCP tool '{tool_name}': {e}")

        logger.info(f"Discovered {len(skills)} MCP tools as skills")

    except ImportError:
        logger.debug("MCP plugin not available - no MCP tools to bridge")
    except Exception as e:
        logger.warning(f"Failed to discover MCP tools: {e}")

    return skills
