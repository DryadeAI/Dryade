"""Autonomous skill execution layer for Dryade.

This module provides the foundational infrastructure for autonomous skill execution:

- **Models** (models.py): Pydantic models for execution state, thoughts, observations,
  and results used throughout the autonomous execution pipeline.

- **Leash** (leash.py): Configurable autonomy constraints that enforce resource limits,
  time bounds, and dangerous action detection. Supports per-skill or global configuration.

- **Audit** (audit.py): Comprehensive audit logging for regulatory compliance (EU AI Act,
  FDA, financial regulators). Captures every autonomous decision with full context.

The autonomous execution layer enables:
- ReAct-style reasoning loops with tool/skill invocation
- Goal-driven plan-and-execute workflows
- Self-development sandbox for agent-generated code
- Human-in-the-loop escalation when constraints are exceeded
"""

from core.autonomous.audit import AuditEntry, AuditLogger
from core.autonomous.executor import (
    DefaultSkillExecutor,
    HumanInputHandler,
    ReActExecutor,
    SkillExecutor,
    ThinkingProvider,
)
from core.autonomous.leash import (
    LEASH_CONSERVATIVE,
    LEASH_PERMISSIVE,
    LEASH_STANDARD,
    LeashConfig,
    LeashResult,
)
from core.autonomous.models import (
    ActionType,
    CapabilityNegotiationRequest,
    CapabilityNegotiationResult,
    ExecutionResult,
    ExecutionState,
    GoalResult,
    Observation,
    SkillCreationRequest,
    Thought,
)
from core.autonomous.planner import (
    Plan,
    PlanAndExecuteAutonomy,
    PlanningProvider,
    PlanStep,
    StepExecutor,
)
from core.autonomous.router import (
    IntelligentSkillRouter,
    get_skill_router,
    reset_skill_router,
)
from core.autonomous.scheduler import (
    ProactiveScheduler,
    ScheduledJob,
    get_proactive_scheduler,
    reset_proactive_scheduler,
)
from core.autonomous.skill_creator import (
    LLMSkillGenerator,
    SkillCreationResult,
    SkillCreator,
    get_skill_creator,
    reset_skill_creator,
)

__all__ = [
    # Models
    "ActionType",
    "CapabilityNegotiationRequest",
    "CapabilityNegotiationResult",
    "ExecutionState",
    "Thought",
    "Observation",
    "ExecutionResult",
    "GoalResult",
    "SkillCreationRequest",
    # Leash
    "LeashConfig",
    "LeashResult",
    "LEASH_CONSERVATIVE",
    "LEASH_STANDARD",
    "LEASH_PERMISSIVE",
    # Audit
    "AuditEntry",
    "AuditLogger",
    # Router
    "IntelligentSkillRouter",
    "get_skill_router",
    "reset_skill_router",
    # Planner
    "PlanAndExecuteAutonomy",
    "PlanningProvider",
    "StepExecutor",
    "Plan",
    "PlanStep",
    # Executor
    "ReActExecutor",
    "DefaultSkillExecutor",
    "ThinkingProvider",
    "SkillExecutor",
    "HumanInputHandler",
    # Scheduler
    "ProactiveScheduler",
    "ScheduledJob",
    "get_proactive_scheduler",
    "reset_proactive_scheduler",
    # Skill Creator
    "SkillCreator",
    "SkillCreationResult",
    "LLMSkillGenerator",
    "get_skill_creator",
    "reset_skill_creator",
]
