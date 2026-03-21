"""Unit tests for Context7 MCP server wrapper."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.mcp.config import MCPServerTransport
from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.context7 import (
    Context7Server,
    DocChunk,
    LibraryInfo,
    create_context7_server,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock()
    registry.is_registered.return_value = False
    return registry

@pytest.fixture
def mock_result_text():
    """Create a factory for MCPToolCallResult with text content."""

    def _make_result(text: str, is_error: bool = False) -> MCPToolCallResult:
        return MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text=text)],
            isError=is_error,
        )

    return _make_result

@pytest.fixture
def mock_result_empty():
    """Create an empty MCPToolCallResult."""
    return MCPToolCallResult(content=[], isError=False)

# ============================================================================
# Context7Server Config Tests
# ============================================================================

class TestContext7ServerConfig:
    """Tests for configuration generation."""

    def test_config_without_api_key(self):
        """Test config without API key."""
        config = Context7Server.get_config()

        assert config.name == "context7"
        assert config.transport == MCPServerTransport.HTTP
        assert config.url == "https://mcp.context7.com/mcp"
        assert config.auth_type == "none"
        assert config.headers == {}

    def test_config_with_api_key(self):
        """Test config with API key adds header."""
        config = Context7Server.get_config(api_key="test-api-key")

        assert config.auth_type == "api_key"
        assert config.headers.get("X-Api-Key") == "test-api-key"
        assert config.credential_service == "dryade-mcp-context7"

# ============================================================================
# Context7Server Initialization Tests
# ============================================================================

class TestContext7ServerInit:
    """Tests for Context7Server initialization."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'context7'."""
        server = Context7Server(mock_registry)

        assert server._server_name == "context7"
        assert server._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        server = Context7Server(mock_registry, server_name="custom-context7")

        assert server._server_name == "custom-context7"

# ============================================================================
# LibraryInfo Tests
# ============================================================================

class TestLibraryInfo:
    """Tests for LibraryInfo dataclass."""

    def test_from_text_path_format(self):
        """Test parsing path-style library ID."""
        info = LibraryInfo.from_text("/react/18.2.0", "react")

        assert info is not None
        assert info.library_id == "/react/18.2.0"
        assert info.name == "react"
        assert info.version == "18.2.0"

    def test_from_text_path_format_latest(self):
        """Test parsing path with only library name."""
        info = LibraryInfo.from_text("/react", "react")

        assert info is not None
        assert info.library_id == "/react"
        assert info.name == "react"
        assert info.version == "latest"

    def test_from_text_json_dict(self):
        """Test parsing JSON dict response."""
        text = json.dumps(
            {
                "libraryId": "/fastapi/0.100.0",
                "name": "fastapi",
                "version": "0.100.0",
                "description": "Modern Python web framework",
            }
        )
        info = LibraryInfo.from_text(text, "fastapi")

        assert info is not None
        assert info.library_id == "/fastapi/0.100.0"
        assert info.name == "fastapi"
        assert info.version == "0.100.0"
        assert info.description == "Modern Python web framework"

    def test_from_text_json_list(self):
        """Test parsing JSON list response (takes first)."""
        text = json.dumps(
            [
                {"libraryId": "/react/18.2.0", "name": "react", "version": "18.2.0"},
                {"libraryId": "/react/17.0.0", "name": "react", "version": "17.0.0"},
            ]
        )
        info = LibraryInfo.from_text(text, "react")

        assert info is not None
        assert info.library_id == "/react/18.2.0"
        assert info.version == "18.2.0"

    def test_from_text_not_found(self):
        """Test returns None for not found."""
        assert LibraryInfo.from_text("Library not found", "unknown") is None
        assert LibraryInfo.from_text("error: no match", "unknown") is None
        assert LibraryInfo.from_text("", "unknown") is None

    def test_from_text_plain_string(self):
        """Test parsing plain string as library ID."""
        info = LibraryInfo.from_text("some-library-id", "mylib")

        assert info is not None
        assert info.library_id == "some-library-id"
        assert info.name == "mylib"
        assert info.version == "latest"

# ============================================================================
# DocChunk Tests
# ============================================================================

class TestDocChunk:
    """Tests for DocChunk dataclass."""

    def test_from_dict_full(self):
        """Test creating DocChunk from full dict."""
        data = {
            "content": "Documentation text here",
            "source": "https://docs.example.com/page",
            "relevance": 0.95,
        }
        chunk = DocChunk.from_dict(data)

        assert chunk.content == "Documentation text here"
        assert chunk.source == "https://docs.example.com/page"
        assert chunk.relevance == 0.95

    def test_from_dict_alternative_keys(self):
        """Test creating DocChunk with alternative key names."""
        data = {
            "text": "Alt content",
            "url": "https://alt.source.com",
            "score": 0.8,
        }
        chunk = DocChunk.from_dict(data)

        assert chunk.content == "Alt content"
        assert chunk.source == "https://alt.source.com"
        assert chunk.relevance == 0.8

    def test_from_dict_minimal(self):
        """Test creating DocChunk with minimal data."""
        chunk = DocChunk.from_dict({})

        assert chunk.content == ""
        assert chunk.source == ""
        assert chunk.relevance == 1.0

    def test_from_text_json_array(self):
        """Test parsing JSON array of chunks."""
        text = json.dumps(
            [
                {"content": "Chunk 1", "source": "src1"},
                {"content": "Chunk 2", "source": "src2"},
            ]
        )
        chunks = DocChunk.from_text(text)

        assert len(chunks) == 2
        assert chunks[0].content == "Chunk 1"
        assert chunks[1].content == "Chunk 2"

    def test_from_text_json_single(self):
        """Test parsing single JSON object."""
        text = json.dumps({"content": "Single chunk", "source": "single-src"})
        chunks = DocChunk.from_text(text)

        assert len(chunks) == 1
        assert chunks[0].content == "Single chunk"

    def test_from_text_plain(self):
        """Test parsing plain text as single chunk."""
        text = "This is plain documentation text without JSON formatting."
        chunks = DocChunk.from_text(text)

        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_from_text_empty(self):
        """Test parsing empty text."""
        assert DocChunk.from_text("") == []
        assert DocChunk.from_text(None) == []

