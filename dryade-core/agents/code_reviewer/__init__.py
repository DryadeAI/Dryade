"""Code Reviewer Agent - CrewAI Implementation.

Demonstrates CrewAI multi-tool agent pattern with GitHub, Context7, and Git
MCP tool integration. Implements graceful fallback for resilience when MCP
servers are unavailable.

This agent specializes in code review tasks:
- Analyzing pull requests via GitHub API
- Checking code against library best practices via Context7
- Reviewing local git diffs

Usage:
    from agents.code_reviewer import CodeReviewerAgent, create_code_reviewer_agent

    # Factory function (recommended)
    agent = create_code_reviewer_agent()
    result = await agent.execute("Review PR #123 in owner/repo")

    # Check capabilities
    card = agent.get_card()
    print(card.framework)  # AgentFramework.CREWAI
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

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
# Pydantic Schemas for CrewAI Tool Arguments
# ============================================================================

class GetPullRequestArgs(BaseModel):
    """Arguments for get_pull_request tool."""

    owner: str = Field(..., description="Repository owner (e.g., 'anthropic')")
    repo: str = Field(..., description="Repository name (e.g., 'anthropic-cookbook')")
    pr_number: int = Field(..., description="Pull request number")

class GetLibraryDocsArgs(BaseModel):
    """Arguments for get_library_docs tool."""

    library_name: str = Field(..., description="Name of the library (e.g., 'react', 'fastapi')")
    topic: str | None = Field(None, description="Specific topic to look up (optional)")

class GitDiffArgs(BaseModel):
    """Arguments for git_diff tool."""

    path: str | None = Field(None, description="Optional path to diff (file or directory)")
    repo_path: str = Field(".", description="Path to the git repository")

# ============================================================================
# CrewAI Tool Implementations
# ============================================================================

# CrewAI BaseTool is imported dynamically to avoid import errors when crewai is not installed
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

    class GetPullRequestTool(BaseTool):
        """Get details of a GitHub pull request including diff and comments."""

        name: str = "get_pull_request"
        description: str = "Get details of a GitHub pull request including diff and comments"
        args_schema: type[BaseModel] = GetPullRequestArgs

        _wrapper: MCPToolWrapper | None = None

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            object.__setattr__(
                self,
                "_wrapper",
                MCPToolWrapper("github", "get_pull_request", self.description),
            )

        def _run(
            self,
            owner: str,
            repo: str,
            pr_number: int,
        ) -> str:
            """Execute the tool to get pull request details."""
            try:
                wrapper = object.__getattribute__(self, "_wrapper")
                return wrapper.call(owner=owner, repo=repo, pull_number=pr_number)
            except Exception as e:
                logger.warning(f"GetPullRequestTool error: {e}")
                return f"[Error] Could not fetch PR #{pr_number}: {e}. Ensure GitHub MCP server is configured with valid GITHUB_TOKEN."

    class GetLibraryDocsTool(BaseTool):
        """Get documentation for a library to understand best practices."""

        name: str = "get_library_docs"
        description: str = "Get documentation for a library to understand best practices"
        args_schema: type[BaseModel] = GetLibraryDocsArgs

        _wrapper: MCPToolWrapper | None = None

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            object.__setattr__(
                self,
                "_wrapper",
                MCPToolWrapper("context7", "get-library-docs", self.description),
            )

        def _run(
            self,
            library_name: str,
            topic: str | None = None,
        ) -> str:
            """Execute the tool to get library documentation."""
            try:
                wrapper = object.__getattribute__(self, "_wrapper")
                kwargs: dict[str, Any] = {"library_name": library_name}
                if topic:
                    kwargs["topic"] = topic
                return wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"GetLibraryDocsTool error: {e}")
                return f"[Error] Could not fetch docs for {library_name}: {e}. Ensure Context7 MCP server is configured."

    class GitDiffTool(BaseTool):
        """Get git diff for specific files or entire repo."""

        name: str = "git_diff"
        description: str = "Get git diff for specific files or entire repo"
        args_schema: type[BaseModel] = GitDiffArgs

        _wrapper: MCPToolWrapper | None = None

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            object.__setattr__(
                self,
                "_wrapper",
                MCPToolWrapper("git", "git_diff", self.description),
            )

        def _run(
            self,
            path: str | None = None,
            repo_path: str = ".",
        ) -> str:
            """Execute the tool to get git diff."""
            try:
                wrapper = object.__getattribute__(self, "_wrapper")
                kwargs: dict[str, Any] = {"repo_path": repo_path}
                if path:
                    kwargs["target"] = path
                return wrapper.call(**kwargs)
            except Exception as e:
                logger.warning(f"GitDiffTool error: {e}")
                return f"[Error] Could not get git diff: {e}. Ensure Git MCP server is configured."

    return [GetPullRequestTool(), GetLibraryDocsTool(), GitDiffTool()]

# ============================================================================
# Code Reviewer Agent
# ============================================================================

class CodeReviewerAgent:
    """CrewAI-based Code Reviewer agent with graceful fallback.

    Wraps a CrewAI Agent configured for code review tasks using GitHub,
    Context7, and Git MCP tools. Provides graceful degradation when
    MCP servers are unavailable.

    Attributes:
        name: Agent name for identification.
        description: Human-readable description.
        adapter: CrewAIAgentAdapter wrapping the CrewAI agent.

    Example:
        >>> agent = CodeReviewerAgent()
        >>> card = agent.get_card()
        >>> print(card.framework)
        AgentFramework.CREWAI
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the Code Reviewer agent.

        Args:
            config: Optional configuration override. Loaded from config.yaml if not provided.
        """
        self._config = config or _load_config()
        self.name = self._config.get("name", "code_reviewer")
        self.description = self._config.get(
            "description",
            "Analyzes code changes and provides review feedback",
        )
        self._adapter: CrewAIAgentAdapter | None = None
        self._tools: list[Any] = []
        self._init_agent()

    def _init_agent(self) -> None:
        """Initialize the CrewAI agent and adapter."""
        self._init_error: str | None = None

        try:
            from crewai import LLM, Agent
        except ImportError:
            self._init_error = "CrewAI not installed. Install with: pip install crewai"
            logger.warning("CrewAI not installed - agent will run in degraded mode")
            return

        # Create MCP tools
        self._tools = _create_crewai_tools()

        try:
            # Create placeholder LLM to avoid env var lookup at startup
            # Real LLM is injected by CrewAIAgentAdapter._configure_llm_from_context() at execution time
            placeholder_llm = LLM(model="openai/gpt-4o", api_key="placeholder-replaced-at-runtime")

            # Create CrewAI agent
            crewai_agent = Agent(
                role="Senior Code Reviewer",
                goal="Provide thorough, constructive code reviews focusing on correctness, maintainability, and best practices",
                backstory=(
                    "Expert developer with 15+ years experience reviewing enterprise code. "
                    "Known for catching subtle bugs, security issues, and suggesting clean, "
                    "maintainable solutions. Uses library documentation to ensure best practices."
                ),
                tools=self._tools,
                llm=placeholder_llm,
                verbose=False,
                allow_delegation=False,
            )

            # Wrap with adapter
            self._adapter = CrewAIAgentAdapter(crewai_agent, name=self.name)
        except Exception as e:
            # Handle LLM configuration errors (e.g., missing API key)
            self._init_error = f"CrewAI agent initialization failed: {e}"
            logger.warning(f"CrewAI agent init failed - running in degraded mode: {e}")

    def get_card(self):
        """Return agent's capability card.

        Returns:
            AgentCard with framework=CREWAI and code review capabilities.
        """
        if self._adapter:
            card = self._adapter.get_card()
            # Override description from config
            card.description = self.description
            return card

        # Fallback card when CrewAI not installed
        from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework

        return AgentCard(
            name=self.name,
            description=self.description,
            version="1.0",
            framework=AgentFramework.CREWAI,
            capabilities=[
                AgentCapability(
                    name="get_pull_request",
                    description="Get details of a GitHub pull request",
                    input_schema={"owner": "str", "repo": "str", "pr_number": "int"},
                    output_schema={},
                ),
                AgentCapability(
                    name="get_library_docs",
                    description="Get documentation for a library",
                    input_schema={"library_name": "str", "topic": "str|None"},
                    output_schema={},
                ),
                AgentCapability(
                    name="git_diff",
                    description="Get git diff for files or repo",
                    input_schema={"path": "str|None", "repo_path": "str"},
                    output_schema={},
                ),
            ],
            metadata={
                "required_servers": ["github", "git", "context7"],
                "degraded_mode": True,
            },
        )

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Execute a code review task with graceful fallback.

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

        Attempts to execute the task via CrewAI adapter. If execution fails,
        returns a helpful error message indicating required MCP servers.

        Args:
            task: Task description.
            context: Execution context.

        Returns:
            AgentResult with result or helpful error.
        """
        if not self._adapter:
            error_msg = self._init_error or "CrewAI not available"
            return AgentResult(
                result=None,
                status="error",
                error=(f"{error_msg}. Required MCP servers: github, git, context7"),
                metadata={
                    "recoverable": True,
                    "required_servers": ["github", "git", "context7"],
                    "agent": self.name,
                },
            )

        try:
            result = await self._adapter.execute(task, context)
            return result
        except Exception as e:
            logger.error(f"Code review execution failed: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=(
                    f"Code review failed: {e}. "
                    "Ensure GitHub, Git, and Context7 MCP servers are configured."
                ),
                metadata={
                    "recoverable": True,
                    "required_servers": ["github", "git", "context7"],
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
                    "name": "get_pull_request",
                    "description": "Get details of a GitHub pull request",
                    "parameters": GetPullRequestArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_library_docs",
                    "description": "Get documentation for a library",
                    "parameters": GetLibraryDocsArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "git_diff",
                    "description": "Get git diff for files or repo",
                    "parameters": GitDiffArgs.model_json_schema(),
                },
            },
        ]

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return False

def create_code_reviewer_agent(
    config: dict[str, Any] | None = None,
) -> CodeReviewerAgent:
    """Factory function to create a Code Reviewer agent.

    Args:
        config: Optional configuration override.

    Returns:
        Configured CodeReviewerAgent instance.

    Example:
        >>> agent = create_code_reviewer_agent()
        >>> result = await agent.execute("Review PR #42 in owner/repo")
    """
    return CodeReviewerAgent(config=config)

__all__ = [
    "CodeReviewerAgent",
    "create_code_reviewer_agent",
]
