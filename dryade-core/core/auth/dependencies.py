"""Auth Dependencies for FastAPI route protection.

Provides reusable dependencies for authentication and authorization.
Works with existing AuthMiddleware that sets request.state.user.

Target: ~50 LOC
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.database.models import User
from core.database.rls import set_rls_context
from core.database.session import get_session


def get_db():
    """Database session dependency."""
    with get_session() as db:
        yield db

async def get_current_user(request: Request) -> dict:
    """Get current user from request state.

    Works with both local auth (AuthMiddleware) and
    external auth (Zitadel plugin when installed).

    Returns:
        User dict with sub, role, email from JWT payload

    Raises:
        HTTPException: 401 if not authenticated
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Set RLS context so database sessions enforce row-level isolation
    is_admin = user.get("role") == "admin"
    set_rls_context(user_id=user.get("sub"), is_admin=is_admin)

    return user

def require_role(allowed_roles: list[str]):
    """Dependency factory for role checking.

    Args:
        allowed_roles: List of roles that can access the endpoint

    Returns:
        Dependency that checks user role
    """

    async def role_checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return role_checker

# Convenience dependencies
require_admin = require_role(["admin"])
require_member = require_role(["admin", "member"])

async def get_current_user_db(
    user: dict = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Get current user as database model.

    Args:
        user: JWT payload from get_current_user
        db: Database session

    Returns:
        User model instance

    Raises:
        HTTPException: 404 if user not found in database
    """
    db_user = db.query(User).filter(User.id == user["sub"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found in database")
    return db_user
