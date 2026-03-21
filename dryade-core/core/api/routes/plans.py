"""Plan Management Routes - CRUD operations for execution plans.

Provides REST API for plan persistence, modification, and re-execution.
Target: ~350 LOC
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from time import time
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from core.api.models.openapi import response_with_errors
from core.auth.dependencies import get_current_user, get_db
from core.database.models import Conversation, ExecutionPlan, Message, PlanExecutionResult

router = APIRouter()
logger = logging.getLogger(__name__)

PlanStatus = Literal["draft", "approved", "executing", "completed", "failed", "cancelled"]
PlanExecutionStatus = Literal["executing", "completed", "failed", "cancelled", "timeout"]
PlanNodeStatus = Literal["pending", "executing", "completed", "failed", "skipped", "degraded"]

# Content-based refusal detection patterns.
# Used to detect agent outputs that indicate the agent could not actually
# complete the task (e.g. "I can't do this", "tool not found").
# All patterns MUST be lowercase for case-insensitive matching.
REFUSAL_PATTERNS = [
    "i can't",
    "i cannot",
    "i'm unable",
    "i am unable",
    "i don't have",
    "i do not have",
    "not available",
    "cannot complete",
    "unable to complete",
    "function not found",
    "tool not found",
    "i'm sorry",
    "i am sorry",
    "does not include",
    "no tool",
    "no function",
    "not supported",
    "not implemented",
    "failed to",
    "could not",
]

# ============================================================================
# Request/Response Models
# ============================================================================

class PlanNodeRequest(BaseModel):
    """Plan node definition.

    Each node represents a task assigned to an agent within the execution plan.
    """

    id: str = Field(..., description="Unique node identifier within the plan")
    agent: str = Field(
        ..., description="Agent name to execute this task (e.g., 'research', 'writer')"
    )
    task: str = Field(..., description="Task description for the agent to execute")
    depends_on: list[str] = Field(
        default_factory=list, description="Node IDs that must complete before this node"
    )
    expected_output: str | None = Field(None, description="Expected output format or description")

class PlanEdgeRequest(BaseModel):
    """Plan edge (dependency) definition.

    Defines execution order between nodes in the plan DAG.
    Uses source/target as canonical field names, with from/to as aliases
    for backward compatibility with older clients.
    """

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(..., alias="from", description="Source node ID (executes first)")
    target: str = Field(..., alias="to", description="Target node ID (executes after source)")

class CreatePlanRequest(BaseModel):
    """Request to create/save a new execution plan.

    Plans represent multi-agent execution workflows with task dependencies.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "conv_abc123",
                "name": "Research and Summarize",
                "description": "Research a topic and create a summary",
                "nodes": [
                    {"id": "research", "agent": "research", "task": "Research AI trends"},
                    {
                        "id": "summarize",
                        "agent": "writer",
                        "task": "Summarize findings",
                        "depends_on": ["research"],
                    },
                ],
                "edges": [{"from": "research", "to": "summarize"}],
                "confidence": 0.85,
                "status": "draft",
            }
        }
    )

    conversation_id: str = Field(..., description="Conversation ID to associate this plan with")
    user_id: str | None = Field(None, description="User ID who created this plan")
    name: str = Field(..., description="Plan name (1-200 characters)", min_length=1, max_length=200)
    description: str | None = Field(
        None, description="Human-readable plan description", max_length=2000
    )
    nodes: list[dict[str, Any]] = Field(
        ..., description="List of plan nodes defining tasks and agents"
    )
    edges: list[dict[str, Any]] = Field(
        default_factory=list, description="List of edges defining execution dependencies"
    )
    reasoning: str | None = Field(None, description="LLM reasoning for why this plan was generated")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score (0.0-1.0) in plan quality"
    )
    status: PlanStatus = Field(
        "draft",
        description="Initial status. One of: draft, approved, executing, completed, failed, cancelled",
    )
    ai_generated: bool = Field(False, description="Whether this plan was AI-generated")

class UpdatePlanRequest(BaseModel):
    """Request to update an existing plan.

    Only plans in modifiable states (draft, approved, failed, cancelled) can be updated.
    Plans in executing or completed states are immutable.
    """

    name: str | None = Field(None, description="Updated plan name", min_length=1, max_length=200)
    description: str | None = Field(None, description="Updated description", max_length=2000)
    nodes: list[dict[str, Any]] | None = Field(None, description="Updated node definitions")
    edges: list[dict[str, Any]] | None = Field(None, description="Updated edge definitions")
    reasoning: str | None = Field(None, description="Updated reasoning")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Updated confidence score (0.0-1.0)"
    )
    status: PlanStatus | None = Field(
        None, description="Updated status. Valid transitions depend on current status"
    )

class ExecutePlanRequest(BaseModel):
    """Request to execute a saved plan.

    Execution creates a PlanExecutionResult record and tracks per-node results.
    """

    conversation_id: str | None = Field(
        None, description="Override conversation ID for this execution"
    )
    user_id: str | None = Field(None, description="User ID for tracking and cost attribution")

class FeedbackRequest(BaseModel):
    """Request to submit user feedback for a plan execution.

    Feedback helps improve plan generation quality over time.
    """

    execution_id: str = Field(..., description="Execution ID to provide feedback for")
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 (poor) to 5 (excellent)")
    comment: str | None = Field(
        None, description="Optional free-text feedback comment", max_length=2000
    )

class PlanValidationResult(BaseModel):
    """Pre-execution validation result for a plan.

    Returned by POST /plans/{plan_id}/validate and used internally
    by execute_plan() to block execution when errors are found.
    """

    valid: bool = Field(..., description="True if no blocking errors were found")
    errors: list[str] = Field(default_factory=list, description="Blocking validation errors")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings")
    node_issues: list[dict] = Field(
        default_factory=list,
        description="Per-node issues: [{node_id, agent, issues: [str]}]",
    )

class PlanResponse(BaseModel):
    """Plan details response.

    Status lifecycle (per prior decision 03-02):
    - draft: Initial state, can be modified
    - approved: Reviewed and ready for execution
    - executing: Currently running
    - completed: Successfully finished
    - failed: Terminated with error
    - cancelled: Manually cancelled by user

    Valid transitions:
    - draft -> approved, executing, cancelled
    - approved -> executing, cancelled
    - executing -> completed, failed
    - failed -> draft (retry), cancelled
    - cancelled -> draft (retry)
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "conversation_id": "conv_abc123",
                "user_id": "user_123",
                "name": "Research and Summarize",
                "description": "Research a topic and create a summary",
                "nodes": [{"id": "research", "agent": "research", "task": "Research AI trends"}],
                "edges": [],
                "reasoning": "User requested research task",
                "confidence": 0.85,
                "plan_json": {"nodes": [], "edges": []},
                "estimated_cost": 0.0,
                "approved_at": None,
                "completed_at": None,
                "status": "completed",
                "created_at": "2026-01-14T10:00:00Z",
                "updated_at": "2026-01-14T10:05:00Z",
                "execution_count": 3,
            }
        },
    )

    id: int = Field(..., description="Unique plan identifier (auto-generated)")
    conversation_id: str = Field(..., description="Associated conversation ID")
    user_id: str | None = Field(None, description="User ID who created this plan")
    name: str = Field(..., description="Plan name (1-200 characters)")
    description: str | None = Field(None, description="Human-readable plan description")
    nodes: list[dict[str, Any]] = Field(..., description="List of plan nodes with tasks and agents")
    edges: list[dict[str, Any]] = Field(..., description="List of edges defining execution order")
    reasoning: str | None = Field(None, description="LLM reasoning for plan generation")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    plan_json: dict[str, Any] | None = Field(
        default=None, description="Wrapper for nodes/edges for UI contract"
    )
    estimated_cost: float | None = Field(None, ge=0.0, description="Estimated cost if available")
    approved_at: str | None = Field(None, description="ISO timestamp when plan was approved")
    completed_at: str | None = Field(None, description="ISO timestamp when plan completed")
    status: PlanStatus = Field(
        ..., description="Plan status: draft, approved, executing, completed, failed, cancelled"
    )
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last modification timestamp")
    execution_count: int = Field(0, ge=0, description="Number of times this plan has been executed")
    ai_generated: bool = Field(False, description="Whether this plan was AI-generated")

class PlanNodeResultResponse(BaseModel):
    """Per-node execution result within a plan run."""

    node_id: str = Field(..., description="Plan node ID")
    status: PlanNodeStatus = Field(
        ..., description="Node status: pending, executing, completed, failed, skipped"
    )
    output: str | None = Field(None, description="Node output (may be truncated)")
    error: str | None = Field(None, description="Error message if the node failed")
    duration_ms: float | None = Field(None, ge=0, description="Execution duration in ms")
    agent: str | None = Field(None, description="Agent name (if applicable)")
    task: str | None = Field(None, description="Task description (may be truncated)")

class ExecutionResultResponse(BaseModel):
    """Plan execution result response.

    Tracks execution progress and outcomes for each plan run.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 42,
                "plan_id": 1,
                "execution_id": "exec_abc123",
                "start_time": "2026-01-14T10:00:00Z",
                "end_time": "2026-01-14T10:02:30Z",
                "status": "completed",
                "node_results": [
                    {"node_id": "research", "status": "completed", "output": "Found 5 trends..."}
                ],
                "total_cost": 0.0035,
                "user_feedback_rating": 5,
                "user_feedback_comment": "Great results!",
                "created_at": "2026-01-14T10:00:00Z",
            }
        },
    )

    id: int = Field(..., description="Unique execution result identifier")
    plan_id: int = Field(..., description="ID of the executed plan")
    execution_id: str = Field(..., description="UUID for this specific execution run")
    start_time: str = Field(..., description="ISO 8601 timestamp when execution started")
    end_time: str | None = Field(
        None, description="ISO 8601 timestamp when execution completed. Null while running"
    )
    status: PlanExecutionStatus = Field(
        ..., description="Execution status: executing, completed, failed, cancelled, timeout"
    )
    node_results: list[PlanNodeResultResponse] = Field(
        ..., description="Per-node execution results in completion order"
    )
    total_cost: float | None = Field(None, ge=0, description="Total execution cost in USD")
    user_feedback_rating: int | None = Field(
        None, ge=1, le=5, description="User rating (1-5) if feedback provided"
    )
    user_feedback_comment: str | None = Field(None, description="User feedback comment if provided")
    created_at: str = Field(..., description="ISO 8601 record creation timestamp")

