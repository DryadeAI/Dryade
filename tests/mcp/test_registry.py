"""Unit tests for MCP Registry.

Comprehensive tests for MCPRegistry covering:
- Server registration and discovery
- Lifecycle management (start/stop/shutdown)
- Lazy start pattern (call_tool auto-starts)
- Tool routing across servers
- Health monitoring
- Async variants
- Singleton and instance patterns

Uses mocking to avoid real subprocess communication.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from core.mcp.config import MCPServerConfig
from core.mcp.protocol import MCPTool, MCPToolCallContent, MCPToolCallResult
from core.mcp.registry import (
    MCPRegistry,
    MCPRegistryError,
    get_registry,
    reset_registry,
)
from core.mcp.stdio_transport import MCPServerStatus, StdioTransport

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def registry():
    """Fresh MCPRegistry instance for testing."""
    return MCPRegistry()

@pytest.fixture
def sample_config():
    """Valid MCPServerConfig for testing."""
    return MCPServerConfig(
        name="test-server",
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        enabled=True,
        timeout=30.0,
        startup_delay=0.1,
    )

@pytest.fixture
def sample_config_2():
    """Second valid MCPServerConfig for multi-server tests."""
    return MCPServerConfig(
        name="test-server-2",
        command=["uvx", "mcp-server-git"],
        enabled=True,
        timeout=30.0,
        startup_delay=0.1,
    )

@pytest.fixture
def disabled_config():
    """Disabled MCPServerConfig for testing."""
    return MCPServerConfig(
        name="disabled-server",
        command=["echo", "disabled"],
        enabled=False,
        timeout=30.0,
    )

@pytest.fixture
def mock_transport():
    """MagicMock of StdioTransport."""
    transport = MagicMock(spec=StdioTransport)
    transport.is_alive = True
    transport.status = MCPServerStatus.HEALTHY
    transport._restart_count = 0
    transport.list_tools.return_value = [
        MCPTool(name="test_tool", description="A test tool"),
    ]
    transport.call_tool.return_value = MCPToolCallResult(
        content=[MCPToolCallContent(type="text", text="Success")],
        isError=False,
    )
    return transport

# ============================================================================
# Registration Tests
# ============================================================================

class TestRegistration:
    """Tests for server registration functionality."""

    def test_register_server(self, registry, sample_config):
        """Test successfully registering a server config."""
        registry.register(sample_config)

        assert registry.is_registered(sample_config.name)
        assert sample_config.name in registry.list_servers()

    def test_register_duplicate_raises(self, registry, sample_config):
        """Test re-registering same name raises error."""
        registry.register(sample_config)

        with pytest.raises(MCPRegistryError) as exc_info:
            registry.register(sample_config)

        assert "already registered" in str(exc_info.value)

    def test_register_from_dict(self, registry):
        """Test registering via dictionary."""
        data = {
            "name": "dict-server",
            "command": ["echo", "hello"],
        }
        registry.register_from_dict(data)

        assert registry.is_registered("dict-server")
        config = registry.get_config("dict-server")
        assert config.command == ["echo", "hello"]

    def test_register_invalid_config_raises(self, registry):
        """Test invalid config raises ValidationError."""
        data = {
            "name": "",  # Invalid: empty name
            "command": ["echo"],
        }

        with pytest.raises(ValidationError):
            registry.register_from_dict(data)

    def test_register_missing_command_raises(self, registry):
        """Test missing command raises ValidationError."""
        data = {
            "name": "no-command",
            # Missing required 'command' field
        }

        with pytest.raises(ValidationError):
            registry.register_from_dict(data)

    def test_unregister_server(self, registry, sample_config):
        """Test successfully unregistering a server."""
        registry.register(sample_config)
        assert registry.is_registered(sample_config.name)

        registry.unregister(sample_config.name)

        assert not registry.is_registered(sample_config.name)

    def test_unregister_unknown_raises(self, registry):
        """Test unregistering unknown server raises error."""
        with pytest.raises(MCPRegistryError) as exc_info:
            registry.unregister("nonexistent")

        assert "not registered" in str(exc_info.value)

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_unregister_stops_running(
        self, mock_stop, mock_init, mock_start, registry, sample_config
    ):
        """Test running server stopped on unregister."""
        registry.register(sample_config)
        registry.start(sample_config.name)

        registry.unregister(sample_config.name)

        mock_stop.assert_called()
        assert not registry.is_registered(sample_config.name)

    def test_is_registered_true(self, registry, sample_config):
        """Test is_registered returns True for registered server."""
        registry.register(sample_config)
        assert registry.is_registered(sample_config.name) is True

    def test_is_registered_false(self, registry):
        """Test is_registered returns False for unknown server."""
        assert registry.is_registered("nonexistent") is False

# ============================================================================
# Discovery Tests
# ============================================================================

class TestDiscovery:
    """Tests for server discovery functionality."""

    def test_list_servers_empty(self, registry):
        """Test empty list when no servers registered."""
        assert registry.list_servers() == []

    def test_list_servers_returns_names(self, registry, sample_config, sample_config_2):
        """Test returns registered server names."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        servers = registry.list_servers()

        assert sample_config.name in servers
        assert sample_config_2.name in servers
        assert len(servers) == 2

    def test_get_config_success(self, registry, sample_config):
        """Test returns config for registered server."""
        registry.register(sample_config)

        config = registry.get_config(sample_config.name)

        assert config.name == sample_config.name
        assert config.command == sample_config.command

    def test_get_config_unknown_raises(self, registry):
        """Test unknown server raises error."""
        with pytest.raises(MCPRegistryError) as exc_info:
            registry.get_config("nonexistent")

        assert "not registered" in str(exc_info.value)

    def test_list_servers_order_preserved(self, registry):
        """Test list_servers preserves registration order."""
        for i in range(5):
            config = MCPServerConfig(
                name=f"server-{i}",
                command=["echo", str(i)],
            )
            registry.register(config)

        servers = registry.list_servers()
        assert servers == ["server-0", "server-1", "server-2", "server-3", "server-4"]

