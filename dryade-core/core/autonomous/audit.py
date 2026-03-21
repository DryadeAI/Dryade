"""Comprehensive audit logging for autonomous execution.

Provides full decision trail for regulatory compliance (EU AI Act, FDA, RBI/SEBI).
Uses structlog for tamper-evident, queryable audit entries.
"""

import logging
import os
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.autonomous.models import Thought

_persist_logger = logging.getLogger(__name__)

class AuditEntry(BaseModel):
    """Comprehensive audit trail entry for autonomous actions.

    Required for regulatory compliance:
    - EU AI Act (transparency requirements)
    - FDA (clinical AI audit trails)
    - Financial regulators (RBI/SEBI/SEC)
    """

    # Identity
    entry_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str

    # Actor
    initiator_type: Literal["user", "agent", "scheduler", "webhook"] = "user"
    initiator_id: str
    agent_id: str | None = None

    # Action
    action_type: Literal[
        "thought",
        "tool_call",
        "skill_exec",
        "plan",
        "replan",
        "escalation",
        "leash_exceeded",
        "approval_granted",
        "approval_denied",
        "self_dev_start",
        "self_dev_artifact",
        "self_dev_staged",
        "capability_negotiation",
        "skill_creation_request",
        "skill_creation_complete",
    ]
    action_details: dict[str, Any] = Field(default_factory=dict)

    # Context
    skill_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] | None = None

    # Decision
    confidence: float | None = None
    reasoning: str | None = None
    alternatives_considered: list[str] | None = None

    # Outcome
    success: bool = True
    error: str | None = None
    duration_ms: int = 0
    tokens_used: int = 0

    # Human-in-the-loop
    human_review_required: bool = False
    human_reviewer_id: str | None = None
    human_decision: str | None = None
    human_notes: str | None = None

    # EU AI Act transparency metadata
    model_id: str | None = None
    provider: str | None = None
    orchestration_mode: str | None = None  # chat/plan/orchestrate/tool_selection
    prompt_category: str | None = None  # Category label, NOT prompt content
    risk_level: str = "limited"  # minimal/limited/high
    human_override: bool = False
    override_reason: str | None = None

