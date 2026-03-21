"""AgentSkills (SKILL.md) support for Dryade.

Enables markdown-based skill files for natural language capability injection.
Follows the AgentSkills specification (https://agentskills.io/specification).

Components:
- loader: Parse SKILL.md files with gating
- adapter: Format skills for system prompt injection
- registry: Global skill management with caching
- watcher: File watching for hot reload

Usage:
    from core.skills import get_skill_registry, format_skills_for_prompt

    # Get eligible skills
    registry = get_skill_registry()
    skills = registry.get_eligible_skills()

    # Format for prompt
    skill_context = format_skills_for_prompt(skills)
"""

from core.skills.adapter import MarkdownSkillAdapter, format_skills_for_prompt
from core.skills.loader import MarkdownSkillLoader
from core.skills.models import Skill, SkillGateResult, SkillMetadata, SkillRequirements
from core.skills.registry import (
    SkillRegistry,
    SkillSnapshot,
    create_and_register_skill,
    get_skill_registry,
    register_skill_from_path,
    reset_skill_registry,
)
from core.skills.watcher import (
    SkillWatcher,
    get_skill_watcher,
    is_hot_reload_available,
    start_skill_watcher,
    stop_skill_watcher,
)

__all__ = [
    # Models
    "Skill",
    "SkillMetadata",
    "SkillRequirements",
    "SkillGateResult",
    # Loader
    "MarkdownSkillLoader",
    # Adapter
    "MarkdownSkillAdapter",
    "format_skills_for_prompt",
    # Registry
    "SkillRegistry",
    "SkillSnapshot",
    "get_skill_registry",
    "reset_skill_registry",
    # Hot-reload helpers
    "register_skill_from_path",
    "create_and_register_skill",
    # Watcher
    "SkillWatcher",
    "get_skill_watcher",
    "start_skill_watcher",
    "stop_skill_watcher",
    "is_hot_reload_available",
]
