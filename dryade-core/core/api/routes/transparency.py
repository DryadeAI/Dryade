"""Transparency API Routes (EU AI Act Article 52 compliance).

Public AI system disclosure endpoint, admin-only decision audit trail
with filtering/pagination/statistics, and human oversight metrics
(EU AI Act Article 14).

Target: ~250 LOC
"""

import math
import os
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.auth.audit import log_audit
from core.auth.dependencies import get_current_user, get_db, require_admin
from core.database.ai_decision_log import AIDecisionLog
from core.database.models import WorkflowApprovalAuditLog, WorkflowApprovalRequest
from core.utils.time import utcnow

router = APIRouter()

@router.get("/transparency")
async def get_transparency():
    """Public AI system disclosure (EU AI Act Article 52).

    Returns metadata about the AI system's capabilities, purposes,
    and data processing practices. No authentication required.
    """
    return JSONResponse(
        content={
            "system_name": "Dryade AI Orchestration Platform",
            "system_version": os.environ.get("DRYADE_VERSION", "1.0.0"),
            "ai_disclosure": os.environ.get(
                "DRYADE_AI_DISCLOSURE",
                "Dryade uses AI models to process requests, route tasks, and generate "
                "responses. All AI interactions are logged for transparency and oversight.",
            ),
            "models_configured": os.environ.get("DRYADE_MODELS_LIST", "User-configured LLM models"),
            "purposes": [
                "Conversational AI assistance",
                "Task orchestration and routing",
                "Workflow automation",
                "Knowledge retrieval",
            ],
            "data_processing_summary": (
                "User inputs are processed by configured LLM providers. No training on user data."
            ),
            "human_oversight": (
                "Human-in-the-loop approval available for high-risk operations "
                "via workflow approval system."
            ),
            "risk_classification": os.environ.get("DRYADE_AI_RISK_LEVEL", "limited"),
            "privacy_policy_url": os.environ.get(
                "DRYADE_PRIVACY_URL", "/docs/compliance/privacy-policy"
            ),
            "transparency_updated_at": utcnow().isoformat(),
        }
    )

