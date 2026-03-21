"""
Unit tests for sandbox plugin.

Tests cover:
1. Plugin protocol implementation
2. Sandbox executor initialization
3. Isolation level NONE (direct execution)
4. Isolation level PROCESS (subprocess)
5. Isolation level CONTAINER (mock Docker)
6. Timeout handling
7. Resource limits
8. Error handling
9. Graceful degradation (gVisor unavailable)

Target: ~120 LOC
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

@pytest.fixture
def mock_subprocess():
    """Mock asyncio subprocess."""
    proc = MagicMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"output", b""))
    return proc

@pytest.mark.unit
class TestSandboxPlugin:
    """Tests for SandboxPlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""
        from plugins.sandbox import plugin

        assert hasattr(plugin, "name")
        assert hasattr(plugin, "version")
        assert hasattr(plugin, "description")
        assert hasattr(plugin, "register")
        assert hasattr(plugin, "startup")
        assert hasattr(plugin, "shutdown")

    def test_plugin_name_and_version(self):
        """Test plugin name and version."""
        from plugins.sandbox import plugin

        assert plugin.name == "sandbox"
        assert plugin.version == "1.0.0"

    def test_plugin_register(self):
        """Test plugin registration with registry."""
        from plugins.sandbox import plugin

        from core.extensions.pipeline import ExtensionRegistry

        registry = ExtensionRegistry()
        plugin.register(registry)

        config = registry.get("sandbox")
        assert config is not None
        assert config.priority == 4

@pytest.mark.unit
class TestSandboxExecutor:
    """Tests for ToolSandbox class."""

    def test_sandbox_initialization(self):
        """Test sandbox initializes with default config."""
        from plugins.sandbox.executor import IsolationLevel, ToolSandbox

        sandbox = ToolSandbox()

        assert sandbox.default_config is not None
        assert sandbox.default_config.isolation == IsolationLevel.PROCESS

    def test_sandbox_custom_config(self):
        """Test sandbox with custom config."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        config = SandboxConfig(
            isolation=IsolationLevel.CONTAINER, timeout_seconds=30, memory_limit_mb=256
        )
        sandbox = ToolSandbox(default_config=config)

        assert sandbox.default_config.isolation == IsolationLevel.CONTAINER
        assert sandbox.default_config.timeout_seconds == 30
        assert sandbox.default_config.memory_limit_mb == 256

    def test_get_config_for_tool_known(self):
        """Test getting config for known tool."""
        from plugins.sandbox.executor import IsolationLevel, ToolSandbox

        sandbox = ToolSandbox()
        config = sandbox._get_config_for_tool("capella_list")

        assert config.isolation == IsolationLevel.NONE

    def test_get_config_for_tool_unknown(self):
        """Test getting config for unknown tool defaults to PROCESS."""
        from plugins.sandbox.executor import IsolationLevel, ToolSandbox

        sandbox = ToolSandbox()
        config = sandbox._get_config_for_tool("unknown_tool")

        assert config.isolation == IsolationLevel.PROCESS

    @pytest.mark.asyncio
    async def test_execute_isolation_none(self):
        """Test direct execution with NONE isolation."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(isolation=IsolationLevel.NONE)

        async def test_func(value):
            return f"result: {value}"

        result = await sandbox.execute(
            "test_tool", {"value": "hello"}, func=test_func, config=config
        )

        assert result.success is True
        assert result.output == "result: hello"
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_execute_isolation_none_no_func(self):
        """Test NONE isolation fails without function."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(isolation=IsolationLevel.NONE)

        result = await sandbox.execute("test_tool", {"value": "hello"}, func=None, config=config)

        assert result.success is False
        assert "No function provided" in result.error

    @pytest.mark.asyncio
    async def test_execute_isolation_process(self, mock_subprocess):
        """Test subprocess execution with PROCESS isolation."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(isolation=IsolationLevel.PROCESS, timeout_seconds=10)

        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            result = await sandbox.execute("test_tool", {"arg": "value"}, config=config)

            assert result.success is True
            assert result.output == "output"
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_isolation_container(self, mock_subprocess):
        """Test Docker container execution."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(
            isolation=IsolationLevel.CONTAINER,
            timeout_seconds=30,
            memory_limit_mb=512,
            network_enabled=False,
            filesystem_readonly=True,
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            result = await sandbox.execute(
                "execute_code", {"code": "print('hello')"}, config=config
            )

            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_timeout_handling(self):
        """Test timeout handling in subprocess."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(isolation=IsolationLevel.PROCESS, timeout_seconds=1)

        async def slow_communicate():
            await asyncio.sleep(10)
            return (b"output", b"")

        mock_proc = MagicMock()
        mock_proc.communicate = slow_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await sandbox.execute("slow_tool", {}, config=config)

            assert result.success is False
            assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_execute_gvisor_fallback_disabled(self, mock_subprocess):
        """Test gVisor falls back to Docker when disabled."""
        import os

        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(isolation=IsolationLevel.GVISOR, timeout_seconds=30)

        with (
            patch.dict(os.environ, {"DRYADE_GVISOR_ENABLED": "false"}),
            patch("asyncio.create_subprocess_exec", return_value=mock_subprocess),
        ):
            result = await sandbox.execute("test_tool", {"arg": "value"}, config=config)

            # Should succeed using Docker fallback
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_error_handling(self):
        """Test error handling during execution."""
        from plugins.sandbox.executor import IsolationLevel, SandboxConfig, ToolSandbox

        sandbox = ToolSandbox()
        config = SandboxConfig(isolation=IsolationLevel.NONE)

        async def failing_func(value):
            raise ValueError("Test error")

        result = await sandbox.execute(
            "test_tool", {"value": "test"}, func=failing_func, config=config
        )

        assert result.success is False
        assert "Test error" in result.error

@pytest.mark.unit
class TestSandboxResult:
    """Tests for SandboxResult dataclass."""

    def test_result_success(self):
        """Test successful result."""
        from plugins.sandbox.executor import SandboxResult

        result = SandboxResult(success=True, output="test output", execution_time_ms=100.5)

        assert result.success is True
        assert result.output == "test output"
        assert result.error is None
        assert result.exit_code == 0
        assert result.execution_time_ms == 100.5

    def test_result_failure(self):
        """Test failed result."""
        from plugins.sandbox.executor import SandboxResult

        result = SandboxResult(success=False, error="Something went wrong", exit_code=1)

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.exit_code == 1

@pytest.mark.unit
class TestIsolationLevel:
    """Tests for IsolationLevel enum."""

    def test_isolation_levels(self):
        """Test all isolation levels exist."""
        from plugins.sandbox.executor import IsolationLevel

        assert IsolationLevel.NONE == "none"
        assert IsolationLevel.PROCESS == "process"
        assert IsolationLevel.CONTAINER == "container"
        assert IsolationLevel.GVISOR == "gvisor"

    def test_tool_risk_levels(self):
        """Test tool risk level mapping."""
        from plugins.sandbox.executor import TOOL_RISK_LEVELS, IsolationLevel

        assert TOOL_RISK_LEVELS["capella_list"] == IsolationLevel.NONE
        assert TOOL_RISK_LEVELS["execute_code"] == IsolationLevel.CONTAINER
