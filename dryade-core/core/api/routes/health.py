"""Health check endpoints with comprehensive dependency verification.

Provides health, readiness, and liveness endpoints for monitoring and orchestration.
These endpoints follow Kubernetes probe conventions:

- /live: Liveness probe - restart container if fails (process health only)
- /ready: Readiness probe - don't route traffic if fails (dependency health)
- /health: Comprehensive health check for monitoring dashboards

Target: 200 LOC
"""

import asyncio
import platform
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

from core import __version__
from core.api.models.openapi import response_with_errors
from core.config import get_settings
from core.extensions import get_all_circuit_breakers
from core.extensions.request_queue import get_request_queue
from core.health_checks import (
    HealthStatus,
    check_all_dependencies,
    get_plugin_health_registry,
)
from core.logs import get_logger
from core.utils.time import utcnow

router = APIRouter(tags=["health"])
logger = get_logger(__name__)

# Health check caching to prevent thundering herd
_health_cache: dict[str, HealthStatus] = {}
_health_cache_time: datetime | None = None
_health_lock = asyncio.Lock()
_CACHE_TTL_SECONDS = 5

# Metrics collection
health_check_counts = defaultdict(int)
health_check_failures = defaultdict(int)

# Response Models

class DependencyCheck(BaseModel):
    """Health status for a single dependency.

    Represents the result of checking one external service or resource.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"healthy": True, "latency_ms": 12.5, "message": "Connected successfully"}
        }
    )

    healthy: bool = Field(..., description="Whether the dependency is operational")
    latency_ms: float | None = Field(
        None, ge=0.0, description="Response time for health check in milliseconds"
    )
    message: str = Field(..., description="Human-readable status message or error details")

class QueueStatus(BaseModel):
    """Request queue status for load monitoring."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "healthy", "active": 5, "queued": 0, "max_concurrent": 50}
        }
    )

    status: str = Field(
        ...,
        description="Queue status: 'healthy' (empty), 'busy' (has queued), 'overloaded' (>80% capacity)",
    )
    active: int = Field(..., ge=0, description="Number of requests currently being processed")
    queued: int = Field(..., ge=0, description="Number of requests waiting in queue")
    max_concurrent: int = Field(..., ge=1, description="Maximum concurrent requests allowed")

class HealthResponse(BaseModel):
    """Comprehensive health check response.

    Includes overall status, per-dependency checks, and queue status.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "timestamp": "2026-01-13T12:00:00Z",
                "checks": {
                    "database": {"healthy": True, "latency_ms": 5.2, "message": "Connected"},
                    "redis": {"healthy": True, "latency_ms": 1.1, "message": "Connected"},
                },
                "queue": {"status": "healthy", "active": 3, "queued": 0, "max_concurrent": 50},
                "warnings": [],
            }
        }
    )

    status: str = Field(
        ...,
        description="Overall health: 'healthy' (all critical OK), 'degraded' (optional down), 'unhealthy' (critical down)",
    )
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of health check")
    checks: dict[str, DependencyCheck] = Field(
        ..., description="Per-dependency health check results"
    )
    components: dict[str, dict] | None = Field(
        default=None, description="Frontend-oriented component map"
    )
    queue: QueueStatus = Field(..., description="Request queue status")
    warnings: list[str] | None = Field(
        None, description="List of non-critical issues (optional dependencies down)"
    )

class ReadinessResponse(BaseModel):
    """Readiness probe response for Kubernetes.

    Kubernetes uses this to determine if the pod should receive traffic.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ready": True,
                "message": "Service ready",
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    ready: bool = Field(..., description="True if service can accept traffic")
    message: str = Field(..., description="Human-readable status explanation")
    timestamp: str | None = Field(None, description="ISO 8601 UTC timestamp (included when ready)")
    checks: dict[str, DependencyCheck] | None = Field(
        None, description="Per-dependency status (included when not ready)"
    )

class LivenessResponse(BaseModel):
    """Liveness probe response for Kubernetes.

    Kubernetes uses this to determine if the container needs restart.
    Does NOT check dependencies to prevent restart loops.
    """

    model_config = ConfigDict(
        json_schema_extra={"example": {"alive": True, "timestamp": "2026-01-13T12:00:00Z"}}
    )

    alive: bool = Field(True, description="Always true if the process is running")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

