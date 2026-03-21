"""MCP Tool Wrapper with Observability.

Base class for framework-agnostic MCP tool wrapping with integrated tracing.
Provides mock mode support for testing/demos and full observability integration.

Usage:
    from core.mcp.tool_wrapper import MCPToolWrapper, extract_mcp_text

    # Create a wrapper for a specific MCP tool
    wrapper = MCPToolWrapper('github', 'get_repo', 'Get repository info')
    result = wrapper.call(owner='owner', repo='repo')

    # Extract text from raw MCP results
    text = extract_mcp_text(mcp_result)
"""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import get_settings
from core.mcp.protocol import MCPToolCallResult
from core.mcp.registry import get_registry
from core.observability.metrics import record_mcp_tool_call
from core.observability.tracing import trace_event

def extract_mcp_text(result: MCPToolCallResult) -> str:
    """Extract text content from MCP tool call result.

    Iterates through result.content and returns the text from the first
    item with type == "text".

    Args:
        result: MCPToolCallResult from registry.call_tool()

    Returns:
        Text content from the first text item, or empty string if not found.

    Example:
        >>> result = registry.call_tool("git", "git_status", {})
        >>> text = extract_mcp_text(result)
        >>> print(text)
    """
    if result is None or not hasattr(result, "content"):
        return ""

    for item in result.content:
        if hasattr(item, "type") and item.type == "text":
            if hasattr(item, "text") and item.text:
                return item.text
    return ""

def extract_mcp_content(result: MCPToolCallResult) -> dict:
    """Extract all content types from MCP tool call result.

    Returns a dict with both text and image content, preserving
    image data that extract_mcp_text() discards.

    Args:
        result: MCPToolCallResult from registry.call_tool()

    Returns:
        Dict with keys:
          - text: str (concatenated text items)
          - images: list[dict] with keys: data (base64), mimeType, alt_text

    Example:
        >>> result = MCPToolCallResult(content=[
        ...     MCPToolCallContent(type="text", text="Generated image"),
        ...     MCPToolCallContent(type="image", data="iVBORw0KGgo=", mimeType="image/png"),
        ... ])
        >>> content = extract_mcp_content(result)
        >>> assert content["text"] == "Generated image"
        >>> assert len(content["images"]) == 1
    """
    text_parts: list[str] = []
    images: list[dict] = []

    if result is None or not hasattr(result, "content"):
        return {"text": "", "images": []}

    for item in result.content:
        item_type = getattr(item, "type", "text")
        if item_type == "text" and getattr(item, "text", None):
            text_parts.append(item.text)
        elif item_type == "image" and getattr(item, "data", None):
            images.append(
                {
                    "data": item.data,
                    "mimeType": getattr(item, "mimeType", None) or "image/png",
                    "alt_text": "Generated image",
                }
            )

    return {"text": "\n".join(text_parts), "images": images}

class MCPToolWrapper:
    """Framework-agnostic wrapper for MCP tools with observability.

    Wraps MCP registry calls with tracing and mock mode support.
    Use this as a base for framework-specific tool adapters (CrewAI, LangChain, etc.).

    Attributes:
        server_name: Name of the MCP server (e.g., "github", "git").
        tool_name: Name of the tool on the server (e.g., "get_repo", "git_status").
        description: Human-readable description of what the tool does.

    Example:
        >>> wrapper = MCPToolWrapper('github', 'get_repo', 'Get repository info')
        >>> result = wrapper.call(owner='anthropic', repo='anthropic-cookbook')
        >>> print(result)
    """

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str = "",
    ) -> None:
        """Initialize the tool wrapper.

        Args:
            server_name: Name of the MCP server to call.
            tool_name: Name of the tool to invoke.
            description: Optional description for documentation/display.
        """
        self.server_name = server_name
        self.tool_name = tool_name
        self.description = description

    @property
    def _mock_mode(self) -> bool:
        """Check if mock mode is enabled via Settings.

        Returns:
            True if DRYADE_MOCK_MODE=true, False otherwise.
        """
        return get_settings().mock_mode

    def call(self, **kwargs: Any) -> str:
        """Execute the MCP tool with tracing.

        Traces the tool call start and completion, handles errors gracefully,
        and supports mock mode for testing.

        Args:
            **kwargs: Arguments to pass to the MCP tool.

        Returns:
            Text result from the tool, or mock response if in mock mode.

        Raises:
            Exception: Re-raises any exception from the MCP call after tracing.

        Example:
            >>> wrapper = MCPToolWrapper('git', 'git_status', 'Get git status')
            >>> status = wrapper.call(repo_path='/path/to/repo')
        """
        start_time = time.time()
        status = "ok"

        # Trace start
        trace_event(
            "mcp_tool_start",
            tool_name=self.tool_name,
            data={
                "server": self.server_name,
                "args": kwargs,
                "mock_mode": self._mock_mode,
            },
        )

        try:
            # Handle mock mode
            if self._mock_mode:
                result = self._get_mock_response(kwargs)
                duration_ms = (time.time() - start_time) * 1000

                trace_event(
                    "mcp_tool_complete",
                    tool_name=self.tool_name,
                    duration_ms=duration_ms,
                    status="ok",
                    data={
                        "server": self.server_name,
                        "mock": True,
                        "result_length": len(result),
                    },
                )
                return result

            # Real MCP call
            registry = get_registry()
            mcp_result = registry.call_tool(self.server_name, self.tool_name, kwargs)
            result = extract_mcp_text(mcp_result)

            duration_ms = (time.time() - start_time) * 1000

            trace_event(
                "mcp_tool_complete",
                tool_name=self.tool_name,
                duration_ms=duration_ms,
                status="ok",
                data={
                    "server": self.server_name,
                    "result_length": len(result) if result else 0,
                },
            )

            return result

        except Exception as e:
            status = "error"
            duration_ms = (time.time() - start_time) * 1000

            trace_event(
                "mcp_tool_complete",
                tool_name=self.tool_name,
                duration_ms=duration_ms,
                status="error",
                data={
                    "server": self.server_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise
        finally:
            # Record Prometheus metrics (always, even on error)
            record_mcp_tool_call(
                server_name=self.server_name,
                tool_name=self.tool_name,
                status=status,
                duration=time.time() - start_time,
            )

    def _get_mock_response(self, kwargs: dict[str, Any]) -> str:
        """Generate mock response for testing/demos.

        Args:
            kwargs: Arguments that were passed to the tool.

        Returns:
            JSON string with mock response data.
        """
        return json.dumps(
            {
                "mock": True,
                "server": self.server_name,
                "tool": self.tool_name,
                "args": kwargs,
            },
            indent=2,
        )

    def __repr__(self) -> str:
        """Return string representation of the wrapper."""
        return f"MCPToolWrapper({self.server_name!r}, {self.tool_name!r})"