class PlanListResponse(BaseModel):
    """Paginated list of plans response.

    Pagination follows prior decision 03-03: max 100 items, offset-based.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plans": [{"id": 1, "name": "Research Plan", "status": "completed"}],
                "total": 42,
                "offset": 0,
                "limit": 50,
                "has_more": False,
            }
        }
    )

    plans: list[PlanResponse] = Field(..., description="List of plans for current page")
    items: list[PlanResponse] | None = Field(
        default=None, description="Alias for plans (frontend contract)"
    )
    total: int = Field(..., ge=0, description="Total count of plans matching filters")
    offset: int = Field(..., ge=0, description="Number of items skipped (0-based)")
    limit: int = Field(..., ge=1, le=100, description="Maximum items per page")
    has_more: bool = Field(False, description="True if more items exist beyond current page")

class ExecutionListResponse(BaseModel):
    """Paginated list of execution results."""

    executions: list[ExecutionResultResponse] = Field(..., description="List of execution results")
    total: int = Field(..., ge=0, description="Total count of executions")
    has_more: bool = Field(False, description="True if more items exist")

# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/plans",
    response_model=PlanListResponse,
    summary="List execution plans",
    description="List execution plans with optional filters and pagination. Max 100 items per page.",
    responses=response_with_errors(400, 401, 500),
)
async def list_plans(
    conversation_id: str | None = Query(None, description="Filter by conversation ID"),
    status: PlanStatus | None = Query(
        None,
        description="Filter by status (draft, approved, executing, completed, failed, cancelled)",
    ),
    ai_generated: bool | None = Query(None, description="Filter by AI-generated flag"),
    limit: int = Query(50, ge=1, le=100, description="Maximum plans to return (1-100)"),
    offset: int = Query(0, ge=0, description="Number of plans to skip for pagination"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List execution plans with optional filters and pagination.

    Returns paginated list ordered by created_at DESC (most recent first).
    Users see only their own plans. Admins see all.

    **Query Parameters:**
    - **conversation_id**: Filter by associated conversation
    - **status**: Filter by plan status (6 states per prior decision 03-02)
    - **limit**: Max results per page (1-100, default: 50)
    - **offset**: Pagination offset (default: 0)

    **Returns:**
    - **200**: Paginated list of plans with execution counts
    - **400**: Invalid parameters (limit > 100)
    - **401**: Not authenticated
    """
    try:
        user_id = user.get("sub")

        # Build query - filter by owner unless admin
        query = db.query(ExecutionPlan)
        if user.get("role") != "admin":
            query = query.filter(ExecutionPlan.user_id == user_id)

        # Apply additional filters
        if conversation_id:
            query = query.filter(ExecutionPlan.conversation_id == conversation_id)
        if status:
            query = query.filter(ExecutionPlan.status == status)
        if ai_generated is not None:
            query = query.filter(ExecutionPlan.ai_generated == ai_generated)

        # Get total count before pagination
        total = query.count()

        # Order by most recent first and apply pagination
        plans = query.order_by(ExecutionPlan.created_at.desc()).offset(offset).limit(limit).all()

        # Build response with execution counts
        result = []
        for plan in plans:
            plan_dict = {
                "id": plan.id,
                "conversation_id": plan.conversation_id,
                "user_id": plan.user_id,
                "name": plan.name,
                "description": plan.description,
                "nodes": plan.nodes,
                "edges": plan.edges,
                "plan_json": {"nodes": plan.nodes or [], "edges": plan.edges or []},
                "reasoning": plan.reasoning,
                "confidence": plan.confidence,
                "estimated_cost": None,
                "approved_at": None,
                "completed_at": None,
                "status": plan.status,
                "created_at": plan.created_at.isoformat() if plan.created_at else None,
                "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
                "execution_count": len(plan.execution_results) if plan.execution_results else 0,
                "ai_generated": plan.ai_generated if hasattr(plan, "ai_generated") else False,
            }
            result.append(plan_dict)

        # Compute has_more for pagination
        has_more = (offset + len(result)) < total

        return {
            "plans": result,
            "items": result,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing plans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list plans: {str(e)}") from e

@router.post(
    "/plans",
    response_model=PlanResponse,
    status_code=201,
    summary="Create execution plan",
    description="Create a new execution plan for multi-agent task orchestration.",
    responses=response_with_errors(400, 404, 500),
)
def create_plan(
    request: CreatePlanRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create and save a new execution plan.

    Creates a plan in draft status by default. The plan must be associated with
    an existing conversation.

    **Returns:**
    - **201**: Plan created successfully
    - **400**: Invalid plan data or constraint violation
    - **401**: Not authenticated
    - **404**: Conversation not found
    """
    try:
        user_id = user.get("sub")

        # Validate conversation exists
        conversation = db.query(Conversation).filter_by(id=request.conversation_id).first()
        if not conversation:
            raise HTTPException(
                status_code=404, detail=f"Conversation {request.conversation_id} not found"
            )

        # Validate agent names if nodes provided
        if request.nodes:
            invalid_agents = _validate_plan_agents(request.nodes)
            if invalid_agents:
                from core.adapters import list_agents

                available = [c.name for c in list_agents()]
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agent(s): {', '.join(invalid_agents)}. Available agents: {available}",
                )

            # Validate step references
            ref_errors = _validate_step_references(request.nodes)
            if ref_errors:
                raise HTTPException(
                    status_code=400, detail=f"Invalid step references: {'; '.join(ref_errors)}"
                )

        # Create plan -- normalize edges to canonical source/target format
        plan = ExecutionPlan(
            conversation_id=request.conversation_id,
            user_id=user_id or request.user_id or conversation.user_id,
            name=request.name,
            description=request.description,
            nodes=request.nodes,
            edges=_normalize_edges(request.edges),
            reasoning=request.reasoning,
            confidence=request.confidence,
            status=request.status,
            ai_generated=request.ai_generated,
        )

        db.add(plan)
        db.commit()
        db.refresh(plan)

        logger.info(
            f"Created plan {plan.id} '{plan.name}' for conversation {request.conversation_id}"
        )

        return {
            "id": plan.id,
            "conversation_id": plan.conversation_id,
            "user_id": plan.user_id,
            "name": plan.name,
            "description": plan.description,
            "nodes": plan.nodes,
            "edges": plan.edges,
            "plan_json": {"nodes": plan.nodes or [], "edges": plan.edges or []},
            "reasoning": plan.reasoning,
            "confidence": plan.confidence,
            "estimated_cost": None,
            "approved_at": None,
            "completed_at": None,
            "status": plan.status,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
            "execution_count": 0,
            "ai_generated": plan.ai_generated,
        }

    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating plan: {e}")
        raise HTTPException(
            status_code=400, detail="Invalid plan data or constraint violation"
        ) from e
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create plan: {str(e)}") from e

class GeneratePlanRequest(BaseModel):
    """Request to generate an execution plan from natural language."""

    prompt: str = Field(..., description="Natural language description of desired workflow")
    conversation_id: str | None = Field(None, description="Conversation ID to associate plan with")
    plan_id: int | None = Field(None, description="Existing plan ID for refinement (optional)")

class GeneratePlanResponse(BaseModel):
    """Response from plan generation - either a plan or clarification request.

    When the LLM needs more information to generate a plan, it returns
    clarification questions instead of a plan. The frontend should display
    these questions and allow the user to respond.
    """

    type: Literal["plan", "clarification"] = Field(
        ...,
        description="Response type: 'plan' if generation succeeded, 'clarification' if questions needed",
    )
    plan: PlanResponse | None = Field(None, description="Generated plan (when type='plan')")
    questions: list[str] | None = Field(
        None,
        description="Clarifying questions referencing available agents (when type='clarification')",
    )
    context: str | None = Field(
        None,
        description="Brief explanation of what the planner understands (when type='clarification')",
    )

@router.post(
    "/plans/generate",
    response_model=GeneratePlanResponse,
    status_code=201,
    summary="Generate execution plan from prompt",
    description="Use AI to generate an execution plan from natural language description. May return clarification questions if the request is ambiguous. Returns 503 if the LLM backend is unreachable.",
    responses=response_with_errors(400, 500, 503),
)
async def generate_plan(
    request: GeneratePlanRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate an execution plan using AI.

    Takes a natural language prompt and generates an optimal execution plan
    with appropriate agents and tasks. The generated plan is automatically
    marked as ai_generated=true.

    If the request is ambiguous, returns clarification questions that reference
    available agents by name, asking about specific parameters (file paths,
    formats, scope) rather than capability existence.

    **Returns:**
    - **201**: Plan generated and saved (type='plan'), or clarification needed (type='clarification')
    - **400**: Invalid prompt or generation failed
    """
    try:
        from core.clarification import ClarificationRequest
        from core.orchestrator.planner import LLMUnavailableError, generate_execution_plan

        user_id = user.get("sub")

        # Build context with conversation history (for multi-turn clarification)
        context = None
        if request.conversation_id:
            messages = (
                db.query(Message)
                .filter_by(conversation_id=request.conversation_id)
                .order_by(Message.created_at)
                .all()
            )
            if messages:
                context = {"history": [{"role": m.role, "content": m.content} for m in messages]}
                logger.info(f"Including {len(messages)} messages from conversation history")

        # Generate plan using the planner (with conversation context for multi-turn)
        generated = await generate_execution_plan(request.prompt, context)

        # Check if planner needs clarification
        if isinstance(generated, ClarificationRequest):
            logger.info(f"Planner requests clarification: {len(generated.questions)} questions")
            return GeneratePlanResponse(
                type="clarification",
                questions=generated.questions,
                context=generated.context,
            )

        # Handle dict returns from clarification plugin (form schema)
        if isinstance(generated, dict):
            logger.info(f"Planner returned plugin clarification form: {list(generated.keys())}")
            return GeneratePlanResponse(
                type="clarification",
                questions=generated.get("questions", []),
                context=generated.get("context", "Clarification needed before plan generation."),
            )

        # Convert nodes' depends_on to edges format
        # The planner's ExecutionPlan uses nodes[].depends_on, but the database model uses edges
        edges = [
            {"source": dep, "target": node.id}
            for node in generated.nodes
            for dep in node.depends_on
        ]

        # Create or get conversation
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                title=f"Generated: {request.prompt[:50]}...",
                mode="planner",
            )
            db.add(conversation)
            db.flush()
        else:
            conversation = db.query(Conversation).filter_by(id=conversation_id).first()
            if not conversation:
                raise HTTPException(
                    status_code=404, detail=f"Conversation {conversation_id} not found"
                )

        # If refining an existing plan, update it
        if request.plan_id:
            existing_plan = db.query(ExecutionPlan).filter_by(id=request.plan_id).first()
            if existing_plan and (user.get("role") == "admin" or existing_plan.user_id == user_id):
                existing_plan.name = generated.name
                existing_plan.description = generated.description
                existing_plan.nodes = [n.model_dump() for n in generated.nodes]
                existing_plan.edges = edges
                existing_plan.reasoning = generated.reasoning
                existing_plan.confidence = generated.confidence
                existing_plan.updated_at = datetime.now(UTC)
                db.commit()
                db.refresh(existing_plan)
                plan = existing_plan
            else:
                raise HTTPException(
                    status_code=404, detail=f"Plan {request.plan_id} not found or access denied"
                )
        else:
            # Create new plan with ai_generated=true
            plan = ExecutionPlan(
                conversation_id=conversation_id,
                user_id=user_id,
                name=generated.name,
                description=generated.description,
                nodes=[n.model_dump() for n in generated.nodes],
                edges=edges,
                reasoning=generated.reasoning,
                confidence=generated.confidence,
                status="draft",
                ai_generated=True,  # Always true for generated plans
            )
            db.add(plan)
            db.commit()
            db.refresh(plan)

        logger.info(f"Generated plan {plan.id} from prompt: {request.prompt[:50]}...")

        # Wrap plan response in GeneratePlanResponse with type='plan'
        plan_response = {
            "id": plan.id,
            "conversation_id": plan.conversation_id,
            "user_id": plan.user_id,
            "name": plan.name,
            "description": plan.description,
            "nodes": plan.nodes,
            "edges": plan.edges,
            "plan_json": {"nodes": plan.nodes or [], "edges": plan.edges or []},
            "reasoning": plan.reasoning,
            "confidence": plan.confidence,
            "estimated_cost": None,
            "approved_at": None,
            "completed_at": None,
            "status": plan.status,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
            "execution_count": 0,
            "ai_generated": plan.ai_generated,
        }

        return GeneratePlanResponse(
            type="plan",
            plan=plan_response,
        )

    except HTTPException:
        raise
    except LLMUnavailableError as e:
        db.rollback()
        logger.error(f"LLM unavailable during plan generation: {e}")
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate plan: {str(e)}") from e

def cleanup_old_draft_plans(db: Session, retention_days: int = 30) -> int:
    """Delete draft plans older than retention_days.

    Only deletes plans in 'draft' status. Approved, completed, and other
    statuses are preserved indefinitely.

    Returns count of deleted plans.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    old_drafts = (
        db.query(ExecutionPlan)
        .filter(
            ExecutionPlan.status == "draft",
            ExecutionPlan.created_at < cutoff,
        )
        .all()
    )
    count = len(old_drafts)
    for plan in old_drafts:
        db.delete(plan)
    if count > 0:
        db.commit()
        logger.info(f"Cleaned up {count} draft plans older than {retention_days} days")
    return count

@router.post(
    "/plans/cleanup",
    summary="Cleanup old draft plans",
    description="Delete draft plans older than the configured retention period. Admin only.",
    responses=response_with_errors(403, 500),
)
def cleanup_plans(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    retention_days: int = Query(30, description="Days to retain draft plans"),
):
    """Cleanup old draft plans. Admin only.

    Deletes draft plans older than the specified retention period.
    Only plans in 'draft' status are affected -- approved, completed,
    and other statuses are preserved indefinitely.

    **Query Parameters:**
    - **retention_days**: Number of days to retain drafts (default: 30)

    **Returns:**
    - **200**: Cleanup summary with deleted count
    - **403**: Admin access required
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    count = cleanup_old_draft_plans(db, retention_days)
    return {"deleted": count, "retention_days": retention_days}

@router.get(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Get plan by ID",
    description="Get execution plan details including nodes, edges, and execution count.",
    responses=response_with_errors(401, 403, 404, 500),
)
async def get_plan(
    plan_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get plan details by ID.

    Returns full plan details including execution count.
    Users can only access their own plans. Admins can access all.

    **Returns:**
    - **200**: Plan details with execution count
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan not found
    """
    try:
        user_id = user.get("sub")

        # Query plan with execution results loaded
        plan = (
            db.query(ExecutionPlan)
            .options(joinedload(ExecutionPlan.execution_results))
            .filter_by(id=plan_id)
            .first()
        )

        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # Ownership check
        if user.get("role") != "admin" and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        return {
            "id": plan.id,
            "conversation_id": plan.conversation_id,
            "user_id": plan.user_id,
            "name": plan.name,
            "description": plan.description,
            "nodes": plan.nodes,
            "edges": plan.edges,
            "plan_json": {"nodes": plan.nodes or [], "edges": plan.edges or []},
            "reasoning": plan.reasoning,
            "confidence": plan.confidence,
            "estimated_cost": None,
            "approved_at": None,
            "completed_at": None,
            "status": plan.status,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
            "execution_count": len(plan.execution_results) if plan.execution_results else 0,
            "ai_generated": plan.ai_generated if hasattr(plan, "ai_generated") else False,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get plan: {str(e)}") from e

@router.put(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Update plan",
    description="Update an existing plan. Only modifiable plans (draft, approved, failed, cancelled) can be updated.",
    responses=response_with_errors(400, 403, 404, 500),
)
def update_plan(
    plan_id: int,
    request: UpdatePlanRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing plan.

    Only plans in modifiable states can be updated. Plans in executing or completed
    status are immutable.

    **Returns:**
    - **200**: Updated plan details
    - **400**: Invalid status transition or plan is immutable
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan not found
    """
    try:
        user_id = user.get("sub")

        # Get plan
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # Ownership check with admin bypass
        if user.get("role") != "admin" and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Don't allow modification of executing/completed plans
        # Exception: allow status-only transitions (cancel, approve) from executing
        is_status_only = (
            request.status is not None
            and request.name is None
            and request.description is None
            and request.nodes is None
            and request.edges is None
            and request.reasoning is None
            and request.confidence is None
        )
        if plan.status in ["executing", "completed"] and not is_status_only:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot modify plan in '{plan.status}' status. Only draft, approved, failed, or cancelled plans can be modified.",
            )
        # Completed plans cannot have their status changed (terminal state)
        if plan.status == "completed" and request.status is not None:
            raise HTTPException(
                status_code=400,
                detail="Cannot change status of a completed plan.",
            )

        # Validate agent names and step references when nodes are updated
        if request.nodes is not None:
            invalid_agents = _validate_plan_agents(request.nodes)
            if invalid_agents:
                from core.adapters import list_agents

                available = [c.name for c in list_agents()]
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agent(s): {', '.join(invalid_agents)}. Available agents: {available}",
                )

            ref_errors = _validate_step_references(request.nodes)
            if ref_errors:
                raise HTTPException(
                    status_code=400, detail=f"Invalid step references: {'; '.join(ref_errors)}"
                )

        # Update fields
        if request.name is not None:
            plan.name = request.name
        if request.description is not None:
            plan.description = request.description
        if request.nodes is not None:
            plan.nodes = request.nodes
        if request.edges is not None:
            plan.edges = _normalize_edges(request.edges)
        if request.reasoning is not None:
            plan.reasoning = request.reasoning
        if request.confidence is not None:
            plan.confidence = request.confidence
        if request.status is not None:
            plan.status = request.status

        plan.updated_at = datetime.now(UTC)

        db.commit()
        db.refresh(plan)

        logger.info(f"Updated plan {plan_id}")

        return {
            "id": plan.id,
            "conversation_id": plan.conversation_id,
            "user_id": plan.user_id,
            "name": plan.name,
            "description": plan.description,
            "nodes": plan.nodes,
            "edges": plan.edges,
            "plan_json": {"nodes": plan.nodes or [], "edges": plan.edges or []},
            "reasoning": plan.reasoning,
            "confidence": plan.confidence,
            "estimated_cost": None,
            "approved_at": None,
            "completed_at": None,
            "status": plan.status,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
            "execution_count": len(plan.execution_results) if plan.execution_results else 0,
            "ai_generated": plan.ai_generated if hasattr(plan, "ai_generated") else False,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update plan: {str(e)}") from e

@router.delete(
    "/plans/{plan_id}",
    status_code=204,
    summary="Delete plan",
    description="Delete a plan. Cannot delete plans that are currently executing.",
    responses=response_with_errors(400, 403, 404, 500),
)
def delete_plan(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a plan.

    Plans currently executing cannot be deleted. Use cancel first.

    **Returns:**
    - **204**: Plan deleted (no content)
    - **400**: Cannot delete executing plan
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan not found
    """
    try:
        user_id = user.get("sub")

        # Get plan
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # Ownership check with admin bypass
        if user.get("role") != "admin" and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Don't allow deletion of executing plans
        if plan.status == "executing":
            raise HTTPException(
                status_code=400, detail="Cannot delete plan that is currently executing"
            )

        db.delete(plan)
        db.commit()

        logger.info(f"Deleted plan {plan_id}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete plan: {str(e)}") from e

# ============================================================================
# Background Plan Execution
# ============================================================================

def _topological_sort(nodes: list[dict], edges: list[dict]) -> tuple[list[str], list[str]]:
    """Sort nodes by dependencies (topological order).

    Uses Kahn's algorithm to determine execution order based on dependencies.
    Detects cycles by checking if all nodes were included in the sorted output.

    Args:
        nodes: List of node dicts with 'id' field
        edges: List of edge dicts with 'from'/'source' and 'to'/'target' fields

    Returns:
        Tuple of (sorted_node_ids, dropped_node_ids).
        dropped_node_ids contains nodes involved in cycles that could not be
        topologically sorted.  Empty list when the graph is acyclic.
    """
    # Build adjacency list and in-degree counts
    graph = {n.get("id"): [] for n in nodes}
    in_degree = {n.get("id"): 0 for n in nodes}

    for edge in edges:
        # Dual-read: source/target (canonical) + from/to (legacy) for backward compat
        source = edge.get("source") or edge.get("from")
        target = edge.get("target") or edge.get("to")
        if source in graph and target in in_degree:
            graph[source].append(target)
            in_degree[target] += 1

    # Kahn's algorithm
    queue = [n for n, d in in_degree.items() if d == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # GAP-P10: Detect cycles -- nodes not in result are involved in cycles
    all_ids = {n.get("id") for n in nodes}
    dropped = list(all_ids - set(result))
    if dropped:
        logger.warning(
            f"Cycle detected: nodes {dropped} dropped from execution order. "
            f"These nodes have circular dependencies and will be skipped."
        )

    return result, dropped

def _resolve_step_references(arguments: dict[str, Any], results: dict[str, str]) -> dict[str, Any]:
    """Resolve step output references in argument values.

    Supports patterns like:
    - ``"{{step_1}}"`` -- replaced with full output from step_1
    - ``"{{step_1.session_id}}"`` -- extracted from JSON output of step_1

    Non-string values and strings without ``{{...}}`` are passed through
    unchanged.  If a referenced step has no result or the JSON path
    doesn't exist, the original placeholder string is left intact so the
    caller can report a meaningful error.

    Args:
        arguments: Dict of argument name to value (may contain ``{{...}}``).
        results: Dict of step_id to output string from previous steps.

    Returns:
        New dict with resolved values.
    """
    ref_pattern = re.compile(r"\{\{(\w+)(?:\.(\w+))?\}\}")
    resolved: dict[str, Any] = {}

    for key, value in arguments.items():
        if not isinstance(value, str):
            resolved[key] = value
            continue

        match = ref_pattern.fullmatch(value.strip())
        if not match:
            resolved[key] = value
            continue

        step_id = match.group(1)
        json_field = match.group(2)
        step_output = results.get(step_id)

        if step_output is None:
            # Referenced step hasn't produced output yet
            resolved[key] = value
            continue

        if json_field:
            # Try to extract a field from JSON output
            try:
                parsed = json.loads(step_output)
                if isinstance(parsed, dict) and json_field in parsed:
                    resolved[key] = parsed[json_field]
                else:
                    resolved[key] = step_output
            except (json.JSONDecodeError, TypeError):
                resolved[key] = step_output
        else:
            resolved[key] = step_output

    return resolved

def _mark_execution_failed(execution_id: str, error_message: str) -> None:
    """Mark an execution as failed in the database.

    Helper function to ensure executions don't get stuck in 'executing' state.
    """
    from core.database.session import get_session

    try:
        with get_session() as db:
            execution_result = (
                db.query(PlanExecutionResult).filter_by(execution_id=execution_id).first()
            )
            if execution_result:
                execution_result.end_time = datetime.now(UTC)
                execution_result.status = "failed"
                execution_result.node_results = [
                    {
                        "node_id": "system",
                        "agent": None,
                        "task": "System",
                        "status": "failed",
                        "output": "",
                        "error": error_message,
                        "duration_ms": 0,
                    }
                ]
                db.commit()
                logger.info(
                    f"[PLAN_EXEC] Marked execution {execution_id} as failed: {error_message}"
                )

                # Also update plan status
                if execution_result.plan_id:
                    plan = db.query(ExecutionPlan).filter_by(id=execution_result.plan_id).first()
                    if plan and plan.status == "executing":
                        plan.status = "failed"
                        plan.updated_at = datetime.now(UTC)
                        db.commit()
    except Exception as e:
        logger.error(f"[PLAN_EXEC] Failed to mark execution as failed: {e}")

def _normalize_edges(edges: list[dict]) -> list[dict]:
    """Normalize edge format to source/target (canonical).

    Accepts edges in any combination of source/target, from/to, or from_node/to_node
    formats and normalizes them to the canonical source/target format for DB storage.
    """
    normalized = []
    for edge in edges:
        normalized.append(
            {
                "source": edge.get("source") or edge.get("from") or edge.get("from_node", ""),
                "target": edge.get("target") or edge.get("to") or edge.get("to_node", ""),
            }
        )
    return normalized

def _validate_plan_agents(nodes: list[dict]) -> list[str]:
    """Validate agent names in plan nodes against the agent registry.

    Uses _resolve_agent_name() for fuzzy matching to avoid rejecting
    names that would successfully resolve at execution time.

    Returns list of completely unresolvable agent names (empty if all valid).
    """
    unresolvable = []
    for node in nodes:
        agent_name = node.get("agent")
        if not agent_name:
            continue
        _resolved_name, agent = _resolve_agent_name(agent_name)
        if agent is None:
            unresolvable.append(agent_name)
    return unresolvable

def _validate_step_references(nodes: list[dict]) -> list[str]:
    """Validate {{step_ref}} patterns reference existing node IDs.

    Checks that all {{step_id}} and {{step_id.field}} patterns in node
    arguments reference actual node IDs in the plan.

    Returns list of error messages (empty if all valid).
    """
    ref_pattern = re.compile(r"\{\{(\w+)(?:\.\w+)?\}\}")
    node_ids = {n.get("id") for n in nodes}
    errors = []

    for node in nodes:
        arguments = node.get("arguments", {})
        if not isinstance(arguments, dict):
            continue
        for key, value in arguments.items():
            if not isinstance(value, str):
                continue
            for match in ref_pattern.finditer(value):
                step_id = match.group(1)
                if step_id not in node_ids:
                    errors.append(
                        f"Node '{node.get('id')}' references unknown step '{{{{{step_id}}}}}' in argument '{key}'"
                    )
    return errors

def _resolve_agent_name(agent_name: str) -> tuple[str, "UniversalAgent | None"]:
    """Resolve an agent name with fuzzy matching fallback.

    The LLM planner may produce agent names that don't exactly match the
    registry (e.g. ``"server.tools"`` instead of ``"mcp-server"``).
    This function tries:

    1. Exact match
    2. Normalized match (lowercase, replace ``.`` with ``_`` / ``-``)
    3. Substring containment match
    4. Prefix "mcp-" match (``"server"`` -> ``"mcp-server"``)

    Returns:
        Tuple of (resolved_name, agent_or_None).
    """
    from core.adapters import get_agent, list_agents

    # 1. Exact match
    agent = get_agent(agent_name)
    if agent:
        return agent_name, agent

    # Build lookup table of registered agents
    all_cards = list_agents()
    registry_names = [card.name for card in all_cards]

    # Normalise the requested name for fuzzy comparison
    normalised = agent_name.lower().replace(".", "_").replace("-", "_")

    # 2. Normalized match
    for registered in registry_names:
        if registered.lower().replace(".", "_").replace("-", "_") == normalised:
            logger.info(f"[PLAN_EXEC] Fuzzy resolved '{agent_name}' -> '{registered}' (normalised)")
            return registered, get_agent(registered)

    # 3. Substring containment (e.g. "server.tools" contains "server")
    #    Pick the best match by longest overlap
    best_match: str | None = None
    best_score = 0
    for registered in registry_names:
        reg_norm = registered.lower().replace("-", "_")
        # Check if normalised name contains the registered name or vice versa
        if reg_norm in normalised or normalised in reg_norm:
            score = len(reg_norm)
            if score > best_score:
                best_score = score
                best_match = registered

    if best_match:
        logger.info(f"[PLAN_EXEC] Fuzzy resolved '{agent_name}' -> '{best_match}' (substring)")
        return best_match, get_agent(best_match)

    # 4. Try with "mcp-" prefix
    mcp_name = f"mcp-{agent_name.split('.')[-1]}"
    agent = get_agent(mcp_name)
    if agent:
        logger.info(f"[PLAN_EXEC] Fuzzy resolved '{agent_name}' -> '{mcp_name}' (mcp prefix)")
        return mcp_name, agent

    logger.warning(
        f"[PLAN_EXEC] Could not resolve agent '{agent_name}'. Available agents: {registry_names}"
    )
    return agent_name, None

def _validate_plan_for_execution(
    nodes: list[dict[str, Any]],
) -> "PlanValidationResult":
    """Pre-flight validation of plan nodes before execution.

    Checks:
    1. Agent existence (via fuzzy matching)
    2. MCP tool existence on the server (if node specifies "tool")
    3. Required tool arguments present (from inputSchema.required)
    4. Warns when MCP nodes lack an explicit tool field

    Returns a PlanValidationResult with errors and warnings.
    """
    from core.mcp.registry import get_registry

    errors: list[str] = []
    warnings: list[str] = []
    node_issues: list[dict] = []

    for node in nodes:
        node_id = node.get("id", "unknown")
        agent_name = node.get("agent", "")
        issues: list[str] = []

        # 1. Check agent existence
        _resolved_name, agent = _resolve_agent_name(agent_name)
        if agent is None:
            issues.append(f"Agent '{agent_name}' not found in registry")
            errors.append(f"Node '{node_id}': agent '{agent_name}' not found")
        else:
            # 2. MCP-specific checks
            is_mcp = agent_name.startswith("mcp-") or _resolved_name.startswith("mcp-")
            if is_mcp:
                node_tool = node.get("tool")
                node_arguments = node.get("arguments", {})
                server_name = _resolved_name.removeprefix("mcp-")

                if node_tool:
                    # Check tool exists on the server
                    try:
                        registry = get_registry()
                        if registry.is_registered(server_name):
                            server_tools = registry.list_tools(server_name)
                            tool_map = {t.name: t for t in server_tools}
                            if node_tool not in tool_map:
                                tool_names = [t.name for t in server_tools]
                                issues.append(
                                    f"Tool '{node_tool}' not found on server '{server_name}'. "
                                    f"Available: {tool_names}"
                                )
                                errors.append(
                                    f"Node '{node_id}': tool '{node_tool}' not found on MCP server '{server_name}'"
                                )
                            else:
                                # Check required arguments
                                tool_def = tool_map[node_tool]
                                required = tool_def.inputSchema.required
                                if required:
                                    provided = (
                                        set(node_arguments.keys())
                                        if isinstance(node_arguments, dict)
                                        else set()
                                    )
                                    missing = [p for p in required if p not in provided]
                                    if missing:
                                        issues.append(
                                            f"Tool '{node_tool}' missing required arguments: {missing}"
                                        )
                                        errors.append(
                                            f"Node '{node_id}': tool '{node_tool}' missing required arguments: {missing}"
                                        )
                        else:
                            warnings.append(
                                f"Node '{node_id}': MCP server '{server_name}' not registered "
                                "(may become available before execution)"
                            )
                    except Exception as e:
                        warnings.append(
                            f"Node '{node_id}': could not validate MCP tool '{node_tool}' "
                            f"on server '{server_name}': {e}"
                        )
                else:
                    # MCP agent without explicit tool
                    warnings.append(
                        f"Node '{node_id}': MCP agent '{agent_name}' has no explicit 'tool' field. "
                        "Execution will rely on task-description matching (may fail)."
                    )

        if issues:
            node_issues.append(
                {
                    "node_id": node_id,
                    "agent": agent_name,
                    "issues": issues,
                }
            )

    return PlanValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        node_issues=node_issues,
    )

def _update_node_result_in_db(execution_id: str, node_result: dict[str, Any]) -> None:
    """Persist a single node result to the database incrementally.

    Appends *node_result* to the ``node_results`` JSON array on the
    ``PlanExecutionResult`` row identified by *execution_id*.  This
    enables the frontend to see per-node progress during plan execution
    instead of waiting for all nodes to finish.
    """
    from core.database.session import get_session

    try:
        with get_session() as db:
            execution = db.query(PlanExecutionResult).filter_by(execution_id=execution_id).first()
            if execution:
                current = execution.node_results or []
                current.append(node_result)
                execution.node_results = current
                # SQLAlchemy may not detect in-place JSON mutation -- force flag
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(execution, "node_results")
                db.commit()
    except Exception as e:
        logger.warning(f"[PLAN_EXEC] Failed to persist node result incrementally: {e}")

async def _execute_plan_background(
    plan_id: int,
    execution_id: str,
    user_id: str | None,
) -> None:
    """Background task to execute a plan.

    Loads the plan from database, executes nodes in topological order,
    and updates the PlanExecutionResult with per-node results.

    Args:
        plan_id: Database ID of the plan to execute
        execution_id: UUID for this execution run
        user_id: Optional user ID for context
    """
    from core.database.session import get_session

    logger.info(f"[PLAN_EXEC] Starting background execution {execution_id} for plan {plan_id}")

    from core.auth.audit import log_audit_sync

    node_results = []
    results = {}
    execution_start = time()
    final_status = "completed"

    try:
        # Load plan from database
        with get_session() as db:
            plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
            if not plan:
                logger.error(f"[PLAN_EXEC] Plan {plan_id} not found")
                # Mark execution as failed since plan doesn't exist
                _mark_execution_failed(execution_id, "Plan not found")
                return

            # Extract plan data while session is open
            plan_name = plan.name
            nodes = plan.nodes or []
            edges = plan.edges or []

        logger.info(f"[PLAN_EXEC] Loaded plan '{plan_name}' with {len(nodes)} nodes")

        try:
            log_audit_sync(None, user_id or "", "plan_execution_started", "plan", str(plan_id),
                           metadata={"execution_id": str(execution_id), "node_count": len(nodes)})
        except Exception:
            pass

        if not nodes:
            logger.warning(f"[PLAN_EXEC] Plan {plan_id} has no nodes to execute")
            final_status = "completed"
        else:
            # Compute topological sort for execution order
            node_order, dropped_nodes = _topological_sort(nodes, edges)
            logger.info(f"[PLAN_EXEC] Execution order: {' -> '.join(node_order)}")

            # Record dropped (cyclic) nodes as skipped
            if dropped_nodes:
                for dropped_id in dropped_nodes:
                    dropped_result = {
                        "node_id": dropped_id,
                        "agent": None,
                        "task": "Skipped (cycle)",
                        "status": "skipped",
                        "output": "",
                        "error": "Node dropped: involved in dependency cycle",
                        "duration_ms": 0,
                    }
                    node_results.append(dropped_result)
                    _update_node_result_in_db(execution_id, dropped_result)

            # GAP-P11: Track failed node IDs for stop-on-failure propagation
            failed_node_ids: set[str] = set()

            # Execute nodes in order
            for idx, node_id in enumerate(node_order, 1):
                node = next((n for n in nodes if n.get("id") == node_id), None)
                if not node:
                    logger.warning(f"[PLAN_EXEC] Node '{node_id}' not found, skipping")
                    continue

                # GAP-P11: Check if any upstream dependency failed -- skip downstream
                upstream_deps = [
                    e.get("source") or e.get("from")
                    for e in edges
                    if (e.get("target") or e.get("to")) == node_id
                ]
                if any(dep_id in failed_node_ids for dep_id in upstream_deps):
                    logger.info(
                        f"[PLAN_EXEC] Skipping node '{node_id}' -- upstream dependency failed"
                    )
                    skip_result = {
                        "node_id": node_id,
                        "agent": node.get("agent"),
                        "task": node.get("task", "")[:500],
                        "status": "skipped",
                        "output": "",
                        "error": "Upstream dependency failed",
                        "duration_ms": 0,
                    }
                    node_results.append(skip_result)
                    _update_node_result_in_db(execution_id, skip_result)
                    failed_node_ids.add(node_id)  # Propagate failure downstream
                    continue

                agent_name = node.get("agent")
                task = node.get("task", "")

                # Enrich task with results from dependency steps so the agent
                # knows what previous steps produced (e.g. file paths, session IDs)
                dep_ids = node.get("depends_on", [])
                dep_results = {dep: results[dep] for dep in dep_ids if dep in results}
                if dep_results:
                    dep_lines = "\n".join(
                        f"- {dep_id}: {str(val)[:500]}" for dep_id, val in dep_results.items()
                    )
                    task = f"{task}\n\nResults from previous steps:\n{dep_lines}"
                    logger.info(
                        f"[PLAN_EXEC] Enriched task with {len(dep_results)} dependency result(s)"
                    )

                logger.info(
                    f"[PLAN_EXEC] === Executing node {idx}/{len(node_order)}: {node_id} ==="
                )
                logger.info(f"[PLAN_EXEC] Agent: {agent_name}, Task: {task[:100]}...")

                try:
                    log_audit_sync(None, user_id or "", "plan_node_started", "plan_node", node_id,
                                   metadata={"agent": agent_name, "task": str(task)[:200], "plan_id": plan_id})
                except Exception:
                    pass

                node_start = time()
                node_status = "executing"
                node_output = ""
                node_error = None
                result = None  # Agent execution result (used for tool_calls metadata)

                if agent_name:
                    resolved_name, agent = _resolve_agent_name(agent_name)
                    if agent:
                        try:
                            # Include previous results and node tool/args in context
                            node_context: dict[str, Any] = {
                                "user_id": user_id,
                                "execution_id": execution_id,
                                "previous_results": results,
                            }

                            # Pass explicit tool name and arguments if defined on the node.
                            # MCPAgentAdapter.execute() checks context.get("tool") and
                            # context.get("arguments") for direct tool invocation.
                            node_tool = node.get("tool")
                            node_arguments = node.get("arguments")
                            if node_tool:
                                node_context["tool"] = node_tool
                            if node_arguments:
                                # Resolve argument references to previous step outputs.
                                # Patterns like "{{step_1}}" or "{{step_1.session_id}}"
                                # are replaced with actual values from results dict.
                                resolved_args = _resolve_step_references(node_arguments, results)
                                node_context["arguments"] = resolved_args

                            # Execute agent
                            result = await agent.execute(task, node_context)

                            if result.status == "error":
                                error_str = result.error or "Unknown agent error"
                                logger.warning(
                                    f"[PLAN_EXEC] Agent {agent_name} returned error: {error_str}"
                                )
                                results[node_id] = f"Error: {error_str}"
                                node_output = f"Error: {error_str}"
                                node_error = error_str
                                node_status = "failed"
                            else:
                                results[node_id] = result.output
                                node_output = str(result.output)[:1000]  # Limit output size

                                # Content-based refusal detection: scan output for patterns
                                # indicating the agent could not actually complete the task
                                output_lower = node_output.lower()
                                refusal_match = next(
                                    (p for p in REFUSAL_PATTERNS if p in output_lower), None
                                )
                                if refusal_match:
                                    node_status = "degraded"
                                    logger.warning(
                                        f"[PLAN_EXEC] Node '{node_id}' output matches refusal pattern "
                                        f"'{refusal_match}' -- marking as degraded"
                                    )
                                else:
                                    node_status = "completed"
                                    logger.info(
                                        f"[PLAN_EXEC] Node '{node_id}' completed successfully"
                                    )

                        except Exception as e:
                            logger.error(
                                f"[PLAN_EXEC] ✗ Node '{node_id}' exception: {e}", exc_info=True
                            )
                            error_str = str(e)
                            results[node_id] = f"Error: {error_str}"
                            node_output = f"Error: {error_str}"
                            node_error = error_str
                            node_status = "failed"
                    else:
                        from core.adapters import list_agents as _list_agents

                        available = [c.name for c in _list_agents()]
                        error_msg = (
                            f"Agent '{agent_name}' not found (tried fuzzy matching). "
                            f"Available: {available}"
                        )
                        logger.error(f"[PLAN_EXEC] ✗ {error_msg}")
                        results[node_id] = error_msg
                        node_output = error_msg
                        node_error = error_msg
                        node_status = "failed"
                else:
                    error_msg = "No agent specified for node"
                    logger.warning(f"[PLAN_EXEC] ✗ Node '{node_id}': {error_msg}")
                    results[node_id] = error_msg
                    node_output = error_msg
                    node_error = error_msg
                    node_status = "failed"

                # Record node result
                node_duration_ms = (time() - node_start) * 1000
                node_result_entry = {
                    "node_id": node_id,
                    "agent": agent_name,
                    "task": task[:500],
                    "status": node_status,
                    "output": node_output,
                    "error": node_error,
                    "duration_ms": round(node_duration_ms, 2),
                    "tool_calls": (result.metadata or {}).get("tool_calls") if result else None,
                }
                node_results.append(node_result_entry)

                # Persist this node result incrementally so the frontend
                # can show per-node progress via polling.
                _update_node_result_in_db(execution_id, node_result_entry)

                try:
                    log_audit_sync(None, user_id or "", "plan_node_completed", "plan_node", node_id,
                                   metadata={"status": node_status, "plan_id": plan_id})
                except Exception:
                    pass

                # GAP-P11: Track failed nodes for stop-on-failure propagation
                if node_status in ("failed", "degraded"):
                    failed_node_ids.add(node_id)
                    final_status = "failed"

    except Exception as e:
        logger.error(f"[PLAN_EXEC] ✗ Execution failed with exception: {e}", exc_info=True)
        final_status = "failed"
        node_results.append(
            {
                "node_id": "system",
                "agent": None,
                "task": "System execution",
                "status": "failed",
                "output": "",
                "error": str(e),
                "duration_ms": 0,
            }
        )

    # Calculate totals
    total_duration_ms = (time() - execution_start) * 1000
    failed_count = sum(1 for r in node_results if r["status"] in ("failed", "degraded"))
    if failed_count > 0:
        final_status = "failed"

    # Estimate cost ($0.01 per node)
    total_cost = len([r for r in node_results if r["node_id"] != "system"]) * 0.01

    logger.info(f"[PLAN_EXEC] Execution completed: {final_status}")
    logger.info(
        f"[PLAN_EXEC] {len(node_results)} nodes, {failed_count} failed, {total_duration_ms:.2f}ms total"
    )

    try:
        log_audit_sync(None, user_id or "", "plan_execution_completed", "plan", str(plan_id),
                       metadata={"final_status": final_status})
    except Exception:
        pass

    # Update execution result in database
    try:
        with get_session() as db:
            execution_result = (
                db.query(PlanExecutionResult).filter_by(execution_id=execution_id).first()
            )

            if execution_result:
                execution_result.end_time = datetime.now(UTC)
                execution_result.status = final_status
                execution_result.node_results = node_results
                execution_result.total_cost = total_cost
                db.commit()
                logger.info(f"[PLAN_EXEC] ✓ Updated execution result: {final_status}")
            else:
                logger.error(f"[PLAN_EXEC] Execution result not found for {execution_id}")

            # Update plan status
            plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
            if plan:
                plan.status = final_status
                plan.updated_at = datetime.now(UTC)
                db.commit()
                logger.info(f"[PLAN_EXEC] ✓ Updated plan status to: {final_status}")

    except Exception as e:
        logger.error(f"[PLAN_EXEC] Failed to update database: {e}", exc_info=True)
        # Retry once to prevent plans from getting stuck in 'executing' forever
        try:
            _mark_execution_failed(execution_id, f"Database update failed: {e}")
            logger.info(
                f"[PLAN_EXEC] Recovery: marked execution {execution_id} as failed via retry"
            )
        except Exception as retry_err:
            logger.error(f"[PLAN_EXEC] Recovery also failed: {retry_err}", exc_info=True)

def run_plan_execution_background(plan_id: int, execution_id: str, user_id: str | None):
    """Wrapper to run async plan execution in a new event loop.

    This is needed because BackgroundTasks runs in a thread pool,
    and we need an event loop for async agent execution.
    """
    asyncio.run(_execute_plan_background(plan_id, execution_id, user_id))

@router.post(
    "/plans/{plan_id}/validate",
    summary="Validate plan before execution",
    description="Pre-flight validation: checks agent availability, MCP tool existence, and required arguments.",
    response_model=PlanValidationResult,
    responses=response_with_errors(403, 404),
)
async def validate_before_execute(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate a plan before execution.

    Performs pre-flight checks:
    - Agent existence for each node
    - MCP tool existence on the target server
    - Required tool arguments are present
    - Warns when MCP nodes lack explicit tool field

    **Returns:**
    - **200**: Validation result with errors and warnings
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan not found
    """
    plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    # Ownership check with admin bypass
    user_id = user.get("sub")
    if user.get("role") != "admin" and plan.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    nodes = plan.nodes or []
    return _validate_plan_for_execution(nodes)

@router.post(
    "/plans/{plan_id}/execute",
    summary="Execute plan",
    description="Initiate execution of a saved plan. Returns execution_id for tracking.",
    responses=response_with_errors(400, 403, 404, 500),
)
async def execute_plan(
    plan_id: int,
    _request: ExecutePlanRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute a saved plan.

    Initiates plan execution and returns immediately with execution_id.
    Use GET /plans/{id}/executions to track progress.

    Only draft, approved, or failed plans can be executed.

    **Returns:**
    - **200**: Execution initiated with execution_id for tracking
    - **400**: Plan status does not allow execution
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan not found
    """
    try:
        user_id = user.get("sub")

        # Get plan
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # Ownership check with admin bypass
        if user.get("role") != "admin" and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # P1-1: Concurrent execution guard -- reject if plan is already executing
        if plan.status == "executing":
            raise HTTPException(
                status_code=409,
                detail=f"Plan {plan_id} is already executing. Wait for current execution to complete or cancel it.",
            )

        # GAP-P12: Optional approval enforcement
        require_approval = os.getenv("DRYADE_REQUIRE_PLAN_APPROVAL", "").lower() == "true"
        if require_approval and plan.status not in ("approved", "failed"):
            raise HTTPException(
                status_code=400,
                detail="Plan must be approved before execution (DRYADE_REQUIRE_PLAN_APPROVAL=true)",
            )

        # Validate plan status
        if plan.status not in ["draft", "approved", "failed"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot execute plan in '{plan.status}' status. Plan must be draft, approved, or failed.",
            )

        # Pre-execution validation: check agents, MCP tools, required arguments
        nodes = plan.nodes or []
        validation = _validate_plan_for_execution(nodes)
        if not validation.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Plan validation failed. Fix errors before executing.",
                    "validation": validation.model_dump(),
                },
            )

        # Create execution result record
        execution_id = str(uuid.uuid4())
        result = PlanExecutionResult(
            plan_id=plan.id,
            execution_id=execution_id,
            start_time=datetime.now(UTC),
            status="executing",
            node_results=[],
        )

        db.add(result)

        # Update plan status
        plan.status = "executing"
        plan.updated_at = datetime.now(UTC)

        db.commit()

        logger.info(f"Initiated execution {execution_id} for plan {plan_id}")

        # Trigger actual plan execution in background task
        # This runs the plan nodes in topological order using registered agents
        background_tasks.add_task(
            run_plan_execution_background,
            plan_id,
            execution_id,
            user_id,
        )
        logger.info(f"Queued background execution for plan {plan_id}")

        return {
            "execution_id": execution_id,
            "plan_id": plan.id,
            "status": "executing",
            "message": "Plan execution started. Use GET /api/plans/{plan_id}/executions to track progress.",
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error executing plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to execute plan: {str(e)}") from e

@router.post(
    "/plans/reset-stuck",
    summary="Reset all stuck plans",
    description="Reset ALL plans stuck in 'executing' status back to 'failed'. Use this to recover from background execution failures.",
    responses=response_with_errors(500),
)
def reset_all_stuck_plans(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset all plans stuck in 'executing' status.

    This endpoint allows bulk recovery when background executions fail
    without properly updating status. Resets all stuck plans to 'failed'
    so they can be modified or re-executed.

    GAP-P9: Only resets plans that have been executing for longer than
    30 minutes to avoid accidentally resetting plans that are genuinely running.

    Users only see their own stuck plans reset. Admins reset all.

    **Returns:**
    - **200**: Summary of reset plans
    """
    try:
        user_id = user.get("sub")
        is_admin = user.get("role") == "admin"

        # GAP-P9: Age-based stuck detection -- only reset plans older than threshold
        AGE_THRESHOLD = timedelta(minutes=30)
        cutoff = datetime.now(UTC) - AGE_THRESHOLD

        # Find plans stuck in executing AND older than the threshold
        query = db.query(ExecutionPlan).filter(
            ExecutionPlan.status == "executing",
            ExecutionPlan.updated_at < cutoff,
        )
        if not is_admin:
            query = query.filter(ExecutionPlan.user_id == user_id)

        stuck_plans = query.all()

        if not stuck_plans:
            return {
                "message": "No stuck plans found",
                "plans_reset": 0,
                "executions_reset": 0,
                "plan_ids": [],
            }

        reset_plan_ids = []
        total_executions_reset = 0

        for plan in stuck_plans:
            plan.status = "failed"
            plan.updated_at = datetime.now(UTC)
            reset_plan_ids.append(plan.id)

            # Also mark any executing execution results as failed
            executing_results = (
                db.query(PlanExecutionResult).filter_by(plan_id=plan.id, status="executing").all()
            )
            for result in executing_results:
                result.status = "failed"
                result.end_time = datetime.now(UTC)
                if not result.node_results:
                    result.node_results = [
                        {
                            "node_id": "system",
                            "agent": None,
                            "task": "Bulk reset",
                            "status": "failed",
                            "output": "",
                            "error": "Execution was manually reset due to stuck state",
                            "duration_ms": 0,
                        }
                    ]
                total_executions_reset += 1

        db.commit()

        logger.info(f"Bulk reset {len(reset_plan_ids)} stuck plans: {reset_plan_ids}")

        return {
            "message": f"Reset {len(reset_plan_ids)} stuck plan(s) to 'failed'",
            "plans_reset": len(reset_plan_ids),
            "executions_reset": total_executions_reset,
            "plan_ids": reset_plan_ids,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting stuck plans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset stuck plans: {str(e)}") from e

@router.post(
    "/plans/{plan_id}/reset",
    summary="Reset stuck plan",
    description="Reset a specific plan stuck in 'executing' status back to 'failed'. Use this to recover from background execution failures.",
    responses=response_with_errors(400, 403, 404, 500),
)
def reset_stuck_plan(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset a plan stuck in 'executing' status.

    This endpoint allows recovery when a plan's background execution fails
    without properly updating the status. It resets the plan to 'failed'
    status so it can be modified or re-executed.

    **Returns:**
    - **200**: Plan reset successfully
    - **400**: Plan is not in 'executing' status
    - **403**: Access denied
    - **404**: Plan not found
    """
    try:
        user_id = user.get("sub")
        is_admin = user.get("role") == "admin"

        # Get plan
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # User isolation
        if not is_admin and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Only allow reset if stuck in executing
        if plan.status != "executing":
            raise HTTPException(
                status_code=400,
                detail=f"Plan is in '{plan.status}' status, not 'executing'. No reset needed.",
            )

        # Reset plan status to failed
        old_status = plan.status
        plan.status = "failed"
        plan.updated_at = datetime.now(UTC)

        # Also mark any executing execution results as failed
        executing_results = (
            db.query(PlanExecutionResult).filter_by(plan_id=plan_id, status="executing").all()
        )
        for result in executing_results:
            result.status = "failed"
            result.end_time = datetime.now(UTC)
            if not result.node_results:
                result.node_results = [
                    {
                        "node_id": "system",
                        "agent": None,
                        "task": "Manual reset",
                        "status": "failed",
                        "output": "",
                        "error": "Execution was manually reset due to stuck state",
                        "duration_ms": 0,
                    }
                ]

        db.commit()

        logger.info(
            f"Reset plan {plan_id} from '{old_status}' to 'failed' (reset {len(executing_results)} executions)"
        )

        return {
            "message": f"Plan reset from '{old_status}' to 'failed'",
            "plan_id": plan_id,
            "status": "failed",
            "executions_reset": len(executing_results),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error resetting plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset plan: {str(e)}") from e

@router.get(
    "/plans/{plan_id}/executions",
    response_model=list[ExecutionResultResponse],
    summary="List plan executions",
    description="Get all execution results for a plan, ordered by most recent first.",
    responses=response_with_errors(403, 404, 500),
)
def list_executions(
    plan_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all execution results for a plan.

    Returns execution history ordered by start_time DESC (most recent first).

    **Returns:**
    - **200**: List of execution results
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan not found
    """
    try:
        user_id = user.get("sub")

        # Get plan
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # Ownership check with admin bypass
        if user.get("role") != "admin" and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get execution results
        results = (
            db.query(PlanExecutionResult)
            .filter_by(plan_id=plan_id)
            .order_by(PlanExecutionResult.start_time.desc())
            .all()
        )

        def _compute_duration_ms(r: PlanExecutionResult) -> float | None:
            if r.start_time and r.end_time:
                return (r.end_time - r.start_time).total_seconds() * 1000
            return None

        return [
            {
                "id": r.id,
                "plan_id": r.plan_id,
                "execution_id": r.execution_id,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "status": r.status,
                "duration_ms": _compute_duration_ms(r),
                "node_results": r.node_results or [],
                "total_cost": r.total_cost,
                "user_feedback_rating": r.user_feedback_rating,
                "user_feedback_comment": r.user_feedback_comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing executions for plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list executions: {str(e)}") from e

@router.post(
    "/plans/{plan_id}/feedback",
    status_code=200,
    summary="Submit execution feedback",
    description="Submit user feedback (1-5 rating) for a plan execution.",
    responses=response_with_errors(403, 404, 500),
)
def submit_feedback(
    plan_id: int,
    request: FeedbackRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit user feedback for a plan execution.

    Feedback helps improve plan generation quality.

    **Returns:**
    - **200**: Feedback submitted successfully
    - **401**: Not authenticated
    - **403**: Access denied
    - **404**: Plan or execution not found
    """
    try:
        user_id = user.get("sub")

        # Get plan
        plan = db.query(ExecutionPlan).filter_by(id=plan_id).first()
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

        # Ownership check with admin bypass
        if user.get("role") != "admin" and plan.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get execution result
        result = (
            db.query(PlanExecutionResult)
            .filter_by(plan_id=plan_id, execution_id=request.execution_id)
            .first()
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {request.execution_id} not found for plan {plan_id}",
            )

        # Update feedback
        result.user_feedback_rating = request.rating
        result.user_feedback_comment = request.comment

        db.commit()

        logger.info(
            f"Submitted feedback for execution {request.execution_id}: {request.rating} stars"
        )

        return {
            "message": "Feedback submitted successfully",
            "execution_id": request.execution_id,
            "rating": request.rating,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error submitting feedback for plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(e)}") from e

# ============================================================================
# Template Endpoints
# ============================================================================

class InstantiateTemplateRequest(BaseModel):
    """Request to instantiate a plan template.

    Templates define reusable plan structures with parameter placeholders.
    """

    parameters: dict[str, Any] = Field(
        ..., description="Key-value parameters to substitute into the template"
    )

@router.get(
    "/plan-templates",
    summary="List plan templates",
    description="Get available plan templates with optional category filter.",
    responses=response_with_errors(500),
)
def list_plan_templates(
    category: str | None = Query(None, description="Filter by template category"),
):
    """List available plan templates.

    Templates provide pre-built plan structures for common tasks.

    **Returns:**
    - **200**: List of templates with metadata
    """
    try:
        from core.orchestrator.templates import list_templates

        templates = list_templates(category)
        logger.info(
            f"Listed {len(templates)} templates"
            + (f" in category '{category}'" if category else "")
        )

        return {"templates": templates, "total": len(templates)}

    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}") from e

@router.post(
    "/plan-templates/{template_name}/instantiate",
    response_model=PlanResponse,
    status_code=201,
    summary="Instantiate plan template",
    description="Create a new plan from a template by substituting parameters.",
    responses=response_with_errors(400, 404, 500),
)
def instantiate_plan_template(
    template_name: str,
    request: InstantiateTemplateRequest,
    conversation_id: str | None = Query(None, description="Conversation ID to associate with plan"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Instantiate a plan template with parameters.

    Creates a new plan from a template by substituting provided parameters.
    If no conversation_id is provided, creates a new conversation.

    **Returns:**
    - **201**: Plan created from template
    - **400**: Invalid template or parameters
    - **401**: Not authenticated
    - **404**: Template or conversation not found
    """
    try:
        user_id = user.get("sub")

        from core.orchestrator.templates import instantiate_template

        # Instantiate template
        logger.info(
            f"Instantiating template '{template_name}' with parameters: {list(request.parameters.keys())}"
        )

        plan_data = instantiate_template(template_name, request.parameters)

        # Create conversation if needed
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                title=f"Template: {template_name}",
                mode="planner",
            )
            db.add(conversation)
            db.flush()

        # Validate conversation exists
        conversation = db.query(Conversation).filter_by(id=conversation_id).first()
        if not conversation:
            raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")

        # Create plan from template
        plan = ExecutionPlan(
            conversation_id=conversation_id,
            user_id=user_id or conversation.user_id,
            name=plan_data["name"],
            description=plan_data["description"],
            nodes=plan_data["nodes"],
            edges=plan_data.get("edges", []),
            reasoning=plan_data["reasoning"],
            confidence=plan_data["confidence"],
            status="draft",
        )

        db.add(plan)
        db.commit()
        db.refresh(plan)

        logger.info(f"Created plan {plan.id} from template '{template_name}'")

        return {
            "id": plan.id,
            "conversation_id": plan.conversation_id,
            "user_id": plan.user_id,
            "name": plan.name,
            "description": plan.description,
            "nodes": plan.nodes,
            "edges": plan.edges,
            "reasoning": plan.reasoning,
            "confidence": plan.confidence,
            "status": plan.status,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
            "execution_count": 0,
        }

    except ValueError as e:
        logger.exception(f"Template instantiation error: {e}")
        raise HTTPException(
            status_code=400,
            detail="Failed to instantiate template. Verify template name and parameters.",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error instantiating template '{template_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to instantiate template. Please check logs or try again.",
        ) from e
