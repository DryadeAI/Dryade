"""Unit tests for Playwright MCP server wrapper."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.mcp import MCPRegistry, MCPServerTransport
from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.playwright import (
    PlaywrightServer,
    Screenshot,
    create_playwright_server,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock(spec=MCPRegistry)
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
def mock_result_binary():
    """Create a factory for MCPToolCallResult with binary content."""

    def _make_result(data: bytes, is_error: bool = False) -> MCPToolCallResult:
        encoded = base64.b64encode(data).decode()
        return MCPToolCallResult(
            content=[MCPToolCallContent(type="image", data=encoded)],
            isError=is_error,
        )

    return _make_result

@pytest.fixture
def server(mock_registry):
    """Create a PlaywrightServer with mocked registry."""
    mock_registry.is_registered.return_value = True
    return PlaywrightServer(mock_registry)

# ============================================================================
# Configuration Tests
# ============================================================================

class TestPlaywrightServerConfig:
    """Tests for configuration generation."""

    def test_config_headless_default(self):
        """Test config with default headless mode."""
        config = PlaywrightServer.get_config()
        assert config.name == "playwright"
        assert "--headless" in config.command
        assert config.timeout == 300.0
        assert config.transport == MCPServerTransport.STDIO

    def test_config_headed(self):
        """Test config with headed mode."""
        config = PlaywrightServer.get_config(headless=False)
        assert "--headless" not in config.command

    def test_config_firefox(self):
        """Test config with Firefox browser."""
        config = PlaywrightServer.get_config(browser="firefox")
        assert "--browser" in config.command
        idx = config.command.index("--browser")
        assert config.command[idx + 1] == "firefox"

    def test_config_webkit(self):
        """Test config with WebKit browser."""
        config = PlaywrightServer.get_config(browser="webkit")
        assert "--browser" in config.command
        idx = config.command.index("--browser")
        assert config.command[idx + 1] == "webkit"

    def test_config_chromium_default(self):
        """Test config defaults to Chromium browser."""
        config = PlaywrightServer.get_config()
        assert "--browser" in config.command
        idx = config.command.index("--browser")
        assert config.command[idx + 1] == "chromium"

    def test_config_startup_delay(self):
        """Test config has appropriate startup delay."""
        config = PlaywrightServer.get_config()
        assert config.startup_delay == 5.0  # Browser initialization takes time

# ============================================================================
# Factory Function Tests
# ============================================================================

class TestCreatePlaywrightServer:
    """Tests for factory function."""

    def test_creates_server(self, mock_registry):
        """Test factory creates PlaywrightServer instance."""
        server = create_playwright_server(mock_registry)
        assert isinstance(server, PlaywrightServer)
        assert server._server_name == "playwright"

    def test_auto_register(self, mock_registry):
        """Test factory auto-registers with registry."""
        mock_registry.is_registered.return_value = False
        create_playwright_server(mock_registry)
        mock_registry.register.assert_called_once()

    def test_skip_register_if_exists(self, mock_registry):
        """Test factory skips registration if already registered."""
        mock_registry.is_registered.return_value = True
        create_playwright_server(mock_registry)
        mock_registry.register.assert_not_called()

    def test_auto_register_false(self, mock_registry):
        """Test factory respects auto_register=False."""
        create_playwright_server(mock_registry, auto_register=False)
        mock_registry.register.assert_not_called()

# ============================================================================
# Navigation Tests
# ============================================================================

class TestPlaywrightServerNavigation:
    """Tests for navigation operations."""

    @pytest.mark.asyncio
    async def test_goto(self, server, mock_registry):
        """Test goto navigates to URL."""
        mock_registry.acall_tool = AsyncMock()
        await server.goto("https://example.com")
        mock_registry.acall_tool.assert_called_once_with(
            "playwright", "playwright_navigate", {"url": "https://example.com"}
        )

    @pytest.mark.asyncio
    async def test_click(self, server, mock_registry):
        """Test click sends correct selector."""
        mock_registry.acall_tool = AsyncMock()
        await server.click("button#submit")
        mock_registry.acall_tool.assert_called_once_with(
            "playwright", "playwright_click", {"selector": "button#submit"}
        )

    @pytest.mark.asyncio
    async def test_fill(self, server, mock_registry):
        """Test fill sends selector and value."""
        mock_registry.acall_tool = AsyncMock()
        await server.fill("input#email", "test@example.com")
        mock_registry.acall_tool.assert_called_once_with(
            "playwright",
            "playwright_fill",
            {"selector": "input#email", "value": "test@example.com"},
        )

    @pytest.mark.asyncio
    async def test_hover(self, server, mock_registry):
        """Test hover sends correct selector."""
        mock_registry.acall_tool = AsyncMock()
        await server.hover("a.link")
        mock_registry.acall_tool.assert_called_once_with(
            "playwright", "playwright_hover", {"selector": "a.link"}
        )

    @pytest.mark.asyncio
    async def test_select(self, server, mock_registry):
        """Test select sends selector and value."""
        mock_registry.acall_tool = AsyncMock()
        await server.select("select#country", "US")
        mock_registry.acall_tool.assert_called_once_with(
            "playwright",
            "playwright_select_option",
            {"selector": "select#country", "value": "US"},
        )

# ============================================================================
# Screenshot and PDF Tests
# ============================================================================

class TestPlaywrightServerScreenshots:
    """Tests for screenshot and PDF operations."""

    @pytest.mark.asyncio
    async def test_screenshot(self, server, mock_registry, mock_result_binary):
        """Test screenshot returns Screenshot object."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_binary(b"PNG data"))
        screenshot = await server.screenshot()
        assert isinstance(screenshot, Screenshot)
        assert screenshot.data == b"PNG data"
        assert screenshot.mime_type == "image/png"

    @pytest.mark.asyncio
    async def test_screenshot_full_page(self, server, mock_registry, mock_result_binary):
        """Test full page screenshot passes fullPage parameter."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_binary(b"PNG data"))
        await server.screenshot(full_page=True)
        mock_registry.acall_tool.assert_called_once_with(
            "playwright", "playwright_screenshot", {"fullPage": True}
        )

    @pytest.mark.asyncio
    async def test_screenshot_element(self, server, mock_registry, mock_result_binary):
        """Test element screenshot passes selector."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_binary(b"PNG data"))
        await server.screenshot_element("div#content")
        mock_registry.acall_tool.assert_called_once_with(
            "playwright", "playwright_screenshot", {"selector": "div#content"}
        )

    @pytest.mark.asyncio
    async def test_pdf(self, server, mock_registry, mock_result_binary):
        """Test pdf returns bytes."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_binary(b"PDF data"))
        pdf_data = await server.pdf()
        assert pdf_data == b"PDF data"
        mock_registry.acall_tool.assert_called_once_with("playwright", "playwright_pdf", {})

# ============================================================================
# Screenshot Helper Tests
# ============================================================================

class TestScreenshot:
    """Tests for Screenshot helper class."""

    def test_screenshot_init(self):
        """Test Screenshot initialization."""
        screenshot = Screenshot(data=b"test data")
        assert screenshot.data == b"test data"
        assert screenshot.mime_type == "image/png"

    def test_screenshot_custom_mime(self):
        """Test Screenshot with custom mime type."""
        screenshot = Screenshot(data=b"test", mime_type="image/jpeg")
        assert screenshot.mime_type == "image/jpeg"

    def test_screenshot_save(self, tmp_path):
        """Test Screenshot save to file."""
        screenshot = Screenshot(data=b"test image data")
        filepath = tmp_path / "test.png"
        screenshot.save(str(filepath))
        assert filepath.read_bytes() == b"test image data"

# ============================================================================
# Accessibility Tests
# ============================================================================

class TestPlaywrightServerAccessibility:
    """Tests for accessibility operations."""

    @pytest.mark.asyncio
    async def test_get_accessibility_tree(self, server, mock_registry, mock_result_text):
        """Test get_accessibility_tree returns text."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text("role: document, name: Page")
        )
        tree = await server.get_accessibility_tree()
        assert tree == "role: document, name: Page"
        mock_registry.acall_tool.assert_called_once_with("playwright", "playwright_snapshot", {})