class AuditLogger:
    """Structured audit logger for autonomous execution.

    Logs all decisions, tool calls, and state changes with full context.
    Uses structlog for JSON-structured, queryable output.
    """

    def __init__(self, session_id: str | None = None, initiator_id: str = "system"):
        """Initialize audit logger.

        Args:
            session_id: Unique session identifier (generated if not provided)
            initiator_id: ID of user/system initiating execution
        """
        self.session_id = session_id or str(uuid4())
        self.initiator_id = initiator_id
        self._entries: list[AuditEntry] = []

        # Configure structlog for this logger
        self._log = structlog.get_logger("dryade.autonomous.audit").bind(
            session_id=self.session_id, initiator_id=self.initiator_id
        )

    def _create_entry(self, action_type: str, **kwargs: Any) -> AuditEntry:
        """Create and store audit entry."""
        entry = AuditEntry(
            session_id=self.session_id,
            initiator_id=self.initiator_id,
            action_type=action_type,  # type: ignore[arg-type]
            **kwargs,
        )
        self._entries.append(entry)
        return entry

    def log_thought(self, thought: Thought) -> AuditEntry:
        """Log LLM reasoning step."""
        entry = self._create_entry(
            action_type="thought",
            skill_name=thought.skill_name,
            inputs=thought.inputs,
            confidence=thought.confidence,
            reasoning=thought.reasoning,
            action_details={
                "is_final": thought.is_final,
                "answer": thought.answer,
            },
        )
        self._log.info(
            "thought",
            skill=thought.skill_name,
            confidence=thought.confidence,
            is_final=thought.is_final,
        )
        return entry

    def log_action(
        self,
        skill_name: str,
        inputs: dict[str, Any],
        result: Any,
        success: bool = True,
        error: str | None = None,
        duration_ms: int = 0,
        tokens_used: int = 0,
    ) -> AuditEntry:
        """Log skill/tool execution."""
        entry = self._create_entry(
            action_type="skill_exec",
            skill_name=skill_name,
            inputs=inputs,
            outputs={"result": str(result)[:1000]} if result else None,  # Truncate large outputs
            success=success,
            error=error,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
        )
        self._log.info(
            "skill_exec", skill=skill_name, success=success, duration_ms=duration_ms, error=error
        )
        return entry

    def log_plan(self, plan: list[str], goal: str) -> AuditEntry:
        """Log plan creation."""
        entry = self._create_entry(
            action_type="plan",
            action_details={"goal": goal, "steps": plan, "step_count": len(plan)},
        )
        self._log.info("plan_created", goal=goal, steps=len(plan))
        return entry

    def log_replan(self, reason: str, new_plan: list[str]) -> AuditEntry:
        """Log plan revision."""
        entry = self._create_entry(
            action_type="replan",
            action_details={
                "reason": reason,
                "new_steps": new_plan,
                "step_count": len(new_plan),
            },
        )
        self._log.info("replan", reason=reason, steps=len(new_plan))
        return entry

    def log_leash_exceeded(self, reasons: list[str]) -> AuditEntry:
        """Log leash constraint exceeded."""
        entry = self._create_entry(
            action_type="leash_exceeded", success=False, action_details={"reasons": reasons}
        )
        self._log.warning("leash_exceeded", reasons=reasons)
        return entry

    def log_escalation(
        self, reason: str, context: dict[str, Any], requires_human: bool = True
    ) -> AuditEntry:
        """Log human escalation request."""
        entry = self._create_entry(
            action_type="escalation",
            action_details={"reason": reason, "context": context},
            human_review_required=requires_human,
        )
        self._log.warning("escalation", reason=reason, requires_human=requires_human)
        return entry

    def log_approval(
        self, approved: bool, reviewer_id: str, notes: str | None = None
    ) -> AuditEntry:
        """Log human approval decision."""
        entry = self._create_entry(
            action_type="approval_granted" if approved else "approval_denied",
            human_reviewer_id=reviewer_id,
            human_decision="approved" if approved else "denied",
            human_notes=notes,
        )
        self._log.info("approval", approved=approved, reviewer=reviewer_id)
        return entry

    def log_self_dev_start(self, goal: str, dev_session_id: str) -> AuditEntry:
        """Log self-development session start."""
        entry = self._create_entry(
            action_type="self_dev_start",
            action_details={"goal": goal, "dev_session_id": dev_session_id},
        )
        self._log.info("self_dev_start", goal=goal, dev_session=dev_session_id)
        return entry

    def log_self_dev_artifact(
        self, artifact_type: str, path: str, signed: bool = False
    ) -> AuditEntry:
        """Log self-development artifact creation."""
        entry = self._create_entry(
            action_type="self_dev_artifact",
            action_details={"artifact_type": artifact_type, "path": path, "signed": signed},
        )
        self._log.info("self_dev_artifact", type=artifact_type, path=path, signed=signed)
        return entry

    def log_self_dev_staged(self, output_path: str, artifacts: list[str]) -> AuditEntry:
        """Log self-development staging completion."""
        entry = self._create_entry(
            action_type="self_dev_staged",
            action_details={
                "output_path": output_path,
                "artifacts": artifacts,
                "artifact_count": len(artifacts),
            },
        )
        self._log.info("self_dev_staged", output=output_path, artifacts=len(artifacts))
        return entry

    def log_capability_negotiation(
        self,
        request: str,
        status: str,
        bound_tools: list[str],
        alternatives: list[str] | None = None,
    ) -> AuditEntry:
        """Log capability negotiation result.

        Args:
            request: Natural language capability request
            status: Negotiation outcome (auto_bound, degraded, failed, etc.)
            bound_tools: List of tools/skills that were bound
            alternatives: Alternative capabilities suggested

        Returns:
            Created AuditEntry
        """
        entry = self._create_entry(
            action_type="capability_negotiation",
            action_details={
                "request": request,
                "status": status,
                "bound_tools": bound_tools,
                "alternatives": alternatives or [],
            },
            success=status in ("auto_bound", "degraded"),
        )
        self._log.info(
            "capability_negotiation",
            request=request[:50],
            status=status,
            bound_count=len(bound_tools),
        )
        return entry

    def log_skill_creation_request(
        self,
        goal: str,
        skill_name: str | None = None,
        triggered_by: str = "capability_gap",
    ) -> AuditEntry:
        """Log skill creation request.

        Args:
            goal: What the skill should accomplish
            skill_name: Requested name for the skill (optional)
            triggered_by: What triggered the creation (capability_gap, user_request, etc.)

        Returns:
            Created AuditEntry
        """
        entry = self._create_entry(
            action_type="skill_creation_request",
            action_details={
                "goal": goal,
                "requested_name": skill_name,
                "triggered_by": triggered_by,
            },
        )
        self._log.info(
            "skill_creation_request",
            goal=goal[:50],
            skill_name=skill_name,
        )
        return entry

    def log_skill_creation_complete(
        self,
        skill_name: str,
        success: bool,
        signed: bool = False,
        error: str | None = None,
        validation_issues: list[str] | None = None,
    ) -> AuditEntry:
        """Log skill creation completion.

        Args:
            skill_name: Name of the created skill
            success: Whether creation succeeded
            signed: Whether skill was signed
            error: Error message if failed
            validation_issues: Validation issues encountered

        Returns:
            Created AuditEntry
        """
        entry = self._create_entry(
            action_type="skill_creation_complete",
            skill_name=skill_name,
            success=success,
            error=error,
            action_details={
                "signed": signed,
                "validation_issues": validation_issues or [],
            },
        )
        self._log.info(
            "skill_creation_complete",
            skill=skill_name,
            success=success,
            signed=signed,
        )
        return entry

    def get_entries(self) -> list[AuditEntry]:
        """Get all audit entries for this session."""
        return list(self._entries)

    def get_entries_by_type(self, action_type: str) -> list[AuditEntry]:
        """Get audit entries filtered by action type."""
        return [e for e in self._entries if e.action_type == action_type]

    def to_json(self) -> list[dict[str, Any]]:
        """Export entries as JSON-serializable list."""
        return [entry.model_dump(mode="json") for entry in self._entries]

    def persist_entry(self, entry: AuditEntry, db: Session) -> None:
        """Persist an audit entry to the ai_decision_log table.

        Never raises -- logs errors and returns silently to avoid
        breaking the main request path.
        """
        try:
            from datetime import UTC as _UTC
            from datetime import datetime as _dt

            from sqlalchemy import text as _text

            from core.auth.audit import compute_entry_hash
            from core.database.ai_decision_log import AIDecisionLog

            now = _dt.now(_UTC)
            next_id = db.execute(_text("SELECT nextval('ai_decision_log_id_seq')")).scalar()
            model_id_val = entry.model_id or "unknown"
            provider_val = entry.provider or "unknown"
            entry_hash = compute_entry_hash(
                next_id, model_id_val, now.isoformat(), provider_val, None,
            )

            record = AIDecisionLog(
                id=next_id,
                request_id=getattr(entry, "request_id", None),
                model_id=model_id_val,
                provider=provider_val,
                orchestration_mode=entry.orchestration_mode,
                prompt_category=entry.prompt_category,
                confidence=entry.confidence,
                alternatives_considered=entry.alternatives_considered or [],
                reasoning=entry.reasoning,
                human_review_required=entry.human_review_required,
                human_reviewer_id=entry.human_reviewer_id,
                human_override=entry.human_override,
                override_reason=entry.override_reason,
                token_count=entry.tokens_used,
                latency_ms=entry.duration_ms,
                risk_level=entry.risk_level,
                created_at=now,
                entry_hash=entry_hash,
            )
            db.add(record)
            db.commit()
        except Exception:
            db.rollback()
            _persist_logger.exception("Failed to persist AI decision to database")

