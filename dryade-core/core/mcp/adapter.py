"""MCP Agent Adapter.

Wraps MCP servers as UniversalAgent instances, enabling them to be discovered
and used like any other agent in the system.

Features:
- MCP servers appear as agents in the agent registry
- get_card() returns server info with tools as capabilities
- execute() routes natural language tasks to appropriate MCP tools
- get_tools() returns MCP tools in OpenAI function format
- Server-specific descriptions for developer productivity servers

Usage:
    from core.mcp import MCPAgentAdapter, create_mcp_agent
    from core.mcp import MCPServerConfig, get_registry

    # Create adapter for a registered server
    config = MCPServerConfig(name="memory", command=["npx", "-y", "@modelcontextprotocol/server-memory"])
    registry = get_registry()
    registry.register(config)

    adapter = MCPAgentAdapter(server_name="memory", registry=registry)

    # Or use the factory function
    adapter = create_mcp_agent("memory")

    # Use like any UniversalAgent
    card = adapter.get_card()
    result = await adapter.execute("Store a note about meeting tomorrow")
    tools = adapter.get_tools()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.exceptions import MCPTimeoutError, MCPTransportError
from core.mcp.protocol import MCPTool
from core.mcp.registry import MCPRegistry, get_registry
from core.orchestrator.config import get_orchestration_config

logger = logging.getLogger(__name__)

# Server-specific descriptions for developer productivity servers
SERVER_DESCRIPTIONS: dict[str, str] = {
    "github": "GitHub integration for repositories, issues, pull requests, and code search",
    "context7": "Library documentation lookup for up-to-date API references",
    "playwright": "Browser automation for testing, screenshots, and web interactions",
    "linear": "Issue tracking and project management with Linear",
    "memory": "Knowledge graph operations for persistent agent memory",
    "filesystem": "Secure file operations with directory access control",
    "git": "Git repository operations (status, diff, commit, branch)",
    "dbhub": "Database operations for Postgres, MySQL, SQLite, SQL Server, MariaDB",
    "grafana": "Observability integration (dashboards, alerts, queries)",
    "pdf_reader": "PDF extraction (text, tables, images, structure)",
    "document_ops": "Office format operations (DOCX, XLSX, PPTX, CSV, Markdown)",
    "image-gen": "Image generation via Stable Diffusion, ComfyUI, or DALL-E compatible API",
}

# Module-level verb-to-tool-pattern map for Tier 3 action verb matching
ACTION_VERB_MAP: dict[str, list[str]] = {
    "search": ["search", "find", "glob"],
    "find": ["search", "find", "glob"],
    "list": ["list", "directory", "ls"],
    "read": ["read", "get", "cat"],
    "write": ["write", "create", "save"],
    "open": ["open", "load"],
    "query": ["query", "execute", "run"],
    "close": ["close", "end", "stop", "terminate", "session"],
    "discover": ["discover", "explore", "inspect", "schema"],
    "create": ["create", "make", "new", "add", "generate", "build"],
    "delete": ["delete", "remove", "drop", "destroy"],
    "update": ["update", "modify", "change", "edit", "patch"],
    "trace": ["trace", "track", "follow", "traceability"],
    "export": ["export", "download", "dump", "extract"],
    "save": ["save", "persist", "store", "commit"],
    "rollback": ["rollback", "undo", "revert", "restore"],
    "coverage": ["coverage", "analyze", "check", "audit", "verify"],
    "info": ["info", "information", "details", "describe", "about"],
    "start": ["start", "begin", "init", "initialize", "launch"],
    "status": ["status", "state", "health", "progress"],
    "sync": ["sync", "synchronize", "replicate", "mirror"],
    "schema": ["schema", "structure", "model", "metadata"],
    "get": ["get", "fetch", "retrieve", "obtain", "show"],
    "session": ["session", "connect", "connection"],
}

class MCPAgentAdapter(UniversalAgent):
    """Adapter that wraps an MCP server as a UniversalAgent.

    Enables MCP servers to be discovered and used seamlessly alongside
    CrewAI, LangChain, and other framework agents.

    Attributes:
        server_name: Name of the MCP server to wrap.
        registry: MCPRegistry instance managing the server.
        description: Optional description override for the agent card.
        version: Version string for the agent card.
    """

    def __init__(
        self,
        server_name: str,
        registry: MCPRegistry | None = None,
        description: str | None = None,
        version: str = "1.0.0",
    ) -> None:
        """Initialize the MCP agent adapter.

        Args:
            server_name: Name of the registered MCP server.
            registry: MCPRegistry instance. Uses global registry if not provided.
            description: Optional description override.
            version: Version string for agent card.

        Raises:
            MCPRegistryError: If server is not registered in the registry.
        """
        self._server_name = server_name
        self._registry = registry or get_registry()
        self._description = description
        self._version = version

        # Validate server is registered and get transport type
        config = self._registry.get_config(server_name)
        self._transport_type = config.transport.value

    @property
    def server_name(self) -> str:
        """Return the MCP server name."""
        return self._server_name

    def get_card(self) -> AgentCard:
        """Return agent's capability card.

        The card includes:
        - Server name prefixed with "mcp-" for namespacing
        - Server-specific description or fallback
        - Framework set to MCP
        - Tools exposed as capabilities
        - Transport type and tool count in metadata

        Returns:
            AgentCard describing this MCP server as an agent.
        """
        config = self._registry.get_config(self._server_name)

        # Get description - from override, server-specific, or generate default
        description = self._description
        if description is None:
            description = SERVER_DESCRIPTIONS.get(
                self._server_name, f"MCP server: {self._server_name}"
            )

        # Build capabilities from tools (lazy-starts server if needed)
        capabilities = self._build_capabilities()

        return AgentCard(
            name=f"mcp-{self._server_name}",
            description=description,
            version=self._version,
            capabilities=capabilities,
            framework=AgentFramework.MCP,
            endpoint=None,  # MCP servers are local, not remote
            metadata={
                "mcp_server": self._server_name,
                "transport": self._transport_type,
                "tool_count": len(capabilities),
                "command": config.command,
            },
        )

    def _build_capabilities(self) -> list[AgentCapability]:
        """Build AgentCapability list from MCP tools.

        Returns:
            List of AgentCapability describing available tools.
        """
        try:
            tools = self._registry.list_tools(self._server_name)
            return [self._tool_to_capability(tool) for tool in tools]
        except Exception as e:
            logger.warning(
                f"Failed to list tools for '{self._server_name}': {e}. "
                "Returning empty capabilities."
            )
            return []

    def _tool_to_capability(self, tool: MCPTool) -> AgentCapability:
        """Convert an MCPTool to an AgentCapability.

        Args:
            tool: MCP tool definition.

        Returns:
            AgentCapability representation of the tool.
        """
        return AgentCapability(
            name=tool.name,
            description=tool.description,
            input_schema={
                "type": tool.inputSchema.type,
                "properties": tool.inputSchema.properties,
                "required": tool.inputSchema.required,
            },
            output_schema={},  # MCP tools don't define output schema
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute a task using MCP tools with graceful fallback.

        Routes natural language tasks to appropriate MCP tools. The context
        can include:
        - tool: Explicit tool name to call
        - arguments: Arguments for the tool
        - If no tool specified, attempts to match task to available tools

        Args:
            task: Natural language task description or tool name.
            context: Execution context with optional tool and arguments.

        Returns:
            AgentResult with status and result. Never raises exceptions.
        """
        try:
            context = context or {}

            # Check if explicit tool is specified
            tool_name = context.get("tool")
            arguments = context.get("arguments", {})

            if tool_name:
                # Direct tool call
                return await self._call_tool(tool_name, arguments)

            # Try to find matching tool by task description
            tool_name = self._match_tool_to_task(task)
            if tool_name:
                return await self._call_tool(tool_name, arguments)

            # No matching tool found
            available_tools = [t.name for t in self._registry.list_tools(self._server_name)]
            return AgentResult(
                result=None,
                status="error",
                error=f"No tool found matching task: '{task}'. Available tools: {available_tools}",
                metadata={
                    "error_type": "no_match",
                    "server": self._server_name,
                    "available_tools": available_tools,
                },
            )

        except MCPTimeoutError as e:
            logger.warning(f"MCP timeout for {self._server_name}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error="MCP server timed out. Try a simpler request.",
                metadata={"error_type": "mcp_timeout", "server": self._server_name},
            )
        except MCPTransportError as e:
            logger.warning(f"MCP transport error for {self._server_name}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error="MCP server communication failed. Check server status.",
                metadata={"error_type": "mcp_transport", "server": self._server_name},
            )
        except Exception as e:
            logger.exception(f"MCP execution failed for {self._server_name}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"MCP tool execution failed: {type(e).__name__}",
                metadata={"error_type": "mcp_error", "server": self._server_name},
            )

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> AgentResult:
        """Call an MCP tool and return the result.

        Args:
            tool_name: Name of the tool to call.
            arguments: Arguments for the tool.

        Returns:
            AgentResult with tool output.
        """
        config = get_orchestration_config()
        mcp_timeout = config.mcp_tool_timeout

        try:
            # Sanitize arguments: remove null values that should be arrays
            # LLMs often generate {"excludePatterns": null} but MCP expects []
            sanitized_args = {k: v for k, v in arguments.items() if v is not None}

            try:
                result = await asyncio.wait_for(
                    self._registry.acall_tool(self._server_name, tool_name, sanitized_args),
                    timeout=mcp_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"MCP tool call timed out: {self._server_name}/{tool_name} after {mcp_timeout}s"
                )
                return AgentResult(
                    result=None,
                    status="error",
                    error=f"MCP tool '{tool_name}' timed out after {mcp_timeout}s",
                    metadata={
                        "error_type": "mcp_tool_timeout",
                        "server": self._server_name,
                        "tool": tool_name,
                        "timeout_seconds": mcp_timeout,
                    },
                )

            # Extract text content from result
            content_parts = []
            for item in result.content:
                if item.text:
                    content_parts.append(item.text)
                elif item.data:
                    content_parts.append(f"[Binary data: {item.mimeType}]")

            output = "\n".join(content_parts) if content_parts else None

            if result.isError:
                return AgentResult(
                    result=output,
                    status="error",
                    error=output or "Tool execution failed",
                    metadata={
                        "error_type": "tool_error",
                        "server": self._server_name,
                        "tool": tool_name,
                        "is_error": True,
                    },
                )

            return AgentResult(
                result=output,
                status="ok",
                error=None,
                metadata={
                    "server": self._server_name,
                    "tool": tool_name,
                    "content_count": len(result.content),
                },
            )

        except Exception as e:
            logger.exception(f"Tool call failed: {self._server_name}/{tool_name}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Tool call failed: {type(e).__name__}",
                metadata={
                    "error_type": "tool_call_error",
                    "server": self._server_name,
                    "tool": tool_name,
                },
            )

    def _match_tool_to_task(self, task: str) -> str | None:
        """Match task description to tool name with multi-tier strategy.

        Matching tiers:
        1. Exact tool name match
        2. Tool name contained in task
        3. Action verb matching (search, list, read, etc.)

        Args:
            task: Task description.

        Returns:
            Tool name if match found, None otherwise.
        """
        task_lower = task.lower()

        try:
            tools = self._registry.list_tools(self._server_name)
        except Exception:
            return None

        # Tier 1: Exact match
        for tool in tools:
            if tool.name.lower() == task_lower:
                return tool.name

        # Tier 2: Tool name in task
        for tool in tools:
            if tool.name.lower() in task_lower:
                return tool.name

        # Tier 2.5: Tool name parts in task (split on underscore)
        task_words = set(task_lower.split())
        best_part_match = None
        best_part_score = 0
        for tool in tools:
            parts = [p for p in tool.name.lower().split("_") if len(p) >= 3]
            if not parts:
                continue
            matches = sum(1 for p in parts if p in task_words)
            score = matches / len(parts)
            if score > best_part_score and score >= 0.5:  # At least half the parts match
                best_part_score = score
                best_part_match = tool.name
        if best_part_match:
            logger.debug(
                f"[_match_tool_to_task] Part match: '{best_part_match}' (score={best_part_score:.2f})"
            )
            return best_part_match

        # Tier 3: Action verb matching
        for verb, tool_patterns in ACTION_VERB_MAP.items():
            if verb in task_lower:
                for tool in tools:
                    tool_name_lower = tool.name.lower()
                    tool_desc_lower = (tool.description or "").lower()
                    for pattern in tool_patterns:
                        if pattern in tool_name_lower or pattern in tool_desc_lower:
                            logger.debug(
                                f"[_match_tool_to_task] Verb match: '{verb}' -> '{tool.name}'"
                            )
                            return tool.name

        return None

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format.

        Format follows OpenAI's function calling schema for compatibility
        with LLM tool calling.

        Returns:
            List of tool definitions in OpenAI function format.
        """
        try:
            tools = self._registry.list_tools(self._server_name)
            return [self._tool_to_openai_format(tool) for tool in tools]
        except Exception as e:
            logger.warning(
                f"Failed to list tools for '{self._server_name}': {e}. Returning empty tools list."
            )
            return []

    def _tool_to_openai_format(self, tool: MCPTool) -> dict[str, Any]:
        """Convert an MCPTool to OpenAI function format.

        Args:
            tool: MCP tool definition.

        Returns:
            Tool in OpenAI function calling format.
        """
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": tool.inputSchema.type,
                    "properties": tool.inputSchema.properties,
                    "required": tool.inputSchema.required,
                },
            },
        }

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming output.

        MCP servers do not support streaming tool responses.

        Returns:
            False - MCP tools don't support streaming.
        """
        return False

    def capabilities(self) -> AgentCapabilities:
        """Return MCP-specific capabilities."""
        config = (
            self._registry.get_config(self._server_name) if hasattr(self, "_server_name") else None
        )
        caps = config.capabilities if config and hasattr(config, "capabilities") else None
        return AgentCapabilities(
            supports_streaming=False,
            supports_resources=caps.resources is not None if caps else False,
            supports_prompts=caps.prompts is not None if caps else False,
            max_retries=3,
            timeout_seconds=60,
            framework_specific={
                "mcp_server": self._server_name if hasattr(self, "_server_name") else None
            },
        )

    def get_memory(self) -> dict | None:
        """MCP servers don't have memory in the traditional sense."""
        return None

    async def list_resources(self) -> list[dict]:
        """List available resources from MCP server."""
        if not hasattr(self, "_registry") or not hasattr(self, "_server_name"):
            return []
        try:
            resources = await self._registry.list_resources(self._server_name)
            return [
                {"uri": r.uri, "name": r.name, "description": getattr(r, "description", "")}
                for r in resources
            ]
        except Exception:
            return []

    async def list_prompts(self) -> list[dict]:
        """List available prompt templates."""
        if not hasattr(self, "_registry") or not hasattr(self, "_server_name"):
            return []
        try:
            prompts = await self._registry.list_prompts(self._server_name)
            return [{"name": p.name, "description": getattr(p, "description", "")} for p in prompts]
        except Exception:
            return []

def create_mcp_agent(
    server_name: str,
    registry: MCPRegistry | None = None,
    description: str | None = None,
    version: str = "1.0.0",
) -> MCPAgentAdapter:
    """Factory function to create an MCPAgentAdapter.

    Convenience function for creating MCP agent adapters.

    Args:
        server_name: Name of the registered MCP server.
        registry: MCPRegistry instance. Uses global registry if not provided.
        description: Optional description override.
        version: Version string for agent card.

    Returns:
        MCPAgentAdapter wrapping the specified MCP server.

    Raises:
        MCPRegistryError: If server is not registered in the registry.

    Example:
        >>> from core.mcp import create_mcp_agent, MCPServerConfig, get_registry
        >>> registry = get_registry()
        >>> config = MCPServerConfig(name="memory", command=["npx", "-y", "@modelcontextprotocol/server-memory"])
        >>> registry.register(config)
        >>> agent = create_mcp_agent("memory")
        >>> card = agent.get_card()
        >>> print(card.name)
        memory
    """
    return MCPAgentAdapter(
        server_name=server_name,
        registry=registry,
        description=description,
        version=version,
    )
