"""Tests for skills module coverage gaps.

Covers:
- core.skills.executor (SkillScriptExecutor, ScriptExecutionResult)
- core.skills.watcher (SkillWatcher, singleton functions)
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.skills.models import Skill, SkillMetadata

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_skill(
    name="test-skill",
    scripts_dir=None,
    has_scripts=False,
    skill_dir="/tmp/test-skill",
):
    """Create a mock Skill for testing."""
    return Skill(
        name=name,
        description="A test skill",
        instructions="Test instructions",
        metadata=SkillMetadata(),
        skill_dir=skill_dir,
        scripts_dir=scripts_dir,
        has_scripts=has_scripts,
    )

# ---------------------------------------------------------------------------
# ScriptExecutionResult tests
# ---------------------------------------------------------------------------

class TestScriptExecutionResult:
    """Tests for ScriptExecutionResult model."""

    def test_creation_defaults(self):
        """ScriptExecutionResult initializes with defaults."""
        from core.skills.executor import ScriptExecutionResult

        result = ScriptExecutionResult(success=True)
        assert result.success is True
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.return_code == 0
        assert result.timed_out is False
        assert result.error is None
        assert result.script_path is None
        assert result.duration_ms == 0

    def test_creation_all_fields(self):
        """ScriptExecutionResult with all fields set."""
        from core.skills.executor import ScriptExecutionResult

        result = ScriptExecutionResult(
            success=False,
            stdout="out",
            stderr="err",
            return_code=1,
            timed_out=True,
            error="timeout",
            script_path="/tmp/script.sh",
            duration_ms=5000,
        )
        assert result.success is False
        assert result.timed_out is True
        assert result.error == "timeout"

# ---------------------------------------------------------------------------
# SkillScriptExecutor tests
# ---------------------------------------------------------------------------

class TestSkillScriptExecutor:
    """Tests for SkillScriptExecutor."""

    def test_creation_defaults(self):
        """Executor initializes with default values."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor()
        assert executor.timeout == 60
        assert executor.max_output_size == 1024 * 1024
        assert "PATH" in executor.allowed_env_vars
        assert "OPENAI_API_KEY" in executor.allowed_env_vars

    def test_creation_custom(self):
        """Executor initializes with custom values."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(timeout=30, max_output_size=1024, allowed_env_vars=["PATH"])
        assert executor.timeout == 30
        assert executor.max_output_size == 1024
        assert executor.allowed_env_vars == ["PATH"]

    def test_build_env(self):
        """_build_env creates safe environment dict."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=["PATH", "HOME"])
        skill = _make_skill(scripts_dir="/tmp/test-skill/scripts")
        env = executor._build_env(skill)
        assert env["SKILL_DIR"] == "/tmp/test-skill"
        assert env["SKILL_NAME"] == "test-skill"
        assert env["SCRIPTS_DIR"] == "/tmp/test-skill/scripts"
        # PATH should be passed if present in os.environ
        if "PATH" in os.environ:
            assert "PATH" in env

    def test_build_env_with_extra(self):
        """_build_env merges extra environment variables."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill()
        env = executor._build_env(skill, extra_env={"CUSTOM_VAR": "value"})
        assert env["CUSTOM_VAR"] == "value"

    def test_build_env_no_scripts_dir(self):
        """_build_env handles None scripts_dir."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir=None)
        env = executor._build_env(skill)
        assert "SCRIPTS_DIR" not in env

    @pytest.mark.asyncio
    async def test_execute_no_scripts_dir(self):
        """execute returns error when skill has no scripts_dir."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor()
        skill = _make_skill(scripts_dir=None)
        result = await executor.execute(skill, "run.sh")
        assert result.success is False
        assert "no scripts/ folder" in result.error

    @pytest.mark.asyncio
    async def test_execute_script_not_found(self):
        """execute returns error when script not found."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor()
        skill = _make_skill(scripts_dir="/tmp/test-scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value=None)
        skill.get_scripts = MagicMock(return_value=["other.sh"])
        result = await executor.execute(skill, "missing.sh")
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """execute runs script successfully."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/run.sh")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))
        mock_process.returncode = 0

        with (
            patch("os.access", return_value=True),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
        ):
            mock_exec.return_value = mock_process
            result = await executor.execute(skill, "run.sh", args=["--flag"])

        assert result.success is True
        assert result.stdout == "output"
        assert result.return_code == 0

    @pytest.mark.asyncio
    async def test_execute_script_failure(self):
        """execute handles non-zero return code."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/fail.sh")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"error msg"))
        mock_process.returncode = 1

        with (
            patch("os.access", return_value=True),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
        ):
            mock_exec.return_value = mock_process
            result = await executor.execute(skill, "fail.sh")

        assert result.success is False
        assert result.stderr == "error msg"
        assert result.return_code == 1

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """execute handles script timeout."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(timeout=1, allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/slow.sh")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=TimeoutError)
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with (
            patch("os.access", return_value=True),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
            patch("asyncio.wait_for", side_effect=TimeoutError),
        ):
            mock_exec.return_value = mock_process
            result = await executor.execute(skill, "slow.sh", timeout=1)

        assert result.success is False
        assert result.timed_out is True

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self):
        """execute handles FileNotFoundError."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/missing.sh")

        with (
            patch("os.access", return_value=True),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                side_effect=FileNotFoundError("not found"),
            ),
        ):
            result = await executor.execute(skill, "missing.sh")

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_permission_error(self):
        """execute handles PermissionError."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/noperm.sh")

        with (
            patch("os.access", return_value=True),
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                side_effect=PermissionError("denied"),
            ),
        ):
            result = await executor.execute(skill, "noperm.sh")

        assert result.success is False
        assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_execute_not_executable_chmod_success(self):
        """execute makes script executable if not already."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/run.sh")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_process.returncode = 0

        with (
            patch("os.access", return_value=False),
            patch("os.chmod") as mock_chmod,
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
        ):
            mock_exec.return_value = mock_process
            result = await executor.execute(skill, "run.sh")

        assert result.success is True
        mock_chmod.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_not_executable_chmod_failure(self):
        """execute returns error when chmod fails."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/locked.sh")

        with (
            patch("os.access", return_value=False),
            patch("os.chmod", side_effect=OSError("cannot chmod")),
        ):
            result = await executor.execute(skill, "locked.sh")

        assert result.success is False
        assert "cannot chmod" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_stdin(self):
        """execute passes stdin_data to process."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor(allowed_env_vars=[])
        skill = _make_skill(scripts_dir="/tmp/scripts", has_scripts=True)
        skill.get_script_path = MagicMock(return_value="/tmp/scripts/read.sh")

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"processed", b""))
        mock_process.returncode = 0

        with (
            patch("os.access", return_value=True),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec,
        ):
            mock_exec.return_value = mock_process
            result = await executor.execute(skill, "read.sh", stdin_data="hello")

        assert result.success is True
        # Check stdin was passed to communicate
        mock_process.communicate.assert_awaited_once()

    def test_list_scripts(self):
        """list_scripts returns script info dicts."""
        from core.skills.executor import SkillScriptExecutor

        executor = SkillScriptExecutor()
        skill = _make_skill(scripts_dir=None)
        assert executor.list_scripts(skill) == []

    def test_list_scripts_with_dir(self, tmp_path):
        """list_scripts returns script info from directory."""
        from core.skills.executor import SkillScriptExecutor

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash\necho ok")
        (scripts_dir / ".hidden").write_text("skip")

        executor = SkillScriptExecutor()
        skill = _make_skill(scripts_dir=str(scripts_dir))
        scripts = executor.list_scripts(skill)
        assert len(scripts) == 1
        assert scripts[0]["name"] == "run.sh"

