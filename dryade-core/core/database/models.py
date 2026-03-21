"""SQLAlchemy models for Dryade.

Target: ~200 LOC
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, validates

Base = declarative_base()

class User(Base):
    """User account with password-based authentication.

    Supports both local auth (password) and external auth (Zitadel plugin).
    External users have is_external=True and null password_hash.
    """

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email"),)

    id = Column(String(64), primary_key=True)  # UUID
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # Null for external auth
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(512), nullable=True)
    role = Column(String(32), default="member")  # admin, member
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # Email verified
    is_external = Column(Boolean, default=False)  # External auth (Zitadel)
    external_provider = Column(String(64), nullable=True)  # zitadel, google, etc
    preferences = Column(JSON, default=dict)

    # MFA (TOTP) — all nullable for backward compatibility
    totp_secret = Column(String(64), nullable=True)  # TOTP base32 seed
    mfa_enabled = Column(Boolean, default=False)  # TOTP fully configured
    mfa_grace_deadline = Column(DateTime, nullable=True)  # Enforcement grace period deadline
    mfa_enabled_at = Column(
        DateTime, nullable=True
    )  # When MFA was enabled (for refresh token invalidation)
    first_seen = Column(DateTime, default=lambda: datetime.now(UTC))
    last_seen = Column(DateTime, default=lambda: datetime.now(UTC))
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships (ForeignKey constraints added in migration g1_postgresql_fk_indexes)
    conversations = relationship(
        "Conversation", foreign_keys="Conversation.user_id", backref="owner"
    )
    workflows = relationship("Workflow", foreign_keys="Workflow.user_id", backref="owner")

class Project(Base):
    """Project for grouping conversations (ChatGPT-like feature).

    Projects allow users to organize related conversations together.
    Each project can have a custom name, description, icon, and color.
    """

    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_user_id", "user_id"),)

    id = Column(String(64), primary_key=True)  # UUID
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # Index defined in __table_args__
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(32), nullable=True)  # Emoji or icon name
    color = Column(String(7), nullable=True)  # Hex color like #3B82F6
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationship to conversations
    conversations = relationship(
        "Conversation", back_populates="project", foreign_keys="Conversation.project_id"
    )

class Conversation(Base):
    """Conversation record."""

    __tablename__ = "conversations"

    id = Column(String(64), primary_key=True)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id = Column(
        String(64), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title = Column(String(255), nullable=True)
    mode = Column(String(16), default="chat")  # chat, crew, flow
    status = Column(String(16), default="active")  # active, completed, archived
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    checkpoints = relationship(
        "Checkpoint", back_populates="conversation", cascade="all, delete-orphan"
    )
    execution_plans = relationship(
        "ExecutionPlan", back_populates="conversation", cascade="all, delete-orphan"
    )
    project = relationship("Project", back_populates="conversations")

class Message(Base):
    """Chat message record."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # system, user, assistant, tool
    content = Column(Text, nullable=True)
    name = Column(String(64), nullable=True)  # For tool messages
    tool_call_id = Column(String(64), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    conversation = relationship("Conversation", back_populates="messages")
    tool_results = relationship(
        "ToolResult", back_populates="message", cascade="all, delete-orphan"
    )

class ToolResult(Base):
    """Tool execution result."""

    __tablename__ = "tool_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    tool_name = Column(String(64), nullable=False)
    tool_call_id = Column(String(64), nullable=True)
    arguments = Column(JSON, default=dict)
    result = Column(Text, nullable=True)
    success = Column(Boolean, default=True)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    message = relationship("Message", back_populates="tool_results")

class Checkpoint(Base):
    """Execution checkpoint for resume."""

    __tablename__ = "checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id"), nullable=False, index=True)
    checkpoint_id = Column(String(64), nullable=False, unique=True)
    state = Column(JSON, nullable=False)
    step = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    conversation = relationship("Conversation", back_populates="checkpoints")

