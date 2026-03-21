"""Unit tests for A2A (Agent-to-Agent) protocol adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

@pytest.mark.unit
class TestA2AAdapterInitialization:
    """Tests for A2AAgentAdapter initialization."""

    def test_a2a_adapter_initialization(self):
        """Test basic initialization with endpoint."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://localhost:8080")

        assert adapter.endpoint == "http://localhost:8080"
        assert adapter.timeout == 300.0
        assert adapter._card is None

    def test_a2a_adapter_initialization_trailing_slash(self):
        """Test initialization strips trailing slash from endpoint."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://localhost:8080/")

        assert adapter.endpoint == "http://localhost:8080"

    def test_a2a_adapter_initialization_custom_timeout(self):
        """Test initialization with custom timeout."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://localhost:8080", timeout=60.0)

        assert adapter.timeout == 60.0

@pytest.mark.unit
class TestA2AAdapterFetchCard:
    """Tests for A2AAgentAdapter._fetch_card()."""

    @pytest.mark.asyncio
    async def test_a2a_adapter_fetch_card_success(self):
        """Test fetching agent card from remote endpoint."""
        from core.adapters.a2a_adapter import A2AAgentAdapter
        from core.adapters.protocol import AgentFramework

        adapter = A2AAgentAdapter("http://remote-agent.example.com")

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "remote_agent",
            "description": "A remote A2A agent",
            "version": "2.0",
            "capabilities": [
                {
                    "name": "search",
                    "description": "Search capability",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "string"},
                }
            ],
            "metadata": {"provider": "example"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, "get", new=AsyncMock(return_value=mock_response)):
            card = await adapter._fetch_card()

        assert card.name == "remote_agent"
        assert card.description == "A remote A2A agent"
        assert card.version == "2.0"
        assert card.framework == AgentFramework.A2A
        assert card.endpoint == "http://remote-agent.example.com"
        assert len(card.capabilities) == 1
        assert card.capabilities[0].name == "search"
        assert card.metadata["provider"] == "example"

    @pytest.mark.asyncio
    async def test_a2a_adapter_fetch_card_error(self):
        """Test fetching agent card handles errors gracefully."""
        from core.adapters.a2a_adapter import A2AAgentAdapter
        from core.adapters.protocol import AgentFramework

        adapter = A2AAgentAdapter("http://unreachable.example.com")

        with patch.object(
            adapter._client, "get", new=AsyncMock(side_effect=Exception("Connection refused"))
        ):
            card = await adapter._fetch_card()

        # Should return a minimal card with error info
        assert card.name == "remote_agent"
        assert card.framework == AgentFramework.A2A
        assert card.endpoint == "http://unreachable.example.com"
        assert "error" in card.metadata
        assert "Connection refused" in card.metadata["error"]

