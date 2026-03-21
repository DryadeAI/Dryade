"""Planner mode execution handler.

Handles plan generation and validation:
- Intent classification (NEW_PLAN, MODIFY_PLAN, CONVERSATION)
- Pre-plan clarification questions
- Active plan caching per conversation
- Conversational follow-up handling
- LLM-based plan generation
- Plan validation
- Plan data emission for frontend rendering
"""

import json
import logging
import re
from collections.abc import AsyncGenerator
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.extensions.events import (
    ChatEvent,
    emit_complete,
    emit_error,
    emit_token,
)

if TYPE_CHECKING:
    from core.orchestrator.router import ExecutionContext

logger = logging.getLogger("dryade.router.planner")

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

class PlannerIntent(str, Enum):
    """Classified intent for planner mode messages."""

    NEW_PLAN = "new_plan"
    MODIFY_PLAN = "modify_plan"
    CONVERSATION = "conversation"

# Regex patterns for intent classification (module-level, compiled once)
MODIFY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bchange\s+(step|node|task)\b", re.IGNORECASE),
    re.compile(r"\b(modify|update|edit|adjust|tweak)\s+(step|node|the plan)\b", re.IGNORECASE),
    re.compile(r"\bstep\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b(add|remove|delete|swap|replace)\s+(a\s+)?(step|node|agent)\b", re.IGNORECASE),
    re.compile(r"\b(move|reorder)\s+(step|node)\b", re.IGNORECASE),
    re.compile(r"\binstead\s+of\b", re.IGNORECASE),
]

CONVO_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(what|why|how|explain|tell me|can you)\b", re.IGNORECASE),
    re.compile(r"\b(understand|meaning|purpose|reason)\b", re.IGNORECASE),
    re.compile(r"\bhow (long|much|many)\b", re.IGNORECASE),
    re.compile(r"^(thanks|ok|got it|I see)\b", re.IGNORECASE),
]

NEW_PLAN_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(new plan|start over|from scratch|plan something|create a plan|generate a plan)\b",
        re.IGNORECASE,
    ),
]

def classify_planner_intent(message: str, has_active_plan: bool) -> PlannerIntent:
    """Classify user message intent for planner mode.

    Args:
        message: The user's message text.
        has_active_plan: Whether there is an active plan for the conversation.

    Returns:
        PlannerIntent indicating what the user wants to do.
    """
    if not has_active_plan:
        return PlannerIntent.NEW_PLAN

    # Explicit new plan request takes priority
    for pattern in NEW_PLAN_PATTERNS:
        if pattern.search(message):
            return PlannerIntent.NEW_PLAN

    # Conversational patterns checked before modify -- questions about steps
    # (e.g. "What does step 2 do?") are conversation, not modification
    for pattern in CONVO_PATTERNS:
        if pattern.search(message):
            return PlannerIntent.CONVERSATION

    # Plan modification patterns
    for pattern in MODIFY_PATTERNS:
        if pattern.search(message):
            return PlannerIntent.MODIFY_PLAN

    # Default with active plan: user is iterating, not starting fresh
    return PlannerIntent.MODIFY_PLAN

