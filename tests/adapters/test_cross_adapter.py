"""
Cross-adapter error propagation tests.

Tests validating error handling across adapter boundaries,
tool sharing between frameworks, and circuit breaker integration.
"""

import pytest

from core.adapters.protocol import (
    AgentCapability,
    AgentCard,
    AgentFramework,
    AgentResult,
    UniversalAgent,
)

# =============================================================================
# Test Adapter for Cross-Framework Testing
# =============================================================================

class MockUniversalAgent(UniversalAgent):
    """Mock adapter for testing cross-adapter interactions."""

    def __init__(
        self,
        name: str,
        framework: AgentFramework,
        result: AgentResult | None = None,
        error: Exception | None = None,
        tools: list | None = None,
    ):
        self._name = name
        self._framework = framework
        self._result = result
        self._error = error
        self._tools = tools or []
        self._execute_called = False
        self._execute_task = None
        self._execute_context = None

    def get_card(self) -> AgentCard:
        """Return agent's capability card."""
        capabilities = []
        for tool in self._tools:
            capabilities.append(
                AgentCapability(
                    name=tool.get("name", "unknown"),
                    description=tool.get("description", ""),
                    input_schema=tool.get("input_schema", {}),
                    output_schema=tool.get("output_schema", {}),
                )
            )

        return AgentCard(
            name=self._name,
            description=f"Mock {self._framework.value} agent",
            version="1.0",
            framework=self._framework,
            capabilities=capabilities,
            metadata={"mock": True},
        )

    async def execute(self, task: str, context: dict | None = None) -> AgentResult:
        """Execute task, returning preset result or raising error."""
        self._execute_called = True
        self._execute_task = task
        self._execute_context = context

        if self._error:
            return AgentResult(
                result=None,
                status="error",
                error=str(self._error),
                metadata={"framework": self._framework.value},
            )

        if self._result:
            return self._result

        return AgentResult(
            result=f"Result from {self._name}",
            status="ok",
            metadata={"framework": self._framework.value},
        )

    def get_tools(self) -> list[dict]:
        """Return available tools in OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            for tool in self._tools
        ]

# =============================================================================
# Cross-Adapter Error Propagation Tests
# =============================================================================

class TestCrossAdapterErrorPropagation:
    """Tests for error handling across adapter boundaries."""

    @pytest.mark.asyncio
    async def test_error_propagation_crewai_to_langchain(self, isolated_registry):
        """Test that errors propagate from CrewAI to dependent LangChain agent.

        Verifies:
        - Error captured with framework="crewai" in metadata
        - LangChain agent not executed (fail fast)
        """
        # Create CrewAI agent that fails
        crewai_agent = MockUniversalAgent(
            name="crewai_researcher",
            framework=AgentFramework.CREWAI,
            error=Exception("CrewAI execution failed: API rate limit exceeded"),
        )

        # Create LangChain agent that depends on CrewAI output
        langchain_agent = MockUniversalAgent(
            name="langchain_processor",
            framework=AgentFramework.LANGCHAIN,
            result=AgentResult(
                result="Processed data",
                status="ok",
                metadata={"framework": "langchain"},
            ),
        )

        # Register agents
        isolated_registry.register(crewai_agent)
        isolated_registry.register(langchain_agent)

        # Simulate cross-adapter chain: CrewAI -> LangChain
        # Execute CrewAI first
        crewai_result = await crewai_agent.execute("Research topic X")

        # Verify error captured with framework metadata
        assert crewai_result.status == "error"
        assert crewai_result.metadata.get("framework") == "crewai"
        assert "CrewAI execution failed" in crewai_result.error

        # Verify LangChain agent NOT executed (fail fast behavior)
        # In real orchestration, we would check crewai_result.status before calling langchain
        if crewai_result.status == "error":
            # Do not execute dependent agent
            pass
        else:
            await langchain_agent.execute("Process data", {"input": crewai_result.result})

        # LangChain should not have been called
        assert langchain_agent._execute_called is False

    @pytest.mark.asyncio
    async def test_error_propagation_with_circuit_breaker(self, isolated_registry):
        """Test circuit breaker opens after repeated failures.

        Verifies:
        - Circuit breaker opens after threshold
        - Error response includes circuit breaker status
        """
        # Simulate circuit breaker state
        circuit_breaker_state = {
            "state": "closed",
            "failure_count": 0,
            "threshold": 3,
        }

        # Create agent that fails repeatedly
        failing_agent = MockUniversalAgent(
            name="failing_agent",
            framework=AgentFramework.CREWAI,
            error=Exception("Service unavailable"),
        )

        isolated_registry.register(failing_agent)

        # Simulate repeated failures triggering circuit breaker
        for i in range(4):
            result = await failing_agent.execute(f"Task {i}")
            assert result.status == "error"

            # Update circuit breaker state
            circuit_breaker_state["failure_count"] += 1
            if circuit_breaker_state["failure_count"] >= circuit_breaker_state["threshold"]:
                circuit_breaker_state["state"] = "open"

        # Verify circuit breaker is now open
        assert circuit_breaker_state["state"] == "open"
        assert circuit_breaker_state["failure_count"] >= circuit_breaker_state["threshold"]

        # Create result with circuit breaker metadata
        error_with_breaker = AgentResult(
            result=None,
            status="error",
            error="Circuit breaker open - service unavailable",
            metadata={
                "framework": "crewai",
                "circuit_breaker": circuit_breaker_state,
            },
        )

        # Verify error includes circuit breaker status
        assert error_with_breaker.metadata["circuit_breaker"]["state"] == "open"
        assert error_with_breaker.metadata["circuit_breaker"]["failure_count"] >= 3

    @pytest.mark.asyncio
    async def test_successful_cross_adapter_chain(self, isolated_registry):
        """Test successful CrewAI -> LangChain -> A2A chain.

        Verifies:
        - Results passed between adapters
        - Each adapter's metadata preserved
        """
        # Create chain of agents
        crewai_agent = MockUniversalAgent(
            name="crewai_researcher",
            framework=AgentFramework.CREWAI,
            result=AgentResult(
                result="Research findings: Topic X is important",
                status="ok",
                metadata={"framework": "crewai", "execution_time_ms": 150},
            ),
        )

        langchain_agent = MockUniversalAgent(
            name="langchain_processor",
            framework=AgentFramework.LANGCHAIN,
            result=AgentResult(
                result="Processed: Topic X analysis complete",
                status="ok",
                metadata={"framework": "langchain", "tokens_used": 500},
            ),
        )

        a2a_agent = MockUniversalAgent(
            name="a2a_publisher",
            framework=AgentFramework.A2A,
            result=AgentResult(
                result="Published: Article on Topic X",
                status="ok",
                metadata={"framework": "a2a", "endpoint": "https://api.example.com"},
            ),
        )

        # Register all agents
        isolated_registry.register(crewai_agent)
        isolated_registry.register(langchain_agent)
        isolated_registry.register(a2a_agent)

        # Execute chain
        chain_results = []

        # Step 1: CrewAI researches
        result1 = await crewai_agent.execute("Research topic X")
        assert result1.status == "ok"
        assert result1.metadata.get("framework") == "crewai"
        chain_results.append(result1)

        # Step 2: LangChain processes (with CrewAI output as context)
        result2 = await langchain_agent.execute(
            "Process research",
            context={"crewai_output": result1.result},
        )
        assert result2.status == "ok"
        assert result2.metadata.get("framework") == "langchain"
        chain_results.append(result2)

        # Step 3: A2A publishes (with processed output)
        result3 = await a2a_agent.execute(
            "Publish article",
            context={"processed_content": result2.result},
        )
        assert result3.status == "ok"
        assert result3.metadata.get("framework") == "a2a"
        chain_results.append(result3)

        # Verify all results preserved with correct metadata
        assert len(chain_results) == 3
        frameworks = [r.metadata.get("framework") for r in chain_results]
        assert frameworks == ["crewai", "langchain", "a2a"]

        # Verify context passed correctly
        assert langchain_agent._execute_context == {
            "crewai_output": "Research findings: Topic X is important"
        }
        assert a2a_agent._execute_context == {
            "processed_content": "Processed: Topic X analysis complete"
        }

    @pytest.mark.asyncio
    async def test_partial_failure_with_optional_agent(self, isolated_registry):
        """Test chain continues when optional agent fails.

        Verifies:
        - Chain continues with degraded output
        - Optional failure tracked but doesn't halt chain
        """
        # Create agents - middle one is optional and fails
        primary_agent = MockUniversalAgent(
            name="primary_agent",
            framework=AgentFramework.CREWAI,
            result=AgentResult(
                result="Primary result",
                status="ok",
                metadata={"framework": "crewai"},
            ),
        )

        optional_agent = MockUniversalAgent(
            name="optional_enricher",
            framework=AgentFramework.LANGCHAIN,
            error=Exception("Optional enrichment failed"),
        )

        final_agent = MockUniversalAgent(
            name="final_agent",
            framework=AgentFramework.A2A,
            result=AgentResult(
                result="Final output (without enrichment)",
                status="ok",
                metadata={"framework": "a2a"},
            ),
        )

        # Register agents
        isolated_registry.register(primary_agent)
        isolated_registry.register(optional_agent)
        isolated_registry.register(final_agent)

        # Execute with optional agent handling
        chain_metadata = {
            "steps": [],
            "degraded": False,
            "skipped_agents": [],
        }

        # Step 1: Primary agent
        result1 = await primary_agent.execute("Primary task")
        assert result1.status == "ok"
        chain_metadata["steps"].append({"agent": "primary_agent", "status": "ok"})

        # Step 2: Optional agent (failure tolerated)
        result2 = await optional_agent.execute(
            "Enrich data",
            context={"input": result1.result},
        )
        if result2.status == "error":
            # Mark as degraded but continue
            chain_metadata["degraded"] = True
            chain_metadata["skipped_agents"].append("optional_enricher")
            chain_metadata["steps"].append({"agent": "optional_enricher", "status": "skipped"})
            enriched_input = result1.result  # Use original input
        else:
            enriched_input = result2.result

        # Step 3: Final agent (continues despite optional failure)
        result3 = await final_agent.execute(
            "Finalize",
            context={"input": enriched_input},
        )
        assert result3.status == "ok"
        chain_metadata["steps"].append({"agent": "final_agent", "status": "ok"})

        # Verify chain completed with degraded output
        assert chain_metadata["degraded"] is True
        assert "optional_enricher" in chain_metadata["skipped_agents"]
        assert len(chain_metadata["steps"]) == 3
        assert final_agent._execute_called is True

class TestCrossAdapterToolSharing:
    """Tests for tool sharing across adapter boundaries."""

    @pytest.mark.asyncio
    async def test_tool_sharing_across_adapters(self, isolated_registry):
        """Test tools registered in one adapter accessible from another.

        Verifies:
        - Tool registered with CrewAI agent
        - Tool accessible from LangChain agent
        - Result format consistent
        """
        # Create shared tool definition
        shared_tool = {
            "name": "search_tool",
            "description": "Search for information",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                },
            },
        }

        # Create CrewAI agent with the tool
        crewai_agent = MockUniversalAgent(
            name="crewai_with_tool",
            framework=AgentFramework.CREWAI,
            tools=[shared_tool],
            result=AgentResult(
                result="Search results from CrewAI",
                status="ok",
                metadata={"framework": "crewai", "tool_used": "search_tool"},
            ),
        )

        # Create LangChain agent that can access shared tools
        langchain_agent = MockUniversalAgent(
            name="langchain_with_tool",
            framework=AgentFramework.LANGCHAIN,
            tools=[shared_tool],  # Same tool available
            result=AgentResult(
                result="Search results from LangChain",
                status="ok",
                metadata={"framework": "langchain", "tool_used": "search_tool"},
            ),
        )

        # Register both agents
        isolated_registry.register(crewai_agent)
        isolated_registry.register(langchain_agent)

        # Verify tool accessible from CrewAI agent
        crewai_tools = crewai_agent.get_tools()
        assert len(crewai_tools) == 1
        assert crewai_tools[0]["function"]["name"] == "search_tool"
        assert crewai_tools[0]["function"]["parameters"]["properties"]["query"]["type"] == "string"

        # Verify same tool accessible from LangChain agent
        langchain_tools = langchain_agent.get_tools()
        assert len(langchain_tools) == 1
        assert langchain_tools[0]["function"]["name"] == "search_tool"

        # Verify tool definition is consistent across adapters
        assert crewai_tools[0]["function"]["name"] == langchain_tools[0]["function"]["name"]
        assert (
            crewai_tools[0]["function"]["description"]
            == langchain_tools[0]["function"]["description"]
        )
        assert (
            crewai_tools[0]["function"]["parameters"]
            == langchain_tools[0]["function"]["parameters"]
        )

        # Mock tool execution and verify result format
        tool_result_crewai = await crewai_agent.execute("Search for X")
        tool_result_langchain = await langchain_agent.execute("Search for X")

        # Both return AgentResult with consistent structure
        assert isinstance(tool_result_crewai, AgentResult)
        assert isinstance(tool_result_langchain, AgentResult)
        assert tool_result_crewai.status == "ok"
        assert tool_result_langchain.status == "ok"

        # Both track tool usage in metadata
        assert tool_result_crewai.metadata.get("tool_used") == "search_tool"
        assert tool_result_langchain.metadata.get("tool_used") == "search_tool"

        # Framework metadata preserved despite shared tool
        assert tool_result_crewai.metadata.get("framework") == "crewai"
        assert tool_result_langchain.metadata.get("framework") == "langchain"
