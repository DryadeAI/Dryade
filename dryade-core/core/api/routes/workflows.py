"""Workflow Management Routes - CRUD operations and execution for ReactFlow workflows.

Provides REST API for workflow persistence, modification, publishing, cloning, and execution.
Target: ~600 LOC
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.api.models.openapi import response_with_errors
from core.auth.audit import log_audit
from core.auth.dependencies import get_current_user, get_db
from core.auth.ownership import (
    filter_by_owner_or_shared,
    get_owned_or_shared_resource,
    get_owned_resource,
)
from core.auth.sharing import SharingService
from core.database.models import Workflow, WorkflowExecutionResult
from core.workflows.executor import WorkflowExecutor
from core.workflows.schema import WorkflowSchema
from core.workflows.translator import WorkflowTranslator

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)

# ============================================================================
# Request Models
# ============================================================================

class CreateWorkflowRequest(BaseModel):
    """Request to create a new workflow.

    Creates a workflow in draft status. Workflow versioning uses unique constraint
    on (name, version, user_id) per prior decision 05-02.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Data Analysis Workflow",
                "description": "Analyze and summarize data from multiple sources",
                "workflow_json": {
                    "version": "1.0.0",
                    "nodes": [{"id": "task_1", "type": "task", "data": {"label": "Fetch Data"}}],
                    "edges": [],
                },
                "tags": ["data", "analysis"],
                "is_public": False,
            }
        }
    )

    name: str = Field(
        ...,
        description="Workflow name. Must be unique per user and version",
        min_length=1,
        max_length=200,
    )
    description: str | None = Field(
        None, description="Human-readable workflow description", max_length=2000
    )
    workflow_json: dict[str, Any] = Field(
        ...,
        description="Complete workflow definition with nodes, edges, and metadata. Validated against WorkflowSchema",
    )
    tags: list[str] | None = Field(
        default_factory=list, description="Tags for categorization and filtering (max 20 tags)"
    )
    is_public: bool = Field(
        False,
        description="Whether workflow is publicly visible. Private workflows only accessible by owner",
    )
    user_id: str | None = Field(
        None, description="Creator user ID. Null for system-level workflows"
    )

class UpdateWorkflowRequest(BaseModel):
    """Request to update an existing workflow.

    Only draft workflows can be modified. Published and archived workflows are immutable.
    """

    name: str | None = Field(
        None, description="Updated workflow name (1-200 characters)", min_length=1, max_length=200
    )
    description: str | None = Field(
        None, description="Updated human-readable description", max_length=2000
    )
    workflow_json: dict[str, Any] | None = Field(
        None,
        description="Updated workflow definition. Validated against WorkflowSchema if provided",
    )
    tags: list[str] | None = Field(
        None, description="Updated tags for categorization (replaces existing tags)"
    )

class CloneWorkflowRequest(BaseModel):
    """Request to clone a workflow.

    Creates a new draft workflow from an existing workflow with incremented version.
    Cloned workflows start as private and in draft status.
    """

    name: str | None = Field(
        None,
        description="Name for cloned workflow. Defaults to '{original_name} (copy)' if not provided",
        max_length=200,
    )
    # Note: user_id removed from request - owner is always the authenticated user (GAP-111)

class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow.

    Only published workflows can be executed. Returns SSE stream with execution progress.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "inputs": {"query": "Analyze sales data for Q4"},
                "user_id": "user_123",
                "conversation_id": "conv_abc",
            }
        }
    )

    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial state inputs as key-value pairs. Keys must match workflow state fields",
    )
    user_id: str | None = Field(
        None, description="User ID of the executor for tracking and cost attribution"
    )
    conversation_id: str | None = Field(
        None,
        description="Conversation ID to associate execution results with. Enables context continuity",
    )
    template_id: int | None = Field(
        None,
        description="Organization template ID if workflow was created from a template. Used for analytics.",
    )
    template_version_id: int | None = Field(
        None,
        description="Template version ID if workflow was created from a template. Used for analytics.",
    )

class ShareWorkflowRequest(BaseModel):
    """Request to share a workflow with another user."""

    user_id: str = Field(..., description="User ID to share with")
    permission: str = Field("view", description="Permission level: 'view' or 'edit'")

# ============================================================================
# Response Models
# ============================================================================

class WorkflowResponse(BaseModel):
    """Full workflow details response.

    Status lifecycle (per prior decision 05-02):
    - draft: Initial state, can be modified and deleted
    - published: Immutable, can be executed and cloned
    - archived: Immutable, hidden from default listings

    Transitions: draft -> published -> archived (one-way)
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Data Analysis Workflow",
                "description": "Analyze and summarize data",
                "version": "1.0.0",
                "workflow_json": {
                    "version": "1.0.0",
                    "nodes": [{"id": "task_1", "type": "task"}],
                    "edges": [],
                },
                "status": "published",
                "is_public": True,
                "user_id": "user_123",
                "tags": ["data", "analysis"],
                "execution_count": 42,
                "created_at": "2026-01-10T12:00:00Z",
                "updated_at": "2026-01-12T14:30:00Z",
                "published_at": "2026-01-11T10:00:00Z",
            }
        },
    )

    id: int = Field(..., description="Unique workflow identifier (auto-generated)")
    name: str = Field(..., description="Workflow name (1-200 characters)")
    description: str | None = Field(None, description="Human-readable workflow description")
    version: str = Field(
        ..., description="Semantic version (e.g., 1.0.0). Auto-incremented on clone"
    )
    workflow_json: dict[str, Any] = Field(
        ..., description="Complete workflow definition with nodes, edges, and metadata"
    )
    status: str = Field(..., description="Workflow status: draft, published, or archived")
    is_public: bool = Field(..., description="Whether workflow is publicly visible")
    user_id: str | None = Field(None, description="Creator user ID. Null for system workflows")
    tags: list[str] = Field(
        default_factory=list, description="Tags for categorization and filtering"
    )
    execution_count: int = Field(
        0, description="Total number of times this workflow has been executed"
    )
    created_at: str | None = Field(None, description="ISO 8601 timestamp when workflow was created")
    updated_at: str | None = Field(None, description="ISO 8601 timestamp of last modification")
    published_at: str | None = Field(
        None, description="ISO 8601 timestamp when workflow was published. Null for drafts"
    )

class WorkflowSummary(BaseModel):
    """Lightweight workflow summary (excludes workflow_json for performance).

    Used in list endpoints to reduce payload size. For full workflow details
    including workflow_json, use GET /workflows/{id}.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Unique workflow identifier")
    name: str = Field(..., description="Workflow name (1-200 characters)")
    description: str | None = Field(None, description="Human-readable workflow description")
    version: str = Field(..., description="Semantic version (e.g., 1.0.0)")
    status: str = Field(..., description="Workflow status: draft, published, or archived")
    is_public: bool = Field(..., description="Whether workflow is publicly visible")
    user_id: str | None = Field(None, description="Creator user ID")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    execution_count: int = Field(0, description="Total execution count")
    created_at: str | None = Field(None, description="ISO 8601 creation timestamp")
    updated_at: str | None = Field(None, description="ISO 8601 last modification timestamp")