# ============================================================================
# Lifecycle Tests
# ============================================================================

class TestLifecycle:
    """Tests for server lifecycle management."""

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_start_server(self, mock_init, mock_start, registry, sample_config):
        """Test start creates transport and initializes."""
        registry.register(sample_config)

        registry.start(sample_config.name)

        mock_start.assert_called_once()
        mock_init.assert_called_once()
        assert sample_config.name in registry._transports

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_start_already_running(
        self, mock_init, mock_start, registry, sample_config, mock_transport
    ):
        """Test starting already-running server is idempotent."""
        registry.register(sample_config)
        # Inject mock transport directly
        registry._transports[sample_config.name] = mock_transport

        # Second start should be a no-op (transport already alive)
        mock_start.reset_mock()
        mock_init.reset_mock()
        registry.start(sample_config.name)

        mock_start.assert_not_called()
        mock_init.assert_not_called()

    def test_start_unknown_raises(self, registry):
        """Test starting unknown server raises error."""
        with pytest.raises(MCPRegistryError) as exc_info:
            registry.start("nonexistent")

        assert "not registered" in str(exc_info.value)

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_stop_server(self, mock_stop, mock_init, mock_start, registry, sample_config):
        """Test stop terminates transport."""
        registry.register(sample_config)
        registry.start(sample_config.name)

        registry.stop(sample_config.name)

        mock_stop.assert_called_once()
        assert sample_config.name not in registry._transports

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_stop_not_running_raises(self, mock_init, mock_start, registry, sample_config):
        """Test stopping non-running server raises error."""
        registry.register(sample_config)
        # Don't start the server

        with pytest.raises(MCPRegistryError) as exc_info:
            registry.stop(sample_config.name)

        assert "not running" in str(exc_info.value)

    def test_stop_unknown_raises(self, registry):
        """Test stopping unknown server raises error."""
        with pytest.raises(MCPRegistryError) as exc_info:
            registry.stop("nonexistent")

        assert "not registered" in str(exc_info.value)

    def test_is_running_true(self, registry, sample_config, mock_transport):
        """Test is_running returns True when transport active."""
        registry.register(sample_config)
        # Inject mock transport directly
        registry._transports[sample_config.name] = mock_transport

        assert registry.is_running(sample_config.name) is True

    def test_is_running_false(self, registry, sample_config):
        """Test is_running returns False when stopped."""
        registry.register(sample_config)

        assert registry.is_running(sample_config.name) is False

    def test_get_status_stopped(self, registry, sample_config):
        """Test returns STOPPED for non-running server."""
        registry.register(sample_config)

        status = registry.get_status(sample_config.name)

        assert status == MCPServerStatus.STOPPED

    def test_get_status_healthy(self, registry, sample_config, mock_transport):
        """Test returns HEALTHY after successful start."""
        registry.register(sample_config)
        # Inject mock transport directly (mock_transport already has status=HEALTHY)
        registry._transports[sample_config.name] = mock_transport

        status = registry.get_status(sample_config.name)

        assert status == MCPServerStatus.HEALTHY

    def test_get_status_unknown_raises(self, registry):
        """Test get_status raises for unknown server."""
        with pytest.raises(MCPRegistryError) as exc_info:
            registry.get_status("nonexistent")

        assert "not registered" in str(exc_info.value)

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_start_all_enabled(
        self, mock_init, mock_start, registry, sample_config, sample_config_2
    ):
        """Test starts all enabled servers."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        results = registry.start_all()

        assert len(results) == 2
        assert results[sample_config.name] is None
        assert results[sample_config_2.name] is None
        # Verify transports were created
        assert sample_config.name in registry._transports
        assert sample_config_2.name in registry._transports

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_start_all_skips_disabled(
        self, mock_init, mock_start, registry, sample_config, disabled_config
    ):
        """Test skips disabled servers."""
        registry.register(sample_config)
        registry.register(disabled_config)

        results = registry.start_all()

        # Only enabled server should be in results
        assert sample_config.name in results
        assert disabled_config.name not in results
        # Verify transport only created for enabled
        assert sample_config.name in registry._transports
        assert disabled_config.name not in registry._transports

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_start_all_returns_errors(
        self, mock_init, mock_start, registry, sample_config, sample_config_2
    ):
        """Test returns dict of errors on failures."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        # Make second server fail
        def fail_second_start():
            if mock_start.call_count == 2:
                raise RuntimeError("Server 2 failed")

        mock_start.side_effect = fail_second_start

        results = registry.start_all()

        # First should succeed, second should have error
        assert results[sample_config.name] is None
        assert isinstance(results[sample_config_2.name], RuntimeError)

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_shutdown_stops_all(
        self, mock_stop, mock_init, mock_start, registry, sample_config, sample_config_2
    ):
        """Test shutdown stops all running servers."""
        registry.register(sample_config)
        registry.register(sample_config_2)
        registry.start(sample_config.name)
        registry.start(sample_config_2.name)

        registry.shutdown()

        # Both should be stopped
        assert mock_stop.call_count >= 2
        assert len(registry._transports) == 0

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_shutdown_clears_transports(
        self, mock_stop, mock_init, mock_start, registry, sample_config
    ):
        """Test shutdown clears _transports dict."""
        registry.register(sample_config)
        registry.start(sample_config.name)

        registry.shutdown()

        assert registry._transports == {}

