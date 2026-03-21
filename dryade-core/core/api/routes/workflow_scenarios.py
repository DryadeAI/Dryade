"""Workflow Scenarios Routes - REST API for scenario management and execution.

Provides endpoints for listing, retrieving, triggering, and managing
workflow scenarios with SSE progress streaming.
Target: ~350 LOC
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.database.models import ScenarioExecutionResult

logger = logging.getLogger("dryade.api.workflow_scenarios")

router = APIRouter(prefix="/workflow-scenarios", tags=["workflow-scenarios"])

# =============================================================================
# Response Models
# =============================================================================

class TriggerInfo(BaseModel):
    """Trigger configuration info."""

    chat_command: str | None = None
    api_endpoint: str | None = None
    ui_button: dict[str, str] | None = None

class ScenarioInfo(BaseModel):
    """Lightweight scenario summary for listing."""

    name: str
    display_name: str
    description: str
    domain: str
    version: str
    triggers: TriggerInfo

class WorkflowNodeData(BaseModel):
    """Task node data."""

    agent: str | None = None
    task: str | None = None
    context: dict[str, Any] | None = None
    condition: str | None = None
    branches: list[dict[str, str]] | None = None

class WorkflowNodeMetadata(BaseModel):
    """Node metadata matching internal NodeMetadata schema."""

    label: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None
    created_at: str | None = None  # ISO string representation

class WorkflowNode(BaseModel):
    """Workflow node."""

    id: str
    type: str
    data: WorkflowNodeData | None = None
    position: dict[str, float]
    metadata: WorkflowNodeMetadata | None = None

class WorkflowEdge(BaseModel):
    """Workflow edge."""

    id: str
    source: str
    target: str
    data: dict[str, Any] | None = None

class WorkflowGraph(BaseModel):
    """Full workflow graph structure."""

    version: str
    metadata: dict[str, Any]
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]

class InputSchemaInfo(BaseModel):
    """Input schema information."""

    name: str
    type: str
    required: bool
    description: str
    default: Any | None = None

class OutputSchemaInfo(BaseModel):
    """Output schema information."""

    name: str
    type: str

class ScenarioDetail(BaseModel):
    """Full scenario details including schemas."""

    name: str
    display_name: str
    description: str
    domain: str
    version: str
    triggers: TriggerInfo
    inputs: list[InputSchemaInfo]
    outputs: list[OutputSchemaInfo]
    required_agents: list[str]
    observability: dict[str, bool]

class CheckpointInfo(BaseModel):
    """Checkpoint metadata."""

    node_id: str
    timestamp: str
    state_keys: list[str] = Field(default_factory=list)

class ValidationResult(BaseModel):
    """Input validation result."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class ExecutionSummary(BaseModel):
    """Execution summary for listing."""

    id: int
    execution_id: str
    scenario_name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None

class NodeResult(BaseModel):
    """Per-node execution result."""

    node_id: str
    status: str
    output: Any | None = None
    duration_ms: int | None = None
    error: str | None = None

class ExecutionDetail(BaseModel):
    """Full execution details."""

    id: int
    execution_id: str
    scenario_name: str
    user_id: str | None = None
    trigger_source: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    node_results: list[NodeResult] = Field(default_factory=list)
    final_result: Any | None = None
    error: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None

class ExecutionListResponse(BaseModel):
    """Response for execution list endpoint."""

    executions: list[ExecutionSummary]
    total: int

# =============================================================================
# Helper Functions
# =============================================================================

def _get_registry():
    """Get ScenarioRegistry instance."""
    from core.workflows.scenarios import get_registry

    return get_registry()

def _get_executor():
    """Get CheckpointedWorkflowExecutor instance."""
    from core.workflows.checkpointed_executor import CheckpointedWorkflowExecutor

    return CheckpointedWorkflowExecutor()

def _get_trigger_handler():
    """Get TriggerHandler instance."""
    from core.workflows.triggers import TriggerHandler

    return TriggerHandler(_get_registry(), _get_executor())

