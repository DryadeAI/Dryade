"""LangChain/LangGraph Agent Adapter.

Wraps LangChain agents to conform to UniversalAgent interface.
Target: ~80 LOC
"""

import logging
from typing import Any

from core.adapters.protocol import (
    AgentCapabilities,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

logger = logging.getLogger(__name__)

class LangChainAgentAdapter(UniversalAgent):
    """Wrap LangChain Agent as UniversalAgent.

    Supports:
    - LangChain AgentExecutor
    - LangGraph CompiledGraph
    """

    def __init__(self, agent, name: str, description: str):
        """Initialize with a LangChain agent.

        Args:
            agent: LangChain AgentExecutor or LangGraph CompiledGraph
            name: Agent name for identification
            description: What the agent does
        """
        self.agent = agent
        self.name = name
        self.description = description

    def get_card(self) -> AgentCard:
        """Return agent's capability card."""
        return AgentCard(
            name=self.name,
            description=self.description,
            version="1.0",
            framework=AgentFramework.LANGCHAIN,
            capabilities=[],  # LangChain doesn't expose capabilities cleanly
            metadata={
                "type": type(self.agent).__name__,
            },
        )

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> AgentResult:
        """Execute a task using the LangChain agent with graceful error handling."""
        try:
            # LangGraph CompiledGraph
            if hasattr(self.agent, "ainvoke"):
                result = await self.agent.ainvoke({"input": task, **(context or {})})
                return AgentResult(
                    result=result,
                    status="ok",
                    metadata={"framework": "langgraph", "agent": self.name},
                )

            # LangChain AgentExecutor with async
            if hasattr(self.agent, "arun"):
                result = await self.agent.arun(task)
                return AgentResult(
                    result=result,
                    status="ok",
                    metadata={"framework": "langchain", "agent": self.name},
                )

            # Sync fallback
            if hasattr(self.agent, "run"):
                result = self.agent.run(task)
                return AgentResult(
                    result=result,
                    status="ok",
                    metadata={"framework": "langchain", "agent": self.name},
                )

            # No suitable method found - return error result instead of raising
            logger.warning(f"LangChain agent {self.name} has no run/arun/ainvoke method")
            return AgentResult(
                result=None,
                status="error",
                error="Agent has no compatible execution method (run/arun/ainvoke)",
                metadata={
                    "error_type": "unsupported",
                    "framework": "langchain",
                    "agent": self.name,
                },
            )

        except TimeoutError as e:
            logger.warning(f"LangChain adapter timeout for {self.name}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error="Agent timed out. Try simplifying the request.",
                metadata={"error_type": "timeout", "framework": "langchain", "agent": self.name},
            )
        except Exception as e:
            logger.exception(f"LangChain adapter execution failed for {self.name}: {e}")
            return AgentResult(
                result=None,
                status="error",
                error=f"Agent execution failed: {type(e).__name__}",
                metadata={"error_type": "execution", "framework": "langchain", "agent": self.name},
            )

    def get_tools(self) -> list[dict[str, Any]]:
        """Return available tools in OpenAI function format."""
        tools = []

        # Try to get tools from agent
        agent_tools = getattr(self.agent, "tools", [])

        for tool in agent_tools:
            tool_def = {
                "type": "function",
                "function": {
                    "name": getattr(tool, "name", str(tool)),
                    "description": getattr(tool, "description", ""),
                    "parameters": {},
                },
            }

            # Try to get schema
            if hasattr(tool, "args_schema") and tool.args_schema:
                tool_def["function"]["parameters"] = tool.args_schema.schema()

            tools.append(tool_def)

        return tools

    def supports_streaming(self) -> bool:
        """Check if agent supports streaming."""
        return hasattr(self.agent, "astream") or hasattr(self.agent, "stream")

    async def execute_stream(self, task: str, context: dict | None = None):
        """Execute with streaming output."""
        if hasattr(self.agent, "astream"):
            async for chunk in self.agent.astream({"input": task, **(context or {})}):
                yield chunk
        elif hasattr(self.agent, "stream"):
            for chunk in self.agent.stream({"input": task, **(context or {})}):
                yield chunk
        else:
            raise NotImplementedError("Agent does not support streaming")

    def capabilities(self) -> AgentCapabilities:
        """Return LangChain-specific capabilities."""
        has_memory = hasattr(self.agent, "memory") and self.agent.memory is not None
        is_langgraph = hasattr(self.agent, "get_state")
        return AgentCapabilities(
            supports_streaming=hasattr(self.agent, "astream"),
            supports_memory=has_memory,
            supports_callbacks=True,
            max_retries=3,
            timeout_seconds=30,
            framework_specific={
                "is_langgraph": is_langgraph,
                "supports_delegation": is_langgraph,
            },
        )

    def get_memory(self) -> dict | None:
        """Get conversation memory if agent has it."""
        if not hasattr(self.agent, "memory") or not self.agent.memory:
            return None
        messages = []
        if hasattr(self.agent.memory, "chat_memory"):
            messages = [
                {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
                for m in self.agent.memory.chat_memory.messages
            ]
        return {"type": "langchain", "messages": messages}

    def is_langgraph(self) -> bool:
        """Check if this is a LangGraph agent (stateful)."""
        return hasattr(self.agent, "get_state")
