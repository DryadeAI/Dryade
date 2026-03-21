"""ReAct (Reasoning and Acting) executor for autonomous skill execution.

Implements the core execution loop:
1. THOUGHT: LLM reasons about next action
2. ACTION: Execute selected skill/tool
3. OBSERVATION: Record and analyze result
4. REPEAT until goal achieved or leash exceeded

Based on:
- LangChain ReAct pattern
- MoltBot's LLM-as-orchestrator approach
- Dryade's existing skill infrastructure
"""

import logging
import time
from typing import TYPE_CHECKING, Any, Protocol

from core.autonomous.audit import AuditLogger
from core.autonomous.leash import LeashConfig
from core.autonomous.models import (
    ActionType,
    ExecutionResult,
    ExecutionState,
    Observation,
    Thought,
)
from core.autonomous.skill_creator import SkillCreationResult, SkillCreator, get_skill_creator

if TYPE_CHECKING:
    from core.skills import Skill, SkillSnapshot

logger = logging.getLogger(__name__)

class CapabilityNegotiatorProtocol(Protocol):
    """Protocol for capability negotiation.

    Implementations provide dynamic tool binding based on agent requests.
    Used when executor needs capabilities not in current skill set.
    """

    async def negotiate(
        self,
        agent_request: str,
        user_prefs: dict[str, Any] | None = None,
    ) -> Any:  # Returns NegotiationResult
        """Negotiate capabilities for agent request.

        Args:
            agent_request: Natural language description of needed capability
            user_prefs: User preferences (auto_accept, accept_all_session)

        Returns:
            NegotiationResult with status and bound_tools
        """
        ...

