"""Auth Event Logging.

Helper functions for logging authentication events to the audit trail.
Each auth operation (login, logout, register, MFA) creates an audit entry
with appropriate severity for SOC 2 / GDPR compliance.

Target: ~60 LOC
"""

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from core.auth.audit import log_audit

logger = logging.getLogger(__name__)

# Severity mapping for auth events
_SEVERITY_MAP: dict[str, str] = {
    "login_fail": "warning",
    "mfa_validation_failed": "warning",
    "mfa_disabled": "warning",
    "mfa_recovery_used": "warning",
    "admin_setup": "critical",
    "role_changed": "critical",
}

def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Checks X-Forwarded-For header first (reverse proxy),
    falls back to request.client.host.

    Args:
        request: FastAPI Request object.

    Returns:
        Client IP address string, or None if unavailable.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For can contain multiple IPs; first is the client
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None

async def log_auth_event(
    db: Session,
    user_id: str,
    event: str,
    ip_address: str | None = None,
    metadata: dict | None = None,
    severity: str | None = None,
) -> None:
    """Log an authentication event to the audit trail.

    Designed for use with FastAPI BackgroundTasks:
        background_tasks.add_task(
            log_auth_event, db, user.id, "login_success", get_client_ip(request)
        )

    Args:
        db: Database session.
        user_id: ID of the user (or email for failed logins).
        event: Event type (login_success, login_fail, user_registered, etc.).
        ip_address: Client IP address.
        metadata: Additional context (e.g. failure reason).
        severity: Override severity. If None, uses _SEVERITY_MAP or "info".
    """
    resolved_severity = severity or _SEVERITY_MAP.get(event, "info")
    await log_audit(
        db,
        user_id=user_id,
        action=event,
        resource_type="auth",
        ip_address=ip_address,
        metadata=metadata,
        event_severity=resolved_severity,
    )
