"""Cost Tracking API Routes.

Migrated from plugin to core in Phase 191. These routes are unconditionally
available to all users (community, team, enterprise).

Endpoints for viewing LLM usage costs across the system.
Uses hybrid storage: in-memory for real-time session costs and database
for historical persistence. Cost records include model, tokens, and USD amounts.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.api.models.openapi import response_with_errors
from core.auth.dependencies import get_current_user, get_db, require_admin
from core.cost_tracker.pricing import PricingService
from core.cost_tracker.tracker import get_cost_summary, get_cost_tracker
from core.database.models import CostRecord as DBCostRecord
from core.logs import get_logger

logger = get_logger(__name__)
router = APIRouter()

def _group_by_field(records: list[DBCostRecord], field: str) -> dict[str, float]:
    """Group records by a field and sum costs."""
    result: dict[str, float] = {}
    for r in records:
        key = getattr(r, field, "unknown") or "unknown"
        result[key] = result.get(key, 0) + r.cost_usd
    return result

def _get_breakdown_list(records: list[DBCostRecord], field: str) -> list["CostBreakdownItem"]:
    """Group records by a field and return list of breakdown items."""
    groups = {}
    for r in records:
        key = getattr(r, field, "unknown") or "unknown"
        if key not in groups:
            groups[key] = {"key": key, "total_cost": 0.0, "total_tokens": 0, "request_count": 0}

        groups[key]["total_cost"] += r.cost_usd
        groups[key]["total_tokens"] += r.input_tokens + r.output_tokens
        groups[key]["request_count"] += 1

    return [CostBreakdownItem(**item) for item in groups.values()]

def _get_template_breakdown(records: list[DBCostRecord]) -> list["TemplateCostItem"]:
    """Group records by template_id and return breakdown items."""
    groups: dict[int, dict] = {}
    for r in records:
        tid = getattr(r, "template_id", None)
        if tid is None:
            continue
        if tid not in groups:
            groups[tid] = {
                "template_id": tid,
                "total_cost": 0.0,
                "total_tokens": 0,
                "request_count": 0,
            }
        groups[tid]["total_cost"] += r.cost_usd
        groups[tid]["total_tokens"] += r.input_tokens + r.output_tokens
        groups[tid]["request_count"] += 1

    return [TemplateCostItem(**item) for item in groups.values()]

# Response Models
class CostSummaryResponse(BaseModel):
    """Aggregated cost summary with breakdowns by agent, model, and template."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_cost_usd": 12.345678,
                "total_input_tokens": 500000,
                "total_output_tokens": 100000,
                "by_agent": {"research_agent": 5.0, "writer_agent": 7.345678},
                "by_model": {"claude-3-opus": 10.0, "claude-3-haiku": 2.345678},
                "by_template": {1: 8.0, 2: 4.345678},
                "record_count": 150,
            }
        }
    )

    total_cost_usd: float = Field(..., description="Total cost in USD across all matching records")
    total_input_tokens: int = Field(
        ..., description="Total input tokens across all matching records"
    )
    total_output_tokens: int = Field(
        ..., description="Total output tokens across all matching records"
    )
    by_agent: dict[str, float] = Field(..., description="Cost breakdown by agent name")
    by_model: dict[str, float] = Field(..., description="Cost breakdown by model name")
    by_template: dict[int, float] = Field(
        default_factory=dict, description="Cost breakdown by template ID"
    )
    record_count: int = Field(..., description="Number of cost records matching the query")

class CostRecordItem(BaseModel):
    """Individual cost record with token counts and metadata."""

    id: int = Field(..., description="Unique record identifier")
    model: str = Field(..., description="LLM model used for this request")
    agent: str | None = Field(None, description="Agent that made the request")
    user_id: str | None = Field(None, description="User associated with this cost")
    conversation_id: str | None = Field(None, description="Conversation this cost belongs to")
    task_id: str | None = Field(None, description="Task ID associated with this cost")
    input_tokens: int = Field(..., description="Number of input tokens")
    output_tokens: int = Field(..., description="Number of output tokens")
    cost_usd: float = Field(..., description="Cost in USD for this request")
    timestamp: datetime = Field(..., description="When the request was made")
    template_id: int | None = Field(None, description="Template ID if from template execution")
    template_version_id: int | None = Field(None, description="Template version ID")

