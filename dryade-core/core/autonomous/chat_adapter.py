"""Chat adapter for ReActExecutor - bridges autonomous execution with chat streaming.

This module provides the implementation classes needed to wire ReActExecutor
into the chat route, enabling Moltbot-style mission execution:

1. User describes a mission
2. Skills are retrieved and matched via semantic routing
3. ReActExecutor runs the THOUGHT -> ACTION -> OBSERVATION loop
4. If no skill matches, LLM decides next step (or creates a skill)
5. Human escalation when confidence is low or dangerous actions detected

Usage:
    async for event in stream_react_execution(
        goal="Deploy my app to staging",
        conversation_id="conv_123",
        user_id="user_456",
        leash_preset="standard",
    ):
        yield event
"""

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from core.autonomous.executor import ReActExecutor
from core.autonomous.leash import (
    LEASH_CONSERVATIVE,
    LEASH_PERMISSIVE,
    LEASH_STANDARD,
    LeashConfig,
)
from core.autonomous.models import (
    ActionType,
    ExecutionResult,
    Observation,
    Thought,
)
from core.autonomous.router import get_skill_router
from core.extensions.events import (
    ChatEvent,
    emit_clarify,
    emit_complete,
    emit_error,
    emit_thinking,
    emit_tool_result,
    emit_tool_start,
)
from core.skills.registry import get_skill_registry

if TYPE_CHECKING:
    from plugins.sandbox.executor import IsolationLevel

    from core.clarification import ClarificationResponse
    from core.skills.models import Skill

logger = logging.getLogger(__name__)

# Storage for autonomous execution clarifications (separate from planner mode)
# These are keyed by conversation_id to track pending user responses
_execution_clarify_events: dict[str, asyncio.Event] = {}
_execution_clarify_responses: dict[str, "ClarificationResponse"] = {}
_execution_clarify_lock = threading.Lock()

def submit_autonomous_clarification(
    conversation_id: str, response: "ClarificationResponse"
) -> bool:
    """Submit user response to autonomous execution clarification.

    Called by /api/chat/clarify when conversation is in autonomous mode.

    Args:
        conversation_id: Conversation ID with pending clarification
        response: User's response to the clarification prompt

    Returns:
        True if pending clarification was found, False otherwise
    """
    with _execution_clarify_lock:
        if conversation_id not in _execution_clarify_events:
            return False

        _execution_clarify_responses[conversation_id] = response
        _execution_clarify_events[conversation_id].set()
        return True

def has_pending_autonomous_clarification(conversation_id: str) -> bool:
    """Check if there's a pending autonomous clarification for a conversation.

    Args:
        conversation_id: Conversation ID to check

    Returns:
        True if autonomous clarification is pending, False otherwise
    """
    with _execution_clarify_lock:
        return conversation_id in _execution_clarify_events

# Leash preset mapping
LEASH_PRESETS: dict[str, LeashConfig] = {
    "conservative": LEASH_CONSERVATIVE,
    "standard": LEASH_STANDARD,
    "permissive": LEASH_PERMISSIVE,
}

# System prompt for ReAct reasoning
REACT_SYSTEM_PROMPT = """You are an autonomous agent executing skills to accomplish goals.

For each step, analyze the goal and observations, then decide:
1. Which skill to execute next (or if goal is achieved)
2. What inputs to provide to the skill
3. Your confidence level (0.0-1.0)

## Available Skills
{skills_xml}

## Observations So Far
{observations_xml}

## Output Format
Respond with JSON:
{{
    "reasoning": "Your step-by-step thinking about what to do next",
    "action_type": "execute_skill" | "ask_human" | "create_skill",
    "skill_name": "name of skill to execute (if action_type=execute_skill)",
    "inputs": {{"param1": "value1"}},
    "confidence": 0.85,
    "is_final": false,
    "answer": "final answer if is_final=true"
}}

If you cannot find an appropriate skill, set action_type="ask_human" to request guidance.
If confidence < 0.7, consider asking for human confirmation.
"""

