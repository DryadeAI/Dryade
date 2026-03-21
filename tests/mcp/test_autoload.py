"""Unit tests for MCP agent auto-registration.

Tests the autoload module that registers MCP servers as agents.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.adapters.protocol import AgentFramework
from core.adapters.registry import AgentRegistry
from core.mcp.autoload import (
    _config_to_mcp_server_config,
    get_enabled_mcp_servers,
    load_mcp_config,
    register_mcp_agents,
    unregister_mcp_agents,
)
from core.mcp.config import MCPServerTransport
from core.mcp.registry import MCPRegistry

class TestLoadMcpConfig:
    """Tests for load_mcp_config function."""

    def test_load_valid_config(self, tmp_path: Path):
        """Test loading a valid YAML config."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: true
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
  git:
    enabled: false
    command: ["uvx", "mcp-server-git"]
""")
        config = load_mcp_config(config_file)

        assert "servers" in config
        assert "memory" in config["servers"]
        assert config["servers"]["memory"]["enabled"] is True
        assert config["servers"]["git"]["enabled"] is False

    def test_load_missing_file_returns_empty(self, tmp_path: Path):
        """Test that missing file returns empty dict."""
        config = load_mcp_config(tmp_path / "nonexistent.yaml")
        assert config == {}

    def test_load_invalid_yaml_returns_empty(self, tmp_path: Path):
        """Test that invalid YAML returns empty dict."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("this: is: not: valid: yaml: [")

        config = load_mcp_config(config_file)
        assert config == {}

    def test_load_empty_file_returns_empty(self, tmp_path: Path):
        """Test that empty file returns empty dict."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        config = load_mcp_config(config_file)
        assert config == {}

    def test_load_string_path(self, tmp_path: Path):
        """Test loading config with string path instead of Path object."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: true
    command: ["echo"]
""")
        config = load_mcp_config(str(config_file))
        assert "servers" in config

class TestGetEnabledMcpServers:
    """Tests for get_enabled_mcp_servers function."""

    def test_returns_enabled_servers(self):
        """Test that only enabled servers are returned."""
        config = {
            "servers": {
                "memory": {"enabled": True},
                "git": {"enabled": False},
                "filesystem": {"enabled": True},
            }
        }
        enabled = get_enabled_mcp_servers(config)

        assert "memory" in enabled
        assert "filesystem" in enabled
        assert "git" not in enabled

    def test_empty_config_returns_empty_list(self):
        """Test that empty config returns empty list."""
        assert get_enabled_mcp_servers({}) == []
        assert get_enabled_mcp_servers({"servers": {}}) == []

    def test_default_disabled(self):
        """Test that servers without enabled key are disabled."""
        config = {
            "servers": {
                "memory": {"command": ["echo"]},  # No enabled key
            }
        }
        assert get_enabled_mcp_servers(config) == []

    def test_none_config_loads_default(self, tmp_path: Path):
        """Test that None config loads from default path."""
        with patch("core.mcp.autoload.load_mcp_config") as mock_load:
            mock_load.return_value = {"servers": {"memory": {"enabled": True}}}
            enabled = get_enabled_mcp_servers(None)
            mock_load.assert_called_once()
            assert "memory" in enabled

class TestConfigToMcpServerConfig:
    """Tests for _config_to_mcp_server_config function."""

    def test_stdio_transport_default(self):
        """Test that STDIO transport is default."""
        cfg = {
            "command": ["npx", "-y", "@modelcontextprotocol/server-memory"],
            "enabled": True,
        }
        config = _config_to_mcp_server_config("memory", cfg)

        assert config.name == "memory"
        assert config.transport == MCPServerTransport.STDIO
        assert config.command == ["npx", "-y", "@modelcontextprotocol/server-memory"]

    def test_http_transport(self):
        """Test HTTP transport configuration."""
        cfg = {
            "transport": "http",
            "url": "https://api.example.com/mcp",
            "auth_type": "bearer",
            "credential_service": "test-service",
            "enabled": True,
        }
        config = _config_to_mcp_server_config("github", cfg)

        assert config.transport == MCPServerTransport.HTTP
        assert config.url == "https://api.example.com/mcp"
        assert config.auth_type == "bearer"
        assert config.credential_service == "test-service"

    def test_env_vars_preserved(self):
        """Test that env vars are preserved."""
        cfg = {
            "command": ["echo"],
            "env": {"MY_VAR": "my_value"},
            "enabled": True,
        }
        config = _config_to_mcp_server_config("test", cfg)

        assert config.env == {"MY_VAR": "my_value"}

    def test_hyphenated_name_preserved(self):
        """Test that hyphenated names are preserved."""
        cfg = {"command": ["echo"], "enabled": True}
        config = _config_to_mcp_server_config("pdf-reader", cfg)

        assert config.name == "pdf-reader"

    def test_timeout_default(self):
        """Test that timeout has default value."""
        cfg = {"command": ["echo"], "enabled": True}
        config = _config_to_mcp_server_config("test", cfg)

        assert config.timeout == 30.0

    def test_timeout_override(self):
        """Test that timeout can be overridden."""
        cfg = {"command": ["echo"], "enabled": True, "timeout": 60.0}
        config = _config_to_mcp_server_config("test", cfg)

        assert config.timeout == 60.0

    def test_auto_restart_default(self):
        """Test that auto_restart defaults to True."""
        cfg = {"command": ["echo"], "enabled": True}
        config = _config_to_mcp_server_config("test", cfg)

        assert config.auto_restart is True

    def test_uppercase_name_lowercased(self):
        """Test that uppercase names are lowercased."""
        cfg = {"command": ["echo"], "enabled": True}
        config = _config_to_mcp_server_config("MEMORY", cfg)

        assert config.name == "memory"

class TestRegisterMcpAgents:
    """Tests for register_mcp_agents function."""

    @pytest.fixture
    def mock_registries(self):
        """Create mock registries for testing."""
        agent_registry = AgentRegistry()
        mcp_registry = MCPRegistry()

        with (
            patch("core.mcp.autoload.get_agent_registry", return_value=agent_registry),
            patch("core.mcp.autoload.get_mcp_registry", return_value=mcp_registry),
            patch("core.mcp.autoload.register_agent") as mock_register,
        ):
            yield {
                "agent_registry": agent_registry,
                "mcp_registry": mcp_registry,
                "mock_register": mock_register,
            }

    def test_registers_enabled_servers(self, tmp_path: Path, mock_registries):
        """Test that enabled servers are registered as agents."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: true
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
    description: "Test memory server"
""")
        count = register_mcp_agents(config_file)

        assert count == 1
        mock_registries["mock_register"].assert_called_once()

        # Verify the adapter was created correctly
        adapter = mock_registries["mock_register"].call_args[0][0]
        card = adapter.get_card()
        assert card.name == "mcp-memory"
        assert card.framework == AgentFramework.MCP

    def test_skips_disabled_servers(self, tmp_path: Path, mock_registries):
        """Test that disabled servers are not registered."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: false
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
""")
        count = register_mcp_agents(config_file)

        assert count == 0
        mock_registries["mock_register"].assert_not_called()

    def test_idempotent_registration(self, tmp_path: Path, mock_registries):
        """Test that double registration doesn't create duplicates."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: true
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
""")
        # First registration
        count1 = register_mcp_agents(config_file)
        assert count1 == 1

        # Simulate the agent being in registry
        mock_registries["agent_registry"]._agents["mcp-memory"] = MagicMock()

        # Second registration should skip
        count2 = register_mcp_agents(config_file)
        assert count2 == 0

    def test_handles_missing_config(self, tmp_path: Path, mock_registries):
        """Test graceful handling of missing config file."""
        count = register_mcp_agents(tmp_path / "nonexistent.yaml")
        assert count == 0

    def test_uses_server_descriptions_fallback(self, tmp_path: Path, mock_registries):
        """Test that SERVER_DESCRIPTIONS is used when no description in config."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: true
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
    # No description - should fall back to SERVER_DESCRIPTIONS
""")
        register_mcp_agents(config_file)

        adapter = mock_registries["mock_register"].call_args[0][0]
        card = adapter.get_card()
        # Should use fallback from SERVER_DESCRIPTIONS
        assert "memory" in card.description.lower() or "knowledge" in card.description.lower()

    def test_registers_multiple_servers(self, tmp_path: Path, mock_registries):
        """Test registering multiple enabled servers."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  memory:
    enabled: true
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
  git:
    enabled: true
    command: ["uvx", "mcp-server-git"]
  filesystem:
    enabled: false
    command: ["echo"]
""")
        count = register_mcp_agents(config_file)

        assert count == 2
        assert mock_registries["mock_register"].call_count == 2

    def test_handles_registration_error(self, tmp_path: Path):
        """Test that registration errors for one server don't stop others."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers:
  bad-server:
    enabled: true
    command: ["invalid"]
  memory:
    enabled: true
    command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
""")
        agent_registry = AgentRegistry()
        mcp_registry = MCPRegistry()
        call_count = [0]

        def register_side_effect(adapter):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Registration failed")
            agent_registry.register(adapter)

        with (
            patch("core.mcp.autoload.get_agent_registry", return_value=agent_registry),
            patch("core.mcp.autoload.get_mcp_registry", return_value=mcp_registry),
            patch("core.mcp.autoload.register_agent", side_effect=register_side_effect),
        ):
            count = register_mcp_agents(config_file)

        # Only one should succeed
        assert count == 1

    def test_empty_servers_section(self, tmp_path: Path, mock_registries):
        """Test handling empty servers section."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
servers: {}
""")
        count = register_mcp_agents(config_file)
        assert count == 0

    def test_no_servers_section(self, tmp_path: Path, mock_registries):
        """Test handling config without servers section."""
        config_file = tmp_path / "mcp_servers.yaml"
        config_file.write_text("""
other_config:
  key: value
""")
        count = register_mcp_agents(config_file)
        assert count == 0

class TestUnregisterMcpAgents:
    """Tests for unregister_mcp_agents function."""

    def test_unregisters_mcp_agents(self):
        """Test that MCP agents are unregistered."""
        agent_registry = AgentRegistry()

        # Create a mock MCP agent
        mock_agent = MagicMock()
        mock_card = MagicMock()
        mock_card.name = "mcp-test"
        mock_card.framework = AgentFramework.MCP
        mock_agent.get_card.return_value = mock_card

        agent_registry.register(mock_agent)

        with patch("core.mcp.autoload.get_agent_registry", return_value=agent_registry):
            count = unregister_mcp_agents()

        assert count == 1
        assert "mcp-test" not in agent_registry

    def test_unregister_multiple_agents(self):
        """Test unregistering multiple MCP agents."""
        agent_registry = AgentRegistry()

        # Create mock MCP agents
        for name in ["mcp-memory", "mcp-git", "mcp-filesystem"]:
            mock_agent = MagicMock()
            mock_card = MagicMock()
            mock_card.name = name
            mock_card.framework = AgentFramework.MCP
            mock_agent.get_card.return_value = mock_card
            agent_registry.register(mock_agent)

        with patch("core.mcp.autoload.get_agent_registry", return_value=agent_registry):
            count = unregister_mcp_agents()

        assert count == 3
        assert len(agent_registry) == 0

    def test_doesnt_unregister_non_mcp_agents(self):
        """Test that non-MCP agents are not unregistered."""
        agent_registry = AgentRegistry()

        # Create MCP agent
        mock_mcp = MagicMock()
        mock_mcp_card = MagicMock()
        mock_mcp_card.name = "mcp-memory"
        mock_mcp_card.framework = AgentFramework.MCP
        mock_mcp.get_card.return_value = mock_mcp_card
        agent_registry.register(mock_mcp)

        # Create non-MCP agent
        mock_other = MagicMock()
        mock_other_card = MagicMock()
        mock_other_card.name = "crewai-agent"
        mock_other_card.framework = AgentFramework.CREWAI
        mock_other.get_card.return_value = mock_other_card
        agent_registry.register(mock_other)

        with patch("core.mcp.autoload.get_agent_registry", return_value=agent_registry):
            count = unregister_mcp_agents()

        assert count == 1
        assert "mcp-memory" not in agent_registry
        assert "crewai-agent" in agent_registry

    def test_empty_registry(self):
        """Test unregister with empty registry."""
        agent_registry = AgentRegistry()

        with patch("core.mcp.autoload.get_agent_registry", return_value=agent_registry):
            count = unregister_mcp_agents()

        assert count == 0
