"""Unit tests for adapter protocol (UniversalAgent interface)."""

import pytest

@pytest.mark.unit
class TestAgentFramework:
    """Tests for AgentFramework enum."""

    def test_agent_framework_values(self):
        """Test all framework enum values exist."""
        from core.adapters.protocol import AgentFramework

        assert AgentFramework.CREWAI.value == "crewai"
        assert AgentFramework.LANGCHAIN.value == "langchain"
        assert AgentFramework.ADK.value == "adk"
        assert AgentFramework.A2A.value == "a2a"
        assert AgentFramework.CUSTOM.value == "custom"

@pytest.mark.unit
class TestAgentCapability:
    """Tests for AgentCapability model."""

    def test_agent_capability_creation(self):
        """Test creating an AgentCapability."""
        from core.adapters.protocol import AgentCapability

        cap = AgentCapability(
            name="search",
            description="Search the web",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            output_schema={"type": "string"},
        )

        assert cap.name == "search"
        assert cap.description == "Search the web"
        assert cap.input_schema["type"] == "object"
        assert cap.output_schema["type"] == "string"

    def test_agent_capability_defaults(self):
        """Test AgentCapability with default values."""
        from core.adapters.protocol import AgentCapability

        cap = AgentCapability(name="simple", description="Simple capability")

        assert cap.name == "simple"
        assert cap.input_schema == {}
        assert cap.output_schema == {}

@pytest.mark.unit
class TestAgentCard:
    """Tests for AgentCard model."""

    def test_agent_card_creation(self):
        """Test creating an AgentCard with all fields."""
        from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework

        cap = AgentCapability(name="tool1", description="Tool 1")
        card = AgentCard(
            name="test_agent",
            description="A test agent",
            version="1.0.0",
            capabilities=[cap],
            framework=AgentFramework.CREWAI,
            endpoint="http://localhost:8080",
            metadata={"author": "test"},
        )

        assert card.name == "test_agent"
        assert card.description == "A test agent"
        assert card.version == "1.0.0"
        assert len(card.capabilities) == 1
        assert card.framework == AgentFramework.CREWAI
        assert card.endpoint == "http://localhost:8080"
        assert card.metadata["author"] == "test"

    def test_agent_card_defaults(self):
        """Test AgentCard with default values."""
        from core.adapters.protocol import AgentCard, AgentFramework

        card = AgentCard(
            name="minimal", description="Minimal agent", version="1.0", framework=AgentFramework.ADK
        )

        assert card.capabilities == []
        assert card.endpoint is None
        assert card.metadata == {}

@pytest.mark.unit
class TestAgentResult:
    """Tests for AgentResult model."""

    def test_agent_result_success(self):
        """Test creating a successful AgentResult."""
        from core.adapters.protocol import AgentResult

        result = AgentResult(result={"answer": "42"}, status="ok", metadata={"time_ms": 100})

        assert result.result == {"answer": "42"}
        assert result.status == "ok"
        assert result.error is None
        assert result.metadata["time_ms"] == 100

    def test_agent_result_error(self):
        """Test creating an error AgentResult."""
        from core.adapters.protocol import AgentResult

        result = AgentResult(
            result=None, status="error", error="Connection timeout", metadata={"retry_count": 3}
        )

        assert result.result is None
        assert result.status == "error"
        assert result.error == "Connection timeout"

@pytest.mark.unit
class TestUniversalAgent:
    """Tests for UniversalAgent abstract base class."""

    def test_universal_agent_is_abstract(self):
        """Test that UniversalAgent cannot be instantiated directly."""
        from core.adapters.protocol import UniversalAgent

        with pytest.raises(TypeError):
            UniversalAgent()

    def test_universal_agent_required_methods(self):
        """Test that UniversalAgent defines required abstract methods."""
        import inspect
        from abc import ABC

        from core.adapters.protocol import UniversalAgent

        # Check it's an ABC
        assert issubclass(UniversalAgent, ABC)

        # Check abstract methods exist
        abstract_methods = {
            name
            for name, method in inspect.getmembers(UniversalAgent)
            if getattr(method, "__isabstractmethod__", False)
        }

        assert "get_card" in abstract_methods
        assert "execute" in abstract_methods
        assert "get_tools" in abstract_methods

    def test_concrete_adapter_implements_protocol(self):
        """Test that a concrete implementation can be created."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent

        class ConcreteAgent(UniversalAgent):
            def get_card(self) -> AgentCard:
                return AgentCard(
                    name="concrete",
                    description="Concrete agent",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                )

            async def execute(self, task, context=None) -> AgentResult:
                return AgentResult(result=f"Executed: {task}", status="ok")

            def get_tools(self):
                return []

        agent = ConcreteAgent()
        card = agent.get_card()

        assert card.name == "concrete"
        assert card.framework == AgentFramework.CUSTOM
        assert agent.get_tools() == []

    def test_supports_streaming_default(self):
        """Test that supports_streaming defaults to False."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent

        class BasicAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="basic", description="", version="1.0", framework=AgentFramework.CUSTOM
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        agent = BasicAgent()
        assert agent.supports_streaming() is False

    @pytest.mark.asyncio
    async def test_execute_stream_raises_not_implemented(self):
        """Test that execute_stream raises NotImplementedError by default."""
        from core.adapters.protocol import AgentCard, AgentFramework, AgentResult, UniversalAgent

        class NonStreamingAgent(UniversalAgent):
            def get_card(self):
                return AgentCard(
                    name="non_streaming",
                    description="",
                    version="1.0",
                    framework=AgentFramework.CUSTOM,
                )

            async def execute(self, task, context=None):
                return AgentResult(result="", status="ok")

            def get_tools(self):
                return []

        agent = NonStreamingAgent()

        with pytest.raises(NotImplementedError, match="does not support streaming"):
            await agent.execute_stream("task")

@pytest.mark.unit
class TestAgentExecutionError:
    """Tests for AgentExecutionError exception."""

    def test_agent_execution_error_creation(self):
        """Test creating an AgentExecutionError."""
        from core.adapters.protocol import AgentExecutionError

        error = AgentExecutionError(
            message="Task failed", agent_name="test_agent", details={"code": 500}
        )

        assert error.agent_name == "test_agent"
        assert error.details == {"code": 500}
        assert "[test_agent] Task failed" in str(error)

    def test_agent_execution_error_default_details(self):
        """Test AgentExecutionError with default details."""
        from core.adapters.protocol import AgentExecutionError

        error = AgentExecutionError("Failed", "my_agent")

        assert error.details == {}
        assert error.agent_name == "my_agent"
