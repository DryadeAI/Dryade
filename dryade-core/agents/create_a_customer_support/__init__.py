"""create_a_customer_support Agent - CrewAI Implementation.

Customer support triage agent that classifies incoming tickets, answers common questions using FAQ knowledge, and escalates complex or sensitive issues to the appropriate specialized team.

Factory-generated CrewAI agent with MCP tool integration.

Usage:
    from agents.create_a_customer_support import CreateACustomerSupportAgent, create_crew

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

_search_tickets_wrapper = MCPToolWrapper(
    "zendesk-mcp-server", "search_tickets", "Search support tickets by keyword or status"
)
_update_ticket_wrapper = MCPToolWrapper(
    "zendesk-mcp-server", "update_ticket", "Update ticket status priority or assignee"
)
_search_knowledge_base_wrapper = MCPToolWrapper(
    "knowledge-base-mcp-server", "search_knowledge_base", "Search FAQ and knowledge base articles"
)
_send_message_wrapper = MCPToolWrapper(
    "slack-mcp-server", "send_message", "Send notification or escalation to Slack channel"
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

    class SearchTicketsTool(BaseTool):
        """Search support tickets by keyword or status"""

        name: str = "search_tickets"
        description: str = "Search support tickets by keyword or status"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _search_tickets_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"search_tickets error: {e}")
                return f"[Error] search_tickets failed: {e}"

    tools.append(SearchTicketsTool())

    class UpdateTicketTool(BaseTool):
        """Update ticket status priority or assignee"""

        name: str = "update_ticket"
        description: str = "Update ticket status priority or assignee"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _update_ticket_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"update_ticket error: {e}")
                return f"[Error] update_ticket failed: {e}"

    tools.append(UpdateTicketTool())

    class SearchKnowledgeBaseTool(BaseTool):
        """Search FAQ and knowledge base articles"""

        name: str = "search_knowledge_base"
        description: str = "Search FAQ and knowledge base articles"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _search_knowledge_base_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"search_knowledge_base error: {e}")
                return f"[Error] search_knowledge_base failed: {e}"

    tools.append(SearchKnowledgeBaseTool())

    class SendMessageTool(BaseTool):
        """Send notification or escalation to Slack channel"""

        name: str = "send_message"
        description: str = "Send notification or escalation to Slack channel"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _send_message_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"send_message error: {e}")
                return f"[Error] send_message failed: {e}"

    tools.append(SendMessageTool())
    return tools

# ============================================================================
# CreateACustomerSupport Agent
# ============================================================================

class CreateACustomerSupportAgent:
    """CrewAI-based create_a_customer_support agent with graceful fallback.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the create_a_customer_support agent."""
        self._config = config or _load_config()
        self.name = self._config.get("name", "create_a_customer_support")
        self.description = self._config.get(
            "description",
            "Customer support triage agent that classifies incoming tickets, answers common questions using FAQ knowledge, and escalates complex or sensitive issues to the appropriate specialized team.",
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
                role="Customer Support Triage Specialist",
                goal="Create a customer support agent that handles ticket triage, responds to common questions from our FAQ, and escalates complex issues to the right team",
                backstory="You are a seasoned customer support professional with over 10 years of experience in frontline support operations. You have an encyclopedic knowledge of the company's FAQ and product documentation, and you've developed a keen instinct for quickly categorizing issues by severity, topic, and complexity. You pride yourself on resolving common inquiries swiftly and accurately while knowing exactly when an issue requires escalation and which specialized team (billing, engineering, account management, or security) should handle it. You maintain a warm, empathetic, and professional tone in every interaction, ensuring customers feel heard and valued even when their issue needs to be passed along.",
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
                error=f"{error_msg}. Required MCP servers: zendesk-mcp-server, freshdesk-mcp-server, slack-mcp-server, knowledge-base-mcp-server",
                metadata={
                    "recoverable": True,
                    "required_servers": [
                        "zendesk-mcp-server",
                        "freshdesk-mcp-server",
                        "slack-mcp-server",
                        "knowledge-base-mcp-server",
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
                        "zendesk-mcp-server",
                        "freshdesk-mcp-server",
                        "slack-mcp-server",
                        "knowledge-base-mcp-server",
                    ],
                    "agent": self.name,
                },
            )

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return False

def create_crew(config: dict[str, Any] | None = None) -> CreateACustomerSupportAgent:
    """Factory function to create the create_a_customer_support agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured CreateACustomerSupportAgent instance.
    """
    return CreateACustomerSupportAgent(config=config)

async def run(task: str, **kwargs) -> str:
    """Entry point declared in dryade.json run_function."""
    agent = create_crew()
    result = await agent.execute(task, context=kwargs)
    if result.status == "ok":
        return str(result.result) if result.result is not None else ""
    raise RuntimeError(result.error or "Execution failed")

__all__ = [
    "CreateACustomerSupportAgent",
    "create_crew",
    "run",
]
