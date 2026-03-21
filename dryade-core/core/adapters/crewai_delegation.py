"""CrewAI Crew Delegation Adapter.

Wraps an entire CrewAI Crew (multi-agent, multi-task) as a single
UniversalAgent.execute() call. The crew handles its own internal
orchestration; Dryade orchestrates between frameworks.

Target: ~150 LOC
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger("dryade.adapter.delegation")

class CrewDelegationAdapter(UniversalAgent):
    """Wrap a full CrewAI Crew as a single UniversalAgent.

    Enables the orchestrator to delegate to a multi-agent, multi-task
    CrewAI Crew (sequential or hierarchical process) as one orchestration
    step. The framework manages its own internal agent coordination.

    Usage:
        from crewai import Agent, Task, Crew, Process

        agents = [researcher, writer]
        tasks = [research_task, write_task]
        crew = Crew(agents=agents, tasks=tasks, process=Process.sequential)

        adapter = CrewDelegationAdapter(
            crew=crew,
            name="content-team",
            description="Research and write content",
        )
        result = await adapter.execute("Write about AI trends")
    """

    def __init__(
        self,
        crew: Any,
        name: str,
        description: str,
        sse_emitter: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Initialize with a CrewAI Crew instance.

        Args:
            crew: crewai.Crew instance (type is Any for import-guarding)
            name: Identifier for this delegation unit
            description: What the crew does
            sse_emitter: Optional SSE callback for event streaming
        """
        self._crew = crew
        self._name = name
        self._description = description
        self._sse_emitter = sse_emitter

    @property
    def _process_value(self) -> str:
        """Get the crew process type as a string."""
        process = getattr(self._crew, "process", None)
        if process is not None and hasattr(process, "value"):
            return process.value
        return str(process) if process else "sequential"

    @property
    def _agents_count(self) -> int:
        """Get the number of agents in the crew."""
        agents = getattr(self._crew, "agents", [])
        return len(agents) if agents else 0

    @property
    def _tasks_count(self) -> int:
        """Get the number of tasks in the crew."""
        tasks = getattr(self._crew, "tasks", [])
        return len(tasks) if tasks else 0

    def get_card(self) -> AgentCard:
        """Return agent card for this crew delegation unit."""
        return AgentCard(
            name=self._name,
            description=self._description,
            version="1.0",
            framework=AgentFramework.CREWAI,
            metadata={
                "process": self._process_value,
                "agents_count": self._agents_count,
                "tasks_count": self._tasks_count,
                "delegation": True,
            },
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute the full crew as a single orchestration step.

        Injects user's LLM config into all crew agents, then runs
        crew.kickoff() in a thread to avoid blocking the async loop.

        Args:
            task: Natural language task description
            context: Optional execution context merged into crew inputs

        Returns:
            AgentResult with crew output and execution metadata
        """
        from core.providers.llm_adapter import get_configured_llm

        start = time.time()

        try:
            # Inject user's LLM into ALL crew agents before kickoff
            configured_llm = get_configured_llm()
            for agent in getattr(self._crew, "agents", []):
                agent.llm = configured_llm

            # Build inputs: merge context with task
            inputs: dict[str, Any] = {}
            if context:
                inputs.update(context)
            inputs["task"] = task

            # Execute with optional event bridge for SSE streaming
            if self._sse_emitter is not None:
                result = await self._execute_with_events(inputs)
            else:
                result = await asyncio.to_thread(self._crew.kickoff, inputs=inputs)

            execution_time_ms = (time.time() - start) * 1000

            return AgentResult(
                result=str(result),
                status="ok",
                metadata={
                    "framework": "crewai",
                    "process": self._process_value,
                    "agents_count": self._agents_count,
                    "tasks_count": self._tasks_count,
                    "delegation": True,
                    "execution_time_ms": execution_time_ms,
                },
            )

        except Exception as e:
            execution_time_ms = (time.time() - start) * 1000
            logger.exception(f"Crew execution failed for '{self._name}': {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Crew execution failed: {type(e).__name__}",
                metadata={
                    "framework": "crewai",
                    "process": self._process_value,
                    "agents_count": self._agents_count,
                    "tasks_count": self._tasks_count,
                    "delegation": True,
                    "execution_time_ms": execution_time_ms,
                },
            )

    async def _execute_with_events(self, inputs: dict[str, Any]) -> Any:
        """Execute crew kickoff inside CrewAIEventBridge context.

        Wraps the threaded kickoff in an event bridge so that CrewAI
        internal events stream via SSE to the frontend.
        """
        from core.crew import CrewAIEventBridge
        from core.crew.event_bridge import SSEEvent

        def emit_sse(event: SSEEvent) -> None:
            """Convert SSEEvent to dict for SSE emission."""
            if self._sse_emitter is None:
                return
            self._sse_emitter(
                {
                    "type": event.type,
                    "agent": event.agent,
                    "content": event.content,
                    "tool": event.tool,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "metadata": event.metadata or {},
                }
            )

        with CrewAIEventBridge(emit_sse):
            return await asyncio.to_thread(self._crew.kickoff, inputs=inputs)

    def get_tools(self) -> list[dict[str, Any]]:
        """Return empty list -- crew manages its own tools internally."""
        return []

    def supports_streaming(self) -> bool:
        """Supports streaming via CrewAI event bridge."""
        return True

    def capabilities(self) -> AgentCapabilities:
        """Return delegation-specific capabilities."""
        crew_memory = getattr(self._crew, "memory", False)
        return AgentCapabilities(
            supports_streaming=True,
            supports_memory=bool(crew_memory),
            supports_delegation=True,
            supports_callbacks=True,
            framework_specific={
                "process": self._process_value,
                "delegation": True,
            },
        )