def log_ai_decision(
    db: Session,
    model_id: str,
    provider: str,
    orchestration_mode: str | None = None,
    prompt_category: str | None = None,
    confidence: float | None = None,
    alternatives_considered: list[str] | None = None,
    reasoning: str | None = None,
    human_override: bool = False,
    token_count: int | None = None,
    latency_ms: int | None = None,
    risk_level: str | None = None,
) -> None:
    """Convenience function to persist an AI decision to the database.

    Creates an AIDecisionLog directly without going through AuditEntry.
    Never raises -- logs errors and returns silently (same pattern as log_audit).
    """
    try:
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from sqlalchemy import text as _text

        from core.auth.audit import compute_entry_hash
        from core.database.ai_decision_log import AIDecisionLog

        effective_risk = risk_level or os.environ.get("DRYADE_AI_RISK_LEVEL", "limited")

        now = _dt.now(_UTC)
        next_id = db.execute(_text("SELECT nextval('ai_decision_log_id_seq')")).scalar()
        entry_hash = compute_entry_hash(
            next_id, model_id, now.isoformat(), provider, None,
        )

        record = AIDecisionLog(
            id=next_id,
            model_id=model_id,
            provider=provider,
            orchestration_mode=orchestration_mode,
            prompt_category=prompt_category,
            confidence=confidence,
            alternatives_considered=alternatives_considered or [],
            reasoning=reasoning,
            human_override=human_override,
            token_count=token_count,
            latency_ms=latency_ms,
            risk_level=effective_risk,
            created_at=now,
            entry_hash=entry_hash,
        )
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        _persist_logger.exception("Failed to persist AI decision to database")