class TestSkillExecutorSingleton:
    """Tests for get_skill_executor singleton."""

    def test_get_skill_executor(self):
        """get_skill_executor returns singleton."""
        import core.skills.executor as se
        from core.skills.executor import SkillScriptExecutor, get_skill_executor

        se._executor = None
        executor = get_skill_executor()
        assert isinstance(executor, SkillScriptExecutor)
        assert get_skill_executor() is executor
        se._executor = None

# ---------------------------------------------------------------------------
# SkillWatcher tests
# ---------------------------------------------------------------------------

class TestSkillWatcher:
    """Tests for SkillWatcher."""

    def test_creation(self):
        """SkillWatcher initializes correctly."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        assert watcher._watch_paths is None
        assert watcher._task is None
        assert watcher.is_running is False

    def test_creation_with_paths(self):
        """SkillWatcher accepts custom watch paths."""
        from core.skills.watcher import SkillWatcher

        paths = [Path("/tmp/skills")]
        watcher = SkillWatcher(watch_paths=paths)
        assert watcher._watch_paths == paths

    @pytest.mark.asyncio
    async def test_start_no_watchfiles(self):
        """start is no-op when watchfiles not available."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        with patch("core.skills.watcher.WATCHFILES_AVAILABLE", False):
            await watcher.start()
        assert watcher.is_running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """start is no-op when already running."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        watcher._running = True
        with patch("core.skills.watcher.WATCHFILES_AVAILABLE", True):
            await watcher.start()
        # No task created since already running

    @pytest.mark.asyncio
    async def test_stop_not_running(self):
        """stop is no-op when not running."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        await watcher.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop_running(self):
        """stop cancels task and clears state."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        watcher._running = True

        # Create an actual asyncio.Task that's already done
        async def noop():
            pass

        loop = asyncio.get_event_loop()
        task = asyncio.ensure_future(noop())
        await task  # Let it complete
        watcher._task = task

        await watcher.stop()
        assert watcher.is_running is False
        assert watcher._task is None

    def test_is_running_property(self):
        """is_running reflects _running state."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        assert watcher.is_running is False
        watcher._running = True
        assert watcher.is_running is True

    def test_get_watch_paths_custom(self):
        """_get_watch_paths returns custom paths when set."""
        from core.skills.watcher import SkillWatcher

        paths = [Path("/custom/path")]
        watcher = SkillWatcher(watch_paths=paths)
        assert watcher._get_watch_paths() == paths

    def test_get_watch_paths_from_registry(self):
        """_get_watch_paths uses registry when no custom paths."""
        from core.skills.watcher import SkillWatcher

        watcher = SkillWatcher()
        with patch("core.skills.registry.get_skill_registry") as mock_reg:
            mock_registry = MagicMock()
            mock_registry.get_search_paths.return_value = [Path("/a"), Path("/b")]
            mock_reg.return_value = mock_registry
            paths = watcher._get_watch_paths()
        assert paths == [Path("/a"), Path("/b")]

