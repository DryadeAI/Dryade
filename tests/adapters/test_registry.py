"""
AgentRegistry unit tests.

Comprehensive tests for registry operations including:
- Register, get, unregister agents
- List and filter by framework/capability
- Clear and isolation verification
- Duplicate registration handling
"""

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)
from core.adapters.registry import (
    get_agent,
    get_registry,
    list_agents,
    register_agent,
    unregister_agent,
)

# =============================================================================
# Mock Adapter for Registry Testing
# =============================================================================

class MockAgentForRegistry(UniversalAgent):
    """Mock agent implementation for registry testing."""

    def __init__(
        self,
        name: str,
        framework: AgentFramework = AgentFramework.CUSTOM,
        capabilities: list[AgentCapability] | None = None,
    ):
        self._name = name
        self._framework = framework
        self._capabilities = capabilities or []

    def get_card(self) -> AgentCard:
        """Return agent's capability card."""
        return AgentCard(
            name=self._name,
            description=f"Mock agent: {self._name}",
            version="1.0",
            framework=self._framework,
            capabilities=self._capabilities,
            metadata={"mock": True},
        )

    async def execute(self, task: str, context: dict | None = None) -> AgentResult:
        """Execute task (mock implementation)."""
        return AgentResult(
            result=f"Mock result from {self._name}",
            status="ok",
            metadata={"framework": self._framework.value},
        )

    def get_tools(self) -> list[dict]:
        """Return available tools."""
        return []

# =============================================================================
# Registry Unit Tests
# =============================================================================

