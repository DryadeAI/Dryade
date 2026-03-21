"""infrastructure_health_checker Agent - LangGraph Implementation.

Infrastructure monitoring agent that performs continuous health checks across cloud resources, containers, and network endpoints, predicts capacity issues before they impact users, and executes automated remediation runbooks.

Factory-generated LangGraph agent with MCP tool integration.

Usage:
    from agents.infrastructure_health_checker import InfrastructureHealthCheckerAgent, create_graph

    agent = create_graph()
    result = await agent.execute("Your task here")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from core.adapters.langchain_adapter import LangChainAgentAdapter
from core.adapters.protocol import (
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
# MCP Tool Wrappers
# ============================================================================

_get_pod_status_wrapper = MCPToolWrapper(
    "kubernetes-mcp-server", "get_pod_status", "Check pod health"
)
_query_metrics_wrapper = MCPToolWrapper(
    "prometheus-mcp-server", "query_metrics", "Query infrastructure metrics"
)
_get_alarms_wrapper = MCPToolWrapper("cloudwatch-mcp-server", "get_alarms", "Get active alarms")
_create_incident_wrapper = MCPToolWrapper(
    "pagerduty-mcp-server", "create_incident", "Create PagerDuty incident"
)

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
        from langchain_core.tools import tool as langchain_tool
    except ImportError:
        logger.warning("LangChain not installed - tools will not be available")
        return []

    tools: list[Any] = []

    @langchain_tool
    def get_pod_status(**kwargs: Any) -> str:
        """Check pod health"""
        try:
            return _get_pod_status_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"get_pod_status error: {e}")
            return f"[Error] get_pod_status failed: {e}"

    tools.append(get_pod_status)

    @langchain_tool
    def query_metrics(**kwargs: Any) -> str:
        """Query infrastructure metrics"""
        try:
            return _query_metrics_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"query_metrics error: {e}")
            return f"[Error] query_metrics failed: {e}"

    tools.append(query_metrics)

    @langchain_tool
    def get_alarms(**kwargs: Any) -> str:
        """Get active alarms"""
        try:
            return _get_alarms_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"get_alarms error: {e}")
            return f"[Error] get_alarms failed: {e}"

    tools.append(get_alarms)

    @langchain_tool
    def create_incident(**kwargs: Any) -> str:
        """Create PagerDuty incident"""
        try:
            return _create_incident_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"create_incident error: {e}")
            return f"[Error] create_incident failed: {e}"

    tools.append(create_incident)
    return tools

# ============================================================================
# InfrastructureHealthChecker Agent
# ============================================================================

class InfrastructureHealthCheckerAgent:
    """LangGraph-based infrastructure_health_checker agent with graceful fallback.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the infrastructure_health_checker agent."""
        self._config = config or _load_config()
        self.name = self._config.get("name", "infrastructure_health_checker")
        self.description = self._config.get(
            "description",
            "Infrastructure monitoring agent that performs continuous health checks across cloud resources, containers, and network endpoints, predicts capacity issues before they impact users, and executes automated remediation runbooks.",
        )
        self._adapter: LangChainAgentAdapter | None = None
        self._tools: list[Any] = []
        self._init_error: str | None = None
        self._init_agent()

    def _init_agent(self) -> None:
        """Initialize the LangGraph agent and adapter."""
        self._tools = _create_langchain_tools()

        if not self._tools:
            self._init_error = (
                "LangChain not installed. Install with: pip install langchain langchain-core"
            )
            return

        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError:
            self._init_error = "LangGraph not installed. Install with: pip install langgraph"
            logger.warning("LangGraph not installed - agent will run in degraded mode")
            return

        try:
            from core.providers.langchain_adapter import get_langchain_llm

            llm = get_langchain_llm()

            agent = create_react_agent(
                llm,
                self._tools,
            )

            self._adapter = LangChainAgentAdapter(
                agent, name=self.name, description=self.description
            )
        except Exception as e:
            self._init_error = f"LangGraph agent initialization failed: {e}"
            logger.warning(f"LangGraph agent init failed - running in degraded mode: {e}")

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute a task with graceful fallback.

        Args:
            task: Natural language task description.
            context: Optional execution context.

        Returns:
            AgentResult with status and result.
        """
        if not self._adapter:
            error_msg = self._init_error or "LangGraph not available"
            return AgentResult(
                result=None,
                status="error",
                error=f"{error_msg}. Required MCP servers: kubernetes-mcp-server, prometheus-mcp-server, cloudwatch-mcp-server, pagerduty-mcp-server",
                metadata={
                    "recoverable": True,
                    "required_servers": [
                        "kubernetes-mcp-server",
                        "prometheus-mcp-server",
                        "cloudwatch-mcp-server",
                        "pagerduty-mcp-server",
                    ],
                    "agent": self.name,
                },
            )

        try:
            return await self._adapter.execute(task, context or {})
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Execution failed: {e}",
                metadata={
                    "recoverable": True,
                    "required_servers": [
                        "kubernetes-mcp-server",
                        "prometheus-mcp-server",
                        "cloudwatch-mcp-server",
                        "pagerduty-mcp-server",
                    ],
                    "agent": self.name,
                },
            )

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return True

def create_graph(config: dict[str, Any] | None = None) -> InfrastructureHealthCheckerAgent:
    """Factory function to create the infrastructure_health_checker agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured InfrastructureHealthCheckerAgent instance.
    """
    return InfrastructureHealthCheckerAgent(config=config)

async def run(task: str, **kwargs) -> str:
    """Entry point declared in dryade.json run_function."""
    agent = create_graph()
    result = await agent.execute(task, context=kwargs)
    if result.status == "ok":
        return str(result.result) if result.result is not None else ""
    raise RuntimeError(result.error or "Execution failed")

__all__ = [
    "InfrastructureHealthCheckerAgent",
    "create_graph",
    "run",
]