# ============================================================================
# Page Info Tests
# ============================================================================

class TestPlaywrightServerPageInfo:
    """Tests for page info operations."""

    @pytest.mark.asyncio
    async def test_get_title(self, server, mock_registry, mock_result_text):
        """Test get_title returns page title."""
        mock_registry.acall_tool = AsyncMock(return_value=mock_result_text("Example Domain"))
        title = await server.get_title()
        assert title == "Example Domain"
        mock_registry.acall_tool.assert_called_once_with("playwright", "playwright_get_title", {})

    @pytest.mark.asyncio
    async def test_get_url(self, server, mock_registry, mock_result_text):
        """Test get_url returns current URL."""
        mock_registry.acall_tool = AsyncMock(
            return_value=mock_result_text("https://example.com/page")
        )
        url = await server.get_url()
        assert url == "https://example.com/page"
        mock_registry.acall_tool.assert_called_once_with("playwright", "playwright_get_url", {})

# ============================================================================
# Edge Case Tests
# ============================================================================

class TestPlaywrightServerEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_screenshot_result(self, server, mock_registry):
        """Test handling of empty screenshot result."""
        mock_registry.acall_tool = AsyncMock(
            return_value=MCPToolCallResult(content=[], isError=False)
        )
        screenshot = await server.screenshot()
        assert screenshot.data == b""

    @pytest.mark.asyncio
    async def test_empty_text_result(self, server, mock_registry):
        """Test handling of empty text result."""
        mock_registry.acall_tool = AsyncMock(
            return_value=MCPToolCallResult(content=[], isError=False)
        )
        title = await server.get_title()
        assert title == ""

    def test_custom_server_name(self, mock_registry):
        """Test PlaywrightServer with custom server name."""
        server = PlaywrightServer(mock_registry, server_name="custom-playwright")
        assert server._server_name == "custom-playwright"
