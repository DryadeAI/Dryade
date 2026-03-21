"""Unit tests for MCP server configuration.

Tests for MCPServerConfig model validation and configuration loading utilities.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from core.mcp.config import (
    MCPServerConfig,
    MCPServerTransport,
    get_default_servers,
    load_config,
    load_config_from_file,
    load_configs_from_directory,
)

# ============================================================================
# TestMCPServerConfig - Model Validation Tests
# ============================================================================

class TestMCPServerConfig:
    """Test MCPServerConfig model validation."""

    def test_valid_minimal_config(self) -> None:
        """Test config with only required fields."""
        config = MCPServerConfig(
            name="test",
            command=["echo", "hello"],
        )
        assert config.name == "test"
        assert config.command == ["echo", "hello"]

    def test_valid_full_config(self) -> None:
        """Test config with all fields specified."""
        config = MCPServerConfig(
            name="my-server",
            command=["npx", "-y", "some-package"],
            transport=MCPServerTransport.STDIO,
            timeout=60.0,
            startup_delay=5.0,
            env={"KEY": "value"},
            auto_restart=False,
            max_restarts=5,
            health_check_interval=15.0,
            enabled=False,
        )
        assert config.name == "my-server"
        assert config.command == ["npx", "-y", "some-package"]
        assert config.transport == MCPServerTransport.STDIO
        assert config.timeout == 60.0
        assert config.startup_delay == 5.0
        assert config.env == {"KEY": "value"}
        assert config.auto_restart is False
        assert config.max_restarts == 5
        assert config.health_check_interval == 15.0
        assert config.enabled is False

    def test_default_values(self) -> None:
        """Test that all defaults are set correctly."""
        config = MCPServerConfig(name="test", command=["echo"])
        assert config.transport == MCPServerTransport.STDIO
        assert config.timeout == 60.0
        assert config.startup_delay == 2.0
        assert config.env == {}
        assert config.auto_restart is True
        assert config.max_restarts == 3
        assert config.health_check_interval == 30.0
        assert config.enabled is True

    def test_invalid_name_empty(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="", command=["echo"])
        assert "name must be non-empty" in str(exc_info.value)

    def test_invalid_name_uppercase(self) -> None:
        """Test that uppercase name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="MyServer", command=["echo"])
        assert "lowercase" in str(exc_info.value)

    def test_invalid_name_special_chars(self) -> None:
        """Test that special characters in name are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="my_server", command=["echo"])
        assert "lowercase" in str(exc_info.value)

        with pytest.raises(ValidationError):
            MCPServerConfig(name="my.server", command=["echo"])

        with pytest.raises(ValidationError):
            MCPServerConfig(name="my server", command=["echo"])

    def test_valid_name_with_hyphens(self) -> None:
        """Test that hyphens are allowed in names."""
        config = MCPServerConfig(name="my-test-server", command=["echo"])
        assert config.name == "my-test-server"

    def test_valid_name_with_numbers(self) -> None:
        """Test that numbers are allowed in names."""
        config = MCPServerConfig(name="server123", command=["echo"])
        assert config.name == "server123"

        config = MCPServerConfig(name="server-v2", command=["echo"])
        assert config.name == "server-v2"

    def test_invalid_name_starts_with_number(self) -> None:
        """Test that name starting with number is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="123server", command=["echo"])
        assert "start with a letter" in str(exc_info.value)

    def test_invalid_name_starts_with_hyphen(self) -> None:
        """Test that name starting with hyphen is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="-server", command=["echo"])
        assert "start with a letter" in str(exc_info.value)

    def test_invalid_command_empty(self) -> None:
        """Test that empty command list is rejected for STDIO transport."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="test", command=[])
        assert "STDIO transport requires a non-empty command" in str(exc_info.value)

    def test_invalid_timeout_negative(self) -> None:
        """Test that negative timeout is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="test", command=["echo"], timeout=-1.0)
        assert "greater than 0" in str(exc_info.value)

    def test_invalid_timeout_zero(self) -> None:
        """Test that zero timeout is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="test", command=["echo"], timeout=0)
        assert "greater than 0" in str(exc_info.value)

    def test_invalid_startup_delay_negative(self) -> None:
        """Test that negative startup_delay is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="test", command=["echo"], startup_delay=-1.0)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_valid_startup_delay_zero(self) -> None:
        """Test that zero startup_delay is allowed."""
        config = MCPServerConfig(name="test", command=["echo"], startup_delay=0)
        assert config.startup_delay == 0

    def test_invalid_max_restarts_negative(self) -> None:
        """Test that negative max_restarts is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="test", command=["echo"], max_restarts=-1)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_valid_max_restarts_zero(self) -> None:
        """Test that zero max_restarts is allowed (no restarts)."""
        config = MCPServerConfig(name="test", command=["echo"], max_restarts=0)
        assert config.max_restarts == 0

    def test_invalid_health_check_interval_zero(self) -> None:
        """Test that zero health_check_interval is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(name="test", command=["echo"], health_check_interval=0)
        assert "greater than 0" in str(exc_info.value)

    def test_env_var_expansion(self) -> None:
        """Test ${VAR} substitution in env dict values."""
        with patch.dict(os.environ, {"MY_TOKEN": "secret123", "MY_PATH": "/home/user"}):
            config = MCPServerConfig(
                name="test",
                command=["echo"],
                env={
                    "TOKEN": "${MY_TOKEN}",
                    "PATH_VAR": "${MY_PATH}/subdir",
                    "LITERAL": "no-var-here",
                    "MULTI": "${MY_TOKEN}:${MY_PATH}",
                },
            )
            expanded = config.expand_env_vars()
            assert expanded["TOKEN"] == "secret123"
            assert expanded["PATH_VAR"] == "/home/user/subdir"
            assert expanded["LITERAL"] == "no-var-here"
            assert expanded["MULTI"] == "secret123:/home/user"

    def test_env_var_missing(self) -> None:
        """Test that missing env vars keep literal ${VAR} value."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the var doesn't exist
            os.environ.pop("NONEXISTENT_VAR_12345", None)
            config = MCPServerConfig(
                name="test",
                command=["echo"],
                env={"MISSING": "${NONEXISTENT_VAR_12345}"},
            )
            expanded = config.expand_env_vars()
            assert expanded["MISSING"] == "${NONEXISTENT_VAR_12345}"

    def test_get_full_env(self) -> None:
        """Test get_full_env merges current environment with expanded vars."""
        with patch.dict(os.environ, {"EXISTING": "value1", "MY_VAR": "expanded"}):
            config = MCPServerConfig(
                name="test",
                command=["echo"],
                env={"NEW_VAR": "new_value", "EXPANDED": "${MY_VAR}"},
            )
            full_env = config.get_full_env()
            assert full_env["EXISTING"] == "value1"
            assert full_env["NEW_VAR"] == "new_value"
            assert full_env["EXPANDED"] == "expanded"

    def test_transport_enum_values(self) -> None:
        """Test transport enum has correct values."""
        assert MCPServerTransport.STDIO.value == "stdio"
        assert MCPServerTransport.HTTP.value == "http"

    def test_transport_from_string(self) -> None:
        """Test creating config with transport as string."""
        config = MCPServerConfig(
            name="test",
            command=["echo"],
            transport="stdio",
        )
        assert config.transport == MCPServerTransport.STDIO