class CostRecordsResponse(BaseModel):
    """Response containing a list of cost records."""

    items: list[CostRecordItem] = Field(..., description="List of typed cost record items")
    total: int = Field(..., description="Total number of records matching the query")
    has_more: bool = Field(False, description="Whether more records are available")

class CostBreakdownItem(BaseModel):
    """Cost breakdown for a specific category (model, agent, etc.)."""

    key: str = Field(..., description="The category key (e.g. model name, agent name)")
    total_cost: float = Field(..., description="Total cost in USD")
    total_tokens: int = Field(..., description="Total tokens used")
    request_count: int = Field(..., description="Number of requests")

class TemplateCostItem(BaseModel):
    """Cost breakdown for a specific template."""

    template_id: int = Field(..., description="Template ID")
    total_cost: float = Field(..., description="Total cost in USD")
    total_tokens: int = Field(..., description="Total tokens used")
    request_count: int = Field(..., description="Number of requests")

class CostClearResponse(BaseModel):
    """Response after clearing in-memory cost records."""

    status: str = Field(..., description="Status of the clear operation")
    note: str = Field(..., description="Important note about what was cleared")

# Pricing Models
class ModelPricingItem(BaseModel):
    """Single model pricing entry."""

    model_name: str
    provider: str | None
    input_cost_per_token: float
    output_cost_per_token: float
    source: str  # "litellm" | "manual"
    updated_at: datetime | None
    updated_by: str | None

class ModelPricingListResponse(BaseModel):
    """Paginated pricing list."""

    items: list[ModelPricingItem]
    total: int
    has_more: bool

class ModelPricingUpdate(BaseModel):
    """Request body for updating model pricing."""

    input_cost_per_token: float = Field(..., ge=0)
    output_cost_per_token: float = Field(..., ge=0)

class PricingSyncResponse(BaseModel):
    """Response after litellm sync."""

    synced: int
    skipped_manual: int
    total: int

class PricingStatsResponse(BaseModel):
    """Pricing statistics."""

    total_models: int
    by_source: dict[str, int]
    by_provider: dict[str, int]

