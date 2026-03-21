"""data_pipeline_monitor Agent - LangGraph Implementation.

Real-time data pipeline monitoring agent that watches ETL jobs, detects anomalies in data quality and throughput, and triggers corrective actions when pipelines degrade or fail.

Factory-generated LangGraph agent with MCP tool integration.

Usage:
    from agents.data_pipeline_monitor import DataPipelineMonitorAgent, create_graph

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

_query_metrics_wrapper = MCPToolWrapper(
    "prometheus-mcp-server", "query_metrics", "Query pipeline metrics"
)
_check_data_quality_wrapper = MCPToolWrapper(
    "postgres-mcp-server", "check_data_quality", "Run data quality checks"
)
_execute_remediation_wrapper = MCPToolWrapper(
    "postgres-mcp-server", "execute_remediation", "Execute remediation actions"
)
_send_alert_wrapper = MCPToolWrapper("slack-mcp-server", "send_alert", "Send alert notification")

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
    def query_metrics(**kwargs: Any) -> str:
        """Query pipeline metrics"""
        try:
            return _query_metrics_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"query_metrics error: {e}")
            return f"[Error] query_metrics failed: {e}"

    tools.append(query_metrics)

    @langchain_tool
    def check_data_quality(**kwargs: Any) -> str:
        """Run data quality checks"""
        try:
            return _check_data_quality_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"check_data_quality error: {e}")
            return f"[Error] check_data_quality failed: {e}"

    tools.append(check_data_quality)

    @langchain_tool
    def execute_remediation(**kwargs: Any) -> str:
        """Execute remediation actions"""
        try:
            return _execute_remediation_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"execute_remediation error: {e}")
            return f"[Error] execute_remediation failed: {e}"

    tools.append(execute_remediation)

    @langchain_tool
    def send_alert(**kwargs: Any) -> str:
        """Send alert notification"""
        try:
            return _send_alert_wrapper.call(**kwargs)
        except Exception as e:
            logger.warning(f"send_alert error: {e}")
            return f"[Error] send_alert failed: {e}"

    tools.append(send_alert)
    return tools

# ============================================================================
# DataPipelineMonitor Agent
# ============================================================================

class DataPipelineMonitorAgent:
    """LangGraph-based data_pipeline_monitor agent with graceful fallback.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the data_pipeline_monitor agent."""
        self._config = config or _load_config()
        self.name = self._config.get("name", "data_pipeline_monitor")
        self.description = self._config.get(
            "description",
            "Real-time data pipeline monitoring agent that watches ETL jobs, detects anomalies in data quality and throughput, and triggers corrective actions when pipelines degrade or fail.",
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
                error=f"{error_msg}. Required MCP servers: postgres-mcp-server, prometheus-mcp-server, slack-mcp-server",
                metadata={
                    "recoverable": True,
                    "required_servers": [
                        "postgres-mcp-server",
                        "prometheus-mcp-server",
                        "slack-mcp-server",
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
                        "postgres-mcp-server",
                        "prometheus-mcp-server",
                        "slack-mcp-server",
                    ],
                    "agent": self.name,
                },
            )

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return True

def create_graph(config: dict[str, Any] | None = None) -> DataPipelineMonitorAgent:
    """Factory function to create the data_pipeline_monitor agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured DataPipelineMonitorAgent instance.
    """
    return DataPipelineMonitorAgent(config=config)

async def run(task: str, **kwargs) -> str:
    """Entry point declared in dryade.json run_function."""
    agent = create_graph()
    result = await agent.execute(task, context=kwargs)
    if result.status == "ok":
        return str(result.result) if result.result is not None else ""
    raise RuntimeError(result.error or "Execution failed")

__all__ = [
    "DataPipelineMonitorAgent",
    "create_graph",
    "run",
]
