"""Graceful degradation handler for MCP unavailability.

When MCP is unavailable, this module provides:
1. Capability status detection (full/partial/limited)
2. Alternative capability discovery via skills
3. Fallback routing strategies

Usage:
    gd = get_graceful_degradation()
    if not gd.check_mcp_availability():
        alternatives = await gd.find_alternatives("I need to edit files")
        # Returns skill-based alternatives
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

class CapabilityStatus(Enum):
    """Capability availability status.

    FULL: MCP available, all tools accessible
    PARTIAL: MCP available but some tools failed to bind
    LIMITED: MCP unavailable, skills only
    """

    FULL = "full"
    PARTIAL = "partial"
    LIMITED = "limited"

@dataclass
class AlternativeCapability:
    """Alternative capability when primary is unavailable.

    Attributes:
        name: Capability/skill name
        type: Type of alternative (skill, local_tool, manual)
        description: What this capability does
        confidence: Match confidence score (0-1)
    """

    name: str
    type: Literal["skill", "local_tool", "manual"]
    description: str
    confidence: float  # 0-1 match confidence

class GracefulDegradation:
    """Handle MCP unavailability by offering alternatives.

    This class detects MCP availability and provides fallback
    capabilities when MCP tools are not accessible.

    Usage:
        gd = GracefulDegradation()
        if not gd.check_mcp_availability():
            status = gd.get_capability_status()
            alternatives = await gd.find_alternatives("edit files")
    """

    def __init__(self) -> None:
        """Initialize graceful degradation handler."""
        self._mcp_available: bool | None = None
        self.logger = logging.getLogger(__name__)

    def check_mcp_availability(self) -> bool:
        """Check if any MCP server is configured via Settings.

        Returns:
            True if MCP servers are configured, False otherwise.
        """
        import json

        from core.config import get_settings

        servers_json = get_settings().mcp_servers or "{}"
        try:
            servers = json.loads(servers_json)
        except (json.JSONDecodeError, TypeError):
            servers = {}

        if not servers:
            self._mcp_available = False
            self.logger.debug("MCP unavailable: no MCP servers configured")
            return False

        # TODO: Could ping the URLs for actual availability check
        self._mcp_available = True
        self.logger.debug(f"MCP available: {len(servers)} server(s) configured")
        return True

    def get_capability_status(
        self, tools_requested: int = 0, tools_bound: int = 0
    ) -> CapabilityStatus:
        """Determine capability status based on MCP and tool binding.

        Args:
            tools_requested: Number of tools requested
            tools_bound: Number of tools successfully bound

        Returns:
            CapabilityStatus indicating availability level
        """
        if not self._mcp_available:
            return CapabilityStatus.LIMITED

        if tools_requested > 0 and tools_bound < tools_requested:
            return CapabilityStatus.PARTIAL

        return CapabilityStatus.FULL

    async def find_alternatives(self, request: str) -> list[AlternativeCapability]:
        """Find alternative capabilities when MCP unavailable.

        Searches through available skills to find alternatives
        that can fulfill the request.

        Args:
            request: Natural language description of needed capability

        Returns:
            List of alternative capabilities, sorted by confidence
        """
        alternatives: list[AlternativeCapability] = []

        # Try skill router for alternatives
        try:
            from core.autonomous.router import get_skill_router
            from core.skills import get_skill_registry

            router = get_skill_router()
            registry = get_skill_registry()
            skills = registry.get_eligible_skills()

            if skills:
                matches = router.route(request, skills, top_k=3)
                for skill, score in matches:
                    alternatives.append(
                        AlternativeCapability(
                            name=skill.name,
                            type="skill",
                            description=skill.description,
                            confidence=score,
                        )
                    )
                    self.logger.debug(f"Found skill alternative: {skill.name} (score: {score:.3f})")
        except Exception as e:
            self.logger.warning(f"Skill routing failed during alternative search: {e}")

        # Suggest manual intervention if no alternatives found
        if not alternatives:
            alternatives.append(
                AlternativeCapability(
                    name="manual_intervention",
                    type="manual",
                    description=f"User may need to manually handle: {request}",
                    confidence=0.0,
                )
            )
            self.logger.info(
                f"No skill alternatives found for '{request}', suggesting manual intervention"
            )

        return alternatives

    def is_degraded(self) -> bool:
        """Check if currently operating in degraded mode.

        Returns:
            True if MCP is unavailable (limited capability)
        """
        if self._mcp_available is None:
            self.check_mcp_availability()
        return self._mcp_available is False

# Singleton pattern
_graceful_degradation: GracefulDegradation | None = None
_gd_lock = threading.Lock()

def get_graceful_degradation() -> GracefulDegradation:
    """Get or create singleton GracefulDegradation instance.

    Returns:
        Shared GracefulDegradation instance.
    """
    global _graceful_degradation
    if _graceful_degradation is None:
        with _gd_lock:
            if _graceful_degradation is None:
                _graceful_degradation = GracefulDegradation()
    return _graceful_degradation

def reset_graceful_degradation() -> None:
    """Reset the singleton (for testing).

    Clears the singleton so the next call creates a fresh instance.
    """
    global _graceful_degradation
    _graceful_degradation = None
