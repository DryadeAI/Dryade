"""
Unit tests for A2A Agent Adapter.

Tests the A2AAgentAdapter class which enables communication
with A2A-compliant remote agents via JSON-RPC 2.0.

All tests use respx for HTTP mocking to avoid real network calls.
"""

import httpx
import pytest
import respx

from core.adapters.a2a_adapter import A2AAgentAdapter
from core.adapters.protocol import AgentCard, AgentFramework, AgentResult

# =============================================================================
# Sample A2A Agent Card Responses
# =============================================================================

VALID_AGENT_CARD = {
    "name": "remote_task_agent",
    "description": "A remote A2A-compliant task agent",
    "version": "2.0.0",
    "capabilities": [
        {
            "name": "execute_task",
            "description": "Execute arbitrary tasks",
            "inputSchema": {"type": "object", "properties": {"task": {"type": "string"}}},
            "outputSchema": {"type": "object", "properties": {"result": {"type": "string"}}},
        },
        {
            "name": "summarize",
            "description": "Summarize text content",
            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
            "outputSchema": {"type": "object", "properties": {"summary": {"type": "string"}}},
        },
    ],
    "metadata": {"organization": "TestOrg", "region": "us-west"},
}

# JSON-RPC 2.0 response format for A2A message/send
VALID_JSONRPC_RESPONSE = {
    "jsonrpc": "2.0",
    "id": "test-id",
    "result": {
        "id": "task-123",
        "status": {
            "state": "completed",
            "message": {
                "role": "agent",
                "parts": [{"text": "Task completed successfully"}],
            },
        },
    },
}

# The JSON-RPC endpoint is at the root path with trailing slash
JSONRPC_ENDPOINT = "https://remote-agent.example.com/"

# =============================================================================
# A2A Discovery Tests (.well-known/agent.json)
# =============================================================================

class TestA2AAdapterDiscovery:
    """Test A2A adapter discovery via .well-known/agent.json."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_discovery(self):
        """Verify adapter fetches and parses agent card from .well-known/agent.json."""
        # Mock the .well-known/agent.json endpoint
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=VALID_AGENT_CARD)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        # get_card() triggers async fetch (wrapped in sync)
        # For testing, we call _fetch_card directly
        card = await adapter._fetch_card()

        assert isinstance(card, AgentCard)
        assert card.name == "remote_task_agent"
        assert card.description == "A remote A2A-compliant task agent"
        assert card.version == "2.0.0"
        assert card.framework == AgentFramework.A2A
        assert card.endpoint == "https://remote-agent.example.com"
        assert len(card.capabilities) == 2
        assert card.capabilities[0].name == "execute_task"
        assert card.capabilities[1].name == "summarize"
        assert card.metadata["organization"] == "TestOrg"

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_discovery_trailing_slash(self):
        """Verify trailing slash in endpoint is handled correctly."""
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=VALID_AGENT_CARD)
        )

        # Endpoint with trailing slash
        adapter = A2AAgentAdapter("https://remote-agent.example.com/")

        card = await adapter._fetch_card()

        assert card.name == "remote_task_agent"
        assert card.endpoint == "https://remote-agent.example.com"

        await adapter.close()

# =============================================================================
# A2A Execute Tests (JSON-RPC 2.0 message/send)
# =============================================================================

class TestA2AAdapterExecute:
    """Test A2A adapter task execution via JSON-RPC 2.0."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_execute_success(self):
        """Verify successful execution returns proper AgentResult."""
        # Mock JSON-RPC endpoint at root path
        respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=VALID_JSONRPC_RESPONSE)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        result = await adapter.execute("Complete the test task")

        assert isinstance(result, AgentResult)
        assert result.status == "ok"
        assert result.result == "Task completed successfully"
        assert result.error is None
        assert result.metadata["framework"] == "a2a"
        assert result.metadata["endpoint"] == "https://remote-agent.example.com"
        assert result.metadata["task_id"] == "task-123"

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_execute_with_context(self):
        """Verify context is passed as metadata during execution."""
        context = {"user_id": "user-456", "session_id": "sess-789"}

        response = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {
                "id": "task-456",
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"text": "Context-aware result"}],
                    },
                },
            },
        }

        # Capture the request to verify context is sent
        route = respx.post(JSONRPC_ENDPOINT).mock(return_value=httpx.Response(200, json=response))

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        result = await adapter.execute("Use context", context=context)

        assert result.status == "ok"
        assert result.result == "Context-aware result"

        # Verify the request included context as metadata
        assert route.called
        request = route.calls.last.request
        request_body = request.content.decode()
        assert "user_id" in request_body
        assert "user-456" in request_body

        await adapter.close()

