"""FactoryPipeline -- 8-step TCST orchestrator for the Agent Factory.

Coordinates deduplication, config generation, user review, scaffolding,
registry registration, testing, auto-discovery, and result assembly.
Supports two-tier execution: fast scaffold-only (< 2s) and full async
pipeline with WebSocket progress events.
"""

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from core.extensions.events import ChatEvent
from core.factory.models import (
    ArtifactStatus,
    ArtifactType,
    CreationRequest,
    CreationResult,
    FactoryArtifact,
)

logger = logging.getLogger(__name__)

__all__ = ["FactoryPipeline", "emit_factory_progress", "PIPELINE_STEPS"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPELINE_STEPS: list[str] = [
    "deduplication",
    "config_generation",
    "user_review",
    "scaffold",
    "register",
    "test",
    "discover",
    "complete",
]

_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
_LEADING_TRAILING_UNDER = re.compile(r"^[_-]+|[_-]+$")

# ---------------------------------------------------------------------------
# Helper: factory progress event
# ---------------------------------------------------------------------------

def emit_factory_progress(
    step: int,
    step_name: str,
    artifact_name: str,
    detail: str = "",
) -> ChatEvent:
    """Create a ChatEvent for pipeline progress tracking.

    Args:
        step: Current step number (1-8).
        step_name: Name of the current pipeline step.
        artifact_name: Name of the artifact being created.
        detail: Optional detail message.

    Returns:
        ChatEvent with type="progress" and factory metadata.
    """
    total = len(PIPELINE_STEPS)
    pct = round(step / total * 100)
    content = f"Factory: {step_name} ({step}/{total}) - {artifact_name}"
    if detail:
        content += f" - {detail}"

    return ChatEvent(
        type="progress",
        content=content,
        metadata={
            "current_step": step,
            "total_steps": total,
            "percentage": pct,
            "current_agent": f"factory:{step_name}",
            "factory": True,
            "artifact_name": artifact_name,
            "detail": detail,
        },
    )

# ---------------------------------------------------------------------------
# Helper: name sanitization
# ---------------------------------------------------------------------------

def _sanitize_name(goal: str) -> str:
    """Derive a slug-style artifact name from a goal string.

    Extracts meaningful words, lowercases, replaces non-alphanumeric with
    underscores, and truncates to 64 characters.

    Args:
        goal: Natural-language goal description.

    Returns:
        A slug matching ``^[a-z][a-z0-9_-]*$``.
    """
    # Lowercase and take first ~4 words
    words = goal.lower().split()[:4]
    raw = "_".join(words) if words else "unnamed"

    # Replace non-alphanumeric sequences with underscore
    slug = _SANITIZE_RE.sub("_", raw)

    # Strip leading/trailing underscores and dashes
    slug = _LEADING_TRAILING_UNDER.sub("", slug)

    # Ensure starts with a letter
    if not slug or not slug[0].isalpha():
        slug = "artifact_" + slug

    # Truncate
    slug = slug[:64]

    # Final strip of trailing underscores after truncation
    slug = _LEADING_TRAILING_UNDER.sub("", slug)

    return slug or "unnamed"

# ---------------------------------------------------------------------------
# FactoryPipeline
# ---------------------------------------------------------------------------

class FactoryPipeline:
    """Orchestrates the 8-step TCST pipeline for artifact creation.

    Supports two execution tiers:
    - **Full path**: Runs all 8 steps sequentially (dedup -> config -> review
      -> scaffold -> register -> test -> discover -> complete).
    - **Fast path** (``fast_path=True``): Returns immediately after scaffold
      + register (steps 1-5) and schedules background completion of steps 6-8.

    WebSocket progress events are emitted at each step via ChatEvent when a
    ``conversation_id`` is provided.
    """

    def __init__(self, conversation_id: str | None = None):
        """Initialize the pipeline.

        Args:
            conversation_id: Optional conversation ID for WebSocket event
                routing. If None, progress events are silently skipped.
        """
        self._conversation_id = conversation_id

    # -- WebSocket progress --------------------------------------------------

    async def _emit_progress(
        self,
        step: int,
        step_name: str,
        artifact_name: str,
        detail: str = "",
    ) -> None:
        """Best-effort WebSocket event delivery.

        Fire-and-forget per research Pitfall 5: never block the pipeline
        on event emission failure.
        """
        if self._conversation_id is None:
            return

        try:
            from core.api.routes.websocket import manager

            event = emit_factory_progress(step, step_name, artifact_name, detail)
            session = manager.get_session(self._conversation_id)
            if session is not None:
                event_data = {"content": event.content}
                if event.metadata:
                    event_data.update(event.metadata)
                await manager.send_sequenced(session, event.type, event_data)
        except Exception:
            # Silently pass -- WS emission must never block pipeline
            pass

    # -- Main pipeline: create -----------------------------------------------

    async def create(
        self,
        request: CreationRequest,
        *,
        fast_path: bool = False,
        skip_autonomy: bool = False,
    ) -> CreationResult:
        """Run the full 8-step TCST pipeline.

        Args:
            request: The artifact creation request.
            fast_path: If True, return after scaffold+register and schedule
                background completion of test/discover steps.
            skip_autonomy: If True, skip the autonomy check (used by
                execute_approved_creation after user approval).

        Returns:
            CreationResult with all pipeline outputs.
        """
        start_time = time.monotonic()

        # Derive artifact name
        artifact_name = request.suggested_name or _sanitize_name(request.goal)

        # ------------------------------------------------------------------
        # STEP 1: DEDUPLICATION CHECK
        # ------------------------------------------------------------------
        await self._emit_progress(1, "deduplication", artifact_name)
        deduplication_warnings: list[str] = []
        try:
            from core.factory.relevance import check_existing_capabilities

            warnings = await check_existing_capabilities(artifact_name, request.goal)
            if warnings:
                deduplication_warnings = list(warnings)
        except (ImportError, Exception) as exc:
            logger.debug("Deduplication check skipped: %s", exc)

        # ------------------------------------------------------------------
        # STEP 2: CONFIG GENERATION
        # ------------------------------------------------------------------
        await self._emit_progress(2, "config_generation", artifact_name)
        try:
            from core.factory.config_generator import generate_config

            config = await generate_config(
                request.goal,
                artifact_name,
                request.framework,
                request.artifact_type,
            )
        except ImportError:
            logger.debug("config_generator not available, using inline fallback config")
            config = {
                "artifact_type": (request.artifact_type or ArtifactType.AGENT).value,
                "framework": request.framework or "custom",
                "name": artifact_name,
                "description": request.goal,
                "goal": request.goal,
                "test_task": request.test_task or "",
            }

        # Resolve types from config (config_generator may have auto-detected)
        artifact_type_str = config.get(
            "artifact_type",
            (request.artifact_type or ArtifactType.AGENT).value,
        )
        artifact_type_enum = ArtifactType(artifact_type_str)
        framework = config.get("framework", request.framework or "custom")

        # ------------------------------------------------------------------
        # STEP 3: USER REVIEW (AUTONOMY CHECK)
        # ------------------------------------------------------------------
        await self._emit_progress(3, "user_review", artifact_name)

        if not skip_autonomy:
            # Determine factory action type for autonomy check
            artifact_type_val = artifact_type_enum.value  # "agent", "tool", "skill"
            action_type = f"factory_create_{artifact_type_val}"

            try:
                from core.orchestrator.action_autonomy import (
                    AutonomyLevel,
                    get_action_autonomy,
                )

                autonomy = get_action_autonomy()
                level = autonomy.check_autonomy(action_type)

                if level == AutonomyLevel.APPROVE:
                    # Requires full approval -- return early with pending status
                    logger.info(
                        "Factory creation of %s requires approval (action=%s, level=%s)",
                        artifact_name,
                        action_type,
                        level.value,
                    )
                    from core.factory.registry import FactoryRegistry as _ApprovalReg

                    _approval_reg = _ApprovalReg()
                    # Register a placeholder so it can be found and approved later
                    now = datetime.now(UTC)
                    _pending_id = str(uuid4())
                    _pending_artifact = FactoryArtifact(
                        id=_pending_id,
                        name=artifact_name,
                        artifact_type=artifact_type_enum,
                        framework=framework,
                        version=0,
                        status=ArtifactStatus.PENDING_APPROVAL,
                        source_prompt=request.goal,
                        config_json=config,
                        artifact_path="",
                        trigger=request.trigger,
                        created_at=now,
                        updated_at=now,
                    )
                    _approval_reg.register(_pending_artifact)
                    elapsed = time.monotonic() - start_time
                    return CreationResult(
                        success=False,
                        artifact_name=artifact_name,
                        artifact_type=artifact_type_enum,
                        framework=framework,
                        artifact_path="",
                        artifact_id=_pending_id,
                        message=(
                            f"Creation requires approval (autonomy level: {level.value}). "
                            f"Use execute_approved_creation() after approval."
                        ),
                        config_json=config,
                        duration_seconds=elapsed,
                        deduplication_warnings=deduplication_warnings,
                    )
                elif level == AutonomyLevel.CONFIRM:
                    logger.info(
                        "Factory creation of %s confirmed (action=%s, level=%s)",
                        artifact_name,
                        action_type,
                        level.value,
                    )
                else:
                    # AUTO -- proceed silently
                    pass
            except ImportError:
                logger.debug("action_autonomy not available, auto-approving")
        else:
            logger.info(
                "Factory creating %s (%s %s) -- autonomy skipped (approved)",
                artifact_name,
                framework,
                artifact_type_str,
            )

        # ------------------------------------------------------------------
        # STEP 4: TEMPLATE SCAFFOLD
        # ------------------------------------------------------------------
        await self._emit_progress(4, "scaffold", artifact_name)
        from core.factory.scaffold import scaffold_artifact

        success, artifact_path, scaffold_msg = scaffold_artifact(
            config, artifact_type_enum, framework
        )
        if not success:
            elapsed = time.monotonic() - start_time
            return CreationResult(
                success=False,
                artifact_name=artifact_name,
                artifact_type=artifact_type_enum,
                framework=framework,
                artifact_path="",
                artifact_id="",
                message=f"Scaffold failed: {scaffold_msg}",
                config_json=config,
                duration_seconds=elapsed,
                deduplication_warnings=deduplication_warnings,
            )

        # ------------------------------------------------------------------
        # STEP 5: REGISTER IN REGISTRY
        # ------------------------------------------------------------------
        await self._emit_progress(5, "register", artifact_name)
        from core.factory.registry import FactoryRegistry

        now = datetime.now(UTC)
        artifact_id = str(uuid4())
        artifact = FactoryArtifact(
            id=artifact_id,
            name=artifact_name,
            artifact_type=artifact_type_enum,
            framework=framework,
            version=1,
            status=ArtifactStatus.SCAFFOLDED,
            source_prompt=request.goal,
            config_json=config,
            artifact_path=artifact_path,
            trigger=request.trigger,
            created_at=now,
            updated_at=now,
        )
        registry = FactoryRegistry()
        # register() creates the artifact AND initial version entry (version=1)
        registry.register(artifact)

        # ------------------------------------------------------------------
        # FAST PATH CHECK
        # ------------------------------------------------------------------
        if fast_path:
            elapsed = time.monotonic() - start_time
            asyncio.create_task(
                self._complete_pipeline_background(
                    artifact_name,
                    artifact_path,
                    artifact_type_enum,
                    framework,
                    config,
                    request,
                    registry,
                    artifact_id,
                )
            )
            return CreationResult(
                success=True,
                artifact_name=artifact_name,
                artifact_type=artifact_type_enum,
                framework=framework,
                artifact_path=artifact_path,
                artifact_id=artifact_id,
                version=1,
                test_passed=False,
                test_iterations=0,
                message="Scaffolded (testing in background)",
                config_json=config,
                duration_seconds=elapsed,
                deduplication_warnings=deduplication_warnings,
            )

        # ------------------------------------------------------------------
        # STEP 6: TEST-VALIDATE-ITERATE
        # ------------------------------------------------------------------
        await self._emit_progress(6, "test", artifact_name)
        from core.factory.tester import test_artifact

        test_task_str = config.get("test_task") or request.test_task
        passed, iterations, output = await test_artifact(
            artifact_path,
            artifact_type_enum,
            framework,
            test_task_str,
            request.max_test_iterations,
        )
        final_status = ArtifactStatus.ACTIVE if passed else ArtifactStatus.FAILED
        registry.update_status(artifact_name, final_status)
        registry.update_artifact(
            artifact_name,
            test_passed=passed,
            test_iterations=iterations,
            test_result=output[:5000] if output else "",
        )

        # ------------------------------------------------------------------
        # STEP 7: AUTO-DISCOVERY REGISTRATION
        # ------------------------------------------------------------------
        await self._emit_progress(7, "discover", artifact_name)
        await self._run_discovery(artifact_type_enum, artifact_path)

        # ------------------------------------------------------------------
        # STEP 8: RETURN RESULT
        # ------------------------------------------------------------------
        await self._emit_progress(8, "complete", artifact_name)
        elapsed = time.monotonic() - start_time

        return CreationResult(
            success=passed,
            artifact_name=artifact_name,
            artifact_type=artifact_type_enum,
            framework=framework,
            artifact_path=artifact_path,
            artifact_id=artifact_id,
            version=1,
            test_passed=passed,
            test_iterations=iterations,
            test_output=output[:5000] if output else None,
            message=(
                f"Created {artifact_name} ({framework} {artifact_type_str})"
                if passed
                else (
                    f"Created {artifact_name} but tests failed after {iterations} iterations"
                    + (f": {output[:200]}" if output else "")
                )
            ),
            config_json=config,
            duration_seconds=elapsed,
            deduplication_warnings=deduplication_warnings,
        )

    # -- Background completion (fast path) -----------------------------------

    async def _complete_pipeline_background(
        self,
        artifact_name: str,
        artifact_path: str,
        artifact_type: ArtifactType,
        framework: str,
        config: dict,
        request: CreationRequest,
        registry: "FactoryRegistry",
        artifact_id: str,
    ) -> None:
        """Run steps 6-8 in background after fast-path return.

        Called via ``asyncio.create_task`` from the fast path. Catches all
        exceptions to prevent unhandled task errors.
        """
        try:
            # Step 6: Test
            await self._emit_progress(6, "test", artifact_name)
            from core.factory.tester import test_artifact

            test_task_str = config.get("test_task") or request.test_task
            passed, iterations, output = await test_artifact(
                artifact_path,
                artifact_type,
                framework,
                test_task_str,
                request.max_test_iterations,
            )
            final_status = ArtifactStatus.ACTIVE if passed else ArtifactStatus.FAILED
            registry.update_status(artifact_name, final_status)
            registry.update_artifact(
                artifact_name,
                test_passed=passed,
                test_iterations=iterations,
                test_result=output[:5000] if output else "",
            )

            # Step 7: Discover
            await self._emit_progress(7, "discover", artifact_name)
            await self._run_discovery(artifact_type, artifact_path)

            # Step 8: Complete
            await self._emit_progress(8, "complete", artifact_name)
            logger.info(
                "Background pipeline complete for %s: passed=%s",
                artifact_name,
                passed,
            )

        except Exception:
            logger.exception("Background pipeline failed for %s", artifact_name)
            try:
                registry.update_status(artifact_name, ArtifactStatus.FAILED)
            except Exception:
                pass

    # -- Auto-discovery helper -----------------------------------------------

    async def _run_discovery(self, artifact_type: ArtifactType, artifact_path: str) -> None:
        """Best-effort auto-discovery registration.

        All discovery calls are wrapped in try/except -- these are integration
        points that may not exist yet.
        """
        if artifact_type == ArtifactType.AGENT:
            try:
                from core.adapters.auto_discovery import AgentAutoDiscovery

                agents_dir = Path(artifact_path).parent
                AgentAutoDiscovery(agents_dir).discover_and_register()
            except (ImportError, Exception) as exc:
                logger.debug("Agent auto-discovery skipped: %s", exc)

        elif artifact_type == ArtifactType.TOOL:
            try:
                from core.mcp import add_mcp_server  # noqa: F401

                # Placeholder for tool registration (Phase 119.4)
                logger.debug("Tool auto-discovery placeholder for %s", artifact_path)
            except (ImportError, Exception) as exc:
                logger.debug("Tool auto-discovery skipped: %s", exc)

        # Skills are auto-detected by SkillWatcher -- no explicit action needed
        elif artifact_type == ArtifactType.SKILL:
            logger.debug("Skill auto-discovery handled by SkillWatcher")

        # Refresh capability registry so router/orchestrator can find new artifact
        try:
            from core.orchestrator.capability_registry import get_capability_registry

            cap_registry = get_capability_registry()
            cap_registry.refresh_from_sources()
            logger.info("Capability registry refreshed after factory creation")
        except (ImportError, Exception) as exc:
            logger.debug("Capability registry refresh skipped: %s", exc)

    # -- Update pipeline -----------------------------------------------------

    async def update(self, name: str, request: CreationRequest) -> CreationResult:
        """Update an existing artifact by running TCST with new config.

        Creates a new version entry on success. On failure, restores the
        previous version by re-scaffolding from stored config.

        Args:
            name: Existing artifact name.
            request: Updated creation request.

        Returns:
            CreationResult with updated artifact state.

        Raises:
            ValueError: If the artifact is not found.
        """
        from core.factory.registry import FactoryRegistry
        from core.factory.scaffold import scaffold_artifact
        from core.factory.tester import test_artifact

        registry = FactoryRegistry()
        existing = registry.get(name)
        if existing is None:
            raise ValueError(f"Artifact not found: {name}")

        start_time = time.monotonic()
        new_version = existing.version + 1

        # Generate updated config (inline fallback if config_generator missing)
        try:
            from core.factory.config_generator import generate_config

            config = await generate_config(
                request.goal,
                name,
                request.framework or existing.framework,
                request.artifact_type or existing.artifact_type,
            )
        except ImportError:
            config = {
                "artifact_type": (request.artifact_type or existing.artifact_type).value,
                "framework": request.framework or existing.framework,
                "name": name,
                "description": request.goal,
                "goal": request.goal,
                "test_task": request.test_task or "",
            }

        artifact_type_enum = ArtifactType(config.get("artifact_type", existing.artifact_type.value))
        framework = config.get("framework", existing.framework)

        # Remove old scaffold directory so scaffold_artifact can create fresh
        old_path = Path(existing.artifact_path)
        if old_path.is_dir():
            import shutil

            shutil.rmtree(old_path, ignore_errors=True)

        # Re-scaffold
        success, artifact_path, scaffold_msg = scaffold_artifact(
            config, artifact_type_enum, framework
        )
        if not success:
            # Restore previous version by re-scaffolding from old config
            old_config = existing.config_json
            scaffold_artifact(old_config, existing.artifact_type, existing.framework)

            elapsed = time.monotonic() - start_time
            return CreationResult(
                success=False,
                artifact_name=name,
                artifact_type=artifact_type_enum,
                framework=framework,
                artifact_path=existing.artifact_path,
                artifact_id=existing.id,
                version=existing.version,
                message=f"Update failed: {scaffold_msg}. Reverted to v{existing.version}.",
                config_json=config,
                duration_seconds=elapsed,
            )

        # Test
        test_task_str = config.get("test_task") or request.test_task
        passed, iterations, output = await test_artifact(
            artifact_path,
            artifact_type_enum,
            framework,
            test_task_str,
            request.max_test_iterations,
        )

        # Update registry
        final_status = ArtifactStatus.ACTIVE if passed else ArtifactStatus.FAILED
        registry.update_status(name, final_status)
        registry.update_artifact(
            name,
            test_passed=passed,
            test_iterations=iterations,
            test_result=output[:5000] if output else "",
            config_json=config,
            artifact_path=artifact_path,
        )

        # Add new version entry (version 2+ since register already created v1)
        registry.add_version(
            existing.id,
            new_version,
            config,
            [artifact_path],
        )

        # Update version in main artifact record (uses ORM via public API)
        registry.update_artifact(name, version=new_version)

        elapsed = time.monotonic() - start_time
        return CreationResult(
            success=passed,
            artifact_name=name,
            artifact_type=artifact_type_enum,
            framework=framework,
            artifact_path=artifact_path,
            artifact_id=existing.id,
            version=new_version,
            test_passed=passed,
            test_iterations=iterations,
            test_output=output[:5000] if output else None,
            message=(
                f"Updated {name} to v{new_version}"
                if passed
                else f"Updated {name} to v{new_version} but tests failed"
            ),
            config_json=config,
            duration_seconds=elapsed,
        )

    # -- Rollback pipeline ---------------------------------------------------

    async def rollback(self, name: str, version: int) -> CreationResult:
        """Rollback to a previous artifact version.

        Re-scaffolds from stored config and re-runs tests.

        Args:
            name: Artifact name.
            version: Target version number to roll back to.

        Returns:
            CreationResult with rollback outcome.

        Raises:
            ValueError: If artifact or version not found.
        """
        from core.factory.registry import FactoryRegistry
        from core.factory.scaffold import scaffold_artifact
        from core.factory.tester import test_artifact

        registry = FactoryRegistry()
        existing = registry.get(name)
        if existing is None:
            raise ValueError(f"Artifact not found: {name}")

        start_time = time.monotonic()

        # Find target version
        versions = registry.get_versions(existing.id)
        target = None
        for v in versions:
            if v.version == version:
                target = v
                break
        if target is None:
            raise ValueError(f"Version {version} not found for artifact {name}")

        config = target.config_json
        artifact_type_enum = ArtifactType(config.get("artifact_type", existing.artifact_type.value))
        framework = config.get("framework", existing.framework)

        # Remove current scaffold directory
        old_path = Path(existing.artifact_path)
        if old_path.is_dir():
            import shutil

            shutil.rmtree(old_path, ignore_errors=True)

        # Re-scaffold from target version config
        success, artifact_path, scaffold_msg = scaffold_artifact(
            config, artifact_type_enum, framework
        )
        if not success:
            elapsed = time.monotonic() - start_time
            return CreationResult(
                success=False,
                artifact_name=name,
                artifact_type=artifact_type_enum,
                framework=framework,
                artifact_path="",
                artifact_id=existing.id,
                version=existing.version,
                message=f"Rollback failed: {scaffold_msg}",
                config_json=config,
                duration_seconds=elapsed,
            )

        # Re-run tests on rolled-back code
        test_task_str = config.get("test_task", "")
        passed, iterations, output = await test_artifact(
            artifact_path,
            artifact_type_enum,
            framework,
            test_task_str or None,
        )

        # Update registry
        final_status = ArtifactStatus.ACTIVE if passed else ArtifactStatus.FAILED
        registry.update_status(name, final_status)
        registry.update_artifact(
            name,
            test_passed=passed,
            test_iterations=iterations,
            test_result=output[:5000] if output else "",
            config_json=config,
            artifact_path=artifact_path,
        )

        # Record rollback as new version entry
        new_version = existing.version + 1
        registry.add_version(
            existing.id,
            new_version,
            config,
            [artifact_path],
            rollback_reason=f"Rolled back to v{version}",
        )

        # Update version in main artifact record (uses ORM via public API)
        registry.update_artifact(name, version=new_version)

        elapsed = time.monotonic() - start_time
        return CreationResult(
            success=passed,
            artifact_name=name,
            artifact_type=artifact_type_enum,
            framework=framework,
            artifact_path=artifact_path,
            artifact_id=existing.id,
            version=new_version,
            test_passed=passed,
            test_iterations=iterations,
            test_output=output[:5000] if output else None,
            message=(
                f"Rolled back {name} to v{version} (now v{new_version})"
                if passed
                else f"Rolled back {name} to v{version} but tests failed"
            ),
            config_json=config,
            duration_seconds=elapsed,
        )

    # -- Escalation executor integration -------------------------------------

    async def execute_approved_creation(self, params: dict) -> tuple[bool, str]:
        """Execute creation after user approval (Phase 119.4 integration).

        Called by the escalation executor after the user approves a factory
        creation suggestion. Resumes the TCST pipeline from step 4 (scaffold)
        with the pre-generated config.

        Args:
            params: Dict with keys matching CreationRequest fields plus
                a pre-generated 'config' dict.

        Returns:
            Tuple of (success, message) matching escalation executor contract.
        """
        try:
            config = params.get("config", {})
            goal = params.get("goal", config.get("goal", ""))
            artifact_name = params.get("name", config.get("name", ""))

            request = CreationRequest(
                goal=goal,
                suggested_name=artifact_name or None,
                artifact_type=params.get("artifact_type"),
                framework=params.get("framework", config.get("framework")),
                test_task=params.get("test_task", config.get("test_task")),
                conversation_id=params.get("conversation_id"),
            )

            result = await self.create(request, skip_autonomy=True)
            return (result.success, result.message)

        except Exception as exc:
            logger.exception("execute_approved_creation failed")
            return (False, f"Factory creation failed: {exc}")
