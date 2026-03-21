"""Dryade Database.

Provides SQLAlchemy models and session management.

IMPORTANT: All models must be imported here to be created by init_db().
"""

from core.database.migrate import run_migrations
from core.database.models import (
    # Factory Registry (Phase 120-04)
    ArtifactVersionRecord,
    # Audit & Security
    AuditLog,
    # Base
    Base,
    CacheEntry,
    Checkpoint,
    Conversation,
    # Cost & Cache
    CostRecord,
    DatasetGeneration,
    # Escalation & Suggestion (Phase 120-04)
    EscalationHistoryRecord,
    # Execution Planning
    ExecutionPlan,
    # Extension Pipeline
    ExtensionExecution,
    ExtensionTimeline,
    FactoryArtifactRecord,
    # Failure History (Phase 120-04)
    FailureHistoryRecord,
    FileOperation,
    # File Safety
    FileScanResult,
    # Skills
    MarkdownSkill,
    Message,
    # Model Configuration
    ModelConfig,
    PlanExecutionResult,
    # Projects & Conversations
    Project,
    ProviderApiKey,
    # Relevance Signals (Phase 120-04)
    RelevanceSignalRecord,
    ResourceShare,
    # Security & Validation
    SanitizationEvent,
    ScenarioExecutionResult,
    SecurityEvent,
    SuggestionLogRecord,
    ToolResult,
    TrainedModel,
    # Trainer Plugin
    TrainingJob,
    # User & Auth
    User,
    UserInvite,
    # Notifications (Phase 70.2)
    UserNotification,
    ValidationFailure,
    # Workflows
    Workflow,
    WorkflowExecutionResult,
)
from core.database.session import (
    drop_db,
    get_engine,
    get_session,
    get_session_factory,
    init_db,
)

__all__ = [
    # Base
    "Base",
    # User & Auth
    "User",
    "UserInvite",
    "ResourceShare",
    # Projects & Conversations
    "Project",
    "Conversation",
    "Message",
    "ToolResult",
    "Checkpoint",
    # Cost & Cache
    "CostRecord",
    "CacheEntry",
    # File Safety
    "FileScanResult",
    "FileOperation",
    # Security & Validation
    "SanitizationEvent",
    "ValidationFailure",
    # Extension Pipeline
    "ExtensionExecution",
    "ExtensionTimeline",
    # Execution Planning
    "ExecutionPlan",
    "PlanExecutionResult",
    # Workflows
    "Workflow",
    "WorkflowExecutionResult",
    "ScenarioExecutionResult",
    # Audit & Security
    "AuditLog",
    "SecurityEvent",
    # Model Configuration
    "ModelConfig",
    "ProviderApiKey",
    # Skills
    "MarkdownSkill",
    # Trainer Plugin
    "TrainingJob",
    "TrainedModel",
    "DatasetGeneration",
    # Notifications (Phase 70.2)
    "UserNotification",
    # Factory Registry (Phase 120-04)
    "FactoryArtifactRecord",
    "ArtifactVersionRecord",
    "RelevanceSignalRecord",
    "EscalationHistoryRecord",
    "SuggestionLogRecord",
    # Failure History (Phase 120-04)
    "FailureHistoryRecord",
    # Session
    "get_engine",
    "get_session",
    "get_session_factory",
    "init_db",
    "drop_db",
    # Migrations
    "run_migrations",
]
