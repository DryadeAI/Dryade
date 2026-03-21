"""Self-Healing Management Endpoints.

Provides monitoring and management for self-healing and circuit breakers.
The self-healing system provides automatic error recovery with:

Error Classification:
- TRANSIENT: Temporary failures, automatically retried (network timeout, rate limit)
- RECOVERABLE: May succeed with backoff (service overload, resource contention)
- PERMANENT: Will not recover, fail immediately (auth error, invalid request)

Circuit Breaker States:
- CLOSED: Normal operation, requests pass through
- OPEN: Failures exceeded threshold, requests fail immediately
- HALF_OPEN: Testing recovery, allowing limited requests

Target: ~120 LOC
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field

from core.api.models.openapi import response_with_errors
from core.config import get_settings
import core.extensions as _extensions
from core.logs import get_logger
from core.utils.time import utcnow

router = APIRouter(tags=["healing"])
logger = get_logger(__name__)

class CircuitBreakerState(BaseModel):
    """State of a single circuit breaker.

    Circuit breakers prevent cascade failures by stopping requests
    to failing services until they recover.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "anthropic_api",
                "state": "closed",
                "failure_count": 2,
                "failure_threshold": 5,
                "timeout_seconds": 60,
                "last_failure_time": "2026-01-13T11:55:00Z",
                "last_state_change": "2026-01-13T10:00:00Z",
            }
        }
    )

    name: str = Field(..., description="Circuit breaker identifier (usually service name)")
    state: str = Field(
        ..., description="Current state: 'closed' (normal), 'open' (failing), 'half_open' (testing)"
    )
    failure_count: int = Field(..., ge=0, description="Current consecutive failure count")
    failure_threshold: int = Field(..., ge=1, description="Failures needed to open the circuit")
    timeout_seconds: int = Field(
        ..., ge=1, description="Seconds to wait in open state before testing"
    )
    last_failure_time: str | None = Field(None, description="ISO 8601 timestamp of last failure")
    last_state_change: str = Field(..., description="ISO 8601 timestamp of last state transition")

class HealingStatsResponse(BaseModel):
    """Comprehensive self-healing statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "max_retry_attempts": 3,
                "circuit_breakers": {},
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    enabled: bool = Field(..., description="Whether self-healing is globally enabled")
    max_retry_attempts: int = Field(
        ..., ge=0, description="Maximum retry attempts for transient failures"
    )
    circuit_breakers: dict[str, CircuitBreakerState] = Field(
        ..., description="All circuit breakers with their current states"
    )
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

class CircuitBreakerListResponse(BaseModel):
    """Response listing all circuit breakers."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_circuits": 3,
                "circuits": {},
                "summary": {"closed": 2, "open": 1, "half_open": 0},
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    total_circuits: int = Field(
        ..., ge=0, description="Total number of registered circuit breakers"
    )
    circuits: dict[str, dict[str, Any]] = Field(
        ..., description="Circuit breaker states keyed by name"
    )
    summary: dict[str, int] = Field(
        ..., description="Count of circuits in each state (closed, open, half_open)"
    )
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

class CircuitBreakerDetailResponse(BaseModel):
    """Detailed single circuit breaker response."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "anthropic_api",
                "state": "closed",
                "failure_count": 0,
                "failure_threshold": 5,
                "timeout_seconds": 60,
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    name: str = Field(..., description="Circuit breaker identifier")
    state: str = Field(..., description="Current state")
    failure_count: int = Field(..., ge=0, description="Current failure count")
    failure_threshold: int = Field(..., ge=1, description="Threshold to open circuit")
    timeout_seconds: int = Field(..., ge=1, description="Recovery timeout")
    last_failure_time: str | None = Field(None, description="Last failure timestamp")
    last_state_change: str | None = Field(None, description="Last state change timestamp")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

class HealingHealthResponse(BaseModel):
    """Self-healing system health status."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "healthy": True,
                "issues": None,
                "self_healing": {"enabled": True, "max_retry_attempts": 3},
                "circuit_breakers": {"total": 3, "closed": 3, "open": 0, "half_open": 0},
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    healthy: bool = Field(..., description="Overall health (true if no circuits open)")
    issues: list[str] | None = Field(None, description="List of issues if not healthy")
    self_healing: dict[str, Any] = Field(..., description="Self-healing configuration")
    circuit_breakers: dict[str, int] = Field(..., description="Circuit breaker summary by state")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

@router.get(
    "/stats",
    response_model=HealingStatsResponse,
    responses=response_with_errors(500),
    summary="Get self-healing statistics",
    description="Returns configuration and all circuit breaker states.",
)
async def get_healing_stats():
    """Get comprehensive self-healing statistics.

    Returns:
    - Self-healing enabled status
    - Maximum retry attempts configuration
    - All circuit breaker states

    Circuit Breaker States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests fail fast
    - HALF_OPEN: Testing if service recovered

    Use for monitoring system reliability and identifying failing services.
    """
    try:
        # Get circuit breakers
        breakers = _extensions.get_all_circuit_breakers()
        breaker_states = {}

        for name, breaker in breakers.items():
            state_dict = breaker.get_state()
            breaker_states[name] = CircuitBreakerState(**state_dict)

        # Get configuration
        settings = get_settings()
        enabled = settings.self_healing_enabled
        max_attempts = settings.retry_max_attempts

        return HealingStatsResponse(
            enabled=enabled,
            max_retry_attempts=max_attempts,
            circuit_breakers=breaker_states,
            timestamp=utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to get healing stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve healing statistics: {str(e)}",
        ) from e