class TestAgentRegistry:
    """Unit tests for AgentRegistry class."""

    def test_registry_register(self, isolated_registry):
        """Test registering an agent stores it correctly."""
        agent = MockAgentForRegistry(name="test_agent")

        isolated_registry.register(agent)

        # Verify agent is stored
        assert "test_agent" in isolated_registry
        assert len(isolated_registry) == 1

    def test_registry_get(self, isolated_registry):
        """Test registering and retrieving an agent by name."""
        agent = MockAgentForRegistry(name="retrieval_agent")

        isolated_registry.register(agent)
        retrieved = isolated_registry.get("retrieval_agent")

        # Verify correct agent retrieved
        assert retrieved is not None
        assert retrieved is agent
        assert retrieved.get_card().name == "retrieval_agent"

        # Verify non-existent agent returns None
        assert isolated_registry.get("nonexistent") is None

    def test_registry_unregister(self, isolated_registry):
        """Test registering, unregistering, and verifying removal."""
        agent = MockAgentForRegistry(name="removable_agent")

        # Register
        isolated_registry.register(agent)
        assert "removable_agent" in isolated_registry

        # Unregister
        isolated_registry.unregister("removable_agent")

        # Verify removed
        assert "removable_agent" not in isolated_registry
        assert isolated_registry.get("removable_agent") is None
        assert len(isolated_registry) == 0

        # Unregistering non-existent should not raise
        isolated_registry.unregister("nonexistent")  # Should not raise

    def test_registry_list_agents(self, isolated_registry):
        """Test registering multiple agents and listing all."""
        agent1 = MockAgentForRegistry(name="agent_1", framework=AgentFramework.CREWAI)
        agent2 = MockAgentForRegistry(name="agent_2", framework=AgentFramework.LANGCHAIN)
        agent3 = MockAgentForRegistry(name="agent_3", framework=AgentFramework.A2A)

        isolated_registry.register(agent1)
        isolated_registry.register(agent2)
        isolated_registry.register(agent3)

        agents_list = isolated_registry.list_agents()

        # Verify all agents listed
        assert len(agents_list) == 3
        agent_names = [card.name for card in agents_list]
        assert "agent_1" in agent_names
        assert "agent_2" in agent_names
        assert "agent_3" in agent_names

        # Verify cards are AgentCard instances
        for card in agents_list:
            assert isinstance(card, AgentCard)

    def test_registry_find_by_framework(self, isolated_registry):
        """Test registering mixed frameworks and filtering by framework."""
        crewai_agent_1 = MockAgentForRegistry(name="crew_1", framework=AgentFramework.CREWAI)
        crewai_agent_2 = MockAgentForRegistry(name="crew_2", framework=AgentFramework.CREWAI)
        langchain_agent = MockAgentForRegistry(name="lang_1", framework=AgentFramework.LANGCHAIN)
        a2a_agent = MockAgentForRegistry(name="a2a_1", framework=AgentFramework.A2A)

        isolated_registry.register(crewai_agent_1)
        isolated_registry.register(crewai_agent_2)
        isolated_registry.register(langchain_agent)
        isolated_registry.register(a2a_agent)

        # Find CrewAI agents
        crewai_agents = isolated_registry.find_by_framework(AgentFramework.CREWAI)
        assert len(crewai_agents) == 2
        crewai_names = [a.get_card().name for a in crewai_agents]
        assert "crew_1" in crewai_names
        assert "crew_2" in crewai_names

        # Find LangChain agents
        langchain_agents = isolated_registry.find_by_framework(AgentFramework.LANGCHAIN)
        assert len(langchain_agents) == 1
        assert langchain_agents[0].get_card().name == "lang_1"

        # Find A2A agents
        a2a_agents = isolated_registry.find_by_framework(AgentFramework.A2A)
        assert len(a2a_agents) == 1
        assert a2a_agents[0].get_card().name == "a2a_1"

        # Find ADK agents (none registered)
        adk_agents = isolated_registry.find_by_framework(AgentFramework.ADK)
        assert len(adk_agents) == 0

    def test_registry_find_by_capability(self, isolated_registry):
        """Test registering agents with capabilities and searching by capability."""
        # Create capability
        search_cap = AgentCapability(
            name="search",
            description="Search capability",
            input_schema={"query": "string"},
            output_schema={"results": "array"},
        )
        analysis_cap = AgentCapability(
            name="analysis",
            description="Analysis capability",
            input_schema={"data": "string"},
            output_schema={"insights": "array"},
        )

        # Create agents with different capabilities
        search_agent = MockAgentForRegistry(
            name="searcher",
            framework=AgentFramework.CREWAI,
            capabilities=[search_cap],
        )
        analyzer_agent = MockAgentForRegistry(
            name="analyzer",
            framework=AgentFramework.LANGCHAIN,
            capabilities=[analysis_cap],
        )
        multi_agent = MockAgentForRegistry(
            name="multi_capable",
            framework=AgentFramework.A2A,
            capabilities=[search_cap, analysis_cap],
        )

        isolated_registry.register(search_agent)
        isolated_registry.register(analyzer_agent)
        isolated_registry.register(multi_agent)

        # Find agents with search capability
        search_agents = isolated_registry.find_by_capability("search")
        assert len(search_agents) == 2
        search_names = [a.get_card().name for a in search_agents]
        assert "searcher" in search_names
        assert "multi_capable" in search_names

        # Find agents with analysis capability
        analysis_agents = isolated_registry.find_by_capability("analysis")
        assert len(analysis_agents) == 2
        analysis_names = [a.get_card().name for a in analysis_agents]
        assert "analyzer" in analysis_names
        assert "multi_capable" in analysis_names

        # Find agents with nonexistent capability
        nonexistent_agents = isolated_registry.find_by_capability("nonexistent")
        assert len(nonexistent_agents) == 0

    def test_registry_clear(self, isolated_registry):
        """Test registering multiple agents, clearing, and verifying empty."""
        agent1 = MockAgentForRegistry(name="agent_1")
        agent2 = MockAgentForRegistry(name="agent_2")
        agent3 = MockAgentForRegistry(name="agent_3")

        isolated_registry.register(agent1)
        isolated_registry.register(agent2)
        isolated_registry.register(agent3)

        assert len(isolated_registry) == 3

        # Clear registry
        isolated_registry.clear()

        # Verify empty
        assert len(isolated_registry) == 0
        assert isolated_registry.list_agents() == []
        assert isolated_registry.get("agent_1") is None

    def test_registry_isolation(self, isolated_registry, mock_registry):
        """Test that mock_registry fixture provides isolation from isolated_registry."""
        # This test verifies no state leakage between registry instances

        agent1 = MockAgentForRegistry(name="isolated_agent")
        agent2 = MockAgentForRegistry(name="mock_agent")

        # Register in different registries
        isolated_registry.register(agent1)
        mock_registry.register(agent2)

        # Verify isolation
        assert "isolated_agent" in isolated_registry
        assert "mock_agent" not in isolated_registry

        assert "mock_agent" in mock_registry
        assert "isolated_agent" not in mock_registry

        # Verify lengths
        assert len(isolated_registry) == 1
        assert len(mock_registry) == 1

    def test_registry_duplicate_registration(self, isolated_registry):
        """Test registering same name twice overwrites the previous agent."""
        agent_v1 = MockAgentForRegistry(name="duplicate_agent", framework=AgentFramework.CREWAI)
        agent_v2 = MockAgentForRegistry(name="duplicate_agent", framework=AgentFramework.LANGCHAIN)

        # Register first version
        isolated_registry.register(agent_v1)
        assert len(isolated_registry) == 1
        retrieved_v1 = isolated_registry.get("duplicate_agent")
        assert retrieved_v1.get_card().framework == AgentFramework.CREWAI

        # Register second version with same name (overwrites)
        isolated_registry.register(agent_v2)

        # Verify overwritten, not duplicated
        assert len(isolated_registry) == 1
        retrieved_v2 = isolated_registry.get("duplicate_agent")
        assert retrieved_v2.get_card().framework == AgentFramework.LANGCHAIN
        assert retrieved_v2 is agent_v2

