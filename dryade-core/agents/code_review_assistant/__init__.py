"""code_review_assistant Agent - CrewAI Implementation.

Automated code review agent that analyzes pull requests for bugs, security vulnerabilities, performance issues, and style violations. Provides actionable inline feedback with severity levels and suggested fixes.

Factory-generated CrewAI agent with MCP tool integration.

Usage:
    from agents.code_review_assistant import CodeReviewAssistantAgent, create_crew

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

_get_pull_request_diff_wrapper = MCPToolWrapper(
    "github-mcp-server", "get_pull_request_diff", "Analyze pull request diffs for code changes"
)
_search_code_wrapper = MCPToolWrapper(
    "github-mcp-server", "search_code", "Search code repositories for patterns and vulnerabilities"
)
_read_file_wrapper = MCPToolWrapper(
    "filesystem-mcp-server", "read_file", "Read source files for full context around changes"
)
_create_review_comment_wrapper = MCPToolWrapper(
    "github-mcp-server", "create_review_comment", "Post inline review comments on pull requests"
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

    class GetPullRequestDiffTool(BaseTool):
        """Analyze pull request diffs for code changes"""

        name: str = "get_pull_request_diff"
        description: str = "Analyze pull request diffs for code changes"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _get_pull_request_diff_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"get_pull_request_diff error: {e}")
                return f"[Error] get_pull_request_diff failed: {e}"

    tools.append(GetPullRequestDiffTool())

    class SearchCodeTool(BaseTool):
        """Search code repositories for patterns and vulnerabilities"""

        name: str = "search_code"
        description: str = "Search code repositories for patterns and vulnerabilities"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _search_code_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"search_code error: {e}")
                return f"[Error] search_code failed: {e}"

    tools.append(SearchCodeTool())

    class ReadFileTool(BaseTool):
        """Read source files for full context around changes"""

        name: str = "read_file"
        description: str = "Read source files for full context around changes"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _read_file_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"read_file error: {e}")
                return f"[Error] read_file failed: {e}"

    tools.append(ReadFileTool())

    class CreateReviewCommentTool(BaseTool):
        """Post inline review comments on pull requests"""

        name: str = "create_review_comment"
        description: str = "Post inline review comments on pull requests"

        def _run(self, **kwargs: Any) -> str:
            """Execute the tool."""
            try:
                return _create_review_comment_wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"create_review_comment error: {e}")
                return f"[Error] create_review_comment failed: {e}"

    tools.append(CreateReviewCommentTool())
    return tools

# ============================================================================
# CodeReviewAssistant Agent
# ============================================================================

class CodeReviewAssistantAgent:
    """CrewAI-based code_review_assistant agent with graceful fallback.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the code_review_assistant agent."""
        self._config = config or _load_config()
        self.name = self._config.get("name", "code_review_assistant")
        self.description = self._config.get(
            "description",
            "Automated code review agent that analyzes pull requests for bugs, security vulnerabilities, performance issues, and style violations. Provides actionable inline feedback with severity levels and suggested fixes.",
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
                role="Senior Code Review Engineer",
                goal="Analyze code changes for bugs, security issues, performance problems, and style violations, providing precise inline feedback that helps developers ship safer and cleaner code",
                backstory="You are a meticulous software engineer with 15 years of experience across backend systems, distributed architectures, and security-sensitive applications. You have reviewed thousands of pull requests and developed an instinct for spotting subtle bugs that slip past automated linters. You focus on actionable feedback — every comment includes a clear explanation of the risk and a concrete fix suggestion. You know the difference between a nitpick and a blocking issue, and you always prioritize security and correctness over style.",
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
                error=f"{error_msg}. Required MCP servers: github-mcp-server, filesystem-mcp-server",
                metadata={
                    "recoverable": True,
                    "required_servers": ["github-mcp-server", "filesystem-mcp-server"],
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
                    "required_servers": ["github-mcp-server", "filesystem-mcp-server"],
                    "agent": self.name,
                },
            )

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return False

def create_crew(config: dict[str, Any] | None = None) -> CodeReviewAssistantAgent:
    """Factory function to create the code_review_assistant agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured CodeReviewAssistantAgent instance.
    """
    return CodeReviewAssistantAgent(config=config)

async def run(task: str, **kwargs) -> str:
    """Entry point declared in dryade.json run_function."""
    agent = create_crew()
    result = await agent.execute(task, context=kwargs)
    if result.status == "ok":
        return str(result.result) if result.result is not None else ""
    raise RuntimeError(result.error or "Execution failed")

__all__ = [
    "CodeReviewAssistantAgent",
    "create_crew",
    "run",
]