def _format_skills_xml(skills: list["Skill"]) -> str:
    """Format skills as XML for LLM context."""
    if not skills:
        return "<skills>No skills available</skills>"

    lines = ["<skills>"]
    for skill in skills:
        lines.append(f'  <skill name="{skill.name}">')
        lines.append(f"    <description>{skill.description}</description>")
        # Include input schema if available (from metadata.extra or direct attribute)
        inputs = getattr(skill.metadata, "inputs", None) if skill.metadata else None
        if not inputs and skill.metadata:
            inputs = (
                skill.metadata.extra.get("inputs") if hasattr(skill.metadata, "extra") else None
            )
        if inputs:
            lines.append("    <inputs>")
            for inp in inputs:
                # Handle both dict and object input formats
                if isinstance(inp, dict):
                    lines.append(
                        f'      <input name="{inp.get("name", "unknown")}" type="{inp.get("type", "string")}">{inp.get("description", "")}</input>'
                    )
                else:
                    lines.append(
                        f'      <input name="{getattr(inp, "name", "unknown")}" type="{getattr(inp, "type", "string")}">{getattr(inp, "description", "")}</input>'
                    )
            lines.append("    </inputs>")
        lines.append("  </skill>")
    lines.append("</skills>")
    return "\n".join(lines)

def _format_observations_xml(observations: list[Observation]) -> str:
    """Format observation history as XML."""
    if not observations:
        return "<observations>No actions taken yet</observations>"

    lines = ["<observations>"]
    for i, obs in enumerate(observations, 1):
        status = "success" if obs.success else "failed"
        lines.append(f'  <observation step="{i}" skill="{obs.skill_name}" status="{status}">')
        lines.append(f"    <inputs>{json.dumps(obs.inputs)}</inputs>")
        if obs.success:
            # Truncate long results
            result_str = str(obs.result)
            if len(result_str) > 500:
                result_str = result_str[:500] + "..."
            lines.append(f"    <result>{result_str}</result>")
        else:
            lines.append(f"    <error>{obs.error}</error>")
        lines.append("  </observation>")
    lines.append("</observations>")
    return "\n".join(lines)

class LLMThinkingProvider:
    """Implements ThinkingProvider protocol using configured LLM.

    Uses the LLM adapter to get properly configured LLM and formats
    ReAct prompts for reasoning about next actions.
    """

    def __init__(self):
        """Initialize the thinking provider."""
        self._llm = None

    def _get_llm(self):
        """Lazy-load LLM instance."""
        if self._llm is None:
            from core.providers.llm_adapter import get_configured_llm

            self._llm = get_configured_llm()
        return self._llm

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
        llm = self._get_llm()

        # Format system prompt with skills and observations
        skills_xml = _format_skills_xml(available_skills)
        observations_xml = _format_observations_xml(observations)

        system_prompt = REACT_SYSTEM_PROMPT.format(
            skills_xml=skills_xml,
            observations_xml=observations_xml,
        )

        # Build user message
        user_message = f"Goal: {goal}\n\nDecide the next action to take."

        # Add any context hints
        if context.get("hints"):
            user_message += f"\n\nHints: {context['hints']}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            # Call LLM
            if hasattr(llm, "acall"):
                response = await llm.acall(messages)
            else:
                # Fallback for sync-only LLMs
                import asyncio

                response = await asyncio.to_thread(llm.call, messages)

            # Handle structured response
            if isinstance(response, dict):
                response_text = response.get("content", str(response))
            else:
                response_text = str(response)

            # Parse JSON response
            thought_data = self._parse_thought_response(response_text)
            return thought_data

        except Exception as e:
            logger.error(f"[ThinkingProvider] LLM call failed: {e}")
            # Return low-confidence thought requesting human help
            return Thought(
                reasoning=f"LLM reasoning failed: {e}. Requesting human guidance.",
                action_type=ActionType.ASK_HUMAN,
                confidence=0.1,
                is_final=False,
            )

    def _parse_thought_response(self, response_text: str) -> Thought:
        """Parse LLM response into Thought model."""
        try:
            # Try to extract JSON from response
            # Handle case where LLM wraps JSON in markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                # Remove markdown code block
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
                text = text.strip()

            data = json.loads(text)

            # Map action_type string to enum
            action_type_str = data.get("action_type", "execute_skill")
            action_type_map = {
                "execute_skill": ActionType.EXECUTE_SKILL,
                "ask_human": ActionType.ASK_HUMAN,
                "create_skill": ActionType.CREATE_SKILL,
                "negotiate_capability": ActionType.NEGOTIATE_CAPABILITY,
            }
            action_type = action_type_map.get(action_type_str, ActionType.EXECUTE_SKILL)

            return Thought(
                reasoning=data.get("reasoning", "No reasoning provided"),
                action_type=action_type,
                skill_name=data.get("skill_name"),
                inputs=data.get("inputs", {}),
                confidence=float(data.get("confidence", 0.5)),
                is_final=data.get("is_final", False),
                answer=data.get("answer"),
                capability_request=data.get("capability_request"),
                skill_creation_goal=data.get("skill_creation_goal"),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"[ThinkingProvider] Failed to parse JSON response: {e}")
            # Try to extract reasoning from text
            return Thought(
                reasoning=f"Could not parse structured response. Raw: {response_text[:200]}...",
                action_type=ActionType.ASK_HUMAN,
                confidence=0.3,
                is_final=False,
            )

