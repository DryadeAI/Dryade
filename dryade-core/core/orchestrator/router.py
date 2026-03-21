"""Execution Router - Routes requests to appropriate execution handler.

Two-path dispatcher (Phase 85):
- PLANNER: Workflow/plan execution (PlannerHandler)
- ORCHESTRATE: Everything else - chat, agent coordination, autonomous (OrchestrateHandler)

No intent detection or classification step. The orchestrator handles all
non-planner messages directly, including simple chat, via its ReAct loop.

Architecture:
- Router is thin dispatcher (~150 LOC)
- Two handlers in core/orchestrator/handlers/
- mode_override from frontend selects path
- Default path is ORCHESTRATE (orchestrator handles chat natively)
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.extensions.events import (
    ChatEvent,
    emit_complete,
    emit_error,
    emit_thinking,
)
from core.orchestrator.handlers import OrchestrateHandler, PlannerHandler

logger = logging.getLogger("dryade.router")

class ExecutionMode(str, Enum):
    """Execution modes supported by the router.

    Simplified to 2 modes (Phase 85):
    - PLANNER: Workflow/plan execution
    - ORCHESTRATE: Everything else (chat, agents, autonomous)
    """

    PLANNER = "planner"
    ORCHESTRATE = "orchestrate"

class ExecutionContext(BaseModel):
    """Context for a single execution request.

    Attributes:
        conversation_id: Unique identifier for the conversation.
        user_id: Optional user identifier.
        mode: Selected execution mode.
        metadata: Additional context data (enable_thinking, user_llm_config, etc.).
    """

    conversation_id: str
    user_id: str | None = None
    mode: ExecutionMode = ExecutionMode.ORCHESTRATE
    metadata: dict[str, Any] = Field(default_factory=dict)

class ExecutionRouter:
    """Routes execution requests to mode-specific handlers.

    Two-path dispatcher:
    - PlannerHandler for PLANNER mode
    - OrchestrateHandler for ORCHESTRATE mode (default)

    Also handles escalation responses (cross-mode concern).
    """

    def __init__(self) -> None:
        """Initialize the execution router with handlers."""
        self._planner_handler = PlannerHandler()
        self._orchestrate_handler = OrchestrateHandler()

    async def route(
        self,
        message: str,
        context: ExecutionContext,
        stream: bool = True,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Route message to appropriate handler.

        Checks for pending escalation first, then delegates to mode handler.
        """
        # Check for pending escalation approval first
        escalation_result = await self._handle_escalation_response(message, context)
        if escalation_result is not None:
            async for event in escalation_result:
                yield event
            return

        # Check for pending clarification (AFTER escalation -- escalation takes priority)
        clarification_result = await self._handle_clarification_response(message, context)
        if clarification_result is not None:
            async for event in clarification_result:
                yield event
            return

        try:
            handler = {
                ExecutionMode.PLANNER: self._planner_handler,
                ExecutionMode.ORCHESTRATE: self._orchestrate_handler,
            }.get(context.mode)

            if handler:
                async for event in handler.handle(message, context, stream):
                    yield event
            else:
                yield emit_error(f"Unknown mode: {context.mode}", "UNKNOWN_MODE")
        except Exception as e:
            logger.error(
                f"[ROUTER] Execution error in {context.mode} mode: {str(e)}", exc_info=True
            )
            yield emit_error(f"{type(e).__name__}: {str(e)}", "EXECUTION_ERROR")

    async def _handle_escalation_response(
        self, message: str, context: ExecutionContext
    ) -> AsyncGenerator[ChatEvent, None] | None:
        """Check if message is a response to a pending escalation.

        If there's a pending escalation for this conversation and the message
        indicates approval or rejection, handle it accordingly.

        Returns:
            AsyncGenerator yielding events if escalation was handled, None otherwise.
        """
        from core.orchestrator.escalation import (
            EscalationActionType,
            EscalationExecutor,
            get_escalation_registry,
            is_approval_message,
        )

        registry = get_escalation_registry()
        escalation = registry.get_pending(context.conversation_id)

        if not escalation:
            return None

        approval = is_approval_message(message)

        if approval is None:
            # Check if this is factory refinement (not a clear yes/no)
            if escalation.action.action_type == EscalationActionType.FACTORY_CREATE:
                refinement_result = self._handle_factory_refinement(
                    message, escalation, context, registry
                )
                if refinement_result is not None:
                    return refinement_result

            # Message doesn't seem to be a direct response to escalation
            # Clear the escalation and proceed normally
            registry.clear(context.conversation_id)
            logger.info("[ROUTER] Escalation cleared - message was not a response")
            return None

        # Handle rejection
        if approval is False:
            registry.clear(context.conversation_id)
            logger.info("[ROUTER] Escalation rejected by user")

            async def rejection_events():
                yield emit_thinking("Understood, I won't make any changes.")
                yield emit_complete(
                    "No problem. Let me know if you'd like to try a different approach.",
                    {"escalation_rejected": True},
                )

            return rejection_events()

        # Handle approval - execute the fix
        logger.info(
            f"[ROUTER] Escalation approved - executing action: {escalation.action.action_type.value}"
        )

        async def approval_events():
            yield emit_thinking(f"Executing: {escalation.action.description}")

            # Bridge factory progress events into this generator via a queue
            # so the user sees real-time status instead of 90s of silence.
            progress_queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

            # Monkey-patch the factory progress callback for this execution
            _original_emit = None
            try:
                from core.factory.orchestrator import FactoryPipeline

                _original_emit = FactoryPipeline._emit_progress

                async def _bridged_emit(
                    self_pipeline: Any,
                    step: int,
                    step_name: str,
                    artifact_name: str,
                    detail: str = "",
                ) -> None:
                    """Send progress both to WS (out-of-band) and to the generator queue."""
                    # Original WS direct send (best-effort)
                    await _original_emit(self_pipeline, step, step_name, artifact_name, detail)
                    # Bridge into generator so frontend sees thinking tokens
                    total = 8
                    msg = f"Factory step {step}/{total}: {step_name}"
                    if detail:
                        msg += f" — {detail}"
                    if artifact_name:
                        msg += f" ({artifact_name})"
                    await progress_queue.put(emit_thinking(msg))

                FactoryPipeline._emit_progress = _bridged_emit  # type: ignore[assignment]
            except (ImportError, AttributeError):
                pass

            # Run executor in a task so we can drain the progress queue concurrently
            async def _run_executor() -> tuple[bool, str]:
                executor = EscalationExecutor()
                return await executor.execute(escalation.action)

            executor_task = asyncio.create_task(_run_executor())

            # Drain progress events until executor completes
            while not executor_task.done():
                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                    if event is not None:
                        yield event
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining queued events
            while not progress_queue.empty():
                event = progress_queue.get_nowait()
                if event is not None:
                    yield event

            # Restore original method
            if _original_emit is not None:
                try:
                    from core.factory.orchestrator import FactoryPipeline

                    FactoryPipeline._emit_progress = _original_emit  # type: ignore[assignment]
                except (ImportError, AttributeError):
                    pass

            success, result_message = executor_task.result()

            if success:
                # Clear the escalation
                registry.clear(context.conversation_id)

                # Phase 174.5: FACTORY_CREATE completes the entire workflow
                # (config → scaffold → test → register). Don't retry the
                # original goal — the artifact is already created. Retrying
                # causes the LLM to see "Created X" in observations and
                # hallucinate "already created" without doing anything.
                if escalation.action.action_type == EscalationActionType.FACTORY_CREATE:
                    yield emit_thinking(f"Factory complete: {result_message}")
                    yield emit_complete(
                        result_message,
                        {"factory_create_success": True},
                    )
                else:
                    # Non-factory escalations (MCP config, etc.) need retry
                    # to re-attempt the original operation with the fix applied.
                    yield emit_thinking(f"Fix applied: {result_message}")
                    yield emit_thinking("Retrying your original request...")

                    executor_obs = {
                        "agent_name": "escalation-executor",
                        "task": f"Execute {escalation.action.action_type.value}",
                        "result": result_message,
                        "success": success,
                        "error": None,
                    }
                    prior_observations = list(escalation.observations or [])
                    prior_observations.append(executor_obs)

                    retry_metadata = {
                        **(escalation.original_context or {}),
                        "_prior_observations": prior_observations,
                        "_prior_state": escalation.orchestration_state,
                        "_prior_observation_history": escalation.observation_history,
                        "_is_escalation_retry": True,
                    }
                    retry_context = ExecutionContext(
                        conversation_id=context.conversation_id,
                        user_id=context.user_id,
                        mode=ExecutionMode.ORCHESTRATE,
                        metadata=retry_metadata,
                    )

                    async for event in self._orchestrate_handler.handle(
                        escalation.original_goal, retry_context, stream=True
                    ):
                        yield event
            else:
                # Build actionable failure message based on the error.
                # Extract artifact name from result_message since params may
                # not have suggested_name (Phase 167 removed English regex).
                params = escalation.action.parameters or {}
                agent_name = params.get("suggested_name") or params.get("failed_agent")
                if not agent_name:
                    # Try to extract from factory result: "Created {name} but..."
                    import re as _re

                    _match = _re.search(r"Created\s+(\S+)", result_message)
                    agent_name = _match.group(1) if _match else params.get("goal", "agent")[:60]

                task_desc = params.get("task_description", "")

                guidance_parts = [f"Failed to create **{agent_name}** automatically."]

                # Always include the actual error reason
                guidance_parts.append(f"\n**Reason:** {result_message}")

                if "Server process exited during startup" in result_message:
                    # MCP server startup failure — likely missing env var or package
                    guidance_parts.append(
                        "\n**Possible causes:**\n"
                        "- Missing API key (check environment variables)\n"
                        "- Package not available (check npx/npm connectivity)\n"
                        "- Server binary not installed"
                    )
                    cmd = params.get("command")
                    if cmd:
                        cmd_str = " ".join(cmd)
                        guidance_parts.append(f"\n**To debug manually**, run:\n`{cmd_str}`")
                elif "without a command" in result_message:
                    guidance_parts.append(
                        "\n**To create this agent manually**, use the "
                        "`add_mcp_server` tool with the MCP server command."
                    )

                if task_desc:
                    guidance_parts.append(f"\n**Original request:** {task_desc[:200]}")

                failure_msg = "\n".join(guidance_parts)

                # Use emit_thinking instead of emit_error to avoid killing the
                # event stream — frontend's error handler returns early,
                # preventing emit_complete from being processed.
                yield emit_thinking(f"Escalation failed: {result_message}")
                yield emit_complete(failure_msg, {"escalation_failed": True})
                registry.clear(context.conversation_id)

        return approval_events()

    def _handle_factory_refinement(
        self,
        message: str,
        escalation: "PendingEscalation",
        context: "ExecutionContext",
        registry: "EscalationRegistry",
    ) -> AsyncGenerator | None:
        """Handle refinement input for FACTORY_CREATE escalations.

        When the user responds to a factory creation proposal with something
        other than yes/no (e.g., "but use crewai" or "add error handling"),
        merge the refinement into the factory parameters and re-propose.

        Returns an async generator of events if refinement was handled,
        None if refinement should not be attempted (e.g., max turns reached).
        """
        from core.orchestrator.escalation import (
            EscalationAction,
            EscalationActionType,
            PendingEscalation,
        )

        params = dict(escalation.action.parameters or {})

        # Track refinement turns (max 5)
        refinement_count = params.get("_refinement_count", 0)
        if refinement_count >= 5:
            logger.info("[ROUTER] Max factory refinement turns reached, forcing decision")
            return None  # Fall through to clear escalation

        # Merge user refinement into goal
        original_goal = params.get("goal", "")
        refined_goal = f"{original_goal}\n\nUser refinement: {message}"
        params["goal"] = refined_goal
        params["_refinement_count"] = refinement_count + 1

        # Check for explicit framework override in user message
        msg_lower = message.lower()
        framework_keywords = {
            "crewai": "crewai",
            "crew ai": "crewai",
            "langgraph": "langgraph",
            "langchain": "langgraph",
            "adk": "adk",
            "google adk": "adk",
            "custom": "custom_python",
            "custom python": "custom_python",
            "mcp": "mcp_function",
            "mcp server": "mcp_server",
            "fastmcp": "mcp_function",
        }
        for keyword, framework in framework_keywords.items():
            if keyword in msg_lower:
                params["framework"] = framework
                break

        # Build updated escalation action
        updated_action = EscalationAction(
            action_type=EscalationActionType.FACTORY_CREATE,
            parameters=params,
            description=f"Create via factory (refined x{refinement_count + 1}): {refined_goal[:200]}",
        )

        suggested_name = params.get("suggested_name", "artifact")
        question = f"**Agent Factory** → **{suggested_name}**\n\n{refined_goal[:300]}\n"
        if params.get("framework"):
            question += f"Framework: {params['framework']}\n"
        if params.get("artifact_type"):
            question += f"Type: {params['artifact_type']}\n"
        question += f"\n({refinement_count + 1}/5) ✅ / ❌ ?"

        # Replace the pending escalation with the refined version
        updated_escalation = PendingEscalation(
            conversation_id=escalation.conversation_id,
            original_goal=escalation.original_goal,
            original_context=escalation.original_context,
            action=updated_action,
            question=question,
            observations=escalation.observations,
            orchestration_state=escalation.orchestration_state,
            observation_history=escalation.observation_history,
        )

        # Clear old and register updated
        registry.clear(context.conversation_id)
        registry.register(updated_escalation)
        logger.info(f"[ROUTER] Factory refinement {refinement_count + 1}/5 applied")

        async def refinement_events():
            yield emit_complete(question, {"factory_refinement": True})

        return refinement_events()

    async def _handle_clarification_response(
        self, message: str, context: ExecutionContext
    ) -> AsyncGenerator[ChatEvent, None] | None:
        """Check if this message is a response to a pending clarification.

        When the orchestrator asked a clarification question, it registered
        the original goal and context. If the user's next message lands in
        a conversation with a pending clarification, we merge the original
        goal with the user's answer and re-dispatch through ORCHESTRATE.

        Returns:
            An async generator of events if clarification was detected,
            or None to continue normal routing.
        """
        from core.orchestrator.clarification import get_clarification_registry

        registry = get_clarification_registry()
        pending = registry.get_pending(context.conversation_id)
        if pending is None:
            return None

        # Clear the pending clarification (consumed)
        registry.clear(context.conversation_id)

        # Merge the original goal with the user's clarification answer
        merged_goal = f"{pending.original_goal}\n\nUser clarified: {message}"

        logger.info(
            f"[ROUTER] Clarification response detected for conversation "
            f"{context.conversation_id}. Merging with original goal and re-dispatching."
        )

        # Re-dispatch through the ORCHESTRATE handler with merged goal
        # Preserve original context metadata (router_hints, etc.)
        merged_metadata = {**pending.original_context, **context.metadata}
        # Debug marker: flag this as a clarification retry
        merged_metadata["_is_clarification_retry"] = True
        # Ensure the execution mode is ORCHESTRATE (clarification always comes from complex path)
        retry_context = ExecutionContext(
            conversation_id=context.conversation_id,
            user_id=context.user_id,
            mode=ExecutionMode.ORCHESTRATE,
            metadata=merged_metadata,
        )

        async def _generate():
            async for event in self._orchestrate_handler.handle(
                merged_goal, retry_context, stream=True
            ):
                yield event

        return _generate()