class DetailedHealthResponse(BaseModel):
    """Detailed health information for debugging and monitoring dashboards."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "service": "dryade-api",
                "version": "1.0.0",
                "environment": "production",
                "platform": "Linux",
                "python_version": "3.11.0",
                "dependencies": {},
            }
        }
    )

    status: str = Field(..., description="Overall health status")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    components: dict[str, dict] | None = Field(
        default=None, description="Frontend-oriented component map"
    )
    service: str = Field(..., description="Service name identifier")
    version: str = Field(..., description="API version string")
    environment: str = Field(
        ..., description="Deployment environment (development, staging, production)"
    )
    platform: str = Field(..., description="Operating system platform")
    python_version: str = Field(..., description="Python runtime version")
    dependencies: dict[str, DependencyCheck] = Field(
        ..., description="Detailed dependency health checks with latency"
    )
    uptime_seconds: int = Field(..., description="Process uptime in seconds")

class HealthMetricsResponse(BaseModel):
    """Health check metrics for monitoring and alerting."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "checks_total": {"database": 150, "redis": 150},
                "failures_total": {"database": 0, "redis": 2},
                "failure_rates": {"database": 0.0, "redis": 1.33},
            }
        }
    )

    checks_total: dict[str, int] = Field(
        ..., description="Total health checks performed per dependency"
    )
    failures_total: dict[str, int] = Field(
        ..., description="Total failed health checks per dependency"
    )
    failure_rates: dict[str, float] = Field(
        ..., description="Failure rate percentage per dependency (0-100)"
    )

