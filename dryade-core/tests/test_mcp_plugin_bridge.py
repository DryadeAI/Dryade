"""Tests for MCPPluginProtocol -- MCP-to-plugin security bridge.

Ensures MCP-based plugins go through the same allowlist/hash verification
as regular Python plugins before any MCP server is registered.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.ee.plugins_ee import PluginProtocol
from core.mcp_plugin_bridge import MCPPluginProtocol

def _mock_mcp_imports():
    """Create mock modules for MCP imports that require sentence_transformers.

    Returns context manager patches for the internal imports used by register().
    """
    mock_adapter = MagicMock()
    mock_config = MagicMock()

    # MCPServerConfig and MCPServerTransport need to be usable as constructors/enums
    mock_config.MCPServerConfig = MagicMock()
    mock_config.MCPServerTransport = MagicMock()
    mock_config.MCPServerTransport.STDIO = "stdio"

    mock_adapter.MCPAgentAdapter = MagicMock()

    return mock_adapter, mock_config

class TestMCPPluginProtocolInterface:
    """Verify MCPPluginProtocol satisfies PluginProtocol contract."""

    def test_mcp_plugin_has_plugin_protocol_interface(self) -> None:
        """MCPPluginProtocol is a subclass of PluginProtocol."""
        assert issubclass(MCPPluginProtocol, PluginProtocol)

    def test_mcp_plugin_has_required_attributes(self) -> None:
        """MCPPluginProtocol instances have all PluginProtocol attributes."""
        plugin = MCPPluginProtocol(
            name="test_mcp",
            version="1.0.0",
            description="Test MCP plugin",
            mcp_server_name="test-server",
            mcp_command=["python", "-m", "test_server"],
        )
        assert plugin.name == "test_mcp"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Test MCP plugin"
        assert hasattr(plugin, "core_version_constraint")
        assert hasattr(plugin, "register")
        assert hasattr(plugin, "shutdown")

class TestMCPPluginRegistration:
    """Test register/unregister lifecycle."""

    def _make_plugin(self, **kwargs: object) -> MCPPluginProtocol:
        """Create a test MCPPluginProtocol instance."""
        defaults = {
            "name": "capella_mcp",
            "version": "1.0.0",
            "description": "Capella MCP bridge",
            "mcp_server_name": "capella",
            "mcp_command": ["python", "-m", "capella_server"],
            "mcp_args": [],
            "mcp_env": {},
        }
        defaults.update(kwargs)
        return MCPPluginProtocol(**defaults)  # type: ignore[arg-type]

    @patch("core.mcp_plugin_bridge.get_mcp_registry")
    @patch("core.mcp_plugin_bridge.get_agent_registry")
    @patch("core.mcp_plugin_bridge.register_agent")
    def test_mcp_plugin_register_triggers_mcp_server(
        self,
        mock_register_agent: MagicMock,
        mock_get_agent_reg: MagicMock,
        mock_get_mcp_reg: MagicMock,
    ) -> None:
        """register() creates MCPAgentAdapter and registers MCP server."""
        mock_mcp_reg = MagicMock()
        mock_mcp_reg.is_registered.return_value = False
        mock_get_mcp_reg.return_value = mock_mcp_reg

        mock_agent_reg = MagicMock()
        mock_agent_reg.__contains__ = MagicMock(return_value=False)
        mock_get_agent_reg.return_value = mock_agent_reg

        mock_adapter_mod, mock_config_mod = _mock_mcp_imports()

        plugin = self._make_plugin()
        registry = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "core.mcp.adapter": mock_adapter_mod,
                "core.mcp.config": mock_config_mod,
            },
        ):
            plugin.register(registry)

        # MCP server config should be registered
        mock_mcp_reg.register.assert_called_once()
        # Agent adapter should be registered
        mock_register_agent.assert_called_once()

    @patch("core.mcp_plugin_bridge.get_mcp_registry")
    @patch("core.mcp_plugin_bridge.get_agent_registry")
    @patch("core.mcp_plugin_bridge.register_agent")
    def test_mcp_plugin_register_skips_without_server_name(
        self,
        mock_register_agent: MagicMock,
        mock_get_agent_reg: MagicMock,
        mock_get_mcp_reg: MagicMock,
    ) -> None:
        """register() with empty mcp_server_name skips registration."""
        plugin = self._make_plugin(mcp_server_name="")
        registry = MagicMock()
        plugin.register(registry)

        # Nothing should be registered
        mock_register_agent.assert_not_called()

    @patch("core.mcp_plugin_bridge.get_agent_registry")
    def test_mcp_plugin_unregister_stops_server(
        self,
        mock_get_agent_reg: MagicMock,
    ) -> None:
        """unregister() removes MCP server from AgentRegistry."""
        mock_agent_reg = MagicMock()
        mock_get_agent_reg.return_value = mock_agent_reg

        plugin = self._make_plugin()
        plugin.unregister()

        # Agent should be unregistered by name
        mock_agent_reg.unregister.assert_called_once_with("mcp-capella")

    def test_mcp_plugin_config_from_manifest(self) -> None:
        """MCP server config (command, args, env) is read from plugin attributes."""
        plugin = MCPPluginProtocol(
            name="custom_mcp",
            version="2.0.0",
            description="Custom MCP",
            mcp_server_name="custom-server",
            mcp_command=["node", "server.js"],
            mcp_args=["--port", "3000"],
            mcp_env={"API_KEY": "test123"},
        )
        assert plugin.mcp_server_name == "custom-server"
        assert plugin.mcp_command == ["node", "server.js"]
        assert plugin.mcp_args == ["--port", "3000"]
        assert plugin.mcp_env == {"API_KEY": "test123"}

class TestMCPPluginSecurity:
    """Test that MCP plugins respect the allowlist security model."""

    def test_mcp_plugin_requires_allowlist(self) -> None:
        """MCPPluginProtocol goes through validate_before_load like any plugin.

        This test verifies the bridge is a proper PluginProtocol subclass,
        meaning PluginManager.discover/register_all will call validate_before_load
        on it just like any other plugin. The security gate is in PluginManager,
        not in the plugin itself.
        """
        plugin = MCPPluginProtocol(
            name="secured_mcp",
            version="1.0.0",
            description="Secured MCP plugin",
            mcp_server_name="secured",
            mcp_command=["python", "-m", "secured_server"],
        )
        # Being a PluginProtocol subclass means the PluginManager will validate
        # this plugin through validate_before_load before calling register()
        assert isinstance(plugin, PluginProtocol)
        assert hasattr(plugin, "name")
        assert plugin.name == "secured_mcp"

    @patch("core.mcp_plugin_bridge.register_agent")
    def test_mcp_plugin_blocked_without_allowlist(
        self,
        mock_register_agent: MagicMock,
    ) -> None:
        """Without allowlist entry, MCP server is NOT registered.

        When validate_before_load returns (False, reason), the PluginManager
        skips register() entirely. We verify that register_all with a blocked
        plugin never calls register(), so no MCP server starts.
        """
        from core.ee.plugins_ee import PluginManager

        with patch("core.plugins.validate_before_load", return_value=(False, "not in allowlist")):
            manager = PluginManager()
            plugin = MCPPluginProtocol(
                name="blocked_mcp",
                version="1.0.0",
                description="Should be blocked",
                mcp_server_name="blocked",
                mcp_command=["python", "-m", "blocked_server"],
            )
            # Manually add to manager's internal dict to simulate discovery
            manager._plugins["blocked_mcp"] = plugin

            # register_all should skip this plugin because validate_before_load returns False
            mock_registry = MagicMock()
            manager.register_all(mock_registry)

            # The MCP register_agent should NOT have been called
            mock_register_agent.assert_not_called()

    @patch("core.mcp_plugin_bridge.get_agent_registry")
    def test_mcp_plugin_shutdown_calls_unregister(
        self,
        mock_get_agent_reg: MagicMock,
    ) -> None:
        """shutdown() triggers unregister to clean up MCP server."""
        mock_agent_reg = MagicMock()
        mock_get_agent_reg.return_value = mock_agent_reg

        plugin = MCPPluginProtocol(
            name="shutdown_mcp",
            version="1.0.0",
            description="Shutdown test",
            mcp_server_name="shutdown-server",
            mcp_command=["python", "-m", "shutdown_server"],
        )
        plugin.shutdown()

        mock_agent_reg.unregister.assert_called_once_with("mcp-shutdown-server")
