"""CrewAI integration for Dryade.

Provides:
- Event bridging and SSE streaming for CrewAI execution
- Graceful degradation when MCP is unavailable
"""

from core.crew.event_bridge import CrewAIEventBridge, SSEEvent
from core.crew.graceful_degradation import (
    AlternativeCapability,
    CapabilityStatus,
    GracefulDegradation,
    get_graceful_degradation,
    reset_graceful_degradation,
)

__all__ = [
    # Event Bridge (from 67-01)
    "CrewAIEventBridge",
    "SSEEvent",
    # Graceful Degradation
    "GracefulDegradation",
    "CapabilityStatus",
    "AlternativeCapability",
    "get_graceful_degradation",
    "reset_graceful_degradation",
]
