"""Filesystem MCP Server wrapper.

Provides typed Python interface for @modelcontextprotocol/server-filesystem
file operations with secure directory access control.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

class FilesystemServer:
    """Typed wrapper for @modelcontextprotocol/server-filesystem MCP server.

    Provides typed Python methods for all 14 filesystem operations.
    Delegates to MCPRegistry for actual MCP communication.

    The Filesystem server provides secure file operations with configurable
    access control via allowed directories.

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="filesystem",
        ...     command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        ... )
        >>> registry.register(config)
        >>> fs = FilesystemServer(registry)
        >>> content = fs.read_text_file("/tmp/test.txt")
    """

    def __init__(self, registry: MCPRegistry, server_name: str = "filesystem") -> None:
        """Initialize FilesystemServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the filesystem server in registry (default: "filesystem").
        """
        self._registry = registry
        self._server_name = server_name

    def read_text_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents as text with encoding support.

        Args:
            path: Absolute path to the file to read.
            encoding: Character encoding (default: "utf-8").

        Returns:
            File contents as a string.

        Raises:
            MCPTransportError: If the file cannot be read.
        """
        result = self._registry.call_tool(
            self._server_name,
            "read_text_file",
            {"path": path, "encoding": encoding},
        )
        return self._extract_text(result)

    def read_media_file(self, path: str) -> bytes:
        """Read image/audio files as binary data.

        The MCP server returns base64-encoded content which is decoded
        to raw bytes.

        Args:
            path: Absolute path to the media file.

        Returns:
            File contents as bytes.

        Raises:
            MCPTransportError: If the file cannot be read.
        """
        result = self._registry.call_tool(self._server_name, "read_media_file", {"path": path})
        text = self._extract_text(result)
        return base64.b64decode(text)

    def read_multiple_files(self, paths: list[str]) -> dict[str, str]:
        """Read multiple files simultaneously.

        Args:
            paths: List of absolute paths to files.

        Returns:
            Dict mapping file paths to their contents.

        Raises:
            MCPTransportError: If any file cannot be read.
        """
        result = self._registry.call_tool(
            self._server_name, "read_multiple_files", {"paths": paths}
        )
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return {}

    def write_file(self, path: str, content: str) -> None:
        """Create or overwrite a file.

        Args:
            path: Absolute path to the file to write.
            content: Content to write to the file.

        Raises:
            MCPTransportError: If the file cannot be written.
        """
        self._registry.call_tool(
            self._server_name, "write_file", {"path": path, "content": content}
        )

    def edit_file(self, path: str, edits: list[dict[str, str]]) -> str:
        """Make line-based edits to text files.

        Args:
            path: Absolute path to the file to edit.
            edits: List of edits, each with "oldText" and "newText" keys.

        Returns:
            Result message from the server.

        Raises:
            MCPTransportError: If the file cannot be edited.

        Example:
            >>> fs.edit_file("/tmp/test.txt", [
            ...     {"oldText": "old content", "newText": "new content"}
            ... ])
        """
        result = self._registry.call_tool(
            self._server_name, "edit_file", {"path": path, "edits": edits}
        )
        return self._extract_text(result)

    def create_directory(self, path: str) -> None:
        """Create a directory (nested directories supported).

        Args:
            path: Absolute path to the directory to create.

        Raises:
            MCPTransportError: If the directory cannot be created.
        """
        self._registry.call_tool(self._server_name, "create_directory", {"path": path})

    def list_directory(self, path: str) -> list[str]:
        """List directory contents with [FILE]/[DIR] prefixes.

        Args:
            path: Absolute path to the directory.

        Returns:
            List of entries like "[FILE] name.txt" or "[DIR] subdir".

        Raises:
            MCPTransportError: If the directory cannot be listed.
        """
        result = self._registry.call_tool(self._server_name, "list_directory", {"path": path})
        text = self._extract_text(result)
        return text.strip().split("\n") if text.strip() else []

    def list_directory_with_sizes(self, path: str) -> str:
        """List directory contents with file sizes.

        Args:
            path: Absolute path to the directory.

        Returns:
            Formatted string with entries and their sizes.

        Raises:
            MCPTransportError: If the directory cannot be listed.
        """
        result = self._registry.call_tool(
            self._server_name, "list_directory_with_sizes", {"path": path}
        )
        return self._extract_text(result)

    def directory_tree(self, path: str) -> dict:
        """Get recursive JSON tree view of a directory.

        Args:
            path: Absolute path to the directory.

        Returns:
            Dict representing the directory tree structure.

        Raises:
            MCPTransportError: If the directory tree cannot be generated.
        """
        result = self._registry.call_tool(self._server_name, "directory_tree", {"path": path})
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return {}

    def move_file(self, source: str, destination: str) -> None:
        """Move or rename a file.

        Args:
            source: Absolute path to the source file.
            destination: Absolute path to the destination.

        Raises:
            MCPTransportError: If the file cannot be moved.
        """
        self._registry.call_tool(
            self._server_name,
            "move_file",
            {"source": source, "destination": destination},
        )

    def search_files(
        self,
        path: str,
        pattern: str,
        exclude_patterns: list[str] | None = None,
    ) -> list[str]:
        """Search for files matching glob patterns.

        Args:
            path: Absolute path to the directory to search in.
            pattern: Glob pattern to match files against.
                Use ``**`` for recursive search (e.g. ``**/*.py``).
            exclude_patterns: Optional list of glob patterns to exclude
                from results (e.g. ``["node_modules/**", ".git/**"]``).

        Returns:
            List of matching file paths.

        Raises:
            MCPTransportError: If the search fails.
        """
        args: dict = {"path": path, "pattern": pattern}
        if exclude_patterns:
            args["excludePatterns"] = exclude_patterns
        result = self._registry.call_tool(self._server_name, "search_files", args)
        text = self._extract_text(result)
        return text.strip().split("\n") if text.strip() else []

    def get_file_info(self, path: str) -> dict:
        """Get detailed file metadata.

        Args:
            path: Absolute path to the file.

        Returns:
            Dict with file metadata (size, mtime, ctime, etc.).

        Raises:
            MCPTransportError: If the file info cannot be retrieved.
        """
        result = self._registry.call_tool(self._server_name, "get_file_info", {"path": path})
        text = self._extract_text(result)
        if text:
            return json.loads(text)
        return {}

    def list_allowed_directories(self) -> list[str]:
        """List configured allowed directories.

        Returns:
            List of directory paths that the server can access.

        Raises:
            MCPTransportError: If the list cannot be retrieved.
        """
        result = self._registry.call_tool(self._server_name, "list_allowed_directories", {})
        text = self._extract_text(result)
        return text.strip().split("\n") if text.strip() else []

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