class RuntimeSkillExecutor:
    """Implements SkillExecutor protocol - actually executes skills.

    Routes skill execution to:
    1. Callable execution for MCP tools (run.type == "callable")
    2. Sandbox execution for skills with run: blocks (string or dict)
    3. RuntimeError for skills without executable run: blocks

    Skills MUST have executable run: blocks. No LLM interpretation fallback.
    """

    def __init__(self):
        """Initialize the skill executor."""
        self._llm = None

    def _get_llm(self):
        """Lazy-load LLM instance."""
        if self._llm is None:
            from core.providers.llm_adapter import get_configured_llm

            self._llm = get_configured_llm()
        return self._llm

    def _get_skill_isolation(self, skill: "Skill") -> "IsolationLevel":
        """Determine sandbox isolation level for skill execution.

        Priority:
        1. Skill-declared isolation in metadata.extra['isolation']
        2. TOOL_RISK_LEVELS mapping by skill name
        3. Default: PROCESS isolation for safety

        Args:
            skill: Skill to get isolation level for

        Returns:
            IsolationLevel enum value

        Raises:
            RuntimeError: If sandbox plugin is not available
        """
        try:
            from plugins.sandbox.executor import TOOL_RISK_LEVELS, IsolationLevel
        except ImportError:
            raise RuntimeError(
                "Sandbox plugin is required for skill isolation but is not installed. "
                "Install the sandbox plugin or use callable-type skills only."
            )

        # Check if skill declares isolation level
        if skill.metadata and skill.metadata.extra:
            declared = skill.metadata.extra.get("isolation")
            if declared:
                try:
                    return IsolationLevel(declared)
                except ValueError:
                    logger.warning(
                        f"[SkillExecutor] Invalid isolation level '{declared}' for {skill.name}, using PROCESS"
                    )

        # Check risk level mapping
        if skill.name in TOOL_RISK_LEVELS:
            return TOOL_RISK_LEVELS[skill.name]

        # Default: PROCESS isolation for safety
        return IsolationLevel.PROCESS

    async def execute_skill(
        self,
        skill: "Skill",
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a skill with given inputs.

        Routes to:
        1. Callable execution for MCP tools (run.type == "callable")
        2. Sandbox execution for skills with run: blocks (string or dict)
        3. RuntimeError for skills without executable run: blocks

        Args:
            skill: Skill to execute
            inputs: Input parameters for skill
            context: Execution context

        Returns:
            Skill execution result

        Raises:
            RuntimeError: If skill has no executable run: block
        """
        # Extract run: block from metadata
        run_block = None
        if skill.metadata and skill.metadata.extra:
            run_block = skill.metadata.extra.get("run")

        # Case 1: No run block - error (no LLM fallback)
        if not run_block:
            logger.error(f"[SkillExecutor] Skill '{skill.name}' has no run: block")
            raise RuntimeError(
                f"Skill '{skill.name}' has no executable run: block. "
                f"Skills must define execution method (sandbox command or callable)."
            )

        # Case 2: Callable (MCP tool)
        if isinstance(run_block, dict) and run_block.get("type") == "callable":
            callable_func = run_block.get("callable")
            if not callable_func:
                raise RuntimeError(
                    f"Skill '{skill.name}' has callable type but no callable function"
                )
            logger.info(f"[SkillExecutor] Executing '{skill.name}' via callable (MCP tool)")
            return await self._execute_callable(skill, inputs, context, callable_func)

        # Case 3: Sandbox execution (string command or dict with code)
        logger.info(f"[SkillExecutor] Executing '{skill.name}' via sandbox")
        return await self._execute_sandboxed(skill, inputs, context, run_block)

    async def _execute_sandboxed(
        self,
        skill: "Skill",
        inputs: dict[str, Any],
        context: dict[str, Any],
        run_block: str | dict[str, Any],
    ) -> Any:
        """Execute skill via ToolSandbox.

        Args:
            skill: Skill to execute
            inputs: Input parameters for skill
            context: Execution context
            run_block: The run: block content from skill metadata

        Returns:
            Execution result from sandbox
        """
        try:
            from plugins.sandbox.executor import SandboxConfig, get_sandbox
        except ImportError:
            raise RuntimeError(
                "Sandbox plugin is required for sandboxed skill execution but is not installed."
            )

        sandbox = get_sandbox()
        isolation = self._get_skill_isolation(skill)

        # Get network and timeout settings from skill metadata
        network_enabled = False
        timeout_seconds = 60

        if skill.metadata and skill.metadata.extra:
            network_enabled = skill.metadata.extra.get("network", False)
            timeout_seconds = skill.metadata.extra.get("timeout", 60)

        config = SandboxConfig(
            isolation=isolation,
            timeout_seconds=timeout_seconds,
            network_enabled=network_enabled,
        )

        # Prepare args for sandbox execution
        # run_block can be a string (shell command) or dict with code/type
        if isinstance(run_block, str):
            args = {"command": run_block, "inputs": inputs}
        else:
            args = {**run_block, "inputs": inputs}

        logger.debug(
            f"[SkillExecutor] Sandbox config: isolation={isolation}, timeout={timeout_seconds}s, network={network_enabled}"
        )

        result = await sandbox.execute(
            tool_name=skill.name,
            args=args,
            config=config,
        )

        if result.success:
            logger.info(
                f"[SkillExecutor] Sandbox execution succeeded in {result.execution_time_ms:.0f}ms"
            )
            return result.output
        else:
            logger.error(f"[SkillExecutor] Sandbox execution failed: {result.error}")
            raise RuntimeError(f"Sandbox execution failed for '{skill.name}': {result.error}")

    async def _execute_callable(
        self,
        skill: "Skill",
        inputs: dict[str, Any],
        context: dict[str, Any],
        callable_func,
    ) -> Any:
        """Execute skill via direct callable invocation.

        Used for MCP tools bridged to skills.

        Args:
            skill: Skill being executed
            inputs: Input parameters for skill
            context: Execution context
            callable_func: The callable function to invoke

        Returns:
            Result from callable execution

        Raises:
            RuntimeError: If callable execution fails
        """
        import inspect

        logger.info(f"[SkillExecutor] Executing '{skill.name}' via callable")

        try:
            # Check if callable is async
            if inspect.iscoroutinefunction(callable_func):
                result = await callable_func(**inputs)
            else:
                # Run sync callable in thread pool
                result = await asyncio.to_thread(callable_func, **inputs)

            logger.info("[SkillExecutor] Callable execution succeeded")
            return result

        except Exception as e:
            logger.error(f"[SkillExecutor] Callable execution failed: {e}")
            raise RuntimeError(f"Callable execution failed for '{skill.name}': {e}") from e

class ClarifyHumanHandler:
    """Implements HumanInputHandler using clarify protocol.

    Routes human escalation requests through the clarify plugin,
    which emits clarify events and waits for user responses.
    """

    def __init__(self, conversation_id: str):
        """Initialize the human handler.

        Args:
            conversation_id: Conversation ID for clarification requests
        """
        self.conversation_id = conversation_id
        self._pending_event: ChatEvent | None = None

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
        from core.clarification import request_clarification

        # Build question from thought and reason
        question = f"{reason}\n\nAgent reasoning: {thought.reasoning}"

        if thought.skill_name:
            question += f"\n\nProposed action: Execute skill '{thought.skill_name}'"
            if thought.inputs:
                question += f" with inputs: {json.dumps(thought.inputs)}"

        # Build options based on context
        options = ["Proceed with action", "Skip this action", "Provide alternative"]

        try:
            # Request clarification - this will emit a clarify event
            # and wait for user response
            response = await request_clarification(
                conversation_id=self.conversation_id,
                question=question,
                options=options,
                timeout=300.0,  # 5 minutes
            )

            # Parse user response
            if response == "Proceed with action":
                # User approved - return success with original thought
                return ExecutionResult(
                    success=True,
                    output=f"User approved action: {thought.skill_name}",
                    reason="Human approval received",
                )
            elif response == "Skip this action":
                return ExecutionResult(
                    success=False,
                    reason="User requested to skip this action",
                )
            else:
                # User provided alternative guidance
                return ExecutionResult(
                    success=True,
                    output=f"User guidance: {response}",
                    reason="Human provided alternative instruction",
                )

        except TimeoutError:
            return ExecutionResult(
                success=False,
                reason="Human input request timed out (5 minutes)",
            )
        except Exception as e:
            logger.error(f"[HumanHandler] Clarification failed: {e}")
            return ExecutionResult(
                success=False,
                reason=f"Failed to get human input: {e}",
            )

    def get_pending_event(self) -> ChatEvent | None:
        """Get any pending clarify event to yield."""
        event = self._pending_event
        self._pending_event = None
        return event

async def stream_react_execution(
    goal: str,
    conversation_id: str,
    user_id: str | None,
    leash_preset: str = "standard",
) -> AsyncGenerator[ChatEvent, None]:
    """Main entry point - streams ReAct events as ChatEvents.

    This function orchestrates the entire autonomous execution flow:
    1. Load skills from registry
    2. Route to top-k relevant skills via IntelligentSkillRouter
    3. Create ReActExecutor with our adapters
    4. Run execution, emitting events for each step
    5. Handle human escalation via clarify protocol

    Args:
        goal: The mission/goal to accomplish
        conversation_id: Conversation ID for tracking and clarification
        user_id: User ID for personalization
        leash_preset: Autonomy constraint preset ("conservative", "standard", "permissive")

    Yields:
        ChatEvent for each step: thinking, tool_start, tool_result, clarify, complete/error
    """
    logger.info(f"[ReAct] Starting autonomous execution for goal: {goal[:100]}...")
    logger.info(f"[ReAct] Conversation: {conversation_id}, User: {user_id}, Leash: {leash_preset}")

    # Get leash configuration
    leash = LEASH_PRESETS.get(leash_preset, LEASH_STANDARD)
    logger.info(
        f"[ReAct] Leash config: max_actions={leash.max_actions}, confidence_threshold={leash.confidence_threshold}"
    )

    # Load skills from registry
    try:
        registry = get_skill_registry()
        all_skills = registry.get_eligible_skills()
        logger.info(f"[ReAct] Loaded {len(all_skills)} eligible skills from registry")
    except Exception as e:
        logger.error(f"[ReAct] Failed to load skills: {e}")
        yield emit_error(f"Failed to load skills: {e}", "SKILL_LOAD_ERROR")
        return

    # Route to relevant skills using semantic similarity
    try:
        router = get_skill_router()
        router.index_skills(all_skills)

        # Get top-10 relevant skills
        routed_skills = router.route(goal, all_skills, top_k=10, threshold=0.2)
        relevant_skills = [skill for skill, _score in routed_skills]

        if relevant_skills:
            logger.info(f"[ReAct] Routed to {len(relevant_skills)} relevant skills")
            for skill, score in routed_skills[:5]:
                logger.debug(f"  - {skill.name}: {score:.3f}")
        else:
            # Fall back to all skills if routing finds nothing
            logger.warning("[ReAct] No skills matched routing, using all skills")
            relevant_skills = all_skills

    except Exception as e:
        logger.warning(f"[ReAct] Skill routing failed, using all skills: {e}")
        relevant_skills = all_skills

    # Emit initial thinking event
    yield emit_thinking(
        f"Analyzing goal and selecting from {len(relevant_skills)} relevant skills...",
        agent="autonomous",
    )

    # Create adapters
    thinking_provider = LLMThinkingProvider()
    skill_executor = RuntimeSkillExecutor()
    human_handler = ClarifyHumanHandler(conversation_id)

    # Create ReActExecutor
    _executor = ReActExecutor(
        thinking_provider=thinking_provider,
        skill_executor=skill_executor,
        leash=leash,
        human_handler=human_handler,
        session_id=conversation_id,
        initiator_id=user_id or "anonymous",
    )

    # Execute with event streaming
    # We need to run the executor step-by-step to yield events
    context: dict[str, Any] = {
        "conversation_id": conversation_id,
        "user_id": user_id,
    }
    observations: list[Observation] = []
    skill_list = list(relevant_skills)

    step = 0
    max_steps = leash.max_actions or 20

    while step < max_steps:
        step += 1
        logger.info(f"[ReAct] === Step {step}/{max_steps} ===")

        # 1. Check leash constraints
        from core.autonomous.models import ExecutionState

        state = ExecutionState(actions_taken=step - 1, tool_calls=len(observations))
        leash_result = leash.exceeded(state)

        if leash_result.exceeded:
            logger.warning(f"[ReAct] Leash exceeded: {leash_result.reasons}")
            yield emit_error(
                f"Autonomy leash exceeded: {', '.join(leash_result.reasons)}", "LEASH_EXCEEDED"
            )
            return

        # 2. THOUGHT: LLM decides next action
        yield emit_thinking(f"Step {step}: Reasoning about next action...", agent="autonomous")

        try:
            thought = await thinking_provider.think(goal, observations, skill_list, context)
            logger.info(f"[ReAct] Thought: {thought.reasoning[:100]}...")
            logger.info(
                f"[ReAct] Action: {thought.action_type}, Skill: {thought.skill_name}, Confidence: {thought.confidence:.2%}"
            )

            # Emit detailed thinking
            yield emit_thinking(thought.reasoning, agent="autonomous")

        except Exception as e:
            logger.error(f"[ReAct] Thinking failed: {e}")
            yield emit_error(f"Reasoning failed: {e}", "THINKING_ERROR")
            return

        # 3. Check if goal achieved
        if thought.is_final:
            logger.info(
                f"[ReAct] Goal achieved: {thought.answer[:100] if thought.answer else 'done'}..."
            )
            yield emit_complete(
                thought.answer or "Goal accomplished",
                {"mode": "autonomous", "steps": step, "observations": len(observations)},
            )
            return

        # 4. Check confidence - escalate if needed (BLOCKING)
        confidence_check = leash.check_confidence(thought.confidence)
        if confidence_check.requires_approval:
            logger.info(
                f"[ReAct] Low confidence ({thought.confidence:.2%}), requesting human input"
            )

            # Create blocking event for this clarification
            blocking_event = asyncio.Event()
            with _execution_clarify_lock:
                _execution_clarify_events[conversation_id] = blocking_event

            try:
                # Emit clarify event
                yield emit_clarify(
                    question=f"Low confidence ({thought.confidence:.2%}): {thought.reasoning}",
                    options=["Proceed anyway", "Skip and continue", "Abort execution"],
                    context={"skill": thought.skill_name, "inputs": thought.inputs},
                )

                # Block and wait for user response (5 minute timeout)
                try:
                    await asyncio.wait_for(blocking_event.wait(), timeout=300.0)
                    with _execution_clarify_lock:
                        response = _execution_clarify_responses.pop(conversation_id, None)

                    if response:
                        user_choice = response.value.lower() if response.value else ""
                        selected_idx = response.selected_option

                        # Handle abort
                        if selected_idx == 2 or "abort" in user_choice:
                            logger.info("[ReAct] User aborted execution at low confidence check")
                            yield emit_error("Execution aborted by user", "USER_ABORT")
                            return

                        # Handle skip
                        if selected_idx == 1 or "skip" in user_choice:
                            logger.info("[ReAct] User skipped low confidence action")
                            observations.append(
                                Observation(
                                    skill_name=thought.skill_name or "unknown",
                                    inputs=thought.inputs,
                                    result=None,
                                    success=False,
                                    error="Skipped by user due to low confidence",
                                )
                            )
                            continue

                        # Proceed anyway (selected_idx == 0 or "proceed" in user_choice)
                        logger.info("[ReAct] User approved low confidence action")

                except TimeoutError:
                    logger.warning("[ReAct] Clarification timeout (5 min), aborting execution")
                    yield emit_error(
                        "Clarification request timed out after 5 minutes", "CLARIFY_TIMEOUT"
                    )
                    return

            finally:
                # Clean up pending state
                with _execution_clarify_lock:
                    _execution_clarify_events.pop(conversation_id, None)
                    _execution_clarify_responses.pop(conversation_id, None)

        # 5. Route based on action_type
        if thought.action_type == ActionType.ASK_HUMAN:
            logger.info("[ReAct] Agent requested human input")

            # Create blocking event for this clarification
            blocking_event = asyncio.Event()
            with _execution_clarify_lock:
                _execution_clarify_events[conversation_id] = blocking_event

            try:
                # Emit clarify event to frontend
                yield emit_clarify(
                    question=thought.reasoning,
                    options=["Provide guidance", "Skip this step", "Abort execution"],
                    context={"step": step, "skill": thought.skill_name},
                )

                # Block and wait for user response (5 minute timeout)
                try:
                    await asyncio.wait_for(blocking_event.wait(), timeout=300.0)
                    with _execution_clarify_lock:
                        response = _execution_clarify_responses.pop(conversation_id, None)

                    if response:
                        user_choice = response.value.lower() if response.value else ""
                        selected_idx = response.selected_option

                        # Handle abort
                        if selected_idx == 2 or "abort" in user_choice:
                            logger.info("[ReAct] User aborted at ASK_HUMAN")
                            yield emit_error("Execution aborted by user", "USER_ABORT")
                            return

                        # Handle skip
                        if selected_idx == 1 or "skip" in user_choice:
                            logger.info("[ReAct] User skipped ASK_HUMAN step")
                            observations.append(
                                Observation(
                                    skill_name="ask_human",
                                    inputs={"question": thought.reasoning},
                                    result=None,
                                    success=False,
                                    error="Skipped by user",
                                )
                            )
                            continue

                        # User provided guidance
                        observations.append(
                            Observation(
                                skill_name="ask_human",
                                inputs={"question": thought.reasoning},
                                result=f"User guidance: {response.value}",
                                success=True,
                            )
                        )
                    continue

                except TimeoutError:
                    logger.warning("[ReAct] ASK_HUMAN clarification timeout (5 min)")
                    yield emit_error(
                        "Clarification request timed out after 5 minutes", "CLARIFY_TIMEOUT"
                    )
                    return

            finally:
                # Clean up pending state
                with _execution_clarify_lock:
                    _execution_clarify_events.pop(conversation_id, None)
                    _execution_clarify_responses.pop(conversation_id, None)

        elif thought.action_type == ActionType.CREATE_SKILL:
            logger.info(f"[ReAct] Skill creation requested: {thought.skill_creation_goal}")
            yield emit_thinking(
                f"Skill creation requested: {thought.skill_creation_goal}", agent="autonomous"
            )
            # For now, emit as observation and continue
            observations.append(
                Observation(
                    skill_name="create_skill",
                    inputs={"goal": thought.skill_creation_goal},
                    result="Skill creation not yet implemented in streaming mode",
                    success=False,
                    error="Feature not available",
                )
            )
            continue

        # 6. Validate skill selection
        if not thought.skill_name:
            logger.warning("[ReAct] No skill selected in thought")
            observations.append(
                Observation(
                    skill_name="none",
                    inputs={},
                    result=None,
                    success=False,
                    error="No skill selected for action",
                )
            )
            continue

        # Find skill
        skill = next((s for s in skill_list if s.name == thought.skill_name), None)
        if not skill:
            logger.warning(f"[ReAct] Skill not found: {thought.skill_name}")
            observations.append(
                Observation(
                    skill_name=thought.skill_name,
                    inputs=thought.inputs,
                    result=None,
                    success=False,
                    error=f"Skill '{thought.skill_name}' not found",
                )
            )
            yield emit_thinking(
                f"Skill '{thought.skill_name}' not found, will reconsider...", agent="autonomous"
            )
            continue

        # 7. Check action safety (BLOCKING)
        action_text = f"{thought.skill_name} {thought.inputs}"
        action_check = leash.check_action(action_text)
        if action_check.requires_approval:
            logger.info(f"[ReAct] Dangerous action detected: {action_check.approval_reason}")

            # Create blocking event for this clarification
            blocking_event = asyncio.Event()
            with _execution_clarify_lock:
                _execution_clarify_events[conversation_id] = blocking_event

            try:
                # Emit clarify event
                yield emit_clarify(
                    question=f"Dangerous action detected: {action_check.approval_reason}",
                    options=["Approve and proceed", "Skip this action", "Abort execution"],
                    context={"skill": thought.skill_name, "inputs": thought.inputs},
                )

                # Block and wait for user response (5 minute timeout)
                try:
                    await asyncio.wait_for(blocking_event.wait(), timeout=300.0)
                    with _execution_clarify_lock:
                        response = _execution_clarify_responses.pop(conversation_id, None)

                    if response:
                        user_choice = response.value.lower() if response.value else ""
                        selected_idx = response.selected_option

                        # Handle abort
                        if selected_idx == 2 or "abort" in user_choice:
                            logger.info("[ReAct] User aborted execution at dangerous action check")
                            yield emit_error("Execution aborted by user", "USER_ABORT")
                            return

                        # Handle skip
                        if selected_idx == 1 or "skip" in user_choice:
                            logger.info("[ReAct] User skipped dangerous action")
                            observations.append(
                                Observation(
                                    skill_name=skill.name,
                                    inputs=thought.inputs,
                                    result=None,
                                    success=False,
                                    error="Skipped by user due to dangerous action",
                                )
                            )
                            continue

                        # Approve and proceed (selected_idx == 0 or "approve" in user_choice)
                        logger.info("[ReAct] User approved dangerous action")

                except TimeoutError:
                    logger.warning("[ReAct] Clarification timeout (5 min), aborting execution")
                    yield emit_error(
                        "Clarification request timed out after 5 minutes", "CLARIFY_TIMEOUT"
                    )
                    return

            finally:
                # Clean up pending state
                with _execution_clarify_lock:
                    _execution_clarify_events.pop(conversation_id, None)
                    _execution_clarify_responses.pop(conversation_id, None)

        # 8. ACTION: Execute skill
        yield emit_tool_start(skill.name, thought.inputs)

        start_time = time.time()
        try:
            result = await skill_executor.execute_skill(skill, thought.inputs, context)
            duration_ms = (time.time() - start_time) * 1000

            observation = Observation(
                skill_name=skill.name,
                inputs=thought.inputs,
                result=result,
                success=True,
                duration_ms=int(duration_ms),
            )
            observations.append(observation)

            yield emit_tool_result(skill.name, result, duration_ms, success=True)
            logger.info(f"[ReAct] Skill '{skill.name}' executed in {duration_ms:.0f}ms")

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            observation = Observation(
                skill_name=skill.name,
                inputs=thought.inputs,
                result=None,
                success=False,
                error=error_msg,
                duration_ms=int(duration_ms),
            )
            observations.append(observation)

            yield emit_tool_result(skill.name, {"error": error_msg}, duration_ms, success=False)
            logger.warning(f"[ReAct] Skill '{skill.name}' failed: {error_msg}")

    # Max steps reached
    logger.warning(f"[ReAct] Max steps ({max_steps}) reached without completion")
    yield emit_error(
        f"Maximum steps ({max_steps}) reached without achieving goal", "MAX_STEPS_EXCEEDED"
    )

__all__ = [
    "LLMThinkingProvider",
    "RuntimeSkillExecutor",
    "ClarifyHumanHandler",
    "stream_react_execution",
    "LEASH_PRESETS",
    "submit_autonomous_clarification",
    "has_pending_autonomous_clarification",
]