class PlannerHandler:
    """Handler for PLANNER execution mode.

    Generates execution plans from user requests, validates them,
    and emits plan data for frontend rendering.

    Workflow:
        1. Classify user intent (new plan, modify, conversation)
        2. Check clarification needs before generating new plans
        3. Generate/modify plan or respond conversationally
        4. Validate plan structure
        5. Emit plan data for frontend PlanCard rendering

    Features:
        - Intent classification (NEW_PLAN, MODIFY_PLAN, CONVERSATION)
        - Pre-plan clarification questions via LLM
        - Active plan caching per conversation
        - Conversational follow-up without plan regeneration
        - LLM-based plan generation and modification
        - Plan validation
    """

    _MAX_CACHED_PLANS = 100

    def __init__(self) -> None:
        self._active_plans: dict[str, Any] = {}

    def _load_plan_from_db(self, conversation_id: str) -> Any | None:
        """Load the latest active plan from DB for a conversation.

        Returns an ExecutionPlan-like object from the planner module, or None.
        Used as fallback when in-memory cache misses (e.g., after restart).
        """
        try:
            from core.database.models import ExecutionPlan as DBExecutionPlan
            from core.database.session import get_session
            from core.orchestrator.models import ExecutionPlan, PlanNode

            with get_session() as db:
                db_plan = (
                    db.query(DBExecutionPlan)
                    .filter_by(conversation_id=conversation_id)
                    .filter(DBExecutionPlan.status.in_(["draft", "approved"]))
                    .order_by(DBExecutionPlan.updated_at.desc())
                    .first()
                )
                if not db_plan:
                    return None

                # Convert DB model back to planner ExecutionPlan
                nodes = [
                    PlanNode(
                        id=n.get("id", ""),
                        agent=n.get("agent", ""),
                        task=n.get("task", ""),
                        depends_on=n.get("depends_on", []),
                    )
                    for n in (db_plan.nodes or [])
                ]
                plan = ExecutionPlan.from_nodes(
                    name=db_plan.name,
                    description=db_plan.description or "",
                    nodes=nodes,
                    reasoning=db_plan.reasoning or "",
                    confidence=db_plan.confidence or 0.0,
                )
                # Store the DB id for future updates
                plan._db_id = db_plan.id  # type: ignore[attr-defined]

                logger.debug(
                    "[PLANNER] Loaded plan from DB for conversation %s (plan_id=%s)",
                    conversation_id,
                    db_plan.id,
                )
                return plan

        except Exception:
            logger.warning(
                "[PLANNER] Failed to load plan from DB, continuing without",
                exc_info=True,
            )
            return None

    def _save_plan_to_db(self, plan: Any, conversation_id: str, user_id: str | None) -> None:
        """Persist the active plan to the ExecutionPlan table.

        Creates a new record or updates existing one. Errors are logged but
        never crash the handler -- the in-memory cache is always the primary.
        """
        try:
            from core.database.models import ExecutionPlan as DBExecutionPlan
            from core.database.session import get_session

            nodes_data = [
                {"id": n.id, "agent": n.agent, "task": n.task, "depends_on": n.depends_on}
                for n in plan.nodes
            ]
            edges_data = [
                {"source": dep, "target": n.id} for n in plan.nodes for dep in n.depends_on
            ]

            with get_session() as db:
                db_id = getattr(plan, "_db_id", None)
                if db_id:
                    # Update existing record
                    db_plan = db.query(DBExecutionPlan).filter_by(id=db_id).first()
                    if db_plan:
                        db_plan.name = plan.name
                        db_plan.description = plan.description
                        db_plan.nodes = nodes_data
                        db_plan.edges = edges_data
                        db_plan.reasoning = plan.reasoning
                        db_plan.confidence = plan.confidence
                        db.commit()
                        logger.debug("[PLANNER] Updated plan in DB (id=%s)", db_id)
                        return

                # Ensure conversation record exists (FK constraint)
                from core.database.models import Conversation

                existing = db.query(Conversation).filter_by(id=conversation_id).first()
                if not existing:
                    conv = Conversation(id=conversation_id, user_id=user_id, title=plan.name)
                    db.add(conv)
                    db.flush()

                # Create new record
                db_plan = DBExecutionPlan(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    name=plan.name,
                    description=plan.description,
                    nodes=nodes_data,
                    edges=edges_data,
                    reasoning=plan.reasoning,
                    confidence=plan.confidence,
                    status="draft",
                    ai_generated=True,
                )
                db.add(db_plan)
                db.commit()
                db.refresh(db_plan)
                plan._db_id = db_plan.id  # type: ignore[attr-defined]
                logger.info("[PLANNER] Saved new plan to DB (id=%s)", db_plan.id)

        except Exception:
            logger.error(
                "[PLANNER] Failed to save plan to DB, continuing with in-memory only",
                exc_info=True,
            )

    async def _check_needs_clarification(
        self, message: str, context: "ExecutionContext"
    ) -> str | None:
        """Check if the user request needs clarification before planning.

        Uses a focused LLM prompt to determine if the request is clear enough
        to generate an execution plan, given the available agents.

        Only triggers for genuinely vague/ambiguous requests (< 5 words with
        no clear action). Detailed requests skip clarification entirely.

        Args:
            message: User's request message.
            context: Execution context with metadata.

        Returns:
            Clarification questions string if needed, None if request is clear.
        """
        # Heuristic pre-filter: skip clarification for specific-enough messages.
        # Messages with 5+ words or that mention an action are clear enough.
        words = message.strip().split()
        if len(words) >= 5:
            logger.debug("[PLANNER] Skipping clarification -- message has %d words", len(words))
            return None

        from core.orchestrator.planner import get_planner

        planner = get_planner()
        capabilities = planner.get_available_capabilities()

        if not capabilities:
            return None  # Nothing to clarify against

        agents_summary = json.dumps(
            [{"name": c["agent"], "description": c["description"]} for c in capabilities],
            indent=2,
        )

        prompt_text = (
            "You are a planning assistant. A user wants to create an execution plan.\n\n"
            f"Available Agents:\n{agents_summary}\n\n"
            f"User Request: {message}\n\n"
            "IMPORTANT: Almost all requests are clear enough to plan. The planner can "
            "infer missing details and choose appropriate agents automatically. "
            "Only ask for clarification if the request is truly meaningless or "
            "completely ambiguous (e.g., 'do something', 'help me', single words "
            "with no context).\n\n"
            "If you can reasonably interpret the request, respond: "
            '{{"clear": true}}\n'
            "Only if the request is genuinely too vague, respond: "
            '{{"clear": false, "questions": '
            '"Your clarification questions as a natural response to the user"}}'
        )

        # Include last 4 messages from history for conversation context
        history = context.metadata.get("history", [])
        recent_history = history[-4:] if history else []
        messages = recent_history + [{"role": "user", "content": prompt_text}]

        try:
            logger.debug("[PLANNER] Calling LLM for clarification check")
            response = planner.llm.call(messages)

            # Parse response
            response_text = response
            if isinstance(response, dict):
                response_text = response.get("content", "")
            response_text = str(response_text).strip()

            # Strip thinking tags if present
            if "<think>" in response_text and "</think>" in response_text:
                response_text = response_text.split("</think>")[-1].strip()

            # Extract JSON from markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            # Find JSON object
            if not response_text.startswith("{"):
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}")
                if start_idx != -1 and end_idx > start_idx:
                    response_text = response_text[start_idx : end_idx + 1]

            result = json.loads(response_text)

            if not result.get("clear", True):
                questions = result.get("questions", "")
                if questions:
                    logger.info("[PLANNER] Clarification needed, returning questions")
                    return questions

            return None

        except Exception:
            # Fail open: on any parse/call error, proceed with plan generation
            logger.debug("[PLANNER] Clarification check failed, proceeding with planning")
            return None

    async def _chat_about_plan(self, message: str, plan: Any, context: "ExecutionContext") -> str:
        """Answer a conversational question about the active plan.

        Args:
            message: User's question about the plan.
            plan: The active ExecutionPlan object.
            context: Execution context with metadata.

        Returns:
            LLM response string answering the user's question.
        """
        from core.orchestrator.planner import get_planner

        planner = get_planner()

        nodes_summary = ", ".join(f"{n.agent}: {n.task[:50]}" for n in plan.nodes)

        prompt_text = (
            "You are answering a question about an execution plan.\n\n"
            f"Plan Name: {plan.name}\n"
            f"Description: {plan.description}\n"
            f"Steps: {nodes_summary}\n\n"
            f"User Question: {message}\n\n"
            "Provide a helpful, concise answer about the plan."
        )

        try:
            response = planner.llm.call([{"role": "user", "content": prompt_text}])
            response_text = response
            if isinstance(response, dict):
                response_text = response.get("content", "")
            return str(response_text).strip()
        except Exception:
            logger.error("[PLANNER] Error in _chat_about_plan", exc_info=True)
            return "I couldn't process that question about the plan."

    async def handle(
        self,
        message: str,
        context: "ExecutionContext",
        stream: bool = True,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle planner mode - classify intent and route accordingly.

        Classifies the user's intent and routes to:
        - CONVERSATION: Direct LLM answer about the active plan
        - MODIFY_PLAN: Context-aware plan regeneration
        - NEW_PLAN: Clarification check, then plan generation

        Args:
            message: User message describing the task
            context: Execution context with metadata
            stream: Whether to stream progress updates

        Yields:
            ChatEvent: Progress, token, complete, or error events
        """
        from core.orchestrator.models import ExecutionPlan
        from core.orchestrator.planner import get_planner

        logger.info(f"[PLANNER] Starting planner mode for conversation {context.conversation_id}")
        logger.info(f"[PLANNER] User message: {message[:100]}...")

        planner = get_planner()
        conversation_id = context.conversation_id

        # Step 1: Check if there's an active plan for this conversation
        active_plan = self._active_plans.get(conversation_id)
        if active_plan is None:
            active_plan = self._load_plan_from_db(conversation_id)
            if active_plan is not None:
                self._active_plans[conversation_id] = active_plan
        has_active_plan = active_plan is not None

        # Step 2: Classify intent
        intent = classify_planner_intent(message, has_active_plan)
        logger.info(f"[PLANNER] Intent: {intent.value}, active_plan: {has_active_plan}")

        # Step 3: Handle CONVERSATION intent (no plan generation)
        if intent == PlannerIntent.CONVERSATION and active_plan:
            response = await self._chat_about_plan(message, active_plan, context)
            yield emit_token(response)
            yield emit_complete(response, {"mode": "planner", "intent": "conversation"})
            return

        # Step 4: Handle MODIFY_PLAN intent
        if intent == PlannerIntent.MODIFY_PLAN and active_plan:
            if stream:
                yield emit_token("Updating plan based on your feedback...\n")
            try:
                plan = await planner.modify_plan(active_plan, message, context.metadata)
            except Exception as e:
                logger.error("[PLANNER] modify_plan failed: %s", e, exc_info=True)
                yield emit_error(f"Failed to modify plan: {e}", "PLAN_MODIFY_ERROR")
                return
        else:
            # Step 5: NEW_PLAN -- check clarification first
            clarification = await self._check_needs_clarification(message, context)
            if clarification:
                logger.info("[PLANNER] Returning clarification questions instead of plan")
                yield emit_token(clarification)
                yield emit_complete(clarification, {"mode": "planner", "needs_clarification": True})
                return

            if stream:
                yield emit_token("Analyzing request and generating execution plan...\n")
            try:
                plan = await planner.generate_plan(message, context.metadata)
            except Exception as e:
                logger.error("[PLANNER] generate_plan failed: %s", e, exc_info=True)
                yield emit_error(f"Failed to generate plan: {e}", "PLAN_GENERATE_ERROR")
                return

        logger.info(f"[PLANNER] Received plan '{plan.name}' from planner")

        # Cache the active plan
        if isinstance(plan, ExecutionPlan):
            self._active_plans[conversation_id] = plan
            # Enforce cache size limit
            if len(self._active_plans) > self._MAX_CACHED_PLANS:
                oldest_key = next(iter(self._active_plans))
                del self._active_plans[oldest_key]

            # Persist to DB for cross-worker and restart resilience
            user_id = context.user_id or context.metadata.get("user_id")
            self._save_plan_to_db(plan, conversation_id, user_id)

        # Validate plan
        logger.info("[PLANNER] Validating generated plan")
        is_valid, issues = await planner.validate_plan(plan)

        if not is_valid:
            logger.error(f"[PLANNER] Plan validation failed: {issues}")
            yield emit_error(f"Invalid plan: {', '.join(issues)}", "PLAN_VALIDATION_ERROR")
            return

        logger.info("[PLANNER] Plan validation successful")

        # Emit plan summary as text
        plan_summary = (
            f"Generated plan: {plan.name}\n"
            f"Reasoning: {plan.reasoning}\n"
            f"Confidence: {plan.confidence:.0%}\n"
            f"Steps: {len(plan.nodes)}"
        )
        if stream:
            yield emit_token(plan_summary + "\n\n")

        # Emit complete with plan data in metadata for frontend PlanCard rendering
        plan_data = {
            "id": None,  # Not saved to DB yet — frontend will save via createPlan
            "name": plan.name,
            "description": plan.description,
            "confidence": plan.confidence,
            "reasoning": plan.reasoning,
            "nodes": [
                {"id": n.id, "agent": n.agent, "task": n.task, "depends_on": n.depends_on}
                for n in plan.nodes
            ],
            "edges": [{"source": dep, "target": n.id} for n in plan.nodes for dep in n.depends_on],
            "status": "draft",
            "ai_generated": True,
        }

        yield emit_complete(
            plan_summary,
            {
                "mode": "planner",
                "intent": intent.value,
                "plan_data": plan_data,
            },
        )

        logger.info("[PLANNER] Planner mode completed - plan emitted for frontend rendering")
