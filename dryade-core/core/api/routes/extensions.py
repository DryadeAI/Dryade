"""Extension Observability API.

Provides status, metrics, timeline, and configuration for extensions.
The extension pipeline composes middleware-style extensions that execute
in priority order, each transforming or enriching the request/response.

Target: ~180 LOC
"""

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.api.models.openapi import response_with_errors
from core.auth.dependencies import get_db
from core.config import get_settings
from core.database.models import CacheEntry, ExtensionExecution, ExtensionTimeline
from core.extensions.pipeline import ExtensionType, get_extension_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extensions", tags=["extensions"])

class ExtensionStatus(BaseModel):
    """Status of a single extension in the pipeline.

    Extensions execute in priority order during request processing.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "semantic_cache",
                "type": "semantic_cache",
                "enabled": True,
                "priority": 10,
                "health": "healthy",
            }
        }
    )

    name: str = Field(..., description="Unique identifier for the extension")
    type: str = Field(
        ..., description="Extension type category (semantic_cache, sandbox, file_safety, etc.)"
    )
    enabled: bool = Field(
        ..., description="Whether the extension is currently active in the pipeline"
    )
    priority: int = Field(
        ..., ge=0, description="Execution order priority (lower = earlier in pipeline, 0-100)"
    )
    health: str = Field(
        ...,
        description="Health status: 'healthy' (fully operational), 'degraded' (fallback mode), 'down' (disabled)",
    )

class ExtensionMetrics(BaseModel):
    """Aggregated metrics across all extensions for impact analysis.

    Use to track cost savings, performance overhead, and security efficacy.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cache_hit_rate": 0.65,
                "cache_savings_usd": 12.50,
                "sandbox_overhead_ms": 45.3,
                "healing_success_rate": 0.92,
                "threats_blocked": 7,
                "validation_failures": 23,
                "total_requests": 1500,
            }
        }
    )

    cache_hit_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of cache hits to total cache-eligible requests (0.0-1.0)",
    )
    cache_savings_usd: float = Field(
        ...,
        ge=0.0,
        description="Estimated cost savings from cache hits in USD (assumes $0.002/query)",
    )
    sandbox_overhead_ms: float = Field(
        ..., ge=0.0, description="Average latency overhead from sandbox execution in milliseconds"
    )
    healing_success_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of successful automatic recoveries to total retry attempts (0.0-1.0)",
    )
    threats_blocked: int = Field(
        ..., ge=0, description="Count of malicious files/inputs blocked by security extensions"
    )
    validation_failures: int = Field(
        ..., ge=0, description="Count of input validation errors caught by safety extensions"
    )
    total_requests: int = Field(
        ..., ge=0, description="Total number of requests processed through the extension pipeline"
    )

class ExtensionTimelineEntry(BaseModel):
    """Timeline entry showing extension execution for a single request.

    Use to debug performance issues and understand extension behavior.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "req_abc123",
                "conversation_id": "conv_xyz789",
                "operation": "chat_completion",
                "extensions_applied": ["input_validation", "semantic_cache", "output_sanitization"],
                "total_duration_ms": 125.5,
                "outcomes": {"cache_hit": False, "validation_passed": True},
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    request_id: str = Field(..., description="Unique identifier for the request")
    conversation_id: str | None = Field(
        None, description="Associated conversation ID if part of a multi-turn conversation"
    )
    operation: str = Field(
        ..., description="Operation type (chat_completion, agent_execution, flow_run, etc.)"
    )
    extensions_applied: list[str] = Field(
        ..., description="Ordered list of extensions that executed for this request"
    )
    total_duration_ms: float = Field(
        ..., ge=0.0, description="Total time spent in extension pipeline in milliseconds"
    )
    outcomes: dict[str, Any] = Field(
        ...,
        description="Extension-specific outcomes (cache_hit, threats_found, validation_errors, etc.)",
    )
    timestamp: datetime = Field(..., description="UTC timestamp when the request was processed")

class ExtensionConfig(BaseModel):
    """Current configuration state for all extensions.

    Configuration is controlled via environment variables for runtime flexibility.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "extensions_enabled": True,
                "input_validation_enabled": True,
                "semantic_cache_enabled": True,
                "self_healing_enabled": True,
                "sandbox_enabled": True,
                "file_safety_enabled": True,
                "output_sanitization_enabled": True,
            }
        }
    )

    extensions_enabled: bool = Field(
        ..., description="Master switch for all extensions (DRYADE_EXTENSIONS_ENABLED)"
    )
    input_validation_enabled: bool = Field(
        ...,
        description="Enable input validation and sanitization (DRYADE_SAFETY_VALIDATION_ENABLED)",
    )
    semantic_cache_enabled: bool = Field(
        ..., description="Enable semantic similarity caching (DRYADE_SEMANTIC_CACHE_ENABLED)"
    )
    self_healing_enabled: bool = Field(
        ..., description="Enable automatic retry and recovery (DRYADE_SELF_HEALING_ENABLED)"
    )
    sandbox_enabled: bool = Field(
        ..., description="Enable code execution sandboxing (DRYADE_SANDBOX_ENABLED)"
    )
    file_safety_enabled: bool = Field(
        ..., description="Enable file scanning with ClamAV/YARA (DRYADE_FILE_SAFETY_ENABLED)"
    )
    output_sanitization_enabled: bool = Field(
        ...,
        description="Enable output sanitization for PII/secrets (DRYADE_OUTPUT_SANITIZATION_ENABLED)",
    )

