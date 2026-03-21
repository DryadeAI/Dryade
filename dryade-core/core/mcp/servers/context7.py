"""Context7 MCP Server Wrapper.

Provides typed Python API for library documentation lookup.
Uses HTTP transport to Context7's hosted MCP endpoint.

Tools:
- resolve-library-id: Match library name to Context7 ID
- get-library-docs: Get version-specific documentation chunks
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

from core.mcp.config import MCPServerConfig, MCPServerTransport

logger = logging.getLogger(__name__)

@dataclass
class LibraryInfo:
    """Resolved library information."""

    library_id: str
    name: str
    version: str
    description: str | None = None

    @classmethod
    def from_text(cls, text: str, library_name: str) -> LibraryInfo | None:
        """Parse LibraryInfo from Context7 resolve response.

        The response format is typically the library ID path like:
        /react/18.2.0 or just the library ID.

        Args:
            text: Response text from resolve-library-id.
            library_name: Original library name for reference.

        Returns:
            LibraryInfo or None if text indicates not found.
        """
        if not text or "not found" in text.lower() or "error" in text.lower():
            return None

        # Try to parse as JSON first
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return cls(
                    library_id=data.get("libraryId", data.get("id", text.strip())),
                    name=data.get("name", library_name),
                    version=data.get("version", "latest"),
                    description=data.get("description"),
                )
            if isinstance(data, list) and data:
                # Take first result
                first = data[0]
                if isinstance(first, dict):
                    return cls(
                        library_id=first.get("libraryId", first.get("id", "")),
                        name=first.get("name", library_name),
                        version=first.get("version", "latest"),
                        description=first.get("description"),
                    )
        except json.JSONDecodeError:
            pass

        # Parse text format like "/react/18.2.0"
        text = text.strip()
        if text.startswith("/"):
            parts = text.split("/")
            if len(parts) >= 2:
                name = parts[1] if len(parts) > 1 else library_name
                version = parts[2] if len(parts) > 2 else "latest"
                return cls(
                    library_id=text,
                    name=name,
                    version=version,
                    description=None,
                )

        # Fallback: use text as library_id
        return cls(
            library_id=text,
            name=library_name,
            version="latest",
            description=None,
        )

@dataclass
class DocChunk:
    """Documentation chunk from Context7."""

    content: str
    source: str = ""
    relevance: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocChunk:
        """Create DocChunk from response dict."""
        return cls(
            content=data.get("content", data.get("text", "")),
            source=data.get("source", data.get("url", "")),
            relevance=data.get("relevance", data.get("score", 1.0)),
        )

    @classmethod
    def from_text(cls, text: str) -> list[DocChunk]:
        """Parse DocChunks from text response.

        Context7 may return plain text, markdown, or JSON array.

        Args:
            text: Response text from get-library-docs.

        Returns:
            List of DocChunk objects.
        """
        if not text:
            return []

        # Try JSON array first
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [
                    cls.from_dict(item) if isinstance(item, dict) else cls(content=str(item))
                    for item in data
                ]
            if isinstance(data, dict):
                # Single chunk
                return [cls.from_dict(data)]
        except json.JSONDecodeError:
            pass

        # Treat as single text chunk
        return [cls(content=text)]

class Context7Server:
    """Typed wrapper for Context7 MCP server.

    Provides library documentation lookup for coding agents.
    Uses Context7's free hosted endpoint (API key optional for higher limits).

    Usage:
        server = Context7Server(registry)
        lib = await server.resolve_library("react")
        docs = await server.get_library_docs(lib.library_id, "useEffect")
    """

    SERVER_NAME = "context7"
    DEFAULT_URL = "https://mcp.context7.com/mcp"

    def __init__(self, registry: MCPRegistry, server_name: str | None = None) -> None:
        """Initialize Context7Server wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the Context7 server in registry (default: "context7").
        """
        self._registry = registry
        self._server_name = server_name or self.SERVER_NAME

    @classmethod
    def get_config(cls, api_key: str | None = None) -> MCPServerConfig:
        """Get Context7 server configuration.

        Args:
            api_key: Optional API key for higher rate limits.

        Returns:
            MCPServerConfig for Context7 HTTP endpoint.
        """
        headers: dict[str, str] = {}
        if api_key:
            headers["X-Api-Key"] = api_key

        return MCPServerConfig(
            name=cls.SERVER_NAME,
            command=[],
            transport=MCPServerTransport.HTTP,
            url=cls.DEFAULT_URL,
            headers=headers,
            auth_type="api_key" if api_key else "none",
            credential_service="dryade-mcp-context7",
            timeout=30.0,
        )

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""

    async def resolve_library(self, library_name: str) -> LibraryInfo | None:
        """Resolve library name to Context7 library ID.

        ALWAYS call this before get_library_docs to get correct library ID.

        Args:
            library_name: Common library name (e.g., "react", "fastapi")

        Returns:
            LibraryInfo with library_id for get_library_docs, or None if not found.
        """
        result = await self._registry.acall_tool(
            self._server_name,
            "resolve-library-id",
            {"libraryName": library_name},
        )
        text = self._extract_text(result)
        return LibraryInfo.from_text(text, library_name)

    async def get_library_docs(
        self,
        library_id: str,
        topic: str,
        tokens: int = 5000,
    ) -> list[DocChunk]:
        """Get documentation for a library topic.

        Args:
            library_id: Library ID from resolve_library (e.g., "/react/latest")
            topic: Documentation topic to fetch (e.g., "useEffect cleanup function")
            tokens: Maximum tokens to return (default 5000)

        Returns:
            List of relevant documentation chunks.
        """
        result = await self._registry.acall_tool(
            self._server_name,
            "get-library-docs",
            {
                "context7CompatibleLibraryID": library_id,
                "topic": topic,
                "tokens": tokens,
            },
        )
        text = self._extract_text(result)
        return DocChunk.from_text(text)

    async def query_docs(
        self,
        library_name: str,
        query: str,
        tokens: int = 5000,
    ) -> list[DocChunk]:
        """Convenience method: resolve library and query in one call.

        Args:
            library_name: Common library name (e.g., "react", "fastapi")
            query: Documentation search query

        Returns:
            Documentation chunks, or empty list if library not found.
        """
        lib = await self.resolve_library(library_name)
        if not lib:
            logger.warning("Library not found: %s", library_name)
            return []
        return await self.get_library_docs(lib.library_id, query, tokens)

def create_context7_server(
    registry: MCPRegistry,
    api_key: str | None = None,
    auto_register: bool = True,
) -> Context7Server:
    """Factory function to create Context7Server.

    Args:
        registry: MCP registry instance.
        api_key: Optional API key for higher rate limits.
        auto_register: Automatically register config with registry.

    Returns:
        Configured Context7Server instance.
    """
    config = Context7Server.get_config(api_key)
    if auto_register and not registry.is_registered(config.name):
        registry.register(config)
    return Context7Server(registry)
