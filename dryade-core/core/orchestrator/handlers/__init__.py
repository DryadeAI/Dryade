"""Execution mode handlers.

Each handler implements a specific execution mode.
The router delegates to these handlers based on the execution mode.

Architecture:
    - PlannerHandler: Workflow/plan generation and execution
    - TierDispatcher: Classifies tier (INSTANT/SIMPLE/COMPLEX) and delegates
    - OrchestrateHandler: Backward-compat alias for TierDispatcher

Tier handlers (used by TierDispatcher):
    - InstantHandler: Direct LLM response, no orchestration
    - SimpleHandler: Direct agent dispatch, zero extra LLM calls
    - ComplexHandler: Full ReAct/PLAN orchestration path

Each handler follows the same interface:
    async def handle(message, context, stream) -> AsyncGenerator[ChatEvent, None]
"""

from core.orchestrator.handlers._utils import (
    VISIBILITY_DENY,
    _emit_escalation,
    _emit_reasoning,
    _emit_resource_suggestion,
    _should_emit,
)
from core.orchestrator.handlers.base import OrchestrateHandlerBase
from core.orchestrator.handlers.complex_handler import ComplexHandler, TierDispatcher
from core.orchestrator.handlers.instant_handler import InstantHandler
from core.orchestrator.handlers.planner_handler import PlannerHandler
from core.orchestrator.handlers.simple_handler import SimpleHandler

# Backward compat alias: OrchestrateHandler -> TierDispatcher
OrchestrateHandler = TierDispatcher

__all__ = [
    "PlannerHandler",
    "OrchestrateHandler",
    "TierDispatcher",
    "InstantHandler",
    "SimpleHandler",
    "ComplexHandler",
    "OrchestrateHandlerBase",
    "VISIBILITY_DENY",
    "_should_emit",
    "_emit_escalation",
    "_emit_reasoning",
    "_emit_resource_suggestion",
]
