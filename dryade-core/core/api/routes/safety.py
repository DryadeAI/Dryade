"""Safety Management Endpoints.

Provides monitoring for input validation and output sanitization.
The safety system implements three-layer protection:

1. Input Validation: Schema enforcement, injection detection
2. Content Filtering: Harmful content detection and rejection
3. Output Sanitization: PII masking, secret removal, safe encoding

Target: ~80 LOC
"""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func

from core.api.models.openapi import response_with_errors
from core.database.models import SanitizationEvent, ValidationFailure
from core.database.session import get_session
from core.logs import get_logger
from core.utils.time import utcnow

router = APIRouter(tags=["safety"])
logger = get_logger(__name__)

class ValidationViolation(BaseModel):
    """Record of a validation failure."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_type": "ChatRequest",
                "route": "/api/chat/completions",
                "errors": ["messages: field required", "max_tokens: must be positive"],
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    model_type: str = Field(..., description="Pydantic model that failed validation")
    route: str = Field(..., description="API route where validation failed")
    errors: list[str] = Field(..., description="List of validation error messages")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the violation")

class SanitizationStat(BaseModel):
    """Sanitization statistics for a specific context."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"context": "html", "total_events": 250, "avg_size_reduction": 0.05}
        }
    )

    context: str = Field(..., description="Sanitization context (html, sql, shell, json, plain)")
    total_events: int = Field(..., ge=0, description="Total sanitization events for this context")
    avg_size_reduction: float = Field(
        ..., ge=0.0, le=1.0, description="Average output size reduction ratio (0.0-1.0)"
    )

class ViolationsResponse(BaseModel):
    """Response containing recent safety violations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "validation_failures": [],
                "sanitization_events": [],
                "total_violations": 0,
                "time_period": "last_24h",
            }
        }
    )

    validation_failures: list[ValidationViolation] = Field(
        ..., description="Recent input validation failures"
    )
    sanitization_events: list[dict[str, Any]] = Field(
        ..., description="Recent output sanitization events"
    )
    total_violations: int = Field(..., ge=0, description="Total violations in the time period")
    time_period: str = Field(..., description="Time period for the violations (e.g., 'last_24h')")
    error: str | None = Field(None, description="Error message if query failed")

class SafetyStatsResponse(BaseModel):
    """Comprehensive safety statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "validation_failures": 15,
                "sanitization_events": 450,
                "most_common_violations": [{"error": "messages: field required", "count": 8}],
                "sanitization_by_context": [
                    {"context": "html", "total_events": 200, "avg_size_reduction": 0.05}
                ],
            }
        }
    )

    validation_failures: int = Field(..., ge=0, description="Total input validation failures")
    sanitization_events: int = Field(..., ge=0, description="Total output sanitization events")
    most_common_violations: list[dict[str, Any]] = Field(
        ..., description="Most frequent validation errors with counts"
    )
    sanitization_by_context: list[SanitizationStat] = Field(
        ..., description="Sanitization breakdown by context (html, sql, etc.)"
    )