def _config_to_info(config) -> ScenarioInfo:
    """Convert ScenarioConfig to ScenarioInfo response."""
    return ScenarioInfo(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        domain=config.domain,
        version=config.version,
        triggers=TriggerInfo(
            chat_command=config.triggers.chat_command,
            api_endpoint=config.triggers.api_endpoint,
            ui_button=config.triggers.ui_button,
        ),
    )

def _config_to_detail(config) -> ScenarioDetail:
    """Convert ScenarioConfig to ScenarioDetail response."""
    return ScenarioDetail(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        domain=config.domain,
        version=config.version,
        triggers=TriggerInfo(
            chat_command=config.triggers.chat_command,
            api_endpoint=config.triggers.api_endpoint,
            ui_button=config.triggers.ui_button,
        ),
        inputs=[
            InputSchemaInfo(
                name=inp.name,
                type=inp.type,
                required=inp.required,
                description=inp.description,
                default=inp.default,
            )
            for inp in config.inputs
        ],
        outputs=[OutputSchemaInfo(name=out.name, type=out.type) for out in config.outputs],
        required_agents=config.required_agents,
        observability=config.observability,
    )

# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    response_model=list[ScenarioInfo],
    summary="List workflow scenarios",
    description="Get a list of all available workflow scenarios with their basic info and triggers.",
)
async def list_scenarios() -> list[ScenarioInfo]:
    """List all available workflow scenarios.

    Returns:
        List of scenario info objects with name, description, domain, and triggers.
    """
    try:
        registry = _get_registry()
        configs = registry.list_scenarios()

        logger.info(f"[WORKFLOW_SCENARIOS] Listed {len(configs)} scenarios")
        return [_config_to_info(config) for config in configs]

    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error listing scenarios: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list scenarios. This may be a temporary issue - please try again.",
        ) from e

# =============================================================================
# Execution History Endpoints (must be before /{scenario_name} routes)
# =============================================================================

