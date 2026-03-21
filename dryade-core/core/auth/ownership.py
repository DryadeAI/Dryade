"""Resource Ownership Dependencies for FastAPI route protection.

Provides reusable dependencies for checking resource ownership.
Supports admin bypass, owner access, public access, and shared access.

Target: ~180 LOC
"""

from typing import TypeVar

from fastapi import Depends, HTTPException, Path
from sqlalchemy import String, cast
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.auth.sharing import SharingService
from core.database.models import Base, ResourceShare

T = TypeVar("T", bound=Base)

def get_owned_resource[T: Base](model: type[T], id_param: str = "id"):
    """Factory for ownership-checking dependencies.

    Access granted if:
    1. User is admin
    2. User owns the resource (user_id matches)
    3. Resource is public (if is_public field exists)

    Args:
        model: SQLAlchemy model class with user_id field
        id_param: Name of the path parameter for resource ID

    Returns:
        FastAPI dependency that returns the resource if access granted

    Raises:
        HTTPException: 404 if not found, 403 if access denied
    """

    async def dependency(
        resource_id: int = Path(..., alias=id_param),
        user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> T:
        resource = db.query(model).filter(model.id == resource_id).first()
        if not resource:
            raise HTTPException(status_code=404, detail=f"{model.__name__} not found")

        user_id = user.get("sub")

        # Admin can access all
        if user.get("role") == "admin":
            return resource

        # Owner can access
        if hasattr(resource, "user_id") and resource.user_id == user_id:
            return resource

        # Public resources (read-only)
        if hasattr(resource, "is_public") and resource.is_public:
            return resource

        raise HTTPException(status_code=403, detail="Access denied")

    return dependency

def filter_by_owner[T: Base](model: type[T]):
    """Factory for list queries filtered by owner.

    Returns: own resources + public resources (if applicable)
    Admin sees all.

    Args:
        model: SQLAlchemy model class with user_id field

    Returns:
        FastAPI dependency that returns a filtered query
    """

    async def dependency(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        query = db.query(model)
        user_id = user.get("sub")

        # Admin sees all
        if user.get("role") == "admin":
            return query

        # Filter by ownership + public
        if hasattr(model, "is_public"):
            query = query.filter(
                (model.user_id == user_id) | (model.is_public == True)  # noqa: E712
            )
        else:
            query = query.filter(model.user_id == user_id)

        return query

    return dependency

def get_owned_or_shared_resource[T: Base](
    model: type[T], resource_type: str, id_param: str = "id", require_edit: bool = False
):
    """Factory for ownership-checking dependencies with sharing support.

    Access granted if:
    1. User is admin
    2. User owns the resource (user_id matches)
    3. Resource is public (view only, unless require_edit=False)
    4. Resource is shared with user (with appropriate permission)

    Args:
        model: SQLAlchemy model class with user_id field
        resource_type: Resource type for sharing lookup (e.g., 'workflow')
        id_param: Name of the path parameter for resource ID
        require_edit: If True, requires edit permission for shared resources

    Returns:
        FastAPI dependency that returns the resource if access granted

    Raises:
        HTTPException: 404 if not found, 403 if access denied
    """

    async def dependency(
        resource_id: int = Path(..., alias=id_param),
        user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> T:
        resource = db.query(model).filter(model.id == resource_id).first()
        if not resource:
            raise HTTPException(status_code=404, detail=f"{model.__name__} not found")

        user_id = user.get("sub")

        # Admin can access all
        if user.get("role") == "admin":
            return resource

        # Owner can access
        if hasattr(resource, "user_id") and resource.user_id == user_id:
            return resource

        # Public resources (view only)
        if not require_edit and hasattr(resource, "is_public") and resource.is_public:
            return resource

        # Shared access
        sharing = SharingService(db)
        permission = sharing.get_permission(resource_type, resource_id, user_id)
        if permission:
            if require_edit and permission != "edit":
                raise HTTPException(status_code=403, detail="Edit permission required")
            return resource

        raise HTTPException(status_code=403, detail="Access denied")

    return dependency

def filter_by_owner_or_shared[T: Base](model: type[T], resource_type: str):
    """Factory for list queries filtered by owner with sharing support.

    Returns: own resources + shared resources + public resources (if applicable)
    Admin sees all.

    Args:
        model: SQLAlchemy model class with user_id field
        resource_type: Resource type for sharing lookup (e.g., 'workflow')

    Returns:
        FastAPI dependency that returns a filtered query
    """

    async def dependency(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
        user_id = user.get("sub")

        # Admin sees all
        if user.get("role") == "admin":
            return db.query(model)

        # Get IDs of shared resources
        shared_ids = (
            db.query(ResourceShare.resource_id)
            .filter(ResourceShare.resource_type == resource_type, ResourceShare.user_id == user_id)
            .scalar_subquery()
        )

        # Build filter: owned OR shared OR public
        # Cast model.id to String for comparison with ResourceShare.resource_id (String)
        # to handle models with Integer PKs (e.g. Workflow)
        id_expr = cast(model.id, String)
        query = db.query(model)
        if hasattr(model, "is_public"):
            query = query.filter(
                (model.user_id == user_id) | (id_expr.in_(shared_ids)) | (model.is_public == True)  # noqa: E712
            )
        else:
            query = query.filter((model.user_id == user_id) | (id_expr.in_(shared_ids)))

        return query

    return dependency
