"""Plan-and-Execute autonomy for complex goal-driven planning.

While ReAct handles reactive execution, Plan-and-Execute handles
complex goals requiring multi-step coordination:

1. PLAN: Large model creates multi-step plan
2. EXECUTE: Smaller models execute individual steps
3. REPLAN: Adjust plan when execution deviates

Based on:
- LangGraph Plan-and-Execute pattern
- Dryade's existing planner mode
- Research from 66.1-RESEARCH.md
"""

import logging
from typing import TYPE_CHECKING, Any, Protocol

from core.autonomous.audit import AuditLogger
from core.autonomous.leash import LeashConfig
from core.autonomous.models import ExecutionResult, ExecutionState, GoalResult

if TYPE_CHECKING:
    from core.skills import Skill, SkillSnapshot

logger = logging.getLogger(__name__)

class PlanStep:
    """Single step in execution plan."""

    def __init__(
        self,
        step_id: int,
        description: str,
        skill_hint: str | None = None,
        inputs_hint: dict[str, Any] | None = None,
        depends_on: list[int] | None = None,
    ):
        """Initialize plan step.

        Args:
            step_id: Unique step identifier
            description: What this step accomplishes
            skill_hint: Suggested skill to use (optional)
            inputs_hint: Suggested inputs (optional)
            depends_on: Step IDs this depends on
        """
        self.step_id = step_id
        self.description = description
        self.skill_hint = skill_hint
        self.inputs_hint = inputs_hint or {}
        self.depends_on = depends_on or []

    def __repr__(self) -> str:
        return f"PlanStep({self.step_id}: {self.description[:50]}...)"

class Plan:
    """Multi-step execution plan."""

    def __init__(self, goal: str, steps: list[PlanStep]):
        """Initialize plan.

        Args:
            goal: Original goal
            steps: Ordered list of steps
        """
        self.goal = goal
        self.steps = steps
        self.current_step_index = 0

    @property
    def current_step(self) -> PlanStep | None:
        """Get current step to execute."""
        if self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def remaining_steps(self) -> list[PlanStep]:
        """Get remaining steps."""
        return self.steps[self.current_step_index :]

    @property
    def is_complete(self) -> bool:
        """Check if all steps completed."""
        return self.current_step_index >= len(self.steps)

    def advance(self) -> None:
        """Move to next step."""
        self.current_step_index += 1

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "goal": self.goal,
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "skill_hint": s.skill_hint,
                    "inputs_hint": s.inputs_hint,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
            "current_step_index": self.current_step_index,
        }

class PlanningProvider(Protocol):
    """Protocol for LLM planning provider.

    Implementations generate and revise execution plans.
    """

    async def create_plan(
        self, goal: str, available_skills: list["Skill"], context: dict[str, Any]
    ) -> Plan:
        """Create initial execution plan.

        Args:
            goal: What to achieve
            available_skills: Skills that can be used
            context: Additional context

        Returns:
            Multi-step execution plan
        """
        ...

    async def should_replan(
        self, plan: Plan, step_result: ExecutionResult, context: dict[str, Any]
    ) -> bool:
        """Determine if replanning needed.

        Args:
            plan: Current plan
            step_result: Result from last step
            context: Execution context

        Returns:
            True if plan should be revised
        """
        ...

    async def replan(
        self,
        original_goal: str,
        completed_steps: list[tuple[PlanStep, ExecutionResult]],
        failed_step: PlanStep | None,
        available_skills: list["Skill"],
        context: dict[str, Any],
    ) -> Plan:
        """Create revised plan based on execution results.

        Args:
            original_goal: Original goal
            completed_steps: Successfully completed steps
            failed_step: Step that failed (if any)
            available_skills: Available skills
            context: Execution context

        Returns:
            Revised execution plan
        """
        ...

class StepExecutor(Protocol):
    """Protocol for step execution.

    Implementations execute individual plan steps.
    Can be ReActExecutor or simpler direct execution.
    """

    async def execute_step(
        self, step: PlanStep, skills: list["Skill"], context: dict[str, Any]
    ) -> ExecutionResult:
        """Execute a single plan step.

        Args:
            step: Step to execute
            skills: Available skills
            context: Execution context

        Returns:
            Execution result
        """
        ...

