"""CrewAI Agent Adapter (Native).

Wraps CrewAI agents to conform to UniversalAgent interface.
Supports both eager (existing agent) and lazy (deferred creation) modes.
Target: ~120 LOC
"""

import ast
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger("dryade.adapter")

# Pattern to detect CrewAI "Action: X / Action Input: Y" text responses
# that should have been tool calls but were rendered as plain text by vLLM.
_ACTION_PATTERN = re.compile(
    r"Action:\s*(.+?)\s*\n\s*Action Input:\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)

class CrewAIAgentAdapter(UniversalAgent):
    """Wrap CrewAI Agent as UniversalAgent.

    Supports two modes:
    1. Eager: Pass an existing crewai.Agent instance
    2. Lazy: Pass agent_config dict, agent created on first use with user's LLM config
    """

    def __init__(
        self,
        agent=None,
        name: str | None = None,
        *,
        agent_config: dict[str, Any] | None = None,
        tools: list[Any] | None = None,
        sse_emitter: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Initialize with a CrewAI Agent or config for lazy creation.

        Args:
            agent: crewai.Agent instance (eager mode)
            name: Optional custom name for the agent (defaults to agent's role)
            agent_config: Config dict for lazy agent creation (lazy mode)
            tools: Tools to attach to agent (lazy mode)
            sse_emitter: Optional callback for SSE event streaming (Phase 67)
        """
        self._agent = agent
        self._name = name
        self._agent_config = agent_config
        self._tools = tools or []
        self._sse_emitter = sse_emitter

    @property
    def agent(self):
        """Get the CrewAI agent, creating lazily if needed."""
        if self._agent is None and self._agent_config:
            self._agent = self._create_agent_from_config()
        return self._agent

    @agent.setter
    def agent(self, value):
        """Set the agent directly."""
        self._agent = value

    def _create_agent_from_config(self):
        """Create CrewAI agent from stored config with current user's LLM."""
        from crewai import Agent

        from core.providers.llm_adapter import get_configured_llm

        config = self._agent_config
        return Agent(
            role=config.get("role", "Agent"),
            goal=config.get("goal", ""),
            backstory=config.get("backstory", ""),
            tools=self._tools,
            llm=get_configured_llm(),
            verbose=config.get("verbose", True),
            allow_delegation=config.get("allow_delegation", False),
        )

    def _parse_action_response(self, text: str) -> tuple[str, dict] | None:
        """Parse CrewAI Action/ActionInput text into (tool_name, args).

        When vLLM returns tool calls, CrewAI sometimes converts them to
        "Action: X / Action Input: Y" text instead of executing them.
        This method detects and parses that pattern.

        Returns None if text does not match the Action pattern.
        """
        match = _ACTION_PATTERN.search(text)
        if not match:
            return None
        tool_name = match.group(1).strip()
        raw_args = match.group(2).strip()
        try:
            args = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            args = {"input": raw_args}
        return (tool_name, args)

    def _detect_raw_tool_call_dict(self, result_text: str) -> tuple[str, dict] | None:
        """Detect when result_text is a serialized dict containing tool_calls.

        When VLLMBaseLLM.call() Path 2 returns a raw dict (because
        available_functions is None), CrewAI does str(dict) on it and
        treats it as "Final Answer".  This method detects that pattern
        using ast.literal_eval for safe parsing.

        Returns (tool_name, args_dict) or None.
        """
        stripped = result_text.strip()
        if not stripped.startswith("{"):
            return None
        try:
            parsed = ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(parsed, dict) or "tool_calls" not in parsed:
            return None
        tool_calls = parsed["tool_calls"]
        if not isinstance(tool_calls, list) or len(tool_calls) == 0:
            return None
        first_call = tool_calls[0]
        func = first_call.get("function") if isinstance(first_call, dict) else None
        if not func or not isinstance(func, dict):
            return None
        tool_name = func.get("name")
        if not tool_name:
            return None
        raw_args = func.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = {"input": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        return (tool_name, args)

    def _configure_llm_from_context(self) -> None:
        """Configure agent's LLM from user context or environment.

        Uses get_configured_llm() which respects the llm_config_source toggle
        and properly handles all provider types including vLLM (returns VLLMBaseLLM
        instead of crewai.LLM which would trigger LiteLLM's native vLLM handler).
        """
        from core.providers.llm_adapter import get_configured_llm

        self.agent.llm = get_configured_llm()

    def get_card(self) -> AgentCard:
        """Return agent's capability card.

        Works with both eager (existing agent) and lazy (config-based) modes.
        For lazy mode, returns card info from config without creating the agent.
        """
        # For lazy mode, return card from config without triggering agent creation
        if self._agent is None and self._agent_config:
            capabilities = []
            for tool in self._tools:
                cap = AgentCapability(
                    name=getattr(tool, "name", str(tool)),
                    description=getattr(tool, "description", ""),
                    input_schema=tool.args_schema.schema()
                    if hasattr(tool, "args_schema") and tool.args_schema
                    else {},
                    output_schema={},
                )
                capabilities.append(cap)

            return AgentCard(
                name=self._name or self._agent_config.get("role", "unknown"),
                description=self._agent_config.get("goal", ""),
                version="1.0",
                framework=AgentFramework.CREWAI,
                capabilities=capabilities,
                metadata={
                    "backstory": self._agent_config.get("backstory", ""),
                    "verbose": self._agent_config.get("verbose", False),
                    "lazy": True,  # Indicates agent not yet created
                },
            )

        # Eager mode - agent already exists
        capabilities = []
        for tool in getattr(self.agent, "tools", []):
            cap = AgentCapability(
                name=getattr(tool, "name", str(tool)),
                description=getattr(tool, "description", ""),
                input_schema=tool.args_schema.schema()
                if hasattr(tool, "args_schema") and tool.args_schema
                else {},
                output_schema={},
            )
            capabilities.append(cap)

        return AgentCard(
            name=self._name or getattr(self.agent, "role", "unknown"),
            description=getattr(self.agent, "goal", ""),
            version="1.0",
            framework=AgentFramework.CREWAI,
            capabilities=capabilities,
            metadata={
                "backstory": getattr(self.agent, "backstory", ""),
                "verbose": getattr(self.agent, "verbose", False),
            },
        )

    async def execute(self, task: str, _context: dict[str, Any] | None = None) -> AgentResult:
        """Execute a task using the CrewAI agent with sandbox and healing tracking."""
        import time

        start_time = time.time()

        try:
            from crewai import Crew, Task

            # Inject user's LLM configuration if available (from request context or env)
            self._configure_llm_from_context()

            # Create a task for this agent
            crewai_task = Task(
                description=task, agent=self.agent, expected_output="Result of the task"
            )

            # Create a minimal crew and execute
            crew = Crew(agents=[self.agent], tasks=[crewai_task], verbose=False)

            logger.debug(f"Executing CrewAI agent: {self._name or 'unknown'}")
            result = crew.kickoff()
            execution_time_ms = (time.time() - start_time) * 1000

            result_text = str(result)

            # Check if vLLM returned tool_calls formatted as Action/ActionInput text
            # OR as a raw dict (Path 2). CrewAI treats both as final answer instead
            # of executing the tool. We intercept and execute via MCP registry.
            parsed = self._parse_action_response(result_text)
            if not parsed:
                parsed = self._detect_raw_tool_call_dict(result_text)
            if parsed:
                tool_name, tool_args = parsed
                tool_executed = False

                # Try local agent tools first (CrewAI BaseTool instances)
                for tool in getattr(self.agent, "tools", []):
                    if getattr(tool, "name", "") == tool_name:
                        logger.info(f"[CrewAI] Executing local tool: {tool_name}")
                        try:
                            result_text = str(tool._run(**tool_args) if tool_args else tool._run())
                            tool_executed = True
                        except Exception as e:
                            logger.warning(f"[CrewAI] Local tool {tool_name} failed: {e}")
                        break

                # Fall back to MCP registry
                if not tool_executed:
                    try:
                        from core.mcp import get_registry

                        registry = get_registry()
                        tool_result = registry.call_tool_by_name(tool_name, tool_args)
                        content_parts = []
                        for item in tool_result.content:
                            if hasattr(item, "text") and item.text:
                                content_parts.append(item.text)
                        result_text = "\n".join(content_parts) if content_parts else str(tool_result)
                        tool_executed = True
                    except Exception as mcp_err:
                        logger.warning(f"[CrewAI] Tool {tool_name} not found locally or in MCP: {mcp_err}")

            # Collect sandbox metadata from agent tools
            sandbox_metadata = self._get_sandbox_metadata()

            # Collect self-healing metadata
            healing_metadata = self._get_healing_metadata()

            metadata = {
                "framework": "crewai",
                "execution_time_ms": execution_time_ms,
                "tools_count": len(getattr(self.agent, "tools", [])),
                "tool_intercepted": parsed is not None,
                "tool_name": parsed[0] if parsed else None,
            }

            # Add sandbox info if available
            if sandbox_metadata:
                metadata["sandbox"] = sandbox_metadata

            # Add healing info if available
            if healing_metadata:
                metadata["healing"] = healing_metadata

            return AgentResult(result=result_text, status="ok", metadata=metadata)

        except TimeoutError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.warning(f"CrewAI agent timeout for {self._name or 'unknown'}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error="Agent timed out. Try simplifying the request.",
                metadata={
                    "error_type": "timeout",
                    "framework": "crewai",
                    "agent": self._name,
                    "execution_time_ms": execution_time_ms,
                },
            )
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.exception(f"CrewAI agent execution failed for {self._name or 'unknown'}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Agent execution failed: {type(e).__name__}",
                metadata={
                    "error_type": "execution",
                    "framework": "crewai",
                    "agent": self._name,
                    "execution_time_ms": execution_time_ms,
                },
            )

    def _get_sandbox_metadata(self) -> dict[str, Any]:
        """Get sandbox metadata for agent tools."""
        try:
            from core.extensions import get_sandbox_registry

            registry = get_sandbox_registry()

            # Collect isolation levels for agent tools
            tool_isolation = {}
            for tool in getattr(self.agent, "tools", []):
                tool_name = getattr(tool, "name", str(tool))
                level = registry.get_isolation_level(tool_name)
                tool_isolation[tool_name] = level.value

            return {"enabled": registry.is_enabled(), "tool_isolation_levels": tool_isolation}
        except Exception as e:
            return {"error": f"Failed to get sandbox metadata: {str(e)}"}

    def _get_healing_metadata(self) -> dict[str, Any]:
        """Get self-healing metadata for agent execution."""
        try:
            from core.config import get_settings
            from core.extensions import get_all_circuit_breakers

            # Get circuit breaker states
            breakers = get_all_circuit_breakers()
            breaker_states = {name: breaker.get_state() for name, breaker in breakers.items()}

            # Get self-healing configuration
            settings = get_settings()

            return {
                "enabled": settings.self_healing_enabled,
                "max_retry_attempts": settings.retry_max_attempts,
                "circuit_breakers": breaker_states,
            }
        except Exception as e:
            return {"error": f"Failed to get healing metadata: {str(e)}"}

    def run_with_events(
        self,
        task: str,
        sse_emitter: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentResult:
        """Run agent with event streaming to SSE.

        Uses the CrewAI event bridge to capture agent execution events
        and stream them via SSE for real-time frontend visibility.

        Args:
            task: Task description for the agent
            sse_emitter: Optional SSE callback (overrides constructor emitter)

        Returns:
            AgentResult from execution
        """
        import asyncio

        # Run the async method synchronously
        return asyncio.get_event_loop().run_until_complete(self.arun_with_events(task, sse_emitter))

    async def arun_with_events(
        self,
        task: str,
        sse_emitter: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentResult:
        """Async run agent with event streaming to SSE.

        Uses the CrewAI event bridge to capture agent execution events
        and stream them via SSE for real-time frontend visibility.

        Args:
            task: Task description for the agent
            sse_emitter: Optional SSE callback (overrides constructor emitter)

        Returns:
            AgentResult from execution
        """
        emitter = sse_emitter or self._sse_emitter

        if emitter is None:
            # No SSE streaming, run normally
            return await self.execute(task)

        # Import event bridge
        from core.crew import CrewAIEventBridge

        # Create SSE-compatible event converter
        def emit_sse(event):
            """Convert SSEEvent to dict for SSE emission."""
            emitter(
                {
                    "type": event.type,
                    "agent": event.agent,
                    "content": event.content,
                    "tool": event.tool,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "metadata": event.metadata or {},
                }
            )

        # Run with event bridge context manager
        with CrewAIEventBridge(emit_sse):
            return await self.execute(task)

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format."""
        tools = []
        for tool in getattr(self.agent, "tools", []):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": getattr(tool, "name", str(tool)),
                        "description": getattr(tool, "description", ""),
                        "parameters": tool.args_schema.schema()
                        if hasattr(tool, "args_schema") and tool.args_schema
                        else {},
                    },
                }
            )
        return tools

    def capabilities(self) -> AgentCapabilities:
        """Return CrewAI-specific capabilities."""
        has_memory = hasattr(self.agent, "memory") and self.agent.memory is not None
        has_knowledge = hasattr(self.agent, "knowledge_sources") and bool(
            self.agent.knowledge_sources
        )
        return AgentCapabilities(
            supports_streaming=True,  # Via event bus
            supports_memory=has_memory,
            supports_knowledge=has_knowledge,
            supports_delegation=getattr(self.agent, "allow_delegation", False),
            supports_callbacks=True,
            max_retries=3,
            timeout_seconds=30,
            is_critical=getattr(self.agent, "is_critical", False),
            framework_specific={"has_event_bus": True},
        )

    def get_memory(self) -> dict | None:
        """Get agent's memory if available."""
        if hasattr(self.agent, "memory") and self.agent.memory:
            return {"type": "crewai", "data": self.agent.memory}
        return None

    async def inject_knowledge(self, sources: list) -> None:
        """Inject knowledge bases into agent before execution."""
        if self.agent is not None:
            self.agent.knowledge_sources = sources

    def supports_delegation(self) -> bool:
        """Check if agent can delegate to peers."""
        return getattr(self.agent, "allow_delegation", False) if self.agent else False
