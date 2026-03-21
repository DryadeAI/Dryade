"""security_incident_responder Agent - CrewAI Implementation.

Automated security incident response agent that triages alerts from SIEM and EDR systems, correlates indicators of compromise, contains threats, and generates forensic timelines for post-incident review.

Factory-generated CrewAI agent with MCP tool integration.

Usage:
    from agents.security_incident_responder import SecurityIncidentResponderAgent, create_crew

    agent = create_crew()
    result = await agent.execute("Your task here")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from core.adapters.crewai_adapter import CrewAIAgentAdapter
from core.adapters.protocol import AgentResult
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

_search_logs_wrapper = MCPToolWrapper(
    "splunk-mcp-server", "search_logs", "Search SIEM logs for indicators of compromise"
)
_get_detections_wrapper = MCPToolWrapper(
    "crowdstrike-mcp-server", "get_detections", "Get endpoint detections and threat intelligence"
)
_create_issue_wrapper = MCPToolWrapper(
    "jira-mcp-server", "create_issue", "Create incident tracking ticket in Jira"
)
_send_alert_wrapper = MCPToolWrapper(
    "slack-mcp-server", "send_alert", "Send security alert to incident response channel"
)

# ============================================================================
# CrewAI Tool Implementations
# ============================================================================

def _create_crewai_tools() -> list[Any]:
    """Create CrewAI BaseTool subclasses for MCP tools.

    Returns:
        List of CrewAI tool instances.

    Note:
        Returns empty list if crewai is not installed.
    """
    try:
        from crewai.tools import BaseTool
    except ImportError:
        logger.warning("CrewAI not installed - tools will not be available")
        return []

    tools: list[Any] = []

    class SearchLogsTool(BaseTool):
        """Search SIEM logs for indicators of compromise"""

        name: str = "search_logs"
        description: str = "Search SIEM logs for indicators of compromise"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _search_logs_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"search_logs error: {e}")
                return f"[Error] search_logs failed: {e}"

    tools.append(SearchLogsTool())

    class GetDetectionsTool(BaseTool):
        """Get endpoint detections and threat intelligence"""

        name: str = "get_detections"
        description: str = "Get endpoint detections and threat intelligence"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _get_detections_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"get_detections error: {e}")
                return f"[Error] get_detections failed: {e}"

    tools.append(GetDetectionsTool())

    class CreateIssueTool(BaseTool):
        """Create incident tracking ticket in Jira"""

        name: str = "create_issue"
        description: str = "Create incident tracking ticket in Jira"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _create_issue_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"create_issue error: {e}")
                return f"[Error] create_issue failed: {e}"

    tools.append(CreateIssueTool())

    class SendAlertTool(BaseTool):
        """Send security alert to incident response channel"""

        name: str = "send_alert"
        description: str = "Send security alert to incident response channel"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _send_alert_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"send_alert error: {e}")
                return f"[Error] send_alert failed: {e}"

    tools.append(SendAlertTool())
    return tools

# ============================================================================
# SecurityIncidentResponder Agent
# ============================================================================

class SecurityIncidentResponderAgent:
    """CrewAI-based security_incident_responder agent with graceful fallback.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the security_incident_responder agent."""
        self._config = config or _load_config()
        self.name = self._config.get("name", "security_incident_responder")
        self.description = self._config.get(
            "description",
            "Automated security incident response agent that triages alerts from SIEM and EDR systems, correlates indicators of compromise, contains threats, and generates forensic timelines for post-incident review.",
        )
        self._adapter: CrewAIAgentAdapter | None = None
        self._tools: list[Any] = []
        self._init_error: str | None = None
        self._init_agent()

    def _init_agent(self) -> None:
        """Initialize the CrewAI agent and adapter."""
        try:
            from crewai import LLM, Agent
        except ImportError:
            self._init_error = "CrewAI not installed. Install with: pip install crewai"
            logger.warning("CrewAI not installed - agent will run in degraded mode")
            return

        self._tools = _create_crewai_tools()

        try:
            placeholder_llm = LLM(
                model="openai/gpt-4o",
                api_key="placeholder-replaced-at-runtime",
            )

            crewai_agent = Agent(
                role="Security Incident Response Analyst",
                goal="Triage security alerts rapidly, correlate indicators of compromise across telemetry sources, contain active threats, and produce forensic timelines that enable full remediation",
                backstory="You are a seasoned SOC analyst and incident commander with experience handling everything from opportunistic phishing campaigns to advanced persistent threats targeting critical infrastructure. You think in kill chains and MITRE ATT&CK techniques. Your first instinct on any alert is to scope the blast radius — how far did the attacker get, what did they touch, and what is still at risk. You are methodical in containment, always preferring reversible actions that preserve forensic evidence. You write incident reports that both executives and engineers can act on.",
                tools=self._tools,
                llm=placeholder_llm,
                verbose=False,
                allow_delegation=False,
                max_iter=25,
            )

            self._adapter = CrewAIAgentAdapter(crewai_agent, name=self.name)
        except Exception as e:
            self._init_error = f"CrewAI agent initialization failed: {e}"
            logger.warning(f"CrewAI agent init failed - running in degraded mode: {e}")

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
            error_msg = self._init_error or "CrewAI not available"
            return AgentResult(
                result=None,
                status="error",
                error=f"{error_msg}. Required MCP servers: splunk-mcp-server, crowdstrike-mcp-server, jira-mcp-server, slack-mcp-server",
                metadata={
                    "recoverable": True,
                    "required_servers": [
                        "splunk-mcp-server",
                        "crowdstrike-mcp-server",
                        "jira-mcp-server",
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
                        "splunk-mcp-server",
                        "crowdstrike-mcp-server",
                        "jira-mcp-server",
                        "slack-mcp-server",
                    ],
                    "agent": self.name,
                },
            )

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return False

def create_crew(config: dict[str, Any] | None = None) -> SecurityIncidentResponderAgent:
    """Factory function to create the security_incident_responder agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured SecurityIncidentResponderAgent instance.
    """
    return SecurityIncidentResponderAgent(config=config)

async def run(task: str, **kwargs) -> str:
    """Entry point declared in dryade.json run_function."""
    agent = create_crew()
    result = await agent.execute(task, context=kwargs)
    if result.status == "ok":
        return str(result.result) if result.result is not None else ""
    raise RuntimeError(result.error or "Execution failed")

__all__ = [
    "SecurityIncidentResponderAgent",
    "create_crew",
    "run",
]