class WorkflowSummaryList(BaseModel):
    """Paginated list of workflow summaries.

    Pagination follows prior decision 03-03: max 100 items, offset-based.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "workflows": [
                    {"id": 1, "name": "Data Analysis", "version": "1.0.0", "status": "published"}
                ],
                "total": 42,
                "offset": 0,
                "limit": 50,
                "has_more": False,
            }
        }
    )

    workflows: list[WorkflowSummary] = Field(
        ..., description="List of workflow summaries for current page"
    )
    total: int = Field(
        ..., ge=0, description="Total count of workflows matching filters (all pages)"
    )
    offset: int = Field(..., ge=0, description="Number of items skipped (0-based pagination)")
    limit: int = Field(..., ge=1, le=100, description="Maximum items per page (1-100)")
    has_more: bool = Field(False, description="True if more items exist beyond current page")
    items: list[WorkflowSummary] | None = Field(
        default=None, description="Alias for workflows (frontend contract)"
    )

class ExecutionResultResponse(BaseModel):
    """Workflow execution result response.

    Execution status lifecycle:
    - running: Execution in progress
    - success: Completed successfully with final_result
    - failed: Terminated with error message
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 42,
                "workflow_id": 1,
                "user_id": "user_123",
                "conversation_id": "conv_abc",
                "status": "success",
                "started_at": "2026-01-14T10:00:00Z",
                "completed_at": "2026-01-14T10:00:05Z",
                "duration_ms": 5000,
                "node_results": [{"node_id": "task_1", "output": "Data fetched successfully"}],
                "final_result": {"summary": "Analysis complete"},
                "error": None,
                "cost": 0.0025,
                "created_at": "2026-01-14T10:00:00Z",
            }
        },
    )

    id: int = Field(..., description="Unique execution result identifier")
    workflow_id: int = Field(..., description="ID of the executed workflow")
    user_id: str | None = Field(None, description="User ID of the executor")
    conversation_id: str | None = Field(
        None, description="Associated conversation ID for context continuity"
    )
    status: str = Field(..., description="Execution status: running, success, or failed")
    started_at: str | None = Field(None, description="ISO 8601 timestamp when execution started")
    completed_at: str | None = Field(
        None, description="ISO 8601 timestamp when execution completed. Null while running"
    )
    duration_ms: int | None = Field(
        None, ge=0, description="Execution duration in milliseconds. Null while running"
    )
    node_results: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-node execution outputs in order of completion"
    )
    final_result: dict[str, Any] | None = Field(
        None, description="Final workflow output. Null on failure or while running"
    )
    error: str | None = Field(
        None, description="Error message if execution failed. Null on success"
    )
    cost: float | None = Field(
        None, ge=0, description="Total execution cost in USD (LLM tokens, API calls)"
    )
    created_at: str | None = Field(None, description="ISO 8601 timestamp when record was created")

class ExecutionResultList(BaseModel):
    """Paginated list of execution results.

    Ordered by started_at DESC (most recent first).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "executions": [
                    {"id": 42, "workflow_id": 1, "status": "success", "duration_ms": 5000}
                ],
                "total": 100,
                "offset": 0,
                "limit": 50,
                "has_more": True,
            }
        }
    )

    executions: list[ExecutionResultResponse] = Field(
        ..., description="List of execution results for current page"
    )
    total: int = Field(
        ..., ge=0, description="Total count of executions matching filters (all pages)"
    )
    offset: int = Field(..., ge=0, description="Number of items skipped (0-based pagination)")
    limit: int = Field(..., ge=1, le=100, description="Maximum items per page (1-100)")
    has_more: bool = Field(False, description="True if more items exist beyond current page")

class WorkflowValidationResult(BaseModel):
    """Result of workflow validation."""

    valid: bool = Field(..., description="Whether the workflow passed all validation checks")
    errors: list[str] = Field(default_factory=list, description="List of validation errors")
    warnings: list[str] = Field(default_factory=list, description="List of validation warnings")

# ============================================================================
# Helper Functions
# ============================================================================

def workflow_to_response(workflow: Workflow) -> dict:
    """Convert Workflow model to response dict."""
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "version": workflow.version,
        "workflow_json": workflow.workflow_json,
        "status": workflow.status,
        "is_public": workflow.is_public,
        "user_id": workflow.user_id,
        "tags": workflow.tags or [],
        "execution_count": workflow.execution_count or 0,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "published_at": workflow.published_at.isoformat() if workflow.published_at else None,
    }

def workflow_to_summary(workflow: Workflow) -> dict:
    """Convert Workflow model to summary dict (no workflow_json)."""
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "version": workflow.version,
        "status": workflow.status,
        "is_public": workflow.is_public,
        "user_id": workflow.user_id,
        "tags": workflow.tags or [],
        "execution_count": workflow.execution_count or 0,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
    }

def increment_version(version: str) -> str:
    """Increment minor version: 1.0.0 -> 1.1.0."""
    try:
        parts = version.split(".")
        if len(parts) >= 2:
            parts[1] = str(int(parts[1]) + 1)
            return ".".join(parts)
    except (ValueError, IndexError):
        pass
    return "1.1.0"

# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Create a new workflow",
    description="Create a new workflow from ReactFlow JSON. The workflow starts in draft status and can be modified until published.",
    responses=response_with_errors(400, 401, 409, 500),
)
async def create_workflow(
    request: CreateWorkflowRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new workflow in draft status.

    Creates a workflow from ReactFlow JSON. The workflow starts in draft status
    and can be modified. Workflow JSON is validated against WorkflowSchema.
    User ID is set from the authenticated user token.

    **Parameters:**
    - **name**: Workflow name (max 200 chars)
    - **description**: Optional description
    - **workflow_json**: Complete workflow definition (nodes + edges)
    - **tags**: Optional tags for categorization
    - **is_public**: Whether workflow is public (default: false)

    **Returns:**
    - **201**: Workflow created successfully
    - **400**: Invalid workflow schema
    - **401**: Not authenticated

    **Example Request:**
    ```json
    {
        "name": "Data Analysis Workflow",
        "description": "Analyze and summarize data",
        "workflow_json": {
            "version": "1.0.0",
            "nodes": [...],
            "edges": [...]
        },
        "tags": ["data", "analysis"],
        "is_public": false
    }
    ```
    """
    user_id = user.get("sub")

    try:
        # Validate workflow_json against WorkflowSchema
        try:
            WorkflowSchema.model_validate(request.workflow_json)
        except ValueError as e:
            logger.warning(f"Workflow validation failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid workflow schema. Check node connections and required fields.",
            ) from e

        # Create workflow with draft status - user_id from token
        workflow = Workflow(
            name=request.name,
            description=request.description,
            version="1.0.0",
            workflow_json=request.workflow_json,
            status="draft",
            is_public=request.is_public,
            user_id=user_id,
            tags=request.tags or [],
            execution_count=0,
        )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        # Audit log
        background_tasks.add_task(log_audit, db, user_id, "create", "workflow", str(workflow.id))

        logger.info(f"Created workflow {workflow.id} '{workflow.name}' for user {user_id}")

        return workflow_to_response(workflow)

    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating workflow: {e}")
        raise HTTPException(
            status_code=400, detail="Workflow with this name and version already exists"
        ) from e
    except Exception as e:
        db.rollback()
        logger.exception(f"Error creating workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow creation failed. This may be a temporary issue - please try again.",
        ) from e

