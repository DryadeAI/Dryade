"""SKILL.md loader for AgentSkills format.

Parses markdown skill files with YAML frontmatter.
Implements skill gating based on system requirements.
"""

import json
import logging
import os
import platform
import shutil
from pathlib import Path
from typing import Any

import yaml

from core.skills.models import Skill, SkillGateResult, SkillMetadata, SkillRequirements

logger = logging.getLogger(__name__)

class MarkdownSkillLoader:
    """Load and parse SKILL.md files (AgentSkills format).

    Skill directory structure:
        skill-name/
            SKILL.md          # Required
            scripts/          # Optional: executable code
            references/       # Optional: additional documentation

    Loading hierarchy (later overrides earlier):
        1. Bundled skills (shipped with Dryade plugins)
        2. Managed skills (~/.dryade/skills/)
        3. Workspace skills (<workspace>/skills/)
    """

    SKILL_FILE = "SKILL.md"

    def __init__(self):
        """Initialize loader with current platform info."""
        self._platform = platform.system().lower()
        # Map Python platform names to AgentSkills convention
        self._os_map = {
            "darwin": "darwin",
            "linux": "linux",
            "windows": "win32",
        }
        self._current_os = self._os_map.get(self._platform, self._platform)

    def load_skill(self, skill_dir: Path) -> Skill:
        """Load a single skill from a directory.

        Args:
            skill_dir: Path to skill directory containing SKILL.md

        Returns:
            Parsed Skill object

        Raises:
            FileNotFoundError: If SKILL.md not found
            ValueError: If SKILL.md format is invalid
        """
        skill_md = skill_dir / self.SKILL_FILE
        if not skill_md.exists():
            raise FileNotFoundError(f"No {self.SKILL_FILE} in {skill_dir}")

        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(content)

        # Extract metadata with nested structure handling
        raw_metadata = frontmatter.get("metadata", {})
        if isinstance(raw_metadata, str):
            # Handle JSON-encoded metadata (common in some AgentSkills)
            try:
                raw_metadata = json.loads(raw_metadata)
            except json.JSONDecodeError:
                raw_metadata = {}

        # Extract Dryade-specific metadata (could be under "dryade" or "clawdbot" key)
        dryade_meta = raw_metadata.get("dryade", raw_metadata.get("clawdbot", raw_metadata))

        # Build requirements
        requires_data = dryade_meta.get("requires", {})
        requirements = SkillRequirements(
            bins=requires_data.get("bins", []),
            env=requires_data.get("env", []),
            config=requires_data.get("config", []),
        )

        # Get chat_eligible from metadata (default True)
        chat_eligible = dryade_meta.get("chat_eligible", True)

        # Build metadata
        metadata = SkillMetadata(
            emoji=dryade_meta.get("emoji"),
            os=dryade_meta.get("os", []),
            requires=requirements,
            extra={
                k: v
                for k, v in dryade_meta.items()
                if k not in ("emoji", "os", "requires", "chat_eligible")
            },
            chat_eligible=chat_eligible,
        )

        # Detect scripts/ folder (OpenClaw pattern)
        scripts_path = skill_dir / "scripts"
        scripts_dir = str(scripts_path) if scripts_path.exists() and scripts_path.is_dir() else None
        has_scripts = (
            scripts_dir is not None and any(scripts_path.iterdir()) if scripts_dir else False
        )

        return Skill(
            name=frontmatter.get("name", skill_dir.name),
            description=frontmatter.get("description", ""),
            instructions=body.strip(),
            metadata=metadata,
            skill_dir=str(skill_dir),
            scripts_dir=scripts_dir,
            has_scripts=has_scripts,
            chat_eligible=chat_eligible,
        )

    def load_metadata_only(self, skill_dir: Path) -> Skill:
        """Load skill metadata without full instruction body (Stage 1).

        Reads frontmatter (name, description, metadata) but defers the
        markdown instruction body. Use ensure_instructions_loaded() on the
        returned Skill before accessing instructions for execution.

        Args:
            skill_dir: Path to skill directory containing SKILL.md

        Returns:
            Skill with instructions="" and instructions_loaded=False

        Raises:
            FileNotFoundError: If SKILL.md not found
            ValueError: If SKILL.md format is invalid
        """
        skill_md = skill_dir / self.SKILL_FILE
        if not skill_md.exists():
            raise FileNotFoundError(f"No {self.SKILL_FILE} in {skill_dir}")

        content = skill_md.read_text(encoding="utf-8")
        frontmatter, _ = self._parse_frontmatter(content)

        # Same metadata extraction as load_skill()
        raw_metadata = frontmatter.get("metadata", {})
        if isinstance(raw_metadata, str):
            try:
                raw_metadata = json.loads(raw_metadata)
            except json.JSONDecodeError:
                raw_metadata = {}

        dryade_meta = raw_metadata.get("dryade", raw_metadata.get("clawdbot", raw_metadata))

        requires_data = dryade_meta.get("requires", {})
        requirements = SkillRequirements(
            bins=requires_data.get("bins", []),
            env=requires_data.get("env", []),
            config=requires_data.get("config", []),
        )

        chat_eligible = dryade_meta.get("chat_eligible", True)

        metadata = SkillMetadata(
            emoji=dryade_meta.get("emoji"),
            os=dryade_meta.get("os", []),
            requires=requirements,
            extra={
                k: v
                for k, v in dryade_meta.items()
                if k not in ("emoji", "os", "requires", "chat_eligible")
            },
            chat_eligible=chat_eligible,
        )

        scripts_path = skill_dir / "scripts"
        scripts_dir = str(scripts_path) if scripts_path.exists() and scripts_path.is_dir() else None
        has_scripts = (
            scripts_dir is not None and any(scripts_path.iterdir()) if scripts_dir else False
        )

        return Skill(
            name=frontmatter.get("name", skill_dir.name),
            description=frontmatter.get("description", ""),
            instructions="",  # Deferred -- Stage 2
            metadata=metadata,
            skill_dir=str(skill_dir),
            scripts_dir=scripts_dir,
            has_scripts=has_scripts,
            chat_eligible=chat_eligible,
            instructions_loaded=False,  # Flag for lazy loading
        )

    def _parse_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML frontmatter from markdown content.

        Args:
            content: Full SKILL.md content

        Returns:
            (frontmatter dict, markdown body)

        Raises:
            ValueError: If frontmatter format is invalid
        """
        lines = content.split("\n")
        if not lines or lines[0].strip() != "---":
            raise ValueError("SKILL.md must start with ---")

        frontmatter_lines = []
        body_start = 1
        found_end = False

        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body_start = i + 1
                found_end = True
                break
            frontmatter_lines.append(line)

        if not found_end:
            raise ValueError("SKILL.md frontmatter must be closed with ---")

        frontmatter = yaml.safe_load("\n".join(frontmatter_lines)) or {}
        body = "\n".join(lines[body_start:])

        return frontmatter, body

    def check_skill_eligibility(self, skill: Skill) -> SkillGateResult:
        """Check if a skill is eligible to run on current system.

        Gating checks:
        1. OS platform match
        2. Required binaries available
        3. Required environment variables set
        4. Required config paths exist

        Args:
            skill: Skill to check

        Returns:
            SkillGateResult with eligibility status
        """
        missing_bins = []
        missing_env = []
        missing_config = []

        meta = skill.metadata

        # 1. Check OS platform
        if meta.os and self._current_os not in meta.os:
            return SkillGateResult(
                eligible=False,
                reason=f"OS mismatch: skill requires {meta.os}, current is {self._current_os}",
            )

        # 2. Check required binaries
        for binary in meta.requires.bins:
            if not shutil.which(binary):
                missing_bins.append(binary)

        # 3. Check required environment variables
        for env_var in meta.requires.env:
            if not os.environ.get(env_var):
                missing_env.append(env_var)

        # 4. Check required config paths
        for config_path in meta.requires.config:
            expanded = Path(config_path).expanduser()
            if not expanded.exists():
                missing_config.append(config_path)

        # Determine eligibility
        if missing_bins or missing_env or missing_config:
            reasons = []
            if missing_bins:
                reasons.append(f"missing binaries: {missing_bins}")
            if missing_env:
                reasons.append(f"missing env vars: {missing_env}")
            if missing_config:
                reasons.append(f"missing config: {missing_config}")

            return SkillGateResult(
                eligible=False,
                reason="; ".join(reasons),
                missing_bins=missing_bins,
                missing_env=missing_env,
                missing_config=missing_config,
            )

        return SkillGateResult(eligible=True)

    def discover_skills(
        self,
        search_paths: list[Path],
        filter_eligible: bool = True,
        metadata_only: bool = False,
    ) -> list[Skill]:
        """Discover skills from multiple search paths.

        Later paths override earlier (workspace > managed > bundled).

        Args:
            search_paths: List of directories to search for skills
            filter_eligible: If True, only return eligible skills
            metadata_only: If True, load only frontmatter (Stage 1). Default False for full loading.

        Returns:
            List of discovered skills (deduplicated by name)
        """
        skills_by_name: dict[str, Skill] = {}

        for search_path in search_paths:
            if not search_path.exists():
                logger.debug(f"Skill search path not found: {search_path}")
                continue

            for item in search_path.iterdir():
                if item.is_dir() and (item / self.SKILL_FILE).exists():
                    try:
                        skill = (
                            self.load_metadata_only(item)
                            if metadata_only
                            else self.load_skill(item)
                        )

                        if filter_eligible:
                            gate_result = self.check_skill_eligibility(skill)
                            if not gate_result.eligible:
                                logger.debug(
                                    f"Skill '{skill.name}' not eligible: {gate_result.reason}"
                                )
                                continue

                        # Later paths override earlier
                        if skill.name in skills_by_name:
                            logger.debug(f"Skill '{skill.name}' overridden by {item}")
                        skills_by_name[skill.name] = skill

                    except Exception as e:
                        logger.warning(f"Failed to load skill from {item}: {e}")

        logger.info(f"Discovered {len(skills_by_name)} skills from {len(search_paths)} paths")
        return list(skills_by_name.values())