class SanitizationStatsResponse(BaseModel):
    """Detailed output sanitization statistics."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_events": 450,
                "by_context": {"html": 200, "sql": 50, "shell": 30, "json": 100, "plain": 70},
                "avg_size_reduction_pct": 3.5,
                "timestamp": "2026-01-13T12:00:00Z",
            }
        }
    )

    total_events: int = Field(..., ge=0, description="Total sanitization events")
    by_context: dict[str, int] = Field(..., description="Event counts per sanitization context")
    avg_size_reduction_pct: float = Field(
        ..., ge=0.0, description="Average output size reduction as percentage"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    error: str | None = Field(None, description="Error message if query failed")

@router.get(
    "/violations",
    response_model=ViolationsResponse,
    responses=response_with_errors(500),
    summary="Get recent safety violations",
    description="Returns recent validation failures and sanitization events.",
)
async def get_violations(
    _limit: int = Query(
        default=100, ge=1, le=1000, description="Maximum number of violations to return"
    ),
):
    """Get recent validation failures and sanitization events.

    Three-Layer Protection Violations:
    1. Input Validation: Missing fields, type errors, injection attempts
    2. Content Filtering: Harmful content detected
    3. Output Sanitization: PII or secrets removed from responses

    Use for security monitoring and incident investigation.
    """
    try:
        # Query last 24 hours of violations
        cutoff = utcnow() - timedelta(hours=24)

        with get_session() as session:
            # Get validation failures
            validation_failures = (
                session.query(ValidationFailure)
                .filter(ValidationFailure.created_at >= cutoff)
                .order_by(ValidationFailure.created_at.desc())
                .limit(_limit)
                .all()
            )

            # Get sanitization events
            sanitization_events = (
                session.query(SanitizationEvent)
                .filter(SanitizationEvent.created_at >= cutoff)
                .order_by(SanitizationEvent.created_at.desc())
                .limit(_limit)
                .all()
            )

            # Convert to response format
            validation_data = [
                {
                    "model_type": vf.model_type,
                    "route": vf.route or "unknown",
                    "errors": vf.errors,
                    "timestamp": vf.created_at.isoformat(),
                }
                for vf in validation_failures
            ]

            sanitization_data = [
                {
                    "context": se.context,
                    "route": se.route or "unknown",
                    "original_length": se.original_length,
                    "sanitized_length": se.sanitized_length,
                    "modifications": se.modifications,
                    "timestamp": se.created_at.isoformat(),
                }
                for se in sanitization_events
            ]

            return {
                "validation_failures": validation_data,
                "sanitization_events": sanitization_data,
                "total_violations": len(validation_data) + len(sanitization_data),
                "time_period": "last_24h",
            }

    except Exception as e:
        logger.error(f"Failed to get violations: {e}")
        return {
            "validation_failures": [],
            "sanitization_events": [],
            "total_violations": 0,
            "time_period": "last_24h",
            "error": str(e),
        }

@router.get(
    "/stats",
    response_model=SafetyStatsResponse,
    responses=response_with_errors(500),
    summary="Get safety statistics",
    description="Returns comprehensive validation and sanitization metrics.",
)
async def get_safety_stats():
    """Get comprehensive safety statistics.

    Returns:
    - Total validation failures and sanitization events
    - Most common validation errors (for improving API clients)
    - Sanitization breakdown by context (html, sql, shell, json, plain)

    Use for security dashboards and trend analysis.
    """
    try:
        with get_session() as session:
            # Count validation failures
            validation_count = session.query(func.count(ValidationFailure.id)).scalar() or 0

            # Count sanitization events
            sanitization_count = session.query(func.count(SanitizationEvent.id)).scalar() or 0

            # Get most common validation errors
            # Group by first error in the errors JSON array
            most_common = []
            recent_failures = (
                session.query(ValidationFailure)
                .order_by(ValidationFailure.created_at.desc())
                .limit(1000)
                .all()
            )

            # Count error occurrences
            error_counts = {}
            for failure in recent_failures:
                if failure.errors:
                    first_error = (
                        failure.errors[0]
                        if isinstance(failure.errors, list)
                        else str(failure.errors)
                    )
                    error_counts[first_error] = error_counts.get(first_error, 0) + 1

            # Get top 5 most common
            most_common = [
                {"error": error, "count": count}
                for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[
                    :5
                ]
            ]

            # Get sanitization breakdown by context
            context_stats = (
                session.query(
                    SanitizationEvent.context,
                    func.count(SanitizationEvent.id).label("total_events"),
                    func.avg(
                        (SanitizationEvent.original_length - SanitizationEvent.sanitized_length)
                        / SanitizationEvent.original_length
                    ).label("avg_reduction"),
                )
                .group_by(SanitizationEvent.context)
                .all()
            )

            sanitization_by_context = [
                SanitizationStat(
                    context=stat.context,
                    total_events=stat.total_events,
                    avg_size_reduction=stat.avg_reduction or 0.0,
                )
                for stat in context_stats
            ]

            return SafetyStatsResponse(
                validation_failures=validation_count,
                sanitization_events=sanitization_count,
                most_common_violations=most_common,
                sanitization_by_context=sanitization_by_context,
            )

    except Exception as e:
        logger.error(f"Failed to get safety stats: {e}")
        return SafetyStatsResponse(
            validation_failures=0,
            sanitization_events=0,
            most_common_violations=[],
            sanitization_by_context=[],
        )

@router.get(
    "/sanitization_stats",
    response_model=SanitizationStatsResponse,
    responses=response_with_errors(500),
    summary="Get sanitization statistics",
    description="Returns detailed output sanitization metrics by context.",
)
async def get_sanitization_stats():
    """Get output sanitization statistics.

    Sanitization Contexts:
    - html: HTML entity encoding, XSS prevention
    - sql: SQL injection prevention
    - shell: Command injection prevention
    - json: Safe JSON encoding
    - plain: General text sanitization

    Use to monitor sanitization effectiveness and identify patterns.
    """
    try:
        with get_session() as session:
            # Get total count
            total_events = session.query(func.count(SanitizationEvent.id)).scalar() or 0

            # Get counts by context
            context_counts = (
                session.query(
                    SanitizationEvent.context,
                    func.count(SanitizationEvent.id).label("count"),
                )
                .group_by(SanitizationEvent.context)
                .all()
            )

            by_context = {"html": 0, "sql": 0, "shell": 0, "json": 0, "plain": 0}
            for ctx, count in context_counts:
                if ctx in by_context:
                    by_context[ctx] = count

            # Calculate average size reduction percentage
            avg_reduction = (
                session.query(
                    func.avg(
                        (SanitizationEvent.original_length - SanitizationEvent.sanitized_length)
                        * 100.0
                        / SanitizationEvent.original_length
                    )
                )
                .filter(SanitizationEvent.original_length > 0)
                .scalar()
            ) or 0.0

            return {
                "total_events": total_events,
                "by_context": by_context,
                "avg_size_reduction_pct": avg_reduction,
                "timestamp": utcnow().isoformat(),
            }

    except Exception as e:
        logger.error(f"Failed to get sanitization stats: {e}")
        return {
            "total_events": 0,
            "by_context": {"html": 0, "sql": 0, "shell": 0, "json": 0, "plain": 0},
            "avg_size_reduction_pct": 0.0,
            "timestamp": utcnow().isoformat(),
            "error": str(e),
        }