@router.get(
    "/executions",
    response_model=ExecutionListResponse,
    summary="List execution history",
    description="Get a list of workflow executions with optional filtering.",
)
async def list_executions(
    scenario_name: str | None = Query(None, description="Filter by scenario name"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ExecutionListResponse:
    """List workflow executions with optional filtering.

    Args:
        scenario_name: Filter by scenario name (optional).
        status: Filter by status (optional): running, completed, failed, cancelled.
        limit: Maximum number of results (default 50, max 200).
        offset: Offset for pagination (default 0).
        db: Database session.

    Returns:
        List of execution summaries with total count.
    """
    try:
        query = db.query(ScenarioExecutionResult)

        # Filter by user_id so users only see their own executions (admin bypass)
        if current_user.get("role") != "admin":
            query = query.filter(ScenarioExecutionResult.user_id == current_user.get("sub"))

        if scenario_name:
            query = query.filter(ScenarioExecutionResult.scenario_name == scenario_name)
        if status:
            query = query.filter(ScenarioExecutionResult.status == status)

        total = query.count()
        results = (
            query.order_by(ScenarioExecutionResult.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        executions = [
            ExecutionSummary(
                id=r.id,
                execution_id=r.execution_id,
                scenario_name=r.scenario_name,
                status=r.status,
                started_at=r.started_at.isoformat() if r.started_at else None,
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
                duration_ms=r.duration_ms,
            )
            for r in results
        ]

        logger.info(f"[WORKFLOW_SCENARIOS] Listed {len(executions)} executions (total={total})")
        return ExecutionListResponse(executions=executions, total=total)

    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error listing executions: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list executions. This may be a temporary issue - please try again.",
        ) from e

@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionDetail,
    summary="Get execution details",
    description="Get full details for a specific workflow execution.",
)
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ExecutionDetail:
    """Get detailed information about a specific execution.

    Args:
        execution_id: UUID of the execution.
        db: Database session.

    Returns:
        Full execution details including node results and final output.

    Raises:
        HTTPException: 404 if execution not found.
    """
    try:
        result = (
            db.query(ScenarioExecutionResult)
            .filter(ScenarioExecutionResult.execution_id == execution_id)
            .first()
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")

        # Verify ownership: non-admin users can only view their own executions
        if current_user.get("role") != "admin" and result.user_id != current_user.get("sub"):
            raise HTTPException(status_code=403, detail="Access denied")

        # Convert node_results from JSON to NodeResult objects
        node_results = []
        if result.node_results:
            for nr in result.node_results:
                node_results.append(
                    NodeResult(
                        node_id=nr.get("node_id", ""),
                        status=nr.get("status", "unknown"),
                        output=nr.get("output"),
                        duration_ms=nr.get("duration_ms"),
                        error=nr.get("error"),
                    )
                )

        logger.info(f"[WORKFLOW_SCENARIOS] Retrieved execution: {execution_id}")
        return ExecutionDetail(
            id=result.id,
            execution_id=result.execution_id,
            scenario_name=result.scenario_name,
            user_id=result.user_id,
            trigger_source=result.trigger_source,
            status=result.status,
            started_at=result.started_at.isoformat() if result.started_at else None,
            completed_at=result.completed_at.isoformat() if result.completed_at else None,
            duration_ms=result.duration_ms,
            node_results=node_results,
            final_result=result.final_result,
            error=result.error,
            inputs=result.inputs or {},
            created_at=result.created_at.isoformat() if result.created_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error getting execution: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve execution. This may be a temporary issue - please try again.",
        ) from e

@router.post(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionDetail,
    summary="Cancel execution",
    description="Cancel a running workflow execution.",
)
async def cancel_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ExecutionDetail:
    """Cancel a running workflow execution.

    Args:
        execution_id: UUID of the execution to cancel.
        db: Database session.

    Returns:
        Updated execution details.

    Raises:
        HTTPException: 404 if execution not found, 400 if not running.
    """
    try:
        result = (
            db.query(ScenarioExecutionResult)
            .filter(ScenarioExecutionResult.execution_id == execution_id)
            .first()
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")

        # Verify ownership: non-admin users can only cancel their own executions
        if current_user.get("role") != "admin" and result.user_id != current_user.get("sub"):
            raise HTTPException(status_code=403, detail="Access denied")

        if result.status != "running":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel execution with status '{result.status}'. Only running executions can be cancelled.",
            )

        # Update status to cancelled
        result.status = "cancelled"
        result.completed_at = datetime.now(UTC)
        if result.started_at:
            # Normalize for duration calculation
            completed = (
                result.completed_at.replace(tzinfo=None)
                if result.completed_at.tzinfo
                else result.completed_at
            )
            started = (
                result.started_at.replace(tzinfo=None)
                if result.started_at.tzinfo
                else result.started_at
            )
            duration = (completed - started).total_seconds() * 1000
            result.duration_ms = int(duration)

        db.commit()

        logger.info(f"[WORKFLOW_SCENARIOS] Cancelled execution: {execution_id}")

        # Convert node_results from JSON to NodeResult objects
        node_results = []
        if result.node_results:
            for nr in result.node_results:
                node_results.append(
                    NodeResult(
                        node_id=nr.get("node_id", ""),
                        status=nr.get("status", "unknown"),
                        output=nr.get("output"),
                        duration_ms=nr.get("duration_ms"),
                        error=nr.get("error"),
                    )
                )

        return ExecutionDetail(
            id=result.id,
            execution_id=result.execution_id,
            scenario_name=result.scenario_name,
            user_id=result.user_id,
            trigger_source=result.trigger_source,
            status=result.status,
            started_at=result.started_at.isoformat() if result.started_at else None,
            completed_at=result.completed_at.isoformat() if result.completed_at else None,
            duration_ms=result.duration_ms,
            node_results=node_results,
            final_result=result.final_result,
            error=result.error,
            inputs=result.inputs or {},
            created_at=result.created_at.isoformat() if result.created_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error cancelling execution: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to cancel execution. This may be a temporary issue - please try again.",
        ) from e

# =============================================================================
# Scenario-specific Endpoints
# =============================================================================

@router.get(
    "/{scenario_name}",
    response_model=ScenarioDetail,
    summary="Get scenario details",
    description="Get full details for a workflow scenario including input/output schemas.",
)
async def get_scenario(scenario_name: str) -> ScenarioDetail:
    """Get detailed information about a specific scenario.

    Args:
        scenario_name: Name of the scenario to retrieve.

    Returns:
        Full scenario details including input schema, output schema, and required agents.

    Raises:
        HTTPException: 404 if scenario not found.
    """
    try:
        registry = _get_registry()
        config, _workflow = registry.get_scenario(scenario_name)

        logger.info(f"[WORKFLOW_SCENARIOS] Retrieved scenario: {scenario_name}")
        return _config_to_detail(config)

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_name}")
    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error getting scenario: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve scenario. This may be a temporary issue - please try again.",
        ) from e

@router.get(
    "/{scenario_name}/workflow",
    response_model=WorkflowGraph,
    summary="Get scenario workflow graph",
    description="Get the full workflow graph (nodes and edges) for visual editing.",
)
async def get_scenario_workflow(scenario_name: str) -> WorkflowGraph:
    """Get the workflow graph structure for a scenario.

    Args:
        scenario_name: Name of the scenario to retrieve workflow for.

    Returns:
        Full workflow graph with nodes and edges.

    Raises:
        HTTPException: 404 if scenario not found.
    """
    try:
        registry = _get_registry()
        _config, workflow = registry.get_scenario(scenario_name)

        logger.info(f"[WORKFLOW_SCENARIOS] Retrieved workflow for: {scenario_name}")

        # Convert WorkflowSchema to WorkflowGraph response
        return WorkflowGraph(
            version=workflow.version,
            metadata=workflow.metadata.model_dump()
            if workflow.metadata and hasattr(workflow.metadata, "model_dump")
            else (workflow.metadata if workflow.metadata else {}),
            nodes=[
                WorkflowNode(
                    id=n.id,
                    type=n.type,
                    position=n.position.model_dump()
                    if hasattr(n.position, "model_dump")
                    else n.position,
                    data=WorkflowNodeData(
                        agent=n.data.agent if n.data and hasattr(n.data, "agent") else None,
                        task=n.data.task if n.data and hasattr(n.data, "task") else None,
                        context=n.data.context if n.data and hasattr(n.data, "context") else None,
                        condition=n.data.condition
                        if n.data and hasattr(n.data, "condition")
                        else None,
                        branches=n.data.branches
                        if n.data and hasattr(n.data, "branches")
                        else None,
                    )
                    if n.data
                    else None,
                    metadata=WorkflowNodeMetadata(
                        label=n.metadata.label if hasattr(n.metadata, "label") else None,
                        description=n.metadata.description
                        if hasattr(n.metadata, "description")
                        else None,
                        tags=n.metadata.tags if hasattr(n.metadata, "tags") else [],
                        created_by=n.metadata.created_by
                        if hasattr(n.metadata, "created_by")
                        else None,
                        created_at=n.metadata.created_at.isoformat()
                        if hasattr(n.metadata, "created_at") and n.metadata.created_at
                        else None,
                    )
                    if n.metadata
                    else None,
                )
                for n in workflow.nodes
            ],
            edges=[
                WorkflowEdge(
                    id=e.id,
                    source=e.source,
                    target=e.target,
                    data=e.data.model_dump()
                    if e.data and hasattr(e.data, "model_dump")
                    else (e.data if e.data else None),
                )
                for e in workflow.edges
            ],
        )

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_name}")
    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error getting workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve workflow. This may be a temporary issue - please try again.",
        ) from e