class CircuitBreakerState(BaseModel):
    """Circuit breaker state response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "llm_api",
                "state": "closed",
                "failure_count": 0,
                "failure_threshold": 5,
                "timeout_seconds": 60,
                "last_failure_time": None,
                "last_state_change": "2026-01-30T12:00:00",
            }
        }
    )

    name: str = Field(..., description="Circuit breaker identifier")
    state: str = Field(..., description="Current state: closed, open, or half_open")
    failure_count: int = Field(..., description="Current consecutive failure count")
    failure_threshold: int = Field(..., description="Failures needed to open circuit")
    timeout_seconds: int = Field(..., description="Seconds before retry in open state")
    last_failure_time: str | None = Field(None, description="ISO timestamp of last failure")
    last_state_change: str = Field(..., description="ISO timestamp of last state transition")

class CircuitBreakersResponse(BaseModel):
    """Response listing all circuit breakers."""

    circuit_breakers: list[CircuitBreakerState] = Field(
        ..., description="All registered circuit breakers"
    )
    count: int = Field(..., description="Total number of circuit breakers")

class CircuitBreakerResetResponse(BaseModel):
    """Response after resetting a circuit breaker."""

    message: str = Field(..., description="Success message")
    circuit_breaker: CircuitBreakerState = Field(..., description="Updated circuit breaker state")

async def get_cached_health() -> dict[str, HealthStatus]:
    """Get health status with 5-second cache.

    Prevents overwhelming dependencies with health checks during
    high request load or orchestration probe storms. Uses asyncio.Lock
    with double-check pattern to prevent thundering herd -- only one
    concurrent caller performs the actual health check.

    Returns:
        Dictionary of service name to HealthStatus
    """
    global _health_cache, _health_cache_time

    # Fast path: cache is fresh (no lock needed)
    now = utcnow()
    if _health_cache and _health_cache_time:
        if (now - _health_cache_time).total_seconds() < _CACHE_TTL_SECONDS:
            return _health_cache

    # Slow path: acquire lock, double-check
    async with _health_lock:
        now = utcnow()
        if _health_cache and _health_cache_time:
            if (now - _health_cache_time).total_seconds() < _CACHE_TTL_SECONDS:
                return _health_cache

        checks = await check_all_dependencies()
        _health_cache = checks
        _health_cache_time = now

        # Record metrics
        for service, check in checks.items():
            health_check_counts[service] += 1
            if not check.healthy:
                health_check_failures[service] += 1

    return _health_cache

@router.get(
    "/health",
    responses=response_with_errors(503),
    summary="Comprehensive health check",
    description="Returns full health status including all dependency checks and queue status.",
)
async def health_check(response: Response):
    """Comprehensive health check for monitoring dashboards.

    Returns 200 if all critical dependencies healthy.
    Returns 503 if any critical dependency unhealthy.
    Returns 200 with warnings if optional dependencies down.

    Dependency Classification:
    - Critical (causes 503): database
    - Important (causes warning): Redis, Qdrant
    - Optional (no impact): Neo4j

    Use for:
    - Monitoring dashboards (Grafana, Datadog)
    - Load balancer health checks
    - Debugging connectivity issues
    """
    checks = await get_cached_health()

    # Get plugin health check metadata for categorization
    plugin_registry = get_plugin_health_registry()
    plugin_check_info = plugin_registry.get_check_info()

    # Core infrastructure categories
    core_categories = {
        "database": "critical",
        "redis": "important",
        "qdrant": "important",
        "neo4j": "optional",
    }

    # Determine overall health
    critical_healthy = checks.get("database", HealthStatus(False, "not found")).healthy
    important_issues = []

    # Check important (but not critical) dependencies
    for name, check in checks.items():
        # Determine category
        if name in core_categories:
            category = core_categories[name]
        elif name in plugin_check_info:
            category = plugin_check_info[name]["category"]
        else:
            category = "optional"

        # Track important issues
        if (
            category == "important"
            and not check.healthy
            and "not configured" not in check.message.lower()
        ):
            important_issues.append(name)

        # Track critical issues from plugins
        if category == "critical" and not check.healthy:
            critical_healthy = False

    # Get queue status
    queue = get_request_queue()
    queue_stats = await queue.get_stats()
    queue_status = "healthy" if queue_stats.queued_requests == 0 else "busy"
    if queue_stats.queued_requests >= queue_stats.max_queue_size * 0.8:
        queue_status = "overloaded"

    # Build response
    status_label = "healthy" if critical_healthy else "unhealthy"
    if status_label == "healthy" and important_issues:
        status_label = "degraded"

    components = {}
    for name, check in checks.items():
        # Determine category and plugin source
        if name in core_categories:
            category = core_categories[name]
            plugin_name = None
        elif name in plugin_check_info:
            category = plugin_check_info[name]["category"]
            plugin_name = plugin_check_info[name]["plugin"]
        else:
            category = "optional"
            plugin_name = None

        component_data = {
            "status": "healthy" if check.healthy else "unhealthy",
            "category": category,
            "latency_ms": check.latency_ms,
            "message": check.message,
        }
        if plugin_name:
            component_data["plugin"] = plugin_name

        components[name] = component_data

    queue_component = {
        "status": queue_status,
        "category": "important",
        "latency_ms": None,
        "message": f"active={queue_stats.active_requests}, queued={queue_stats.queued_requests}",
    }
    components["queue"] = queue_component

    response_data = {
        "status": status_label,
        "timestamp": utcnow().isoformat(),
        "checks": {name: check.to_dict() for name, check in checks.items()},
        "components": components,
        "queue": {
            "status": queue_status,
            "active": queue_stats.active_requests,
            "queued": queue_stats.queued_requests,
            "max_concurrent": queue_stats.max_concurrent,
        },
    }

    if important_issues:
        response_data["warnings"] = [f"{svc} unavailable" for svc in important_issues]

    # Set appropriate status code
    if not critical_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.error(
            "Health check failed: critical dependencies unhealthy", extra={"checks": response_data}
        )
    elif important_issues:
        response.status_code = status.HTTP_200_OK
        logger.warning(
            "Health check degraded: optional services down", extra={"warnings": important_issues}
        )
    else:
        response.status_code = status.HTTP_200_OK

    return response_data

@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses=response_with_errors(503),
    summary="Kubernetes readiness probe",
    description="Returns 200 if ready to accept traffic, 503 if not ready.",
)
async def readiness_check(response: Response):
    """Readiness probe for Kubernetes orchestration.

    Returns 200 if service ready to accept traffic.
    Returns 503 if critical dependencies unavailable.

    Kubernetes Configuration:
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
          failureThreshold: 3

    Behavior:
    - Failing probe removes pod from Service endpoints
    - Traffic stops routing to this pod
    - Pod is NOT restarted (use /live for that)
    """
    checks = await get_cached_health()

    # Ready only if critical and important dependencies healthy
    database_ok = checks["database"].healthy
    redis_ok = checks["redis"].healthy or "not configured" in checks["redis"].message.lower()
    qdrant_ok = checks["qdrant"].healthy or "not configured" in checks["qdrant"].message.lower()

    ready = database_ok and redis_ok and qdrant_ok

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "ready": False,
            "message": "Service not ready",
            "checks": {name: check.to_dict() for name, check in checks.items()},
        }

    return {"ready": True, "message": "Service ready", "timestamp": utcnow().isoformat()}

@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Kubernetes liveness probe",
    description="Returns 200 if process is alive. Does NOT check dependencies.",
)
async def liveness_check():
    """Liveness probe for Kubernetes orchestration.

    Returns 200 if service process is alive.
    Does NOT check dependencies to prevent restart loops.

    Kubernetes Configuration:
        livenessProbe:
          httpGet:
            path: /live
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
          failureThreshold: 3

    Behavior:
    - Failing probe triggers container restart
    - ONLY fails if the process is dead/frozen
    - Does NOT check database/Redis to avoid cascading restarts

    Why separate from /ready:
    - Database down should NOT restart containers
    - Only restart if the application itself is broken
    """
    return {"alive": True, "timestamp": utcnow().isoformat()}

@router.get(
    "/health/detailed",
    response_model=DetailedHealthResponse,
    responses=response_with_errors(500),
    summary="Detailed health information",
    description="Returns version, platform, and comprehensive dependency status for debugging.",
)
async def detailed_health():
    """Detailed health information for debugging.

    Includes:
    - Service version and environment
    - Platform and Python version
    - Per-dependency health with latency measurements
    - Plugin health checks with source attribution

    Use for monitoring dashboards and debugging connectivity issues.
    """
    settings = get_settings()
    checks = await check_all_dependencies()

    # Get plugin health check metadata for categorization
    plugin_registry = get_plugin_health_registry()
    plugin_check_info = plugin_registry.get_check_info()

    # Core infrastructure categories
    core_categories = {
        "database": "critical",
        "redis": "important",
        "qdrant": "important",
        "neo4j": "optional",
    }

    components = {}
    for name, check in checks.items():
        # Determine category and plugin source
        if name in core_categories:
            category = core_categories[name]
            plugin_name = None
        elif name in plugin_check_info:
            category = plugin_check_info[name]["category"]
            plugin_name = plugin_check_info[name]["plugin"]
        else:
            category = "optional"
            plugin_name = None

        component_data = {
            "status": "healthy" if check.healthy else "unhealthy",
            "category": category,
            "latency_ms": check.latency_ms,
            "message": check.message,
        }
        if plugin_name:
            component_data["plugin"] = plugin_name
            component_data["description"] = plugin_check_info[name].get("description", "")

        components[name] = component_data

    overall_status = (
        "healthy" if all(c["status"] == "healthy" for c in components.values()) else "unhealthy"
    )

    return {
        "status": overall_status,
        "timestamp": utcnow().isoformat(),
        "components": components,
        "service": "dryade-api",
        "version": __version__,
        "uptime_seconds": 0,
        "environment": settings.env,
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "dependencies": {name: check.to_dict() for name, check in checks.items()},
    }

@router.get(
    "/health/metrics",
    response_model=HealthMetricsResponse,
    responses=response_with_errors(500),
    summary="Health check metrics",
    description="Returns health check counts and failure rates for alerting.",
)
async def health_metrics():
    """Health check metrics for monitoring and alerting.

    Returns:
    - Total checks performed per dependency
    - Total failures per dependency
    - Failure rate percentage

    Use for:
    - Alerting on elevated failure rates
    - SLA monitoring dashboards
    - Capacity planning
    """
    return {
        "checks_total": dict(health_check_counts),
        "failures_total": dict(health_check_failures),
        "failure_rates": {
            svc: (health_check_failures[svc] / health_check_counts[svc] * 100)
            if health_check_counts[svc] > 0
            else 0
            for svc in health_check_counts
        },
    }

@router.get(
    "/health/circuit-breakers",
    response_model=CircuitBreakersResponse,
    summary="List all circuit breakers",
    description="Returns state of all registered circuit breakers for monitoring and debugging.",
)
async def list_circuit_breakers():
    """List all circuit breakers and their current states.

    Returns information about:
    - Circuit state (closed, open, half_open)
    - Failure count and threshold
    - Timeout configuration
    - Last failure and state change timestamps

    Use for monitoring dashboards and debugging service availability issues.
    """
    breakers = get_all_circuit_breakers()
    states = [breaker.get_state() for breaker in breakers.values()]
    return {
        "circuit_breakers": states,
        "count": len(states),
    }

@router.post(
    "/health/circuit-breakers/{name}/reset",
    response_model=CircuitBreakerResetResponse,
    responses=response_with_errors(404),
    summary="Reset a circuit breaker",
    description="Manually reset a circuit breaker to closed state when underlying service recovers.",
)
async def reset_circuit_breaker(name: str, response: Response):
    """Reset a specific circuit breaker to closed state.

    Use when:
    - Underlying service has recovered
    - Circuit is stuck in open state
    - You want to immediately restore traffic flow

    Args:
        name: The circuit breaker identifier (e.g., "llm_api", "database")

    Returns:
        200: Circuit breaker reset successfully
        404: Circuit breaker not found
    """
    breakers = get_all_circuit_breakers()

    if name not in breakers:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"detail": f"Circuit breaker '{name}' not found. Available: {list(breakers.keys())}"}

    breaker = breakers[name]
    breaker.reset()

    logger.info(f"Circuit breaker '{name}' manually reset via API")

    return {
        "message": f"Circuit breaker '{name}' reset to closed state",
        "circuit_breaker": breaker.get_state(),
    }
