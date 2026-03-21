"""Agent Factory -- create agents, tools, and skills from natural language."""

from core.factory.config_generator import generate_config, select_framework, select_framework_llm
from core.factory.models import (
    ArtifactStatus,
    ArtifactType,
    ArtifactVersion,
    CreationRequest,
    CreationResult,
    FactoryArtifact,
    FactoryConfig,
    ProactiveSuggestion,
    RelevanceSignal,
)
from core.factory.registry import FactoryRegistry, register_a2a_agent
from core.factory.relevance import (
    check_existing_capabilities,
    detect_gaps,
    get_factory_config,
    get_proactive_suggestions,
)
from core.factory.scaffold import scaffold_artifact
from core.factory.tester import generate_test_task, test_artifact

__all__ = [
    # Enums
    "ArtifactType",
    "ArtifactStatus",
    # Models
    "CreationRequest",
    "CreationResult",
    "FactoryArtifact",
    "ArtifactVersion",
    "FactoryConfig",
    "RelevanceSignal",
    "ProactiveSuggestion",
    # Registry
    "FactoryRegistry",
    "register_a2a_agent",
    # Scaffold
    "scaffold_artifact",
    # Testing
    "test_artifact",
    "generate_test_task",
    # Config generator
    "select_framework",
    "select_framework_llm",
    "generate_config",
    # Relevance detection
    "check_existing_capabilities",
    "detect_gaps",
    "get_proactive_suggestions",
    "get_factory_config",
    # Pipeline stubs (require TCST orchestrator - Phase 119.3+)
    "FactoryPipeline",
    "create_artifact",
    "update_artifact",
    "rollback_artifact",
    # Working API functions
    "list_artifacts",
    "get_artifact",
    "delete_artifact",
]

# ---------------------------------------------------------------------------
# Pipeline API -- delegates to FactoryPipeline (lazy import to avoid circular)
# ---------------------------------------------------------------------------

# Note: FactoryPipeline is available via lazy import in the functions below,
# and can be imported directly as:
#   from core.factory.orchestrator import FactoryPipeline

async def create_artifact(request: CreationRequest) -> CreationResult:
    """Create an agent, tool, or skill from a natural language request.

    Primary public API. Runs the full TCST pipeline via FactoryPipeline.
    """
    from core.factory.orchestrator import FactoryPipeline

    pipeline = FactoryPipeline(conversation_id=request.conversation_id)
    return await pipeline.create(request)

async def update_artifact(name: str, request: CreationRequest) -> CreationResult:
    """Update an existing artifact (creates new version via TCST pipeline)."""
    from core.factory.orchestrator import FactoryPipeline

    pipeline = FactoryPipeline(conversation_id=request.conversation_id)
    return await pipeline.update(name, request)

async def rollback_artifact(name: str, version: int) -> CreationResult:
    """Rollback to a previous version (re-scaffold from stored config)."""
    from core.factory.orchestrator import FactoryPipeline

    pipeline = FactoryPipeline()
    return await pipeline.rollback(name, version)

# ---------------------------------------------------------------------------
# Working API functions -- delegate to FactoryRegistry
# ---------------------------------------------------------------------------

async def list_artifacts(
    artifact_type: ArtifactType | None = None,
    status: ArtifactStatus | None = None,
) -> list[FactoryArtifact]:
    """List all factory-created artifacts, optionally filtered."""
    registry = FactoryRegistry()
    return registry.list_all(artifact_type=artifact_type, status=status)

async def get_artifact(name: str) -> FactoryArtifact | None:
    """Get a specific artifact by name."""
    registry = FactoryRegistry()
    return registry.get(name)

async def delete_artifact(name: str) -> bool:
    """Soft-delete an artifact (archive it, retain files)."""
    registry = FactoryRegistry()
    return registry.archive(name)
