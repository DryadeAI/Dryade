"""Unit tests for agent registry."""

import pytest

@pytest.mark.unit
class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    def test_registry_creation(self):
        """Test creating an empty AgentRegistry."""
        from core.adapters.registry import AgentRegistry

        registry = AgentRegistry()
        assert len(registry) == 0

    def test_registry_register_agent(self):
        """Test registering an agent."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class MockAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="mock_agent",
                    description="Mock",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        agent = MockAgent()

        registry.register(agent)

        assert len(registry) == 1
        assert "mock_agent" in registry

    def test_registry_get_agent_by_name(self):
        """Test getting an agent by name."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class TestAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="test_agent",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CREWAI,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        agent = TestAgent()
        registry.register(agent)

        retrieved = registry.get("test_agent")

        assert retrieved is agent

    def test_registry_get_agent_not_found(self):
        """Test getting a non-existent agent returns None."""
        from core.adapters.registry import AgentRegistry

        registry = AgentRegistry()

        result = registry.get("nonexistent")

        assert result is None

    def test_registry_list_agents(self):
        """Test listing all registered agents."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class Agent1(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="agent1",
                    description="First",
                    version="1.0",
                    framework=AgentFramework.CREWAI,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        class Agent2(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="agent2", description="Second", version="2.0", framework=AgentFramework.ADK
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        registry.register(Agent1())
        registry.register(Agent2())

        cards = registry.list_agents()

        assert len(cards) == 2
        names = {c.name for c in cards}
        assert "agent1" in names
        assert "agent2" in names

    def test_registry_unregister(self):
        """Test unregistering an agent."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class TempAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="temp", description="", version="1.0", framework=AgentFramework.CUSTOM
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        registry.register(TempAgent())

        assert "temp" in registry

        registry.unregister("temp")

        assert "temp" not in registry
        assert len(registry) == 0

    def test_registry_unregister_nonexistent(self):
        """Test unregistering a non-existent agent does not raise."""
        from core.adapters.registry import AgentRegistry

        registry = AgentRegistry()

        # Should not raise
        registry.unregister("does_not_exist")

    def test_registry_find_by_framework(self):
        """Test finding agents by framework."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class CrewAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="crew1", description="", version="1.0", framework=AgentFramework.CREWAI
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        class LangAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="lang1", description="", version="1.0", framework=AgentFramework.LANGCHAIN
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        registry.register(CrewAgent())
        registry.register(LangAgent())

        crew_agents = registry.find_by_framework(AgentFramework.CREWAI)
        lang_agents = registry.find_by_framework(AgentFramework.LANGCHAIN)
        adk_agents = registry.find_by_framework(AgentFramework.ADK)

        assert len(crew_agents) == 1
        assert len(lang_agents) == 1
        assert len(adk_agents) == 0

    def test_registry_find_by_capability(self):
        """Test finding agents by capability name."""
        from core.adapters.protocol import (
            AgentCapability,
            AgentCard,
            AgentFramework,
            AgentResult,
            UniversalAgent,
        )
        from core.adapters.registry import AgentRegistry

        class SearchAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="searcher",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                    capabilities=[
                        AgentCapability(name="search", description="Search capability"),
                        AgentCapability(name="analyze", description="Analyze capability"),
                    ],
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        class WriteAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="writer",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                    capabilities=[AgentCapability(name="write", description="Write capability")],
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        registry.register(SearchAgent())
        registry.register(WriteAgent())

        search_agents = registry.find_by_capability("search")
        write_agents = registry.find_by_capability("write")
        analyze_agents = registry.find_by_capability("analyze")
        missing_agents = registry.find_by_capability("nonexistent")

        assert len(search_agents) == 1
        assert len(write_agents) == 1
        assert len(analyze_agents) == 1
        assert len(missing_agents) == 0

    def test_registry_clear(self):
        """Test clearing all agents from registry."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class DummyAgent(UniversalAgent):
            def __init__(self, name):
                self._name = name

            def get_card(self):
                return AgentCard(
                    name=self._name, description="", version="1.0", framework=AgentFramework.CUSTOM
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        registry.register(DummyAgent("a1"))
        registry.register(DummyAgent("a2"))
        registry.register(DummyAgent("a3"))

        assert len(registry) == 3

        registry.clear()

        assert len(registry) == 0

    def test_registry_contains(self):
        """Test __contains__ method."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import AgentRegistry

        class ContainedAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="contained", description="", version="1.0", framework=AgentFramework.CUSTOM
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        registry = AgentRegistry()
        registry.register(ContainedAgent())

        assert "contained" in registry
        assert "not_contained" not in registry

@pytest.mark.unit
class TestGlobalRegistryFunctions:
    """Tests for global registry convenience functions."""

    def test_get_registry_returns_singleton(self):
        """Test that get_registry returns singleton instance."""
        import core.adapters.registry as registry_module

        # Reset global registry
        registry_module._registry = None

        from core.adapters.registry import get_registry

        r1 = get_registry()
        r2 = get_registry()

        assert r1 is r2

    def test_register_agent_function(self):
        """Test register_agent convenience function."""
        import core.adapters.registry as registry_module
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import get_registry, register_agent

        # Reset
        registry_module._registry = None

        class GlobalAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="global_agent",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        agent = GlobalAgent()
        register_agent(agent)

        assert "global_agent" in get_registry()

    def test_get_agent_function(self):
        """Test get_agent convenience function."""
        import core.adapters.registry as registry_module
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import get_agent, register_agent

        # Reset
        registry_module._registry = None

        class RetrievableAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="retrievable",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        agent = RetrievableAgent()
        register_agent(agent)

        retrieved = get_agent("retrievable")
        missing = get_agent("missing")

        assert retrieved is agent
        assert missing is None

    def test_list_agents_function(self):
        """Test list_agents convenience function."""
        import core.adapters.registry as registry_module
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import list_agents, register_agent

        # Reset
        registry_module._registry = None

        class ListedAgent1(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="listed1", description="", version="1.0", framework=AgentFramework.CUSTOM
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        class ListedAgent2(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="listed2", description="", version="1.0", framework=AgentFramework.CUSTOM
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        register_agent(ListedAgent1())
        register_agent(ListedAgent2())

        cards = list_agents()
        names = {c.name for c in cards}

        assert len(cards) == 2
        assert "listed1" in names
        assert "listed2" in names

    def test_unregister_agent_function(self):
        """Test unregister_agent convenience function."""
        import core.adapters.registry as registry_module
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent
        from core.adapters.registry import get_registry, register_agent, unregister_agent

        # Reset
        registry_module._registry = None

        class UnregisterableAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="unregisterable",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        register_agent(UnregisterableAgent())
        assert "unregisterable" in get_registry()

        unregister_agent("unregisterable")
        assert "unregisterable" not in get_registry()
