"""Skill script executor for sandboxed bash execution.

OpenClaw pattern: Skills have SKILL.md (instructions) + scripts/ folder (executables).
The LLM reads instructions and runs scripts via this sandboxed executor.

Security:
- Scripts run in subprocess with timeout
- Working directory restricted to skill_dir
- Environment variables controlled
- No shell expansion of user input
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.skills.models import Skill

logger = logging.getLogger(__name__)

# Default execution limits
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB

class ScriptExecutionResult(BaseModel):
    """Result of a skill script execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    timed_out: bool = False
    error: str | None = None
    script_path: str | None = None
    duration_ms: int = 0

class SkillScriptExecutor:
    """Execute skill scripts in a sandboxed environment.

    OpenClaw pattern:
    1. LLM reads skill instructions (SKILL.md)
    2. LLM decides to run a script: {skill.scripts_dir}/script.sh args...
    3. This executor runs the script with safety controls

    Example:
        executor = SkillScriptExecutor()
        result = await executor.execute(
            skill=summarize_skill,
            script="transcribe.sh",
            args=["/path/to/audio.m4a", "--model", "whisper-1"]
        )
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE,
        allowed_env_vars: list[str] | None = None,
    ):
        """Initialize executor.

        Args:
            timeout: Default execution timeout in seconds
            max_output_size: Maximum output size in bytes
            allowed_env_vars: Environment variables to pass through (None = safe defaults)
        """
        self.timeout = timeout
        self.max_output_size = max_output_size
        self.allowed_env_vars = allowed_env_vars or self._default_allowed_env_vars()

    def _default_allowed_env_vars(self) -> list[str]:
        """Safe environment variables to pass through."""
        return [
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "LC_ALL",
            "TERM",
            # API keys that skills commonly need
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            # Dryade-specific
            "DRYADE_WORKSPACE",
            "DRYADE_CONFIG_DIR",
        ]

    def _build_env(self, skill: Skill, extra_env: dict[str, str] | None = None) -> dict[str, str]:
        """Build safe environment for script execution.

        Args:
            skill: Skill being executed
            extra_env: Additional environment variables

        Returns:
            Safe environment dict
        """
        env = {}

        # Pass through allowed env vars
        for var in self.allowed_env_vars:
            if var in os.environ:
                env[var] = os.environ[var]

        # Add skill-specific vars
        env["SKILL_DIR"] = skill.skill_dir
        env["SKILL_NAME"] = skill.name
        if skill.scripts_dir:
            env["SCRIPTS_DIR"] = skill.scripts_dir

        # Add extra env vars (skill-specific config)
        if extra_env:
            env.update(extra_env)

        return env

    async def execute(
        self,
        skill: Skill,
        script: str,
        args: list[str] | None = None,
        timeout: int | None = None,
        extra_env: dict[str, str] | None = None,
        stdin_data: str | None = None,
    ) -> ScriptExecutionResult:
        """Execute a skill script.

        Args:
            skill: Skill containing the script
            script: Script filename (e.g., "transcribe.sh")
            args: Command line arguments
            timeout: Execution timeout (uses default if None)
            extra_env: Additional environment variables
            stdin_data: Data to pass to stdin

        Returns:
            ScriptExecutionResult with stdout, stderr, return code
        """
        import time

        start_time = time.perf_counter()

        # Validate skill has scripts
        if not skill.scripts_dir:
            return ScriptExecutionResult(
                success=False,
                error=f"Skill '{skill.name}' has no scripts/ folder",
            )

        # Get full script path
        script_path = skill.get_script_path(script)
        if not script_path:
            available = skill.get_scripts()
            return ScriptExecutionResult(
                success=False,
                error=f"Script '{script}' not found in skill '{skill.name}'. Available: {available}",
                script_path=script_path,
            )

        # Validate script is executable
        script_file = Path(script_path)
        if not os.access(script_file, os.X_OK):
            # Try to make it executable
            try:
                os.chmod(script_file, 0o755)
                logger.debug(f"Made script executable: {script_path}")
            except OSError as e:
                return ScriptExecutionResult(
                    success=False,
                    error=f"Script not executable and cannot chmod: {e}",
                    script_path=script_path,
                )

        # Build command
        cmd = [script_path] + (args or [])

        # Build environment
        env = self._build_env(skill, extra_env)

        # Execute with timeout
        timeout_seconds = timeout or self.timeout

        logger.info(f"[SKILL] Executing: {script} args={args} timeout={timeout_seconds}s")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                cwd=skill.skill_dir,  # Run in skill directory
                env=env,
            )

            stdin_bytes = stdin_data.encode() if stdin_data else None

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_bytes),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                return ScriptExecutionResult(
                    success=False,
                    timed_out=True,
                    error=f"Script execution timed out after {timeout_seconds}s",
                    script_path=script_path,
                    return_code=-1,
                    duration_ms=duration_ms,
                )

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Decode output with size limit
            stdout_str = stdout.decode("utf-8", errors="replace")[: self.max_output_size]
            stderr_str = stderr.decode("utf-8", errors="replace")[: self.max_output_size]

            success = process.returncode == 0

            if not success:
                logger.warning(f"[SKILL] Script failed: {script} returncode={process.returncode}")
            else:
                logger.info(f"[SKILL] Script completed: {script} duration={duration_ms}ms")

            return ScriptExecutionResult(
                success=success,
                stdout=stdout_str,
                stderr=stderr_str,
                return_code=process.returncode or 0,
                script_path=script_path,
                duration_ms=duration_ms,
            )

        except FileNotFoundError:
            return ScriptExecutionResult(
                success=False,
                error=f"Script not found: {script_path}",
                script_path=script_path,
            )
        except PermissionError:
            return ScriptExecutionResult(
                success=False,
                error=f"Permission denied executing: {script_path}",
                script_path=script_path,
            )
        except Exception as e:
            logger.exception(f"[SKILL] Script execution error: {e}")
            return ScriptExecutionResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                script_path=script_path,
            )

    def list_scripts(self, skill: Skill) -> list[dict[str, Any]]:
        """List available scripts for a skill with metadata.

        Args:
            skill: Skill to inspect

        Returns:
            List of script info dicts
        """
        if not skill.scripts_dir:
            return []

        scripts = []
        scripts_path = Path(skill.scripts_dir)

        for script_file in scripts_path.iterdir():
            if script_file.is_file() and not script_file.name.startswith("."):
                scripts.append(
                    {
                        "name": script_file.name,
                        "path": str(script_file),
                        "executable": os.access(script_file, os.X_OK),
                        "size_bytes": script_file.stat().st_size,
                    }
                )

        return scripts

# Singleton executor instance
_executor: SkillScriptExecutor | None = None

def get_skill_executor() -> SkillScriptExecutor:
    """Get or create global skill script executor."""
    global _executor
    if _executor is None:
        _executor = SkillScriptExecutor()
    return _executor
