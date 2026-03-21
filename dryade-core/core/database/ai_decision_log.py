"""AI Decision Log model for EU AI Act Article 12 transparency logging.

Records model decisions, confidence scores, human overrides, and risk levels.
Hash chain columns enable tamper detection for regulatory audits.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from core.database.models import Base

class AIDecisionLog(Base):
    """EU AI Act transparency log for AI-assisted decisions.

    Tracks every model invocation with metadata required for Article 12
    compliance: model identity, confidence, alternatives considered,
    human review status, and risk classification.
    """

    __tablename__ = "ai_decision_log"
    __table_args__ = (
        Index("ix_ai_decision_log_model_id", "model_id"),
        Index("ix_ai_decision_log_provider", "provider"),
        Index("ix_ai_decision_log_created_at", "created_at"),
        Index("ix_ai_decision_log_risk_level", "risk_level"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=True)
    model_id = Column(String(128), nullable=False)
    provider = Column(String(64), nullable=False)
    orchestration_mode = Column(String(32), nullable=True)
    prompt_category = Column(String(32), nullable=True)
    confidence = Column(Float, nullable=True)
    alternatives_considered = Column(JSON, default=list)
    reasoning = Column(Text, nullable=True)
    human_review_required = Column(Boolean, default=False)
    human_reviewer_id = Column(String(64), nullable=True)
    human_override = Column(Boolean, default=False)
    override_reason = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    risk_level = Column(String(16), nullable=True, default="limited")
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        """Return all fields as a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "request_id": self.request_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "orchestration_mode": self.orchestration_mode,
            "prompt_category": self.prompt_category,
            "confidence": self.confidence,
            "alternatives_considered": self.alternatives_considered,
            "reasoning": self.reasoning,
            "human_review_required": self.human_review_required,
            "human_reviewer_id": self.human_reviewer_id,
            "human_override": self.human_override,
            "override_reason": self.override_reason,
            "token_count": self.token_count,
            "latency_ms": self.latency_ms,
            "risk_level": self.risk_level,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