@router.get(
    "/circuit-breakers",
    response_model=CircuitBreakerListResponse,
    responses=response_with_errors(500),
    summary="List circuit breakers",
    description="Returns all circuit breakers with state summary.",
)
async def list_circuit_breakers():
    """List all circuit breakers and their current states.

    Returns:
    - All registered circuit breakers
    - Current state per breaker
    - Summary counts (closed/open/half_open)

    Interpreting States:
    - All CLOSED: System healthy
    - Any OPEN: Service(s) experiencing failures
    - HALF_OPEN: Recovery in progress

    Use for quick health overview of external service dependencies.
    """
    try:
        breakers = _extensions.get_all_circuit_breakers()

        return {
            "total_circuits": len(breakers),
            "circuits": {name: breaker.get_state() for name, breaker in breakers.items()},
            "summary": {
                "closed": sum(1 for b in breakers.values() if b.state.value == "closed"),
                "open": sum(1 for b in breakers.values() if b.state.value == "open"),
                "half_open": sum(1 for b in breakers.values() if b.state.value == "half_open"),
            },
            "timestamp": utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to list circuit breakers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list circuit breakers: {str(e)}",
        ) from e

@router.get(
    "/circuit-breakers/{name}",
    response_model=CircuitBreakerDetailResponse,
    responses=response_with_errors(404, 500),
    summary="Get circuit breaker by name",
    description="Returns detailed state for a specific circuit breaker.",
)
async def get_circuit_breaker(
    name: str = Path(
        ..., description="Circuit breaker identifier (e.g., 'anthropic_api', 'database')"
    ),
):
    """Get specific circuit breaker state.

    Returns detailed state including:
    - Current state and failure count
    - Threshold and timeout configuration
    - Last failure and state change timestamps

    Use for debugging specific service issues.
    """
    try:
        breakers = _extensions.get_all_circuit_breakers()

        if name not in breakers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Circuit breaker '{name}' not found"
            )

        breaker = breakers[name]
        return {**breaker.get_state(), "timestamp": utcnow().isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get circuit breaker '{name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get circuit breaker state: {str(e)}",
        ) from e

class CircuitBreakerResetResponse(BaseModel):
    """Response after resetting a circuit breaker."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "anthropic_api",
                "previous_state": "open",
                "new_state": "closed",
                "failure_count": 0,
                "message": "Circuit breaker reset successfully",
                "timestamp": "2026-01-24T12:00:00Z",
            }
        }
    )

    name: str = Field(..., description="Circuit breaker identifier")
    previous_state: str = Field(..., description="State before reset")
    new_state: str = Field(..., description="State after reset (should be closed)")
    failure_count: int = Field(..., ge=0, description="Failure count (should be 0 after reset)")
    message: str = Field(..., description="Result message")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")

@router.post(
    "/circuit-breakers/{name}/reset",
    response_model=CircuitBreakerResetResponse,
    responses=response_with_errors(404, 500),
    summary="Reset circuit breaker",
    description="Manually reset a circuit breaker to closed state. Use with caution.",
)
async def reset_circuit_breaker(
    name: str = Path(..., description="Circuit breaker identifier to reset"),
):
    """Reset a circuit breaker to closed state.

    Forces circuit breaker back to CLOSED state with zero failure count.
    Use this when:
    - Underlying service issue has been resolved
    - Manual intervention is needed after timeout
    - Testing circuit breaker behavior

    WARNING: Resetting an open circuit while the service is still failing
    will allow requests to fail again until the breaker reopens.
    """
    try:
        breakers = _extensions.get_all_circuit_breakers()

        if name not in breakers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Circuit breaker '{name}' not found",
            )

        breaker = breakers[name]
        previous_state = breaker.state.value

        # Reset the circuit breaker
        breaker.reset()

        logger.info(f"Circuit breaker '{name}' reset: {previous_state} -> closed")

        return CircuitBreakerResetResponse(
            name=name,
            previous_state=previous_state,
            new_state="closed",
            failure_count=0,
            message="Circuit breaker reset successfully",
            timestamp=utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker '{name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset circuit breaker: {str(e)}",
        ) from e

@router.get(
    "/health",
    response_model=HealingHealthResponse,
    responses=response_with_errors(500),
    summary="Check self-healing health",
    description="Returns system health based on circuit breaker states.",
)
async def healing_health():
    """Check self-healing system health.

    Health is determined by circuit breaker states:
    - HEALTHY: All circuits closed
    - UNHEALTHY: Any circuits open

    Issues reported:
    - Self-healing disabled
    - Open circuits (with names)
    - Half-open circuits testing recovery

    Use for monitoring dashboards and alerting.
    """
    try:
        breakers = _extensions.get_all_circuit_breakers()
        enabled = get_settings().self_healing_enabled

        # Count circuit states
        open_circuits = [name for name, b in breakers.items() if b.state.value == "open"]
        half_open_circuits = [name for name, b in breakers.items() if b.state.value == "half_open"]

        # Determine health status
        healthy = len(open_circuits) == 0
        issues = []

        if not enabled:
            issues.append("Self-healing is disabled")

        if open_circuits:
            issues.append(f"{len(open_circuits)} circuit(s) open: {', '.join(open_circuits)}")

        if half_open_circuits:
            issues.append(
                f"{len(half_open_circuits)} circuit(s) testing recovery: {', '.join(half_open_circuits)}"
            )

        return {
            "healthy": healthy,
            "issues": issues if issues else None,
            "self_healing": {
                "enabled": enabled,
                "max_retry_attempts": get_settings().retry_max_attempts,
            },
            "circuit_breakers": {
                "total": len(breakers),
                "closed": sum(1 for b in breakers.values() if b.state.value == "closed"),
                "open": len(open_circuits),
                "half_open": len(half_open_circuits),
            },
            "timestamp": utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to check healing health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check healing health: {str(e)}",
        ) from e