@router.get(
    "",
    response_model=WorkflowSummaryList,
    summary="List workflows",
    description="List workflows with optional filters and pagination. Returns summaries without full workflow_json for performance.",
    responses=response_with_errors(401, 500),
)
async def list_workflows(
    status: str | None = Query(None, description="Filter by status (draft, published, archived)"),
    tags: str | None = Query(None, description="Filter by tags (comma-separated)"),
    offset: int = Query(0, ge=0, description="Number of workflows to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum workflows to return"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List workflows with optional filters and pagination.

    Returns lightweight WorkflowSummary objects (no workflow_json) for performance.
    Results ordered by created_at DESC (most recent first).

    Access control:
    - Users see their own workflows + shared workflows + public workflows
    - Admins see all workflows

    **Query Parameters:**
    - **status**: Filter by workflow status (draft, published, archived)
    - **tags**: Filter by tags (comma-separated, e.g., "data,analysis")
    - **offset**: Pagination offset (default: 0)
    - **limit**: Max results per page (1-100, default: 50)

    **Returns:**
    - **200**: Paginated list of workflow summaries
    - **total**: Total count matching filters
    """
    try:
        # Get base query with ownership/sharing filter
        filter_dep = filter_by_owner_or_shared(Workflow, "workflow")
        query = await filter_dep(user=user, db=db)

        # Apply additional filters
        if status:
            query = query.filter(Workflow.status == status)
        if tags:
            # Filter workflows that have any of the provided tags
            tag_list = [t.strip() for t in tags.split(",")]
            # Use JSON contains for tag filtering
            for tag in tag_list:
                query = query.filter(Workflow.tags.contains([tag]))

        # Get total count before pagination
        total = query.count()

        # Order by most recent first and apply pagination
        workflows = query.order_by(Workflow.created_at.desc()).offset(offset).limit(limit).all()

        # Compute has_more for pagination
        has_more = (offset + len(workflows)) < total

        return {
            "workflows": [workflow_to_summary(w) for w in workflows],
            "items": [workflow_to_summary(w) for w in workflows],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        }

    except Exception as e:
        logger.exception(f"Error listing workflows: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow listing failed. This may be a temporary issue - please try again.",
        ) from e

@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get workflow by ID",
    description="Get full workflow details including the workflow_json definition.",
    responses=response_with_errors(401, 403, 404, 500),
)
async def get_workflow(
    workflow_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get workflow details by ID.

    Returns full workflow including workflow_json (nodes, edges, metadata).
    Access control: owner, admin, public, or shared with user.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to retrieve

    **Returns:**
    - **200**: Full workflow details with workflow_json
    - **401**: Not authenticated
    - **403**: Access denied to private workflow
    - **404**: Workflow not found
    """
    try:
        # Use sharing-aware dependency
        get_dep = get_owned_or_shared_resource(Workflow, "workflow", "workflow_id")
        workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        return workflow_to_response(workflow)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve workflow. Verify the workflow ID or try again.",
        ) from e

@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update workflow",
    description="Update a draft workflow. Published/archived workflows are immutable.",
    responses=response_with_errors(400, 401, 403, 404, 409, 500),
)
async def update_workflow(
    workflow_id: int,
    request: UpdateWorkflowRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing draft workflow.

    Only draft workflows can be modified. Published/archived workflows are immutable.
    Validates new workflow_json if provided.
    Requires owner or edit permission on shared workflow.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to update

    **Request Body:**
    - **name**: Optional new name
    - **description**: Optional new description
    - **workflow_json**: Optional updated workflow definition
    - **tags**: Optional updated tags

    **Returns:**
    - **200**: Updated workflow details
    - **400**: Invalid workflow schema
    - **401**: Not authenticated
    - **403**: Access denied or cannot modify published/archived workflow
    - **404**: Workflow not found
    """
    user_id = user.get("sub")

    try:
        # Get workflow with edit permission required
        get_dep = get_owned_or_shared_resource(
            Workflow, "workflow", "workflow_id", require_edit=True
        )
        workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        # Only draft workflows can be modified
        if workflow.status != "draft":
            raise HTTPException(
                status_code=403,
                detail=f"Cannot modify workflow in '{workflow.status}' status. Only draft workflows can be modified.",
            )

        # Validate new workflow_json if provided
        if request.workflow_json is not None:
            try:
                WorkflowSchema.model_validate(request.workflow_json)
            except ValueError as e:
                logger.warning(f"Workflow validation failed: {e}")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid workflow schema. Check node connections and required fields.",
                ) from e
            workflow.workflow_json = request.workflow_json

        # Update fields
        if request.name is not None:
            workflow.name = request.name
        if request.description is not None:
            workflow.description = request.description
        if request.tags is not None:
            workflow.tags = request.tags

        workflow.updated_at = datetime.now(UTC)

        db.commit()
        db.refresh(workflow)

        # Audit log
        background_tasks.add_task(log_audit, db, user_id, "update", "workflow", str(workflow.id))

        logger.info(f"Updated workflow {workflow_id}")

        return workflow_to_response(workflow)

    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error updating workflow: {e}")
        raise HTTPException(
            status_code=400, detail="Workflow with this name and version already exists"
        ) from e
    except Exception as e:
        db.rollback()
        logger.exception(f"Error updating workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow update failed. This may be a temporary issue - please try again.",
        ) from e

@router.delete(
    "/{workflow_id}",
    status_code=204,
    summary="Delete workflow",
    description="Delete a draft workflow. Published/archived workflows cannot be deleted.",
    responses=response_with_errors(401, 403, 404, 500),
)
async def delete_workflow(
    workflow_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a draft workflow.

    Only draft workflows can be deleted. Published/archived workflows cannot be deleted.
    To remove a published workflow, archive it instead.
    Only owner can delete (shared users cannot delete).

    **Path Parameters:**
    - **workflow_id**: Workflow ID to delete

    **Returns:**
    - **204**: Workflow deleted (no content)
    - **401**: Not authenticated
    - **403**: Access denied or cannot delete published/archived workflow
    - **404**: Workflow not found
    """
    user_id = user.get("sub")

    try:
        # Owner only check (no shared access for delete)
        get_dep = get_owned_resource(Workflow, "workflow_id")
        workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        # Only draft workflows can be deleted
        if workflow.status != "draft":
            raise HTTPException(
                status_code=403,
                detail=f"Cannot delete workflow in '{workflow.status}' status. Only draft workflows can be deleted.",
            )

        db.delete(workflow)
        db.commit()

        # Audit log
        background_tasks.add_task(log_audit, db, user_id, "delete", "workflow", str(workflow_id))

        logger.info(f"Deleted workflow {workflow_id}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow deletion failed. This may be a temporary issue - please try again.",
        ) from e

# ============================================================================
# Lifecycle Endpoints
# ============================================================================

@router.post(
    "/{workflow_id}/publish",
    response_model=WorkflowResponse,
    summary="Publish workflow",
    description="Transition workflow from draft to published. Published workflows are immutable.",
    responses=response_with_errors(400, 401, 403, 404, 500),
)
async def publish_workflow(
    workflow_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Publish a draft workflow.

    Transitions workflow from 'draft' to 'published' status.
    Validates workflow_json one final time before publishing.
    Published workflows are immutable - they cannot be modified or deleted, only cloned.

    GAP-W2 FIX: Now requires JWT authentication via get_current_user dependency.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to publish

    **Returns:**
    - **200**: Published workflow details with published_at timestamp
    - **400**: Invalid workflow schema
    - **401**: Not authenticated
    - **403**: Cannot publish non-draft workflow or not owner
    - **404**: Workflow not found

    **Side Effects:**
    - Sets status to 'published'
    - Sets published_at timestamp
    - Workflow becomes immutable
    """
    user_id = user.get("sub")

    try:
        # Owner only check (GAP-W2: JWT auth replaces query param user_id)
        get_dep = get_owned_resource(Workflow, "workflow_id")
        workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        # Only draft workflows can be published
        if workflow.status != "draft":
            raise HTTPException(
                status_code=403,
                detail=f"Cannot publish workflow in '{workflow.status}' status. Only draft workflows can be published.",
            )

        # Validate workflow_json one final time before publishing
        try:
            WorkflowSchema.model_validate(workflow.workflow_json)
        except ValueError as e:
            logger.warning(f"Workflow validation failed during publish: {e}")
            raise HTTPException(
                status_code=400,
                detail="Cannot publish: workflow schema is invalid. Check node connections and required fields.",
            ) from e

        # Transition to published status
        workflow.status = "published"
        workflow.published_at = datetime.now(UTC)
        workflow.updated_at = datetime.now(UTC)

        db.commit()
        db.refresh(workflow)

        # Audit log
        background_tasks.add_task(log_audit, db, user_id, "publish", "workflow", str(workflow.id))

        logger.info(f"Workflow {workflow_id} published by user {user_id}")

        return workflow_to_response(workflow)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error publishing workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow publish failed. This may be a temporary issue - please try again.",
        ) from e

@router.post(
    "/{workflow_id}/archive",
    response_model=WorkflowResponse,
    summary="Archive workflow",
    description="Transition workflow from published to archived. Archived workflows are immutable and hidden from default listings.",
    responses=response_with_errors(400, 401, 403, 404, 500),
)
async def archive_workflow(
    workflow_id: int,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Archive a published workflow.

    Transitions workflow from 'published' to 'archived' status.
    Only published workflows can be archived (draft workflows must be published first).
    Only the workflow owner can archive.

    GAP-W1/W12 FIX: Dedicated archive endpoint replacing the broken PUT-with-status pattern.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to archive

    **Returns:**
    - **200**: Archived workflow details
    - **400**: Cannot archive non-published workflow
    - **401**: Not authenticated
    - **403**: Not owner
    - **404**: Workflow not found
    """
    user_id = user.get("sub")

    try:
        # Owner only check
        get_dep = get_owned_resource(Workflow, "workflow_id")
        workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        # Only published workflows can be archived
        if workflow.status != "published":
            raise HTTPException(
                status_code=400,
                detail="Only published workflows can be archived",
            )

        # Transition to archived status
        workflow.status = "archived"
        workflow.updated_at = datetime.now(UTC)

        db.commit()
        db.refresh(workflow)

        # Audit log
        background_tasks.add_task(log_audit, db, user_id, "archive", "workflow", str(workflow.id))

        logger.info(f"Workflow {workflow_id} archived by user {user_id}")

        return workflow_to_response(workflow)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error archiving workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow archive failed. This may be a temporary issue - please try again.",
        ) from e

@router.post(
    "/{workflow_id}/validate",
    response_model=WorkflowValidationResult,
    summary="Validate workflow",
    description="Validate a workflow without publishing. Returns structured validation results.",
    responses=response_with_errors(403, 404, 500),
)
async def validate_workflow(
    workflow_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkflowValidationResult:
    """Validate a workflow's graph structure, agents, and schema.

    Returns a structured validation result with errors and warnings.
    Does NOT change workflow state.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to validate

    **Returns:**
    - **200**: Validation result with {valid, errors, warnings}
    - **403**: Access denied
    - **404**: Workflow not found
    """
    try:
        get_dep = get_owned_or_shared_resource(Workflow, "workflow", "workflow_id")
        workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        errors = []
        warnings = []

        if not workflow.workflow_json:
            return WorkflowValidationResult(
                valid=False, errors=["Workflow has no graph data"], warnings=[]
            )

        # Schema validation
        try:
            schema = WorkflowSchema.model_validate(workflow.workflow_json)
        except ValueError as e:
            errors.extend(str(e).split("; "))
            return WorkflowValidationResult(valid=False, errors=errors, warnings=warnings)

        # Agent validation
        invalid_agents = schema.validate_agents()
        if invalid_agents:
            errors.append(f"Unknown agent(s): {', '.join(invalid_agents)}")

        # Cycle detection with node detail
        cycle_nodes = schema._find_cycle_nodes() if hasattr(schema, "_find_cycle_nodes") else []
        if cycle_nodes:
            cycle_path = " -> ".join(cycle_nodes + [cycle_nodes[0]])
            errors.append(f"Cycle detected: {cycle_path}")

        return WorkflowValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error validating workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow validation failed. This may be a temporary issue - please try again.",
        ) from e

@router.post(
    "/{workflow_id}/clone",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Clone workflow",
    description="Create a new draft workflow based on an existing workflow with incremented version.",
    responses=response_with_errors(400, 401, 403, 404, 409, 500),
)
async def clone_workflow(
    workflow_id: int,
    request: CloneWorkflowRequest = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clone a workflow to create a new draft.

    Creates a new draft workflow based on an existing workflow.
    Increments the minor version (1.0.0 -> 1.1.0).
    New workflow starts in 'draft' status and can be modified.

    GAP-111 FIX: Now requires authentication via get_current_user dependency.
    Cloned workflow is assigned to the authenticated user.

    **Path Parameters:**
    - **workflow_id**: Source workflow ID to clone

    **Request Body (optional):**
    - **name**: Custom name for clone (default: original name + " (copy)")

    **Returns:**
    - **201**: New cloned workflow details
    - **401**: Not authenticated
    - **403**: Access denied to private source workflow
    - **404**: Source workflow not found

    **Side Effects:**
    - Creates new workflow with status 'draft'
    - Version incremented (1.0.0 -> 1.1.0)
    - Cloned workflow is private by default
    - Cloned workflow assigned to authenticated user
    """
    user_id = user.get("sub")

    try:
        # Initialize request if not provided
        if request is None:
            request = CloneWorkflowRequest()

        source_workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

        if not source_workflow:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Access control for private workflows - only owner can clone private workflows
        if (
            not source_workflow.is_public
            and source_workflow.user_id
            and source_workflow.user_id != user_id
        ):
            raise HTTPException(status_code=403, detail="Access denied to private workflow")

        # Determine new workflow properties - always use authenticated user as owner
        new_name = request.name if request.name else f"{source_workflow.name} (copy)"
        new_version = increment_version(source_workflow.version)

        # Create cloned workflow - assigned to authenticated user (GAP-111 fix)
        cloned_workflow = Workflow(
            name=new_name,
            description=source_workflow.description,
            version=new_version,
            workflow_json=source_workflow.workflow_json,
            status="draft",
            is_public=False,  # Clones start as private
            user_id=user_id,  # Always use authenticated user
            tags=source_workflow.tags.copy() if source_workflow.tags else [],
            execution_count=0,
        )

        db.add(cloned_workflow)
        db.commit()
        db.refresh(cloned_workflow)

        logger.info(f"Workflow {workflow_id} cloned to {cloned_workflow.id} by user {user_id}")

        return workflow_to_response(cloned_workflow)

    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error cloning workflow: {e}")
        raise HTTPException(
            status_code=400, detail="Workflow with this name and version already exists"
        ) from e
    except Exception as e:
        db.rollback()
        logger.exception(f"Error cloning workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Workflow clone failed. This may be a temporary issue - please try again.",
        ) from e

# ============================================================================
# Execution Endpoints
# ============================================================================

@router.post(
    "/{workflow_id}/execute",
    summary="Execute workflow",
    description="Execute a published workflow with real-time SSE streaming updates.",
    responses=response_with_errors(400, 401, 403, 404, 500),
)
async def execute_workflow(
    workflow_id: int,
    request: ExecuteWorkflowRequest = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Execute a published workflow with streaming updates.

    DEPRECATION NOTE (GAP-W14/S5): This execution path is superseded by the
    scenario execution pipeline (workflow_scenarios.py). The Workflows API
    execute endpoint should be wired to use the scenario execution engine in a
    future unification pass. WorkflowExecutionResult table will be deprecated
    in favor of ScenarioExecutionResult (which now tracks template_id via
    metadata). See Phase 95.3 gap report.

    Only published workflows can be executed (draft/archived workflows return 403).
    Returns Server-Sent Events (SSE) stream with execution progress.

    GAP-W3 FIX: Now requires JWT authentication via get_current_user dependency.
    User ID for execution tracking is taken from JWT; request body user_id is ignored.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to execute

    **Request Body (optional):**
    - **inputs**: Initial state inputs (key-value pairs)
    - **conversation_id**: Associate execution with a conversation

    **SSE Event Types:**
    - **start**: Workflow execution began (includes execution_id)
    - **node_start**: Node started processing
    - **node_complete**: Node finished (output included)
    - **error**: Node or workflow failed
    - **complete**: Workflow finished (final result, duration_ms)
    - **[DONE]**: Stream terminated

    **Returns:**
    - **200**: SSE stream (text/event-stream)
    - **401**: Not authenticated
    - **403**: Cannot execute draft/archived workflow
    - **404**: Workflow not found

    **Example SSE Stream:**
    ```
    data: {"type": "start", "workflow_id": 1, "execution_id": 42}

    data: {"type": "node_start", "node_id": "task_1", "node_type": "task"}

    data: {"type": "node_complete", "node_id": "task_1", "output": "..."}

    data: {"type": "complete", "result": {...}, "duration_ms": 1234}

    data: [DONE]
    ```
    """
    # GAP-W3: Use JWT-authenticated user instead of request body user_id
    user_id = user.get("sub")

    # Initialize request if not provided
    if request is None:
        request = ExecuteWorkflowRequest()

    # Load workflow from database
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    # Only published workflows can be executed
    if workflow.status != "published":
        raise HTTPException(
            status_code=403,
            detail=f"Cannot execute workflow in '{workflow.status}' status. Only published workflows can be executed.",
        )

    logger.info(f"Executing workflow '{workflow.name}' (ID: {workflow_id}) by user '{user_id}'")

    async def generate_events():
        """Generate SSE events for workflow execution."""
        start_time = datetime.now(UTC)
        node_results = []
        execution_result = None

        logger.info(
            f"[EXECUTION] Starting workflow execution: workflow_id={workflow_id}, "
            f"user_id={request.user_id}, conversation_id={request.conversation_id}"
        )

        try:
            # Create execution result record (status=running)
            # GAP-W3: Use JWT user_id for execution tracking
            execution_result = WorkflowExecutionResult(
                workflow_id=workflow_id,
                user_id=user_id,
                conversation_id=request.conversation_id,
                status="running",
                started_at=start_time,
                template_id=request.template_id,
                template_version_id=request.template_version_id,
            )
            db.add(execution_result)
            db.commit()
            db.refresh(execution_result)

            logger.debug(
                f"[EXECUTION] Created execution record {execution_result.id} for workflow {workflow_id}"
            )

            # Emit start event
            yield f"data: {json.dumps({'type': 'start', 'workflow_id': workflow_id, 'workflow_name': workflow.name, 'execution_id': execution_result.id})}\n\n"

            # Validate workflow schema
            try:
                schema = WorkflowSchema.model_validate(workflow.workflow_json)
            except ValueError as e:
                error_msg = f"Invalid workflow schema: {str(e)}"
                execution_result.status = "failed"
                execution_result.error = error_msg
                execution_result.completed_at = datetime.now(UTC)
                db.commit()
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                yield "data: [DONE]\n\n"
                return

            logger.debug(f"[EXECUTION] Workflow {workflow_id}: schema validated")

            # Translate to FlowConfig
            translator = WorkflowTranslator()
            try:
                flowconfig = translator.to_flowconfig(schema)
            except Exception as e:
                error_msg = f"Translation failed: {str(e)}"
                execution_result.status = "failed"
                execution_result.error = error_msg
                execution_result.completed_at = datetime.now(UTC)
                db.commit()
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                yield "data: [DONE]\n\n"
                return

            logger.debug(
                f"[EXECUTION] Workflow {workflow_id}: translated to flow with {len(flowconfig.nodes)} nodes"
            )

            # Generate Flow class
            executor = WorkflowExecutor()
            try:
                flow_class = executor.generate_flow_class(flowconfig)
            except Exception as e:
                error_msg = f"Flow generation failed: {str(e)}"
                execution_result.status = "failed"
                execution_result.error = error_msg
                execution_result.completed_at = datetime.now(UTC)
                db.commit()
                yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Instantiate flow
            flow_instance = flow_class()

            # Set initial state inputs
            for key, value in request.inputs.items():
                if hasattr(flow_instance.state, key):
                    setattr(flow_instance.state, key, value)

            # Emit node start events for tracking
            for node in flowconfig.nodes:
                node_id = node.get("id", "")
                node_type = node.get("type", "")
                logger.debug(f"[EXECUTION] Node '{node_id}' ({node_type}) execution starting")
                yield f"data: {json.dumps({'type': 'node_start', 'node_id': node_id, 'node_type': node_type})}\n\n"
                await asyncio.sleep(0.01)  # Allow event to be sent

            # Execute flow in thread pool (blocking operation)
            try:
                result = await asyncio.to_thread(flow_instance.kickoff)
            except Exception as e:
                # Check if this is a WorkflowPausedForApproval sentinel (not an error)
                from core.exceptions import WorkflowPausedForApproval

                if isinstance(e.__cause__, WorkflowPausedForApproval) or isinstance(
                    e, WorkflowPausedForApproval
                ):
                    _pause_exc = (
                        e.__cause__ if isinstance(e.__cause__, WorkflowPausedForApproval) else e
                    )
                    # Extract approval metadata from flow state
                    state_dict_pause = (
                        flow_instance.state.model_dump()
                        if hasattr(flow_instance.state, "model_dump")
                        else {}
                    )
                    approval_meta = None
                    for _k, _v in state_dict_pause.items():
                        if isinstance(_v, dict) and _v.get("status") == "awaiting_approval":
                            approval_meta = _v
                            break

                    if approval_meta:
                        from core.workflows.approval import ApprovalService

                        approval_request_id = await ApprovalService.create_approval_request(
                            db=db,
                            execution_id=execution_result.id,
                            workflow_id=workflow_id,
                            node_id=approval_meta["node_id"],
                            state_snapshot=approval_meta.get("state_snapshot", {}),
                            prompt=approval_meta["prompt"],
                            approver=approval_meta.get("approver", "owner"),
                            approver_user_id=approval_meta.get("approver_user_id"),
                            display_fields=approval_meta.get("display_fields", []),
                            timeout_seconds=approval_meta.get("timeout_seconds", 86400),
                            timeout_action=approval_meta.get("timeout_action", "reject"),
                        )
                        logger.info(
                            f"[EXECUTION] Workflow {workflow_id} paused for approval, "
                            f"request_id={approval_request_id}"
                        )
                        # Flat-dict SSE emission (matches frontend useWorkflowState handler)
                        workflow_name = workflow.name if hasattr(workflow, "name") else ""
                        yield f"data: {json.dumps({'type': 'approval_pending', 'approval_request_id': approval_request_id, 'workflow_id': workflow_id, 'workflow_name': workflow_name, 'node_id': approval_meta['node_id'], 'prompt': approval_meta['prompt']})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    else:
                        error_msg = "Workflow paused for approval but no approval metadata found"
                        execution_result.status = "failed"
                        execution_result.error = error_msg
                        execution_result.completed_at = datetime.now(UTC)
                        db.commit()
                        yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                else:
                    error_msg = f"Execution failed: {str(e)}"
                    execution_result.status = "failed"
                    execution_result.error = error_msg
                    execution_result.completed_at = datetime.now(UTC)
                    db.commit()
                    yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            # Emit node complete events
            state_dict = (
                flow_instance.state.model_dump()
                if hasattr(flow_instance.state, "model_dump")
                else {}
            )
            for key, value in state_dict.items():
                if "_output" in key and value is not None:
                    node_id = key.replace("_output", "")
                    node_results.append(
                        {
                            "node_id": node_id,
                            "output": str(value)[:500] if value else None,  # Truncate large outputs
                        }
                    )
                    output_preview = (
                        str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                    )
                    logger.debug(f"[EXECUTION] Node '{node_id}' completed: {output_preview}")
                    yield f"data: {json.dumps({'type': 'node_complete', 'node_id': node_id, 'output': str(value)[:500] if value else None})}\n\n"

            # Calculate duration
            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Update execution count
            try:
                workflow.increment_execution()
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to update execution count: {e}")

            # Update execution result with success
            final_result = result if isinstance(result, dict) else {"output": str(result)}
            # Build step_results from node_results for client consumption
            step_results = {}
            for nr in node_results:
                step_results[nr["node_id"]] = {
                    "output": nr.get("output", ""),
                    "error": nr.get("error"),
                }
            final_result["status"] = "completed"
            final_result["step_results"] = step_results
            final_result["final_output"] = final_result.get("output", str(result))
            execution_result.status = "success"
            execution_result.completed_at = end_time
            execution_result.duration_ms = duration_ms
            execution_result.node_results = node_results
            execution_result.final_result = final_result
            db.commit()

            # Emit complete event
            yield f"data: {json.dumps({'type': 'complete', 'result': final_result, 'duration_ms': duration_ms, 'execution_id': execution_result.id})}\n\n"

            logger.info(
                f"Workflow {workflow_id} execution {execution_result.id}: success in {duration_ms}ms"
            )

        except Exception as e:
            logger.error(f"Workflow execution error: {e}", exc_info=True)
            if execution_result:
                execution_result.status = "failed"
                execution_result.error = str(e)
                execution_result.completed_at = datetime.now(UTC)
                with contextlib.suppress(Exception):
                    db.commit()
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

@router.get(
    "/{workflow_id}/executions",
    response_model=ExecutionResultList,
    summary="Get workflow execution history",
    description="Get paginated execution history for a workflow with optional filters.",
    responses=response_with_errors(401, 403, 404, 500),
)
async def get_workflow_executions(
    workflow_id: int,
    status: str | None = Query(None, description="Filter by status (running, success, failed)"),
    offset: int = Query(0, ge=0, description="Number of executions to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum executions to return"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get execution history for a workflow.

    Returns paginated list of WorkflowExecutionResult records.
    Results ordered by started_at DESC (most recent first).

    GAP-W4 FIX: Now requires JWT authentication via get_current_user dependency.
    Access control: requesting user must be the workflow owner or have a share entry.

    **Path Parameters:**
    - **workflow_id**: Workflow ID

    **Query Parameters:**
    - **status**: Filter by execution status (running, success, failed)
    - **offset**: Pagination offset (default: 0)
    - **limit**: Max results per page (1-100, default: 50)

    **Returns:**
    - **200**: Paginated list of execution results
    - **401**: Not authenticated
    - **403**: Access denied (not owner or shared user)
    - **404**: Workflow not found

    **Response includes:**
    - Execution status, timestamps, duration
    - Per-node results
    - Final result or error message
    - Execution cost (if available)
    """
    try:
        # GAP-W4: Verify workflow exists AND user has access (owner or shared)
        get_dep = get_owned_or_shared_resource(Workflow, "workflow", "workflow_id")
        await get_dep(resource_id=workflow_id, user=user, db=db)

        # Build query
        query = db.query(WorkflowExecutionResult).filter(
            WorkflowExecutionResult.workflow_id == workflow_id
        )

        # Apply filters
        if status:
            query = query.filter(WorkflowExecutionResult.status == status)

        # Get total count before pagination
        total = query.count()

        # Order by most recent first and apply pagination
        executions = (
            query.order_by(WorkflowExecutionResult.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Convert to response format
        execution_responses = []
        for execution in executions:
            execution_responses.append(
                {
                    "id": execution.id,
                    "workflow_id": execution.workflow_id,
                    "user_id": execution.user_id,
                    "conversation_id": execution.conversation_id,
                    "status": execution.status,
                    "started_at": execution.started_at.isoformat()
                    if execution.started_at
                    else None,
                    "completed_at": execution.completed_at.isoformat()
                    if execution.completed_at
                    else None,
                    "duration_ms": execution.duration_ms,
                    "node_results": execution.node_results or [],
                    "final_result": execution.final_result,
                    "error": execution.error,
                    "cost": execution.cost,
                    "created_at": execution.created_at.isoformat()
                    if execution.created_at
                    else None,
                }
            )

        # Compute has_more for pagination
        has_more = (offset + len(execution_responses)) < total

        logger.info(
            f"Workflow {workflow_id} execution history: {total} total, returning {len(execution_responses)}"
        )

        return {
            "executions": execution_responses,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting workflow executions: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve execution history. This may be a temporary issue - please try again.",
        ) from e

# ============================================================================
# Sharing Endpoints
# ============================================================================

@router.post(
    "/{workflow_id}/share",
    summary="Share workflow with user",
    description="Share a workflow with another user with view or edit permission.",
    responses=response_with_errors(400, 401, 403, 404, 500),
)
async def share_workflow(
    workflow_id: int,
    request: ShareWorkflowRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Share a workflow with another user.

    Only the workflow owner can share it. Creates or updates the sharing relationship.

    **Path Parameters:**
    - **workflow_id**: Workflow ID to share

    **Request Body:**
    - **user_id**: User ID to share with
    - **permission**: Permission level ('view' or 'edit')

    **Returns:**
    - **200**: Share created/updated successfully
    - **400**: Invalid permission or cannot share this resource type
    - **401**: Not authenticated
    - **403**: Only owner can share
    - **404**: Workflow or target user not found
    """
    owner_id = user.get("sub")

    try:
        # Only owner can share (not shared users)
        get_dep = get_owned_resource(Workflow, "workflow_id")
        _workflow = await get_dep(resource_id=workflow_id, user=user, db=db)

        # Share with target user
        sharing = SharingService(db)
        share = sharing.share(
            resource_type="workflow",
            resource_id=workflow_id,
            owner_id=owner_id,
            target_user_id=request.user_id,
            permission=request.permission,
        )

        # Audit log
        background_tasks.add_task(
            log_audit,
            db,
            owner_id,
            "share",
            "workflow",
            str(workflow_id),
            metadata={"target_user": request.user_id, "permission": request.permission},
        )

        return {
            "message": "Workflow shared successfully",
            "workflow_id": workflow_id,
            "shared_with": request.user_id,
            "permission": share.permission,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error sharing workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to share workflow. Verify the target user exists and try again.",
        ) from e

@router.delete(
    "/{workflow_id}/share/{target_user_id}",
    status_code=204,
    summary="Unshare workflow",
    description="Remove sharing for a workflow with a specific user.",
    responses=response_with_errors(401, 403, 404, 500),
)
async def unshare_workflow(
    workflow_id: int,
    target_user_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove sharing for a workflow with a user.

    Only the workflow owner can remove sharing.

    **Path Parameters:**
    - **workflow_id**: Workflow ID
    - **target_user_id**: User ID to remove sharing for

    **Returns:**
    - **204**: Share removed (no content)
    - **401**: Not authenticated
    - **403**: Only owner can remove sharing
    - **404**: Workflow not found or share does not exist
    """
    owner_id = user.get("sub")

    try:
        # Only owner can unshare
        get_dep = get_owned_resource(Workflow, "workflow_id")
        await get_dep(resource_id=workflow_id, user=user, db=db)

        # Remove share
        sharing = SharingService(db)
        removed = sharing.unshare("workflow", workflow_id, target_user_id)

        if not removed:
            raise HTTPException(status_code=404, detail="Share not found")

        # Audit log
        background_tasks.add_task(
            log_audit,
            db,
            owner_id,
            "unshare",
            "workflow",
            str(workflow_id),
            metadata={"target_user": target_user_id},
        )

        logger.info(f"Unshared workflow {workflow_id} from user {target_user_id}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error unsharing workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to remove sharing. This may be a temporary issue - please try again.",
        ) from e

@router.get(
    "/{workflow_id}/shares",
    summary="List workflow shares",
    description="Get list of users a workflow is shared with.",
    responses=response_with_errors(401, 403, 404, 500),
)
async def list_workflow_shares(
    workflow_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List all users a workflow is shared with.

    Only the workflow owner can view shares.

    **Path Parameters:**
    - **workflow_id**: Workflow ID

    **Returns:**
    - **200**: List of shares with user IDs and permissions
    - **401**: Not authenticated
    - **403**: Only owner can view shares
    - **404**: Workflow not found
    """
    try:
        # Only owner can list shares
        get_dep = get_owned_resource(Workflow, "workflow_id")
        await get_dep(resource_id=workflow_id, user=user, db=db)

        sharing = SharingService(db)
        shares = sharing.get_shared_users("workflow", workflow_id)

        return {"workflow_id": workflow_id, "shares": shares}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error listing shares for workflow {workflow_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list shares. This may be a temporary issue - please try again.",
        ) from e

# ============================================================================
# Template-Originated Workflow Creation (GAP-W13)
# ============================================================================

class CreateFromTemplateRequest(BaseModel):
    """Request to create a workflow from a template.

    The frontend provides workflow_json from the template (loaded via CustomEvent)
    along with template provenance for lineage tracking.

    Note: Core does NOT import from plugins (per plugin security model).
    The workflow_json is passed by the frontend which already has it from loadTemplate.
    """

    workflow_json: dict[str, Any] = Field(
        ..., description="Workflow definition from template version"
    )
    template_id: int = Field(..., description="Source org template ID for provenance tracking")
    template_version_id: int | None = Field(
        None, description="Source template version ID for provenance tracking"
    )
    name: str = Field("Untitled Workflow", description="Name for the new workflow", max_length=200)
    description: str | None = Field(None, description="Optional description", max_length=2000)

@router.post(
    "/from-template",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Create workflow from template",
    description="Create a new Workflow record from template data with source provenance.",
    responses=response_with_errors(400, 401, 500),
)
async def create_workflow_from_template(
    request: CreateFromTemplateRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a workflow from a template with provenance tracking.

    Creates a new draft Workflow record from template workflow_json.
    Stores source_template_id and source_template_version_id in the
    workflow's metadata for lineage tracking.

    **Request Body:**
    - **workflow_json**: Complete workflow definition from template
    - **template_id**: Source template ID
    - **template_version_id**: Source template version ID (optional)
    - **name**: Name for the new workflow
    - **description**: Optional description

    **Returns:**
    - **201**: Workflow created with template provenance
    - **400**: Invalid workflow schema
    - **401**: Not authenticated
    """
    user_id = user.get("sub")

    try:
        # Validate workflow_json
        try:
            WorkflowSchema.model_validate(request.workflow_json)
        except ValueError as e:
            logger.warning(f"Template workflow validation failed: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid workflow schema from template. Check node connections and required fields.",
            ) from e

        # Create workflow with template provenance in metadata
        workflow = Workflow(
            name=request.name,
            description=request.description,
            version="1.0.0",
            workflow_json=request.workflow_json,
            status="draft",
            is_public=False,
            user_id=user_id,
            tags=["from-template"],
            execution_count=0,
        )

        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        # Audit log
        background_tasks.add_task(
            log_audit,
            db,
            user_id,
            "create",
            "workflow",
            str(workflow.id),
            metadata={
                "source": "template",
                "template_id": request.template_id,
                "template_version_id": request.template_version_id,
            },
        )

        logger.info(
            f"Created workflow {workflow.id} from template {request.template_id} for user {user_id}"
        )

        return workflow_to_response(workflow)

    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating workflow from template: {e}")
        raise HTTPException(
            status_code=400, detail="Workflow with this name and version already exists"
        ) from e
    except Exception as e:
        db.rollback()
        logger.exception(f"Error creating workflow from template: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create workflow from template. Please try again.",
        ) from e

# ============================================================================
# Approval Action Endpoints (Phase 150)
# ============================================================================

class ApprovalActionRequest(BaseModel):
    """Request to act on a pending approval."""

    action: Literal["approve", "reject", "modify"]
    note: str | None = None
    modified_fields: dict[str, Any] | None = None  # Only for action=="modify"

class ApprovalRequestResponse(BaseModel):
    """Response for a pending approval request."""

    id: int
    workflow_id: int
    node_id: str
    status: str
    prompt: str
    approver_type: str
    display_fields: list[str]
    timeout_at: str
    timeout_action: str
    created_at: str

def _approval_to_response(r) -> ApprovalRequestResponse:
    """Convert WorkflowApprovalRequest DB model to response."""
    return ApprovalRequestResponse(
        id=r.id,
        workflow_id=r.workflow_id,
        node_id=r.node_id,
        status=r.status,
        prompt=r.prompt,
        approver_type=r.approver_type,
        display_fields=r.display_fields or [],
        timeout_at=r.timeout_at.isoformat() if r.timeout_at else "",
        timeout_action=r.timeout_action,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )

@router.post(
    "/{workflow_id}/approvals/{request_id}/action",
    summary="Approve, reject, or modify a pending workflow approval",
    responses=response_with_errors(400, 401, 403, 404, 409, 500),
)
async def take_approval_action(
    workflow_id: int,
    request_id: int,
    body: ApprovalActionRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve, reject, or modify a pending approval request.

    Uses optimistic locking: UPDATE WHERE status='pending' — only first actor wins.
    Returns 409 if already resolved.
    """
    from sqlalchemy import update as sa_update

    from core.database.models import WorkflowApprovalRequest
    from core.workflows.approval import ApprovalService

    # 1. Load approval request
    request = (
        db.query(WorkflowApprovalRequest).filter_by(id=request_id, workflow_id=workflow_id).first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    # 2. Validate modify action: check modified_fields against display_fields whitelist
    if body.action == "modify" and body.modified_fields:
        allowed = set(request.display_fields or [])
        invalid_keys = set(body.modified_fields.keys()) - allowed
        if invalid_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Fields not in display_fields whitelist: {list(invalid_keys)}",
            )

    # 3. Optimistic lock: only resolve if still pending
    actor_user_id = user.get("sub", str(user))
    rows = db.execute(
        sa_update(WorkflowApprovalRequest)
        .where(WorkflowApprovalRequest.id == request_id)
        .where(WorkflowApprovalRequest.status == "pending")
        .values(
            status=body.action if body.action != "modify" else "approved",
            resolved_by=actor_user_id,
            resolved_at=datetime.now(UTC),
            resolution_note=body.note,
            modified_fields=body.modified_fields if body.action == "modify" else None,
        )
    ).rowcount
    db.commit()

    if rows == 0:
        raise HTTPException(status_code=409, detail="Approval request already resolved")

    # 4. Record audit
    await ApprovalService.record_audit(
        db,
        request_id,
        actor_user_id,
        body.action,
        {"note": body.note, "modified_fields": body.modified_fields},
    )

    # 5. Resume workflow execution in background
    db.refresh(request)
    effective_action = "approve" if body.action == "modify" else body.action
    background_tasks.add_task(
        ApprovalService.resume_from_approval,
        request,
        effective_action,
        body.modified_fields,
        db,
    )

    logger.info(
        f"[APPROVAL] Action '{body.action}' taken on request {request_id} "
        f"(workflow {workflow_id}) by user '{actor_user_id}'"
    )
    return {"status": "ok", "action": body.action, "approval_request_id": request_id}

@router.get(
    "/{workflow_id}/approvals/pending",
    response_model=list[ApprovalRequestResponse],
    summary="List pending approvals for a workflow",
    responses=response_with_errors(401, 403, 404, 500),
)
async def list_pending_approvals(
    workflow_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List pending approval requests for a specific workflow."""
    from core.database.models import WorkflowApprovalRequest

    requests = (
        db.query(WorkflowApprovalRequest).filter_by(workflow_id=workflow_id, status="pending").all()
    )
    return [_approval_to_response(r) for r in requests]

@router.get(
    "/approvals/pending/count",
    summary="Get count of pending approvals for current user",
    responses=response_with_errors(401, 500),
)
async def get_pending_approval_count(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Global count of pending approvals for the current user (notification badge)."""
    from core.database.models import WorkflowApprovalRequest

    user_id = user.get("sub", str(user))
    count = (
        db.query(WorkflowApprovalRequest)
        .filter(
            WorkflowApprovalRequest.status == "pending",
            (
                (WorkflowApprovalRequest.approver_type == "any_member")
                | (WorkflowApprovalRequest.approver_type == "owner")
                | (
                    (WorkflowApprovalRequest.approver_type == "specific_user")
                    & (WorkflowApprovalRequest.approver_user_id == user_id)
                )
            ),
        )
        .count()
    )
    return {"count": count}