@router.get(
    "/status",
    response_model=list[ExtensionStatus],
    responses=response_with_errors(500, 503),
    summary="Get all extension statuses",
    description="Returns status of all enabled extensions with health information.",
)
async def get_extensions_status():
    """Get status of all extensions in the pipeline.

    Returns list of enabled extensions with their current health status.
    Health is determined by checking external dependencies (Redis, Qdrant, ClamAV).

    Extension Pipeline Composition:
    - Extensions execute in priority order (lower priority = earlier execution)
    - Each extension can transform or short-circuit the request
    - Failed extensions may gracefully degrade without stopping the pipeline
    """
    registry = get_extension_registry()
    extensions = registry.get_enabled()

    status_list = []
    for ext in extensions:
        # Check health based on extension type
        health = await _check_extension_health(ext.type)

        status_list.append(
            ExtensionStatus(
                name=ext.name,
                type=ext.type,
                enabled=ext.enabled,
                priority=ext.priority,
                health=health,
            )
        )

    return status_list

@router.get(
    "/metrics",
    response_model=ExtensionMetrics,
    responses=response_with_errors(500, 503),
    summary="Get extension impact metrics",
    description="Returns aggregated metrics showing extension effectiveness and overhead.",
)
async def get_extensions_metrics(
    hours: int = Query(
        default=24,
        ge=1,
        le=168,
        description="Time window for metrics in hours (1-168, default: 24)",
    ),
    session: Session = Depends(get_db),
):
    """Get combined extension impact metrics.

    Aggregates metrics across all extensions to show:
    - Cost savings from semantic caching
    - Performance overhead from sandboxing
    - Security efficacy (threats blocked, validation failures)

    Use for dashboards and cost/benefit analysis of extensions.
    """
    since = datetime.now(UTC) - timedelta(hours=hours)

    # Cache metrics
    cache_entries = session.execute(select(CacheEntry).where(CacheEntry.created_at >= since))
    cache_entries = cache_entries.scalars().all()
    total_hits = sum(e.hit_count for e in cache_entries)
    total_cache_entries = len(cache_entries)
    cache_hit_rate = total_hits / max(total_cache_entries, 1)

    # Estimate cost savings (assume $0.002 per query saved)
    cache_savings_usd = total_hits * 0.002

    # Extension executions
    executions = session.execute(
        select(ExtensionExecution).where(ExtensionExecution.created_at >= since)
    )
    executions = executions.scalars().all()

    # Sandbox overhead
    sandbox_execs = [e for e in executions if e.extension_name == "sandbox"]
    sandbox_overhead_ms = sum(e.duration_ms for e in sandbox_execs) / max(len(sandbox_execs), 1)

    # Healing success rate
    healed_execs = [e for e in executions if e.healed]
    healing_success_rate = len(healed_execs) / max(len(executions), 1)

    # Threats blocked
    threats_blocked = sum(len(e.threats_found) for e in executions if e.threats_found)

    # Validation failures
    validation_failures = sum(len(e.validation_errors) for e in executions if e.validation_errors)

    # Total requests
    timeline_count = session.execute(
        select(func.count(ExtensionTimeline.id)).where(ExtensionTimeline.created_at >= since)
    )
    total_requests = timeline_count.scalar() or 0

    return ExtensionMetrics(
        cache_hit_rate=cache_hit_rate,
        cache_savings_usd=cache_savings_usd,
        sandbox_overhead_ms=sandbox_overhead_ms,
        healing_success_rate=healing_success_rate,
        threats_blocked=threats_blocked,
        validation_failures=validation_failures,
        total_requests=total_requests,
    )

