"""Sandbox Management Endpoints.

Provides monitoring, statistics, and management for the code execution sandbox.
The sandbox enforces isolation levels based on tool risk classification:

Isolation Levels:
- NONE: Direct execution for trusted operations (read-only tools)
- PROCESS: Subprocess isolation with resource limits (standard tools)
- CONTAINER: Docker container with restricted capabilities (file/network tools)
- GVISOR: Maximum isolation with gVisor runtime (untrusted code execution)

Target: ~150 LOC
"""

import asyncio
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

import core.extensions as _extensions
from core.api.models.openapi import response_with_errors
from core.logs import get_logger
from core.utils.time import utcnow

# Maximum output size per stream (stdout/stderr) — 50KB
_MAX_OUTPUT_BYTES = 50 * 1024

router = APIRouter(tags=["sandbox"])
logger = get_logger(__name__)

class RegistryStats(BaseModel):
    """Sandbox registry statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "total_tools": 25,
                "default_level": "process",
                "by_level": {"none": 5, "process": 15, "container": 4, "gvisor": 1},
            }
        }
    )

    enabled: bool = Field(..., description="Whether sandboxing is globally enabled")
    total_tools: int = Field(
        ..., ge=0, description="Total number of registered tools with isolation levels"
    )
    default_level: str = Field(
        ...,
        description="Default isolation level for unregistered tools (none, process, container, gvisor)",
    )
    by_level: dict[str, int] = Field(..., description="Tool count per isolation level")

class CacheStats(BaseModel):
    """Sandbox cache statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "hits": 150,
                "misses": 50,
                "hit_rate": 0.75,
                "memory_cache_size": 45,
                "redis_available": True,
            }
        }
    )

    enabled: bool = Field(..., description="Whether caching is enabled for sandbox results")
    hits: int = Field(..., ge=0, description="Number of cache hits")
    misses: int = Field(..., ge=0, description="Number of cache misses")
    hit_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Cache hit ratio (hits / total_lookups)"
    )
    memory_cache_size: int = Field(..., ge=0, description="Number of entries in in-memory cache")
    redis_available: bool = Field(..., description="Whether Redis cache backend is available")

class SandboxStatsResponse(BaseModel):
    """Comprehensive sandbox statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "registry": {"enabled": True, "total_tools": 25, "default_level": "process"},
                "cache": {"enabled": True, "hit_rate": 0.75, "redis_available": True},
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    registry: dict[str, Any] = Field(
        ..., description="Registry statistics: enabled status, tool counts, isolation levels"
    )
    cache: dict[str, Any] = Field(
        ..., description="Cache statistics: hit rate, memory size, Redis availability"
    )
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of statistics snapshot")

class SandboxConfigUpdate(BaseModel):
    """Request to update sandbox configuration at runtime."""

    model_config = ConfigDict(json_schema_extra={"example": {"enabled": True}})

    enabled: bool | None = Field(
        None, description="Enable (true) or disable (false) sandboxing globally"
    )

class SandboxConfigResponse(BaseModel):
    """Response after sandbox configuration update."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Configuration updated successfully",
                "updates": {"enabled": True},
                "current_config": {"enabled": True, "total_tools": 25, "default_level": "process"},
                "note": "Changes are not persisted. Update environment variables to persist.",
            }
        }
    )

    message: str = Field(..., description="Result message")
    updates: dict[str, Any] = Field(..., description="Changes that were applied")
    current_config: dict[str, Any] = Field(..., description="Current configuration after updates")
    note: str = Field(..., description="Important note about persistence")

class CacheClearResponse(BaseModel):
    """Response after clearing sandbox cache."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Sandbox cache cleared successfully",
                "entries_before": 45,
                "hits_before": 150,
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    message: str = Field(..., description="Result message")
    entries_before: int = Field(..., ge=0, description="Number of cache entries before clearing")
    hits_before: int = Field(..., ge=0, description="Total hits before clearing")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

class SandboxHealthResponse(BaseModel):
    """Sandbox system health status."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "healthy": True,
                "issues": None,
                "sandbox": {"enabled": True, "total_tools": 25, "default_level": "process"},
                "cache": {"enabled": True, "hit_rate": 0.75, "redis_available": True},
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    healthy: bool = Field(..., description="Overall sandbox system health")
    issues: list[str] | None = Field(None, description="List of issues if not healthy")
    sandbox: dict[str, Any] = Field(..., description="Sandbox configuration status")
    cache: dict[str, Any] = Field(..., description="Cache status")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

