"""Thinking package for native orchestration.

Re-exports all public symbols so that existing imports like
``from core.orchestrator.thinking import OrchestrationThinkingProvider``
continue to work unchanged.
"""

from core.orchestrator.thinking.prompts import (
    FAILURE_SYSTEM_PROMPT,
    LIGHTWEIGHT_AGENT_ADDENDUM,
    MANAGER_SYSTEM_PROMPT,
    ORCHESTRATE_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    REPLAN_SYSTEM_PROMPT,
    SYNTHESIZE_SYSTEM_PROMPT,
    _format_agents_xml,
)
from core.orchestrator.thinking.provider import OrchestrationThinkingProvider

__all__ = [
    "OrchestrationThinkingProvider",
    "ORCHESTRATE_SYSTEM_PROMPT",
    "FAILURE_SYSTEM_PROMPT",
    "MANAGER_SYSTEM_PROMPT",
    "PLAN_SYSTEM_PROMPT",
    "REPLAN_SYSTEM_PROMPT",
    "SYNTHESIZE_SYSTEM_PROMPT",
    "LIGHTWEIGHT_AGENT_ADDENDUM",
    "_format_agents_xml",
]