# ============================================================================
# TestConfigLoading - Loading Function Tests
# ============================================================================

class TestConfigLoading:
    """Test configuration loading functions."""

    def test_load_config_from_dict(self) -> None:
        """Test loading valid config from dict."""
        config = load_config(
            {
                "name": "my-server",
                "command": ["npx", "-y", "package"],
                "timeout": 45.0,
            }
        )
        assert config.name == "my-server"
        assert config.command == ["npx", "-y", "package"]
        assert config.timeout == 45.0

    def test_load_config_invalid_dict(self) -> None:
        """Test that invalid dict raises ValidationError."""
        with pytest.raises(ValidationError):
            load_config({"name": "", "command": ["echo"]})

        with pytest.raises(ValidationError):
            load_config({"name": "test"})  # Missing command

    def test_load_config_from_file(self, tmp_path: Path) -> None:
        """Test loading config from JSON file."""
        config_file = tmp_path / "server.json"
        config_file.write_text(
            json.dumps(
                {
                    "name": "file-server",
                    "command": ["node", "server.js"],
                    "timeout": 60.0,
                }
            )
        )

        config = load_config_from_file(config_file)
        assert config.name == "file-server"
        assert config.command == ["node", "server.js"]
        assert config.timeout == 60.0

    def test_load_config_file_not_found(self, tmp_path: Path) -> None:
        """Test FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_config_from_file(tmp_path / "nonexistent.json")

    def test_load_config_invalid_json(self, tmp_path: Path) -> None:
        """Test JSONDecodeError for invalid JSON."""
        config_file = tmp_path / "bad.json"
        config_file.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            load_config_from_file(config_file)

    def test_load_config_invalid_config_in_file(self, tmp_path: Path) -> None:
        """Test ValidationError for invalid config in valid JSON file."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text(
            json.dumps(
                {
                    "name": "",  # Invalid
                    "command": ["echo"],
                }
            )
        )

        with pytest.raises(ValidationError):
            load_config_from_file(config_file)

    def test_load_configs_from_directory(self, tmp_path: Path) -> None:
        """Test loading multiple configs from directory."""
        # Create config files
        (tmp_path / "server1.json").write_text(
            json.dumps(
                {
                    "name": "server1",
                    "command": ["cmd1"],
                }
            )
        )
        (tmp_path / "server2.json").write_text(
            json.dumps(
                {
                    "name": "server2",
                    "command": ["cmd2"],
                }
            )
        )

        configs = load_configs_from_directory(tmp_path)
        assert len(configs) == 2
        assert "server1" in configs
        assert "server2" in configs
        assert configs["server1"].command == ["cmd1"]
        assert configs["server2"].command == ["cmd2"]

    def test_load_configs_from_servers_subdirectory(self, tmp_path: Path) -> None:
        """Test loading configs from servers/ subdirectory."""
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir()

        (servers_dir / "sub-server.json").write_text(
            json.dumps(
                {
                    "name": "sub-server",
                    "command": ["subcmd"],
                }
            )
        )

        configs = load_configs_from_directory(tmp_path)
        assert len(configs) == 1
        assert "sub-server" in configs

    def test_load_configs_skips_invalid(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that invalid files are logged and skipped."""
        # Valid config
        (tmp_path / "valid.json").write_text(
            json.dumps(
                {
                    "name": "valid",
                    "command": ["echo"],
                }
            )
        )

        # Invalid JSON
        (tmp_path / "bad-json.json").write_text("{ not valid }")

        # Invalid config
        (tmp_path / "bad-config.json").write_text(
            json.dumps(
                {
                    "name": "",
                    "command": ["echo"],
                }
            )
        )

        configs = load_configs_from_directory(tmp_path)
        assert len(configs) == 1
        assert "valid" in configs

        # Check that warnings were logged
        assert "bad-json.json" in caplog.text
        assert "bad-config.json" in caplog.text

    def test_load_configs_empty_directory(self, tmp_path: Path) -> None:
        """Test loading from empty directory returns empty dict."""
        configs = load_configs_from_directory(tmp_path)
        assert configs == {}

    def test_load_configs_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test loading from nonexistent directory returns empty dict."""
        configs = load_configs_from_directory(tmp_path / "nonexistent")
        assert configs == {}

    def test_load_configs_skips_duplicate_names(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that duplicate server names are skipped with warning."""
        # Create two files with same server name
        (tmp_path / "first.json").write_text(
            json.dumps(
                {
                    "name": "duplicate",
                    "command": ["first"],
                }
            )
        )
        (tmp_path / "second.json").write_text(
            json.dumps(
                {
                    "name": "duplicate",
                    "command": ["second"],
                }
            )
        )

        configs = load_configs_from_directory(tmp_path)
        # Only one should be loaded (first one alphabetically wins)
        assert len(configs) == 1
        assert "duplicate" in configs
        assert "Duplicate server name" in caplog.text

# ============================================================================
# TestDefaultServers - Default Server Configuration Tests
# ============================================================================

class TestDefaultServers:
    """Test default server configurations."""

    def test_get_default_servers(self) -> None:
        """Test that get_default_servers returns expected servers."""
        servers = get_default_servers()
        assert len(servers) == 4

        names = {s.name for s in servers}
        assert names == {"memory", "filesystem", "git", "context7"}

    def test_default_servers_disabled(self) -> None:
        """Test that all default servers have enabled=False."""
        servers = get_default_servers()
        for server in servers:
            assert server.enabled is False, f"Server {server.name} should be disabled"

    def test_default_memory_server(self) -> None:
        """Test memory server default configuration."""
        servers = get_default_servers()
        memory = next(s for s in servers if s.name == "memory")

        assert memory.command == ["npx", "-y", "@modelcontextprotocol/server-memory"]
        assert memory.transport == MCPServerTransport.STDIO
        assert memory.enabled is False

    def test_default_filesystem_server(self) -> None:
        """Test filesystem server default configuration."""
        servers = get_default_servers()
        fs = next(s for s in servers if s.name == "filesystem")

        assert fs.command[0] == "npx"
        assert "@modelcontextprotocol/server-filesystem" in fs.command
        assert fs.enabled is False
        assert "MCP_ALLOWED_PATHS" in fs.env

    def test_default_git_server(self) -> None:
        """Test git server default configuration."""
        servers = get_default_servers()
        git = next(s for s in servers if s.name == "git")

        assert git.command == ["uvx", "mcp-server-git"]
        assert git.enabled is False

    def test_default_servers_are_valid(self) -> None:
        """Test that all default servers pass validation."""
        servers = get_default_servers()
        for server in servers:
            # This should not raise
            MCPServerConfig.model_validate(server.model_dump())
