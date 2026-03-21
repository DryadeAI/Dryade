"""Test-validate-iterate loop for the Agent Factory.

Runs factory-created artifacts through subprocess-isolated import checks
and smoke tests, with LLM-driven auto-fix on failure.
"""

import asyncio
import importlib
import logging
import re
import sys
from pathlib import Path

from core.factory.models import ArtifactType

logger = logging.getLogger(__name__)

__all__ = ["test_artifact", "generate_test_task"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOKEN_BUDGET = 200_000  # ~50K tokens * 4 chars/token approximation
_MAX_OUTPUT_LEN = 10_000  # truncate subprocess stdout/stderr
_DEFAULT_TIMEOUT = 30.0  # seconds
_RESPONSE_ESTIMATE = 2000  # estimated response chars for budget tracking

# Framework-to-package mapping for graceful fallback
_FRAMEWORK_PACKAGES: dict[str, str | None] = {
    "crewai": "crewai",
    "langchain": "langchain_core",
    "adk": "google.adk",
    "custom": None,  # always available
    "mcp_function": "fastmcp",
    "mcp_server": "fastmcp",
    "skill": None,  # always available (markdown only)
    "a2a": None,  # registry-only, no code execution
}

# Pattern to strip markdown code fences from LLM responses
_CODE_FENCE_RE = re.compile(r"^```(?:python)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)

# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

async def _run_test_subprocess(
    test_code: str, cwd: str, timeout: float = _DEFAULT_TIMEOUT
) -> tuple[bool, str, str]:
    """Run test code in an isolated subprocess.

    Follows the core/skills/executor.py subprocess isolation pattern:
    asyncio.create_subprocess with PIPE, wait_for with timeout,
    kill + reap on timeout.

    Args:
        test_code: Python code to run via ``python -c``.
        cwd: Working directory for the subprocess.
        timeout: Maximum execution time in seconds.

    Returns:
        Tuple of (success, stdout, stderr). stdout/stderr truncated
        to _MAX_OUTPUT_LEN characters.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            test_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    except OSError as exc:
        return (False, "", f"Failed to start subprocess: {exc}")

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()  # CRITICAL: reap to avoid zombies on DGX Spark
        return (False, "", f"Process timed out after {timeout}s")

    stdout = stdout_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_LEN]
    stderr = stderr_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_LEN]
    success = process.returncode == 0

    return (success, stdout, stderr)

# ---------------------------------------------------------------------------
# Framework availability check
# ---------------------------------------------------------------------------

def _check_framework_available(framework: str) -> bool:
    """Check whether the target framework's Python package is importable.

    Args:
        framework: Framework identifier from _FRAMEWORK_PACKAGES.

    Returns:
        True if the framework's package can be imported (or is None,
        meaning always available).
    """
    package = _FRAMEWORK_PACKAGES.get(framework)
    if package is None:
        return True
    try:
        importlib.import_module(package)
        return True
    except ImportError:
        return False

# ---------------------------------------------------------------------------
# LLM auto-fix
# ---------------------------------------------------------------------------

async def _attempt_fix(
    source_code: str,
    error_message: str,
    traceback_str: str,
    filename: str,
    budget_remaining: int,
) -> tuple[str | None, int]:
    """Ask the LLM to fix broken artifact code.

    Args:
        source_code: Current source code of the failing file.
        error_message: Short error description.
        traceback_str: Full traceback from the subprocess.
        filename: Name of the artifact file being fixed.
        budget_remaining: Remaining character budget for LLM calls.

    Returns:
        Tuple of (corrected_code_or_None, chars_consumed).
        Returns (None, 0) if budget exhausted or LLM call fails.
    """
    prompt = (
        "The factory-created artifact failed during testing.\n"
        f"ARTIFACT FILE: {filename}\n"
        f"ERROR: {error_message}\n"
        f"TRACEBACK: {traceback_str}\n"
        "SOURCE CODE:\n"
        f"{source_code}\n"
        f"Fix the error. Return ONLY the corrected source code for {filename}.\n"
        "Do not explain the fix -- just return the code."
    )

    prompt_chars = len(prompt)
    if prompt_chars + _RESPONSE_ESTIMATE > budget_remaining:
        logger.debug(
            "Auto-fix budget exhausted (need %d, have %d)",
            prompt_chars + _RESPONSE_ESTIMATE,
            budget_remaining,
        )
        return (None, 0)

    try:
        # Lazy import to keep module importable without LLM setup
        from core.factory._llm import call_llm

        response = await call_llm(
            prompt,
            system="You are a code repair assistant. Return only corrected source code.",
        )
    except Exception as exc:
        logger.warning("Auto-fix LLM call failed: %s", exc)
        return (None, 0)

    # Strip markdown code fences from response
    corrected = response.strip()
    fence_match = _CODE_FENCE_RE.match(corrected)
    if fence_match:
        corrected = fence_match.group(1)

    return (corrected, prompt_chars)

# ---------------------------------------------------------------------------
# Test task generation
# ---------------------------------------------------------------------------

def generate_test_task(artifact_type: ArtifactType, config: dict) -> str:
    """Generate a default test task for an artifact.

    Synchronous function, no LLM. Returns a user-provided test_task
    from config if available, otherwise a sensible default per type.

    Args:
        artifact_type: The type of artifact (agent/tool/skill).
        config: Artifact configuration dict (may contain 'test_task' key).

    Returns:
        A test task string.
    """
    user_task = config.get("test_task")
    if user_task and str(user_task).strip():
        return str(user_task).strip()

    if artifact_type == ArtifactType.AGENT:
        return (
            "Respond with a brief description of your capabilities and confirm you are operational."
        )
    elif artifact_type == ArtifactType.TOOL:
        return "Run the first available tool with minimal valid arguments."
    elif artifact_type == ArtifactType.SKILL:
        return "Validate skill frontmatter and instructions."

    return "Verify the artifact loads and responds."

# ---------------------------------------------------------------------------
# Main entry point: test_artifact
# ---------------------------------------------------------------------------

def _find_main_py(artifact_path: str) -> Path | None:
    """Find the main Python file in an artifact directory.

    Checks for __init__.py first, then {dirname}.py, then first .py file.
    """
    p = Path(artifact_path)
    init = p / "__init__.py"
    if init.is_file():
        return init

    named = p / f"{p.name}.py"
    if named.is_file():
        return named

    py_files = sorted(p.glob("*.py"))
    if py_files:
        return py_files[0]

    return None

async def test_artifact(
    artifact_path: str,
    artifact_type: ArtifactType,
    framework: str,
    test_task: str | None = None,
    max_iterations: int = 3,
) -> tuple[bool, int, str]:
    """Run subprocess-isolated import check and smoke test on an artifact.

    Main entry point for the test-validate-iterate loop. Runs the artifact
    through import verification and optional smoke testing, with LLM-driven
    auto-fix on failure (up to max_iterations with _TOKEN_BUDGET cap).

    When the target framework is not installed, gracefully returns success
    with a SCAFFOLDED status message instead of failing.

    Args:
        artifact_path: Path to the artifact directory.
        artifact_type: The type of artifact (agent/tool/skill).
        framework: Framework identifier for availability checking.
        test_task: Optional test task description.
        max_iterations: Maximum fix-retest cycles (default 3).

    Returns:
        Tuple of (passed, iterations_used, output_log).
    """
    log_parts: list[str] = []
    iterations_used = 0
    tokens_used = 0

    # Step 0: Check framework availability
    if not _check_framework_available(framework):
        msg = f"Framework '{framework}' not installed; marked SCAFFOLDED (smoke test skipped)"
        logger.info("test_artifact: %s", msg)
        return (True, 0, msg)

    # Step 1: IMPORT CHECK
    p = Path(artifact_path)
    if artifact_type == ArtifactType.SKILL:
        import_code = (
            f"from pathlib import Path; "
            f"p = Path({str(p)!r}) / 'SKILL.md'; "
            f"assert p.exists(), 'SKILL.md not found'; "
            f"text = p.read_text(); "
            f"assert len(text.strip()) > 10, 'SKILL.md is empty'"
        )
    else:
        parent_dir = str(p.parent)
        module_name = p.name
        import_code = (
            f"import sys; sys.path.insert(0, {parent_dir!r}); "
            f"import importlib; m = importlib.import_module({module_name!r})"
        )

    logger.debug("test_artifact: running import check for %s", artifact_path)
    import_ok, import_out, import_err = await _run_test_subprocess(import_code, artifact_path)
    log_parts.append(f"[IMPORT CHECK] passed={import_ok}")
    if import_out.strip():
        log_parts.append(f"  stdout: {import_out.strip()[:500]}")
    if import_err.strip():
        log_parts.append(f"  stderr: {import_err.strip()[:500]}")

    current_stage = "import"
    current_code = import_code
    stage_ok = import_ok

    # Step 2: SMOKE TEST (only if import passes and not a skill)
    if import_ok and artifact_type != ArtifactType.SKILL:
        _task = test_task or generate_test_task(artifact_type, {})  # noqa: F841
        parent_dir = str(p.parent)
        module_name = p.name
        smoke_code = (
            f"import sys; sys.path.insert(0, {parent_dir!r})\n"
            f"import importlib\n"
            f"try:\n"
            f"    m = importlib.import_module({module_name!r})\n"
            f"    attrs = [a for a in dir(m) if not a.startswith('_')]\n"
            f"    print(f'Module loaded: {{len(attrs)}} public attributes')\n"
            f"    # Phase 174.5: Functional validation — instantiate agent and check card\n"
            f"    agent_cls = None\n"
            f"    for name in attrs:\n"
            f"        obj = getattr(m, name)\n"
            f"        if isinstance(obj, type) and hasattr(obj, 'get_card') and hasattr(obj, 'execute'):\n"
            f"            agent_cls = obj\n"
            f"            break\n"
            f"    if agent_cls:\n"
            f"        agent = agent_cls()\n"
            f"        card = agent.get_card()\n"
            f"        caps = card.capabilities or []\n"
            f"        # Validate capability names aren't empty or dict-repr strings\n"
            f"        for cap in caps:\n"
            f"            if not cap.name or cap.name.startswith('{{'): \n"
            f"                print(f'BAD CAPABILITY: {{cap.name!r}}', file=sys.stderr)\n"
            f"                sys.exit(1)\n"
            f"        # Validate tools dict doesn't have empty keys\n"
            f"        if hasattr(agent, '_tools'):\n"
            f"            for k in agent._tools:\n"
            f"                if not k:\n"
            f"                    print('BAD TOOL: empty tool name in _tools dict', file=sys.stderr)\n"
            f"                    sys.exit(1)\n"
            f"        print(f'Agent validated: {{card.name}} with {{len(caps)}} capabilities')\n"
            f"    else:\n"
            f"        print('No agent class found (no get_card+execute), skipping functional check')\n"
            f"except Exception as e:\n"
            f"    print(f'Smoke test error: {{e}}', file=sys.stderr)\n"
            f"    sys.exit(1)\n"
        )

        logger.debug("test_artifact: running smoke test for %s", artifact_path)
        smoke_ok, smoke_out, smoke_err = await _run_test_subprocess(smoke_code, artifact_path)
        log_parts.append(f"[SMOKE TEST] passed={smoke_ok}")
        if smoke_out.strip():
            log_parts.append(f"  stdout: {smoke_out.strip()[:500]}")
        if smoke_err.strip():
            log_parts.append(f"  stderr: {smoke_err.strip()[:500]}")

        current_stage = "smoke"
        current_code = smoke_code
        stage_ok = smoke_ok

    # Auto-fix loop
    if not stage_ok:
        error_output = import_err if current_stage == "import" else smoke_err
        main_py = _find_main_py(artifact_path)

        while (
            not stage_ok
            and iterations_used < max_iterations
            and tokens_used < _TOKEN_BUDGET
            and main_py is not None
        ):
            iterations_used += 1
            logger.debug(
                "test_artifact: auto-fix iteration %d/%d (budget: %d/%d chars)",
                iterations_used,
                max_iterations,
                tokens_used,
                _TOKEN_BUDGET,
            )

            try:
                source_code = main_py.read_text(encoding="utf-8")
            except OSError as exc:
                log_parts.append(f"[FIX {iterations_used}] Cannot read {main_py}: {exc}")
                break

            corrected, chars_consumed = await _attempt_fix(
                source_code=source_code,
                error_message=error_output[:500],
                traceback_str=error_output[:2000],
                filename=main_py.name,
                budget_remaining=_TOKEN_BUDGET - tokens_used,
            )

            if corrected is None:
                log_parts.append(
                    f"[FIX {iterations_used}] Auto-fix returned None "
                    "(budget exhausted or LLM failure)"
                )
                break

            tokens_used += chars_consumed + _RESPONSE_ESTIMATE

            try:
                main_py.write_text(corrected, encoding="utf-8")
                log_parts.append(f"[FIX {iterations_used}] Applied fix to {main_py.name}")
            except OSError as exc:
                log_parts.append(f"[FIX {iterations_used}] Cannot write {main_py}: {exc}")
                break

            # Re-run the failed test stage
            retest_ok, retest_out, retest_err = await _run_test_subprocess(
                current_code, artifact_path
            )
            log_parts.append(f"[RETEST {iterations_used}] passed={retest_ok}")
            if retest_out.strip():
                log_parts.append(f"  stdout: {retest_out.strip()[:500]}")
            if retest_err.strip():
                log_parts.append(f"  stderr: {retest_err.strip()[:500]}")

            stage_ok = retest_ok
            error_output = retest_err

    output_log = "\n".join(log_parts)
    if stage_ok:
        logger.info(
            "test_artifact: PASSED for %s (%d iterations)",
            artifact_path,
            iterations_used,
        )
    else:
        logger.info(
            "test_artifact: FAILED for %s (%d iterations)",
            artifact_path,
            iterations_used,
        )

    return (stage_ok, iterations_used, output_log)
