"""Self-development sandbox for isolated AI code generation.

Creates a fork/copy of workspace where AI can develop skills,
tests, and docs without touching production code.

Security boundaries:
- AI develops in isolated sandbox directory
- No access to main workspace during development
- All outputs validated before staging
- Explicit trigger required (/dryade:self-improve)
"""

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from core.autonomous.audit import AuditLogger
from core.self_dev.staging import StagingArea, get_staging_area

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Patterns that should never appear in generated code
FORBIDDEN_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "chmod 777",
    "eval(input",
    "__import__('os').system",
    "subprocess.call(input",
    "exec(input",
    "os.system(input",
]

# File patterns that should never be generated
FORBIDDEN_FILES = [
    ".env",
    "credentials",
    "secrets",
    "private_key",
    "id_rsa",
    "password",
]

@dataclass
class SelfDevSession:
    """Active self-development session."""

    session_id: str
    goal: str
    sandbox_path: Path
    output_path: Path
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Permissions
    allowed_operations: list[str] = field(
        default_factory=lambda: [
            "create_skill",
            "create_test",
            "create_doc",
            "create_script",
        ]
    )
    forbidden_patterns: list[str] = field(default_factory=lambda: FORBIDDEN_PATTERNS.copy())

    # State
    artifacts_created: list[Path] = field(default_factory=list)
    is_active: bool = True

