"""Bridge between SkillRegistry and AgentRegistry.

Synchronizes skills into the agent registry as SkillAgentAdapter instances.
Handles initialization, hot-reload, and namespace conflict resolution.
"""

import logging

from core.adapters.registry import AgentRegistry, get_registry
from core.adapters.skill_adapter import SKILL_AGENT_PREFIX, SkillAgentAdapter
from core.skills.models import Skill
from core.skills.registry import SkillRegistry, get_skill_registry

logger = logging.getLogger(__name__)

class SkillAgentBridge:
    """Synchronize SkillRegistry -> AgentRegistry.

    Lifecycle:
      1. On initialize(): iterate all skills, register as adapters
      2. On skill change: listener callback re-syncs
      3. On shutdown(): optionally remove skill adapters

    Namespace:
      Skills are registered with "skill-{name}" prefix. If a coded agent
      with the same name already exists, the coded agent wins (logged warning).

    Thread safety:
      Delegates to SkillRegistry (RLock) and AgentRegistry (dict operations).
      The bridge itself is stateless between calls.
    """

    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        agent_registry: AgentRegistry | None = None,
    ):
        """Initialize bridge.

        Args:
            skill_registry: Skill registry (uses global if None)
            agent_registry: Agent registry (uses global if None)
        """
        self._skill_registry = skill_registry
        self._agent_registry = agent_registry
        self._listener_registered = False

    @property
    def skill_registry(self) -> SkillRegistry:
        return self._skill_registry or get_skill_registry()

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry or get_registry()

    def initialize(self) -> int:
        """Register all current skills as agents.

        Called during application startup after both registries exist.

        Returns:
            Number of skills registered as agents
        """
        skills = self.skill_registry.get_eligible_skills(refresh_if_stale=True)
        count = self._sync_skills(skills)

        # Register change listener for hot-reload
        if not self._listener_registered:
            self.skill_registry.add_change_listener(self._on_skills_changed)
            self._listener_registered = True
            logger.debug("Registered skill change listener on bridge")

        logger.info(f"[SKILL-BRIDGE] Initialized: {count} skills registered as agents")
        return count

    def _on_skills_changed(self, skills: list[Skill]) -> None:
        """Callback when SkillRegistry changes (hot-reload).

        Called by SkillRegistry._notify_listeners() when skills change.
        Re-syncs: removes stale adapters, adds new ones, updates existing.

        Args:
            skills: Updated full skill list
        """
        count = self._sync_skills(skills)
        logger.info(f"[SKILL-BRIDGE] Hot-reload: {count} skills synced to agent registry")

    def _sync_skills(self, skills: list[Skill]) -> int:
        """Full sync: make agent registry match skill list.

        Steps:
        1. Build target set of skill agent names
        2. Remove stale skill adapters (in registry but not in target)
        3. Add/update skill adapters

        Args:
            skills: Current skill list

        Returns:
            Number of skills registered
        """
        registry = self.agent_registry
        target_names = {f"{SKILL_AGENT_PREFIX}{s.name}" for s in skills}

        # Remove stale skill adapters
        current_agents = registry.list_agents()
        for card in current_agents:
            if card.name.startswith(SKILL_AGENT_PREFIX):
                if card.name not in target_names:
                    registry.unregister(card.name)
                    logger.debug(f"[SKILL-BRIDGE] Removed stale: {card.name}")

        # Add/update skill adapters
        registered = 0
        for skill in skills:
            adapter_name = f"{SKILL_AGENT_PREFIX}{skill.name}"

            # Conflict check: coded agent wins
            existing = registry.get(adapter_name)
            if existing and not isinstance(existing, SkillAgentAdapter):
                logger.warning(
                    f"[SKILL-BRIDGE] Name conflict: '{adapter_name}' is a coded agent. "
                    f"Skill '{skill.name}' will NOT override it."
                )
                continue

            # Register or update
            adapter = SkillAgentAdapter(skill)
            registry.register(adapter)
            registered += 1

        return registered

    def shutdown(self) -> None:
        """Remove all skill adapters and unregister listener.

        Called during application shutdown.
        """
        if self._listener_registered:
            self.skill_registry.remove_change_listener(self._on_skills_changed)
            self._listener_registered = False

        # Remove all skill adapters
        registry = self.agent_registry
        current_agents = registry.list_agents()
        for card in current_agents:
            if card.name.startswith(SKILL_AGENT_PREFIX):
                registry.unregister(card.name)

        logger.info("[SKILL-BRIDGE] Shutdown complete")

# Global bridge instance
_bridge: SkillAgentBridge | None = None

def get_skill_agent_bridge() -> SkillAgentBridge:
    """Get or create global skill-agent bridge."""
    global _bridge
    if _bridge is None:
        _bridge = SkillAgentBridge()
    return _bridge

def initialize_skill_bridge() -> int:
    """Initialize the global bridge.

    Convenience function for application startup.

    Returns:
        Number of skills registered as agents
    """
    bridge = get_skill_agent_bridge()
    return bridge.initialize()
