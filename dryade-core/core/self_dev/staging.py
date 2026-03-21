"""Staging area management for self-development artifacts.

All self-development outputs go to .scratch/ for human review.
User manually moves desired artifacts to final location.
"""

import json
import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field

from core.utils.time import utcnow

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class StagedArtifact(BaseModel):
    """Metadata for a staged artifact."""

    artifact_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    artifact_type: str  # "skill", "test", "doc", "script"
    source_path: str  # Path in sandbox
    staged_path: str  # Path in .scratch/
    created_at: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    signed: bool = False
    signature: str | None = None

    # Validation status
    security_validated: bool = False
    validation_notes: list[str] = Field(default_factory=list)

class StagingArea:
    """Manage .scratch/ staging directory for self-dev outputs.

    Structure:
        .scratch/
            output/
                {session_id}/
                    {timestamp}/
                        skills/
                        tests/
                        docs/
                    manifest.json
            sessions/
                {session_id}.json  # Session metadata
    """

    DEFAULT_SCRATCH_DIR = Path(".scratch")

    def __init__(self, scratch_dir: Path | None = None):
        """Initialize staging area.

        Args:
            scratch_dir: Custom scratch directory (defaults to .scratch/)
        """
        self.scratch_dir = scratch_dir or self.DEFAULT_SCRATCH_DIR
        self._artifacts: dict[str, list[StagedArtifact]] = {}  # session_id -> artifacts
        self._lock = threading.Lock()

    def ensure_structure(self) -> None:
        """Ensure staging directory structure exists."""
        (self.scratch_dir / "output").mkdir(parents=True, exist_ok=True)
        (self.scratch_dir / "sessions").mkdir(parents=True, exist_ok=True)

        # Create .gitignore if not exists
        gitignore = self.scratch_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# Self-development staging area\n# Review before merging\n*\n!.gitignore\n"
            )

    def create_session_output_dir(self, session_id: str) -> Path:
        """Create output directory for a session.

        Args:
            session_id: Session identifier

        Returns:
            Path to session output directory
        """
        timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
        output_dir = self.scratch_dir / "output" / session_id / timestamp

        # Create subdirectories for different artifact types
        (output_dir / "skills").mkdir(parents=True, exist_ok=True)
        (output_dir / "tests").mkdir(parents=True, exist_ok=True)
        (output_dir / "docs").mkdir(parents=True, exist_ok=True)

        return output_dir

    def stage_artifact(
        self,
        source_path: Path,
        artifact_type: str,
        session_id: str,
        output_dir: Path,
        signed: bool = False,
        signature: str | None = None,
    ) -> StagedArtifact:
        """Stage an artifact for human review.

        Args:
            source_path: Path to artifact in sandbox
            artifact_type: Type of artifact
            session_id: Session that created this
            output_dir: Session output directory
            signed: Whether artifact is signed
            signature: Signature if signed

        Returns:
            Staged artifact metadata
        """
        # Determine destination based on type
        type_dir = output_dir / (artifact_type + "s")  # skills, tests, docs
        type_dir.mkdir(parents=True, exist_ok=True)

        # Copy to staging
        if source_path.is_dir():
            dest_path = type_dir / source_path.name
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(source_path, dest_path)
        else:
            dest_path = type_dir / source_path.name
            shutil.copy2(source_path, dest_path)

        # Create artifact metadata
        artifact = StagedArtifact(
            artifact_type=artifact_type,
            source_path=str(source_path),
            staged_path=str(dest_path),
            session_id=session_id,
            signed=signed,
            signature=signature,
        )

        # Track artifact
        with self._lock:
            if session_id not in self._artifacts:
                self._artifacts[session_id] = []
            self._artifacts[session_id].append(artifact)

        logger.info(f"[Staging] Staged {artifact_type}: {dest_path}")
        return artifact

    def get_session_artifacts(self, session_id: str) -> list[StagedArtifact]:
        """Get all artifacts for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of staged artifacts
        """
        with self._lock:
            return list(self._artifacts.get(session_id, []))

    def write_manifest(self, session_id: str, output_dir: Path, goal: str) -> Path:
        """Write session manifest for human review.

        Args:
            session_id: Session identifier
            output_dir: Session output directory
            goal: Original goal

        Returns:
            Path to manifest file
        """
        artifacts = self.get_session_artifacts(session_id)
        manifest = {
            "session_id": session_id,
            "goal": goal,
            "created_at": utcnow().isoformat(),
            "artifacts": [a.model_dump(mode="json") for a in artifacts],
            "instructions": (
                "Review the generated artifacts below.\n"
                "Move desired files to their final location.\n"
                "Delete this directory when done."
            ),
        }

        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Also write human-readable summary
        summary_path = output_dir / "README.md"
        summary_lines = [
            f"# Self-Development Output: {session_id[:8]}",
            "",
            f"**Goal:** {goal}",
            f"**Created:** {manifest['created_at']}",
            "",
            "## Artifacts",
            "",
        ]
        for a in artifacts:
            signed_badge = " (signed)" if a.signed else ""
            summary_lines.append(
                f"- **{a.artifact_type}**: `{Path(a.staged_path).name}`{signed_badge}"
            )

        summary_lines.extend(
            [
                "",
                "## Review Instructions",
                "",
                "1. Review each artifact in the subdirectories",
                "2. Run tests if applicable",
                "3. Move approved artifacts to their final location:",
                "   - Skills: `skills/` or `plugins/*/skills/`",
                "   - Tests: `tests/`",
                "   - Docs: `docs/`",
                "4. Delete this directory when done",
            ]
        )
        summary_path.write_text("\n".join(summary_lines))

        logger.info(f"[Staging] Wrote manifest: {manifest_path}")
        return manifest_path

    def list_sessions(self) -> list[dict]:
        """List all staging sessions.

        Returns:
            List of session summaries
        """
        sessions = []
        sessions_dir = self.scratch_dir / "sessions"
        if sessions_dir.exists():
            for session_file in sessions_dir.glob("*.json"):
                try:
                    data = json.loads(session_file.read_text())
                    sessions.append(data)
                except Exception:
                    pass
        return sessions

    def clean_session(self, session_id: str) -> bool:
        """Remove session from staging.

        Args:
            session_id: Session to clean

        Returns:
            True if cleaned
        """
        output_dir = self.scratch_dir / "output" / session_id
        if output_dir.exists():
            shutil.rmtree(output_dir)
            with self._lock:
                if session_id in self._artifacts:
                    del self._artifacts[session_id]
            logger.info(f"[Staging] Cleaned session: {session_id}")
            return True
        return False

# Singleton staging area
_staging: StagingArea | None = None
_staging_lock = threading.Lock()

def get_staging_area() -> StagingArea:
    """Get or create global staging area.

    Returns:
        Singleton StagingArea instance
    """
    global _staging
    if _staging is None:
        with _staging_lock:
            if _staging is None:
                _staging = StagingArea()
                _staging.ensure_structure()
    return _staging
