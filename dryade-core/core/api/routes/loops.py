"""Loop Engine API Routes — CRUD, lifecycle, and execution history for scheduled loops.

Provides 10 REST endpoints for managing scheduled loops:
- CRUD: create, list, get, update, delete
- Lifecycle: trigger, pause, resume
- History: loop executions, single execution
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.loops.models import (
    ExecutionStatus,
    LoopExecution,
    ScheduledLoop,
    TargetType,
    TriggerType,
)
from core.loops.service import get_loop_service

router = APIRouter(prefix="/loops", tags=["loops"])
logger = logging.getLogger(__name__)

# ============================================================================
# Request/Response Models
# ============================================================================

class LoopCreate(BaseModel):
    """Request to create a new scheduled loop."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique loop name")
    target_type: str = Field(
        ..., description="Target type: workflow, agent, skill, orchestrator_task"
    )
    target_id: str = Field(..., min_length=1, max_length=255, description="Target identifier")
    trigger_type: str = Field(..., description="Trigger type: cron, interval, oneshot")
    schedule: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Cron expression, interval (30m/4h), or ISO datetime",
    )
    timezone: str = Field(default="UTC", max_length=64)
    config: dict[str, Any] | None = Field(default=None, description="Inputs/context for target")
    enabled: bool = Field(default=True)

class LoopUpdate(BaseModel):
    """Request to update a scheduled loop."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    schedule: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)

class LoopResponse(BaseModel):
    """Loop details response."""

    id: str
    name: str
    target_type: str
    target_id: str
    trigger_type: str
    schedule: str
    timezone: str
    enabled: bool
    config: dict[str, Any] | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None

    class Config:
        from_attributes = True

class LoopExecutionResponse(BaseModel):
    """Execution details response."""

    id: str
    loop_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempt: int = 1
    trigger_source: str = "schedule"
    created_at: datetime | None = None

    class Config:
        from_attributes = True

class LoopListResponse(BaseModel):
    """Paginated loop list response."""

    items: list[LoopResponse]
    total: int

class ExecutionListResponse(BaseModel):
    """Paginated execution list response."""

    items: list[LoopExecutionResponse]
    total: int

# ============================================================================
# Helper: Convert ORM to response
# ============================================================================

def _loop_to_response(loop: ScheduledLoop) -> LoopResponse:
    """Convert a ScheduledLoop ORM instance to a response model."""
    return LoopResponse(
        id=loop.id,
        name=loop.name,
        target_type=loop.target_type.value
        if isinstance(loop.target_type, TargetType)
        else str(loop.target_type),
        target_id=loop.target_id,
        trigger_type=loop.trigger_type.value
        if isinstance(loop.trigger_type, TriggerType)
        else str(loop.trigger_type),
        schedule=loop.schedule,
        timezone=loop.timezone,
        enabled=loop.enabled,
        config=loop.config,
        created_by=loop.created_by,
        created_at=loop.created_at,
        updated_at=loop.updated_at,
        last_run_at=loop.last_run_at,
        next_run_at=loop.next_run_at,
    )

def _execution_to_response(execution: LoopExecution) -> LoopExecutionResponse:
    """Convert a LoopExecution ORM instance to a response model."""
    return LoopExecutionResponse(
        id=execution.id,
        loop_id=execution.loop_id,
        status=execution.status.value
        if isinstance(execution.status, ExecutionStatus)
        else str(execution.status),
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        duration_ms=execution.duration_ms,
        result=execution.result,
        error=execution.error,
        attempt=execution.attempt,
        trigger_source=execution.trigger_source,
        created_at=execution.created_at,
    )

# ============================================================================
# Endpoints
# ============================================================================

@router.post("", response_model=LoopResponse, status_code=201)
async def create_loop(
    body: LoopCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new scheduled loop."""
    # Validate enums
    try:
        TargetType(body.target_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target_type: {body.target_type}. Must be one of: {[t.value for t in TargetType]}",
        )
    try:
        TriggerType(body.trigger_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trigger_type: {body.trigger_type}. Must be one of: {[t.value for t in TriggerType]}",
        )

    service = get_loop_service()
    try:
        loop = service.create_loop(
            loop_data=body.model_dump(),
            user_id=user.get("sub"),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"A loop named '{body.name}' already exists. Choose a different name.",
        )
    except Exception as e:
        logger.error("Failed to create loop", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))

    return _loop_to_response(loop)

