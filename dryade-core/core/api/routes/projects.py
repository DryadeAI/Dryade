"""Project management API endpoints.

Provides CRUD operations for projects - used to group related conversations.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.api.models.openapi import response_with_errors
from core.auth.dependencies import get_current_user, get_db
from core.database.models import Conversation, Project
from core.logs import get_logger

router = APIRouter(prefix="/projects", tags=["projects"])
logger = get_logger(__name__)

# Request/Response Models

class ProjectCreate(BaseModel):
    """Request body for creating a project."""

    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: str | None = Field(None, max_length=500, description="Optional description")
    icon: str | None = Field(None, max_length=32, description="Emoji or icon name")
    color: str | None = Field(
        None, pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color like #3B82F6"
    )

class ProjectUpdate(BaseModel):
    """Request body for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=100, description="Project name")
    description: str | None = Field(None, max_length=500, description="Optional description")
    icon: str | None = Field(None, max_length=32, description="Emoji or icon name")
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color")
    is_archived: bool | None = Field(None, description="Archive status")

class ProjectResponse(BaseModel):
    """Project response model."""

    id: str
    name: str
    description: str | None
    icon: str | None
    color: str | None
    is_archived: bool
    conversation_count: int
    created_at: str
    updated_at: str

class ProjectListResponse(BaseModel):
    """Response for listing projects."""

    projects: list[ProjectResponse]
    total: int

class MoveToProjectRequest(BaseModel):
    """Request to move conversation to a project."""

    project_id: str | None = Field(..., description="Project ID or null to remove from project")

class DeleteProjectConversationsResponse(BaseModel):
    """Response from deleting project conversations."""

    deleted_count: int
    message: str

# Endpoints

@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List user's projects",
    description="Returns all projects for the authenticated user.",
)
async def list_projects(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all projects for the current user.

    Args:
        include_archived: If True, include archived projects

    Returns:
        List of projects with conversation counts
    """
    user_id = user.get("sub")
    query = db.query(Project).filter(Project.user_id == user_id)

    if not include_archived:
        query = query.filter(Project.is_archived == False)  # noqa: E712

    projects = query.order_by(Project.updated_at.desc()).all()

    result = []
    for p in projects:
        conv_count = db.query(Conversation).filter(Conversation.project_id == p.id).count()
        result.append(
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "icon": p.icon,
                "color": p.color,
                "is_archived": p.is_archived,
                "conversation_count": conv_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
        )

    return {"projects": result, "total": len(result)}

@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    description="Create a new project for grouping conversations.",
)
async def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new project.

    Args:
        body: Project details

    Returns:
        Created project
    """
    user_id = user.get("sub")
    project = Project(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=body.name,
        description=body.description,
        icon=body.icon,
        color=body.color,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    logger.info(f"Created project '{body.name}' for user {user_id}")

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "icon": project.icon,
        "color": project.color,
        "is_archived": project.is_archived,
        "conversation_count": 0,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }

@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses=response_with_errors(404),
    summary="Get project details",
    description="Get details of a specific project.",
)
async def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a specific project by ID.

    Args:
        project_id: Project UUID

    Returns:
        Project details with conversation count

    Raises:
        404: Project not found or not owned by user
    """
    user_id = user.get("sub")
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conv_count = db.query(Conversation).filter(Conversation.project_id == project.id).count()

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "icon": project.icon,
        "color": project.color,
        "is_archived": project.is_archived,
        "conversation_count": conv_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }

@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    responses=response_with_errors(404),
    summary="Update a project",
    description="Update project details.",
)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a project.

    Args:
        project_id: Project UUID
        body: Fields to update (only provided fields are updated)

    Returns:
        Updated project

    Raises:
        404: Project not found or not owned by user
    """
    user_id = user.get("sub")
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update only provided fields
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    conv_count = db.query(Conversation).filter(Conversation.project_id == project.id).count()

    logger.info(f"Updated project {project_id}")

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "icon": project.icon,
        "color": project.color,
        "is_archived": project.is_archived,
        "conversation_count": conv_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }

@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=response_with_errors(404),
    summary="Delete a project",
    description="Delete a project. Conversations are NOT deleted, just unlinked.",
)
async def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Delete a project.

    Note: Conversations in the project are NOT deleted - they are unlinked
    (project_id set to NULL due to ON DELETE SET NULL).

    Args:
        project_id: Project UUID

    Raises:
        404: Project not found or not owned by user
    """
    user_id = user.get("sub")
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()

    logger.info(f"Deleted project {project_id}")

@router.get(
    "/{project_id}/conversations",
    summary="List conversations in a project",
    description="Get all conversations belonging to a project.",
)
async def list_project_conversations(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all conversations in a project.

    Args:
        project_id: Project UUID

    Returns:
        List of conversations in the project

    Raises:
        404: Project not found or not owned by user
    """
    user_id = user.get("sub")
    # Verify project exists and belongs to user
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    conversations = (
        db.query(Conversation)
        .filter(Conversation.project_id == project_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "mode": c.mode,
                "status": c.status,
                "message_count": len(c.messages) if c.messages else 0,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ],
        "total": len(conversations),
    }

@router.delete(
    "/{project_id}/conversations",
    response_model=DeleteProjectConversationsResponse,
    responses=response_with_errors(404, 500),
    summary="Delete all conversations in a project",
    description="Permanently delete all conversations belonging to a project.",
)
async def delete_project_conversations(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> DeleteProjectConversationsResponse:
    """Delete all conversations in a project.

    This is a destructive operation that permanently removes all
    conversations in the project and their messages.
    The project itself is NOT deleted.

    Args:
        project_id: Project UUID

    Returns:
        Count of deleted conversations

    Raises:
        404: Project not found or not owned by user
    """
    user_id = user.get("sub")

    # Verify project exists and belongs to user
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Count conversations before delete
        count = db.query(Conversation).filter(Conversation.project_id == project_id).count()

        # Delete all conversations in project (cascade deletes messages)
        db.query(Conversation).filter(Conversation.project_id == project_id).delete(
            synchronize_session=False
        )
        db.commit()

        logger.info(f"Deleted {count} conversations from project {project_id} for user {user_id}")

        return DeleteProjectConversationsResponse(
            deleted_count=count,
            message=f"Deleted {count} conversation(s) from project",
        )
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting conversations from project {project_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete conversations. Please try again.",
        ) from e
