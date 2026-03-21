"""Factory Routes - REST API for the Agent Factory lifecycle management.

Exposes CRUD + rollback for factory-created artifacts (agents, tools, skills).
All endpoints delegate to the core.factory public API, keeping this layer thin.
Follows the agents.py pattern: APIRouter without prefix (applied in main.py).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.api.models.openapi import response_with_errors
from core.auth.dependencies import get_current_user
from core.factory import (
    ArtifactStatus,
    ArtifactType,
    CreationResult,
    FactoryArtifact,
    delete_artifact,
    get_artifact,
    list_artifacts,
    rollback_artifact,
    update_artifact,
)
from core.factory.models import CreationRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CreateRequest(BaseModel):
    """REST request body for creating a factory artifact."""

    goal: str = Field(..., min_length=3, description="Natural-language goal")
    suggested_name: Optional[str] = Field(
        None, max_length=64, description="Optional slug-style name"
    )
    artifact_type: Optional[str] = Field(None, description="Artifact type: agent, tool, skill")
    framework: Optional[str] = Field(None, description="Target framework")
    test_task: Optional[str] = Field(None, description="Task to verify the artifact")
    max_test_iterations: int = Field(3, ge=1, le=10, description="Max test-fix cycles")
    fast_path: bool = Field(False, description="Use fast scaffold-only path (test in background)")

class UpdateRequest(BaseModel):
    """REST request body for updating an existing artifact."""

    goal: str = Field(..., min_length=3, description="Updated natural-language goal")
    suggested_name: Optional[str] = Field(
        None, max_length=64, description="Optional slug-style name"
    )
    artifact_type: Optional[str] = Field(None, description="Artifact type: agent, tool, skill")
    framework: Optional[str] = Field(None, description="Target framework")
    test_task: Optional[str] = Field(None, description="Task to verify the artifact")
    max_test_iterations: int = Field(3, ge=1, le=10, description="Max test-fix cycles")

class RollbackRequest(BaseModel):
    """REST request body for rolling back to a previous version."""

    version: int = Field(..., ge=1, description="Target version to rollback to")

class ArtifactListResponse(BaseModel):
    """Response for listing factory artifacts."""

    items: list[FactoryArtifact] = Field(description="List of artifacts")
    count: int = Field(description="Total number of items returned")

# ---------------------------------------------------------------------------
# Helper: parse enum from string
# ---------------------------------------------------------------------------

def _parse_artifact_type(value: str) -> ArtifactType:
    """Parse a string into an ArtifactType enum, raising ValueError on bad input."""
    try:
        return ArtifactType(value.lower())
    except ValueError:
        valid = [t.value for t in ArtifactType]
        raise ValueError(f"Invalid artifact type '{value}'. Valid: {valid}")

def _parse_artifact_status(value: str) -> ArtifactStatus:
    """Parse a string into an ArtifactStatus enum, raising ValueError on bad input."""
    try:
        return ArtifactStatus(value.lower())
    except ValueError:
        valid = [s.value for s in ArtifactStatus]
        raise ValueError(f"Invalid artifact status '{value}'. Valid: {valid}")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=CreationResult,
    status_code=201,
    responses=response_with_errors(400, 500),
    summary="Create a factory artifact",
)
async def create(request: CreateRequest, user=Depends(get_current_user)) -> CreationResult:
    """Create an agent, tool, or skill from a natural language goal.

    Returns 201 on success, 202 if awaiting approval, 400 on validation error.
    """
    try:
        # Parse artifact_type string to enum if provided
        artifact_type_enum = None
        if request.artifact_type:
            artifact_type_enum = _parse_artifact_type(request.artifact_type)

        creation_request = CreationRequest(
            goal=request.goal,
            suggested_name=request.suggested_name,
            artifact_type=artifact_type_enum,
            framework=request.framework,
            test_task=request.test_task,
            max_test_iterations=request.max_test_iterations,
        )

        # Use FactoryPipeline directly to support fast_path parameter.
        # The __init__.py create_artifact() function does not accept fast_path,
        # so we bypass it here and call the pipeline directly.
        from core.factory.orchestrator import FactoryPipeline

        pipeline = FactoryPipeline(conversation_id=None)
        result = await pipeline.create(creation_request, fast_path=request.fast_path)

        # 202 Accepted if awaiting human approval
        if not result.success and "requires approval" in result.message:
            return Response(
                content=result.model_dump_json(),
                status_code=202,
                media_type="application/json",
            )

        return result

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Factory create failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "",
    response_model=ArtifactListResponse,
    responses=response_with_errors(400),
    summary="List factory artifacts",
)
async def list_all(
    artifact_type: Optional[str] = Query(None, description="Filter by type: agent, tool, skill"),
    artifact_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    user=Depends(get_current_user),
) -> ArtifactListResponse:
    """List all factory-created artifacts with optional type/status filters."""
    try:
        type_filter = None
        if artifact_type:
            type_filter = _parse_artifact_type(artifact_type)

        status_filter = None
        if artifact_status:
            status_filter = _parse_artifact_status(artifact_status)

        results = await list_artifacts(artifact_type=type_filter, status=status_filter)
        return ArtifactListResponse(items=results, count=len(results))

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Factory list failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get(
    "/{name}",
    response_model=FactoryArtifact,
    responses=response_with_errors(404),
    summary="Get a factory artifact",
)
async def get_one(name: str, user=Depends(get_current_user)) -> FactoryArtifact:
    """Get details for a specific factory artifact by name."""
    try:
        artifact = await get_artifact(name)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact '{name}' not found")
        return artifact
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Factory get failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put(
    "/{name}",
    response_model=CreationResult,
    responses=response_with_errors(400, 404, 500),
    summary="Update a factory artifact",
)
async def update(
    name: str, request: UpdateRequest, user=Depends(get_current_user)
) -> CreationResult:
    """Update an existing artifact (creates a new version via TCST pipeline)."""
    try:
        artifact_type_enum = None
        if request.artifact_type:
            artifact_type_enum = _parse_artifact_type(request.artifact_type)

        creation_request = CreationRequest(
            goal=request.goal,
            suggested_name=request.suggested_name,
            artifact_type=artifact_type_enum,
            framework=request.framework,
            test_task=request.test_task,
            max_test_iterations=request.max_test_iterations,
        )

        result = await update_artifact(name, creation_request)
        return result

    except ValueError as exc:
        # update_artifact raises ValueError if not found
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Factory update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete(
    "/{name}",
    status_code=204,
    responses=response_with_errors(404),
    summary="Delete (archive) a factory artifact",
)
async def delete(name: str, user=Depends(get_current_user)) -> Response:
    """Soft-delete an artifact (archives it, retains files)."""
    try:
        deleted = await delete_artifact(name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Artifact '{name}' not found")
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Factory delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/{name}/approve",
    response_model=CreationResult,
    responses=response_with_errors(404, 500),
    summary="Approve a pending factory artifact",
)
async def approve(name: str, user=Depends(get_current_user)) -> CreationResult:
    """Approve a pending_approval artifact and resume the TCST pipeline.

    Retrieves the stored config and re-runs creation with skip_autonomy=True.
    """
    try:
        artifact = await get_artifact(name)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Artifact '{name}' not found")

        if artifact.status != ArtifactStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=400,
                detail=f"Artifact '{name}' is not pending approval (status: {artifact.status.value})",
            )

        from core.factory.orchestrator import FactoryPipeline
        from core.factory.scaffold import get_output_dir

        # Clean up partial scaffold from the initial (gated) creation attempt
        config = artifact.config_json or {}
        at_enum = _parse_artifact_type(artifact.artifact_type)
        expected_dir = get_output_dir(at_enum, artifact.name)
        if expected_dir.exists() and not artifact.artifact_path:
            import shutil

            shutil.rmtree(expected_dir, ignore_errors=True)
            logger.info("Cleaned up partial scaffold at %s before re-creation", expected_dir)

        # Hard-delete old pending_approval DB record so create() can register fresh
        # (soft-delete/archive would still block register's name-uniqueness check)
        from core.factory.registry import FactoryRegistry

        _registry = FactoryRegistry()
        _registry.hard_delete(name)
        logger.info("Removed pending_approval record for '%s' before re-creation", name)

        pipeline = FactoryPipeline(conversation_id=None)
        success, message = await pipeline.execute_approved_creation(
            {
                "config": config,
                "goal": config.get("goal", artifact.name),
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "framework": artifact.framework,
            }
        )

        # Re-fetch updated artifact for the response
        updated = await get_artifact(name)
        src = updated if updated else artifact
        return CreationResult(
            success=success,
            message=message,
            artifact_name=src.name,
            artifact_type=src.artifact_type,
            framework=src.framework,
            artifact_path=src.artifact_path or "",
            artifact_id=src.id,
            version=src.version,
            test_passed=src.test_passed,
            test_iterations=src.test_iterations,
            test_output=src.test_result,
            config_json=src.config_json or {},
            created_at=src.created_at,
            duration_seconds=0,
            deduplication_warnings=[],
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Factory approve failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Factory approve failed: {exc}")

@router.post(
    "/{name}/rollback",
    response_model=CreationResult,
    responses=response_with_errors(400, 404),
    summary="Rollback artifact to a previous version",
)
async def rollback(
    name: str, request: RollbackRequest, user=Depends(get_current_user)
) -> CreationResult:
    """Rollback an artifact to a specified previous version.

    Re-scaffolds from stored config and re-runs tests.
    """
    try:
        result = await rollback_artifact(name, request.version)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Factory rollback failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")