@pytest.mark.unit
class TestA2AAdapterGetCard:
    """Tests for A2AAgentAdapter.get_card()."""

    def test_a2a_adapter_get_card_cached(self):
        """Test that get_card returns cached card."""
        from core.adapters.a2a_adapter import A2AAgentAdapter
        from core.adapters.protocol import AgentCard, AgentFramework

        adapter = A2AAgentAdapter("http://example.com")

        # Pre-populate the cache
        cached_card = AgentCard(
            name="cached",
            description="Cached agent",
            version="1.0",
            framework=AgentFramework.A2A,
            endpoint="http://example.com",
        )
        adapter._card = cached_card

        result = adapter.get_card()

        assert result is cached_card

    def test_a2a_adapter_get_card_fetches_when_not_cached(self):
        """Test that get_card fetches when cache is empty."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://example.com")

        with patch.object(adapter, "_fetch_card", new=AsyncMock()) as mock_fetch:
            from core.adapters.protocol import AgentCard, AgentFramework

            mock_fetch.return_value = AgentCard(
                name="fetched", description="", version="1.0", framework=AgentFramework.A2A
            )

            # Patch asyncio.run or get_event_loop
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_until_complete = MagicMock(
                    return_value=mock_fetch.return_value
                )
                card = adapter.get_card()

            assert card.name == "fetched"

@pytest.mark.unit
class TestA2AAdapterExecute:
    """Tests for A2AAgentAdapter.execute() using JSON-RPC 2.0 protocol."""

    @pytest.mark.asyncio
    async def test_a2a_adapter_execute_success(self):
        """Test successful task execution via JSON-RPC message/send."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://agent.example.com")

        # JSON-RPC 2.0 response with A2A Task in result
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "id": "task-123",
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"text": "Task completed"}],
                    },
                },
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, "post", new=AsyncMock(return_value=mock_response)):
            result = await adapter.execute("Do something", {"context_key": "value"})

        assert result.status == "ok"
        assert result.result == "Task completed"
        assert result.metadata["framework"] == "a2a"
        assert result.metadata["endpoint"] == "http://agent.example.com"
        assert result.metadata["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_a2a_adapter_execute_http_error(self):
        """Test handling of HTTP errors during execution."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://agent.example.com")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        http_error = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )

        with patch.object(adapter._client, "post", new=AsyncMock(side_effect=http_error)):
            result = await adapter.execute("Task")

        assert result.status == "error"
        assert "500" in result.error
        assert result.metadata["framework"] == "a2a"

    @pytest.mark.asyncio
    async def test_a2a_adapter_execute_general_error(self):
        """Test handling of general errors during execution."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://agent.example.com")

        with patch.object(
            adapter._client, "post", new=AsyncMock(side_effect=Exception("Network error"))
        ):
            result = await adapter.execute("Task")

        assert result.status == "error"
        # The adapter wraps general exceptions as "Agent execution failed: {type}"
        assert "Exception" in result.error

    @pytest.mark.asyncio
    async def test_a2a_adapter_execute_with_error_response(self):
        """Test handling of JSON-RPC error response."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://agent.example.com")

        # JSON-RPC error response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "error": {
                "code": -32000,
                "message": "Task failed on remote",
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(adapter._client, "post", new=AsyncMock(return_value=mock_response)):
            result = await adapter.execute("Failing task")

        assert result.status == "error"
        assert "Task failed on remote" in result.error

@pytest.mark.unit
class TestA2AAdapterGetTools:
    """Tests for A2AAgentAdapter.get_tools()."""

    def test_a2a_adapter_get_tools_empty(self):
        """Test get_tools with no capabilities."""
        from core.adapters.a2a_adapter import A2AAgentAdapter
        from core.adapters.protocol import AgentCard, AgentFramework

        adapter = A2AAgentAdapter("http://example.com")
        adapter._card = AgentCard(
            name="no_caps",
            description="",
            version="1.0",
            framework=AgentFramework.A2A,
            capabilities=[],
        )

        tools = adapter.get_tools()

        assert tools == []

    def test_a2a_adapter_get_tools_with_capabilities(self):
        """Test get_tools returns OpenAI function format."""
        from core.adapters.a2a_adapter import A2AAgentAdapter
        from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework

        adapter = A2AAgentAdapter("http://example.com")
        adapter._card = AgentCard(
            name="capable",
            description="",
            version="1.0",
            framework=AgentFramework.A2A,
            capabilities=[
                AgentCapability(
                    name="search",
                    description="Search for info",
                    input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
                ),
                AgentCapability(
                    name="analyze", description="Analyze data", input_schema={"type": "object"}
                ),
            ],
        )

        tools = adapter.get_tools()

        assert len(tools) == 2
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "search"
        assert tools[0]["function"]["description"] == "Search for info"
        assert tools[0]["function"]["parameters"]["type"] == "object"

@pytest.mark.unit
class TestA2AAdapterLifecycle:
    """Tests for A2AAgentAdapter lifecycle management."""

    @pytest.mark.asyncio
    async def test_a2a_adapter_close(self):
        """Test closing the adapter."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://example.com")

        with patch.object(adapter._client, "aclose", new=AsyncMock()) as mock_close:
            await adapter.close()
            mock_close.assert_awaited_once()

@pytest.mark.unit
class TestA2AAdapterMessageRouting:
    """Tests for A2A adapter JSON-RPC message routing."""

    @pytest.mark.asyncio
    async def test_a2a_adapter_sends_jsonrpc_payload(self):
        """Test that execute sends correct JSON-RPC 2.0 payload to /."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://agent.example.com")

        # Valid JSON-RPC response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "id": "task-1",
                "status": {
                    "state": "completed",
                    "message": {"role": "agent", "parts": [{"text": "ok"}]},
                },
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            adapter._client, "post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await adapter.execute("Test task", {"key": "value"})

            # Verify the JSON-RPC payload
            mock_post.assert_awaited_once()
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs["json"]
            assert payload["jsonrpc"] == "2.0"
            assert payload["method"] == "message/send"
            assert "id" in payload  # JSON-RPC request ID
            assert payload["params"]["message"]["role"] == "user"
            assert payload["params"]["message"]["parts"] == [{"text": "Test task"}]
            assert payload["params"]["metadata"] == {"key": "value"}
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_a2a_adapter_posts_to_root_endpoint(self):
        """Test that execute POSTs to / (JSON-RPC endpoint)."""
        from core.adapters.a2a_adapter import A2AAgentAdapter

        adapter = A2AAgentAdapter("http://agent.example.com")

        # Valid JSON-RPC response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "result": {
                "id": "task-1",
                "status": {"state": "completed"},
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            adapter._client, "post", new=AsyncMock(return_value=mock_response)
        ) as mock_post:
            await adapter.execute("Task")

            # Verify the endpoint is / (JSON-RPC), not /tasks
            call_args = mock_post.call_args
            assert call_args[0][0] == "http://agent.example.com/"
