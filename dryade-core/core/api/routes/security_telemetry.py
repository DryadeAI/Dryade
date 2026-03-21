"""Security Telemetry Routes for Core.

Receives and stores security events for the Dryade platform.
Also provides API for security dashboard.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.auth.dependencies import get_db, require_admin
from core.database.models import SecurityEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])

class SecurityEventInput(BaseModel):
    """Input for a security event."""

    event_type: str
    timestamp: str
    machine_fingerprint: str
    details: dict[str, Any] = Field(default_factory=dict)
    core_version: str = "unknown"
    pm_version: str = "unknown"

class SecurityEventBatch(BaseModel):
    """Batch of security events."""

    events: list[SecurityEventInput]
    batch_timestamp: str

class SecurityEventResponse(BaseModel):
    """Response after receiving events."""

    received: int
    stored: int

@router.post("/events", response_model=SecurityEventResponse)
async def receive_events(
    batch: SecurityEventBatch,
    db: Session = Depends(get_db),
) -> SecurityEventResponse:
    """Receive security events batch.

    Note: This endpoint should be protected in production
    (e.g., require API key or mTLS).
    """
    stored = 0

    for event_input in batch.events:
        try:
            # Parse timestamp
            timestamp = datetime.fromisoformat(event_input.timestamp.replace("Z", "+00:00"))

            event = SecurityEvent(
                event_type=event_input.event_type,
                timestamp=timestamp,
                received_at=datetime.now(UTC),
                machine_fingerprint=event_input.machine_fingerprint[:12],
                details=event_input.details,
                core_version=event_input.core_version,
                pm_version=event_input.pm_version,
            )
            db.add(event)
            stored += 1

            # Log high-severity events
            if event_input.event_type in ["debugger_detected", "integrity_violation"]:
                logger.warning(
                    f"Security event: {event_input.event_type} from {event_input.machine_fingerprint[:12]}"
                )

        except Exception as e:
            logger.warning(f"Failed to store event: {e}")

    db.commit()

    logger.info(f"Received {len(batch.events)} security events, stored {stored}")

    return SecurityEventResponse(received=len(batch.events), stored=stored)

@router.get("/events")
async def list_events(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),  # Admin only
    limit: int = Query(default=100, le=1000),
    event_type: str | None = None,
    machine: str | None = None,
) -> list[dict]:
    """List security events (admin only)."""
    query = db.query(SecurityEvent).order_by(SecurityEvent.timestamp.desc())

    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)

    if machine:
        query = query.filter(SecurityEvent.machine_fingerprint.startswith(machine))

    events = query.limit(limit).all()

    return [e.to_dict() for e in events]

@router.get("/events/stats")
async def get_stats(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    """Get security event statistics (admin only)."""
    total = db.query(func.count(SecurityEvent.id)).scalar() or 0

    by_type = dict(
        db.query(SecurityEvent.event_type, func.count(SecurityEvent.id))
        .group_by(SecurityEvent.event_type)
        .all()
    )

    unique_machines = (
        db.query(func.count(func.distinct(SecurityEvent.machine_fingerprint))).scalar() or 0
    )

    # Get last event
    last_event = db.query(SecurityEvent).order_by(SecurityEvent.timestamp.desc()).first()

    return {
        "total_events": total,
        "by_type": by_type,
        "unique_machines": unique_machines,
        "last_event": last_event.to_dict() if last_event else None,
    }
