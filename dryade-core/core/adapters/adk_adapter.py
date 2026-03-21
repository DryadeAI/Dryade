"""ADK (Agent Development Kit) Adapter.

Wraps Google ADK agents to work with the Dryade universal agent interface.
Uses the ADK Runner pattern with InMemorySessionService for session
persistence across orchestration steps, and InMemoryArtifactService
for artifact extraction.

Target: ~200 LOC
"""

import logging
import time
from typing import Any

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger("dryade.adapter.adk")

# Import-guarded: adapter is importable without google-adk installed
_ADK_AVAILABLE = False
try:
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    _ADK_AVAILABLE = True
except ImportError:
    pass

class ADKAgentAdapter(UniversalAgent):
    """Adapter for Google ADK (Agent Development Kit) agents.

    Uses the Runner + InMemorySessionService pattern for proper session
    lifecycle management. Sessions persist across multiple execute() calls
    within the same adapter instance, maintaining agent context across
    orchestration steps.

    Supports:
    - Single agents (google.adk.Agent)
    - Workflow agents (SequentialAgent, ParallelAgent, LoopAgent)
      which execute as single orchestration steps.

    Usage:
        from google.adk import Agent as ADKAgent

        adk_agent = ADKAgent(name="my_agent", ...)
        adapter = ADKAgentAdapter(adk_agent)
        result = await adapter.execute("Analyze this data")
    """

    def __init__(
        self,
        agent: Any,
        name: str | None = None,
        description: str | None = None,
        session_service: Any | None = None,
        artifact_service: Any | None = None,
    ):
        """Initialize the ADK adapter.

        Args:
            agent: ADK Agent instance (Agent, SequentialAgent, etc.)
            name: Optional name override (defaults to agent.name)
            description: Optional description override
            session_service: Custom SessionService (defaults to InMemorySessionService)
            artifact_service: Custom ArtifactService (defaults to InMemoryArtifactService)
        """
        self._agent = agent
        self._name = name or getattr(agent, "name", "adk_agent")
        self._description = description or getattr(
            agent, "description", getattr(agent, "instruction", "ADK Agent")
        )
        self._custom_session_service = session_service
        self._custom_artifact_service = artifact_service

        # Lazy-initialized on first execute() to avoid import at construction
        self._runner: Any | None = None
        self._session_service: Any | None = None
        self._artifact_service: Any | None = None
        self._session_id: str | None = None
        self._card: AgentCard | None = None
        self._app_name = "dryade"
        self._user_id = "orchestrator"

    async def _ensure_runner(self) -> None:
        """Lazy initialization of Runner, SessionService, ArtifactService.

        Creates a persistent session on first call. Subsequent calls
        reuse the existing runner and session for state continuity.
        """
        if self._runner is not None:
            return

        if not _ADK_AVAILABLE:
            raise ImportError("google-adk is not installed")

        # Create services (custom or default)
        self._session_service = (
            self._custom_session_service
            if self._custom_session_service is not None
            else InMemorySessionService()
        )
        self._artifact_service = (
            self._custom_artifact_service
            if self._custom_artifact_service is not None
            else InMemoryArtifactService()
        )

        # Create Runner with agent and services
        self._runner = Runner(
            agent=self._agent,
            app_name=self._app_name,
            session_service=self._session_service,
            artifact_service=self._artifact_service,
        )

        # Create a persistent session (async in newer ADK versions)
        session = await self._session_service.create_session(
            app_name=self._app_name,
            user_id=self._user_id,
        )
        self._session_id = session.id

        logger.debug(f"ADK Runner initialized for '{self._name}', session={self._session_id}")

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute a task using the ADK Runner.

        Session persists across calls -- the agent maintains context from
        previous interactions within this adapter's lifetime.

        Args:
            task: Natural language task description
            context: Optional execution context (currently unused by ADK,
                     reserved for future prompt augmentation)

        Returns:
            AgentResult with status and output
        """
        if not _ADK_AVAILABLE:
            return AgentResult(
                result="ADK not installed. Install with: pip install google-adk",
                status="error",
                error="ADK not available",
            )

        start = time.time()

        try:
            await self._ensure_runner()

            # Build the user message
            message = genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=task)],
            )

            # Execute via Runner -- returns async iterable of events
            response_text = await self._run_and_extract(message)

            execution_time_ms = (time.time() - start) * 1000

            # Extract artifact count
            artifacts_count = await self._count_artifacts()

            return AgentResult(
                result=response_text,
                status="ok",
                metadata={
                    "agent": self._name,
                    "framework": "adk",
                    "session_id": self._session_id,
                    "artifacts_count": artifacts_count,
                    "execution_time_ms": round(execution_time_ms, 1),
                },
            )

        except ImportError as e:
            return AgentResult(
                result=f"ADK import error: {e}",
                status="error",
                error="ADK not available",
            )
        except Exception as e:
            execution_time_ms = (time.time() - start) * 1000
            logger.exception(f"ADK execution failed for '{self._name}': {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"ADK execution failed: {type(e).__name__}",
                metadata={
                    "agent": self._name,
                    "framework": "adk",
                    "session_id": self._session_id,
                    "execution_time_ms": round(execution_time_ms, 1),
                },
            )

    async def _run_and_extract(self, message: Any) -> str:
        """Run the agent via Runner and extract text from events.

        Runner.run_async() yields Event objects. We collect them and
        extract the final response text from the last event with content.

        Args:
            message: genai_types.Content with user message

        Returns:
            Extracted text response
        """
        events = []
        async for event in self._runner.run_async(
            session_id=self._session_id,
            user_id=self._user_id,
            new_message=message,
        ):
            events.append(event)

        return self._extract_response(events)

    def _extract_response(self, events: list[Any]) -> str:
        """Extract text response from Runner events.

        Iterates events in reverse to find the last event with text
        content parts (the final agent response).

        Args:
            events: List of ADK Event objects

        Returns:
            Extracted text, or string representation of events
        """
        # Walk events in reverse to find the last meaningful response
        for event in reversed(events):
            content = getattr(event, "content", None)
            if content is None:
                continue
            parts = getattr(content, "parts", None)
            if not parts:
                continue
            # Extract text from parts
            texts = []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    texts.append(text)
            if texts:
                return "\n".join(texts)

        # Fallback: stringify all events
        if events:
            return str(events[-1])
        return ""

    async def _count_artifacts(self) -> int:
        """Count artifacts produced during the session.

        Returns:
            Number of artifacts, or 0 if unavailable
        """
        try:
            if self._artifact_service is None:
                return 0
            artifacts = self._artifact_service.list_artifacts(
                app_name=self._app_name,
                user_id=self._user_id,
                session_id=self._session_id,
            )
            if hasattr(artifacts, "__await__"):
                artifacts = await artifacts
            return len(artifacts) if artifacts else 0
        except Exception:
            return 0

    async def reset_session(self) -> str:
        """Create a new session, discarding previous context.

        Useful when starting a fresh orchestration run.

        Returns:
            The new session ID
        """
        if not _ADK_AVAILABLE:
            raise ImportError("google-adk is not installed")

        await self._ensure_runner()

        session = await self._session_service.create_session(
            app_name=self._app_name,
            user_id=self._user_id,
        )
        self._session_id = session.id
        logger.debug(f"ADK session reset for '{self._name}', new session={self._session_id}")
        return self._session_id

    def get_card(self) -> AgentCard:
        """Return agent's capability card."""
        if self._card is None:
            self._card = self._build_card()
        return self._card

    def _build_card(self) -> AgentCard:
        """Build AgentCard from ADK agent metadata."""
        capabilities = []
        tools = getattr(self._agent, "tools", [])
        for tool in tools:
            tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))
            tool_desc = getattr(tool, "description", getattr(tool, "__doc__", ""))

            params = {}
            if hasattr(tool, "parameters"):
                params = tool.parameters
            elif hasattr(tool, "__annotations__"):
                params = {k: str(v) for k, v in tool.__annotations__.items()}

            capabilities.append(
                AgentCapability(
                    name=tool_name,
                    description=tool_desc or f"Tool: {tool_name}",
                    input_schema=params,
                )
            )

        return AgentCard(
            name=self._name,
            description=self._description,
            version=getattr(self._agent, "version", "1.0.0"),
            capabilities=capabilities,
            framework=AgentFramework.ADK,
            metadata={
                "model": getattr(self._agent, "model", None),
                "instruction": getattr(self._agent, "instruction", None),
                "session_persistent": True,
            },
        )

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format."""
        tools = []
        for cap in self.get_card().capabilities:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": cap.name,
                        "description": cap.description,
                        "parameters": cap.input_schema or {"type": "object", "properties": {}},
                    },
                }
            )
        return tools

    def supports_streaming(self) -> bool:
        """ADK Runner supports streaming via event iteration."""
        return True

    def capabilities(self) -> AgentCapabilities:
        """Return ADK-specific capabilities."""
        return AgentCapabilities(
            supports_streaming=True,
            supports_sessions=True,
            supports_artifacts=True,
            max_retries=3,
            timeout_seconds=30,
            framework_specific={
                "google_adk": True,
                "session_persistent": True,
            },
        )