class TestGlobalRegistryFunctions:
    """Tests for global registry convenience functions."""

    def test_get_registry_singleton(self):
        """Test get_registry returns singleton instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        # Both should be same instance
        assert registry1 is registry2

    def test_register_and_get_agent(self):
        """Test register_agent and get_agent convenience functions."""
        agent = MockAgentForRegistry(name="global_test_agent")

        register_agent(agent)
        retrieved = get_agent("global_test_agent")

        assert retrieved is not None
        assert retrieved is agent

        # Cleanup (autouse fixture will also clear)
        unregister_agent("global_test_agent")

    def test_list_agents_function(self):
        """Test list_agents convenience function."""
        agent1 = MockAgentForRegistry(name="list_agent_1")
        agent2 = MockAgentForRegistry(name="list_agent_2")

        register_agent(agent1)
        register_agent(agent2)

        agents = list_agents()
        agent_names = [card.name for card in agents]

        assert "list_agent_1" in agent_names
        assert "list_agent_2" in agent_names

        # Cleanup
        unregister_agent("list_agent_1")
        unregister_agent("list_agent_2")

    def test_unregister_agent_function(self):
        """Test unregister_agent convenience function."""
        agent = MockAgentForRegistry(name="unregister_test_agent")

        register_agent(agent)
        assert get_agent("unregister_test_agent") is not None

        unregister_agent("unregister_test_agent")
        assert get_agent("unregister_test_agent") is None

# =============================================================================
# Registry Edge Cases and Advanced Scenarios
# =============================================================================

class TestRegistryEdgeCases:
    """Test registry edge cases and advanced scenarios."""

    def test_registry_duplicate_name_different_framework(self, isolated_registry):
        """Test registering agents with same name but different frameworks."""
        agent1 = MockAgentForRegistry(name="duplicate", framework=AgentFramework.CREWAI)
        agent2 = MockAgentForRegistry(name="duplicate", framework=AgentFramework.LANGCHAIN)

        isolated_registry.register(agent1)
        isolated_registry.register(agent2)

        # Should overwrite - only one agent with that name
        assert len(isolated_registry) == 1
        retrieved = isolated_registry.get("duplicate")
        # Should have the second agent (last registered)
        assert retrieved.get_card().framework == AgentFramework.LANGCHAIN

    def test_registry_case_sensitive_names(self, isolated_registry):
        """Test that agent names are case-sensitive."""
        agent_lower = MockAgentForRegistry(name="myagent")
        agent_upper = MockAgentForRegistry(name="MyAgent")
        agent_mixed = MockAgentForRegistry(name="myAgent")

        isolated_registry.register(agent_lower)
        isolated_registry.register(agent_upper)
        isolated_registry.register(agent_mixed)

        # All three should be different entries
        assert len(isolated_registry) == 3
        assert isolated_registry.get("myagent") is not None
        assert isolated_registry.get("MyAgent") is not None
        assert isolated_registry.get("myAgent") is not None
        assert isolated_registry.get("MYAGENT") is None

    def test_registry_special_characters_in_name(self, isolated_registry):
        """Test agent names with special characters."""
        special_names = [
            "agent-with-dashes",
            "agent_with_underscores",
            "agent.with.dots",
            "agent:with:colons",
            "agent/with/slashes",
        ]

        for name in special_names:
            agent = MockAgentForRegistry(name=name)
            isolated_registry.register(agent)

        assert len(isolated_registry) == len(special_names)

        for name in special_names:
            retrieved = isolated_registry.get(name)
            assert retrieved is not None
            assert retrieved.get_card().name == name

    def test_registry_empty_name(self, isolated_registry):
        """Test registering agent with empty name."""
        agent = MockAgentForRegistry(name="")

        isolated_registry.register(agent)

        assert len(isolated_registry) == 1
        retrieved = isolated_registry.get("")
        assert retrieved is not None

    def test_registry_unicode_names(self, isolated_registry):
        """Test agent names with unicode characters."""
        unicode_names = [
            "agent_日本語",
            "агент_русский",
            "agent_العربية",
            "agent_emoji_🤖",
        ]

        for name in unicode_names:
            agent = MockAgentForRegistry(name=name)
            isolated_registry.register(agent)

        assert len(isolated_registry) == len(unicode_names)

        for name in unicode_names:
            retrieved = isolated_registry.get(name)
            assert retrieved is not None

    def test_registry_find_by_framework_all_types(self, isolated_registry):
        """Test finding agents by all framework types."""
        frameworks = [
            AgentFramework.CREWAI,
            AgentFramework.LANGCHAIN,
            AgentFramework.A2A,
            AgentFramework.ADK,
            AgentFramework.CUSTOM,
        ]

        for idx, framework in enumerate(frameworks):
            agent = MockAgentForRegistry(name=f"agent_{idx}", framework=framework)
            isolated_registry.register(agent)

        # Verify each framework can be found
        for framework in frameworks:
            agents = isolated_registry.find_by_framework(framework)
            assert len(agents) == 1
            assert agents[0].get_card().framework == framework

    def test_registry_find_by_capability_partial_match(self, isolated_registry):
        """Test finding agents by capability with partial name matching."""
        search_cap = AgentCapability(
            name="advanced_search",
            description="Advanced search",
            input_schema={},
            output_schema={},
        )

        basic_search_cap = AgentCapability(
            name="search",
            description="Basic search",
            input_schema={},
            output_schema={},
        )

        agent1 = MockAgentForRegistry(name="agent1", capabilities=[search_cap])
        agent2 = MockAgentForRegistry(name="agent2", capabilities=[basic_search_cap])

        isolated_registry.register(agent1)
        isolated_registry.register(agent2)

        # Exact match only - no partial matching
        advanced_agents = isolated_registry.find_by_capability("advanced_search")
        assert len(advanced_agents) == 1

        search_agents = isolated_registry.find_by_capability("search")
        assert len(search_agents) == 1

    def test_registry_multiple_capabilities_same_agent(self, isolated_registry):
        """Test agent with many capabilities can be found by any."""
        caps = [
            AgentCapability(
                name=f"capability_{i}", description=f"Cap {i}", input_schema={}, output_schema={}
            )
            for i in range(10)
        ]

        multi_cap_agent = MockAgentForRegistry(name="swiss_army_agent", capabilities=caps)
        isolated_registry.register(multi_cap_agent)

        # Should find agent by any of its capabilities
        for cap in caps:
            agents = isolated_registry.find_by_capability(cap.name)
            assert len(agents) == 1
            assert agents[0].get_card().name == "swiss_army_agent"

    def test_registry_concurrent_registration(self, isolated_registry):
        """Test that registry handles sequential registrations correctly."""
        # Simulate concurrent-like behavior with sequential ops
        agents = [MockAgentForRegistry(name=f"agent_{i}") for i in range(100)]

        for agent in agents:
            isolated_registry.register(agent)

        assert len(isolated_registry) == 100

        # Verify all can be retrieved
        for i in range(100):
            retrieved = isolated_registry.get(f"agent_{i}")
            assert retrieved is not None

    def test_registry_list_agents_order(self, isolated_registry):
        """Test that list_agents returns consistent results."""
        agent1 = MockAgentForRegistry(name="aaa_first")
        agent2 = MockAgentForRegistry(name="zzz_last")
        agent3 = MockAgentForRegistry(name="mmm_middle")

        isolated_registry.register(agent2)
        isolated_registry.register(agent1)
        isolated_registry.register(agent3)

        agents = isolated_registry.list_agents()
        names = [card.name for card in agents]

        # All should be present
        assert "aaa_first" in names
        assert "zzz_last" in names
        assert "mmm_middle" in names
        assert len(names) == 3

    def test_registry_get_nonexistent_returns_none(self, isolated_registry):
        """Test getting nonexistent agent returns None, not exception."""
        result = isolated_registry.get("does_not_exist")
        assert result is None

        # Even with special characters
        result = isolated_registry.get("!@#$%^&*()")
        assert result is None

    def test_registry_unregister_nonexistent_no_error(self, isolated_registry):
        """Test unregistering nonexistent agent doesn't raise error."""
        # Should not raise
        isolated_registry.unregister("does_not_exist")
        isolated_registry.unregister("another_nonexistent")

        assert len(isolated_registry) == 0

    def test_registry_clear_idempotent(self, isolated_registry):
        """Test clearing empty registry is safe."""
        # Clear empty registry
        isolated_registry.clear()
        assert len(isolated_registry) == 0

        # Add agents and clear
        agent = MockAgentForRegistry(name="test")
        isolated_registry.register(agent)
        isolated_registry.clear()
        assert len(isolated_registry) == 0

        # Clear again - should be safe
        isolated_registry.clear()
        assert len(isolated_registry) == 0

    def test_registry_framework_enum_coverage(self, isolated_registry):
        """Test all AgentFramework enum values work with registry."""
        # Test that registry can handle all framework types
        for framework in AgentFramework:
            agent = MockAgentForRegistry(name=f"agent_{framework.value}", framework=framework)
            isolated_registry.register(agent)

        # Should have one agent per framework type
        assert len(isolated_registry) >= len(AgentFramework)

        # Each framework should be findable
        for framework in AgentFramework:
            agents = isolated_registry.find_by_framework(framework)
            assert len(agents) >= 1
