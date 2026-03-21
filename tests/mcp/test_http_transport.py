"""Unit tests for HTTP/SSE transport.

Tests the HttpSseTransport class without requiring actual MCP servers.
Uses mocking to simulate server behavior and SSE connections.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.mcp.http_transport import HttpSseTransport
from core.mcp.stdio_transport import MCPServerStatus, MCPTransportError

# ============================================================================
# Initialization Tests
# ============================================================================

class TestHttpSseTransportInit:
    """Tests for HttpSseTransport initialization."""

    def test_init_with_url(self):
        """Test transport initializes with URL."""
        transport = HttpSseTransport(url="https://example.com/mcp")
        assert transport.url == "https://example.com/mcp"
        assert transport.status == MCPServerStatus.STOPPED
        assert transport.headers == {}
        assert transport.timeout == 120.0

    def test_init_with_headers(self):
        """Test transport initializes with custom headers."""
        transport = HttpSseTransport(
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer token", "X-API-Key": "key123"},
        )
        assert transport.headers["Authorization"] == "Bearer token"
        assert transport.headers["X-API-Key"] == "key123"

    def test_init_with_custom_timeout(self):
        """Test transport accepts custom timeout."""
        transport = HttpSseTransport(url="https://example.com/mcp", timeout=60.0)
        assert transport.timeout == 60.0

    def test_init_with_sse_read_timeout(self):
        """Test transport accepts SSE read timeout."""
        transport = HttpSseTransport(
            url="https://example.com/mcp",
            sse_read_timeout=600.0,
        )
        assert transport.sse_read_timeout == 600.0

    def test_initial_state(self):
        """Test transport starts in correct initial state."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        assert transport._session is None
        assert transport.status == MCPServerStatus.STOPPED
        assert transport.is_alive is False
        assert transport.server_info is None
        assert transport.capabilities is None
        assert transport.protocol_version == ""

# ============================================================================
# Connection Tests
# ============================================================================