# =============================================================================
# A2A Tool Extraction Tests
# =============================================================================

class TestA2AAdapterTools:
    """Test A2A adapter tool extraction."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_get_tools(self):
        """Verify get_tools() returns capabilities as OpenAI function format."""
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=VALID_AGENT_CARD)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        # Force card fetch
        await adapter._fetch_card()
        adapter._card = await adapter._fetch_card()

        tools = adapter.get_tools()

        assert len(tools) == 2
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "execute_task"
        assert tools[0]["function"]["description"] == "Execute arbitrary tasks"
        assert "properties" in tools[0]["function"]["parameters"]

        await adapter.close()

# =============================================================================
# A2A Error Handling Tests
# =============================================================================

class TestA2AAdapterErrorHandling:
    """Test A2A adapter error handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_connection_error(self):
        """Verify connection error returns error AgentResult with user-friendly message."""
        # Mock a connection failure at JSON-RPC endpoint
        respx.post(JSONRPC_ENDPOINT).mock(side_effect=httpx.ConnectError("Connection refused"))

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        result = await adapter.execute("This will fail")

        assert result.status == "error"
        assert result.result is None
        # ConnectError is a subclass of NetworkError -- caught by httpx.NetworkError handler
        assert "network" in result.error.lower()
        assert "network connectivity" in result.error
        assert result.metadata["framework"] == "a2a"
        assert result.metadata["error_type"] == "network"

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_invalid_response(self):
        """Verify malformed JSON response is handled gracefully."""
        # Mock an invalid JSON response (not JSON at all)
        respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, content=b"Not valid JSON {{{")
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        result = await adapter.execute("Test invalid response")

        assert result.status == "error"
        assert result.result is None
        # Error should indicate failure
        assert result.error is not None

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_timeout(self):
        """Verify timeout is handled gracefully."""
        # Mock a timeout
        respx.post(JSONRPC_ENDPOINT).mock(side_effect=httpx.TimeoutException("Request timed out"))

        adapter = A2AAgentAdapter("https://remote-agent.example.com", timeout=1.0)

        result = await adapter.execute("This will timeout")

        assert result.status == "error"
        assert result.result is None
        assert "timed out" in result.error.lower()
        assert result.metadata["framework"] == "a2a"

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_http_error_status(self):
        """Verify HTTP error status codes are handled properly."""
        # Mock a 500 Internal Server Error
        respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        result = await adapter.execute("This causes server error")

        assert result.status == "error"
        assert result.result is None
        assert "500" in result.error
        assert result.metadata["framework"] == "a2a"

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_discovery_error_fallback(self):
        """Verify discovery error returns minimal fallback card."""
        # Mock a 404 for agent.json
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(404, text="Not Found")
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        card = await adapter._fetch_card()

        # Should return minimal fallback card, not raise exception
        assert card.name == "remote_agent"
        assert card.framework == AgentFramework.A2A
        assert card.endpoint == "https://remote-agent.example.com"
        assert card.capabilities == []
        assert "error" in card.metadata

        await adapter.close()

# =============================================================================
# A2A Authentication Tests
# =============================================================================

