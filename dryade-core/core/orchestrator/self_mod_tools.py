"""Self-modification tool definitions for the orchestrator.

Phase 115.1: Register self-mod tools (self_improve, create_tool, modify_config)
as first-class OpenAI function-calling tools instead of relying on regex-based
meta-action detection.

Phase 115.2: Expanded to 8 tools (+ create_agent, add_mcp_server, remove_mcp_server,
configure_mcp_server, search_capabilities) with model-aware description variants
and read-only tool support. search_capabilities returns results directly from
CapabilityRegistry without escalation.

Phase 115.3: Added 4 memory tools (memory_insert, memory_replace, memory_rethink,
memory_search) for Letta-inspired agent self-modification of context via memory
blocks. All memory tools are read-only (modify agent memory, not system state).

Phase 167: Tool consolidation — self_improve/create_agent/create_tool merged into
unified `create` tool with optional artifact_type parameter. memory_delete added.
Always-inject wiring: self-mod tools are injected for all function-calling providers
(not just meta_hint). Language-agnostic meta-action detection (no English regex).
"""

import logging

from core.orchestrator.escalation import (
    EscalationAction,
    EscalationActionType,
    PendingEscalation,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SELF_MOD_TOOL_NAMES",
    "SELF_MOD_TOOLS",
    "READ_ONLY_TOOL_NAMES",
    "is_self_mod_tool",
    "is_read_only_tool",
    "get_self_mod_tools",
    "execute_self_mod_tool",
]

# Set of self-modification tool names for O(1) lookup
# Phase 167: Consolidated from 12 to 11 tools.
# create_agent/create_tool/self_improve merged into unified `create` tool.
# memory_delete added.
SELF_MOD_TOOL_NAMES: set[str] = {
    "factory_create",
    "memory_delete",
    "modify_config",
    "add_mcp_server",
    "remove_mcp_server",
    "configure_mcp_server",
    "search_capabilities",
    "memory_insert",
    "memory_replace",
    "memory_rethink",
    "memory_search",
}

# Read-only tools return results directly without escalation.
# Memory tools operate on agent's own memory blocks -- no system changes, no escalation.
READ_ONLY_TOOL_NAMES: set[str] = {
    "search_capabilities",
    "memory_insert",
    "memory_replace",
    "memory_rethink",
    "memory_search",
    "memory_delete",
}