class TestSkillWatcherGlobals:
    """Tests for global watcher functions."""

    def test_get_skill_watcher(self):
        """get_skill_watcher returns singleton."""
        import core.skills.watcher as sw
        from core.skills.watcher import SkillWatcher, get_skill_watcher

        sw._watcher = None
        watcher = get_skill_watcher()
        assert isinstance(watcher, SkillWatcher)
        assert get_skill_watcher() is watcher
        sw._watcher = None

    def test_is_hot_reload_available(self):
        """is_hot_reload_available reflects WATCHFILES_AVAILABLE."""
        from core.skills.watcher import is_hot_reload_available

        with patch("core.skills.watcher.WATCHFILES_AVAILABLE", True):
            assert is_hot_reload_available() is True
        with patch("core.skills.watcher.WATCHFILES_AVAILABLE", False):
            assert is_hot_reload_available() is False

    @pytest.mark.asyncio
    async def test_start_skill_watcher(self):
        """start_skill_watcher starts global watcher."""
        import core.skills.watcher as sw
        from core.skills.watcher import start_skill_watcher

        sw._watcher = None
        with patch("core.skills.watcher.WATCHFILES_AVAILABLE", False):
            await start_skill_watcher()
        sw._watcher = None

    @pytest.mark.asyncio
    async def test_stop_skill_watcher(self):
        """stop_skill_watcher stops global watcher."""
        import core.skills.watcher as sw
        from core.skills.watcher import stop_skill_watcher

        sw._watcher = None
        await stop_skill_watcher()  # Should not raise on fresh watcher
        sw._watcher = None
