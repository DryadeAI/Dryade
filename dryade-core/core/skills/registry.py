"""Skill registry for global skill management.

Provides centralized skill discovery with caching and hot reload support.
"""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from core.skills.loader import MarkdownSkillLoader
from core.skills.models import Skill

logger = logging.getLogger(__name__)

class SkillRegistry:
    """Central registry for all markdown skills.

    Features:
    - Cached skill discovery with TTL
    - Hot reload via file watcher integration
    - Session-scoped snapshots for execution consistency
    - Thread-safe operations

    Usage:
        registry = get_skill_registry()
        skills = registry.get_eligible_skills()
        snapshot = registry.create_snapshot()  # For session
    """

    DEFAULT_CACHE_TTL = 60  # 60 seconds cache
    DEFAULT_SEARCH_PATHS = [
        Path("plugins"),  # Bundled skills
        Path.home() / ".dryade" / "skills",  # Managed skills
        Path("skills"),  # Workspace skills
    ]

    def __init__(
        self, search_paths: list[Path] | None = None, cache_ttl: float = DEFAULT_CACHE_TTL
    ):
        """Initialize skill registry.

        Args:
            search_paths: Custom skill search paths (uses defaults if None)
            cache_ttl: Cache time-to-live in seconds
        """
        self._loader = MarkdownSkillLoader()
        self._search_paths = search_paths or self._build_default_search_paths()
        self._cache_ttl = cache_ttl

        # Cache state
        self._skills_cache: dict[str, Skill] = {}
        self._cache_time: float = 0
        self._lock = threading.RLock()

        # Change listeners for hot reload
        self._listeners: list[Callable[[list[Skill]], None]] = []

        # Initial load
        self._refresh_cache()

    def _build_default_search_paths(self) -> list[Path]:
        """Build default search paths for skills.

        Order (later overrides earlier):
        1. Bundled skills from plugins
        2. Managed skills (~/.dryade/skills/)
        3. Workspace skills (./skills/)
        """
        paths = []

        # 1. Bundled skills from plugins
        from core.config import get_settings

        plugins_dir = Path(get_settings().plugins_dir)
        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    skills_dir = plugin_dir / "skills"
                    if skills_dir.exists():
                        paths.append(skills_dir)

        # 2. Managed skills
        managed_dir = Path.home() / ".dryade" / "skills"
        paths.append(managed_dir)  # Add even if doesn't exist yet

        # 3. Workspace skills
        workspace_dir = Path("skills")
        paths.append(workspace_dir)  # Add even if doesn't exist yet

        return paths

    def _refresh_cache(self) -> None:
        """Refresh skill cache from disk and MCP tools.

        Thread-safe cache refresh. Loads both SKILL.md files and MCP tools.
        """
        with self._lock:
            try:
                # Filter to existing paths
                existing_paths = [p for p in self._search_paths if p.exists()]

                # Load SKILL.md files
                skills = self._loader.discover_skills(
                    existing_paths, filter_eligible=False, metadata_only=True
                )
                self._skills_cache = {s.name: s for s in skills}
                md_count = len(self._skills_cache)

                # Load MCP tools as skills
                mcp_count = self._load_mcp_tools_as_skills()

                self._cache_time = time.time()

                logger.info(
                    f"Skill registry refreshed: {md_count} SKILL.md + {mcp_count} MCP tools"
                )

            except Exception as e:
                logger.error(f"Failed to refresh skill cache: {e}")

    def _load_mcp_tools_as_skills(self) -> int:
        """Load MCP @tool decorated functions as Skills.

        Discovers tools from core.mcp.bridge and converts them to Skill
        objects. This enables autonomous mode to use MCP tools alongside
        SKILL.md defined skills.

        Returns:
            Number of MCP tools loaded
        """
        try:
            from core.skills.mcp_bridge import discover_mcp_tools_as_skills

            mcp_skills = discover_mcp_tools_as_skills()

            for skill in mcp_skills:
                self._skills_cache[skill.name] = skill

            if mcp_skills:
                logger.debug(f"Loaded {len(mcp_skills)} MCP tools as skills")

            return len(mcp_skills)

        except ImportError:
            logger.debug("MCP bridge not available - skipping MCP tool loading")
            return 0
        except Exception as e:
            logger.warning(f"Failed to load MCP tools as skills: {e}")
            return 0

    def _is_cache_stale(self) -> bool:
        """Check if cache has expired."""
        return time.time() - self._cache_time > self._cache_ttl

    def refresh(self) -> None:
        """Force refresh skill cache.

        Called by file watcher on changes.
        """
        self._refresh_cache()
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        """Notify registered listeners of skill changes."""
        skills = list(self._skills_cache.values())
        for listener in self._listeners:
            try:
                listener(skills)
            except Exception as e:
                logger.error(f"Skill change listener error: {e}")

    def add_change_listener(self, callback: Callable[[list[Skill]], None]) -> None:
        """Register a callback for skill changes.

        Args:
            callback: Function called with updated skill list
        """
        self._listeners.append(callback)

    def remove_change_listener(self, callback: Callable[[list[Skill]], None]) -> None:
        """Unregister a change callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def get_all_skills(self, refresh_if_stale: bool = True) -> list[Skill]:
        """Get all discovered skills (including ineligible).

        Args:
            refresh_if_stale: Refresh cache if TTL expired

        Returns:
            List of all skills
        """
        with self._lock:
            if refresh_if_stale and self._is_cache_stale():
                self._refresh_cache()
            return list(self._skills_cache.values())

    def get_eligible_skills(self, refresh_if_stale: bool = True) -> list[Skill]:
        """Get skills that pass gating checks.

        Args:
            refresh_if_stale: Refresh cache if TTL expired

        Returns:
            List of eligible skills
        """
        all_skills = self.get_all_skills(refresh_if_stale)
        eligible = []

        for skill in all_skills:
            gate_result = self._loader.check_skill_eligibility(skill)
            if gate_result.eligible:
                eligible.append(skill)

        return eligible

    def get_skill(self, name: str) -> Skill | None:
        """Get a specific skill by name.

        Automatically loads full instructions if the skill was cached
        via metadata_only (lazy Stage 2 loading).

        Args:
            name: Skill name

        Returns:
            Skill if found, None otherwise
        """
        with self._lock:
            if self._is_cache_stale():
                self._refresh_cache()
            skill = self._skills_cache.get(name)
        if skill is not None:
            skill.ensure_instructions_loaded()
        return skill

    def create_snapshot(self, eligible_only: bool = True) -> "SkillSnapshot":
        """Create a point-in-time snapshot of skills.

        Use for session-scoped skill sets to ensure consistency
        during execution.

        Args:
            eligible_only: Only include eligible skills

        Returns:
            Immutable skill snapshot
        """
        if eligible_only:
            skills = self.get_eligible_skills(refresh_if_stale=True)
        else:
            skills = self.get_all_skills(refresh_if_stale=True)

        return SkillSnapshot(skills)

    def get_search_paths(self) -> list[Path]:
        """Get configured search paths."""
        return list(self._search_paths)

    def add_search_path(self, path: Path) -> None:
        """Add a search path for skill discovery.

        Args:
            path: Directory to add to search paths
        """
        with self._lock:
            if path not in self._search_paths:
                self._search_paths.append(path)
                self._refresh_cache()

    def register_skill(self, skill: Skill, persist: bool = False) -> bool:
        """Register a skill dynamically at runtime.

        Adds skill to cache and notifies listeners (including router).
        Optionally persists to disk.

        Args:
            skill: Skill to register
            persist: If True, saves skill to disk in managed skills directory

        Returns:
            True if registered successfully
        """
        with self._lock:
            # Add to cache
            self._skills_cache[skill.name] = skill

            # Persist if requested
            if persist:
                self._persist_skill(skill)

            logger.info(f"Registered skill: {skill.name} (persist={persist})")

        # Notify listeners (router will update its index)
        self._notify_listeners()
        return True

    def _persist_skill(self, skill: Skill) -> Path:
        """Persist skill to managed skills directory.

        Args:
            skill: Skill to persist

        Returns:
            Path where skill was saved
        """
        managed_dir = Path.home() / ".dryade" / "skills" / skill.name
        managed_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_md_path = managed_dir / "SKILL.md"

        # Format skill as markdown
        skill_content = f"""---