@router.get("", response_model=LoopListResponse)
async def list_loops(
    target_type: str | None = Query(default=None, description="Filter by target type"),
    enabled: bool | None = Query(default=None, description="Filter by enabled status"),
    user: dict = Depends(get_current_user),
):
    """List all scheduled loops with optional filters."""
    service = get_loop_service()
    loops = service.list_loops(target_type=target_type, enabled=enabled)
    return LoopListResponse(
        items=[_loop_to_response(loop) for loop in loops],
        total=len(loops),
    )

# NOTE: /executions/{execution_id} MUST be before /{loop_id} to avoid
# "executions" being captured as a loop_id parameter.
@router.get("/executions/{execution_id}", response_model=LoopExecutionResponse)
async def get_execution(
    execution_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single execution's details."""
    execution = db.query(LoopExecution).filter(LoopExecution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return _execution_to_response(execution)

@router.get("/{loop_id}", response_model=LoopResponse)
async def get_loop(
    loop_id: str,
    user: dict = Depends(get_current_user),
):
    """Get loop details by ID."""
    service = get_loop_service()
    loop = service.get_loop(loop_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")
    return _loop_to_response(loop)

@router.patch("/{loop_id}", response_model=LoopResponse)
async def update_loop(
    loop_id: str,
    body: LoopUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a scheduled loop's schedule, config, or enabled state."""
    loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")

    update_data = body.model_dump(exclude_unset=True)
    service = get_loop_service()

    # Track if schedule changed (requires re-registration)
    schedule_changed = False

    for field, value in update_data.items():
        if field in ("schedule", "timezone"):
            schedule_changed = True
        setattr(loop, field, value)

    db.commit()
    db.refresh(loop)

    # Re-register with scheduler if schedule changed or enabled toggled
    if schedule_changed or "enabled" in update_data:
        if loop.enabled:
            service._unregister_from_scheduler(loop_id)
            try:
                service._register_with_scheduler(loop)
            except Exception as e:
                logger.error(
                    "Failed to re-register loop", extra={"loop_id": loop_id, "error": str(e)}
                )
        else:
            service._unregister_from_scheduler(loop_id)

    return _loop_to_response(loop)

@router.delete("/{loop_id}", status_code=204)
async def delete_loop(
    loop_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a loop and cancel its scheduler job."""
    service = get_loop_service()
    deleted = service.delete_loop(loop_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Loop not found")

@router.post("/{loop_id}/trigger", response_model=LoopExecutionResponse)
async def trigger_loop(
    loop_id: str,
    user: dict = Depends(get_current_user),
):
    """Manually trigger a loop execution."""
    service = get_loop_service()
    execution = await service.trigger_manual(loop_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Loop not found")
    return _execution_to_response(execution)

@router.post("/{loop_id}/pause", response_model=LoopResponse)
async def pause_loop(
    loop_id: str,
    user: dict = Depends(get_current_user),
):
    """Pause a loop — disables scheduling."""
    service = get_loop_service()
    loop = service.pause_loop(loop_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")
    return _loop_to_response(loop)

@router.post("/{loop_id}/resume", response_model=LoopResponse)
async def resume_loop(
    loop_id: str,
    user: dict = Depends(get_current_user),
):
    """Resume a paused loop — re-enables scheduling."""
    service = get_loop_service()
    loop = service.resume_loop(loop_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")
    return _loop_to_response(loop)

@router.get("/{loop_id}/executions", response_model=ExecutionListResponse)
async def get_loop_executions(
    loop_id: str,
    status: str | None = Query(default=None, description="Filter by execution status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get execution history for a loop with pagination and status filter."""
    # Verify loop exists
    loop = db.query(ScheduledLoop).filter(ScheduledLoop.id == loop_id).first()
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")

    query = db.query(LoopExecution).filter(LoopExecution.loop_id == loop_id)
    if status:
        query = query.filter(LoopExecution.status == status)

    total = query.count()
    executions = query.order_by(LoopExecution.started_at.desc()).offset(offset).limit(limit).all()

    return ExecutionListResponse(
        items=[_execution_to_response(e) for e in executions],
        total=total,
    )
