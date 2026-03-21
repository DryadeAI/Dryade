"""Multi-Framework Agent Adapters."""

from core.adapters.a2a_adapter import A2AAgentAdapter
from core.adapters.adk_adapter import ADKAgentAdapter
from core.adapters.crewai_adapter import CrewAIAgentAdapter
from core.adapters.crewai_delegation import CrewDelegationAdapter
from core.adapters.langchain_adapter import LangChainAgentAdapter
from core.adapters.langgraph_delegation import LangGraphDelegationAdapter
from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentExecutionError,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.adapters.registry import (
    AgentRegistry,
    get_agent,
    get_registry,
    list_agents,
    register_agent,
    unregister_agent,
)

__all__ = [
    # Protocol
    "UniversalAgent",
    "AgentCard",
    "AgentCapability",
    "AgentResult",
    "AgentFramework",
    "AgentExecutionError",
    # Adapters
    "CrewAIAgentAdapter",
    "CrewDelegationAdapter",
    "LangChainAgentAdapter",
    "LangGraphDelegationAdapter",
    "A2AAgentAdapter",
    "ADKAgentAdapter",
    # Registry
    "AgentRegistry",
    "get_registry",
    "register_agent",
    "unregister_agent",
    "get_agent",
    "list_agents",
]
