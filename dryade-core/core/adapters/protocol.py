"""Universal Agent Protocol.

All framework adapters implement this interface.
Target: ~100 LOC
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from core.skills.models import Skill

# Import from unified exception hierarchy
from core.exceptions import AgentExecutionError

# Re-export for backward compatibility
__all__ = [
    "AgentFramework",
    "AgentCapability",
    "AgentCapabilities",
    "AgentCard",
    "AgentResult",
    "UniversalAgent",
    "AgentExecutionError",
]

class AgentFramework(str, Enum):
    """Supported agent frameworks."""

    CREWAI = "crewai"
    LANGCHAIN = "langchain"
    ADK = "adk"
    A2A = "a2a"
    MCP = "mcp"
    CUSTOM = "custom"

class AgentCapability(BaseModel):
    """Describes what an agent can do."""

    name: str
    description: str
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}

class AgentCapabilities(BaseModel):
    """Runtime capabilities of an agent for orchestrator negotiation.

    Used by DryadeOrchestrator to validate agent supports required features
    before calling (per user decision: capability negotiation pattern).
    """

    supports_streaming: bool = False
    supports_memory: bool = False
    supports_knowledge: bool = False
    supports_delegation: bool = False
    supports_callbacks: bool = False
    supports_resources: bool = False  # MCP resources
    supports_prompts: bool = False  # MCP prompts
    supports_sessions: bool = False  # ADK sessions
    supports_artifacts: bool = False  # ADK artifacts
    supports_async_tasks: bool = False  # A2A long-running
    supports_push: bool = False  # A2A push notifications
    max_retries: int = 3  # Default retry limit (user decision: 3 retries)
    timeout_seconds: int = 60  # Default timeout
    is_critical: bool = False  # For criticality-based failure handling
    framework_specific: dict[str, Any] = {}  # Additional framework features

class AgentCard(BaseModel):
    """Agent discovery card (inspired by A2A protocol).

    See: https://github.com/a2aproject/A2A
    """

    name: str
    description: str
    version: str
    capabilities: list[AgentCapability] = []
    framework: AgentFramework
    endpoint: str | None = None  # For A2A remote agents
    metadata: dict[str, Any] = {}
    skills: list[str] = []  # Names of injected skills

class AgentResult(BaseModel):
    """Standard result format for all agents."""

    result: Any
    status: str  # "ok", "error", "partial"
    error: str | None = None
    metadata: dict[str, Any] = {}

    @property
    def output(self) -> Any:
        """Alias for result field - for backward compatibility with router code."""
        return self.result

class UniversalAgent(ABC):
    """Universal agent interface.

    All framework adapters implement this.
    """

    @abstractmethod
    def get_card(self) -> AgentCard:
        """Return agent's capability card."""
        pass

    @abstractmethod
    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute a task.

        Args:
            task: Natural language task description
            context: Execution context (state, history, etc.)

        Returns:
            AgentResult with status and result
        """
        pass

    @abstractmethod
    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format."""
        pass

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming output."""
        return False

    async def execute_stream(self, task: str, context: dict | None = None):
        """Execute with streaming (optional)."""
        raise NotImplementedError("This agent does not support streaming")

    def inject_skills(self, skills: list["Skill"]) -> None:
        """Inject markdown skills into agent's system prompt.

        Override this method in adapters to customize skill injection
        behavior for specific frameworks.

        Default implementation stores skills for retrieval via get_injected_skills().
        Adapters should call format_skills_for_prompt() and prepend to system prompt.

        Args:
            skills: List of eligible Skill objects to inject
        """
        # Default: store skills for later retrieval
        self._injected_skills = skills

    def get_injected_skills(self) -> list["Skill"]:
        """Get skills that have been injected into this agent.

        Returns:
            List of injected skills, or empty list if none
        """
        return getattr(self, "_injected_skills", [])

    def build_skill_context(self) -> str:
        """Build skill context string for system prompt.

        Convenience method for adapters to format injected skills.

        Returns:
            Formatted skill context, or empty string if no skills
        """
        skills = self.get_injected_skills()
        if not skills:
            return ""

        from core.skills.adapter import MarkdownSkillAdapter

        adapter = MarkdownSkillAdapter()
        skill_text = adapter.format_skills_for_prompt(skills)
        guidance = adapter.build_skill_guidance()
        return skill_text + guidance

    def capabilities(self) -> "AgentCapabilities":
        """Return agent's runtime capabilities.

        Orchestrator calls this to know what features are available.
        Per user decision: dynamic check at each call (not cached).
        Default implementation returns minimal capabilities.
        Override in adapters to expose framework-specific features.
        """
        return AgentCapabilities(supports_streaming=self.supports_streaming())

# AgentExecutionError is imported from core.exceptions for backward compatibility