class ToolIsolationResponse(BaseModel):
    """Tool isolation level listing response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tools": {"file_write": "container", "shell_exec": "gvisor"},
                "by_isolation_level": {"none": ["read_file"], "container": ["file_write"]},
                "total_tools": 25,
                "default_level": "process",
            }
        }
    )

    tools: dict[str, str] = Field(..., description="Tool name to isolation level mapping")
    by_isolation_level: dict[str, list[str]] = Field(
        ..., description="Tools grouped by their isolation level"
    )
    total_tools: int = Field(..., ge=0, description="Total number of registered tools")
    default_level: str = Field(..., description="Default isolation level for unregistered tools")

@router.get(
    "/stats",
    response_model=SandboxStatsResponse,
    responses=response_with_errors(500, 503),
    summary="Get sandbox statistics",
    description="Returns registry and cache statistics for the sandbox system.",
)
async def get_sandbox_stats():
    """Get comprehensive sandbox statistics.

    Returns:
    - Registry stats: enabled status, tool counts, isolation level distribution
    - Cache stats: hit rate, total lookups, memory size, Redis availability

    Isolation Levels (from least to most isolated):
    - NONE: Direct execution, no overhead
    - PROCESS: Subprocess with resource limits (~10ms overhead)
    - CONTAINER: Docker container (~50ms overhead)
    - GVISOR: gVisor runtime (~100ms overhead)

    Use for monitoring and capacity planning.
    """
    try:
        registry = _extensions.get_sandbox_registry()
        cache = _extensions.get_sandbox_cache()

        return SandboxStatsResponse(
            registry=registry.get_stats(),
            cache=cache.get_stats(),
            timestamp=utcnow().isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to get sandbox stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sandbox statistics: {str(e)}",
        ) from e

@router.post(
    "/config",
    response_model=SandboxConfigResponse,
    responses=response_with_errors(400, 500),
    summary="Update sandbox configuration",
    description="Update sandbox settings at runtime. Changes are not persisted.",
)
async def update_sandbox_config(request: SandboxConfigUpdate):
    """Update sandbox configuration dynamically.

    Allows runtime configuration changes:
    - Enable/disable sandboxing globally

    IMPORTANT: Configuration changes take effect immediately but are NOT persisted.
    To persist changes, update the DRYADE_SANDBOX_ENABLED environment variable.

    Use for:
    - Emergency disabling during incidents
    - Testing different configurations
    """
    try:
        registry = _extensions.get_sandbox_registry()
        updates = {}

        if request.enabled is not None:
            registry.set_enabled(request.enabled)
            updates["enabled"] = request.enabled
            logger.info(f"Sandbox {'enabled' if request.enabled else 'disabled'} globally")

        return {
            "message": "Configuration updated successfully",
            "updates": updates,
            "current_config": {
                "enabled": registry.is_enabled(),
                "total_tools": len(registry.get_all_levels()),
                "default_level": registry.get_stats()["default_level"],
            },
            "note": "Changes are not persisted. Update environment variables to persist.",
        }

    except Exception as e:
        logger.error(f"Failed to update sandbox config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update sandbox configuration: {str(e)}",
        ) from e

@router.delete(
    "/cache/clear",
    response_model=CacheClearResponse,
    responses=response_with_errors(500),
    summary="Clear sandbox cache",
    description="Clear all cached sandbox results. Use with caution.",
)
async def clear_sandbox_cache():
    """Clear sandbox result cache.

    Clears:
    - Redis cached sandbox results
    - In-memory cache fallback

    WARNING: This will force re-execution of all sandboxed operations
    until the cache is repopulated, increasing latency.

    Use for:
    - After tool updates that change behavior
    - Clearing corrupted cache entries
    - Testing without caching
    """
    try:
        cache = _extensions.get_sandbox_cache()

        # Get stats before clearing
        stats_before = cache.get_stats()

        # Clear cache
        success = cache.clear()

        if success:
            logger.info("Sandbox cache cleared successfully")
            return {
                "message": "Sandbox cache cleared successfully",
                "entries_before": stats_before["memory_cache_size"],
                "hits_before": stats_before["hits"],
                "timestamp": utcnow().isoformat(),
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to clear sandbox cache",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear sandbox cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear sandbox cache: {str(e)}",
        ) from e

@router.get(
    "/health",
    response_model=SandboxHealthResponse,
    responses=response_with_errors(500),
    summary="Check sandbox health",
    description="Returns sandbox system health status for monitoring.",
)
async def sandbox_health():
    """Check sandbox system health.

    Returns:
    - Sandbox enabled status
    - Cache availability and hit rate
    - Tool counts by isolation level
    - Issues and warnings

    Health Criteria:
    - Redis cache available (warning if not)
    - Cache hit rate > 20% (warning if not, after 100+ lookups)

    Use for monitoring dashboards and alerting.
    """
    try:
        registry = _extensions.get_sandbox_registry()
        cache = _extensions.get_sandbox_cache()

        registry_stats = registry.get_stats()
        cache_stats = cache.get_stats()

        healthy = True
        issues = []

        # Check for potential issues
        if not registry_stats["enabled"]:
            issues.append("Sandbox disabled globally")

        if not cache_stats["redis_available"]:
            issues.append("Redis cache unavailable (using in-memory fallback)")

        # Calculate cache efficiency
        cache_hit_rate = cache_stats["hit_rate"]
        if cache_stats["total_lookups"] > 100 and cache_hit_rate < 0.2:
            issues.append(f"Low cache hit rate: {cache_hit_rate:.1%}")

        return {
            "healthy": healthy,
            "issues": issues if issues else None,
            "sandbox": {
                "enabled": registry_stats["enabled"],
                "total_tools": registry_stats["total_tools"],
                "default_level": registry_stats["default_level"],
            },
            "cache": {
                "enabled": cache_stats["enabled"],
                "hit_rate": cache_stats["hit_rate"],
                "redis_available": cache_stats["redis_available"],
            },
            "timestamp": utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to check sandbox health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check sandbox health: {str(e)}",
        ) from e

@router.get(
    "/tools",
    response_model=ToolIsolationResponse,
    responses=response_with_errors(500),
    summary="List tool isolation levels",
    description="Returns all tools with their configured isolation levels.",
)
async def list_sandboxed_tools():
    """List all tools with their configured isolation levels.

    Returns:
    - Tool name to isolation level mapping
    - Tools grouped by isolation level
    - Default level for unregistered tools

    Isolation Level Risk Classification:
    - NONE: Trusted, read-only (e.g., get_time, list_directory)
    - PROCESS: Standard tools (e.g., calculate, format_text)
    - CONTAINER: File/network access (e.g., write_file, http_request)
    - GVISOR: Untrusted execution (e.g., execute_code, run_script)

    Use for security auditing and configuration verification.
    """
    try:
        registry = _extensions.get_sandbox_registry()
        all_levels = registry.get_all_levels()

        # Group tools by isolation level
        by_level = {}
        for tool_name, level in all_levels.items():
            level_str = level.value
            if level_str not in by_level:
                by_level[level_str] = []
            by_level[level_str].append(tool_name)

        return {
            "tools": {tool: level.value for tool, level in all_levels.items()},
            "by_isolation_level": by_level,
            "total_tools": len(all_levels),
            "default_level": registry.get_stats()["default_level"],
        }

    except Exception as e:
        logger.error(f"Failed to list sandboxed tools: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sandboxed tools: {str(e)}",
        ) from e

# ── Code execution endpoint ─────────────────────────────────────────

class CodeExecuteRequest(BaseModel):
    """Request to execute code in the sandbox."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "print('hello')",
                "language": "python",
                "timeout_seconds": 30,
            }
        }
    )

    code: str = Field(..., min_length=1, description="Code to execute")
    language: Literal["python", "bash", "sh"] = Field(
        default="python",
        description="Language / interpreter to use",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Maximum execution time in seconds (1-120)",
    )

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str) -> str:
        allowed = {"python", "bash", "sh"}
        if v not in allowed:
            msg = f"Language must be one of {sorted(allowed)}, got '{v}'"
            raise ValueError(msg)
        return v

