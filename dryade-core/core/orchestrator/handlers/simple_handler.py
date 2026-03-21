"""SIMPLE tier handler -- direct agent dispatch, no orchestrator.

Dispatches directly to the target agent identified by the classifier,
bypassing orchestrate_think() entirely (zero extra LLM calls).
Falls back to COMPLEX transparently on failure.

Phase 91: Single-agent tasks routed here by ComplexityEstimator.
"""

import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from core.extensions.events import (
    ChatEvent,
    emit_agent_complete,
    emit_agent_start,
    emit_complete,
)
from core.orchestrator.complexity import TierDecision
from core.orchestrator.handlers.base import OrchestrateHandlerBase

if TYPE_CHECKING:
    from core.orchestrator.router import ExecutionContext

logger = logging.getLogger("dryade.router.orchestrate.simple")

# =============================================================================
# SIMPLE Tier Helpers (Phase 91)
# Module-level helpers to resolve agent/tool names, optionally confirm via
# router, and extract arguments from messages.
# =============================================================================

def _resolve_agent(registry, target_agent: str) -> tuple:
    """Resolve an agent from the registry with case-insensitive fallback.

    The classifier lowercases agent names but the registry uses exact match.

    Args:
        registry: AgentRegistry instance.
        target_agent: Agent name from TierDecision (may be lowercased).

    Returns:
        Tuple of (agent_instance_or_None, resolved_name).
    """
    # Try exact match first
    agent = registry.get(target_agent)
    if agent is not None:
        return (agent, target_agent)

    # Case-insensitive fallback
    for card in registry.list_agents():
        if card.name.lower() == target_agent.lower():
            agent = registry.get(card.name)
            if agent is not None:
                return (agent, card.name)

    return (None, target_agent)

def _resolve_tool_name(agent, matched_tool_lower: str | None) -> str | None:
    """Resolve original-case tool name from agent capabilities.

    The classifier lowercases tool names but MCP agents need exact case.

    Args:
        agent: UniversalAgent instance.
        matched_tool_lower: Lowercased tool name from TierDecision, or None.

    Returns:
        Original-case tool name, or the input as-is if no match found.
    """
    if matched_tool_lower is None:
        return None

    card = agent.get_card()
    for cap in card.capabilities:
        if cap.name.lower() == matched_tool_lower.lower():
            return cap.name

    # Fallback: return input as-is
    return matched_tool_lower

def _router_confirms(message: str, target_agent: str) -> bool:
    """Optionally confirm SIMPLE dispatch with the hierarchical router.

    Wraps everything in try/except -- returns True on any error (fail-open
    for router confirmation, since the classifier already decided SIMPLE).

    Args:
        message: User message.
        target_agent: Agent name to confirm.

    Returns:
        True if router agrees or has no strong opinion, False if router
        strongly disagrees (top result score > 0.8 for a different server).
    """
    try:
        from core.mcp.hierarchical_router import get_hierarchical_router

        router = get_hierarchical_router()
        results = router.route(message, top_k=3)

        if not results:
            return True  # No opinion -> proceed

        top = results[0]
        if top.server == target_agent:
            return True  # Agreement

        if top.score > 0.8 and top.server != target_agent:
            return False  # Strong disagreement -> escalate to COMPLEX

        return True  # Weak disagreement -> trust classifier
    except Exception:
        return True  # Error -> proceed

_SIMPLE_PATH_RE = re.compile(r"(?:^|\s)([/~.][\w./\-]+)")
_SIMPLE_QUOTED_RE = re.compile(r'"([^"]+)"')

def _extract_arguments(message: str) -> dict:
    """Extract file paths and quoted strings from a message.

    Conservative extraction per ADR-001 Option A.

    Args:
        message: User message text.

    Returns:
        Dict with optional "path" and "query" keys.
    """
    args: dict = {}

    # Extract file paths (/, ~/, ./ prefixed)
    path_match = _SIMPLE_PATH_RE.search(message)
    if path_match:
        args["path"] = path_match.group(1)

    # Extract quoted strings
    quoted_match = _SIMPLE_QUOTED_RE.search(message)
    if quoted_match:
        args["query"] = quoted_match.group(1)

    return args

