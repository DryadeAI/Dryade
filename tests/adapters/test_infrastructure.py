"""
Infrastructure smoke tests for adapter testing framework.

These tests verify that the testing infrastructure itself works correctly:
- Fixtures are importable and usable
- AsyncMock behaves correctly
- Registry isolation works between tests
- No event loop conflicts with multiple async fixtures
"""

from unittest.mock import AsyncMock

import pytest

class TestFixturesImportable:
    """Verify all fixtures can be imported without error."""

    def test_fixtures_module_imports(self):
        """Test that the fixtures module is importable."""
        from tests.adapters import fixtures

        assert fixtures is not None

    def test_crewai_fixture_importable(self):
        """Test mock_crewai_agent fixture is importable."""
        from tests.adapters.fixtures import mock_crewai_agent

        assert mock_crewai_agent is not None

    def test_langchain_fixture_importable(self):
        """Test mock_langchain_agent fixture is importable."""
        from tests.adapters.fixtures import mock_langchain_agent

        assert mock_langchain_agent is not None

    def test_a2a_fixture_importable(self):
        """Test mock_a2a_agent fixture is importable."""
        from tests.adapters.fixtures import mock_a2a_agent

        assert mock_a2a_agent is not None

    def test_registry_fixture_importable(self):
        """Test mock_registry fixture is importable."""
        from tests.adapters.fixtures import mock_registry

        assert mock_registry is not None

    def test_tool_fixture_importable(self):
        """Test mock_tool fixture is importable."""
        from tests.adapters.fixtures import mock_tool

        assert mock_tool is not None

class TestAsyncMockPattern:
    """Verify AsyncMock behaves correctly for async testing."""

    @pytest.mark.asyncio
    async def test_async_mock_is_awaitable(self):
        """Test that AsyncMock can be awaited."""
        mock = AsyncMock(return_value="test result")

        result = await mock()

        assert result == "test result"

    @pytest.mark.asyncio
    async def test_async_mock_with_arguments(self):
        """Test AsyncMock captures arguments correctly."""
        mock = AsyncMock(return_value={"status": "ok"})

        result = await mock("arg1", kwarg="value")

        mock.assert_awaited_once_with("arg1", kwarg="value")
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_langchain_mock_ainvoke(self, mock_langchain_agent):
        """Test that mock LangChain agent's ainvoke is awaitable."""
        result = await mock_langchain_agent.ainvoke({"input": "test"})

        assert "output" in result
        mock_langchain_agent.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a2a_mock_execute(self, mock_a2a_agent):
        """Test that mock A2A agent's execute is awaitable."""
        result = await mock_a2a_agent.execute("test task")

        assert result.status == "ok"
        mock_a2a_agent.execute.assert_awaited_once()

class TestRegistryIsolation:
    """Verify registry state is isolated between tests."""

    def test_registry_starts_empty_first(self, mock_registry):
        """First test: registry should be empty, then register an agent."""
        from unittest.mock import MagicMock

        from core.adapters.protocol import AgentCard, AgentFramework, UniversalAgent

        assert len(mock_registry) == 0

        # Create a mock universal agent
        mock_agent = MagicMock(spec=UniversalAgent)
        mock_agent.get_card.return_value = AgentCard(
            name="test-agent-1",
            description="Test agent",
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )

        mock_registry.register(mock_agent)
        assert len(mock_registry) == 1
        assert "test-agent-1" in mock_registry

    def test_registry_starts_empty_second(self, mock_registry):
        """Second test: registry should be empty (no state from previous test)."""
        # This test runs after test_registry_starts_empty_first
        # If isolation works, registry should be empty
        assert len(mock_registry) == 0

    def test_global_registry_cleared_first(self):
        """Test that global registry is cleared by autouse fixture."""
        from unittest.mock import MagicMock

        from core.adapters.protocol import AgentCard, AgentFramework, UniversalAgent
        from core.adapters.registry import get_registry

        registry = get_registry()
        assert len(registry) == 0

        # Register to global registry
        mock_agent = MagicMock(spec=UniversalAgent)
        mock_agent.get_card.return_value = AgentCard(
            name="global-test-agent",
            description="Test agent",
            version="1.0",
            framework=AgentFramework.CUSTOM,
        )
        registry.register(mock_agent)
        assert len(registry) == 1

    def test_global_registry_cleared_second(self):
        """Verify global registry was cleared after previous test."""
        from core.adapters.registry import get_registry

        registry = get_registry()
        # Should be empty due to autouse fixture
        assert len(registry) == 0

class TestEventLoopNoConflict:
    """Verify no event loop conflicts with multiple async operations."""

    @pytest.mark.asyncio
    async def test_multiple_async_fixtures_same_test(
        self,
        mock_langchain_agent,
        mock_a2a_agent,
        mock_tool,
    ):
        """Test using multiple async fixtures in the same test."""
        # All three fixtures should work together without event loop conflicts

        # Use langchain agent
        lc_result = await mock_langchain_agent.ainvoke({"input": "test"})
        assert "output" in lc_result

        # Use a2a agent
        a2a_result = await mock_a2a_agent.execute("test")
        assert a2a_result.status == "ok"

        # Use tool
        tool_result = await mock_tool("arg")
        assert tool_result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_sequential_async_calls(self, mock_langchain_agent):
        """Test multiple sequential async calls don't cause conflicts."""
        # Call ainvoke multiple times
        for i in range(3):
            result = await mock_langchain_agent.ainvoke({"input": f"test-{i}"})
            assert "output" in result

        assert mock_langchain_agent.ainvoke.await_count == 3

    @pytest.mark.asyncio
    async def test_async_with_sync_operations(self, mock_registry, mock_langchain_agent):
        """Test mixing async calls with sync registry operations."""
        from unittest.mock import MagicMock

        from core.adapters.protocol import AgentCard, AgentFramework, UniversalAgent

        # Async operation
        result = await mock_langchain_agent.ainvoke({"input": "test"})
        assert "output" in result

        # Sync registry operation
        mock_agent = MagicMock(spec=UniversalAgent)
        mock_agent.get_card.return_value = AgentCard(
            name="sync-test-agent",
            description="Test",
            version="1.0",
            framework=AgentFramework.LANGCHAIN,
        )
        mock_registry.register(mock_agent)
        assert len(mock_registry) == 1

        # Another async operation
        result2 = await mock_langchain_agent.arun("test")
        assert result2 == "LangChain result"
