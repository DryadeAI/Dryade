"""Playwright MCP Server Wrapper.

Provides typed Python API for browser automation via MCP.
Uses stdio transport with Microsoft's official Playwright MCP server.

Tools provided by Playwright MCP:
- Navigation: goto, click, fill, hover, select
- Screenshots: capture page or element
- PDF: generate PDF from page
- Accessibility: get accessibility tree
- Code generation: record actions for automation scripts
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from core.mcp.registry import MCPRegistry

from core.mcp.config import MCPServerConfig, MCPServerTransport
from core.mcp.protocol import MCPToolCallResult

logger = logging.getLogger(__name__)

@dataclass
class BrowserSession:
    """Active browser session information."""

    session_id: str
    url: str
    title: str

@dataclass
class Screenshot:
    """Screenshot result."""

    data: bytes
    mime_type: str = "image/png"

    def save(self, path: str) -> None:
        """Save screenshot to file."""
        with open(path, "wb") as f:
            f.write(self.data)

@dataclass
class AccessibilityNode:
    """Accessibility tree node."""

    role: str
    name: str
    children: list[AccessibilityNode]

class PlaywrightServer:
    """Typed wrapper for Playwright MCP server.

    Provides browser automation for E2E testing. Uses stdio transport
    with Microsoft's official Playwright MCP package.

    Usage:
        server = PlaywrightServer(registry)
        await server.goto("https://example.com")
        await server.click("button#submit")
        screenshot = await server.screenshot()
        screenshot.save("result.png")
    """

    SERVER_NAME = "playwright"

    def __init__(self, registry: MCPRegistry, server_name: str | None = None):
        """Initialize PlaywrightServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the playwright server in registry (default: "playwright").
        """
        self._registry = registry
        self._server_name = server_name or self.SERVER_NAME

    @classmethod
    def get_config(
        cls,
        headless: bool = True,
        browser: Literal["chromium", "firefox", "webkit"] = "chromium",
    ) -> MCPServerConfig:
        """Get Playwright server configuration.

        Args:
            headless: Run browser in headless mode.
            browser: Browser to use (chromium, firefox, webkit).
        """
        command = ["npx", "@playwright/mcp@latest"]
        if headless:
            command.append("--headless")
        command.extend(["--browser", browser])

        return MCPServerConfig(
            name=cls.SERVER_NAME,
            command=command,
            transport=MCPServerTransport.STDIO,
            timeout=300.0,  # Browser operations can be slow
            startup_delay=5.0,  # Browser initialization takes time
        )

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from tool call result."""
        if not result.content:
            return ""
        for item in result.content:
            if item.type == "text" and item.text:
                return item.text
        return ""

    def _extract_binary(self, result: MCPToolCallResult) -> bytes | None:
        """Extract binary content (e.g., screenshot data)."""
        if not result.content:
            return None
        for item in result.content:
            if item.data:
                # Assume base64 encoded
                return base64.b64decode(item.data)
        return None

    # Navigation
    async def goto(self, url: str) -> None:
        """Navigate to URL.

        Args:
            url: The URL to navigate to.
        """
        await self._registry.acall_tool(self._server_name, "playwright_navigate", {"url": url})

    async def click(self, selector: str) -> None:
        """Click element by selector.

        Args:
            selector: CSS selector for the element to click.
        """
        await self._registry.acall_tool(
            self._server_name, "playwright_click", {"selector": selector}
        )

    async def fill(self, selector: str, value: str) -> None:
        """Fill input field.

        Args:
            selector: CSS selector for the input element.
            value: Text to fill into the input.
        """
        await self._registry.acall_tool(
            self._server_name,
            "playwright_fill",
            {"selector": selector, "value": value},
        )

    async def hover(self, selector: str) -> None:
        """Hover over element.

        Args:
            selector: CSS selector for the element to hover over.
        """
        await self._registry.acall_tool(
            self._server_name, "playwright_hover", {"selector": selector}
        )

    async def select(self, selector: str, value: str) -> None:
        """Select option in dropdown.

        Args:
            selector: CSS selector for the select element.
            value: Value of the option to select.
        """
        await self._registry.acall_tool(
            self._server_name,
            "playwright_select_option",
            {"selector": selector, "value": value},
        )

    # Screenshots and PDF
    async def screenshot(self, full_page: bool = False) -> Screenshot:
        """Take screenshot of current page.

        Args:
            full_page: Whether to capture the full scrollable page.

        Returns:
            Screenshot object containing image data.
        """
        result = await self._registry.acall_tool(
            self._server_name, "playwright_screenshot", {"fullPage": full_page}
        )
        data = self._extract_binary(result)
        return Screenshot(data=data or b"")

    async def screenshot_element(self, selector: str) -> Screenshot:
        """Take screenshot of specific element.

        Args:
            selector: CSS selector for the element to capture.

        Returns:
            Screenshot object containing image data.
        """
        result = await self._registry.acall_tool(
            self._server_name, "playwright_screenshot", {"selector": selector}
        )
        data = self._extract_binary(result)
        return Screenshot(data=data or b"")

    async def pdf(self) -> bytes:
        """Generate PDF of current page.

        Returns:
            PDF file contents as bytes.
        """
        result = await self._registry.acall_tool(self._server_name, "playwright_pdf", {})
        return self._extract_binary(result) or b""

    # Accessibility
    async def get_accessibility_tree(self) -> str:
        """Get accessibility tree of current page.

        Returns text representation for LLM analysis.

        Returns:
            Text representation of the accessibility tree.
        """
        result = await self._registry.acall_tool(self._server_name, "playwright_snapshot", {})
        return self._extract_text(result)

    # Page info
    async def get_title(self) -> str:
        """Get current page title.

        Returns:
            The page title.
        """
        result = await self._registry.acall_tool(self._server_name, "playwright_get_title", {})
        return self._extract_text(result)

    async def get_url(self) -> str:
        """Get current page URL.

        Returns:
            The current URL.
        """
        result = await self._registry.acall_tool(self._server_name, "playwright_get_url", {})
        return self._extract_text(result)

def create_playwright_server(
    registry: MCPRegistry,
    headless: bool = True,
    browser: Literal["chromium", "firefox", "webkit"] = "chromium",
    auto_register: bool = True,
) -> PlaywrightServer:
    """Factory function to create PlaywrightServer.

    Args:
        registry: MCP registry instance.
        headless: Run browser in headless mode.
        browser: Browser to use.
        auto_register: Automatically register config with registry.

    Returns:
        Configured PlaywrightServer instance.
    """
    config = PlaywrightServer.get_config(headless=headless, browser=browser)
    if auto_register and not registry.is_registered(config.name):
        registry.register(config)
    return PlaywrightServer(registry)