@router.get(
    "/timeline",
    response_model=list[ExtensionTimelineEntry],
    responses=response_with_errors(500, 503),
    summary="Get extension activity timeline",
    description="Returns recent extension executions showing which extensions ran for each request.",
)
async def get_extensions_timeline(
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of timeline entries to return (1-1000, default: 100)",
    ),
    session: Session = Depends(get_db),
):
    """Get recent extension activity timeline.

    Returns per-request details showing:
    - Which extensions executed
    - Total pipeline duration
    - Extension-specific outcomes (cache hits, threats found, etc.)

    Use for debugging and performance analysis.
    """
    result = session.execute(
        select(ExtensionTimeline).order_by(ExtensionTimeline.created_at.desc()).limit(limit)
    )
    timeline = result.scalars().all()

    return [
        ExtensionTimelineEntry(
            request_id=entry.request_id,
            conversation_id=entry.conversation_id,
            operation=entry.operation,
            extensions_applied=entry.extensions_applied,
            total_duration_ms=entry.total_duration_ms,
            outcomes=entry.outcomes,
            timestamp=entry.created_at,
        )
        for entry in timeline
    ]

@router.get(
    "/config",
    response_model=ExtensionConfig,
    responses=response_with_errors(500),
    summary="Get extension configuration",
    description="Returns current enable/disable state for all extensions.",
)
async def get_extensions_config():
    """Get current extension configuration.

    Returns all extension enable/disable flags read from environment variables.
    Use to verify which extensions are active in the current deployment.
    """
    settings = get_settings()
    return ExtensionConfig(
        extensions_enabled=settings.extensions_enabled,
        input_validation_enabled=settings.safety_validation_enabled,
        semantic_cache_enabled=settings.semantic_cache_enabled,
        self_healing_enabled=settings.self_healing_enabled,
        sandbox_enabled=settings.sandbox_enabled,
        file_safety_enabled=settings.file_safety_enabled,
        output_sanitization_enabled=settings.output_sanitization_enabled,
    )

async def _check_extension_health(ext_type: ExtensionType) -> str:
    """Check health of extension based on type.

    Args:
        ext_type: Extension type

    Returns:
        "healthy", "degraded", or "down"
    """
    try:
        if ext_type == ExtensionType.SEMANTIC_CACHE:
            # Check Redis and Qdrant availability
            try:
                import redis
                from qdrant_client import QdrantClient

                # Quick connectivity check
                redis_host = os.getenv("REDIS_HOST", "localhost")
                redis_port = int(os.getenv("REDIS_PORT", "6379"))
                r = redis.Redis(host=redis_host, port=redis_port, socket_connect_timeout=1)
                r.ping()

                qdrant_host = os.getenv("QDRANT_HOST", "localhost")
                qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
                client = QdrantClient(host=qdrant_host, port=qdrant_port, timeout=1)
                client.get_collections()

                return "healthy"
            except Exception:
                return "degraded"  # Fallback to in-memory

        elif ext_type == ExtensionType.FILE_SAFETY:
            # Check ClamAV availability
            try:
                import pyclamd

                cd = pyclamd.ClamdNetworkSocket()
                cd.ping()
                return "healthy"
            except Exception:
                return "degraded"  # Graceful degradation

        else:
            # Other extensions don't have external dependencies
            return "healthy"

    except Exception as e:
        logger.error(f"Health check failed for {ext_type}: {e}")
        return "down"