# ---------------------------------------------------------------------------
# Detailed tool definitions (for 70B+ models) -- full descriptions with examples
# ---------------------------------------------------------------------------
_TOOLS_DETAILED: list[dict] = [
    # Phase 167: Unified `create` tool (replaces self_improve/create_agent/create_tool)
    {
        "type": "function",
        "function": {
            "name": "factory_create",
            "description": (
                "Create a new agent, tool, or skill using the Agent Factory. "
                "Specify what to create via the goal parameter. "
                "Optionally set artifact_type to 'agent', 'tool', or 'skill' to guide creation; "
                "if omitted, the factory infers the type from the goal. "
                "Use this when the user requests a new capability that doesn't exist yet, "
                "in any language. "
                "Examples:\n"
                '- User says "search the web for X" but no web agent exists -> '
                'factory_create(goal="Create a web search agent that can query search engines", artifact_type="agent")\n'
                '- User says "create a websearch agent" -> '
                'factory_create(goal="Create websearch agent", name="websearch", artifact_type="agent")\n'
                '- User says "I need a JSON validator tool" -> '
                'factory_create(goal="Create a JSON schema validation tool", artifact_type="tool")\n'
                "- User needs PDF analysis but no PDF agent exists -> "
                'factory_create(goal="Create a PDF analysis agent that can extract and summarize PDF content")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Description of the agent, tool, or skill to create and what it should do.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional suggested name for the new artifact.",
                    },
                    "artifact_type": {
                        "type": "string",
                        "enum": ["agent", "tool", "skill"],
                        "description": "Type of artifact to create. If omitted, the factory infers from the goal.",
                    },
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_config",
            "description": (
                "Modify orchestrator or agent configuration. "
                "Use when a configuration change would improve behavior, "
                "such as adjusting timeouts, enabling features, or tuning parameters.\n"
                "Examples:\n"
                '- "Increase the agent timeout" -> '
                'modify_config(config_key="agent_timeout", config_value="120", reason="User needs longer timeout for complex tasks")\n'
                '- "Enable debug mode" -> '
                'modify_config(config_key="debug_mode", config_value="true", reason="User wants detailed logging")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "config_key": {
                        "type": "string",
                        "description": "The configuration key to modify (e.g. 'agent_timeout', 'max_retries').",
                    },
                    "config_value": {
                        "type": "string",
                        "description": "The new value for the configuration key.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this configuration change is needed.",
                    },
                },
                "required": ["config_key", "config_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_mcp_server",
            "description": (
                "Connect a new MCP server and make its tools available to agents. "
                "Supports stdio (local command) and HTTP (remote URL) transports. "
                "For stdio transport, provide a command array. For HTTP, provide a url.\n"
                "Examples:\n"
                '- Add a PostgreSQL server: add_mcp_server(name="postgres", '
                'command=["npx", "-y", "@modelcontextprotocol/server-postgres"], '
                'env={"POSTGRES_URL": "postgresql://localhost/mydb"}, '
                'description="PostgreSQL database access")\n'
                '- Add a remote HTTP server: add_mcp_server(name="remote-tools", '
                'transport="http", url="https://tools.example.com/mcp", '
                'description="Remote tool server")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique name for the MCP server.",
                    },
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Command array to start the server (required for stdio transport).",
                    },
                    "transport": {
                        "type": "string",
                        "enum": ["stdio", "http"],
                        "description": "Transport type. Defaults to 'stdio'.",
                    },
                    "url": {
                        "type": "string",
                        "description": "Server URL (required for http transport).",
                    },
                    "env": {
                        "type": "object",
                        "description": "Environment variables for the server process.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of what this server provides.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_mcp_server",
            "description": (
                "Disconnect and remove an MCP server. Cleans up all registered tools, "
                "indexes, and embeddings for the server.\n"
                "Example:\n"
                '- remove_mcp_server(name="postgres") -- removes the PostgreSQL server '
                "and all its tools from the system."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the MCP server to remove.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_mcp_server",
            "description": (
                "Modify an existing MCP server's configuration. The server is restarted "
                "with the new settings and its tools are re-indexed.\n"
                "Example:\n"
                '- configure_mcp_server(name="postgres", updates={"env": {"POSTGRES_URL": '
                '"postgresql://localhost/newdb"}, "timeout": 60, "description": "Updated DB"}) '
                "-- updates the PostgreSQL server's connection string and timeout."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the MCP server to configure.",
                    },
                    "updates": {
                        "type": "object",
                        "description": (
                            "Configuration updates to apply. Can include: "
                            "env (object), command (array), enabled (bool), "
                            "timeout (number), description (string)."
                        ),
                    },
                },
                "required": ["name", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_capabilities",
            "description": (
                "Search all available capabilities across self-modification tools, "
                "MCP servers, and agents. Returns matching capabilities with descriptions. "
                "This is a read-only operation that does not require approval.\n"
                "Examples:\n"
                '- search_capabilities(query="database") -- find all database-related tools\n'
                '- search_capabilities(query="search", source="mcp") -- find MCP search tools\n'
                '- search_capabilities(query=".*", category="server_management") -- list all server management capabilities'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (regex pattern) to match against capability names, descriptions, and tags.",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["self_mod", "mcp", "agent"],
                        "description": "Optional filter by capability source.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional filter by category (e.g. 'server_management', 'tool_creation', 'config', 'search', 'agent_management').",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # --- Memory tools (Phase 115.3) ---
    {
        "type": "function",
        "function": {
            "name": "memory_insert",
            "description": (
                "Insert text into a memory block at a specific line. "
                "If the block doesn't exist, it is created with the given text. "
                "Memory blocks persist across conversation turns and are compiled "
                "into your system prompt.\n"
                "Examples:\n"
                '- memory_insert(label="user_preferences", new_str="Prefers concise responses")\n'
                '- memory_insert(label="task_context", new_str="Working on data migration project", insert_line=0)'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label (e.g. 'user_preferences', 'task_context').",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Text to insert.",
                    },
                    "insert_line": {
                        "type": "integer",
                        "description": "Line number to insert at. -1 = append (default).",
                        "default": -1,
                    },
                },
                "required": ["label", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_replace",
            "description": (
                "Find and replace text within a memory block. "
                "Use when you need to update specific information in your memory. "
                "The old_str must match exactly (first occurrence is replaced).\n"
                "Examples:\n"
                '- memory_replace(label="user_preferences", old_str="verbose responses", new_str="concise responses")\n'
                '- memory_replace(label="project_status", old_str="in progress", new_str="completed")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label to modify.",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Exact text to find and replace.",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["label", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_rethink",
            "description": (
                "Completely rewrite a memory block's contents. "
                "Use when the entire block needs to be reconsidered or restructured. "
                "Creates the block if it doesn't exist.\n"
                "Examples:\n"
                '- memory_rethink(label="user_preferences", new_memory="User prefers: concise output, code examples, no emojis")\n'
                '- memory_rethink(label="conversation_summary", new_memory="Discussed project timeline and resource allocation")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label to rewrite.",
                    },
                    "new_memory": {
                        "type": "string",
                        "description": "Complete new contents for the block.",
                    },
                },
                "required": ["label", "new_memory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": (
                "Search across all memory blocks for matching content. "
                "This is a read-only operation. Uses regex matching (case-insensitive).\n"
                "Examples:\n"
                '- memory_search(query="user preference") -- find preferences\n'
                '- memory_search(query="project.*timeline") -- regex search for project timeline'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (regex pattern, case-insensitive).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # Phase 167: memory_delete tool
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": (
                "Delete a memory block entirely. "
                "Use when a memory block is no longer relevant and should be removed. "
                "Returns confirmation of deletion or not_found if the block did not exist.\n"
                "Example:\n"
                '- memory_delete(label="old_task_context")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label to delete.",
                    },
                },
                "required": ["label"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Short tool definitions (for 7B models) -- compact descriptions, no examples
# ---------------------------------------------------------------------------
_TOOLS_SHORT: list[dict] = [
    # Phase 167: Unified `create` tool (replaces self_improve/create_agent/create_tool)
    {
        "type": "function",
        "function": {
            "name": "factory_create",
            "description": "Create a new agent, tool, or skill via the Agent Factory. Specify goal; optionally set artifact_type to 'agent', 'tool', or 'skill'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "What to create and what it should do.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Optional suggested name.",
                    },
                    "artifact_type": {
                        "type": "string",
                        "enum": ["agent", "tool", "skill"],
                        "description": "Type of artifact (agent/tool/skill). Factory infers if omitted.",
                    },
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_config",
            "description": "Modify orchestrator or agent configuration settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "config_key": {
                        "type": "string",
                        "description": "Configuration key to modify.",
                    },
                    "config_value": {
                        "type": "string",
                        "description": "New value.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this change is needed.",
                    },
                },
                "required": ["config_key", "config_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_mcp_server",
            "description": "Connect a new MCP server and make its tools available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique server name.",
                    },
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Command to start the server (stdio).",
                    },
                    "transport": {
                        "type": "string",
                        "enum": ["stdio", "http"],
                        "description": "Transport type.",
                    },
                    "url": {
                        "type": "string",
                        "description": "Server URL (http transport).",
                    },
                    "env": {
                        "type": "object",
                        "description": "Environment variables.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Server description.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_mcp_server",
            "description": "Disconnect and remove an MCP server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Server name to remove.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_mcp_server",
            "description": "Modify an existing MCP server's configuration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Server name to configure.",
                    },
                    "updates": {
                        "type": "object",
                        "description": "Configuration updates (env, command, enabled, timeout, description).",
                    },
                },
                "required": ["name", "updates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_capabilities",
            "description": "Search available capabilities and tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (regex).",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["self_mod", "mcp", "agent"],
                        "description": "Filter by source.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # --- Memory tools (Phase 115.3) ---
    {
        "type": "function",
        "function": {
            "name": "memory_insert",
            "description": "Insert text into a memory block. Creates the block if new.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label.",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Text to insert.",
                    },
                    "insert_line": {
                        "type": "integer",
                        "description": "Line number (-1 = append).",
                        "default": -1,
                    },
                },
                "required": ["label", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_replace",
            "description": "Find and replace text within a memory block.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label.",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Text to find.",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["label", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_rethink",
            "description": "Completely rewrite a memory block's contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label.",
                    },
                    "new_memory": {
                        "type": "string",
                        "description": "New block contents.",
                    },
                },
                "required": ["label", "new_memory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search across all memory blocks for matching content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (regex).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    # Phase 167: memory_delete tool
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete a memory block entirely. Returns ok if deleted, not_found if it didn't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Block label to delete.",
                    },
                },
                "required": ["label"],
            },
        },
    },
]

# Keep SELF_MOD_TOOLS as the default (detailed) for backward compat
SELF_MOD_TOOLS = _TOOLS_DETAILED

def get_self_mod_tools(variant: str = "detailed") -> list[dict]:
    """Get self-mod tool definitions appropriate for model capability.

    Args:
        variant: "short" for 7B models, "detailed" for 70B+ models.
            Phase 115.4: Renamed from model_tier for clarity.
            strategy.get_tool_description_variant() feeds directly here.

    Returns:
        List of tool definitions in OpenAI function-calling format.
    """
    if variant == "short":
        return _TOOLS_SHORT
    return _TOOLS_DETAILED

def is_self_mod_tool(tool_name: str | None) -> bool:
    """Check if a tool name is a self-modification tool.

    Args:
        tool_name: The tool name to check. None returns False.

    Returns:
        True if the tool is a self-modification tool.
    """
    if tool_name is None:
        return False
    # Phase 174.5: "create" renamed to "factory_create" to avoid model confusion
    # with code generation requests. Accept both for backward compat.
    if tool_name == "create":
        return True
    return tool_name in SELF_MOD_TOOL_NAMES

def is_read_only_tool(tool_name: str | None) -> bool:
    """Check if a self-mod tool is read-only (returns results without escalation).

    Args:
        tool_name: The tool name to check. None returns False.

    Returns:
        True if the tool is read-only.
    """
    if tool_name is None:
        return False
    return tool_name in READ_ONLY_TOOL_NAMES

async def execute_self_mod_tool(
    tool_name: str,
    arguments: dict,
    conversation_id: str,
    original_goal: str,
    context: dict | None = None,
) -> PendingEscalation | dict:
    """Execute a self-modification tool by creating an escalation action or returning results.

    Self-mod tools typically create PendingEscalation objects that go through
    the existing approval flow. Read-only tools (like search_capabilities)
    return results directly as a dict.

    Args:
        tool_name: Name of the self-mod tool to execute.
        arguments: Tool arguments from the LLM tool call.
        conversation_id: Current conversation ID.
        original_goal: The user's original request.
        context: Optional additional context.

    Returns:
        PendingEscalation with the proposed action, or dict with search results
        for read-only tools.

    Raises:
        ValueError: If tool_name is not a recognized self-mod tool.
    """
    # Default question uses action description; overridden by create
    question = None

    if tool_name in ("factory_create", "create"):  # "create" kept for backward compat
        # Phase 167: Unified create tool (replaces self_improve/create_agent/create_tool)
        goal = arguments.get("goal", original_goal)
        suggested_name = arguments.get("name")
        artifact_type = arguments.get("artifact_type")  # None = factory infers

        # Check factory availability (Q9 graceful degradation)
        try:
            from core.factory.models import FactoryConfig

            if not FactoryConfig().enabled:
                action = EscalationAction(
                    action_type=EscalationActionType.FACTORY_CREATE,
                    parameters={"task_description": goal, "artifact_type": artifact_type},
                    description="Agent Factory is disabled.",
                )
                return PendingEscalation(
                    conversation_id=conversation_id,
                    original_goal=original_goal,
                    original_context=context or {},
                    action=action,
                    question="The Agent Factory is currently disabled. Enable it in Settings to create agents, tools, and skills.",
                )
        except ImportError:
            pass  # Factory not installed, fall through to legacy path below

        # Delegate to factory via FACTORY_CREATE escalation
        action = EscalationAction(
            action_type=EscalationActionType.FACTORY_CREATE,
            parameters={
                "goal": goal,
                "suggested_name": suggested_name,
                "artifact_type": artifact_type,
                "trigger": "user",
                "conversation_id": conversation_id,
            },
            description=f"Create via factory: {goal[:200]}",
        )

        name_part = f" **{suggested_name}**" if suggested_name else ""
        question = f"**Agent Factory**{name_part} → {goal[:200]}\n\n✅ / ❌ ?"

    elif tool_name == "modify_config":
        config_key = arguments.get("config_key", "")
        config_value = arguments.get("config_value", "")
        reason = arguments.get("reason", "")
        action = EscalationAction(
            action_type=EscalationActionType.MODIFY_CONFIG,
            parameters={
                "config_key": config_key,
                "config_value": config_value,
                "reason": reason,
            },
            description=f"Modify config: {config_key} = {config_value}"
            + (f" ({reason})" if reason else ""),
        )

    elif tool_name == "add_mcp_server":
        server_name = arguments.get("name", "")
        action = EscalationAction(
            action_type=EscalationActionType.ADD_MCP_SERVER,
            parameters={
                "name": server_name,
                "command": arguments.get("command"),
                "transport": arguments.get("transport", "stdio"),
                "url": arguments.get("url"),
                "env": arguments.get("env"),
                "description": arguments.get("description", ""),
            },
            description=f"Add MCP server: {server_name}",
        )

    elif tool_name == "remove_mcp_server":
        server_name = arguments.get("name", "")
        action = EscalationAction(
            action_type=EscalationActionType.REMOVE_MCP_SERVER,
            parameters={"name": server_name},
            description=f"Remove MCP server: {server_name}",
        )

    elif tool_name == "configure_mcp_server":
        server_name = arguments.get("name", "")
        updates = arguments.get("updates", {})
        action = EscalationAction(
            action_type=EscalationActionType.CONFIGURE_MCP_SERVER,
            parameters={
                "name": server_name,
                "updates": updates,
            },
            description=f"Configure MCP server: {server_name}",
        )

    elif tool_name == "search_capabilities":
        # Read-only tool -- return results directly, no escalation
        from core.orchestrator.capability_registry import get_capability_registry

        registry = get_capability_registry()
        registry.refresh_from_sources()

        query = arguments.get("query", ".*")
        source_filter = arguments.get("source")
        category_filter = arguments.get("category")

        results = registry.search(
            query=query,
            source_filter=source_filter,
            category_filter=category_filter,
        )

        logger.info(
            "[SELF-MOD] search_capabilities query='%s' returned %d results",
            query,
            len(results),
        )

        return {
            "type": "search_result",
            "results": [
                {
                    "name": r.name,
                    "source": r.source,
                    "category": r.category,
                    "description": r.description_short,
                    "server": r.server,
                    "tags": r.tags,
                }
                for r in results
            ],
        }

    # --- Memory tools (Phase 115.3) ---
    # All memory tools are read-only (modify agent memory, not system state).
    # They return results directly without creating PendingEscalation objects.

    elif tool_name == "memory_insert":
        from core.orchestrator.memory_tools import execute_memory_insert

        return execute_memory_insert(
            agent_id=conversation_id,
            label=arguments.get("label", "default"),
            new_str=arguments.get("new_str", ""),
            insert_line=arguments.get("insert_line", -1),
        )

    elif tool_name == "memory_replace":
        from core.orchestrator.memory_tools import execute_memory_replace

        return execute_memory_replace(
            agent_id=conversation_id,
            label=arguments.get("label", "default"),
            old_str=arguments.get("old_str", ""),
            new_str=arguments.get("new_str", ""),
        )

    elif tool_name == "memory_rethink":
        from core.orchestrator.memory_tools import execute_memory_rethink

        return execute_memory_rethink(
            agent_id=conversation_id,
            label=arguments.get("label", "default"),
            new_memory=arguments.get("new_memory", ""),
        )

    elif tool_name == "memory_search":
        from core.orchestrator.memory_tools import execute_memory_search

        return execute_memory_search(
            agent_id=conversation_id,
            query=arguments.get("query", ""),
        )

    elif tool_name == "memory_delete":
        # Phase 167: memory_delete tool
        from core.orchestrator.memory_tools import execute_memory_delete

        return execute_memory_delete(
            agent_id=conversation_id,
            label=arguments.get("label", ""),
        )

    else:
        raise ValueError(f"Unknown self-mod tool: {tool_name}")

    logger.info(
        "[SELF-MOD] Tool '%s' creating escalation: %s",
        tool_name,
        action.description,
    )

    return PendingEscalation(
        conversation_id=conversation_id,
        original_goal=original_goal,
        original_context=context or {},
        action=action,
        question=question if question is not None else action.description,
    )