class CodeExecuteResponse(BaseModel):
    """Response from code execution."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "stdout": "hello\n",
                "stderr": "",
                "exit_code": 0,
                "execution_time_ms": 42.5,
            }
        }
    )

    success: bool = Field(..., description="True when exit code is 0")
    stdout: str = Field(..., description="Standard output (truncated at 50 KB)")
    stderr: str = Field(..., description="Standard error (truncated at 50 KB)")
    exit_code: int = Field(..., description="Process exit code")
    execution_time_ms: float = Field(..., ge=0, description="Wall-clock time in milliseconds")

def _truncate(data: bytes) -> str:
    """Decode bytes to UTF-8, truncating to *_MAX_OUTPUT_BYTES* if needed."""
    text = data.decode("utf-8", errors="replace")
    if len(data) > _MAX_OUTPUT_BYTES:
        text = text[:_MAX_OUTPUT_BYTES] + "\n[output truncated]"
    return text

@router.post(
    "/execute",
    response_model=CodeExecuteResponse,
    responses=response_with_errors(400, 500),
    summary="Execute code in sandbox",
    description="Execute Python or shell code in an isolated subprocess.",
)
async def execute_code(request: CodeExecuteRequest):
    """Execute user-supplied code in a subprocess.

    Supports Python and bash/sh. Enforces a hard timeout ceiling of 120 s
    and truncates stdout/stderr at 50 KB each.

    Uses asyncio.create_subprocess_exec (not shell) for safety — the code
    string is passed as a single argument to the interpreter, preventing
    shell injection.
    """
    if request.language == "python":
        cmd = ["python", "-c", request.code]
    else:
        # bash -c treats code as a single argument — no shell expansion
        cmd = ["bash", "-c", request.code]

    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_raw, stderr_raw = await asyncio.wait_for(
            proc.communicate(),
            timeout=request.timeout_seconds,
        )
    except asyncio.TimeoutError:
        elapsed_ms = (time.monotonic() - t0) * 1000
        try:
            proc.kill()  # type: ignore[possibly-undefined]
        except ProcessLookupError:
            pass
        return CodeExecuteResponse(
            success=False,
            stdout="",
            stderr=f"Execution timed out after {request.timeout_seconds}s",
            exit_code=-1,
            execution_time_ms=round(elapsed_ms, 1),
        )
    except Exception as e:
        logger.error(f"Failed to execute code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(e)}",
        ) from e

    elapsed_ms = (time.monotonic() - t0) * 1000

    return CodeExecuteResponse(
        success=proc.returncode == 0,
        stdout=_truncate(stdout_raw),
        stderr=_truncate(stderr_raw),
        exit_code=proc.returncode or 0,
        execution_time_ms=round(elapsed_ms, 1),
    )