class PlanAndExecuteAutonomy:
    """Goal-driven autonomy using plan-and-execute pattern.

    For complex goals requiring multiple coordinated steps:
    1. Large model creates initial plan
    2. Steps executed individually (can use smaller models)
    3. Replanning when execution deviates

    Use ReActExecutor for reactive/simple tasks.
    Use PlanAndExecuteAutonomy for complex multi-step goals.

    Example:
        autonomy = PlanAndExecuteAutonomy(
            planning_provider=my_planner,
            step_executor=my_react_executor,
            leash=LeashConfig(max_actions=50)
        )
        result = await autonomy.achieve_goal(
            goal="Set up CI/CD pipeline for my project",
            skills=skill_snapshot,
            context={"repo": "my-app"}
        )
    """

    # Heuristic: goals with estimated steps > this use Plan-and-Execute
    COMPLEXITY_THRESHOLD = 3

    def __init__(
        self,
        planning_provider: PlanningProvider,
        step_executor: StepExecutor,
        leash: LeashConfig | None = None,
        max_replans: int = 3,
        session_id: str | None = None,
        initiator_id: str = "user",
    ):
        """Initialize Plan-and-Execute autonomy.

        Args:
            planning_provider: LLM for planning
            step_executor: Handler for step execution
            leash: Autonomy constraints
            max_replans: Maximum replanning attempts
            session_id: Unique session ID
            initiator_id: Who initiated execution
        """
        self.planning = planning_provider
        self.step_executor = step_executor
        self.leash = leash or LeashConfig()
        self.max_replans = max_replans
        self.audit = AuditLogger(session_id=session_id, initiator_id=initiator_id)

    async def achieve_goal(
        self,
        goal: str,
        skills: "SkillSnapshot | list[Skill]",
        context: dict[str, Any] | None = None,
    ) -> GoalResult:
        """Execute goal using plan-and-execute pattern.

        Args:
            goal: What to achieve
            skills: Available skills
            context: Additional context

        Returns:
            GoalResult with completion status
        """
        context = context or {}
        skill_list = list(skills) if hasattr(skills, "__iter__") else list(skills.skills)
        state = ExecutionState()
        completed_steps: list[tuple[PlanStep, ExecutionResult]] = []
        replan_count = 0

        logger.info(f"[PlanExecute] Creating plan for goal: {goal[:100]}...")

        # 1. Create initial plan
        try:
            plan = await self.planning.create_plan(goal, skill_list, context)
            self.audit.log_plan([s.description for s in plan.steps], goal)
            logger.info(f"[PlanExecute] Plan created with {len(plan.steps)} steps")
        except Exception as e:
            logger.error(f"[PlanExecute] Planning failed: {e}")
            return GoalResult(success=False, failed_step="planning")

        # 2. Execute plan steps
        while not plan.is_complete:
            current_step = plan.current_step
            if current_step is None:
                break

            # Check leash before each step
            leash_result = self.leash.exceeded(state)
            if leash_result.exceeded:
                self.audit.log_leash_exceeded(leash_result.reasons)
                logger.warning(f"[PlanExecute] Leash exceeded: {leash_result.reasons}")
                return GoalResult(
                    success=False,
                    completed_steps=[(s.description, r) for s, r in completed_steps],
                    failed_step=f"leash_exceeded: {', '.join(leash_result.reasons)}",
                )

            logger.info(
                f"[PlanExecute] Executing step {current_step.step_id}: {current_step.description[:50]}..."
            )

            # Execute step
            try:
                step_result = await self.step_executor.execute_step(
                    current_step, skill_list, {**context, "completed_steps": completed_steps}
                )
            except Exception as e:
                step_result = ExecutionResult(success=False, reason=f"Step execution error: {e}")

            state.actions_taken += 1

            # 3. Check if replanning needed
            if not step_result.success:
                logger.warning(
                    f"[PlanExecute] Step {current_step.step_id} failed: {step_result.reason}"
                )

                if replan_count >= self.max_replans:
                    logger.error("[PlanExecute] Max replans exceeded")
                    return GoalResult(
                        success=False,
                        completed_steps=[(s.description, r) for s, r in completed_steps],
                        failed_step=current_step.description,
                    )

                # Attempt replan
                try:
                    should_replan = await self.planning.should_replan(plan, step_result, context)
                    if should_replan:
                        logger.info("[PlanExecute] Replanning...")
                        plan = await self.planning.replan(
                            original_goal=goal,
                            completed_steps=completed_steps,
                            failed_step=current_step,
                            available_skills=skill_list,
                            context=context,
                        )
                        self.audit.log_replan(
                            f"Step {current_step.step_id} failed: {step_result.reason}",
                            [s.description for s in plan.steps],
                        )
                        replan_count += 1
                        continue
                    else:
                        # No replan - fail
                        return GoalResult(
                            success=False,
                            completed_steps=[(s.description, r) for s, r in completed_steps],
                            failed_step=current_step.description,
                        )
                except Exception as e:
                    logger.error(f"[PlanExecute] Replan failed: {e}")
                    return GoalResult(
                        success=False,
                        completed_steps=[(s.description, r) for s, r in completed_steps],
                        failed_step=current_step.description,
                    )

            # Step succeeded - record and advance
            completed_steps.append((current_step, step_result))
            plan.advance()
            logger.debug(f"[PlanExecute] Step {current_step.step_id} completed")

        # All steps complete
        logger.info(f"[PlanExecute] Goal achieved in {len(completed_steps)} steps")
        return GoalResult(
            success=True, completed_steps=[(s.description, r) for s, r in completed_steps]
        )

    @staticmethod
    def estimate_complexity(goal: str) -> int:
        """Estimate goal complexity for execution mode selection.

        Heuristic based on goal text analysis.
        Returns estimated number of steps.

        Args:
            goal: Goal description

        Returns:
            Estimated step count
        """
        # Simple heuristic: count conjunctions and action verbs
        complexity_indicators = [
            "and then",
            "after that",
            "first",
            "next",
            "finally",
            "followed by",
            "once",
            "when",
            "before",
            "after",
            "set up",
            "configure",
            "deploy",
            "migrate",
            "refactor",
        ]

        goal_lower = goal.lower()
        indicator_count = sum(1 for ind in complexity_indicators if ind in goal_lower)

        # Base complexity of 1, plus indicators
        return 1 + indicator_count

    def should_use_planning(self, goal: str) -> bool:
        """Determine if goal should use Plan-and-Execute vs ReAct.

        Args:
            goal: Goal description

        Returns:
            True if Plan-and-Execute recommended
        """
        return self.estimate_complexity(goal) > self.COMPLEXITY_THRESHOLD

    def get_audit_trail(self) -> list[dict]:
        """Get execution audit trail."""
        return self.audit.to_json()
