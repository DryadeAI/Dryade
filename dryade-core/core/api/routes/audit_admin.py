"""Audit Admin API Routes.

Admin-only endpoints for querying, exporting, and verifying the audit trail.
Supports SOC 2 Type II audit requirements and GDPR access logging.

Target: ~120 LOC
"""

import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.auth.audit import compute_entry_hash
from core.auth.dependencies import get_db, require_admin
from core.database.models import AuditLog

router = APIRouter()

def _build_audit_query(
    db: Session,
    user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Build a filtered audit log query."""
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if severity:
        query = query.filter(AuditLog.event_severity == severity)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(AuditLog.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(AuditLog.created_at <= dt_to)
        except ValueError:
            pass
    return query

def _serialize_entry(entry: AuditLog) -> dict:
    """Serialize an AuditLog entry to dict."""
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "ip_address": entry.ip_address,
        "metadata": entry.metadata_,
        "event_severity": entry.event_severity,
        "entry_hash": entry.entry_hash,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }

@router.get("/")
async def query_audit_logs(
    user_id: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    severity: str | None = Query(None),
    date_from: str | None = Query(None, description="ISO-8601 date"),
    date_to: str | None = Query(None, description="ISO-8601 date"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Query audit logs with filters and pagination.

    Returns paginated audit log entries filtered by user, action,
    resource type, severity, and date range.
    """
    query = _build_audit_query(db, user_id, action, resource_type, severity, date_from, date_to)
    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))
    items = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "items": [_serialize_entry(e) for e in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": total_pages,
    }

@router.get("/export")
async def export_audit_logs(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Export audit logs as downloadable JSON.

    Returns all matching audit entries (no pagination limit).
    Sets Content-Disposition header for file download.
    """
    query = _build_audit_query(db, date_from=date_from, date_to=date_to)
    entries = query.order_by(AuditLog.created_at.asc()).all()
    data = [_serialize_entry(e) for e in entries]
    export_date = datetime.utcnow().strftime("%Y-%m-%d")
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": f'attachment; filename="audit-export-{export_date}.json"',
        },
    )

@router.get("/verify-chain")
async def verify_audit_chain(
    limit: int = Query(1000, ge=1, le=100000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Verify the audit log hash chain integrity.

    Walks entries ordered by ID, recomputes entry_hash for each, and
    compares against the stored hash. Reports chain status.

    Status values:
    - "intact": All entries have valid hashes
    - "broken": One or more entries have hash mismatches
    - "partial": Some entries have null hashes (pre-migration)
    """
    entries = db.query(AuditLog).order_by(AuditLog.id.asc()).offset(offset).limit(limit).all()

    verified = 0
    broken = 0
    first_break_id = None
    null_hashes = 0
    prev_hash = None

    for entry in entries:
        if entry.entry_hash is None:
            null_hashes += 1
            prev_hash = None  # Reset chain at null entries
            continue

        timestamp_str = entry.created_at.isoformat() if entry.created_at else ""
        expected = compute_entry_hash(
            entry_id=entry.id,
            action=entry.action,
            timestamp=timestamp_str,
            user_id=entry.user_id or "",
            prev_hash=prev_hash,
        )

        if entry.entry_hash == expected:
            verified += 1
        else:
            broken += 1
            if first_break_id is None:
                first_break_id = entry.id

        prev_hash = entry.entry_hash

    # Determine status
    if broken > 0:
        status = "broken"
        message = f"Hash chain broken at entry {first_break_id}. {broken} mismatches found."
    elif null_hashes > 0:
        status = "partial"
        message = (
            f"Chain partially verified. {verified} entries intact, "
            f"{null_hashes} entries without hashes (pre-migration)."
        )
    else:
        status = "intact"
        message = f"Hash chain intact. {verified} entries verified."

    return {
        "verified": verified,
        "broken": broken,
        "first_break_id": first_break_id,
        "status": status,
        "message": message,
    }
