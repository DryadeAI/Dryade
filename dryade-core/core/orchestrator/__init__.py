"""Dryade Orchestrator.

Routes execution between chat, crew, and flow modes.
Provides native orchestration via DryadeOrchestrator.
"""

from core.orchestrator.failure_metrics import (
    SLO_CIRCUIT_BREAKER_TRIP_MS,
    SLO_FAILURE_DETECTION_MS,
    SLO_RECOVERY_DECISION_DETERMINISTIC_MS,
    SLO_RECOVERY_DECISION_LLM_MS,
)
from core.orchestrator.models import (
    FailureAction,
    OrchestrationMode,
    OrchestrationObservation,
    OrchestrationResult,
    OrchestrationState,
    OrchestrationTask,
    OrchestrationThought,
    Tier,
)
from core.orchestrator.orchestrator import DryadeOrchestrator
from core.orchestrator.router import (
    ExecutionContext,
    ExecutionMode,
    ExecutionRouter,
    get_router,
    route_request,
)
from core.orchestrator.thinking import OrchestrationThinkingProvider

__all__ = [
    # Router (existing)
    "ExecutionRouter",
    "ExecutionMode",
    "ExecutionContext",
    "get_router",
    "route_request",
    # Native orchestration
    "DryadeOrchestrator",
    "OrchestrationThinkingProvider",
    # Models
    "FailureAction",
    "OrchestrationMode",
    "Tier",
    "OrchestrationTask",
    "OrchestrationThought",
    "OrchestrationObservation",
    "OrchestrationState",
    "OrchestrationResult",
    # SLO constants (from failure_metrics)
    "SLO_FAILURE_DETECTION_MS",
    "SLO_RECOVERY_DECISION_DETERMINISTIC_MS",
    "SLO_RECOVERY_DECISION_LLM_MS",
    "SLO_CIRCUIT_BREAKER_TRIP_MS",
]