class TestHttpSseTransportConnection:
    """Tests for connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_raises_if_already_connected(self):
        """Test connect raises error if already connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Simulate already connected
        transport._session = MagicMock()

        with pytest.raises(MCPTransportError) as exc_info:
            await transport.connect()

        assert "already connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connect_failure_sets_unhealthy_status(self):
        """Test connection failure sets UNHEALTHY status."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with patch("core.mcp.http_transport.sse_client") as mock_sse:
            # Make sse_client raise an exception
            mock_context = AsyncMock()
            mock_context.__aenter__.side_effect = ConnectionError("Network error")
            mock_sse.return_value = mock_context

            with pytest.raises(MCPTransportError):
                await transport.connect()

            assert transport.status == MCPServerStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_close_resets_state(self):
        """Test close resets transport state."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Set up mock session
        transport._session = MagicMock()
        transport._status = MCPServerStatus.HEALTHY
        transport._session_context = AsyncMock()
        transport._sse_context = AsyncMock()

        await transport.close()

        assert transport._session is None
        assert transport.status == MCPServerStatus.STOPPED

    @pytest.mark.asyncio
    async def test_close_handles_missing_session(self):
        """Test close works when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Should not raise
        await transport.close()

        assert transport.status == MCPServerStatus.STOPPED

# ============================================================================
# Status Tests
# ============================================================================

class TestHttpSseTransportStatus:
    """Tests for status property."""

    def test_status_stopped_when_not_connected(self):
        """Test status is STOPPED when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")
        assert transport.status == MCPServerStatus.STOPPED

    def test_is_alive_false_when_not_connected(self):
        """Test is_alive is False when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")
        assert transport.is_alive is False

    def test_is_alive_true_when_healthy(self):
        """Test is_alive is True when healthy with session."""
        transport = HttpSseTransport(url="https://example.com/mcp")
        transport._session = MagicMock()
        transport._status = MCPServerStatus.HEALTHY

        assert transport.is_alive is True

# ============================================================================
# Operations Without Connection Tests
# ============================================================================

class TestHttpSseTransportOperationsNoConnection:
    """Tests for operations when not connected."""

    @pytest.mark.asyncio
    async def test_list_tools_raises_when_not_connected(self):
        """Test list_tools raises error when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with pytest.raises(MCPTransportError) as exc_info:
            await transport.list_tools()

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_call_tool_raises_when_not_connected(self):
        """Test call_tool raises error when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with pytest.raises(MCPTransportError) as exc_info:
            await transport.call_tool("test-tool", {"arg": "value"})

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_list_resources_raises_when_not_connected(self):
        """Test list_resources raises error when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with pytest.raises(MCPTransportError) as exc_info:
            await transport.list_resources()

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_list_prompts_raises_when_not_connected(self):
        """Test list_prompts raises error when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with pytest.raises(MCPTransportError) as exc_info:
            await transport.list_prompts()

        assert "not connected" in str(exc_info.value).lower()

# ============================================================================
# Operations With Mocked Session Tests
# ============================================================================

class TestHttpSseTransportOperations:
    """Tests for tool operations with mocked session."""

    @pytest.mark.asyncio
    async def test_list_tools_parses_response(self):
        """Test list_tools parses SDK response correctly."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Mock session
        mock_session = AsyncMock()
        mock_tool = MagicMock()
        mock_tool.name = "test-tool"
        mock_tool.description = "Test description"
        mock_tool.inputSchema = {
            "type": "object",
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"],
        }

        mock_result = MagicMock()
        mock_result.tools = [mock_tool]
        mock_session.list_tools.return_value = mock_result

        transport._session = mock_session
        transport._status = MCPServerStatus.HEALTHY

        tools = await transport.list_tools()

        assert len(tools) == 1
        assert tools[0].name == "test-tool"
        assert tools[0].description == "Test description"
        assert tools[0].inputSchema.type == "object"
        assert "arg1" in tools[0].inputSchema.properties

    @pytest.mark.asyncio
    async def test_call_tool_parses_response(self):
        """Test call_tool parses SDK response correctly."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Mock session - use spec=False to avoid attribute auto-creation issues
        mock_session = AsyncMock()
        mock_content = MagicMock(spec=[])
        mock_content.type = "text"
        mock_content.text = "Result text"

        # Remove auto-generated attributes that would fail pydantic validation
        del mock_content.data
        del mock_content.mimeType

        mock_result = MagicMock()
        mock_result.content = [mock_content]
        mock_result.isError = False
        mock_session.call_tool.return_value = mock_result

        transport._session = mock_session
        transport._status = MCPServerStatus.HEALTHY

        result = await transport.call_tool("test-tool", {"arg": "value"})

        mock_session.call_tool.assert_called_once_with("test-tool", {"arg": "value"})
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert result.content[0].text == "Result text"
        assert result.isError is False

    @pytest.mark.asyncio
    async def test_call_tool_error_sets_unhealthy(self):
        """Test call_tool error sets status to UNHEALTHY."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Mock session that raises error
        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = Exception("Connection lost")

        transport._session = mock_session
        transport._status = MCPServerStatus.HEALTHY

        with pytest.raises(MCPTransportError):
            await transport.call_tool("test-tool", {})

        assert transport.status == MCPServerStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_list_resources_parses_response(self):
        """Test list_resources parses SDK response correctly."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Mock session
        mock_session = AsyncMock()
        mock_resource = MagicMock()
        mock_resource.uri = "file:///test.txt"
        mock_resource.name = "test.txt"
        mock_resource.description = "A test file"
        mock_resource.mimeType = "text/plain"

        mock_result = MagicMock()
        mock_result.resources = [mock_resource]
        mock_session.list_resources.return_value = mock_result

        transport._session = mock_session
        transport._status = MCPServerStatus.HEALTHY

        resources = await transport.list_resources()

        assert len(resources) == 1
        assert resources[0].uri == "file:///test.txt"
        assert resources[0].name == "test.txt"
        assert resources[0].mimeType == "text/plain"

    @pytest.mark.asyncio
    async def test_list_prompts_parses_response(self):
        """Test list_prompts parses SDK response correctly."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        # Mock session
        mock_session = AsyncMock()
        mock_prompt = MagicMock()
        mock_prompt.name = "greeting"
        mock_prompt.description = "A greeting prompt"
        mock_prompt.arguments = [{"name": "name", "required": True}]

        mock_result = MagicMock()
        mock_result.prompts = [mock_prompt]
        mock_session.list_prompts.return_value = mock_result

        transport._session = mock_session
        transport._status = MCPServerStatus.HEALTHY

        prompts = await transport.list_prompts()

        assert len(prompts) == 1
        assert prompts[0].name == "greeting"
        assert prompts[0].description == "A greeting prompt"

# ============================================================================
# Registry Integration Tests
# ============================================================================