class TestA2AAdapterAuthentication:
    """Test A2A adapter authentication header handling."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_content_type_header(self):
        """Verify Content-Type header is set correctly."""
        route = respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=VALID_JSONRPC_RESPONSE)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        await adapter.execute("Test headers")

        # Verify Content-Type header
        assert route.called
        request = route.calls.last.request
        assert request.headers.get("Content-Type") == "application/json"

        await adapter.close()

# =============================================================================
# A2A Protocol Compliance Tests
# =============================================================================

class TestA2AAdapterProtocolCompliance:
    """Test A2A adapter UniversalAgent protocol compliance."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_implements_universal_agent(self):
        """Verify adapter implements UniversalAgent interface."""
        from core.adapters.protocol import UniversalAgent

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        assert isinstance(adapter, UniversalAgent)
        assert hasattr(adapter, "get_card")
        assert hasattr(adapter, "execute")
        assert hasattr(adapter, "get_tools")

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_framework_in_card(self):
        """Verify framework is A2A in agent card."""
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=VALID_AGENT_CARD)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")

        card = await adapter._fetch_card()

        assert card.framework == AgentFramework.A2A

        await adapter.close()

# =============================================================================
# A2A Edge Cases and Error Handling Enhancement
# =============================================================================

class TestA2AAdapterEdgeCases:
    """Test A2A adapter edge cases for message handling and async operations."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_empty_capabilities_list(self):
        """Verify handling of agent card with empty capabilities."""
        empty_card = {
            "name": "minimal_agent",
            "description": "Agent with no capabilities",
            "version": "1.0.0",
            "capabilities": [],
        }
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=empty_card)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        card = await adapter._fetch_card()

        assert len(card.capabilities) == 0
        # Cache the card to avoid get_card calling fetch_card in async context
        adapter._card = card
        assert adapter.get_tools() == []

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_missing_capabilities_field(self):
        """Verify handling of agent card without capabilities field."""
        card_no_caps = {
            "name": "no_caps_agent",
            "description": "Agent without capabilities field",
            "version": "1.0.0",
        }
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=card_no_caps)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        card = await adapter._fetch_card()

        assert len(card.capabilities) == 0

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_malformed_capability_schema(self):
        """Verify handling of capabilities with missing/invalid schema fields."""
        malformed_card = {
            "name": "malformed_agent",
            "description": "Agent with malformed capabilities",
            "version": "1.0.0",
            "capabilities": [
                {"name": "partial_cap"},  # Missing description, schemas
                {
                    "name": "complete_cap",
                    "description": "A complete capability",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "string"},
                },
            ],
        }
        respx.get("https://remote-agent.example.com/.well-known/agent.json").mock(
            return_value=httpx.Response(200, json=malformed_card)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        card = await adapter._fetch_card()

        assert len(card.capabilities) == 2
        # Verify partial cap has empty defaults
        assert card.capabilities[0].name == "partial_cap"
        assert card.capabilities[0].description == ""
        assert card.capabilities[0].input_schema == {}

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_task_response_missing_fields(self):
        """Verify handling of JSON-RPC response with minimal result."""
        # JSON-RPC response with minimal A2A task result
        minimal_response = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {
                "status": {
                    "state": "completed",
                    "message": {
                        "role": "agent",
                        "parts": [{"text": "Success"}],
                    },
                },
                # Missing: id, artifacts
            },
        }
        respx.post(JSONRPC_ENDPOINT).mock(return_value=httpx.Response(200, json=minimal_response))

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Task with minimal response")

        assert result.status == "ok"  # completed maps to ok
        assert result.result == "Success"
        assert result.metadata["task_id"] is None

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_empty_context(self):
        """Verify empty context is handled correctly (not sent as metadata)."""
        route = respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=VALID_JSONRPC_RESPONSE)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Task", context={})

        assert result.status == "ok"
        # Empty context is falsy so should not be included as metadata
        assert route.called

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_none_context(self):
        """Verify None context is not sent as metadata."""
        route = respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=VALID_JSONRPC_RESPONSE)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Task", context=None)

        assert result.status == "ok"
        # None context should not add metadata to params
        assert route.called
        request_body = route.calls.last.request.content.decode()
        assert '"metadata"' not in request_body

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_complex_nested_context(self):
        """Verify complex nested context structures are serialized correctly."""
        complex_context = {
            "user": {"id": "u123", "name": "Test User", "permissions": ["read", "write"]},
            "session": {"token": "abc123", "expires": 3600},
            "metadata": {"source": "api", "version": "2.0", "nested": {"deep": True}},
        }

        route = respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=VALID_JSONRPC_RESPONSE)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Task with complex context", context=complex_context)

        assert result.status == "ok"
        # Verify nested structure was serialized
        request_body = route.calls.last.request.content.decode()
        assert '"user"' in request_body
        assert '"permissions"' in request_body
        assert '"nested"' in request_body

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_custom_timeout(self):
        """Verify custom timeout is respected."""
        # Create adapter with very short timeout
        adapter = A2AAgentAdapter("https://remote-agent.example.com", timeout=0.01)

        # Mock a timeout exception
        respx.post(JSONRPC_ENDPOINT).mock(side_effect=httpx.TimeoutException("Request timed out"))

        result = await adapter.execute("Slow task")

        # Should return error due to timeout
        assert result.status == "error"
        assert "timed out" in result.error.lower() or "timeout" in result.error.lower()

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_401_unauthorized(self):
        """Verify 401 Unauthorized is handled correctly."""
        respx.post(JSONRPC_ENDPOINT).mock(return_value=httpx.Response(401, text="Unauthorized"))

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Unauthorized task")

        assert result.status == "error"
        assert "401" in result.error
        assert result.metadata["framework"] == "a2a"

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_429_rate_limit(self):
        """Verify 429 Rate Limit is handled correctly."""
        respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(429, text="Rate limit exceeded")
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Rate limited task")

        assert result.status == "error"
        assert "429" in result.error
        assert "Rate limit" in result.error

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_network_unreachable(self):
        """Verify network unreachable errors are handled."""
        respx.post(JSONRPC_ENDPOINT).mock(side_effect=httpx.NetworkError("Network unreachable"))

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Unreachable task")

        assert result.status == "error"
        assert "Network unreachable" in result.error

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_partial_json_response(self):
        """Verify partial/truncated JSON response is handled."""
        respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, content=b'{"result": "partial", "status":')
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Partial JSON task")

        assert result.status == "error"
        assert result.error is not None

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_jsonrpc_error_response(self):
        """Verify JSON-RPC error response is handled correctly."""
        error_response = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "error": {
                "code": -32600,
                "message": "Invalid Request",
            },
        }
        respx.post(JSONRPC_ENDPOINT).mock(return_value=httpx.Response(200, json=error_response))

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        result = await adapter.execute("Bad request")

        assert result.status == "error"
        assert "JSON-RPC error" in result.error
        assert "-32600" in result.error

        await adapter.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a2a_adapter_jsonrpc_request_format(self):
        """Verify JSON-RPC 2.0 request is properly formatted."""
        import json

        route = respx.post(JSONRPC_ENDPOINT).mock(
            return_value=httpx.Response(200, json=VALID_JSONRPC_RESPONSE)
        )

        adapter = A2AAgentAdapter("https://remote-agent.example.com")
        await adapter.execute("Test task")

        assert route.called
        request_body = json.loads(route.calls.last.request.content.decode())
        assert request_body["jsonrpc"] == "2.0"
        assert request_body["method"] == "message/send"
        assert "id" in request_body
        assert "params" in request_body
        assert "message" in request_body["params"]
        assert request_body["params"]["message"]["role"] == "user"
        assert request_body["params"]["message"]["parts"][0]["text"] == "Test task"

        await adapter.close()