name: {skill.name}
description: {skill.description}
version: "1.0.0"
---

# {skill.name}

{skill.description}

## Instructions

{skill.instructions}
"""
        skill_md_path.write_text(skill_content)
        logger.debug(f"Persisted skill to {skill_md_path}")
        return managed_dir

    def unregister_skill(self, skill_name: str) -> bool:
        """Remove a skill from the registry.

        Does NOT delete from disk - only removes from cache.

        Args:
            skill_name: Name of skill to remove

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if skill_name not in self._skills_cache:
                return False
            del self._skills_cache[skill_name]

        self._notify_listeners()
        logger.info(f"Unregistered skill: {skill_name}")
        return True

class SkillSnapshot:
    """Immutable point-in-time snapshot of skills.

    Use for session-scoped skill injection to ensure
    consistent skill set during execution.
    """

    def __init__(self, skills: list[Skill]):
        """Create snapshot from skill list.

        Args:
            skills: Skills to include in snapshot
        """
        self._skills = tuple(skills)
        self._skills_by_name = {s.name: s for s in skills}
        self._timestamp = time.time()

    @property
    def skills(self) -> tuple[Skill, ...]:
        """Get all skills in snapshot."""
        return self._skills

    @property
    def timestamp(self) -> float:
        """Get snapshot creation time."""
        return self._timestamp

    def get(self, name: str) -> Skill | None:
        """Get skill by name from snapshot."""
        return self._skills_by_name.get(name)

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self):
        return iter(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills_by_name

# =============================================================================
# Global Registry Singleton
# =============================================================================

_registry: SkillRegistry | None = None
_registry_lock = threading.Lock()

def get_skill_registry() -> SkillRegistry:
    """Get or create global skill registry.

    Returns:
        Singleton SkillRegistry instance
    """
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = SkillRegistry()

                # Wire router as change listener for hot-reload
                try:
                    from core.autonomous.router import get_skill_router

                    router = get_skill_router()
                    _registry.add_change_listener(lambda skills: router.index_skills(skills))
                    logger.debug("Wired skill router as registry change listener")
                except ImportError:
                    logger.debug("Skill router not available for change listener")

                # Wire skill-agent bridge for orchestrator visibility
                try:
                    from core.adapters.skill_bridge import initialize_skill_bridge

                    initialize_skill_bridge()
                    logger.debug("Initialized skill-agent bridge")
                except ImportError:
                    logger.debug("Skill-agent bridge not available")

    return _registry

def reset_skill_registry() -> None:
    """Reset global skill registry.

    Primarily for testing.
    """
    global _registry
    with _registry_lock:
        _registry = None

# =============================================================================
# Hot-Reload Helper Functions
# =============================================================================

def register_skill_from_path(skill_path: Path, persist: bool = False) -> Skill | None:
    """Load and register a skill from a directory.

    Convenience function for registering skills from disk.

    Args:
        skill_path: Path to skill directory (must contain SKILL.md)
        persist: If True, copies to managed directory

    Returns:
        Registered Skill or None if failed
    """
    registry = get_skill_registry()

    try:
        loader = MarkdownSkillLoader()
        skill = loader.load_skill(skill_path)
        if skill:
            registry.register_skill(skill, persist=persist)
            return skill
    except Exception as e:
        logger.error(f"Failed to register skill from {skill_path}: {e}")

    return None

def create_and_register_skill(
    name: str,
    description: str,
    instructions: str,
    persist: bool = True,
) -> Skill:
    """Create a new skill and register it.

    Convenience function for programmatic skill creation.

    Args:
        name: Skill name (slug format recommended)
        description: What the skill does
        instructions: Execution instructions
        persist: If True, saves to managed directory

    Returns:
        Created and registered Skill
    """
    from core.skills.models import SkillMetadata

    # Determine skill directory path
    managed_dir = Path.home() / ".dryade" / "skills" / name

    skill = Skill(
        name=name,
        description=description,
        instructions=instructions,
        metadata=SkillMetadata(),
        skill_dir=str(managed_dir),
    )

    registry = get_skill_registry()
    registry.register_skill(skill, persist=persist)

    return skill
