"""Data Retention Engine.

Enforces GDPR Article 30 retention periods with configurable durations.
Runs as a daily background task, purging expired data with audit trail.

Locked defaults:
  - Audit logs: 7 years (immutable -- skipped from deletion)
  - Conversations: 1 year (uses updated_at, not created_at)
  - Cost records: 3 years
  - Security events: 5 years
  - Backups: 30 days

All periods configurable via DRYADE_RETENTION_* environment variables.
Accepted formats: "7y" (years), "365d" (days).
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.auth.audit import log_audit_sync
from core.auth.dependencies import get_db, require_admin
from core.database.models import Conversation, CostRecord, Message, SecurityEvent

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Retention configuration
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(r"^(\d+)(y|d)$")

def _parse_duration(value: str) -> timedelta:
    """Parse a duration string like '7y' or '30d' into a timedelta."""
    match = _DURATION_RE.match(value.strip().lower())
    if not match:
        raise ValueError(f"Invalid retention duration '{value}'. Expected format: '7y' or '365d'.")
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "y":
        return timedelta(days=amount * 365)
    return timedelta(days=amount)

@dataclass
class RetentionConfig:
    """Configurable retention periods for each data category."""

    audit_logs: timedelta = field(default_factory=lambda: timedelta(days=7 * 365))
    conversations: timedelta = field(default_factory=lambda: timedelta(days=1 * 365))
    cost_records: timedelta = field(default_factory=lambda: timedelta(days=3 * 365))
    security_events: timedelta = field(default_factory=lambda: timedelta(days=5 * 365))
    backups: timedelta = field(default_factory=lambda: timedelta(days=30))

    @classmethod
    def from_env(cls) -> RetentionConfig:
        """Build config from DRYADE_RETENTION_* environment variables.

        Falls back to locked defaults when an env var is absent.
        """
        defaults = cls()
        return cls(
            audit_logs=_parse_duration(os.environ.get("DRYADE_RETENTION_AUDIT_LOGS", "7y"))
            if os.environ.get("DRYADE_RETENTION_AUDIT_LOGS")
            else defaults.audit_logs,
            conversations=_parse_duration(os.environ.get("DRYADE_RETENTION_CONVERSATIONS", "1y"))
            if os.environ.get("DRYADE_RETENTION_CONVERSATIONS")
            else defaults.conversations,
            cost_records=_parse_duration(os.environ.get("DRYADE_RETENTION_COST_RECORDS", "3y"))
            if os.environ.get("DRYADE_RETENTION_COST_RECORDS")
            else defaults.cost_records,
            security_events=_parse_duration(
                os.environ.get("DRYADE_RETENTION_SECURITY_EVENTS", "5y")
            )
            if os.environ.get("DRYADE_RETENTION_SECURITY_EVENTS")
            else defaults.security_events,
            backups=_parse_duration(os.environ.get("DRYADE_RETENTION_BACKUPS", "30d"))
            if os.environ.get("DRYADE_RETENTION_BACKUPS")
            else defaults.backups,
        )

# ---------------------------------------------------------------------------
# Retention purge logic
# ---------------------------------------------------------------------------

def run_retention_purge(
    db: Session,
    config: RetentionConfig,
    dry_run: bool = False,
) -> dict:
    """Execute retention purge across all data categories.

    Args:
        db: Active database session.
        config: Retention periods per category.
        dry_run: If True, count rows without deleting.

    Returns:
        Summary dict with counts and cutoff dates per category.
    """
    now = datetime.now(UTC)
    result: dict = {"dry_run": dry_run}

    # --- Conversations (uses updated_at, NOT created_at) ---
    conv_cutoff = now - config.conversations
    conv_count = db.query(Conversation).filter(Conversation.updated_at < conv_cutoff).count()
    if not dry_run and conv_count > 0:
        _log_purge_audit(db, "conversations", conv_count, conv_cutoff)
        # Delete messages first (explicit, even though cascade exists)
        conv_ids = [
            c.id
            for c in db.query(Conversation.id).filter(Conversation.updated_at < conv_cutoff).all()
        ]
        if conv_ids:
            db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(
                synchronize_session=False
            )
            db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(
                synchronize_session=False
            )
        db.commit()
    result["conversations"] = {"count": conv_count, "cutoff": conv_cutoff.isoformat()}

    # --- Cost records ---
    cost_cutoff = now - config.cost_records
    cost_count = db.query(CostRecord).filter(CostRecord.timestamp < cost_cutoff).count()
    if not dry_run and cost_count > 0:
        _log_purge_audit(db, "cost_records", cost_count, cost_cutoff)
        db.query(CostRecord).filter(CostRecord.timestamp < cost_cutoff).delete(
            synchronize_session=False
        )
        db.commit()
    result["cost_records"] = {"count": cost_count, "cutoff": cost_cutoff.isoformat()}

    # --- Security events ---
    sec_cutoff = now - config.security_events
    sec_count = db.query(SecurityEvent).filter(SecurityEvent.timestamp < sec_cutoff).count()
    if not dry_run and sec_count > 0:
        _log_purge_audit(db, "security_events", sec_count, sec_cutoff)
        db.query(SecurityEvent).filter(SecurityEvent.timestamp < sec_cutoff).delete(
            synchronize_session=False
        )
        db.commit()
    result["security_events"] = {"count": sec_count, "cutoff": sec_cutoff.isoformat()}

    # --- Audit logs (IMMUTABLE -- skip deletion) ---
    audit_cutoff = now - config.audit_logs
    from core.database.models import AuditLog

    audit_count = db.query(AuditLog).filter(AuditLog.created_at < audit_cutoff).count()
    result["audit_logs"] = {
        "count": audit_count,
        "cutoff": audit_cutoff.isoformat(),
        "skipped": True,
        "reason": "immutable -- audit logs require manual archival after retention period (SOC 2 evidence preservation)",
    }
    if audit_count > 0:
        logger.warning(
            "Audit logs past retention period require manual archival",
            count=audit_count,
            cutoff=audit_cutoff.isoformat(),
        )

    return result

def get_retention_preview(db: Session, config: RetentionConfig) -> dict:
    """Return a dry-run preview of what the retention purge would delete."""
    return run_retention_purge(db, config, dry_run=True)

def _log_purge_audit(
    db: Session,
    category: str,
    count: int,
    cutoff: datetime,
) -> None:
    """Create a summary audit entry before purging a category."""
    log_audit_sync(
        db=db,
        user_id="system",
        action="retention_purge",
        resource_type=category,
        metadata={
            "category": category,
            "count": count,
            "cutoff": cutoff.isoformat(),
        },
        event_severity="warning",
    )

# ---------------------------------------------------------------------------
# Scheduler (background task)
# ---------------------------------------------------------------------------

async def start_retention_scheduler() -> None:
    """Run retention purge once daily as a background task.

    First run is deferred by 24 hours (86400 seconds).
    Catches all exceptions to avoid crashing the application.
    """
    from core.database.session import get_session_factory

    logger.info("Retention scheduler started (first run in 24h)")

    while True:
        await asyncio.sleep(86400)
        try:
            session_factory = get_session_factory()
            db = session_factory()
            try:
                config = RetentionConfig.from_env()
                summary = run_retention_purge(db, config, dry_run=False)
                logger.info("Retention purge completed", summary=summary)
            finally:
                db.close()
        except Exception:
            logger.exception("Retention purge failed (will retry in 24h)")

# ---------------------------------------------------------------------------
# Admin preview route
# ---------------------------------------------------------------------------

router = APIRouter()

@router.get(
    "/preview",
    dependencies=[Depends(require_admin)],
    summary="Preview retention purge impact",
    description="Returns the number of rows that would be purged per category without deleting anything.",
)
def retention_preview(db: Session = Depends(get_db)) -> dict:
    """Admin endpoint: dry-run preview of retention purge."""
    config = RetentionConfig.from_env()
    return get_retention_preview(db, config)