class TestHttpSseTransportIntegration:
    """Integration tests with MCPRegistry."""

    def test_transport_factory_creates_http(self):
        """Test registry creates HttpSseTransport for HTTP config."""
        from core.mcp import MCPRegistry, MCPServerConfig, MCPServerTransport
        from core.mcp.http_transport import HttpSseTransport

        registry = MCPRegistry()
        config = MCPServerConfig(
            name="test-http",
            command=[],
            transport=MCPServerTransport.HTTP,
            url="https://example.com/mcp",
        )
        registry.register(config)

        transport = registry._create_transport(config)

        assert isinstance(transport, HttpSseTransport)
        assert transport.url == "https://example.com/mcp"

    def test_transport_factory_creates_stdio(self):
        """Test registry creates StdioTransport for STDIO config."""
        from core.mcp import MCPRegistry, MCPServerConfig, MCPServerTransport
        from core.mcp.stdio_transport import StdioTransport

        registry = MCPRegistry()
        config = MCPServerConfig(
            name="test-stdio",
            command=["echo", "test"],
            transport=MCPServerTransport.STDIO,
        )
        registry.register(config)

        transport = registry._create_transport(config)

        assert isinstance(transport, StdioTransport)
        assert transport.command == ["echo", "test"]

    def test_transport_factory_with_headers(self):
        """Test registry creates HttpSseTransport with headers."""
        from core.mcp import MCPRegistry, MCPServerConfig, MCPServerTransport
        from core.mcp.http_transport import HttpSseTransport

        registry = MCPRegistry()
        config = MCPServerConfig(
            name="test-http",
            command=[],
            transport=MCPServerTransport.HTTP,
            url="https://example.com/mcp",
            headers={"X-Custom": "value"},
        )
        registry.register(config)

        transport = registry._create_transport(config)

        assert isinstance(transport, HttpSseTransport)
        assert transport.headers.get("X-Custom") == "value"

    def test_transport_factory_type_verification(self):
        """Test transport factory returns correct types for each transport."""
        from core.mcp import MCPRegistry, MCPServerConfig, MCPServerTransport
        from core.mcp.http_transport import HttpSseTransport
        from core.mcp.stdio_transport import StdioTransport

        registry = MCPRegistry()

        # HTTP config should produce HttpSseTransport
        http_config = MCPServerConfig(
            name="http-test",
            command=[],
            transport=MCPServerTransport.HTTP,
            url="https://example.com/mcp",
        )
        http_transport = registry._create_transport(http_config)
        assert isinstance(http_transport, HttpSseTransport), (
            f"HTTP config produced {type(http_transport)}"
        )

        # STDIO config should produce StdioTransport
        stdio_config = MCPServerConfig(
            name="stdio-test",
            command=["echo"],
            transport=MCPServerTransport.STDIO,
        )
        stdio_transport = registry._create_transport(stdio_config)
        assert isinstance(stdio_transport, StdioTransport), (
            f"STDIO config produced {type(stdio_transport)}"
        )

# ============================================================================
# Sync Wrapper Tests
# ============================================================================

class TestSyncWrappers:
    """Tests for synchronous wrapper methods."""

    def test_list_tools_sync_raises_when_not_connected(self):
        """Test list_tools_sync raises when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with pytest.raises(MCPTransportError):
            transport.list_tools_sync()

    def test_call_tool_sync_raises_when_not_connected(self):
        """Test call_tool_sync raises when not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with pytest.raises(MCPTransportError):
            transport.call_tool_sync("test-tool", {})

# ============================================================================
# Context Manager Tests
# ============================================================================

class TestContextManager:
    """Tests for async context manager behavior."""

    @pytest.mark.asyncio
    async def test_context_manager_calls_connect_and_close(self):
        """Test context manager calls connect on enter and close on exit."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with patch.object(transport, "connect", new_callable=AsyncMock) as mock_connect:
            with patch.object(transport, "close", new_callable=AsyncMock) as mock_close:
                mock_connect.return_value = MagicMock()

                async with transport:
                    mock_connect.assert_called_once()

                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exception(self):
        """Test context manager closes even on exception."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        with patch.object(transport, "connect", new_callable=AsyncMock) as mock_connect:
            with patch.object(transport, "close", new_callable=AsyncMock) as mock_close:
                mock_connect.return_value = MagicMock()

                with pytest.raises(ValueError):
                    async with transport:
                        raise ValueError("Test error")

                mock_close.assert_called_once()

# ============================================================================
# Initialize Tests
# ============================================================================

class TestInitialize:
    """Tests for initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_calls_connect_if_not_connected(self):
        """Test initialize calls connect if not connected."""
        transport = HttpSseTransport(url="https://example.com/mcp")

        mock_result = MagicMock()

        with patch.object(transport, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_result

            result = await transport.initialize()

            mock_connect.assert_called_once()
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_initialize_returns_cached_if_connected(self):
        """Test initialize returns cached info if already connected."""
        from core.mcp.protocol import MCPServerCapabilities, MCPServerInfo

        transport = HttpSseTransport(url="https://example.com/mcp")

        # Set up as if already connected - use real objects for pydantic compatibility
        transport._session = MagicMock()
        transport.protocol_version = "2024-11-05"
        transport.server_info = MCPServerInfo(name="test", version="1.0")
        transport.capabilities = MCPServerCapabilities()

        with patch.object(transport, "connect", new_callable=AsyncMock) as mock_connect:
            result = await transport.initialize()

            # Should not call connect again
            mock_connect.assert_not_called()
            assert result.protocolVersion == "2024-11-05"
