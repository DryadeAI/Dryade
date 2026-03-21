"""Cookie Consent API (ePrivacy Directive compliance).

GET/PUT endpoints for per-user consent preferences with audit logging.
Essential cookies are always enabled (not user-configurable).

Target: ~80 LOC
"""

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import Session

from core.auth.audit import log_audit
from core.auth.dependencies import get_current_user, get_db
from core.database.models import Base

router = APIRouter()

# ---------------------------------------------------------------------------
# SQLAlchemy model (table created by Alembic migration f3)
# ---------------------------------------------------------------------------
class ConsentPreference(Base):
    """Per-user cookie consent preferences."""

    __tablename__ = "consent_preferences"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), unique=True, nullable=False)
    essential = Column(Boolean, server_default="1")
    analytics = Column(Boolean, server_default="0")
    preferences = Column(Boolean, server_default="0")
    consent_timestamp = Column(DateTime, nullable=False)
    ip_address = Column(String(45), nullable=True)
    updated_at = Column(DateTime, server_default=func.now())

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ConsentPreferencesInput(BaseModel):
    """User-settable consent fields."""

    analytics: bool = False
    preferences: bool = False

class ConsentResponse(BaseModel):
    """Consent state returned to callers."""

    user_id: str
    essential: bool
    analytics: bool
    preferences: bool
    consent_timestamp: str | None
    updated_at: str | None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_response(row: ConsentPreference) -> ConsentResponse:
    return ConsentResponse(
        user_id=row.user_id,
        essential=True,
        analytics=bool(row.analytics),
        preferences=bool(row.preferences),
        consent_timestamp=row.consent_timestamp.isoformat() if row.consent_timestamp else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )

def _check_access(user_id: str, current_user: dict) -> None:
    """Ensure the caller owns the record or is admin."""
    if current_user.get("sub") != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Cannot access another user's consent")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/{user_id}", response_model=ConsentResponse)
async def get_consent(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return consent preferences for *user_id*.

    Users may read their own preferences; admins may read any.
    If no record exists, returns safe defaults (essential only).
    """
    _check_access(user_id, current_user)
    row = db.query(ConsentPreference).filter(ConsentPreference.user_id == user_id).first()
    if not row:
        return ConsentResponse(
            user_id=user_id,
            essential=True,
            analytics=False,
            preferences=False,
            consent_timestamp=None,
            updated_at=None,
        )
    return _to_response(row)

@router.put("/{user_id}", response_model=ConsentResponse)
async def update_consent(
    user_id: str,
    body: ConsentPreferencesInput,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update consent preferences for *user_id*.

    Users may update their own preferences; admins may update any.
    Essential cookies are always True and cannot be changed.
    Changes are audit-logged asynchronously.
    """
    _check_access(user_id, current_user)

    now = datetime.now(UTC)
    ip = request.client.host if request.client else None

    row = db.query(ConsentPreference).filter(ConsentPreference.user_id == user_id).first()
    if row:
        row.analytics = body.analytics
        row.preferences = body.preferences
        row.consent_timestamp = now
        row.ip_address = ip
        row.updated_at = now
    else:
        row = ConsentPreference(
            user_id=user_id,
            essential=True,
            analytics=body.analytics,
            preferences=body.preferences,
            consent_timestamp=now,
            ip_address=ip,
            updated_at=now,
        )
        db.add(row)

    db.commit()
    db.refresh(row)

    # Audit trail
    background_tasks.add_task(
        log_audit,
        db,
        current_user.get("sub", user_id),
        "consent_updated",
        "consent",
        user_id,
        ip,
        {"analytics": body.analytics, "preferences": body.preferences},
    )

    return _to_response(row)
