"""Resource Sharing Service.

Provides services for sharing resources between users with permission levels.
Supports view and edit permissions.

Target: ~80 LOC
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.database.models import ResourceShare, User

# Resource types that can be shared
SHAREABLE_TYPES: set[str] = {"workflow"}

def register_shareable_type(type_name: str) -> None:
    """Register an additional shareable resource type.

    Called by plugins during startup() to extend sharing to new resource types.
    Core's SharingService validates against this set.

    Args:
        type_name: Resource type identifier (e.g., 'conversation', 'project')
    """
    SHAREABLE_TYPES.add(type_name)

class SharingService:
    """Service for managing resource sharing between users."""

    def __init__(self, db: Session):
        """Initialize sharing service.

        Args:
            db: Database session
        """
        self.db = db

    def share(
        self,
        resource_type: str,
        resource_id: int | str,
        owner_id: str,
        target_user_id: str,
        permission: str = "view",
    ) -> ResourceShare:
        """Share a resource with another user.

        Args:
            resource_type: Type of resource (workflow)
            resource_id: ID of the resource
            owner_id: ID of the user sharing the resource
            target_user_id: ID of the user to share with
            permission: Permission level (view, edit)

        Returns:
            ResourceShare record

        Raises:
            HTTPException: 400 if resource type not shareable, 404 if user not found
        """
        if resource_type not in SHAREABLE_TYPES:
            raise HTTPException(status_code=400, detail=f"Cannot share {resource_type}")

        if permission not in ("view", "edit"):
            raise HTTPException(status_code=400, detail="Permission must be 'view' or 'edit'")

        # Check target user exists
        if not self.db.query(User).filter(User.id == target_user_id).first():
            raise HTTPException(status_code=404, detail="User not found")

        # Normalize resource_id to str (ResourceShare.resource_id is VARCHAR)
        resource_id_str = str(resource_id)

        # Upsert share (update if exists, create if not)
        existing = (
            self.db.query(ResourceShare)
            .filter(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id_str,
                ResourceShare.user_id == target_user_id,
            )
            .first()
        )

        if existing:
            existing.permission = permission
            self.db.commit()
            self.db.refresh(existing)
            return existing

        share = ResourceShare(
            resource_type=resource_type,
            resource_id=resource_id_str,
            user_id=target_user_id,
            permission=permission,
            shared_by=owner_id,
        )
        self.db.add(share)
        self.db.commit()
        self.db.refresh(share)
        return share

    def unshare(self, resource_type: str, resource_id: int | str, user_id: str) -> bool:
        """Remove sharing for a resource with a user.

        Args:
            resource_type: Type of resource
            resource_id: ID of the resource
            user_id: ID of the user to unshare from

        Returns:
            True if share was deleted, False if not found
        """
        resource_id_str = str(resource_id)
        deleted = (
            self.db.query(ResourceShare)
            .filter(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id_str,
                ResourceShare.user_id == user_id,
            )
            .delete()
        )
        self.db.commit()
        return deleted > 0

    def get_permission(
        self, resource_type: str, resource_id: int | str, user_id: str
    ) -> str | None:
        """Get permission level for a user on a resource.

        Args:
            resource_type: Type of resource
            resource_id: ID of the resource
            user_id: ID of the user

        Returns:
            Permission level (view, edit) or None if not shared
        """
        resource_id_str = str(resource_id)
        share = (
            self.db.query(ResourceShare)
            .filter(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id_str,
                ResourceShare.user_id == user_id,
            )
            .first()
        )
        return share.permission if share else None

    def get_shared_users(self, resource_type: str, resource_id: int | str) -> list[dict]:
        """Get list of users a resource is shared with.

        Args:
            resource_type: Type of resource
            resource_id: ID of the resource

        Returns:
            List of dicts with user_id and permission
        """
        resource_id_str = str(resource_id)
        shares = (
            self.db.query(ResourceShare)
            .filter(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id_str,
            )
            .all()
        )
        return [
            {"user_id": s.user_id, "permission": s.permission, "shared_by": s.shared_by}
            for s in shares
        ]
