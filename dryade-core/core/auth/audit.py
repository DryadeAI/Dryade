"""Audit Logging Service.

Provides non-blocking audit logging for sensitive operations.
Logs are stored in the database for security auditing.

Hash chain utilities compute SHA-256 entry hashes for tamper detection
(SOC 2 Type II / EU AI Act compliance).

Target: ~100 LOC
"""

import hashlib
import logging

from sqlalchemy.orm import Session

from core.database.models import AuditLog

logger = logging.getLogger(__name__)

def compute_entry_hash(
    entry_id: int,
    action: str,
    timestamp: str,
    user_id: str,
    prev_hash: str | None,
) -> str:
    """Compute SHA-256 hash for an audit log entry.

    The hash covers the entry's identity fields and the previous entry's hash,
    creating a verifiable chain. If prev_hash is None (genesis entry or chain
    not yet computed), 'genesis' is used as the sentinel value.

    Args:
        entry_id: The audit log entry ID.
        action: The action type (login, create, etc.).
        timestamp: ISO-8601 timestamp string.
        user_id: The user who performed the action.
        prev_hash: SHA-256 hex of the previous entry, or None for genesis.

    Returns:
        64-character lowercase hex SHA-256 digest.
    """
    payload = f"{entry_id}:{action}:{timestamp}:{user_id}:{prev_hash or 'genesis'}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

async def log_audit(
    db: Session,
    user_id: str,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    ip_address: str = None,
    metadata: dict = None,
    event_severity: str = "info",
) -> None:
    """Create an audit log entry with hash chain computation.

    This function is designed to be used with FastAPI BackgroundTasks
    for non-blocking audit logging. Uses its own session to avoid
    poisoning the request session on failure.

    Args:
        db: Database session (ignored — kept for backward compat signature)
        user_id: ID of the user performing the action
        action: Action type (login, create, update, delete, share)
        resource_type: Type of resource affected (workflow, conversation, etc.)
        resource_id: ID of the resource affected
        ip_address: IP address of the request
        metadata: Additional metadata as dict
        event_severity: Severity level (info, warning, critical)

    Example:
        background_tasks.add_task(
            log_audit, db, user_id, "create", "workflow", str(workflow.id)
        )
    """
    from datetime import UTC, datetime

    from core.database.session import get_session

    try:
        with get_session() as session:
            # Pre-compute created_at and entry_hash BEFORE insert.
            # audit_logs has ON UPDATE DO INSTEAD NOTHING rules for immutability,
            # so we cannot update rows after insert.
            now = datetime.now(UTC)

            # Get next sequence value for hash computation
            from sqlalchemy import text

            next_id = session.execute(text("SELECT nextval('audit_logs_id_seq')")).scalar()

            timestamp_str = now.isoformat()
            entry_hash = compute_entry_hash(
                entry_id=next_id,
                action=action,
                timestamp=timestamp_str,
                user_id=user_id or "",
                prev_hash=None,  # prev_hash populated during chain verification
            )

            audit = AuditLog(
                id=next_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                ip_address=ip_address,
                metadata_=metadata or {},
                event_severity=event_severity,
                created_at=now,
                entry_hash=entry_hash,
            )
            session.add(audit)
            # commit handled by get_session context manager
    except Exception as e:
        logger.warning(f"Failed to create audit log: {e}")
        # Don't raise - audit logging should never break the main operation

def log_audit_sync(
    db: Session,
    user_id: str,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    ip_address: str = None,
    metadata: dict = None,
    event_severity: str = "info",
) -> None:
    """Synchronous version of log_audit.

    Uses its own session to avoid poisoning the caller's session on failure.
    """
    from datetime import UTC, datetime

    from core.database.session import get_session

    try:
        with get_session() as session:
            # Pre-compute created_at and entry_hash BEFORE insert.
            # audit_logs has ON UPDATE DO INSTEAD NOTHING rules for immutability.
            now = datetime.now(UTC)

            from sqlalchemy import text

            next_id = session.execute(text("SELECT nextval('audit_logs_id_seq')")).scalar()

            timestamp_str = now.isoformat()
            entry_hash = compute_entry_hash(
                entry_id=next_id,
                action=action,
                timestamp=timestamp_str,
                user_id=user_id or "",
                prev_hash=None,
            )

            audit = AuditLog(
                id=next_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                ip_address=ip_address,
                metadata_=metadata or {},
                event_severity=event_severity,
                created_at=now,
                entry_hash=entry_hash,
            )
            session.add(audit)
            # commit handled by get_session context manager
    except Exception as e:
        logger.warning(f"Failed to create audit log: {e}")