def _build_decision_query(
    db: Session,
    model_id: str | None = None,
    provider: str | None = None,
    orchestration_mode: str | None = None,
    risk_level: str | None = None,
    human_override: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Build a filtered AI decision log query."""
    query = db.query(AIDecisionLog)
    if model_id:
        query = query.filter(AIDecisionLog.model_id == model_id)
    if provider:
        query = query.filter(AIDecisionLog.provider == provider)
    if orchestration_mode:
        query = query.filter(AIDecisionLog.orchestration_mode == orchestration_mode)
    if risk_level:
        query = query.filter(AIDecisionLog.risk_level == risk_level)
    if human_override is not None:
        query = query.filter(AIDecisionLog.human_override == human_override)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(AIDecisionLog.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(AIDecisionLog.created_at <= dt_to)
        except ValueError:
            pass
    return query

@router.get("/admin/ai-decisions")
async def get_ai_decisions(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
    model_id: str | None = Query(None, description="Filter by model ID"),
    provider: str | None = Query(None, description="Filter by provider"),
    orchestration_mode: str | None = Query(None, description="Filter by mode"),
    risk_level: str | None = Query(None, description="Filter by risk level"),
    human_override: bool | None = Query(None, description="Filter by human override"),
    date_from: str | None = Query(None, description="ISO date range start"),
    date_to: str | None = Query(None, description="ISO date range end"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
):
    """Admin-only: query AI decision audit trail with filters and pagination."""
    query = _build_decision_query(
        db, model_id, provider, orchestration_mode, risk_level, human_override, date_from, date_to
    )
    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))
    entries = (
        query.order_by(AIDecisionLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return JSONResponse(
        content={
            "entries": [e.to_dict() for e in entries],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    )

@router.get("/admin/ai-decisions/summary")
async def get_ai_decisions_summary(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Admin-only: aggregate statistics for AI decision audit trail."""
    total = db.query(func.count(AIDecisionLog.id)).scalar() or 0

    if total == 0:
        return JSONResponse(
            content={
                "total_decisions": 0,
                "by_model": {},
                "by_provider": {},
                "by_risk_level": {},
                "human_overrides": 0,
                "override_rate": 0.0,
                "avg_confidence": None,
                "avg_latency_ms": None,
                "period": {"from": None, "to": None},
            }
        )

    # Aggregate counts by dimension
    by_model = dict(
        db.query(AIDecisionLog.model_id, func.count(AIDecisionLog.id))
        .group_by(AIDecisionLog.model_id)
        .all()
    )
    by_provider = dict(
        db.query(AIDecisionLog.provider, func.count(AIDecisionLog.id))
        .group_by(AIDecisionLog.provider)
        .all()
    )
    by_risk = dict(
        db.query(AIDecisionLog.risk_level, func.count(AIDecisionLog.id))
        .group_by(AIDecisionLog.risk_level)
        .all()
    )

    human_overrides = (
        db.query(func.count(AIDecisionLog.id))
        .filter(AIDecisionLog.human_override == True)  # noqa: E712
        .scalar()
        or 0
    )

    avg_confidence = db.query(func.avg(AIDecisionLog.confidence)).scalar()
    avg_latency = db.query(func.avg(AIDecisionLog.latency_ms)).scalar()

    oldest = db.query(func.min(AIDecisionLog.created_at)).scalar()
    newest = db.query(func.max(AIDecisionLog.created_at)).scalar()

    return JSONResponse(
        content={
            "total_decisions": total,
            "by_model": by_model,
            "by_provider": by_provider,
            "by_risk_level": by_risk,
            "human_overrides": human_overrides,
            "override_rate": round(human_overrides / total, 4) if total else 0.0,
            "avg_confidence": round(avg_confidence, 4) if avg_confidence is not None else None,
            "avg_latency_ms": round(avg_latency, 2) if avg_latency is not None else None,
            "period": {
                "from": oldest.isoformat() if oldest else None,
                "to": newest.isoformat() if newest else None,
            },
        }
    )

# ---------------------------------------------------------------------------
# Human Oversight (EU AI Act Article 14)
# ---------------------------------------------------------------------------

class OverrideRequest(BaseModel):
    """Body for documenting a human override of an AI decision."""

    reason: str

@router.get("/admin/oversight/metrics")
async def get_oversight_metrics(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Admin-only: human oversight metrics (EU AI Act Article 14).

    Returns override rate, pending approvals, average review time,
    decisions grouped by risk level, and workflow approval stats.
    """
    # --- AI decision log stats ---
    total_decisions = db.query(func.count(AIDecisionLog.id)).scalar() or 0
    human_overrides = (
        db.query(func.count(AIDecisionLog.id))
        .filter(AIDecisionLog.human_override == True)  # noqa: E712
        .scalar()
        or 0
    )
    override_rate = round(human_overrides / total_decisions, 4) if total_decisions else 0.0

    decisions_by_risk = dict(
        db.query(AIDecisionLog.risk_level, func.count(AIDecisionLog.id))
        .group_by(AIDecisionLog.risk_level)
        .all()
    )

    # --- Workflow approval stats ---
    pending_approvals = (
        db.query(func.count(WorkflowApprovalRequest.id))
        .filter(WorkflowApprovalRequest.status == "pending")
        .scalar()
        or 0
    )

    # Average review time: resolved_at - created_at for resolved requests
    resolved = (
        db.query(WorkflowApprovalRequest)
        .filter(WorkflowApprovalRequest.resolved_at.isnot(None))
        .all()
    )
    if resolved:
        durations = [
            (r.resolved_at - r.created_at).total_seconds()
            for r in resolved
            if r.resolved_at and r.created_at
        ]
        avg_review_time_seconds = round(sum(durations) / len(durations), 2) if durations else None
    else:
        avg_review_time_seconds = None

    # Approval audit log counts
    approval_total = db.query(func.count(WorkflowApprovalAuditLog.id)).scalar() or 0
    approved_count = (
        db.query(func.count(WorkflowApprovalAuditLog.id))
        .filter(WorkflowApprovalAuditLog.action == "approved")
        .scalar()
        or 0
    )
    rejected_count = (
        db.query(func.count(WorkflowApprovalAuditLog.id))
        .filter(WorkflowApprovalAuditLog.action == "rejected")
        .scalar()
        or 0
    )

    return JSONResponse(
        content={
            "total_decisions": total_decisions,
            "human_overrides": human_overrides,
            "override_rate": override_rate,
            "pending_approvals": pending_approvals,
            "avg_review_time_seconds": avg_review_time_seconds,
            "decisions_by_risk": decisions_by_risk,
            "approval_decisions": {
                "total": approval_total,
                "approved": approved_count,
                "rejected": rejected_count,
            },
        }
    )

@router.post("/admin/ai-decisions/{decision_id}/override")
async def override_ai_decision(
    decision_id: int,
    body: OverrideRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _admin: dict = Depends(require_admin),
):
    """Admin-only: document a human override of an AI decision.

    Creates a NEW immutable entry in ai_decision_log referencing the
    original decision. The original record is never modified.
    """
    original = db.query(AIDecisionLog).filter(AIDecisionLog.id == decision_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="AI decision not found")

    override_entry = AIDecisionLog(
        request_id=original.request_id,
        model_id=original.model_id,
        provider=original.provider,
        orchestration_mode=original.orchestration_mode,
        prompt_category=original.prompt_category,
        confidence=original.confidence,
        alternatives_considered=original.alternatives_considered,
        reasoning=f"Human override of decision #{decision_id}: {body.reason}",
        human_review_required=True,
        human_reviewer_id=current_user.get("sub"),
        human_override=True,
        override_reason=body.reason,
        token_count=original.token_count,
        latency_ms=original.latency_ms,
        risk_level=original.risk_level,
        created_at=datetime.now(UTC),
    )
    db.add(override_entry)
    db.commit()
    db.refresh(override_entry)

    # Audit trail
    background_tasks.add_task(
        log_audit,
        db,
        current_user.get("sub", "unknown"),
        "ai_decision_override",
        "ai_decision",
        str(decision_id),
        None,
        {
            "original_decision_id": decision_id,
            "override_entry_id": override_entry.id,
            "reason": body.reason,
        },
        "warning",
    )

    return JSONResponse(
        content={
            "status": "override_recorded",
            "original_decision_id": decision_id,
            "override_entry": override_entry.to_dict(),
        }
    )