# Global router instance
_router: ExecutionRouter | None = None

def get_router() -> ExecutionRouter:
    """Get or create the global router instance."""
    global _router
    if _router is None:
        _router = ExecutionRouter()
    return _router

# Mode mapping: all legacy and current mode strings -> ExecutionMode
_MODE_MAP: dict[str, ExecutionMode] = {
    "planner": ExecutionMode.PLANNER,
    "flow": ExecutionMode.PLANNER,
    "chat": ExecutionMode.ORCHESTRATE,
    "orchestrate": ExecutionMode.ORCHESTRATE,
    "crew": ExecutionMode.ORCHESTRATE,
    "autonomous": ExecutionMode.ORCHESTRATE,
}

async def route_request(
    message: str,
    conversation_id: str,
    user_id: str | None = None,
    mode_override: str | None = None,
    stream: bool = True,
    enable_thinking: bool = False,
    user_llm_config: Any | None = None,
    crew_id: str | None = None,
    leash_preset: str | None = None,
    event_visibility: str | None = None,
    image_attachments: list[dict[str, str]] | None = None,
    db: Any | None = None,
) -> AsyncGenerator[ChatEvent, None]:
    """Convenience function to route a request.

    Args:
        message: User message to process
        conversation_id: Conversation identifier
        user_id: Optional user identifier
        mode_override: Optional execution mode override (planner, flow, chat, orchestrate, crew, autonomous)
        stream: Whether to stream the response
        enable_thinking: Enable LLM reasoning mode
        user_llm_config: Optional UserLLMConfig from database (from Settings page)
        crew_id: Optional crew ID for crew mode (analysis_crew, mbse_crew)
        leash_preset: Autonomy constraint preset for autonomous mode
        event_visibility: Visibility level for streamed events (named-steps or full-transparency)
        image_attachments: Optional list of image dicts with base64 and mime_type keys for vision input
    """
    # Map mode_override to ExecutionMode (default: ORCHESTRATE)
    mode = (
        _MODE_MAP.get(mode_override, ExecutionMode.ORCHESTRATE)
        if mode_override
        else ExecutionMode.ORCHESTRATE
    )

    context = ExecutionContext(
        conversation_id=conversation_id,
        user_id=user_id,
        mode=mode,
    )
    # Pass enable_thinking in metadata for LLM calls
    context.metadata["enable_thinking"] = enable_thinking
    # Pass user's LLM config from database (Settings page)
    context.metadata["user_llm_config"] = user_llm_config
    # Pass crew_id for crew mode execution
    context.metadata["crew_id"] = crew_id
    # Pass leash_preset for autonomous mode execution
    context.metadata["leash_preset"] = leash_preset or "standard"
    # Pass event_visibility for full-transparency toggle
    context.metadata["event_visibility"] = event_visibility or "named-steps"
    # Pass the original mode string for orchestration mode tracking
    # ComplexHandler reads this to set OrchestrationMode and propagate to emit_complete
    if mode_override:
        context.metadata["orchestration_mode"] = mode_override
    # Pass image attachments for multimodal vision input
    if image_attachments:
        context.metadata["image_attachments"] = image_attachments

    # Fetch conversation history for LLM context (prior turns only)
    from core.services.conversation import get_recent_history

    history = []
    if conversation_id:
        try:
            raw_history = get_recent_history(conversation_id, limit=10, db=db)
            # Drop the last message if it's the current user message
            # (messages are persisted to DB BEFORE route_request is called)
            if raw_history and raw_history[-1]["role"] == "user":
                history = raw_history[:-1]
            else:
                history = raw_history
        except Exception as e:
            logger.warning("Failed to fetch conversation history: %s", e)
    context.metadata["history"] = history
    if conversation_id:
        logger.info("[ROUTE_REQUEST] conv=%s history_msgs=%d", conversation_id[:12], len(history))

    async for event in get_router().route(message, context, stream):
        yield event