# ============================================================================
# Context7Server Operations Tests
# ============================================================================

class TestContext7ServerOperations:
    """Tests for documentation operations."""

    @pytest.fixture
    def server(self, mock_registry):
        mock_registry.is_registered.return_value = True
        return Context7Server(mock_registry)

    @pytest.mark.asyncio
    async def test_resolve_library(self, server, mock_registry, mock_result_text):
        """Test resolve_library returns LibraryInfo."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("/react/18.2.0"))

        lib = await server.resolve_library("react")

        assert lib is not None
        assert lib.library_id == "/react/18.2.0"
        mock_registry.acall_tool.assert_called_once_with(
            "context7", "resolve-library-id", {"libraryName": "react"}
        )

    @pytest.mark.asyncio
    async def test_resolve_library_not_found(self, server, mock_registry, mock_result_text):
        """Test resolve_library returns None when not found."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("Library not found"))

        lib = await server.resolve_library("nonexistent-lib")

        assert lib is None

    @pytest.mark.asyncio
    async def test_get_library_docs(self, server, mock_registry, mock_result_text):
        """Test get_library_docs returns DocChunks."""
        docs_text = json.dumps(
            [
                {"content": "useEffect is a React Hook...", "source": "hooks.md"},
            ]
        )
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text(docs_text))

        docs = await server.get_library_docs("/react/18.2.0", "useEffect")

        assert len(docs) == 1
        assert "useEffect" in docs[0].content
        mock_registry.acall_tool.assert_called_once_with(
            "context7",
            "get-library-docs",
            {
                "context7CompatibleLibraryID": "/react/18.2.0",
                "topic": "useEffect",
                "tokens": 5000,
            },
        )

    @pytest.mark.asyncio
    async def test_get_library_docs_custom_tokens(self, server, mock_registry, mock_result_text):
        """Test get_library_docs with custom token limit."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("Documentation"))

        await server.get_library_docs("/lib/1.0", "topic", tokens=10000)

        call_args = mock_registry.acall_tool.call_args[0][2]
        assert call_args["tokens"] == 10000

    @pytest.mark.asyncio
    async def test_query_docs_success(self, server, mock_registry, mock_result_text):
        """Test query_docs convenience method."""
        # First call resolves library
        mock_registry.acall_tool = AsyncMock(
            side_effect=[
                mock_result_text("/fastapi/0.100.0"),
                mock_result_text("FastAPI documentation for routing..."),
            ]
        )

        docs = await server.query_docs("fastapi", "routing")

        assert len(docs) == 1
        assert "FastAPI" in docs[0].content
        assert mock_registry.acall_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_query_docs_library_not_found(self, server, mock_registry, mock_result_text):
        """Test query_docs returns empty when library not found."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("Library not found"))

        docs = await server.query_docs("nonexistent", "topic")

        assert docs == []
        mock_registry.acall_tool.assert_called_once()  # Only resolve call

# ============================================================================
# Factory Function Tests
# ============================================================================

class TestCreateContext7Server:
    """Tests for factory function."""

    def test_create_context7_server_default(self, mock_registry):
        """Test factory creates server with default config."""
        server = create_context7_server(mock_registry)

        assert isinstance(server, Context7Server)
        mock_registry.register.assert_called_once()
        config = mock_registry.register.call_args[0][0]
        assert config.transport == MCPServerTransport.HTTP
        assert config.auth_type == "none"

    def test_create_context7_server_with_api_key(self, mock_registry):
        """Test factory creates server with API key."""
        server = create_context7_server(mock_registry, api_key="secret-key")

        assert isinstance(server, Context7Server)
        config = mock_registry.register.call_args[0][0]
        assert config.auth_type == "api_key"
        assert config.headers.get("X-Api-Key") == "secret-key"

    def test_create_context7_server_skip_registration(self, mock_registry):
        """Test factory skips registration when already registered."""
        mock_registry.is_registered.return_value = True

        server = create_context7_server(mock_registry)

        assert isinstance(server, Context7Server)
        mock_registry.register.assert_not_called()

    def test_create_context7_server_no_auto_register(self, mock_registry):
        """Test factory skips registration when auto_register=False."""
        server = create_context7_server(mock_registry, auto_register=False)

        assert isinstance(server, Context7Server)
        mock_registry.register.assert_not_called()