# ============================================================================
# Lazy Start Tests
# ============================================================================

class TestLazyStart:
    """Tests for lazy start pattern."""

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_not_started_on_registration(self, mock_init, mock_start, registry, sample_config):
        """Test server not running after register()."""
        registry.register(sample_config)

        # Server should not be started yet
        mock_start.assert_not_called()
        mock_init.assert_not_called()
        assert sample_config.name not in registry._transports

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "call_tool")
    def test_call_tool_auto_starts(self, mock_call, mock_init, mock_start, registry, sample_config):
        """Test call_tool() starts server if not running."""
        mock_call.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Result")],
            isError=False,
        )

        registry.register(sample_config)

        # Call tool - should auto-start
        registry.call_tool(sample_config.name, "some_tool")

        mock_start.assert_called_once()
        mock_init.assert_called_once()

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "list_tools")
    def test_list_tools_auto_starts(
        self, mock_list, mock_init, mock_start, registry, sample_config
    ):
        """Test list_tools() starts server if not running."""
        mock_list.return_value = [MCPTool(name="tool1")]

        registry.register(sample_config)

        # List tools - should auto-start
        registry.list_tools(sample_config.name)

        mock_start.assert_called_once()
        mock_init.assert_called_once()

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "call_tool")
    def test_lazy_start_logs_info(
        self, mock_call, mock_init, mock_start, registry, sample_config, caplog
    ):
        """Test info message logged when auto-starting."""
        mock_call.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Result")],
            isError=False,
        )

        registry.register(sample_config)

        import logging

        with caplog.at_level(logging.INFO, logger="core.mcp.registry"):
            registry.call_tool(sample_config.name, "some_tool")

        assert "Auto-starting" in caplog.text

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "call_tool")
    @patch.object(StdioTransport, "stop")
    def test_no_auto_shutdown(
        self, mock_stop, mock_call, mock_init, mock_start, registry, sample_config
    ):
        """Test server remains running after tool call (no idle timeout)."""
        mock_call.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Result")],
            isError=False,
        )

        registry.register(sample_config)
        registry.call_tool(sample_config.name, "some_tool")

        # Server should still be in _transports (not auto-stopped)
        mock_stop.assert_not_called()
        assert sample_config.name in registry._transports