@router.post(
    "/{scenario_name}/trigger",
    summary="Trigger workflow scenario",
    description="Trigger a workflow scenario execution with progress streaming via SSE.",
)
async def trigger_scenario(
    scenario_name: str,
    inputs: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Trigger workflow scenario with SSE progress streaming.

    Args:
        scenario_name: Name of the scenario to trigger.
        inputs: Input values for the workflow.
        current_user: Optional authenticated user.

    Returns:
        StreamingResponse with SSE events for execution progress.

    SSE Event Types:
        - workflow_start: Execution began
        - node_start: Node started processing
        - node_complete: Node finished with output
        - checkpoint: Checkpoint reached
        - error: Error occurred
        - workflow_complete: Execution finished

    Raises:
        HTTPException: 404 if scenario not found.
    """
    from core.workflows.triggers import TriggerSource

    # Verify scenario exists before starting stream
    try:
        registry = _get_registry()
        registry.get_scenario(scenario_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_name}")

    user_id = current_user.get("sub")

    logger.info(f"[WORKFLOW_SCENARIOS] Triggering scenario={scenario_name} user={user_id}")

    handler = _get_trigger_handler()
    return StreamingResponse(
        handler.trigger(
            scenario_name,
            inputs,
            TriggerSource.API,
            user_id=user_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

@router.post(
    "/{scenario_name}/resume",
    summary="Resume workflow from checkpoint",
    description="Resume a paused workflow execution from a specific checkpoint.",
)
async def resume_scenario(
    scenario_name: str,
    execution_id: str = Body(..., embed=True),
    checkpoint_node: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Resume workflow execution from a checkpoint.

    GAP-S2: Checkpoint resume is currently a stub. Full implementation requires:
    1. Load checkpoint state from CheckpointStore
    2. Reconstruct Flow class from original scenario config
    3. Set Flow state from checkpoint (skip already-completed nodes)
    4. Execute only remaining nodes
    This is deferred to a dedicated phase due to complexity.
    Current behavior: returns checkpoint data for display but does not re-execute.

    Args:
        scenario_name: Name of the scenario.
        execution_id: ID of the execution to resume.
        checkpoint_node: Node ID of the checkpoint to resume from.
        current_user: Authenticated user.

    Returns:
        StreamingResponse with SSE events for continued execution.

    Raises:
        HTTPException: 404 if scenario or checkpoint not found.
    """

    # Verify scenario exists
    try:
        registry = _get_registry()
        registry.get_scenario(scenario_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_name}")

    # Check checkpoint exists
    executor = _get_executor()
    checkpoints = executor.get_checkpoints(execution_id)

    if not any(cp.get("node_id") == checkpoint_node for cp in checkpoints):
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint not found: execution={execution_id}, node={checkpoint_node}",
        )

    _user_id = current_user.get("sub")

    logger.info(
        f"[WORKFLOW_SCENARIOS] Resuming scenario={scenario_name} "
        f"execution={execution_id} from={checkpoint_node}"
    )

    # Resume execution
    async def resume_stream():
        import json
        from datetime import UTC, datetime

        try:
            checkpoint_data = await executor.resume_from(execution_id, checkpoint_node)

            yield f"data: {json.dumps({'type': 'resumed', 'execution_id': execution_id, 'from_node': checkpoint_node, 'timestamp': datetime.now(UTC).isoformat()})}\n\n"

            # Continue execution from checkpoint
            # For now, return checkpoint data; full resume logic TBD
            yield f"data: {json.dumps({'type': 'checkpoint_data', 'execution_id': execution_id, 'data': str(checkpoint_data)[:500], 'timestamp': datetime.now(UTC).isoformat()})}\n\n"

            yield f"data: {json.dumps({'type': 'workflow_complete', 'execution_id': execution_id, 'timestamp': datetime.now(UTC).isoformat()})}\n\n"

        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'execution_id': execution_id, 'error': str(e), 'timestamp': datetime.now(UTC).isoformat()})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'execution_id': execution_id, 'error': str(e), 'timestamp': datetime.now(UTC).isoformat()})}\n\n"

    return StreamingResponse(
        resume_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

@router.get(
    "/executions/{execution_id}/checkpoints",
    response_model=list[CheckpointInfo],
    summary="List execution checkpoints",
    description="List available checkpoints for a workflow execution.",
)
async def list_checkpoints(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[CheckpointInfo]:
    """List available checkpoints for an execution.

    Args:
        execution_id: ID of the execution to list checkpoints for.
        db: Database session.
        current_user: Authenticated user.

    Returns:
        List of checkpoint metadata.
    """
    try:
        # Verify execution ownership before listing checkpoints
        if current_user.get("role") != "admin":
            result = (
                db.query(ScenarioExecutionResult)
                .filter(ScenarioExecutionResult.execution_id == execution_id)
                .first()
            )
            if result and result.user_id != current_user.get("sub"):
                raise HTTPException(status_code=403, detail="Access denied")

        executor = _get_executor()
        checkpoints = executor.get_checkpoints(execution_id)

        result = [
            CheckpointInfo(
                node_id=cp.get("node_id", ""),
                timestamp=cp.get("timestamp", ""),
                state_keys=list(cp.get("state", {}).keys())
                if isinstance(cp.get("state"), dict)
                else [],
            )
            for cp in checkpoints
        ]

        logger.info(f"[WORKFLOW_SCENARIOS] Listed {len(result)} checkpoints for {execution_id}")
        return result

    except Exception as e:
        logger.exception(f"[WORKFLOW_SCENARIOS] Error listing checkpoints: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list checkpoints. This may be a temporary issue - please try again.",
        ) from e

@router.post(
    "/{scenario_name}/validate",
    response_model=ValidationResult,
    summary="Validate scenario inputs",
    description="Validate inputs against the scenario's input schema before triggering.",
)
async def validate_inputs(
    scenario_name: str,
    inputs: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
) -> ValidationResult:
    """Validate inputs against scenario schema.

    Args:
        scenario_name: Name of the scenario.
        inputs: Input values to validate.

    Returns:
        Validation result with any errors or warnings.

    Raises:
        HTTPException: 404 if scenario not found.
    """
    try:
        registry = _get_registry()
        config, _workflow = registry.get_scenario(scenario_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_name}")

    errors = []
    warnings = []

    # Check required fields
    for inp in config.inputs:
        value = inputs.get(inp.name)
        if value is None and inp.required and inp.default is None:
            errors.append(f"Required input missing: {inp.name}")
        elif value is not None:
            # Type check
            if inp.type == "number":
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors.append(f"Invalid number for {inp.name}: {value}")
            elif inp.type == "boolean":
                if not isinstance(value, bool) and str(value).lower() not in (
                    "true",
                    "false",
                    "1",
                    "0",
                    "yes",
                    "no",
                ):
                    warnings.append(f"Value for {inp.name} may not be a valid boolean")
            elif inp.type == "json":
                import json as json_module

                if not isinstance(value, (dict, list)):
                    try:
                        json_module.loads(value)
                    except (json_module.JSONDecodeError, TypeError):
                        errors.append(f"Invalid JSON for {inp.name}")

    # Check for unknown inputs
    known_names = {inp.name for inp in config.inputs}
    for key in inputs:
        if key not in known_names:
            warnings.append(f"Unknown input will be passed through: {key}")

    logger.info(
        f"[WORKFLOW_SCENARIOS] Validated inputs for {scenario_name}: "
        f"valid={len(errors) == 0}, errors={len(errors)}, warnings={len(warnings)}"
    )

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )

# =============================================================================
# Cross-System Conversion Endpoints
# =============================================================================

class ScenarioFromTemplateRequest(BaseModel):
    """Request body for creating a scenario from a template."""

    name: str = Field(default="template-scenario", description="Scenario name")
    workflow_json: dict[str, Any] = Field(..., description="Template workflow JSON")
    description: str = Field(default="", description="Scenario description")
    template_id: int | None = Field(None, description="Source template ID for provenance")

class ScenarioFromTemplateResponse(BaseModel):
    """Response for scenario creation from template."""

    scenario_name: str
    path: str
    message: str

@router.post(
    "/from-template",
    response_model=ScenarioFromTemplateResponse,
    summary="Create scenario from template",
    description="Create a scenario YAML + workflow.json from a template's workflow_json.",
)
async def create_scenario_from_template(
    request: ScenarioFromTemplateRequest,
    current_user: dict = Depends(get_current_user),
) -> ScenarioFromTemplateResponse:
    """Create a scenario from a template's workflow_json.

    Accepts workflow_json from the frontend (never imports plugin models).
    Creates a scenario config YAML file + workflow.json in the scenarios directory.

    Reverse direction (scenario -> template) is handled by the existing
    "Save as Template" CustomEvent bridge in WorkflowPage.tsx (SEAM-3).
    No separate endpoint needed.

    Args:
        request: Template data including name, workflow_json, and description.
        current_user: Authenticated user.

    Returns:
        Created scenario details.

    Raises:
        HTTPException: 400 if workflow_json is invalid.
    """
    import json
    import os
    import re

    try:
        import yaml
    except ImportError:
        # PyYAML not available, use JSON fallback for config
        yaml = None  # type: ignore[assignment]

    name = request.name
    workflow_json = request.workflow_json
    description = request.description

    if not workflow_json:
        raise HTTPException(400, "workflow_json is required")

    # Sanitize name for filesystem
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    if not safe_name:
        safe_name = "template_scenario"

    # Create scenario directory
    scenarios_dir = os.path.join("config", "scenarios", safe_name)
    os.makedirs(scenarios_dir, exist_ok=True)

    # Write workflow.json
    with open(os.path.join(scenarios_dir, "workflow.json"), "w") as f:
        json.dump(workflow_json, f, indent=2)

    # Generate config from workflow nodes
    nodes = workflow_json.get("nodes", [])
    task_nodes = [n for n in nodes if n.get("type") == "task"]

    config = {
        "name": name,
        "description": description,
        "version": "1.0.0",
        "inputs": {},
        "required_agents": list(
            set(
                n.get("data", {}).get("agent", n.get("agent", ""))
                for n in task_nodes
                if n.get("data", {}).get("agent") or n.get("agent")
            )
        ),
    }

    config_path = os.path.join(scenarios_dir, "config.yaml")
    if yaml:
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
    else:
        # Fallback: write as JSON with .yaml extension
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

    user_id = current_user.get("sub") if current_user else "unknown"
    logger.info(
        f"[WORKFLOW_SCENARIOS] Created scenario '{safe_name}' from template "
        f"(template_id={request.template_id}) by user={user_id}"
    )

    return ScenarioFromTemplateResponse(
        scenario_name=safe_name,
        path=scenarios_dir,
        message=f"Scenario '{name}' created from template",
    )

class UploadResponse(BaseModel):
    """Response for workflow input file upload."""

    path: str
    filename: str

# Import UploadFile, File, Form at top level for endpoint
import uuid
from pathlib import Path

from fastapi import File, Form, UploadFile

@router.post(
    "/upload-input",
    response_model=UploadResponse,
    summary="Upload workflow input file",
    description="Upload a file to be used as input for a workflow scenario.",
)
async def upload_input_file(
    file: UploadFile = File(..., description="File to upload for workflow input"),
    input_name: str = Form("input", description="Name of the workflow input"),
    current_user: dict = Depends(get_current_user),
):
    """Upload a file for use as workflow input.

    Files are stored in a staging area and the path is returned for use
    in workflow trigger requests.

    Args:
        file: The uploaded file.
        input_name: Name of the input this file is for (for logging).
        current_user: Authenticated user.

    Returns:
        UploadResponse with file path and original filename.
    """
    # Create uploads directory for workflow inputs
    uploads_dir = Path("uploads/workflow_inputs")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to avoid collisions
    file_ext = Path(file.filename).suffix if file.filename else ""
    unique_id = str(uuid.uuid4())[:8]
    safe_filename = f"{unique_id}_{input_name}{file_ext}"
    file_path = uploads_dir / safe_filename

    # Write file to disk
    try:
        content = await file.read()
        file_path.write_bytes(content)
    except Exception as e:
        logger.error(f"[WORKFLOW_SCENARIOS] Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}") from e

    logger.info(f"[WORKFLOW_SCENARIOS] Uploaded file for input '{input_name}': {file_path}")

    return UploadResponse(
        path=str(file_path.absolute()),
        filename=file.filename or safe_filename,
    )