@router.get(
    "",
    response_model=CostSummaryResponse,
    responses=response_with_errors(401, 500),
)
async def get_costs(
    conversation_id: str | None = Query(None, description="Filter by conversation ID"),
    start_date: datetime | None = Query(
        None, description="Filter records after this timestamp (ISO 8601)"
    ),
    end_date: datetime | None = Query(
        None, description="Filter records before this timestamp (ISO 8601)"
    ),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CostSummaryResponse:
    """Get aggregated cost summary from database.

    Users see only their own costs. Admins see all.
    """
    try:
        user_id = user.get("sub")

        query = db.query(DBCostRecord)
        if user.get("role") != "admin":
            query = query.filter(DBCostRecord.user_id == user_id)
        if conversation_id:
            query = query.filter(DBCostRecord.conversation_id == conversation_id)
        if start_date:
            query = query.filter(DBCostRecord.timestamp >= start_date)
        if end_date:
            query = query.filter(DBCostRecord.timestamp <= end_date)

        records = query.all()
        total_cost = sum(r.cost_usd for r in records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)

        by_agent = _group_by_field(records, "agent")
        by_model = _group_by_field(records, "model")
        by_template: dict[int, float] = {}
        for r in records:
            tid = getattr(r, "template_id", None)
            if tid is not None:
                by_template[tid] = by_template.get(tid, 0) + r.cost_usd

        return CostSummaryResponse(
            total_cost_usd=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            by_agent=by_agent,
            by_model=by_model,
            by_template=by_template,
            record_count=len(records),
        )
    except Exception as e:
        logger.error(f"Failed to get costs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cost data") from e

@router.get(
    "/records",
    response_model=CostRecordsResponse,
    responses=response_with_errors(401, 500),
)
async def get_cost_records(
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of records to return (1-1000)"
    ),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    agent: str | None = Query(None, description="Filter by agent name"),
    conversation_id: str | None = Query(None, description="Filter by conversation ID"),
    start_date: datetime | None = Query(
        None, description="Filter records after this timestamp (ISO 8601)"
    ),
    end_date: datetime | None = Query(
        None, description="Filter records before this timestamp (ISO 8601)"
    ),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CostRecordsResponse:
    """Get individual cost records from database.

    Users see only their own records. Admins see all.
    """
    try:
        query = db.query(DBCostRecord)
        if user.get("role") != "admin":
            query = query.filter(DBCostRecord.user_id == user["sub"])
        if agent:
            query = query.filter(DBCostRecord.agent == agent)
        if conversation_id:
            query = query.filter(DBCostRecord.conversation_id == conversation_id)
        if start_date:
            query = query.filter(DBCostRecord.timestamp >= start_date)
        if end_date:
            query = query.filter(DBCostRecord.timestamp <= end_date)

        total_count = query.count()
        records = query.order_by(DBCostRecord.timestamp.desc()).offset(offset).limit(limit).all()

        return CostRecordsResponse(
            items=[r.to_dict() for r in records],
            total=total_count,
            has_more=total_count > offset + limit,
        )
    except Exception as e:
        logger.error(f"Failed to get cost records: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cost records") from e

@router.get(
    "/by-conversation/{conversation_id}",
    response_model=CostSummaryResponse,
    responses=response_with_errors(401, 500),
)
async def get_costs_by_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CostSummaryResponse:
    """Get cost breakdown for a specific conversation.

    Users see only their own conversation costs. Admins see all.
    """
    try:
        query = db.query(DBCostRecord).filter(DBCostRecord.conversation_id == conversation_id)
        if user.get("role") != "admin":
            query = query.filter(DBCostRecord.user_id == user["sub"])
        records = query.all()

        total_cost = sum(r.cost_usd for r in records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)

        by_template: dict[int, float] = {}
        for r in records:
            tid = getattr(r, "template_id", None)
            if tid is not None:
                by_template[tid] = by_template.get(tid, 0) + r.cost_usd

        return CostSummaryResponse(
            total_cost_usd=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            by_agent=_group_by_field(records, "agent"),
            by_model=_group_by_field(records, "model"),
            by_template=by_template,
            record_count=len(records),
        )
    except Exception as e:
        logger.error(f"Failed to get costs by conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation costs") from e

@router.get(
    "/by-user/{user_id}",
    response_model=list[CostBreakdownItem],
    responses=response_with_errors(401, 403, 500),
)
async def get_costs_by_user(
    user_id: str,
    start_date: datetime | None = Query(
        None, description="Filter records after this timestamp (ISO 8601)"
    ),
    end_date: datetime | None = Query(
        None, description="Filter records before this timestamp (ISO 8601)"
    ),
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CostBreakdownItem]:
    """Get cost breakdown by model for a specific user (admin only)."""
    try:
        query = db.query(DBCostRecord).filter(DBCostRecord.user_id == user_id)
        if start_date:
            query = query.filter(DBCostRecord.timestamp >= start_date)
        if end_date:
            query = query.filter(DBCostRecord.timestamp <= end_date)

        records = query.all()
        return _get_breakdown_list(records, "model")
    except Exception as e:
        logger.error(f"Failed to get costs by user: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user costs") from e

@router.delete(
    "/clear",
    response_model=CostClearResponse,
    responses=response_with_errors(401, 500),
)
async def clear_costs(user: dict = Depends(get_current_user)) -> CostClearResponse:
    """Clear in-memory cost records for the current session.

    Database records are preserved for historical reporting.
    """
    tracker = get_cost_tracker()
    tracker.clear()
    return CostClearResponse(
        status="cleared", note="In-memory records cleared. Database records preserved."
    )

@router.get(
    "/by-agent",
    response_model=list[CostBreakdownItem],
    responses=response_with_errors(401, 500),
)
async def get_costs_by_agent(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CostBreakdownItem]:
    """Get cost breakdown by agent from database.

    Users see only their own data. Admins see all.
    """
    try:
        query = db.query(DBCostRecord)
        if user.get("role") != "admin":
            query = query.filter(DBCostRecord.user_id == user["sub"])
        records = query.all()
        return _get_breakdown_list(records, "agent")
    except Exception as e:
        logger.error(f"Failed to get costs by agent: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve agent costs") from e

@router.get(
    "/by-model",
    response_model=list[CostBreakdownItem],
    responses=response_with_errors(401, 500),
)
async def get_costs_by_model(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CostBreakdownItem]:
    """Get cost breakdown by model from database.

    Users see only their own data. Admins see all.
    """
    try:
        query = db.query(DBCostRecord)
        if user.get("role") != "admin":
            query = query.filter(DBCostRecord.user_id == user["sub"])
        records = query.all()
        return _get_breakdown_list(records, "model")
    except Exception as e:
        logger.error(f"Failed to get costs by model: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model costs") from e

@router.get(
    "/by-template",
    response_model=list[TemplateCostItem],
    responses=response_with_errors(401, 500),
)
async def get_costs_by_template(
    include_non_template: bool = Query(
        False, description="Include ad-hoc executions as template_id=0"
    ),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TemplateCostItem]:
    """Get cost breakdown by template from database.

    Users see only their own data. Admins see all.
    """
    try:
        query = db.query(DBCostRecord)
        if user.get("role") != "admin":
            query = query.filter(DBCostRecord.user_id == user["sub"])
        if not include_non_template:
            query = query.filter(DBCostRecord.template_id.isnot(None))
        records = query.all()
        return _get_template_breakdown(records)
    except Exception as e:
        logger.error(f"Failed to get costs by template: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve template costs") from e

@router.get(
    "/realtime",
    response_model=CostSummaryResponse,
    responses=response_with_errors(401, 500),
)
async def get_realtime_costs(user: dict = Depends(get_current_user)):
    """Get real-time in-memory cost summary for current session.

    For historical costs persisted to database, use GET /costs instead.
    """
    return get_cost_summary()

# =============================================================================
# Pricing Management Routes
# =============================================================================

_pricing_service = PricingService()

def _pricing_to_item(p) -> ModelPricingItem:
    return ModelPricingItem(
        model_name=p.model_name,
        provider=p.provider,
        input_cost_per_token=p.input_cost_per_token,
        output_cost_per_token=p.output_cost_per_token,
        source=p.source,
        updated_at=p.updated_at,
        updated_by=p.updated_by,
    )

@router.get(
    "/pricing/stats",
    response_model=PricingStatsResponse,
    responses=response_with_errors(401, 500),
)
async def get_pricing_stats(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PricingStatsResponse:
    """Get pricing statistics: total models, by source, by provider."""
    try:
        stats = _pricing_service.get_stats(db)
        return PricingStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Failed to get pricing stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pricing stats") from e

@router.post(
    "/pricing/sync",
    response_model=PricingSyncResponse,
    responses=response_with_errors(401, 403, 500, 503),
)
async def sync_pricing(
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PricingSyncResponse:
    """Sync model pricing from litellm (admin only).

    Manual overrides (source='manual') are preserved.
    """
    try:
        result = _pricing_service.sync_from_litellm(db, updated_by=user.get("sub", "admin"))
        return PricingSyncResponse(**result)
    except ImportError:
        raise HTTPException(status_code=503, detail="litellm is not installed")
    except Exception as e:
        logger.error(f"Failed to sync pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync pricing from litellm") from e

@router.get(
    "/pricing",
    response_model=ModelPricingListResponse,
    responses=response_with_errors(401, 500),
)
async def get_pricing_list(
    search: str | None = Query(None, description="Search by model name"),
    provider: str | None = Query(None, description="Filter by provider"),
    source: str | None = Query(None, description="Filter by source (litellm or manual)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ModelPricingListResponse:
    """List all model pricing (paginated, filterable)."""
    try:
        items, total = _pricing_service.get_all(
            db, search=search, provider=provider, source=source, limit=limit, offset=offset
        )
        return ModelPricingListResponse(
            items=[_pricing_to_item(p) for p in items],
            total=total,
            has_more=total > offset + limit,
        )
    except Exception as e:
        logger.error(f"Failed to get pricing list: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pricing data") from e

@router.put(
    "/pricing/{model_name:path}",
    response_model=ModelPricingItem,
    responses=response_with_errors(401, 403, 500),
)
async def update_model_pricing(
    model_name: str,
    body: ModelPricingUpdate,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ModelPricingItem:
    """Update pricing for a model (admin only). Sets source='manual'."""
    try:
        updated = _pricing_service.update_pricing(
            db,
            model_name=model_name,
            input_cost=body.input_cost_per_token,
            output_cost=body.output_cost_per_token,
            updated_by=user.get("sub", "admin"),
        )
        return _pricing_to_item(updated)
    except Exception as e:
        logger.error(f"Failed to update pricing for {model_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model pricing") from e

@router.get(
    "/pricing/{model_name:path}",
    response_model=ModelPricingItem,
    responses=response_with_errors(401, 404, 500),
)
async def get_model_pricing(
    model_name: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ModelPricingItem:
    """Get pricing for a specific model."""
    try:
        item = _pricing_service.get_by_model(db, model_name)
        if not item:
            raise HTTPException(status_code=404, detail=f"No pricing found for model: {model_name}")
        return _pricing_to_item(item)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pricing for {model_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model pricing") from e