class SkillCreatorProtocol(Protocol):
    """Protocol for autonomous skill creation.

    Implementations handle generating new skills when existing
    capabilities cannot fulfill requirements.
    """

    async def create_skill(
        self,
        goal: str,
        skill_name: str | None = None,
        description: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> SkillCreationResult:
        """Create a new skill to accomplish goal.

        Args:
            goal: What the skill should accomplish
            skill_name: Optional name for the skill
            description: Optional description
            context: Additional context for skill generation

        Returns:
            SkillCreationResult with outcome
        """
        ...

class ThinkingProvider(Protocol):
    """Protocol for LLM reasoning provider.

    Implementations provide the 'thinking' capability for ReAct loop.
    This abstraction allows different LLM backends (Claude, GPT, local).
    """

    async def think(
        self,
        goal: str,
        observations: list[Observation],
        available_skills: list["Skill"],
        context: dict[str, Any],
    ) -> Thought:
        """Generate next thought/action decision.

        Args:
            goal: What we're trying to achieve
            observations: Results from previous actions
            available_skills: Skills that can be invoked
            context: Additional execution context

        Returns:
            Thought with reasoning, skill selection, and confidence
        """
        ...

class SkillExecutor(Protocol):
    """Protocol for skill execution.

    Implementations handle actual skill invocation.
    """

    async def execute_skill(
        self,
        skill: "Skill",
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a skill with given inputs.

        Args:
            skill: Skill to execute
            inputs: Input parameters for skill
            context: Execution context

        Returns:
            Skill execution result
        """
        ...

class HumanInputHandler(Protocol):
    """Protocol for human-in-the-loop escalation.

    Implementations handle requesting human input when needed.
    """

    async def request_input(
        self,
        thought: Thought,
        context: dict[str, Any],
        reason: str,
    ) -> ExecutionResult:
        """Request human input for uncertain decisions.

        Args:
            thought: Current thought requiring review
            context: Execution context
            reason: Why human input needed

        Returns:
            ExecutionResult with human guidance
        """
        ...

class ReActExecutor:
    """Execute skills using ReAct (Reasoning and Acting) loop.

    The ReAct pattern alternates between:
    - Reasoning (Thought): LLM decides what to do next
    - Acting (Action): Execute the selected skill
    - Observing (Observation): Record and analyze the result

    Loop continues until:
    - Goal is achieved (thought.is_final = True)
    - Leash constraints exceeded
    - Human escalation required and handled
    - Unrecoverable error

    Example:
        executor = ReActExecutor(
            thinking_provider=my_llm,
            skill_executor=my_executor,
            leash=LeashConfig(max_actions=10),
        )
        result = await executor.execute(
            goal="Deploy my code to staging",
            skills=skill_snapshot,
            context={"repo": "my-app"}
        )
    """

    def __init__(
        self,
        thinking_provider: ThinkingProvider,
        skill_executor: SkillExecutor,
        leash: LeashConfig | None = None,
        human_handler: HumanInputHandler | None = None,
        capability_negotiator: CapabilityNegotiatorProtocol | None = None,
        skill_creator: "SkillCreator | SkillCreatorProtocol | None" = None,
        session_id: str | None = None,
        initiator_id: str = "user",
    ):
        """Initialize ReAct executor.

        Args:
            thinking_provider: LLM for reasoning
            skill_executor: Handler for skill execution
            leash: Autonomy constraints (defaults to standard)
            human_handler: Handler for escalation (required for human-in-loop)
            capability_negotiator: Handler for mid-execution capability requests
            skill_creator: Handler for autonomous skill creation (SkillCreator or Protocol)
            session_id: Unique session ID for audit
            initiator_id: Who initiated execution
        """
        self.thinking = thinking_provider
        self.skill_executor = skill_executor
        self.leash = leash or LeashConfig()
        self.human_handler = human_handler
        self.capability_negotiator = capability_negotiator
        self.skill_creator: SkillCreator | SkillCreatorProtocol | None = skill_creator
        self.audit = AuditLogger(session_id=session_id, initiator_id=initiator_id)

    async def _handle_negotiate_capability(
        self,
        thought: Thought,
        context: dict[str, Any],
        _observations: list[Observation],
        _state: ExecutionState,
    ) -> tuple[bool, Observation | None]:
        """Handle negotiate_capability action.

        Calls the capability negotiator to bind new tools/capabilities
        mid-execution when the agent needs functionality not in current skills.

        Args:
            thought: Current thought with capability_request
            context: Execution context
            _observations: List of observations (reserved for future use)
            _state: Execution state (reserved for future use)

        Returns:
            (continue_loop, observation) - continue_loop is True if should continue
        """
        request_text = thought.capability_request or thought.reasoning

        if not self.capability_negotiator:
            # No negotiator configured - add observation and continue
            logger.warning("[ReAct] negotiate_capability requested but no negotiator configured")
            observation = Observation(
                skill_name="negotiate_capability",
                inputs={"request": request_text},
                result=None,
                success=False,
                error="No capability negotiator configured",
            )
            return True, observation

        # Call negotiator
        try:
            result = await self.capability_negotiator.negotiate(
                request_text,
                user_prefs=context.get("user_prefs", {}),
            )

            # Log to audit
            self.audit.log_action(
                skill_name="negotiate_capability",
                inputs={"request": request_text},
                result={
                    "status": getattr(result, "status", "unknown"),
                    "bound_tools": getattr(result, "bound_tools", []),
                },
                success=True,
            )

            # Store bound tools in context for later use
            bound_tools = getattr(result, "bound_tools", [])
            if bound_tools:
                context.setdefault("bound_capabilities", []).extend(bound_tools)
                logger.info(f"[ReAct] Bound capabilities: {bound_tools}")

            observation = Observation(
                skill_name="negotiate_capability",
                inputs={"request": request_text},
                result={
                    "status": getattr(result, "status", "unknown"),
                    "bound_tools": bound_tools,
                    "offer_generate": getattr(result, "offer_generate", False),
                },
                success=True,
            )

            return True, observation

        except Exception as e:
            logger.error(f"[ReAct] Capability negotiation failed: {e}")
            observation = Observation(
                skill_name="negotiate_capability",
                inputs={"request": request_text},
                result=None,
                success=False,
                error=str(e),
            )
            return True, observation

    async def _handle_create_skill(
        self,
        thought: Thought,
        context: dict[str, Any],
        skill_list: list["Skill"],
        _observations: list[Observation],
        state: ExecutionState,
    ) -> tuple[bool, Observation | None]:
        """Handle create_skill action.

        Creates a new skill via SkillCreator, registers it,
        and makes it available for subsequent actions.

        Args:
            thought: Current thought with skill_creation_goal
            context: Execution context
            skill_list: Current skill list (will be updated with new skill)
            _observations: Observation history (reserved for future use)
            state: Execution state

        Returns:
            (continue_loop, observation) - continue_loop is True if should continue
        """
        goal = thought.skill_creation_goal or thought.reasoning
        skill_name = thought.inputs.get("skill_name") if thought.inputs else None

        # Check if skill creator available
        if not self.skill_creator:
            # Try to get default creator with our leash config
            try:
                self.skill_creator = get_skill_creator(self.leash)
            except Exception as e:
                observation = Observation(
                    skill_name="create_skill",
                    inputs={"goal": goal},
                    result=None,
                    success=False,
                    error=f"Skill creator unavailable: {e}",
                )
                return True, observation

        # Attempt skill creation
        logger.info(f"[ReAct] Creating skill for: {goal[:50]}...")
        start_time = time.time()

        try:
            result = await self.skill_creator.create_skill(
                goal=goal,
                skill_name=skill_name,
                context=context,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            if result.success:
                # Add new skill to available skills
                if result.skill:
                    skill_list.append(result.skill)
                    logger.info(f"[ReAct] Created and registered skill: {result.skill_name}")

                # Log to audit
                self.audit.log_action(
                    skill_name="create_skill",
                    inputs={"goal": goal, "skill_name": skill_name},
                    result={
                        "created": result.skill_name,
                        "signed": result.signed,
                        "staged_path": str(result.staged_path) if result.staged_path else None,
                    },
                    success=True,
                    duration_ms=duration_ms,
                )

                observation = Observation(
                    skill_name="create_skill",
                    inputs={"goal": goal},
                    result={
                        "status": "created",
                        "skill_name": result.skill_name,
                        "signed": result.signed,
                        "message": f"Skill '{result.skill_name}' is now available",
                    },
                    success=True,
                    duration_ms=duration_ms,
                )
            else:
                # Creation failed
                self.audit.log_action(
                    skill_name="create_skill",
                    inputs={"goal": goal, "skill_name": skill_name},
                    result={"error": result.error, "issues": result.validation_issues},
                    success=False,
                    duration_ms=duration_ms,
                )

                observation = Observation(
                    skill_name="create_skill",
                    inputs={"goal": goal},
                    result=None,
                    success=False,
                    error=result.error,
                    duration_ms=duration_ms,
                )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[ReAct] Skill creation failed: {e}")

            observation = Observation(
                skill_name="create_skill",
                inputs={"goal": goal},
                result=None,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

        state.actions_taken += 1
        return True, observation

    async def execute(
        self,
        goal: str,
        skills: "SkillSnapshot | list[Skill]",
        context: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute ReAct loop to achieve goal.

        Args:
            goal: What to achieve
            skills: Available skills
            context: Additional context

        Returns:
            ExecutionResult with outcome
        """
        context = context or {}
        observations: list[Observation] = []
        state = ExecutionState()

        # Convert skills to list if snapshot
        skill_list = list(skills) if hasattr(skills, "__iter__") else list(skills.skills)

        logger.info(f"[ReAct] Starting execution for goal: {goal[:100]}...")

        while True:
            # 1. Check leash constraints FIRST
            leash_result = self.leash.exceeded(state)
            if leash_result.exceeded:
                self.audit.log_leash_exceeded(leash_result.reasons)
                logger.warning(f"[ReAct] Leash exceeded: {leash_result.reasons}")
                return ExecutionResult(
                    success=False,
                    reason=f"Autonomy leash exceeded: {', '.join(leash_result.reasons)}",
                    partial_results=observations,
                    state=state,
                )

            # 2. THOUGHT: LLM decides next action
            try:
                thought = await self.thinking.think(goal, observations, skill_list, context)
                self.audit.log_thought(thought)
            except Exception as e:
                logger.error(f"[ReAct] Thinking failed: {e}")
                return ExecutionResult(
                    success=False,
                    reason=f"Thinking failed: {e}",
                    partial_results=observations,
                    state=state,
                )

            # 3. Check if goal achieved
            if thought.is_final:
                logger.info(
                    f"[ReAct] Goal achieved: {thought.answer[:100] if thought.answer else 'done'}..."
                )
                return ExecutionResult(
                    success=True,
                    output=thought.answer,
                    partial_results=observations,
                    state=state,
                )

            # 4. Check confidence - escalate if needed
            confidence_check = self.leash.check_confidence(thought.confidence)
            if confidence_check.requires_approval:
                if self.human_handler:
                    logger.info(
                        f"[ReAct] Low confidence ({thought.confidence:.2%}), requesting human input"
                    )
                    self.audit.log_escalation(
                        reason=confidence_check.approval_reason or "Low confidence",
                        context={"thought": thought.reasoning, "skill": thought.skill_name},
                    )
                    return await self.human_handler.request_input(
                        thought,
                        context,
                        reason=confidence_check.approval_reason or "Low confidence",
                    )
                else:
                    # No human handler - fail safe
                    logger.warning("[ReAct] Low confidence but no human handler")
                    return ExecutionResult(
                        success=False,
                        reason=f"Low confidence ({thought.confidence:.2%}) and no human handler",
                        partial_results=observations,
                        state=state,
                    )

            # 4.5. Route based on action_type
            if thought.action_type == ActionType.NEGOTIATE_CAPABILITY:
                continue_loop, observation = await self._handle_negotiate_capability(
                    thought, context, observations, state
                )
                if observation:
                    observations.append(observation)
                state.actions_taken += 1
                if continue_loop:
                    continue
                # If continue_loop is False, fall through to return

            elif thought.action_type == ActionType.CREATE_SKILL:
                continue_loop, observation = await self._handle_create_skill(
                    thought, context, skill_list, observations, state
                )
                if observation:
                    observations.append(observation)
                # Note: state.actions_taken already incremented in _handle_create_skill
                if continue_loop:
                    continue

            elif thought.action_type == ActionType.ASK_HUMAN:
                # Route to human handler
                if self.human_handler:
                    logger.info("[ReAct] Agent requested human input")
                    self.audit.log_escalation(
                        reason="Agent requested human input",
                        context={"thought": thought.reasoning},
                    )
                    return await self.human_handler.request_input(
                        thought,
                        context,
                        reason="Agent requested human input",
                    )
                else:
                    logger.warning("[ReAct] ASK_HUMAN requested but no human handler")
                    return ExecutionResult(
                        success=False,
                        reason="Agent requested human input but no handler configured",
                        partial_results=observations,
                        state=state,
                    )

            # 5. Validate skill selection (for EXECUTE_SKILL or no action_type)
            if not thought.skill_name:
                logger.warning("[ReAct] No skill selected in thought")
                return ExecutionResult(
                    success=False,
                    reason="No skill selected for action",
                    partial_results=observations,
                    state=state,
                )

            # Find skill
            skill = next((s for s in skill_list if s.name == thought.skill_name), None)
            if not skill:
                logger.warning(f"[ReAct] Skill not found: {thought.skill_name}")
                # Add as observation so LLM can adjust
                observations.append(
                    Observation(
                        skill_name=thought.skill_name,
                        inputs=thought.inputs,
                        result=None,
                        success=False,
                        error=f"Skill '{thought.skill_name}' not found",
                    )
                )
                state.actions_taken += 1
                continue

            # 6. Check action safety
            action_text = f"{thought.skill_name} {thought.inputs}"
            action_check = self.leash.check_action(action_text)
            if action_check.requires_approval:
                if self.human_handler:
                    logger.info("[ReAct] Dangerous action detected, requesting approval")
                    self.audit.log_escalation(
                        reason=action_check.approval_reason or "Dangerous action",
                        context={"skill": thought.skill_name, "inputs": thought.inputs},
                    )
                    return await self.human_handler.request_input(
                        thought,
                        context,
                        reason=action_check.approval_reason or "Dangerous action",
                    )
                else:
                    logger.warning("[ReAct] Dangerous action but no human handler")
                    return ExecutionResult(
                        success=False,
                        reason=f"Dangerous action requires approval: {action_check.approval_reason}",
                        partial_results=observations,
                        state=state,
                    )

            # 7. ACTION: Execute skill
            start_time = time.time()
            try:
                result = await self.skill_executor.execute_skill(skill, thought.inputs, context)
                duration_ms = int((time.time() - start_time) * 1000)

                observation = Observation(
                    skill_name=skill.name,
                    inputs=thought.inputs,
                    result=result,
                    success=True,
                    duration_ms=duration_ms,
                )
                observations.append(observation)

                self.audit.log_action(
                    skill_name=skill.name,
                    inputs=thought.inputs,
                    result=result,
                    success=True,
                    duration_ms=duration_ms,
                )

                logger.debug(f"[ReAct] Skill '{skill.name}' executed in {duration_ms}ms")

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                error_msg = str(e)

                observation = Observation(
                    skill_name=skill.name,
                    inputs=thought.inputs,
                    result=None,
                    success=False,
                    error=error_msg,
                    duration_ms=duration_ms,
                )
                observations.append(observation)

                self.audit.log_action(
                    skill_name=skill.name,
                    inputs=thought.inputs,
                    result=None,
                    success=False,
                    error=error_msg,
                    duration_ms=duration_ms,
                )

                logger.warning(f"[ReAct] Skill '{skill.name}' failed: {error_msg}")

            # 8. Update state
            state.actions_taken += 1
            state.tool_calls += 1

    def get_audit_trail(self) -> list[dict]:
        """Get execution audit trail.

        Returns:
            List of audit entries as JSON-serializable dicts
        """
        return self.audit.to_json()

class DefaultSkillExecutor:
    """Default skill executor that runs skill instructions.

    This is a basic implementation that formats skill instructions
    for LLM execution. More sophisticated implementations can
    run scripts, call APIs, or use tool frameworks.
    """

    async def execute_skill(
        self,
        skill: "Skill",
        inputs: dict[str, Any],
        _context: dict[str, Any],
    ) -> str:
        """Execute skill by returning formatted instructions.

        In a full implementation, this would:
        1. Run skill scripts if present
        2. Call skill-specific tools
        3. Execute skill workflows

        For now, returns instructions for manual execution.

        Args:
            skill: Skill to execute
            inputs: Input parameters for skill
            _context: Execution context (unused in basic implementation)

        Returns:
            Formatted skill instructions
        """
        # Basic implementation - return formatted instructions
        instruction_parts = [
            f"# Executing skill: {skill.name}",
            f"Description: {skill.description}",
            "",
            "## Instructions:",
            skill.instructions,
            "",
            "## Provided inputs:",
        ]

        for key, value in inputs.items():
            instruction_parts.append(f"- {key}: {value}")

        return "\n".join(instruction_parts)
