"""Pydantic models for the Agent Factory module."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "ArtifactType",
    "ArtifactStatus",
    "CreationRequest",
    "CreationResult",
    "FactoryArtifact",
    "ArtifactVersion",
    "FactoryConfig",
    "RelevanceSignal",
    "ProactiveSuggestion",
]

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArtifactType(str, Enum):
    """Type of artifact produced by the factory."""

    AGENT = "agent"
    TOOL = "tool"
    SKILL = "skill"

class ArtifactStatus(str, Enum):
    """Lifecycle status of a factory artifact."""

    CONFIGURING = "configuring"
    PENDING_APPROVAL = "pending_approval"
    SCAFFOLDED = "scaffolded"
    TESTING = "testing"
    ACTIVE = "active"
    FAILED = "failed"
    ARCHIVED = "archived"
    ROLLED_BACK = "rolled_back"

# ---------------------------------------------------------------------------
# Valid frameworks for CreationRequest validation
# ---------------------------------------------------------------------------

_VALID_FRAMEWORKS = frozenset(
    {"crewai", "langchain", "adk", "custom", "mcp_function", "mcp_server", "skill", "a2a"}
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreationRequest(BaseModel):
    """User request to create an agent, tool, or skill."""

    goal: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural-language description of what to create",
    )
    suggested_name: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Optional slug-style name for the artifact",
    )
    artifact_type: ArtifactType | None = Field(
        default=None,
        description="Explicit artifact type (auto-detected if omitted)",
    )
    framework: str | None = Field(
        default=None,
        description="Target framework for scaffolding",
    )
    test_task: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional task to verify the created artifact",
    )
    max_test_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum test-fix-retest cycles",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation context for the creation request",
    )
    trigger: str = Field(
        default="user",
        description="What triggered creation: 'user' or 'proactive'",
    )

    @field_validator("framework")
    @classmethod
    def validate_framework(cls, v: str | None) -> str | None:
        """Validate and normalize framework against the known set.

        LLMs sometimes hallucinate framework names like 'custom_python',
        'python', 'mcp' etc. Normalize common variants before rejecting.
        """
        if v is None:
            return v
        # Normalize common LLM-hallucinated framework names
        _ALIASES: dict[str, str] = {
            "custom_python": "custom",
            "python": "custom",
            "custom_agent": "custom",
            "mcp": "mcp_server",
            "mcp_tool": "mcp_function",
            "langchain_agent": "langchain",
            "crew": "crewai",
            "crew_ai": "crewai",
            "google_adk": "adk",
        }
        v = _ALIASES.get(v, v)
        if v not in _VALID_FRAMEWORKS:
            raise ValueError(f"Invalid framework '{v}'. Valid options: {sorted(_VALID_FRAMEWORKS)}")
        return v

class CreationResult(BaseModel):
    """Result of an artifact creation pipeline run."""

    success: bool = Field(description="Whether creation succeeded")
    artifact_name: str = Field(description="Name of the created artifact")
    artifact_type: ArtifactType = Field(description="Type of artifact created")
    framework: str = Field(description="Framework used for scaffolding")
    artifact_path: str = Field(description="Filesystem path to the artifact")
    artifact_id: str = Field(description="Unique identifier for the artifact")
    version: int = Field(default=1, description="Artifact version number")
    test_passed: bool = Field(default=False, description="Whether validation test passed")
    test_iterations: int = Field(default=0, description="Number of test-fix cycles run")
    test_output: str | None = Field(
        default=None,
        max_length=5000,
        description="Output from the last test run",
    )
    message: str = Field(description="Human-readable status message")
    config_json: dict = Field(
        default_factory=dict,
        description="LLM-generated configuration for the artifact",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of creation",
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Total pipeline duration in seconds",
    )
    deduplication_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about similar existing artifacts",
    )

class FactoryArtifact(BaseModel):
    """Persistent record of a factory-created artifact (maps to database row)."""

    id: str = Field(description="Unique artifact identifier")
    name: str = Field(max_length=64, description="Artifact slug name")
    artifact_type: ArtifactType = Field(description="Type of artifact")
    framework: str = Field(description="Framework used for scaffolding")
    version: int = Field(default=1, description="Current version number")
    status: ArtifactStatus = Field(
        default=ArtifactStatus.CONFIGURING,
        description="Lifecycle status",
    )
    source_prompt: str = Field(description="Original user goal/prompt")
    config_json: dict = Field(
        default_factory=dict,
        description="LLM-generated configuration",
    )
    artifact_path: str = Field(description="Filesystem path to the artifact")
    test_result: str | None = Field(
        default=None,
        description="Output from the last test run",
    )
    test_passed: bool = Field(default=False, description="Whether last test passed")
    test_iterations: int = Field(default=0, description="Number of test-fix cycles run")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of initial creation",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of last update",
    )
    created_by: str = Field(default="factory", description="Creator identity")
    trigger: str = Field(default="user", description="Creation trigger source")
    tags: list[str] = Field(default_factory=list, description="User-defined tags")

class ArtifactVersion(BaseModel):
    """Snapshot of an artifact at a specific version (for rollback)."""

    id: str = Field(description="Unique version identifier")
    artifact_id: str = Field(description="Parent artifact identifier")
    version: int = Field(description="Version number")
    config_json: dict = Field(description="Configuration at this version")
    files_snapshot: list[str] = Field(
        default_factory=list,
        description="List of file paths in this version",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of version creation",
    )
    rollback_reason: str | None = Field(
        default=None,
        description="Reason for rollback (if this version was rolled back to)",
    )

class FactoryConfig(BaseModel):
    """Runtime configuration for the factory module."""

    enabled: bool = Field(default=True, description="Whether the factory is enabled")
    default_test_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Default max test-fix cycles",
    )
    proactive_detection_enabled: bool = Field(
        default=False,
        description="Whether proactive gap detection is active",
    )
    proactive_max_suggestions_per_day: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Max proactive suggestions per day",
    )
    proactive_max_suggestions_per_session: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Max proactive suggestions per session",
    )
    proactive_cooldown_after_rejection_hours: int = Field(
        default=72,
        description="Hours to wait after user rejects a suggestion",
    )
    proactive_min_failure_count: int = Field(
        default=3,
        description="Minimum routing failures before suggesting creation",
    )
    routing_failure_window_hours: int = Field(
        default=24,
        description="Window for counting routing failures",
    )
    escalation_pattern_window_hours: int = Field(
        default=72,
        description="Window for detecting escalation patterns",
    )
    deduplication_embedding_threshold: float = Field(
        default=0.8,
        ge=0.5,
        le=1.0,
        description="Cosine similarity threshold for embedding deduplication",
    )
    deduplication_name_jaccard_threshold: float = Field(
        default=0.5,
        ge=0.3,
        le=1.0,
        description="Jaccard similarity threshold for name deduplication",
    )
    default_agents_dir: str = Field(
        default="agents",
        description="Directory for scaffolded agents",
    )
    default_tools_dir: str = Field(
        default="tools",
        description="Directory for scaffolded tools",
    )
    default_skills_dir: str = Field(
        default="skills",
        description="Directory for scaffolded skills",
    )

class RelevanceSignal(BaseModel):
    """A signal indicating a potential gap in agent/tool coverage."""

    signal_type: str = Field(description="Type of signal (e.g. 'routing_failure')")
    pattern: str = Field(description="Pattern or query that triggered the signal")
    count: int = Field(description="Number of times this signal was observed")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that this represents a real gap",
    )
    example_queries: list[str] = Field(
        default_factory=list,
        description="Example queries that triggered this signal",
    )
    suggested_type: ArtifactType | None = Field(
        default=None,
        description="Suggested artifact type to fill the gap",
    )
    urgency: str = Field(
        default="batch",
        description="Urgency level: 'immediate' or 'batch'",
    )
    first_seen: datetime | None = Field(
        default=None,
        description="Timestamp of first occurrence",
    )
    last_seen: datetime | None = Field(
        default=None,
        description="Timestamp of most recent occurrence",
    )

class ProactiveSuggestion(BaseModel):
    """A proactive suggestion to create a new artifact based on signals."""

    signals: list[RelevanceSignal] = Field(
        description="Signals that led to this suggestion",
    )
    combined_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Combined confidence across all signals",
    )
    suggested_goal: str = Field(
        description="Suggested creation goal for the user",
    )
    suggested_name: str | None = Field(
        default=None,
        description="Suggested artifact name",
    )
    suggested_type: ArtifactType | None = Field(
        default=None,
        description="Suggested artifact type",
    )
    reasoning: str = Field(
        description="Explanation of why this suggestion was made",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of suggestion creation",
    )
    status: str = Field(
        default="pending",
        description="Status: 'pending', 'accepted', 'rejected', 'expired'",
    )
