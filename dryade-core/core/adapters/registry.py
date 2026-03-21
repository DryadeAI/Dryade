"""Agent Registry - Discover and manage agents from all frameworks.

Target: ~80 LOC
"""

import threading

from core.adapters.protocol import AgentCard, AgentFramework, UniversalAgent


class AgentRegistry:
    """Central registry for all agents across frameworks.

    Features:
    - Auto-discovery of local agents (CrewAI, LangChain)
    - A2A remote agent discovery
    - Capability-based agent selection
    - Thread-safe: all dict operations protected by RLock
    """

    def __init__(self):
        """Initialize an empty agent registry."""
        self._agents: dict[str, UniversalAgent] = {}
        self._lock = threading.RLock()

    def register(self, agent: UniversalAgent):
        """Register an agent."""
        card = agent.get_card()
        with self._lock:
            self._agents[card.name] = agent

    def unregister(self, name: str):
        """Unregister an agent by name."""
        with self._lock:
            self._agents.pop(name, None)

    def get(self, name: str) -> UniversalAgent | None:
        """Get agent by name."""
        with self._lock:
            return self._agents.get(name)

    def list_agents(self) -> list[AgentCard]:
        """List all registered agents."""
        with self._lock:
            agents = list(self._agents.values())
        return [agent.get_card() for agent in agents]

    def find_by_framework(self, framework: AgentFramework) -> list[UniversalAgent]:
        """Find agents by framework."""
        with self._lock:
            agents = list(self._agents.values())
        return [agent for agent in agents if agent.get_card().framework == framework]

    def find_by_capability(self, capability_name: str) -> list[UniversalAgent]:
        """Find agents that have a specific capability."""
        with self._lock:
            agents = list(self._agents.values())
        result = []
        for agent in agents:
            card = agent.get_card()
            for cap in card.capabilities:
                if cap.name == capability_name:
                    result.append(agent)
                    break
        return result

    def clear(self):
        """Clear all registered agents."""
        with self._lock:
            self._agents.clear()

    def __len__(self) -> int:
        """Return number of registered agents."""
        with self._lock:
            return len(self._agents)

    def __contains__(self, name: str) -> bool:
        """Check if agent is registered."""
        with self._lock:
            return name in self._agents

# Global registry instance
_registry: AgentRegistry | None = None
_registry_lock = threading.Lock()

def get_registry() -> AgentRegistry:
    """Get or create global agent registry.

    Uses double-checked locking to avoid lock acquisition on every call
    while ensuring thread-safe singleton creation.
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = AgentRegistry()
    return _registry

def register_agent(agent: UniversalAgent):
    """Convenience function to register an agent."""
    get_registry().register(agent)

def get_agent(name: str) -> UniversalAgent | None:
    """Convenience function to get an agent."""
    return get_registry().get(name)

def list_agents() -> list[AgentCard]:
    """Convenience function to list all agents."""
    return get_registry().list_agents()

def unregister_agent(name: str):
    """Convenience function to unregister an agent."""
    get_registry().unregister(name)
