"""Pydantic models for AgentSkills (SKILL.md) data structures.

These models define the structure of parsed skill files and gating results.
"""

from typing import Any

from pydantic import BaseModel, Field

class SkillRequirements(BaseModel):
    """Requirements that must be met for a skill to be loaded."""

    bins: list[str] = Field(
        default_factory=list, description="Required binaries (e.g., ['git', 'docker'])"
    )
    env: list[str] = Field(default_factory=list, description="Required environment variables")
    config: list[str] = Field(
        default_factory=list, description="Required config paths (e.g., ['~/.aws/credentials'])"
    )

class SkillMetadata(BaseModel):
    """Metadata from SKILL.md frontmatter."""

    emoji: str | None = None
    os: list[str] = Field(
        default_factory=list, description="Target OS platforms (darwin, linux, win32)"
    )
    requires: SkillRequirements = Field(default_factory=SkillRequirements)
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata")
    chat_eligible: bool = True  # Whether skill is available in CHAT mode (default: True)

class Skill(BaseModel):
    """Parsed skill from SKILL.md file."""

    name: str
    description: str
    instructions: str  # Markdown body
    metadata: SkillMetadata = Field(default_factory=SkillMetadata)
    skill_dir: str  # Path to skill directory
    plugin_id: str | None = None  # Parent plugin if loaded from plugin
    scripts_dir: str | None = None  # Path to scripts/ folder if exists
    has_scripts: bool = False  # Quick check for script availability
    chat_eligible: bool = True  # Whether skill is available in CHAT mode
    instructions_loaded: bool = True  # False when loaded via metadata_only

    class Config:
        extra = "allow"

    def ensure_instructions_loaded(self) -> None:
        """Load full instruction body if not yet loaded (lazy Stage 2).

        Called before skill execution when skill was discovered via
        metadata_only=True. No-op if instructions already loaded.
        """
        if self.instructions_loaded:
            return
        if not self.skill_dir:
            return

        from pathlib import Path

        from core.skills.loader import MarkdownSkillLoader

        loader = MarkdownSkillLoader()
        full_skill = loader.load_skill(Path(self.skill_dir))
        self.instructions = full_skill.instructions
        self.instructions_loaded = True

    def get_scripts(self) -> list[str]:
        """List available scripts in this skill.

        Returns:
            List of script filenames (e.g., ['transcribe.sh', 'process.py'])
        """
        if not self.scripts_dir:
            return []
        from pathlib import Path

        scripts_path = Path(self.scripts_dir)
        if not scripts_path.exists():
            return []
        return [
            f.name for f in scripts_path.iterdir() if f.is_file() and not f.name.startswith(".")
        ]

    def get_script_path(self, script_name: str) -> str | None:
        """Get full path to a script.

        Args:
            script_name: Name of script file

        Returns:
            Full path to script or None if not found
        """
        if not self.scripts_dir:
            return None
        from pathlib import Path

        script_path = Path(self.scripts_dir) / script_name
        return str(script_path) if script_path.exists() else None

class SkillGateResult(BaseModel):
    """Result of skill gating check."""

    eligible: bool
    reason: str | None = None
    missing_bins: list[str] = Field(default_factory=list)
    missing_env: list[str] = Field(default_factory=list)
    missing_config: list[str] = Field(default_factory=list)