# ============================================================================
# AtExit Tests
# ============================================================================

class TestAtExit:
    """Tests for atexit handler registration."""

    @patch("atexit.register")
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    def test_atexit_registered_on_start(
        self, mock_init, mock_start, mock_atexit, registry, sample_config
    ):
        """Test atexit.register called once on first start."""
        registry.register(sample_config)

        registry.start(sample_config.name)

        mock_atexit.assert_called_once_with(registry.shutdown)

    @patch("atexit.register")
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_atexit_not_reregistered(
        self,
        mock_stop,
        mock_init,
        mock_start,
        mock_atexit,
        registry,
        sample_config,
        sample_config_2,
    ):
        """Test multiple starts don't re-register atexit."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        registry.start(sample_config.name)
        registry.start(sample_config_2.name)

        # Should only register once
        mock_atexit.assert_called_once()

    @patch("atexit.register")
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    def test_atexit_not_reregistered_after_stop(
        self, mock_stop, mock_init, mock_start, mock_atexit, registry, sample_config
    ):
        """Test atexit not re-registered after stop and restart."""
        registry.register(sample_config)

        registry.start(sample_config.name)
        registry.stop(sample_config.name)
        registry.start(sample_config.name)

        # Should only register once
        mock_atexit.assert_called_once()

# ============================================================================
# Tool Routing Tests
# ============================================================================

class TestToolRouting:
    """Tests for tool routing across servers."""

    def test_list_tools_from_server(self, registry, sample_config, mock_transport):
        """Test returns tools from running server."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        tools = registry.list_tools(sample_config.name)

        assert len(tools) == 1
        assert tools[0].name == "test_tool"
        mock_transport.list_tools.assert_called_once()

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "list_tools")
    def test_list_tools_auto_starts(
        self, mock_list, mock_init, mock_start, registry, sample_config
    ):
        """Test list_tools auto-starts server if not running."""
        mock_list.return_value = [MCPTool(name="auto_tool")]

        registry.register(sample_config)

        tools = registry.list_tools(sample_config.name)

        mock_start.assert_called_once()
        mock_init.assert_called_once()
        assert len(tools) == 1

    def test_list_tools_unknown_raises(self, registry):
        """Test list_tools raises for unknown server."""
        with pytest.raises(MCPRegistryError) as exc_info:
            registry.list_tools("nonexistent")

        assert "not registered" in str(exc_info.value)

    def test_list_all_tools(self, registry, sample_config, sample_config_2, mock_transport):
        """Test returns dict of server -> tools."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        # Create second mock transport with different tools
        mock_transport_2 = MagicMock(spec=StdioTransport)
        mock_transport_2.is_alive = True
        mock_transport_2.list_tools.return_value = [
            MCPTool(name="tool_a"),
            MCPTool(name="tool_b"),
        ]

        registry._transports[sample_config.name] = mock_transport
        registry._transports[sample_config_2.name] = mock_transport_2

        all_tools = registry.list_all_tools()

        assert sample_config.name in all_tools
        assert sample_config_2.name in all_tools
        assert len(all_tools[sample_config.name]) == 1
        assert len(all_tools[sample_config_2.name]) == 2

    def test_call_tool_success(self, registry, sample_config, mock_transport):
        """Test executes tool and returns result."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        result = registry.call_tool(sample_config.name, "test_tool")

        assert not result.isError
        assert result.content[0].text == "Success"
        mock_transport.call_tool.assert_called_once_with("test_tool", None)

    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "call_tool")
    def test_call_tool_auto_starts(self, mock_call, mock_init, mock_start, registry, sample_config):
        """Test call_tool auto-starts server if not running."""
        mock_call.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Auto result")],
            isError=False,
        )

        registry.register(sample_config)

        result = registry.call_tool(sample_config.name, "some_tool")

        mock_start.assert_called_once()
        mock_init.assert_called_once()
        assert result.content[0].text == "Auto result"

    def test_call_tool_with_arguments(self, registry, sample_config, mock_transport):
        """Test passes arguments correctly."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        args = {"path": "/tmp/file.txt", "mode": "read"}
        registry.call_tool(sample_config.name, "read_file", args)

        mock_transport.call_tool.assert_called_once_with("read_file", args)

    def test_find_tool_found(self, registry, sample_config, mock_transport):
        """Test finds tool and returns (server, tool)."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        result = registry.find_tool("test_tool")

        assert result is not None
        server_name, tool = result
        assert server_name == sample_config.name
        assert tool.name == "test_tool"

    def test_find_tool_not_found(self, registry, sample_config, mock_transport):
        """Test returns None if tool not on any server."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        result = registry.find_tool("nonexistent_tool")

        assert result is None

    def test_call_tool_by_name_success(self, registry, sample_config, mock_transport):
        """Test auto-routes to correct server."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        result = registry.call_tool_by_name("test_tool")

        assert not result.isError
        mock_transport.call_tool.assert_called_once_with("test_tool", None)

    def test_call_tool_by_name_not_found(self, registry, sample_config, mock_transport):
        """Test raises error if tool not found."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        with pytest.raises(MCPRegistryError) as exc_info:
            registry.call_tool_by_name("nonexistent_tool")

        assert "not found" in str(exc_info.value)

# ============================================================================
# Health Tests
# ============================================================================

class TestHealth:
    """Tests for health monitoring."""

    def test_get_health_summary_empty(self, registry):
        """Test returns zeros when no servers registered."""
        summary = registry.get_health_summary()

        assert summary["total_registered"] == 0
        assert summary["total_running"] == 0
        assert summary["total_healthy"] == 0
        assert summary["servers"] == {}

    def test_get_health_summary_registered(self, registry, sample_config, sample_config_2):
        """Test counts registered servers."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        summary = registry.get_health_summary()

        assert summary["total_registered"] == 2
        assert sample_config.name in summary["servers"]
        assert sample_config_2.name in summary["servers"]

    def test_get_health_summary_running(self, registry, sample_config, mock_transport):
        """Test counts running servers."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        summary = registry.get_health_summary()

        assert summary["total_running"] == 1

    def test_get_health_summary_healthy(self, registry, sample_config, mock_transport):
        """Test counts healthy servers."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        summary = registry.get_health_summary()

        assert summary["total_healthy"] == 1

    def test_health_summary_structure(self, registry, sample_config, mock_transport):
        """Test per-server structure: status, restart_count, tool_count."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        summary = registry.get_health_summary()
        server_info = summary["servers"][sample_config.name]

        assert "status" in server_info
        assert "restart_count" in server_info
        assert "tool_count" in server_info
        assert server_info["status"] == MCPServerStatus.HEALTHY.value
        assert server_info["restart_count"] == 0
        assert server_info["tool_count"] == 1  # mock returns one tool

    def test_check_health_healthy(self, registry, sample_config, mock_transport):
        """Test returns True for healthy server."""
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        assert registry.check_health(sample_config.name) is True

    def test_check_health_unhealthy(self, registry, sample_config, mock_transport):
        """Test returns False for unhealthy server."""
        mock_transport.status = MCPServerStatus.CRASHED
        registry.register(sample_config)
        registry._transports[sample_config.name] = mock_transport

        assert registry.check_health(sample_config.name) is False

    def test_check_health_not_running(self, registry, sample_config):
        """Test returns False for stopped server."""
        registry.register(sample_config)

        assert registry.check_health(sample_config.name) is False

# ============================================================================
# Async Variants Tests
# ============================================================================

class TestAsyncVariants:
    """Tests for async API variants."""

    @pytest.mark.asyncio
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    async def test_astart_runs_in_executor(self, mock_init, mock_start, registry, sample_config):
        """Test astart() uses run_in_executor."""
        registry.register(sample_config)

        await registry.astart(sample_config.name)

        mock_start.assert_called_once()
        mock_init.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    async def test_astop_runs_in_executor(
        self, mock_stop, mock_init, mock_start, registry, sample_config
    ):
        """Test astop() uses run_in_executor."""
        registry.register(sample_config)
        registry.start(sample_config.name)

        await registry.astop(sample_config.name)

        mock_stop.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "call_tool")
    async def test_acall_tool_runs_in_executor(
        self, mock_call, mock_init, mock_start, registry, sample_config
    ):
        """Test acall_tool() uses run_in_executor."""
        mock_call.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Async result")],
            isError=False,
        )

        registry.register(sample_config)

        result = await registry.acall_tool(sample_config.name, "test_tool", {"arg": "value"})

        mock_call.assert_called_once_with("test_tool", {"arg": "value"})
        assert result.content[0].text == "Async result"

    @pytest.mark.asyncio
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    async def test_astart_all_concurrent(
        self, mock_init, mock_start, registry, sample_config, sample_config_2
    ):
        """Test astart_all() runs concurrently."""
        registry.register(sample_config)
        registry.register(sample_config_2)

        results = await registry.astart_all()

        assert len(results) == 2
        assert results[sample_config.name] is None
        assert results[sample_config_2.name] is None

    @pytest.mark.asyncio
    @patch.object(StdioTransport, "start")
    @patch.object(StdioTransport, "initialize")
    @patch.object(StdioTransport, "stop")
    async def test_ashutdown_runs_in_executor(
        self, mock_stop, mock_init, mock_start, registry, sample_config
    ):
        """Test ashutdown() uses run_in_executor."""
        registry.register(sample_config)
        registry.start(sample_config.name)

        await registry.ashutdown()

        mock_stop.assert_called()

# ============================================================================
# Singleton Tests
# ============================================================================

class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_registry_returns_same_instance(self):
        """Test global singleton."""
        # Reset first to ensure clean state
        reset_registry()

        r1 = get_registry()
        r2 = get_registry()

        assert r1 is r2

        # Clean up
        reset_registry()

    @patch.object(MCPRegistry, "shutdown")
    def test_reset_registry_calls_shutdown(self, mock_shutdown):
        """Test reset calls shutdown."""
        # Get the registry first
        _ = get_registry()

        reset_registry()

        mock_shutdown.assert_called_once()

    def test_reset_registry_creates_new(self):
        """Test reset creates new instance."""
        reset_registry()

        r1 = get_registry()
        reset_registry()
        r2 = get_registry()

        assert r1 is not r2

        # Clean up
        reset_registry()

    def test_instance_pattern_creates_separate(self):
        """Test MCPRegistry() creates separate instances."""
        registry1 = MCPRegistry()
        registry2 = MCPRegistry()

        assert registry1 is not registry2

        # Each should have independent state
        config = MCPServerConfig(name="test", command=["echo"])
        registry1.register(config)

        assert registry1.is_registered("test")
        assert not registry2.is_registered("test")

# ============================================================================
# Thread Safety Tests
# ============================================================================

class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_registration(self, registry):
        """Test concurrent server registration is safe."""
        errors = []
        registered = []

        def register_server(index):
            try:
                config = MCPServerConfig(
                    name=f"server-{index}",
                    command=["echo", str(index)],
                )
                registry.register(config)
                registered.append(index)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_server, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(registered) == 50
        assert len(registry.list_servers()) == 50

    def test_concurrent_access(self, registry):
        """Test concurrent read/write operations are safe."""
        errors = []
        config = MCPServerConfig(name="test", command=["echo"])
        registry.register(config)

        def read_operations():
            for _ in range(100):
                try:
                    registry.is_registered("test")
                    registry.list_servers()
                    registry.get_config("test")
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=read_operations) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