class CostRecord(Base):
    """LLM cost tracking record.

    Tracks per-request LLM usage for cost analysis, budget tracking, and usage auditing.
    Supports filtering by user, conversation, agent, model, template, and time range.
    """

    __tablename__ = "cost_records"
    __table_args__ = (
        Index("ix_cost_records_user_id", "user_id"),
        Index("ix_cost_records_conversation_id", "conversation_id"),
        Index("ix_cost_records_timestamp", "timestamp"),
        Index("ix_cost_records_model", "model"),
        Index("ix_cost_records_template_id", "template_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    model = Column(String(100), nullable=False)
    agent = Column(String(100), default="unknown", nullable=False)
    task_id = Column(String(36), nullable=True)
    conversation_id = Column(String(36), nullable=True)
    user_id = Column(String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    # Phase 72: Template cost dimension
    template_id = Column(Integer, nullable=True)  # Link to org_templates.id
    template_version_id = Column(Integer, nullable=True)  # Link to template_versions.id

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "model": self.model,
            "agent": self.agent,
            "task_id": self.task_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "template_id": self.template_id,
            "template_version_id": self.template_version_id,
        }

class RoutingMetric(Base):
    """Routing decision metrics for self-modification pipeline.

    Tracks how routing decisions are made (tool-based vs fallback),
    enabling data-driven optimization of the self-mod routing path.
    Phase 115.1.
    """

    __tablename__ = "routing_metrics"
    __table_args__ = (
        Index("ix_routing_metrics_timestamp", "timestamp"),
        Index("ix_routing_metrics_message_hash", "message_hash"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    message_hash = Column(String(64), nullable=False)
    hint_fired = Column(Boolean, default=False)
    hint_type = Column(String(32), nullable=True)
    llm_tool_called = Column(String(64), nullable=True)
    fallback_activated = Column(Boolean, default=False)
    user_approved = Column(Boolean, nullable=True)
    latency_ms = Column(Integer, default=0)
    # Phase 115.5: Optimization pipeline extensions
    tool_arguments_hash = Column(String(32), nullable=True)  # sha256[:16] of serialized arguments
    success_outcome = Column(Boolean, nullable=True)  # whether the tool call ultimately succeeded
    model_tier_used = Column(
        String(16), nullable=True
    )  # which model tier was active during routing

class PromptVersionRecord(Base):
    """Version-controlled prompt for optimization pipeline.

    Stores prompt templates with versioning, activation state, and linkage
    to optimization cycles. Supports rollback via parent_version_id chain.
    Phase 115.5.
    """

    __tablename__ = "prompt_versions"
    __table_args__ = (
        Index("ix_prompt_versions_prompt_key_tier", "prompt_key", "model_tier"),
        Index("ix_prompt_versions_active", "is_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(String(32), unique=True, nullable=False)
    prompt_key = Column(String(64), nullable=False)
    model_tier = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    created_by = Column(String(64), nullable=False)
    optimization_cycle_id = Column(String(64), nullable=True)
    parent_version_id = Column(String(32), nullable=True)
    metrics_snapshot = Column(JSON, nullable=True)

class OptimizationCycleRecord(Base):
    """Autonomous optimization cycle record.

    Tracks each optimization cycle: metrics window analyzed, examples
    added/rejected, prompt version created, holdout validation score.
    Phase 115.5.
    """

    __tablename__ = "optimization_cycles"
    __table_args__ = (Index("ix_optimization_cycles_status", "status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(String(64), unique=True, nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    metrics_window_start = Column(DateTime, nullable=False)
    metrics_window_end = Column(DateTime, nullable=False)
    total_metrics_analyzed = Column(Integer, default=0)
    examples_added = Column(Integer, default=0)
    examples_rejected = Column(Integer, default=0)
    prompt_version_created = Column(String(32), nullable=True)
    holdout_score = Column(Float, nullable=True)
    status = Column(String(16), default="running")

class MemoryBlockRecord(Base):
    """Persistent memory block for agent-scoped context. Phase 115.3."""

    __tablename__ = "memory_blocks"
    __table_args__ = (Index("ix_memory_blocks_agent_label", "agent_id", "label", unique=True),)

    id = Column(String(64), primary_key=True)
    agent_id = Column(String(128), nullable=False)  # conversation_id as initial scope
    label = Column(String(64), nullable=False)
    value = Column(Text, default="")
    description = Column(String(256), default="")
    char_limit = Column(Integer, default=5000)
    read_only = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

class ModelPricing(Base):
    """Model pricing data for cost calculation.

    Populated from litellm.model_cost (1500+ models) with support for
    admin-editable manual overrides. Manual overrides are preserved during
    litellm sync.
    """

    __tablename__ = "model_pricing"
    __table_args__ = (Index("ix_model_pricing_provider", "provider"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(200), unique=True, nullable=False, index=True)
    provider = Column(String(100), nullable=True)
    input_cost_per_token = Column(Float, default=0.0)
    output_cost_per_token = Column(Float, default=0.0)
    source = Column(String(20), default="litellm")  # "litellm" | "manual"
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    updated_by = Column(String(100), nullable=True)  # user_id for manual edits

class CacheEntry(Base):
    """Semantic cache entry."""

    __tablename__ = "cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=True)  # Store as JSON array
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=True)

class FileScanResult(Base):
    """File malware scan result history."""

    __tablename__ = "file_scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String(512), nullable=False, index=True)
    file_hash = Column(String(64), nullable=False, index=True)
    clamav_safe = Column(Boolean, default=True)
    clamav_threats = Column(JSON, default=list)
    yara_safe = Column(Boolean, default=True)
    yara_matches = Column(JSON, default=list)
    scan_time = Column(Float, nullable=True)  # Total scan time in seconds
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class FileOperation(Base):
    """File operation audit log."""

    __tablename__ = "file_operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation = Column(String(32), nullable=False)  # read, write, edit, delete, upload
    file_path = Column(String(512), nullable=False, index=True)
    result = Column(String(16), nullable=False)  # success, blocked, error
    threats = Column(JSON, default=list)
    error = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class SanitizationEvent(Base):
    """Output sanitization event log."""

    __tablename__ = "sanitization_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    context = Column(String(16), nullable=False)  # html, sql, shell, json, plain
    route = Column(String(128), nullable=True)
    original_length = Column(Integer, nullable=False)
    sanitized_length = Column(Integer, nullable=False)
    modifications = Column(JSON, default=list)  # List of modifications made
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class ValidationFailure(Base):
    """Input validation failure log."""

    __tablename__ = "validation_failures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_type = Column(String(64), nullable=False)  # ChatMessage, ToolArgs, etc.
    route = Column(String(128), nullable=True)
    errors = Column(JSON, default=list)  # List of validation errors
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class ExtensionExecution(Base):
    """Extension pipeline execution tracking."""

    __tablename__ = "extension_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    conversation_id = Column(String(64), nullable=True, index=True)
    extension_name = Column(String(64), nullable=False)
    duration_ms = Column(Float, nullable=False)
    cache_hit = Column(Boolean, default=False)
    healed = Column(Boolean, default=False)
    threats_found = Column(JSON, default=list)
    validation_errors = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class ExtensionTimeline(Base):
    """Extension timeline for request flow tracking."""

    __tablename__ = "extension_timeline"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    conversation_id = Column(String(64), nullable=True, index=True)
    operation = Column(String(64), nullable=False)  # agent_execute, tool_call, etc.
    extensions_applied = Column(JSON, default=list)  # Ordered list of extensions
    total_duration_ms = Column(Float, nullable=False)
    outcomes = Column(JSON, default=dict)  # cache_hit, healed, threats_found, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class ExecutionPlan(Base):
    """Generated execution plan for planner mode."""

    __tablename__ = "execution_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'executing', 'completed', 'failed', 'cancelled')",
            name="ck_execution_plans_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(64), ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    nodes = Column(JSON, nullable=False)  # List of node definitions
    edges = Column(JSON, default=list)  # List of dependency edges
    reasoning = Column(Text, nullable=True)  # LLM reasoning for plan generation
    confidence = Column(Float, nullable=True)  # Confidence score (0.0-1.0)
    status = Column(
        String(32), nullable=False, default="draft"
    )  # draft, approved, executing, completed, failed, cancelled
    metadata_ = Column("metadata", JSON, default=dict)
    ai_generated = Column(Boolean, default=False, nullable=False)  # Flag for AI-generated plans
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    conversation = relationship("Conversation", back_populates="execution_plans")
    execution_results = relationship(
        "PlanExecutionResult", back_populates="plan", cascade="all, delete-orphan"
    )

class PlanExecutionResult(Base):
    """Execution result for a plan."""

    __tablename__ = "plan_execution_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('executing', 'completed', 'failed', 'cancelled', 'timeout')",
            name="ck_plan_execution_results_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("execution_plans.id"), nullable=False, index=True)
    execution_id = Column(
        String(64), nullable=False, unique=True, index=True
    )  # Unique ID for this execution
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(32), nullable=False)  # executing, completed, failed, cancelled, timeout
    node_results = Column(
        JSON, default=list
    )  # Per-node execution results with status, duration, output, errors
    total_cost = Column(Float, nullable=True)  # Total cost in USD
    user_feedback_rating = Column(Integer, nullable=True)  # 1-5 star rating
    user_feedback_comment = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    plan = relationship("ExecutionPlan", back_populates="execution_results")

class Workflow(Base):
    """Reusable workflow template for ReactFlow editor.

    Workflows are templates that can be instantiated multiple times by different users.
    They store the complete WorkflowSchema (nodes, edges, metadata) as JSON.

    Lifecycle: draft → published → archived
    - draft: Can be edited, not available to others
    - published: Immutable, available based on is_public flag
    - archived: Hidden from listings, preserved for history
    """

    __tablename__ = "workflows"
    __table_args__ = (
        # Composite index for version queries
        Index("ix_workflows_name_version", "name", "version"),
        # Index on status for filtering
        Index("ix_workflows_status", "status"),
        # Unique constraint: prevent duplicate versions per user
        UniqueConstraint("name", "version", "user_id", name="uq_workflows_name_version_user"),
        # Check constraint: valid status values
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_workflows_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0.0")
    workflow_json = Column(JSON, nullable=False)  # WorkflowSchema as JSON
    status = Column(String(20), nullable=False, default="draft")  # draft, published, archived
    is_public = Column(Boolean, nullable=False, default=False)
    user_id = Column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )  # null = system workflow
    tags = Column(JSON, nullable=True, default=list)
    execution_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    published_at = Column(DateTime, nullable=True)

    # Relationship to execution results
    execution_results = relationship(
        "WorkflowExecutionResult", back_populates="workflow", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return string representation of Workflow."""
        return f"<Workflow(id={self.id}, name='{self.name}', version='{self.version}', status='{self.status}')>"

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "workflow_json": self.workflow_json,
            "status": self.status,
            "is_public": self.is_public,
            "user_id": self.user_id,
            "tags": self.tags or [],
            "execution_count": self.execution_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }

    @classmethod
    def from_schema(
        cls, schema, name: str, description: str = None, user_id: str = None
    ) -> "Workflow":
        """Create a Workflow from a WorkflowSchema object.

        Args:
            schema: WorkflowSchema instance
            name: Workflow name
            description: Optional description
            user_id: Optional creator user ID

        Returns:
            Workflow instance (not yet added to session)
        """
        return cls(
            name=name,
            description=description,
            version=schema.version,
            workflow_json=schema.model_dump(),
            user_id=user_id,
        )

    def increment_execution(self) -> None:
        """Increment execution count."""
        self.execution_count = (self.execution_count or 0) + 1

class ResourceShare(Base):
    """Sharing relationship between users and resources.

    Enables users to share resources (workflows, etc.) with other users
    with specific permission levels (view, edit).
    """

    __tablename__ = "resource_shares"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id", "user_id", name="uq_resource_share"),
        Index("ix_resource_shares_resource", "resource_type", "resource_id"),
        Index("ix_resource_shares_user_id", "user_id"),
        CheckConstraint("permission IN ('view', 'edit')", name="ck_resource_shares_permission"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_type = Column(String(32), nullable=False)  # workflow, conversation
    resource_id = Column(String(64), nullable=False)  # Support both int and UUID string IDs
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # Shared with (indexed in __table_args__)
    permission = Column(String(16), default="view")  # view, edit
    shared_by = Column(String(64), nullable=False)  # Owner who shared
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class UserInvite(Base):
    """User invitation record.

    Tracks invitations sent by one user to an email address with an intended
    permission level. This is used by the Profile page "Share" flow.
    """

    __tablename__ = "user_invites"
    __table_args__ = (
        UniqueConstraint("invited_by", "email", name="uq_user_invites_invited_by_email"),
        Index("ix_user_invites_invited_by", "invited_by"),
        Index("ix_user_invites_email", "email"),
        CheckConstraint(
            "permission IN ('view', 'edit', 'owner')", name="ck_user_invites_permission"
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked')", name="ck_user_invites_status"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    invited_by = Column(String(64), nullable=False)  # User ID who created the invite
    email = Column(String(255), nullable=False)
    permission = Column(String(16), nullable=False, default="view")
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

class WorkflowExecutionResult(Base):
    """Execution result for a workflow.

    Tracks individual workflow execution instances with per-node results,
    duration, cost, and error information.

    Status values: running, success, failed

    Phase 70.2 additions:
    - template_id: Link to OrgTemplate (if executed from org template)
    - template_version_id: Link to specific TemplateVersion used
    """

    __tablename__ = "workflow_execution_results"
    __table_args__ = (
        # Index for workflow execution history queries
        Index("ix_workflow_execution_results_workflow_id", "workflow_id"),
        # Index for user execution history
        Index("ix_workflow_execution_results_user_id", "user_id"),
        # Index for conversation association
        Index("ix_workflow_execution_results_conversation_id", "conversation_id"),
        # Index for template-based execution queries (Phase 70.2)
        Index("ix_workflow_execution_results_template_id", "template_id"),
        Index("ix_workflow_execution_results_template_version_id", "template_version_id"),
        # Check constraint: valid status values
        CheckConstraint(
            "status IN ('running', 'success', 'failed', 'paused')",
            name="ck_workflow_execution_results_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    user_id = Column(
        String(50), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )  # Executor user ID
    conversation_id = Column(String(50), nullable=True)  # Optional conversation association
    status = Column(String(20), nullable=False, default="running")  # running, success, failed
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Execution duration in milliseconds
    node_results = Column(JSON, nullable=True, default=list)  # Per-node outputs and durations
    final_result = Column(JSON, nullable=True)  # Final workflow output
    error = Column(Text, nullable=True)  # Error message if failed
    cost = Column(Float, nullable=True)  # Execution cost if available
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Phase 70.2: Template linkage (nullable - not all executions are from templates)
    # Using string references to avoid circular imports with plugin models
    template_id = Column(Integer, nullable=True)  # Link to org_templates.id
    template_version_id = Column(Integer, nullable=True)  # Link to template_versions.id

    # Relationship to Workflow
    workflow = relationship("Workflow", back_populates="execution_results")

    def __repr__(self) -> str:
        """Return string representation of WorkflowExecutionResult."""
        return (
            f"<WorkflowExecutionResult(id={self.id}, workflow_id={self.workflow_id}, "
            f"status='{self.status}', duration_ms={self.duration_ms})>"
        )

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "node_results": self.node_results or [],
            "final_result": self.final_result,
            "error": self.error,
            "cost": self.cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "template_id": self.template_id,
            "template_version_id": self.template_version_id,
        }

class WorkflowApprovalRequest(Base):
    """Pending approval request — workflow paused here."""

    __tablename__ = "workflow_approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_execution_id", "execution_id"),
        Index("ix_approval_requests_status", "status"),
        Index("ix_approval_requests_workflow_id", "workflow_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(Integer, ForeignKey("workflow_execution_results.id"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    node_id = Column(String(128), nullable=False)
    status = Column(
        String(32), default="pending"
    )  # pending, approved, rejected, modified, timed_out
    prompt = Column(Text, nullable=False)
    approver_type = Column(String(32), nullable=False)  # owner, specific_user, any_member
    approver_user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    display_fields = Column(JSON, default=list)
    state_snapshot = Column(JSON, nullable=False)  # Full serialized Flow state
    timeout_at = Column(DateTime(timezone=True), nullable=False)
    timeout_action = Column(String(16), nullable=False)  # approve, reject, escalate
    resolved_by = Column(String(64), nullable=True)  # user_id of approver
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    modified_fields = Column(JSON, nullable=True)  # Fields changed on Modify action
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return string representation of WorkflowApprovalRequest."""
        return (
            f"<WorkflowApprovalRequest(id={self.id}, workflow_id={self.workflow_id}, "
            f"node_id='{self.node_id}', status='{self.status}')>"
        )

class WorkflowApprovalAuditLog(Base):
    """Immutable audit trail for approval actions (SOC2 feed)."""

    __tablename__ = "workflow_approval_audit_logs"
    __table_args__ = (
        Index("ix_audit_log_request_id", "request_id"),
        Index("ix_audit_log_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("workflow_approval_requests.id"), nullable=False)
    actor_user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(
        String(32), nullable=False
    )  # notified, approved, rejected, modified, timed_out, escalated
    action_data = Column(JSON, nullable=True)  # Modified fields, escalation target, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return string representation of WorkflowApprovalAuditLog."""
        return (
            f"<WorkflowApprovalAuditLog(id={self.id}, request_id={self.request_id}, "
            f"action='{self.action}')>"
        )

class AuditLog(Base):
    """Audit log for user actions.

    Tracks sensitive operations for security auditing including
    login, create, update, delete, and share actions.

    Hash chain columns (prev_hash, entry_hash) enable tamper detection.
    event_severity supports compliance filtering (info/warning/critical).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_event_severity", "event_severity"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)  # login, create, update, delete, share
    resource_type = Column(String(32), nullable=True)
    resource_id = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    # Hash chain for tamper detection (SOC 2 / EU AI Act)
    prev_hash = Column(String(64), nullable=True)
    entry_hash = Column(String(64), nullable=True)
    event_severity = Column(String(16), nullable=True, default="info")

class SecurityEvent(Base):
    """Security and tamper detection events.

    Stores events from Plugin Manager for analytics.
    Event types: debugger_detected, integrity_violation, clock_manipulation,
    environment_suspicious, challenge_replay, decryption_failure
    """

    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_type_time", "event_type", "timestamp"),
        Index("ix_security_events_machine", "machine_fingerprint"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    received_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    machine_fingerprint = Column(String(12), nullable=False, index=True)
    details = Column(JSON, default=dict)
    core_version = Column(String(20), nullable=True)
    pm_version = Column(String(20), nullable=True)

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "machine_fingerprint": self.machine_fingerprint,
            "details": self.details,
            "core_version": self.core_version,
            "pm_version": self.pm_version,
        }

# =============================================================================
# GDPR / DSAR Models
# =============================================================================

class DSARRequest(Base):
    """GDPR Data Subject Access Request tracking.

    Tracks data export (Article 20) and erasure (Article 17) requests
    with a status lifecycle: pending -> processing -> ready -> completed -> expired.
    Table created in Alembic migration f3_add_dsar_consent_tables.
    """

    __tablename__ = "dsar_requests"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_type = Column(String(32), nullable=False)  # export, erasure
    status = Column(String(32), nullable=False, default="pending")
    download_url = Column(Text, nullable=True)
    download_expires_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

# =============================================================================
# Trainer Plugin Models
# =============================================================================

class TrainingJob(Base):
    """Training job tracking for fine-tuning operations.

    Supports job types: datagen, sft, dpo, eval
    Status values: pending, running, completed, failed, cancelled
    """

    __tablename__ = "training_jobs"
    __table_args__ = (Index("ix_training_jobs_user_status", "user_id", "status"),)

    id = Column(String(64), primary_key=True)  # UUID
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type = Column(String(32), nullable=False)  # datagen, sft, dpo, eval
    status = Column(
        String(32), nullable=False, default="pending"
    )  # pending, running, completed, failed, cancelled
    config = Column(JSON, default=dict)  # Job configuration (model, epochs, lr, etc.)
    progress = Column(Float, default=0.0)  # 0.0 to 1.0
    metrics = Column(JSON, nullable=True)  # Training metrics (loss, accuracy, etc.)
    error_message = Column(Text, nullable=True)
    dataset_path = Column(String(512), nullable=True)  # Path to training data
    output_path = Column(String(512), nullable=True)  # Path to saved model/adapter
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Relationships (TrainedModel.training_job_id and DatasetGeneration.job_id
    # still lack FK constraints — use primaryjoin pattern for these non-user columns)
    trained_model = relationship(
        "TrainedModel",
        primaryjoin="TrainingJob.id == foreign(TrainedModel.training_job_id)",
        uselist=False,
        backref="training_job",
    )
    dataset_generation = relationship(
        "DatasetGeneration",
        primaryjoin="TrainingJob.id == foreign(DatasetGeneration.job_id)",
        uselist=False,
        backref="training_job",
    )

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "job_type": self.job_type,
            "status": self.status,
            "config": self.config,
            "progress": self.progress,
            "metrics": self.metrics,
            "error_message": self.error_message,
            "dataset_path": self.dataset_path,
            "output_path": self.output_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class TrainedModel(Base):
    """Registry of trained model adapters.

    Tracks LoRA adapters trained via SFT/DPO with versioning support.
    Status values: training, ready, deprecated
    """

    __tablename__ = "trained_models"
    __table_args__ = (
        UniqueConstraint("name", "version", "user_id", name="uq_trained_models_name_version_user"),
        Index("ix_trained_models_user_id", "user_id"),
    )

    id = Column(String(64), primary_key=True)  # UUID
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # Human readable name
    model_family = Column(String(64), nullable=False)  # gemma, llama3
    base_model = Column(String(255), nullable=False)  # HuggingFace model ID
    adapter_path = Column(String(512), nullable=False)  # Path to LoRA adapter
    version = Column(String(32), nullable=False, default="1.0.0")  # Semver
    status = Column(String(32), nullable=False, default="training")  # training, ready, deprecated
    eval_metrics = Column(JSON, nullable=True)  # Evaluation results (accuracy, f1, etc.)
    training_job_id = Column(String(64), nullable=True)  # Link to TrainingJob (no FK)
    is_default = Column(Boolean, default=False)  # Default model for routing
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "model_family": self.model_family,
            "base_model": self.base_model,
            "adapter_path": self.adapter_path,
            "version": self.version,
            "status": self.status,
            "eval_metrics": self.eval_metrics,
            "training_job_id": self.training_job_id,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class DatasetGeneration(Base):
    """Synthetic dataset generation tracking.

    Tracks dataset generation jobs for creating training data from tools.
    Status values: generating, completed, failed
    """

    __tablename__ = "dataset_generations"
    __table_args__ = (Index("ix_dataset_generations_user_id", "user_id"),)

    id = Column(String(64), primary_key=True)  # UUID
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String(64), nullable=True)  # Link to TrainingJob (no FK)
    name = Column(String(255), nullable=False)
    output_path = Column(String(512), nullable=False)  # Path to JSONL file
    record_count = Column(Integer, default=0)
    config = Column(JSON, default=dict)  # Generation config (tools, count, etc.)
    status = Column(
        String(32), nullable=False, default="generating"
    )  # generating, completed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "job_id": self.job_id,
            "name": self.name,
            "output_path": self.output_path,
            "record_count": self.record_count,
            "config": self.config,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

# =============================================================================
# Model Configuration System
# =============================================================================

class ModelConfig(Base):
    """Per-user model configuration settings.

    Stores user preferences for each model capability type:
    - LLM (chat/completion)
    - Embedding (vector generation)
    - ASR (speech-to-text)
    - TTS (text-to-speech)
    - Vision (image understanding)
    """

    __tablename__ = "model_configs"
    __table_args__ = (Index("ix_model_configs_user_id", "user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # LLM settings
    llm_provider = Column(String(32), nullable=True)  # openai, anthropic, ollama, vllm
    llm_model = Column(String(128), nullable=True)
    llm_endpoint = Column(String(512), nullable=True)  # Custom endpoint URL

    # Embedding settings
    embedding_provider = Column(String(32), nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_endpoint = Column(String(512), nullable=True)  # Custom endpoint URL for embedding

    # Audio settings (ASR/TTS)
    asr_provider = Column(String(32), nullable=True)
    asr_model = Column(String(128), nullable=True)
    asr_endpoint = Column(String(512), nullable=True)  # Custom endpoint URL for ASR
    tts_provider = Column(String(32), nullable=True)
    tts_model = Column(String(128), nullable=True)

    # Vision/Multimodal settings
    vision_provider = Column(String(32), nullable=True)
    vision_model = Column(String(128), nullable=True)

    # Inference parameters (Phase 211) - JSON columns per capability
    llm_inference_params = Column(JSON, nullable=True)  # {"temperature": 0.7, "top_p": 0.9, ...}
    vision_inference_params = Column(JSON, nullable=True)  # Same structure as llm
    audio_inference_params = Column(JSON, nullable=True)  # Only timeout, max_tokens
    embedding_inference_params = Column(JSON, nullable=True)  # Reserved, currently empty

    # vLLM server parameters (separate from inference, requires restart)
    vllm_server_params = Column(JSON, nullable=True)  # {"gpu_memory_utilization": 0.9, ...}

    # LLM Fallback chain (Phase 146)
    fallback_chain = Column(
        Text, nullable=True
    )  # JSON: [{"provider": "openai", "model": "gpt-4o"}, ...]
    fallback_enabled = Column(Boolean, default=False, nullable=False, server_default="0")

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

class ProviderApiKey(Base):
    """Encrypted API key storage per provider per user.

    Supports global keys (one per provider) and optional per-model overrides.
    Keys are encrypted at rest using Fernet (AES-128-CBC).
    """

    __tablename__ = "provider_api_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "model_override", name="uq_provider_key"),
        Index("ix_provider_api_keys_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(32), nullable=False)  # openai, anthropic, google, groq, together
    key_encrypted = Column(Text, nullable=False)  # Fernet encrypted
    key_prefix = Column(String(8), nullable=True)  # First 4 chars for display (e.g., "sk-a...")
    is_global = Column(Boolean, default=True)  # Global or per-model override
    model_override = Column(String(128), nullable=True)  # If not global, which model
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

class CustomProvider(Base):
    """User-defined OpenAI-compatible provider.

    Stores custom provider definitions that appear alongside built-in
    providers in the Settings page. All custom providers use the
    OpenAI-compatible API pattern (/v1/chat/completions).
    """

    __tablename__ = "custom_providers"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_custom_provider_slug"),
        Index("ix_custom_providers_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    slug = Column(String(32), nullable=False)
    display_name = Column(String(128), nullable=False)
    base_url = Column(String(512), nullable=False)
    requires_api_key = Column(Boolean, default=False)
    capabilities = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

# =============================================================================
# AgentSkills (SKILL.md) Models
# =============================================================================

class MarkdownSkill(Base):
    """Persisted markdown skill metadata.

    Stores skill discovery metadata for API listing and management.
    The actual skill content is loaded from SKILL.md files.
    """

    __tablename__ = "markdown_skills"
    __table_args__ = (Index("ix_markdown_skills_plugin_id", "plugin_id"),)

    id = Column(String(64), primary_key=True)  # UUID
    name = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    plugin_id = Column(String(255), nullable=True)  # Parent plugin if from plugin
    skill_dir = Column(String(512), nullable=False)  # Path to skill directory
    metadata_ = Column("metadata", JSON, default=dict)  # Skill metadata (emoji, os, requires)
    enabled = Column(Boolean, default=True)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<MarkdownSkill(name={self.name}, plugin={self.plugin_id})>"

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "plugin_id": self.plugin_id,
            "skill_dir": self.skill_dir,
            "metadata": self.metadata_,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class ScenarioExecutionResult(Base):
    """Execution result for a workflow scenario.

    Tracks scenario-based executions (from workflow-scenarios endpoints)
    with per-node results, duration, and error information.

    Status values: running, completed, failed, cancelled, paused
    """

    __tablename__ = "scenario_execution_results"
    __table_args__ = (
        # Index for user execution history
        Index("ix_scenario_execution_results_user_id", "user_id"),
        # Index for scenario filtering
        Index("ix_scenario_execution_results_scenario_name", "scenario_name"),
        # Index for time-based queries
        Index("ix_scenario_execution_results_started_at", "started_at"),
        # Check constraint: valid status values
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled', 'paused')",
            name="ck_scenario_execution_results_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String(64), unique=True, nullable=False, index=True)  # UUID
    scenario_name = Column(String(100), nullable=False)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )  # User who triggered
    trigger_source = Column(String(20), nullable=False)  # chat, api, ui, schedule
    status = Column(
        String(20), nullable=False, default="running"
    )  # running, completed, failed, cancelled, paused
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Execution duration in milliseconds
    node_results = Column(
        JSON, nullable=True, default=list
    )  # Per-node outputs: [{node_id, status, output, duration_ms}]
    final_result = Column(JSON, nullable=True)  # Final workflow output
    error = Column(Text, nullable=True)  # Error message if failed
    inputs = Column(JSON, nullable=True, default=dict)  # Input values used
    # Phase 95.3.1: Template provenance metadata (GAP-T2)
    # Stores {"template_id": N, "template_version_id": N} for template-originated executions
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return string representation of ScenarioExecutionResult."""
        return (
            f"<ScenarioExecutionResult(id={self.id}, execution_id={self.execution_id}, "
            f"scenario_name='{self.scenario_name}', status='{self.status}')>"
        )

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "scenario_name": self.scenario_name,
            "user_id": self.user_id,
            "trigger_source": self.trigger_source,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "node_results": self.node_results or [],
            "final_result": self.final_result,
            "error": self.error,
            "inputs": self.inputs or {},
            "metadata": self.metadata_ or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

# =============================================================================
# Phase 70.2: User Notification System
# =============================================================================

# Notification types for enterprise templates
NOTIFICATION_TYPES = [
    "template_update",  # Template was updated
    "approval_request",  # Someone requested approval
    "approval_decision",  # Approval was granted/rejected
    "deprecation_warning",  # Template version deprecated
    "weekly_report",  # Weekly template usage summary
]

class UserNotification(Base):
    """User notification for enterprise template events.

    Persistent notification storage for template-related events like
    approvals, updates, deprecations, and usage reports.

    Attributes:
        id: Auto-generated primary key
        user_id: Target user ID (indexed)
        notification_type: Type of notification (template_update, approval_request, etc.)
        title: Short notification title
        body: Full notification content
        metadata: Additional data (template_id, version_id, etc.)
        is_read: Whether notification has been read
        created_at: When notification was created
    """

    __tablename__ = "user_notifications"
    __table_args__ = (
        # Composite index for efficient unread queries
        Index("ix_user_notifications_user_read", "user_id", "is_read"),
        # Index for time-based queries
        Index("ix_user_notifications_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)  # template_id, version_id, etc.
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return string representation of UserNotification."""
        return (
            f"<UserNotification(id={self.id}, user_id={self.user_id}, "
            f"type='{self.notification_type}', is_read={self.is_read})>"
        )

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "body": self.body,
            "metadata": self.metadata_ or {},
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

# =============================================================================
# Knowledge Source Persistence (Phase 94.1)
# =============================================================================

class KnowledgeSourceRecord(Base):
    """Persisted knowledge source metadata.

    Stores the registry information that was previously in-memory only.
    Qdrant stores the actual vectors; this table stores the metadata mapping.
    """

    __tablename__ = "knowledge_sources"

    id = Column(String(128), primary_key=True)  # e.g. "ks_document1"
    name = Column(String(255), nullable=False)
    source_type = Column(String(64), nullable=False)  # "PDFKnowledgeSource", etc.
    file_paths = Column(JSON, nullable=False, default=list)
    description = Column(Text, nullable=True)
    crew_ids = Column(JSON, nullable=False, default=list)
    agent_ids = Column(JSON, nullable=False, default=list)
    chunk_count = Column(Integer, nullable=False, default=0)
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

# =============================================================================
# Factory Registry (was factory_artifacts.db) -- Phase 120-04
# =============================================================================

class FactoryArtifactRecord(Base):
    """Persisted factory artifact (agent/tool/skill created by factory).

    Maps the raw SQL ``factory_artifacts`` table from core/factory/registry.py
    into a dialect-agnostic SQLAlchemy model.
    """

    __tablename__ = "factory_artifacts"
    __table_args__ = (
        Index("ix_factory_artifacts_type", "artifact_type"),
        Index("ix_factory_artifacts_status", "status"),
        Index("ix_factory_artifacts_name", "name"),
        Index("ix_factory_artifacts_created", "created_at"),
    )

    id = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False, unique=True)
    artifact_type = Column(String(32), nullable=False)  # agent, tool, skill
    framework = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="configuring")
    source_prompt = Column(Text, nullable=False)
    config_json = Column(Text, nullable=False, default="{}")
    artifact_path = Column(String(512), nullable=False)
    test_result = Column(Text, nullable=True)
    test_passed = Column(Integer, nullable=False, default=0)
    test_iterations = Column(Integer, nullable=False, default=0)
    trigger = Column(String(64), nullable=False, default="user")
    tags = Column(Text, nullable=False, default="[]")
    created_at = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=False)
    created_by = Column(String(64), nullable=False, default="factory")
    user_id = Column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

class ArtifactVersionRecord(Base):
    """Version history snapshot for factory artifacts."""

    __tablename__ = "artifact_versions"
    __table_args__ = (
        Index("ix_artifact_versions_artifact", "artifact_id"),
        UniqueConstraint("artifact_id", "version", name="uq_artifact_version"),
    )

    id = Column(String(64), primary_key=True)
    artifact_id = Column(
        String(64),
        ForeignKey("factory_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    config_json = Column(Text, nullable=False, default="{}")
    files_snapshot = Column(Text, nullable=False, default="[]")
    created_at = Column(String(64), nullable=False)
    rollback_reason = Column(Text, nullable=True)

class RelevanceSignalRecord(Base):
    """Detected relevance signal for factory gap detection."""

    __tablename__ = "relevance_signals"
    __table_args__ = (
        Index("ix_relevance_signals_type", "signal_type"),
        Index("ix_relevance_signals_status", "status"),
        Index("ix_relevance_signals_pattern", "pattern"),
        UniqueConstraint("signal_type", "pattern", name="uq_signal_type_pattern"),
    )

    id = Column(String(64), primary_key=True)
    signal_type = Column(String(64), nullable=False)
    pattern = Column(String(512), nullable=False)
    count = Column(Integer, nullable=False, default=1)
    confidence = Column(Float, nullable=False, default=0.0)
    example_queries = Column(Text, nullable=False, default="[]")
    suggested_type = Column(String(32), nullable=True)
    urgency = Column(String(32), nullable=False, default="batch")
    first_seen = Column(String(64), nullable=False)
    last_seen = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="open")
    resolved_artifact_id = Column(
        String(64),
        ForeignKey("factory_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )

class EscalationHistoryRecord(Base):
    """Factory escalation history entry."""

    __tablename__ = "escalation_history"
    __table_args__ = (Index("ix_escalation_history_created", "created_at"),)

    id = Column(String(64), primary_key=True)
    action_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=False, default="")
    conversation_id = Column(String(64), nullable=False, default="")
    suggested_name = Column(String(256), nullable=False, default="")
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(String(64), nullable=False)

class SuggestionLogRecord(Base):
    """Factory proactive suggestion log."""

    __tablename__ = "suggestion_log"
    __table_args__ = (Index("ix_suggestion_log_created", "created_at"),)

    id = Column(String(64), primary_key=True)
    category = Column(String(64), nullable=False, default="")
    status = Column(String(32), nullable=False, default="pending")
    session_id = Column(String(64), nullable=False, default="")
    created_at = Column(String(64), nullable=False)

# =============================================================================
# Failure History (was failure_history.db) -- Phase 120-04
# =============================================================================

class FailureHistoryRecord(Base):
    """Tool failure record for adaptive retry and circuit breaking."""

    __tablename__ = "failure_history"
    __table_args__ = (
        Index("ix_failure_history_tool", "tool_name"),
        Index("ix_failure_history_server", "server_name"),
        Index("ix_failure_history_timestamp", "timestamp"),
        Index("ix_failure_history_tool_category", "tool_name", "error_category"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(64), nullable=False)
    tool_name = Column(String(256), nullable=False)
    server_name = Column(String(256), nullable=False)
    error_category = Column(String(64), nullable=False)
    error_message = Column(Text, default="")
    action_taken = Column(String(64), nullable=False)
    recovery_success = Column(Integer, nullable=False)
    duration_ms = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    model_used = Column(String(128), default="")

# =============================================================================
# MFA Recovery Codes -- Phase 147-01
# =============================================================================

class MFARecoveryCode(Base):
    """MFA recovery codes — hashed with argon2, single-use.

    Separate table (not JSON column) for:
    - Atomic mark-as-used (prevents replay via concurrent requests)
    - Individual revocation / audit trail
    - No race conditions on concurrent verification
    """

    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (Index("ix_mfa_recovery_user", "user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash = Column(String(255), nullable=False)  # argon2 hash of recovery code
    used_at = Column(DateTime, nullable=True)  # Null = not yet used
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

# =============================================================================
# Clarify — Preference Memory (migrated from plugin to core, Phase 191)
# =============================================================================

class SavedPreference(Base):
    """User preference for clarification question.

    Stores answered questions with embeddings for semantic matching.
    Supports both global defaults and per-project overrides.

    Scope precedence: project > global (project_id=None)
    """

    __tablename__ = "clarify_preferences"
    __table_args__ = (
        Index("ix_clarify_preferences_user_project", "user_id", "project_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Ownership
    user_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=True, index=True)  # None = global default

    # Question matching
    question = Column(Text, nullable=False)  # Original question text
    question_normalized = Column(String(512), nullable=True)  # Lowercased, trimmed
    question_embedding = Column(JSON, nullable=False)  # List of floats (384 dimensions)

    # Answer storage
    answer = Column(JSON, nullable=False)  # Can be string, list, dict, number
    answer_type = Column(String(32), nullable=False)  # radio, checkbox, text, dropdown, etc.

    # Usage tracking
    used_count = Column(Integer, default=1)
    last_used = Column(DateTime, default=lambda: datetime.now(UTC))
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # Confidence threshold for this preference (user can adjust)
    match_threshold = Column(Float, default=0.85)

    @validates("question")
    def normalize_question(self, key, value):
        """Auto-populate normalized question on set."""
        if value:
            # Store normalized version for potential exact-match fallback
            self.question_normalized = value.lower().strip()[:512]
        return value

    def __repr__(self):
        return f"<SavedPreference(id={self.id}, user={self.user_id}, q='{self.question[:30]}...')>"

# =============================================================================
# Trace Events -- Phase 194 (migrated from raw sqlite3)
# =============================================================================

class TraceEvent(Base):
    """CrewAI event capture and storage for local observability."""

    __tablename__ = "trace_events"
    __table_args__ = (
        Index("ix_trace_events_timestamp", "timestamp"),
        Index("ix_trace_events_event_type", "event_type"),
        Index("ix_trace_events_crew_id", "crew_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(64), nullable=False)
    event_type = Column(String(128), nullable=False)
    crew_id = Column(String(256), nullable=True)
    agent_name = Column(String(256), nullable=True)
    task_id = Column(String(256), nullable=True)
    tool_name = Column(String(256), nullable=True)
    data = Column(Text, nullable=True)  # JSON-encoded
    duration_ms = Column(Float, nullable=True)
    status = Column(String(64), nullable=True)

# =============================================================================
# Orchestration Checkpoints -- Phase 194 (migrated from raw sqlite3)
# =============================================================================

class OrchestrationCheckpoint(Base):
    """Persistent checkpoint for cross-restart orchestration recovery."""

    __tablename__ = "orchestration_checkpoints"
    __table_args__ = (Index("ix_orch_checkpoints_execution_id", "execution_id"),)

    checkpoint_id = Column(String(64), primary_key=True)
    execution_id = Column(String(64), nullable=False)
    created_at = Column(String(64), nullable=False)
    label = Column(String(256), default="")
    state_json = Column(Text, nullable=False)
