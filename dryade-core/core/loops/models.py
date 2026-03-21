"""SQLAlchemy models for the Loop Engine.

Two tables:
- scheduled_loops: Loop definitions with schedule and target configuration.
- loop_executions: Execution history with status tracking and results.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

# Direct module import to avoid circular import through core.database.__init__
# Using __import__ with fromlist bypasses the package __init__.py
_models_mod = __import__("core.database.models", fromlist=["Base"])
Base = _models_mod.Base

# =============================================================================
# Enums
# =============================================================================

class TargetType(str, enum.Enum):
    """Executable target types for scheduled loops."""

    WORKFLOW = "workflow"
    AGENT = "agent"
    SKILL = "skill"
    ORCHESTRATOR_TASK = "orchestrator_task"

class TriggerType(str, enum.Enum):
    """Schedule trigger patterns."""

    CRON = "cron"
    INTERVAL = "interval"
    ONESHOT = "oneshot"

class ExecutionStatus(str, enum.Enum):
    """Loop execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# =============================================================================
# Models
# =============================================================================

class ScheduledLoop(Base):
    """A scheduled loop definition.

    Defines what to execute (target_type + target_id), when (schedule),
    and how (config). Registered with APScheduler for automatic dispatch.
    """

    __tablename__ = "scheduled_loops"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), unique=True, nullable=False, index=True)
    target_type = Column(
        Enum(TargetType, name="target_type_enum", native_enum=False),
        nullable=False,
    )
    target_id = Column(String(255), nullable=False)
    trigger_type = Column(
        Enum(TriggerType, name="trigger_type_enum", native_enum=False),
        nullable=False,
    )
    schedule = Column(String(255), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=True)

    # Ownership
    created_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScheduledLoop(id={self.id}, name='{self.name}', "
            f"target={self.target_type}, enabled={self.enabled})>"
        )

class LoopExecution(Base):
    """A single execution record for a scheduled loop.

    Tracks status, duration, result, and errors for each run.
    """

    __tablename__ = "loop_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    loop_id = Column(
        String(36),
        ForeignKey("scheduled_loops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(ExecutionStatus, name="execution_status_enum", native_enum=False),
        nullable=False,
        default=ExecutionStatus.PENDING,
    )
    started_at = Column(DateTime, nullable=False, index=True, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    attempt = Column(Integer, nullable=False, default=1)
    trigger_source = Column(String(32), nullable=False, default="schedule")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    # Composite index for execution history queries (loop_id + started_at DESC)
    __table_args__ = (Index("ix_loop_executions_loop_started", "loop_id", started_at.desc()),)

    def __repr__(self) -> str:
        return f"<LoopExecution(id={self.id}, loop_id={self.loop_id}, status={self.status})>"
