"""Database Analyst Agent - LangChain/LangGraph Implementation.

Demonstrates LangChain tool binding pattern with DBHub and Grafana MCP tool
integration. Implements graceful fallback and streaming support for multi-step
analysis tasks.

This agent specializes in database analysis tasks:
- Executing SQL queries via DBHub
- Listing and describing database tables
- Querying Prometheus metrics via Grafana

Usage:
    from agents.database_analyst import DatabaseAnalystAgent, create_database_analyst_agent

    # Factory function (recommended)
    agent = create_database_analyst_agent()
    result = await agent.execute("List all tables in the database")

    # Check streaming support
    print(agent.supports_streaming())  # True

    # Check capabilities
    card = agent.get_card()
    print(card.framework)  # AgentFramework.LANGCHAIN
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import yaml

from core.adapters.langchain_adapter import LangChainAgentAdapter
from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
)
from core.mcp.tool_wrapper import MCPToolWrapper

logger = logging.getLogger(__name__)

# Load agent configuration
def _load_config() -> dict[str, Any]:
    """Load agent configuration from YAML file."""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    return {}

# ============================================================================
# SQL Safety Validation
# ============================================================================

# Patterns for potentially destructive SQL operations
_DESTRUCTIVE_SQL_PATTERNS = [
    r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)",  # DELETE without WHERE
    r"\bUPDATE\b(?!.*\bWHERE\b)",  # UPDATE without WHERE
    r"\bALTER\s+TABLE\b.*\bDROP\b",
    r"\bINSERT\s+INTO\b.*\bSELECT\b",  # Bulk insert
]

def _is_safe_query(query: str) -> tuple[bool, str | None]:
    """Validate SQL query for safety in read-only mode.

    Args:
        query: SQL query string to validate.

    Returns:
        Tuple of (is_safe, reason_if_not_safe).
    """
    query_upper = query.upper().strip()

    for pattern in _DESTRUCTIVE_SQL_PATTERNS:
        if re.search(pattern, query_upper, re.IGNORECASE):
            return False, f"Potentially destructive operation detected: matches pattern {pattern}"

    return True, None

# ============================================================================
# LangChain Tool Definitions
# ============================================================================

def _create_langchain_tools() -> list[Any]:
    """Create @tool decorated functions for LangChain.

    Returns:
        List of LangChain tool functions.

    Note:
        Returns empty list if langchain_core is not installed.
    """
    try:
        from langchain_core.tools import tool
    except ImportError:
        logger.warning("LangChain not installed - tools will not be available")
        return []

    # MCP tool wrappers
    _query_wrapper = MCPToolWrapper("dbhub", "query", "Execute SQL query via DBHub")
    _list_tables_wrapper = MCPToolWrapper("dbhub", "list_tables", "List database tables")
    _describe_table_wrapper = MCPToolWrapper("dbhub", "describe_table", "Describe table schema")
    _prometheus_wrapper = MCPToolWrapper("grafana", "query_prometheus", "Query Prometheus metrics")

    @tool
    def query_database(query: str, database: str = "default") -> str:
        """Execute SQL query against a database via DBHub.

        Args:
            query: SQL query to execute.
            database: Database identifier (default: "default").

        Returns:
            Query results as string, or error message.
        """
        # Validate query safety
        is_safe, reason = _is_safe_query(query)
        if not is_safe:
            return f"[Error] Query rejected in read-only mode: {reason}. Use safe SELECT queries."

        try:
            return _query_wrapper.call(query=query, database=database)
        except Exception as e:
            logger.warning(f"query_database error: {e}")
            return f"[Error] Database query failed: {e}. Ensure DBHub MCP server is configured."

    @tool
    def list_tables(database: str = "default") -> str:
        """List all tables in a database.

        Args:
            database: Database identifier (default: "default").

        Returns:
            List of table names as string, or error message.
        """
        try:
            return _list_tables_wrapper.call(database=database)
        except Exception as e:
            logger.warning(f"list_tables error: {e}")
            return f"[Error] Could not list tables: {e}. Ensure DBHub MCP server is configured."

    @tool
    def describe_table(table_name: str, database: str = "default") -> str:
        """Get schema information for a database table.

        Args:
            table_name: Name of the table to describe.
            database: Database identifier (default: "default").

        Returns:
            Table schema as string, or error message.
        """
        try:
            return _describe_table_wrapper.call(table_name=table_name, database=database)
        except Exception as e:
            logger.warning(f"describe_table error: {e}")
            return f"[Error] Could not describe table {table_name}: {e}. Ensure DBHub MCP server is configured."

    @tool
    def query_prometheus(query: str, time_range: str = "1h") -> str:
        """Execute Prometheus query via Grafana for metrics analysis.

        Args:
            query: PromQL query string.
            time_range: Time range for query (default: "1h").

        Returns:
            Prometheus query results as string, or error message.
        """
        try:
            return _prometheus_wrapper.call(query=query, time_range=time_range)
        except Exception as e:
            logger.warning(f"query_prometheus error: {e}")
            return f"[Error] Prometheus query failed: {e}. Ensure Grafana MCP server is configured."

    return [query_database, list_tables, describe_table, query_prometheus]

# ============================================================================
# Database Analyst Agent
# ============================================================================

class DatabaseAnalystAgent:
    """LangChain-based Database Analyst agent with streaming support.

    Wraps a LangChain react agent configured for database analysis tasks using
    DBHub and Grafana MCP tools. Provides graceful degradation when MCP servers
    or LLM are unavailable, and supports streaming for multi-step analysis.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
        adapter: LangChainAgentAdapter wrapping the LangChain agent.

    Example:
        >>> agent = DatabaseAnalystAgent()
        >>> card = agent.get_card()
        >>> print(card.framework)
        AgentFramework.LANGCHAIN
        >>> print(agent.supports_streaming())
        True
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the Database Analyst agent.

        Args:
            config: Optional configuration override. Loaded from config.yaml if not provided.
        """
        self._config = config or _load_config()
        self.name = self._config.get("name", "database_analyst")
        self.description = self._config.get(
            "description",
            "Query and analyze databases with natural language",
        )
        self._adapter: LangChainAgentAdapter | None = None
        self._tools: list[Any] = []
        self._init_error: str | None = None
        self._init_agent()

    def _init_agent(self) -> None:
        """Initialize the LangChain agent and adapter.

        Uses lazy creation pattern: starts in tool-wrapper mode at startup,
        upgrades to full LangGraph agent at execution time when user's LLM config is available.
        """
        # Create LangChain tools
        self._tools = _create_langchain_tools()

        if not self._tools:
            self._init_error = (
                "LangChain not installed. Install with: pip install langchain langchain-core"
            )
            return

        # Start with tool wrapper mode - LangGraph agent created lazily at execution time
        # This avoids requiring OPENAI_API_KEY at startup
        self._adapter = self._create_tool_wrapper_adapter()
        self._langgraph_adapter: LangChainAgentAdapter | None = None

    def _create_langgraph_agent(self) -> LangChainAgentAdapter:
        """Create a LangGraph react agent with LLM.

        Uses the user's configured LLM from Settings page (via contextvars),
        falling back to environment variables if not configured.

        Returns:
            LangChainAgentAdapter wrapping LangGraph agent.

        Raises:
            Exception: If no LLM is configured (neither user config nor env vars).
        """
        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError as e:
            raise ImportError("langgraph required for full agent mode") from e

        # Get LangChain-compatible LLM from user config or environment
        from core.providers.langchain_adapter import get_langchain_llm

        llm = get_langchain_llm()

        # Create react agent with tools
        system_prompt = (
            "You are a database analyst expert. Help users query databases and analyze data. "
            "Always validate queries for safety before execution. Use the available tools to "
            "explore schema, run queries, and analyze metrics."
        )

        agent = create_react_agent(
            llm,
            self._tools,
            prompt=system_prompt,
        )

        return LangChainAgentAdapter(agent, name=self.name, description=self.description)

    def _create_tool_wrapper_adapter(self) -> LangChainAgentAdapter:
        """Create a simple adapter that exposes tools without LLM.

        Returns:
            LangChainAgentAdapter in tool-wrapper mode.
        """

        # Create a simple wrapper object that has the tools
        class ToolWrapperAgent:
            """Simple agent that exposes tools without LLM orchestration."""

            def __init__(self, tools: list[Any], name: str) -> None:
                self.tools = tools
                self.name = name

            async def ainvoke(self, input_dict: dict[str, Any]) -> dict[str, Any]:
                """Execute by parsing task and calling appropriate tool."""
                task = input_dict.get("input", "")
                task_lower = task.lower()

                # Simple keyword-based routing
                try:
                    if "list" in task_lower and "table" in task_lower:
                        result = self.tools[1].invoke({})  # list_tables
                    elif "describe" in task_lower or "schema" in task_lower:
                        # Try to extract table name
                        for tool in self.tools:
                            if tool.name == "describe_table":
                                result = tool.invoke({"table_name": "unknown"})
                                break
                        else:
                            result = "Please specify a table name"
                    elif "prometheus" in task_lower or "metric" in task_lower:
                        result = self.tools[3].invoke({"query": task})  # query_prometheus
                    elif "query" in task_lower or "select" in task_lower:
                        result = self.tools[0].invoke({"query": task})  # query_database
                    else:
                        result = (
                            f"I can help with: listing tables, describing schemas, "
                            f"running SQL queries, and querying Prometheus metrics. "
                            f"Available tools: {[t.name for t in self.tools]}"
                        )
                    return {"output": result}
                except Exception as e:
                    return {"output": f"Error: {e}"}

            async def astream(self, input_dict: dict[str, Any]):
                """Stream execution with progress updates."""
                task = input_dict.get("input", "")

                yield {"step": "analyzing", "message": f"Analyzing task: {task}"}

                try:
                    result = await self.ainvoke(input_dict)
                    yield {"step": "complete", "result": result.get("output")}
                except Exception as e:
                    yield {"step": "error", "error": str(e)}

        wrapper = ToolWrapperAgent(self._tools, self.name)
        return LangChainAgentAdapter(wrapper, name=self.name, description=self.description)

    def get_card(self) -> AgentCard:
        """Return agent's capability card.

        Returns:
            AgentCard with framework=LANGCHAIN and database analysis capabilities.
        """
        capabilities = [
            AgentCapability(
                name="query_database",
                description="Execute SQL queries against databases",
                input_schema={"query": "str", "database": "str"},
                output_schema={"result": "str"},
            ),
            AgentCapability(
                name="list_tables",
                description="List all tables in a database",
                input_schema={"database": "str"},
                output_schema={"tables": "list[str]"},
            ),
            AgentCapability(
                name="describe_table",
                description="Get schema information for a table",
                input_schema={"table_name": "str", "database": "str"},
                output_schema={"schema": "dict"},
            ),
            AgentCapability(
                name="query_prometheus",
                description="Query Prometheus metrics via Grafana",
                input_schema={"query": "str", "time_range": "str"},
                output_schema={"metrics": "list"},
            ),
        ]

        metadata: dict[str, Any] = {
            "required_servers": ["dbhub", "grafana"],
            "streaming": True,
        }

        if self._init_error:
            metadata["degraded_mode"] = True
            metadata["init_error"] = self._init_error

        return AgentCard(
            name=self.name,
            description=self.description,
            version="1.0",
            framework=AgentFramework.LANGCHAIN,
            capabilities=capabilities,
            metadata=metadata,
        )

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute a database analysis task with graceful fallback.

        Args:
            task: Natural language task description.
            context: Optional execution context.

        Returns:
            AgentResult with status and result.
        """
        return await self.execute_with_fallback(task, context or {})

    async def execute_with_fallback(
        self,
        task: str,
        context: dict[str, Any],
    ) -> AgentResult:
        """Execute task with graceful fallback on failure.

        Lazily upgrades to LangGraph agent if user's LLM config is available.
        Falls back to tool-wrapper mode if no LLM configured.

        Args:
            task: Task description.
            context: Execution context.

        Returns:
            AgentResult with result or helpful error.
        """
        if not self._adapter:
            error_msg = self._init_error or "LangChain not available"
            return AgentResult(
                result=None,
                status="error",
                error=(f"{error_msg}. Required MCP servers: dbhub, grafana"),
                metadata={
                    "recoverable": True,
                    "required_servers": ["dbhub", "grafana"],
                    "agent": self.name,
                },
            )

        # Try to upgrade to LangGraph agent if not already done
        if self._langgraph_adapter is None:
            try:
                self._langgraph_adapter = self._create_langgraph_agent()
                logger.info("Upgraded to LangGraph agent with user's LLM config")
            except Exception as e:
                # LLM not available - continue with tool wrapper mode
                logger.debug(f"LangGraph agent not available, using tool wrapper: {e}")

        # Use LangGraph adapter if available, otherwise fall back to tool wrapper
        adapter = self._langgraph_adapter or self._adapter

        try:
            result = await adapter.execute(task, context)
            return result
        except Exception as e:
            logger.error(f"Database analysis execution failed: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=(
                    f"Database analysis failed: {e}. "
                    "Ensure DBHub and Grafana MCP servers are configured."
                ),
                metadata={
                    "recoverable": True,
                    "required_servers": ["dbhub", "grafana"],
                    "agent": self.name,
                },
            )

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format.

        Returns:
            List of tool definitions.
        """
        if self._adapter:
            return self._adapter.get_tools()

        # Fallback tool definitions
        return [
            {
                "type": "function",
                "function": {
                    "name": "query_database",
                    "description": "Execute SQL query against a database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "SQL query to execute"},
                            "database": {
                                "type": "string",
                                "description": "Database identifier",
                                "default": "default",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tables",
                    "description": "List all tables in a database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database": {
                                "type": "string",
                                "description": "Database identifier",
                                "default": "default",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "describe_table",
                    "description": "Get schema information for a table",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "table_name": {"type": "string", "description": "Name of the table"},
                            "database": {
                                "type": "string",
                                "description": "Database identifier",
                                "default": "default",
                            },
                        },
                        "required": ["table_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_prometheus",
                    "description": "Execute Prometheus query via Grafana",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "PromQL query string"},
                            "time_range": {
                                "type": "string",
                                "description": "Time range",
                                "default": "1h",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming.

        Returns:
            True - Database Analyst always supports streaming.
        """
        return True

    async def execute_stream(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute task with streaming progress updates.

        Args:
            task: Task description.
            context: Execution context.

        Yields:
            Progress update dictionaries with step and message/result.
        """
        yield {"step": "start", "message": f"Starting analysis: {task}"}

        if not self._adapter:
            error_msg = self._init_error or "LangChain not available"
            yield {
                "step": "error",
                "error": f"{error_msg}. Required MCP servers: dbhub, grafana",
            }
            return

        try:
            if self._adapter.supports_streaming():
                async for chunk in self._adapter.execute_stream(task, context):
                    yield {"step": "progress", "data": chunk}

            # Final result
            result = await self._adapter.execute(task, context)
            yield {"step": "complete", "result": result.result, "status": result.status}
        except Exception as e:
            logger.error(f"Streaming execution failed: {e}")
            yield {"step": "error", "error": str(e)}

def create_database_analyst_agent(
    config: dict[str, Any] | None = None,
) -> DatabaseAnalystAgent:
    """Factory function to create a Database Analyst agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured DatabaseAnalystAgent instance.

    Example:
        >>> agent = create_database_analyst_agent()
        >>> result = await agent.execute("List all tables")
    """
    return DatabaseAnalystAgent(config=config)

__all__ = [
    "DatabaseAnalystAgent",
    "create_database_analyst_agent",
]
