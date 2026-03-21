"""Flow Routes - Flow discovery, execution, and visualization endpoints.

Target: ~120 LOC
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.api.models.openapi import response_with_errors
from core.flows import FLOW_REGISTRY

try:
    from core.extensions import flow_to_reactflow, get_flow_info
except ImportError:
    flow_to_reactflow = None
    get_flow_info = None

logger = logging.getLogger("dryade.api.flows")

router = APIRouter()

# Request/Response Models
class FlowInfo(BaseModel):
    """Information about a registered flow."""

    name: str = Field(..., description="Unique flow identifier")
    description: str = Field(..., description="Human-readable flow description")
    nodes: list[str] = Field(..., description="List of node names in execution order")
    entry_point: str = Field(..., description="Starting node for flow execution")

class FlowRequest(BaseModel):
    """Request to execute a flow."""

    inputs: dict[str, Any] = Field(..., description="Input values for flow state")
    start_from: str | None = Field(None, description="Node to start execution from (for resume)")

class FlowResponse(BaseModel):
    """Response from flow execution."""

    execution_id: str = Field(..., description="Unique execution identifier (UUID)")
    result: dict[str, Any] = Field(..., description="Flow execution output")
    status: str = Field(..., description="Execution status (complete, error, resumed)")

class ReactFlowJSON(BaseModel):
    """ReactFlow visualization data."""

    nodes: list[dict] = Field(..., description="ReactFlow node definitions")
    edges: list[dict] = Field(..., description="ReactFlow edge definitions")
    viewport: dict = Field(..., description="ReactFlow viewport settings")

class ExecutionStatus(BaseModel):
    """Status of a flow execution."""

    execution_id: str = Field(..., description="Execution identifier")
    status: str = Field(..., description="Current status (running, complete, error)")
    current_node: str | None = Field(None, description="Currently executing node")
    progress: float = Field(0.0, description="Execution progress (0.0 to 1.0)", ge=0, le=1)

# In-memory execution storage (thread-safe with TTL eviction)
_executions: dict[str, dict[str, Any]] = {}
_executions_lock = threading.Lock()
_EXECUTION_TTL = 3600  # 1 hour in seconds

def _evict_expired_executions() -> None:
    """Remove execution entries older than _EXECUTION_TTL seconds. Called inside lock."""
    now = time.time()
    expired = [
        eid
        for eid, data in _executions.items()
        if now - data.get("_created_at", 0) > _EXECUTION_TTL
    ]
    for eid in expired:
        del _executions[eid]

class FlowListResponse(BaseModel):
    """List of available flows."""

    flows: list[FlowInfo] = Field(..., description="List of flow information")

@router.get(
    "",
    response_model=FlowListResponse,
    summary="List available flows",
)
async def list_flows() -> FlowListResponse:
    """List all available execution flows.

    Returns predefined flows like AnalysisFlow, CoverageFlow, etc.
    """
    flows = []
    for name, info in FLOW_REGISTRY.items():
        flow_class = info["class"]
        if get_flow_info:
            fi = get_flow_info(flow_class)
            nodes = fi["nodes"]
        else:
            nodes = []
        flows.append(
            FlowInfo(
                name=name,
                description=info.get("description", ""),
                nodes=nodes,
                entry_point=info.get("entry_point", ""),
            )
        )
    return FlowListResponse(flows=flows)

@router.get(
    "/{name}",
    response_model=FlowInfo,
    responses=response_with_errors(404),
    summary="Get flow definition",
)
async def get_flow(name: str) -> FlowInfo:
    """Get flow definition by name.

    Returns node structure and entry point for the flow.
    """
    if name not in FLOW_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    info = FLOW_REGISTRY[name]
    flow_class = info["class"]
    if get_flow_info:
        fi = get_flow_info(flow_class)
        nodes = fi["nodes"]
    else:
        nodes = []

    return FlowInfo(
        name=name,
        description=info.get("description", ""),
        nodes=nodes,
        entry_point=info.get("entry_point", ""),
    )

@router.get(
    "/{name}/graph",
    response_model=ReactFlowJSON,
    responses=response_with_errors(404),
    summary="Get flow visualization",
)
async def get_flow_graph(name: str) -> ReactFlowJSON:
    """Get ReactFlow visualization data for a flow.

    Returns nodes and edges formatted for ReactFlow rendering.
    """
    logger.info(f"[FLOWS API] Request for ReactFlow graph: flow='{name}'")

    if name not in FLOW_REGISTRY:
        logger.warning(f"[FLOWS API] Flow '{name}' not found in registry")
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    if not flow_to_reactflow:
        raise HTTPException(status_code=501, detail="ReactFlow plugin not available")

    logger.info(f"[FLOWS API] Flow '{name}' found, generating ReactFlow JSON")
    flow_class = FLOW_REGISTRY[name]["class"]
    graph = flow_to_reactflow(flow_class)

    logger.info(
        f"[FLOWS API] ✓ ReactFlow JSON generated for '{name}': {len(graph['nodes'])} nodes, {len(graph['edges'])} edges"
    )
    logger.debug("[FLOWS API] Returning ReactFlow JSON to frontend")

    return ReactFlowJSON(**graph)

async def _execute_flow_impl(name: str, request: FlowRequest) -> FlowResponse:
    """Internal implementation of flow execution."""
    if name not in FLOW_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    execution_id = str(uuid.uuid4())

    try:
        flow_class = FLOW_REGISTRY[name]["class"]
        flow = flow_class()

        # Set inputs on flow state
        for key, value in request.inputs.items():
            if hasattr(flow.state, key):
                setattr(flow.state, key, value)

        # Execute flow in thread pool to avoid blocking event loop
        import concurrent.futures

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, flow.kickoff)

        with _executions_lock:
            _evict_expired_executions()
            _executions[execution_id] = {
                "status": "complete",
                "result": result if isinstance(result, dict) else {"output": str(result)},
                "flow_name": name,
                "_created_at": time.time(),
            }
            result_data = _executions[execution_id]["result"]

        return FlowResponse(
            execution_id=execution_id,
            result=result_data,
            status="complete",
        )
    except Exception as e:
        logger.exception(f"Failed to execute flow '{name}': {e}")
        with _executions_lock:
            _evict_expired_executions()
            _executions[execution_id] = {
                "status": "error",
                "error": str(e),
                "flow_name": name,
                "_created_at": time.time(),
            }
        raise HTTPException(
            status_code=500,
            detail="Failed to execute flow. Check flow configuration and try again.",
        ) from e

@router.post(
    "/{name}/execute",
    response_model=FlowResponse,
    responses=response_with_errors(404, 500),
    summary="Execute a flow",
)
async def execute_flow(name: str, request: FlowRequest) -> FlowResponse:
    """Execute a specific flow with provided inputs.

    Sets flow state from inputs and runs to completion.
    Returns execution ID for status tracking.
    """
    return await _execute_flow_impl(name, request)

@router.post(
    "/{name}/kickoff",
    response_model=FlowResponse,
    responses=response_with_errors(404, 500),
    summary="Kickoff a flow (alias for execute)",
)
async def kickoff_flow(name: str, request: FlowRequest) -> FlowResponse:
    """Kickoff a specific flow (alias for /execute).

    This endpoint exists for frontend compatibility.
    """
    return await _execute_flow_impl(name, request)

@router.post(
    "/{name}/execute/stream",
    responses=response_with_errors(404),
    summary="Stream flow execution",
)
async def execute_flow_stream(name: str, request: FlowRequest) -> StreamingResponse:
    """Execute a flow with streaming progress updates.

    Returns SSE events for each node transition:
    - **start**: Execution started with ID
    - **node_start**: Node beginning execution
    - **complete**: Flow finished with result
    - **error**: Execution failed
    - **[DONE]**: Stream complete
    """
    if name not in FLOW_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    execution_id = str(uuid.uuid4())

    async def generate():
        import concurrent.futures

        yield f"data: {json.dumps({'type': 'start', 'execution_id': execution_id})}\n\n"

        try:
            flow_class = FLOW_REGISTRY[name]["class"]
            flow = flow_class()

            for key, value in request.inputs.items():
                if hasattr(flow.state, key):
                    setattr(flow.state, key, value)

            # Simulate node progress
            nodes = get_flow_info(flow_class)["nodes"] if get_flow_info else []
            for _i, node in enumerate(nodes):
                yield f"data: {json.dumps({'type': 'node_start', 'node': node})}\n\n"
                await asyncio.sleep(0.1)

            # Execute flow in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = await loop.run_in_executor(pool, flow.kickoff)
            yield f"data: {json.dumps({'type': 'complete', 'result': result if isinstance(result, dict) else str(result)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionStatus,
    responses=response_with_errors(404),
    summary="Get execution status",
)
async def get_execution(execution_id: str) -> ExecutionStatus:
    """Get execution status for a flow run.

    Returns current status, progress, and active node.
    """
    with _executions_lock:
        exec_data = _executions.get(execution_id)
    if exec_data is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    return ExecutionStatus(
        execution_id=execution_id,
        status=exec_data.get("status", "unknown"),
        progress=1.0 if exec_data.get("status") == "complete" else 0.5,
    )

@router.post(
    "/executions/{execution_id}/resume",
    response_model=FlowResponse,
    responses=response_with_errors(400, 404, 500),
    summary="Resume flow execution",
)
async def resume_execution(execution_id: str, node_id: str | None = None) -> FlowResponse:
    """Resume flow execution from checkpoint.

    If node_id is provided, resumes from that specific node.
    Otherwise, resumes from the last available checkpoint.
    Requires the flow to support CheckpointMixin.
    """
    with _executions_lock:
        exec_data = _executions.get(execution_id)
    if exec_data is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    flow_name = exec_data.get("flow_name")

    if not flow_name or flow_name not in FLOW_REGISTRY:
        raise HTTPException(status_code=400, detail="Cannot resume: flow not found")

    try:
        from core.extensions import CheckpointMixin

        flow_class = FLOW_REGISTRY[flow_name]["class"]
        flow = flow_class()

        if isinstance(flow, CheckpointMixin):
            if node_id:
                result = await flow.resume_from(node_id)
            else:
                # Resume from last checkpoint
                checkpoints = flow.list_checkpoints()
                if not checkpoints:
                    raise HTTPException(status_code=400, detail="No checkpoints available")
                result = await flow.resume_from(checkpoints[-1]["node_id"])
        else:
            raise HTTPException(status_code=400, detail="Flow does not support checkpoints")

        return FlowResponse(
            execution_id=execution_id,
            result=result if isinstance(result, dict) else {"output": str(result)},
            status="resumed",
        )
    except ValueError as e:
        logger.exception(f"Failed to resume flow checkpoint: {e}")
        raise HTTPException(
            status_code=400,
            detail="Failed to resume flow checkpoint. Verify checkpoint state and node ID.",
        ) from e
    except Exception as e:
        logger.exception(f"Failed to resume flow execution: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to resume flow. Check execution state and try again.",
        ) from e
