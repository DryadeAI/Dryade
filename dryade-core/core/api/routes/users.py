"""User Profile API Routes.

Endpoints for user profile management.

Target: ~80 LOC
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db, require_admin
from core.database.models import User, UserInvite

router = APIRouter()

class UserResponse(BaseModel):
    """User profile response."""

    id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    is_verified: bool
    is_external: bool
    preferences: dict
    first_seen: datetime
    last_seen: datetime

    class Config:
        """Pydantic configuration for ORM mode."""

        from_attributes = True

class UserUpdate(BaseModel):
    """User profile update request."""

    display_name: str | None = None
    avatar_url: str | None = None
    preferences: dict | None = None

class UserInviteCreate(BaseModel):
    """User invite creation request."""

    email: EmailStr
    permission: Literal["view", "edit", "owner"] = "view"

class UserInviteResponse(BaseModel):
    """User invite response."""

    id: int
    invited_by: str
    email: EmailStr
    permission: Literal["view", "edit", "owner"]
    status: Literal["pending", "accepted", "revoked"]
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic configuration for ORM mode."""

        from_attributes = True

@router.get("/me", response_model=UserResponse)
async def get_profile(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get current user's profile.

    Returns the profile information for the authenticated user.
    """
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@router.patch("/me", response_model=UserResponse)
async def update_profile(
    update: UserUpdate, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Update current user's profile.

    Allows updating display_name, avatar_url, and preferences.
    """
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    for key, value in update.model_dump(exclude_unset=True).items():
        setattr(db_user, key, value)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.get("/search", response_model=list[UserResponse])
async def search_users(
    q: str,
    limit: int = 10,
    _: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search users by email or display name.

    Case-insensitive partial match on email or display_name.
    Limited to 10 results by default (max 50).

    Args:
        q: Search query string (min 2 characters)
        limit: Maximum results to return (1-50)

    Returns:
        List of matching users
    """
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")

    limit = min(max(limit, 1), 50)  # Clamp to 1-50

    search_pattern = f"%{q}%"
    users = (
        db.query(User)
        .filter((User.email.ilike(search_pattern)) | (User.display_name.ilike(search_pattern)))
        .limit(limit)
        .all()
    )

    return users

@router.get("", response_model=list[UserResponse])
async def list_users(_: dict = Depends(require_admin), db: Session = Depends(get_db)):
    """List all users (admin only).

    Returns all user accounts in the system.
    Requires admin role.
    """
    return db.query(User).all()

@router.post("/invites", response_model=UserInviteResponse)
async def create_user_invite(
    invite: UserInviteCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update an invite for an email address.

    Note: This stores an invite record only (no email delivery).
    """
    inviter_id = user.get("sub")
    if not inviter_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    inviter = db.query(User).filter(User.id == inviter_id).first()
    if not inviter:
        raise HTTPException(status_code=404, detail="User not found")

    if invite.email.lower() == inviter.email.lower():
        raise HTTPException(status_code=400, detail="Cannot invite yourself")

    existing = (
        db.query(UserInvite)
        .filter(UserInvite.invited_by == inviter_id, UserInvite.email == invite.email)
        .first()
    )
    if existing:
        existing.permission = invite.permission
        existing.status = "pending"
        db.commit()
        db.refresh(existing)
        return existing

    record = UserInvite(
        invited_by=inviter_id,
        email=invite.email,
        permission=invite.permission,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