@dataclass
class ValidationResult:
    """Result of security validation."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

class SelfDevSandbox:
    """Isolated environment for AI self-development.

    Creates a fork/copy of workspace where AI can develop
    skills, tests, and docs without touching production code.

    Usage:
        sandbox = SelfDevSandbox(workspace_path=Path("."))

        # Enter self-dev mode (explicit trigger required)
        session = await sandbox.enter_self_dev_mode(
            goal="Create a deployment skill"
        )

        # AI develops in sandbox...
        # session.sandbox_path contains isolated workspace

        # Validate and stage for human review
        result = await sandbox.validate_and_stage(session, artifacts)
        # result.output_path contains staged artifacts in .scratch/
    """

    def __init__(
        self,
        workspace_path: Path | None = None,
        staging_area: StagingArea | None = None,
        audit_session_id: str | None = None,
    ):
        """Initialize self-dev sandbox.

        Args:
            workspace_path: Main workspace path (default: cwd)
            staging_area: Custom staging area
            audit_session_id: Session ID for audit logging
        """
        self.workspace = workspace_path or Path.cwd()
        self.staging = staging_area or get_staging_area()
        self.audit = AuditLogger(
            session_id=audit_session_id or str(uuid4()), initiator_id="self_dev"
        )

        self._active_sessions: dict[str, SelfDevSession] = {}

    async def enter_self_dev_mode(self, goal: str) -> SelfDevSession:
        """Initialize sandbox for self-development session.

        ONLY called via explicit /dryade:self-improve command.

        Args:
            goal: What the AI should develop

        Returns:
            Active SelfDevSession with sandbox paths
        """
        session_id = uuid4().hex[:12]

        self.audit.log_self_dev_start(goal, session_id)
        logger.info(f"[SelfDev] Starting session {session_id}: {goal[:50]}...")

        # Create isolated sandbox in temp directory
        sandbox_base = Path(tempfile.mkdtemp(prefix=f"dryade_selfdev_{session_id}_"))
        sandbox_path = sandbox_base / "workspace"
        sandbox_path.mkdir()

        # Clone minimal structure for development
        self._clone_for_development(sandbox_path)

        # Create output path in staging area
        output_path = self.staging.create_session_output_dir(session_id)

        # Create session
        session = SelfDevSession(
            session_id=session_id,
            goal=goal,
            sandbox_path=sandbox_path,
            output_path=output_path,
        )

        self._active_sessions[session_id] = session

        logger.info(f"[SelfDev] Sandbox ready: {sandbox_path}")
        return session

    def _clone_for_development(self, sandbox_path: Path) -> None:
        """Clone minimal structure for skill development.

        Args:
            sandbox_path: Target sandbox directory
        """
        # Create directory structure
        (sandbox_path / "skills").mkdir()
        (sandbox_path / "tests").mkdir()
        (sandbox_path / "docs").mkdir()
        (sandbox_path / "scripts").mkdir()

        # Copy skill template if exists
        skill_template = self.workspace / "templates" / "skill"
        if skill_template.exists():
            shutil.copytree(skill_template, sandbox_path / "templates" / "skill")

        # Copy example skills for reference (read-only examples)
        examples_dir = sandbox_path / "examples"
        examples_dir.mkdir()

        # Copy a few existing skills as examples
        skills_dir = self.workspace / "skills"
        if skills_dir.exists():
            for skill_dir in list(skills_dir.iterdir())[:3]:  # Max 3 examples
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    shutil.copytree(skill_dir, examples_dir / skill_dir.name)

        logger.debug(f"[SelfDev] Cloned development structure to {sandbox_path}")

    async def validate_and_stage(
        self, session: SelfDevSession, artifacts: list[Path]
    ) -> ValidationResult:
        """Validate generated artifacts and stage for review.

        Args:
            session: Active session
            artifacts: Paths to generated artifacts in sandbox

        Returns:
            ValidationResult with pass/fail and issues
        """
        if session.session_id not in self._active_sessions:
            return ValidationResult(passed=False, issues=["Session not found or expired"])

        all_issues: list[str] = []
        all_warnings: list[str] = []

        for artifact_path in artifacts:
            # Ensure artifact is within sandbox
            try:
                artifact_path.resolve().relative_to(session.sandbox_path.resolve())
            except ValueError:
                all_issues.append(f"Artifact outside sandbox: {artifact_path}")
                continue

            # Validate artifact
            validation = self._validate_artifact(artifact_path)
            all_issues.extend(validation.issues)
            all_warnings.extend(validation.warnings)

        # If any critical issues, fail
        if all_issues:
            self.audit._create_entry(
                action_type="self_dev_artifact",
                action_details={"validation": "failed", "issues": all_issues},
                success=False,
            )
            return ValidationResult(passed=False, issues=all_issues, warnings=all_warnings)

        # Validation passed - stage artifacts
        for artifact_path in artifacts:
            if not artifact_path.exists():
                continue

            # Determine artifact type
            artifact_type = self._classify_artifact(artifact_path)

            # Stage artifact
            staged = self.staging.stage_artifact(
                source_path=artifact_path,
                artifact_type=artifact_type,
                session_id=session.session_id,
                output_dir=session.output_path,
                signed=False,  # Signing handled separately
            )

            session.artifacts_created.append(artifact_path)

            self.audit.log_self_dev_artifact(
                artifact_type=artifact_type, path=str(staged.staged_path), signed=False
            )

        # Write manifest
        self.staging.write_manifest(
            session_id=session.session_id,
            output_dir=session.output_path,
            goal=session.goal,
        )

        self.audit.log_self_dev_staged(
            output_path=str(session.output_path), artifacts=[str(a) for a in artifacts]
        )

        logger.info(f"[SelfDev] Staged {len(artifacts)} artifacts to {session.output_path}")

        return ValidationResult(passed=True, warnings=all_warnings)

    def _validate_artifact(self, artifact_path: Path) -> ValidationResult:
        """Validate a single artifact for security issues.

        Args:
            artifact_path: Path to artifact

        Returns:
            ValidationResult
        """
        issues: list[str] = []
        warnings: list[str] = []

        # Check filename
        for forbidden in FORBIDDEN_FILES:
            if forbidden in artifact_path.name.lower():
                issues.append(f"Forbidden filename pattern: {artifact_path.name}")

        if artifact_path.is_file():
            # Check content
            try:
                content = artifact_path.read_text(encoding="utf-8", errors="ignore")

                for pattern in FORBIDDEN_PATTERNS:
                    if pattern in content:
                        issues.append(f"Forbidden pattern in {artifact_path.name}: {pattern}")

                # Check for suspicious patterns (warnings)
                if "subprocess" in content and "shell=True" in content:
                    warnings.append(f"subprocess with shell=True in {artifact_path.name}")

                if "eval(" in content or "exec(" in content:
                    warnings.append(f"Dynamic code execution in {artifact_path.name}")

            except Exception as e:
                warnings.append(f"Could not read {artifact_path.name}: {e}")

        elif artifact_path.is_dir():
            # Recursively validate directory contents
            for child in artifact_path.rglob("*"):
                if child.is_file():
                    child_result = self._validate_artifact(child)
                    issues.extend(child_result.issues)
                    warnings.extend(child_result.warnings)

        return ValidationResult(passed=len(issues) == 0, issues=issues, warnings=warnings)

    def _classify_artifact(self, artifact_path: Path) -> str:
        """Classify artifact type based on path/content.

        Args:
            artifact_path: Path to artifact

        Returns:
            Artifact type string
        """
        name = artifact_path.name.lower()

        if artifact_path.is_dir() and (artifact_path / "SKILL.md").exists():
            return "skill"

        if "test" in name or name.startswith("test_") or name.endswith("_test.py"):
            return "test"

        if name.endswith((".md", ".rst", ".txt")) and "readme" in name.lower():
            return "doc"

        if artifact_path.suffix in (".py", ".sh", ".bash"):
            if "test" in name:
                return "test"
            return "script"

        return "doc"

    async def end_session(self, session: SelfDevSession) -> None:
        """End self-development session and cleanup.

        Args:
            session: Session to end
        """
        if session.session_id in self._active_sessions:
            session.is_active = False
            del self._active_sessions[session.session_id]

            # Cleanup sandbox (staging remains)
            if session.sandbox_path.exists():
                shutil.rmtree(session.sandbox_path.parent)  # Remove temp dir

            logger.info(f"[SelfDev] Ended session {session.session_id}")

    def get_active_sessions(self) -> list[SelfDevSession]:
        """Get all active sessions.

        Returns:
            List of active sessions
        """
        return list(self._active_sessions.values())
