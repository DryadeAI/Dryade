"""HTTP/SSE Transport for MCP Servers.

Provides transport layer for remote MCP servers via HTTP with
Server-Sent Events (SSE) for streaming responses.

Uses MCP SDK's built-in sse_client for protocol compliance.
Matches StdioTransport interface for registry compatibility.

Example:
    transport = HttpSseTransport(
        url="https://mcp.context7.com/mcp",
        headers={"X-API-Key": "your-key"},
        timeout=30.0,
    )
    await transport.connect()
    tools = await transport.list_tools()
    result = await transport.call_tool("query-docs", {"topic": "python"})
    await transport.close()
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

from core.mcp.protocol import (
    MCPInitializeResult,
    MCPPrompt,
    MCPResource,
    MCPResourceContents,
    MCPServerCapabilities,
    MCPServerInfo,
    MCPTool,
    MCPToolCallContent,
    MCPToolCallResult,
    MCPToolInputSchema,
)
from core.mcp.stdio_transport import MCPServerStatus, MCPTransportError

logger = logging.getLogger(__name__)

class HttpSseTransport:
    """Transport for communicating with remote MCP servers via HTTP/SSE.

    Uses MCP SDK's sse_client for protocol-compliant communication.
    Provides same interface as StdioTransport for registry compatibility.

    The transport maintains a long-lived SSE connection to the server.
    Call connect() to establish the connection, and close() to terminate.

    Attributes:
        url: Server URL (must support SSE).
        headers: Custom headers to send with requests.
        timeout: Request timeout in seconds.
        sse_read_timeout: SSE stream read timeout in seconds.

    Example:
        >>> transport = HttpSseTransport(
        ...     url="https://example.com/mcp",
        ...     headers={"Authorization": "Bearer token"},
        ... )
        >>> await transport.connect()
        >>> tools = await transport.list_tools()
        >>> await transport.close()
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = float(os.getenv("DRYADE_MCP_TIMEOUT", "120")),
        sse_read_timeout: float = 300.0,
    ):
        """Initialize the HTTP/SSE transport.

        Args:
            url: Server URL with SSE endpoint.
            headers: Custom headers for authentication and other purposes.
            timeout: HTTP operation timeout in seconds.
            sse_read_timeout: SSE stream read timeout in seconds.
        """
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.sse_read_timeout = sse_read_timeout

        # Connection state
        self._session: ClientSession | None = None
        self._status = MCPServerStatus.STOPPED
        self._lock = asyncio.Lock()

        # Server info from initialize
        self.server_info: MCPServerInfo | None = None
        self.capabilities: MCPServerCapabilities | None = None
        self.protocol_version: str = ""

        # Context managers for cleanup
        self._sse_context: Any = None
        self._session_context: Any = None
        self._read_stream: Any = None
        self._write_stream: Any = None

    @property
    def status(self) -> MCPServerStatus:
        """Get the current server connection status."""
        return self._status

    @property
    def is_alive(self) -> bool:
        """Check if the transport has an active connection.

        Returns:
            True if connected and session is active, False otherwise.
        """
        return self._session is not None and self._status == MCPServerStatus.HEALTHY

    async def __aenter__(self) -> HttpSseTransport:
        """Async context manager entry - connects and initializes."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit - closes the connection."""
        await self.close()

    async def connect(self) -> MCPInitializeResult:
        """Establish connection to the MCP server.

        Opens an SSE connection, creates a client session, and performs
        the MCP initialization handshake.

        Returns:
            MCPInitializeResult with server info and capabilities.

        Raises:
            MCPTransportError: If connection fails.
        """
        async with self._lock:
            if self._session is not None:
                raise MCPTransportError("Transport already connected")

            try:
                logger.debug("Connecting to MCP server: %s", self.url)
                self._status = MCPServerStatus.STARTING

                # Create SSE client context manager
                self._sse_context = sse_client(
                    url=self.url,
                    headers=self.headers,
                    timeout=self.timeout,
                    sse_read_timeout=self.sse_read_timeout,
                )

                # Enter the SSE context
                streams = await self._sse_context.__aenter__()
                self._read_stream, self._write_stream = streams

                # Create session context
                self._session_context = ClientSession(self._read_stream, self._write_stream)
                self._session = await self._session_context.__aenter__()

                # Initialize the session
                result = await self._session.initialize()

                # Store server info
                self.protocol_version = result.protocolVersion

                if result.serverInfo:
                    self.server_info = MCPServerInfo(
                        name=result.serverInfo.name,
                        version=result.serverInfo.version,
                    )

                if result.capabilities:
                    self.capabilities = MCPServerCapabilities(
                        tools=result.capabilities.tools,
                        resources=result.capabilities.resources,
                        prompts=result.capabilities.prompts,
                        logging=result.capabilities.logging,
                    )

                self._status = MCPServerStatus.HEALTHY
                logger.info(
                    "Connected to MCP server: %s (version %s)",
                    self.server_info.name if self.server_info else "unknown",
                    self.server_info.version if self.server_info else "unknown",
                )

                return MCPInitializeResult(
                    protocolVersion=self.protocol_version,
                    capabilities=self.capabilities or MCPServerCapabilities(),
                    serverInfo=self.server_info,
                )

            except Exception as e:
                self._status = MCPServerStatus.UNHEALTHY
                # Clean up any partial connection
                await self._cleanup_contexts()
                raise MCPTransportError(f"Failed to connect: {e}") from e

    async def _cleanup_contexts(self) -> None:
        """Clean up context managers safely."""
        try:
            if self._session_context is not None:
                try:
                    await self._session_context.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug("Error closing session context: %s", e)
                self._session_context = None
        finally:
            if self._sse_context is not None:
                try:
                    await self._sse_context.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug("Error closing SSE context: %s", e)
                self._sse_context = None

        self._session = None
        self._read_stream = None
        self._write_stream = None

    async def close(self) -> None:
        """Close the connection to the MCP server.

        Safely cleans up the session and SSE connection.
        """
        async with self._lock:
            logger.debug("Closing HTTP/SSE transport to: %s", self.url)
            await self._cleanup_contexts()
            self._status = MCPServerStatus.STOPPED
            logger.debug("HTTP/SSE transport closed")

    async def initialize(self) -> MCPInitializeResult:
        """Perform MCP initialization handshake.

        If already connected, returns cached info.
        If not connected, establishes connection first.

        Returns:
            MCPInitializeResult with server info and capabilities.
        """
        if self._session is None:
            return await self.connect()

        return MCPInitializeResult(
            protocolVersion=self.protocol_version,
            capabilities=self.capabilities or MCPServerCapabilities(),
            serverInfo=self.server_info,
        )

    def _ensure_connected(self) -> ClientSession:
        """Ensure we have an active session.

        Returns:
            The active ClientSession.

        Raises:
            MCPTransportError: If not connected.
        """
        if self._session is None:
            raise MCPTransportError("Not connected. Call connect() or use async context manager.")
        return self._session

    async def list_tools(self) -> list[MCPTool]:
        """List available tools from the server.

        Returns:
            List of MCPTool definitions.

        Raises:
            MCPTransportError: If not connected or request fails.
        """
        session = self._ensure_connected()

        try:
            result = await session.list_tools()

            return [
                MCPTool(
                    name=t.name,
                    description=t.description or "",
                    inputSchema=MCPToolInputSchema(
                        type=t.inputSchema.get("type", "object") if t.inputSchema else "object",
                        properties=t.inputSchema.get("properties", {}) if t.inputSchema else {},
                        required=t.inputSchema.get("required", []) if t.inputSchema else [],
                    ),
                )
                for t in result.tools
            ]
        except Exception as e:
            self._status = MCPServerStatus.UNHEALTHY
            raise MCPTransportError(f"Failed to list tools: {e}") from e

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> MCPToolCallResult:
        """Call a tool on the server.

        Args:
            name: The tool name.
            arguments: Arguments to pass to the tool.

        Returns:
            MCPToolCallResult with the tool output.

        Raises:
            MCPTransportError: If not connected or tool call fails.
        """
        session = self._ensure_connected()

        try:
            result = await session.call_tool(name, arguments or {})

            return MCPToolCallResult(
                content=[
                    MCPToolCallContent(
                        type=c.type,
                        text=getattr(c, "text", None),
                        data=getattr(c, "data", None),
                        mimeType=getattr(c, "mimeType", None),
                    )
                    for c in result.content
                ],
                isError=result.isError if hasattr(result, "isError") else False,
            )
        except Exception as e:
            self._status = MCPServerStatus.UNHEALTHY
            raise MCPTransportError(f"Failed to call tool '{name}': {e}") from e

    async def list_resources(self) -> list[MCPResource]:
        """List available resources from the server.

        Returns:
            List of MCPResource definitions.

        Raises:
            MCPTransportError: If not connected or request fails.
        """
        session = self._ensure_connected()

        try:
            result = await session.list_resources()

            return [
                MCPResource(
                    uri=r.uri,
                    name=r.name,
                    description=r.description or "",
                    mimeType=getattr(r, "mimeType", None),
                )
                for r in result.resources
            ]
        except Exception as e:
            self._status = MCPServerStatus.UNHEALTHY
            raise MCPTransportError(f"Failed to list resources: {e}") from e

    async def read_resource(self, uri: str) -> MCPResourceContents:
        """Read a resource from the server.

        Args:
            uri: The resource URI.

        Returns:
            MCPResourceContents with the resource data.

        Raises:
            MCPTransportError: If not connected or request fails.
        """
        session = self._ensure_connected()

        try:
            result = await session.read_resource(uri)
            contents = result.contents[0] if result.contents else None

            if contents is None:
                return MCPResourceContents(uri=uri)

            return MCPResourceContents(
                uri=getattr(contents, "uri", uri),
                mimeType=getattr(contents, "mimeType", None),
                text=getattr(contents, "text", None),
                blob=getattr(contents, "blob", None),
            )
        except Exception as e:
            self._status = MCPServerStatus.UNHEALTHY
            raise MCPTransportError(f"Failed to read resource '{uri}': {e}") from e

    async def list_prompts(self) -> list[MCPPrompt]:
        """List available prompts from the server.

        Returns:
            List of MCPPrompt definitions.

        Raises:
            MCPTransportError: If not connected or request fails.
        """
        session = self._ensure_connected()

        try:
            result = await session.list_prompts()

            return [
                MCPPrompt(
                    name=p.name,
                    description=p.description or "",
                    arguments=p.arguments or [],
                )
                for p in result.prompts
            ]
        except Exception as e:
            self._status = MCPServerStatus.UNHEALTHY
            raise MCPTransportError(f"Failed to list prompts: {e}") from e

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Get a prompt from the server.

        Args:
            name: The prompt name.
            arguments: Arguments to fill the prompt template.

        Returns:
            Dict with 'description' and 'messages' keys.

        Raises:
            MCPTransportError: If not connected or request fails.
        """
        session = self._ensure_connected()

        try:
            result = await session.get_prompt(name, arguments or {})

            return {
                "description": result.description or "",
                "messages": [
                    {
                        "role": m.role,
                        "content": {
                            "type": m.content.type,
                            "text": getattr(m.content, "text", None),
                        },
                    }
                    for m in result.messages
                ],
            }
        except Exception as e:
            self._status = MCPServerStatus.UNHEALTHY
            raise MCPTransportError(f"Failed to get prompt '{name}': {e}") from e

    # ========================================================================
    # Sync wrappers for registry compatibility
    # ========================================================================

    def list_tools_sync(self) -> list[MCPTool]:
        """Synchronous wrapper for list_tools().

        Returns:
            List of MCPTool definitions.
        """
        return asyncio.get_event_loop().run_until_complete(self.list_tools())

    def call_tool_sync(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> MCPToolCallResult:
        """Synchronous wrapper for call_tool().

        Args:
            name: The tool name.
            arguments: Arguments to pass to the tool.

        Returns:
            MCPToolCallResult with the tool output.
        """
        return asyncio.get_event_loop().run_until_complete(self.call_tool(name, arguments))

    def connect_sync(self) -> MCPInitializeResult:
        """Synchronous wrapper for connect().

        Returns:
            MCPInitializeResult with server info and capabilities.
        """
        return asyncio.get_event_loop().run_until_complete(self.connect())

    def close_sync(self) -> None:
        """Synchronous wrapper for close()."""
        asyncio.get_event_loop().run_until_complete(self.close())