class SimpleHandler(OrchestrateHandlerBase):
    """Handle SIMPLE tier -- direct agent dispatch, no orchestrator.

    Dispatches directly to the target agent identified by the classifier,
    bypassing orchestrate_think() entirely (zero extra LLM calls).
    Falls back to COMPLEX transparently on failure by yielding no
    complete event (caller detects this and falls through).
    """

    async def handle(
        self,
        message: str,
        context: "ExecutionContext",
        stream: bool = True,
        tier_decision: TierDecision | None = None,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Handle SIMPLE tier message.

        Args:
            message: User message.
            context: Execution context with preferences.
            stream: Whether to stream output.
            tier_decision: TierDecision with target_agent (and optional target_tool).

        Yields:
            ChatEvent: agent_start, agent_complete, complete on success.
            On failure: agent_start + agent_complete (no complete) so caller
            falls through to COMPLEX.
        """
        if tier_decision is None:
            logger.warning("[ORCHESTRATE] SIMPLE: no tier_decision provided")
            return

        from core.adapters.registry import get_registry

        registry = get_registry()
        agent, resolved_name = _resolve_agent(registry, tier_decision.target_agent)

        if agent is None:
            logger.warning(f"[ORCHESTRATE] SIMPLE: agent '{tier_decision.target_agent}' not found")
            return  # No events -> caller falls through to COMPLEX

        # Optional router confirmation
        from core.orchestrator.config import get_orchestration_config

        router_confirm = get_orchestration_config().tier_simple_router_confirm

        if router_confirm:
            if not _router_confirms(message, resolved_name):
                logger.info(
                    f"[ORCHESTRATE] SIMPLE: Router disagrees with agent '{resolved_name}', "
                    "escalating to COMPLEX"
                )
                return  # No events -> caller falls through to COMPLEX

        # Build execution context dict
        context_dict: dict = {
            "conversation_id": context.conversation_id,
            "user_id": context.user_id,
        }
        # Spread metadata (includes history per research Open Question 3)
        if context.metadata:
            context_dict.update(context.metadata)

        # Resolve tool name to original case
        if tier_decision.target_tool:
            resolved_tool = _resolve_tool_name(agent, tier_decision.target_tool)
            if resolved_tool:
                context_dict["tool"] = resolved_tool

        # Extract arguments from message
        arguments = _extract_arguments(message)
        if arguments:
            context_dict["arguments"] = arguments

        # Knowledge context injection (Phase 94.1)
        knowledge_ctx = context.metadata.get("_knowledge_context")
        dispatch_message = (
            f"RELEVANT KNOWLEDGE:\n{knowledge_ctx}\n\n{message}" if knowledge_ctx else message
        )

        # Emit agent_start
        yield emit_agent_start(resolved_name, message)

        # Execute agent
        t0 = time.perf_counter()
        try:
            result = await agent.execute(dispatch_message, context_dict)
        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                f"[ORCHESTRATE] SIMPLE: agent '{resolved_name}' raised {type(e).__name__}: {e}"
            )
            yield emit_agent_complete(resolved_name, str(e), duration_ms)
            return  # No complete -> caller falls through to COMPLEX

        duration_ms = (time.perf_counter() - t0) * 1000

        # Check result status
        if result.status != "ok":
            logger.info(
                f"[ORCHESTRATE] SIMPLE: agent '{resolved_name}' returned "
                f"status={result.status}, error={result.error}"
            )
            yield emit_agent_complete(resolved_name, result.error or "Failed", duration_ms)
            return  # No complete -> caller falls through to COMPLEX

        # Success
        result_str = str(result.result) if result.result else "Task completed."
        yield emit_agent_complete(resolved_name, result_str[:500], duration_ms)
        yield emit_complete(
            response=result_str,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            orchestration_mode="chat",
        )
