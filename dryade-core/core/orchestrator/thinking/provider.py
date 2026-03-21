"""OrchestrationThinkingProvider -- LLM-based orchestration reasoning.

Follows pattern from core/autonomous/chat_adapter.py LLMThinkingProvider.
Uses get_configured_llm() for user's LLM config.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from core.adapters.protocol import AgentCard
from core.extensions.events import ChatEvent, emit_cost_update
from core.orchestrator.models import (
    ExecutionPlan,
    FailureAction,
    OrchestrationObservation,
    OrchestrationTask,
    OrchestrationThought,
    PlanStep,
    StepStatus,
)
from core.orchestrator.thinking.prompts import (
    FAILURE_SYSTEM_PROMPT,
    FINAL_ANSWER_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    LIGHTWEIGHT_AGENT_ADDENDUM,
    MANAGER_SYSTEM_PROMPT,
    ORCHESTRATE_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    REPLAN_SYSTEM_PROMPT,
    SYNTHESIZE_SYSTEM_PROMPT,
    _format_agents_xml,
)

if TYPE_CHECKING:
    from crewai import LLM

    from core.orchestrator.observation import ObservationHistory

logger = logging.getLogger(__name__)

__all__ = ["OrchestrationThinkingProvider"]

# Maximum number of MCP agents to include when the router produces no matches.
# Prevents the fail-open pattern where ALL agents get sent to the LLM.
MAX_FALLBACK_AGENTS = 5

# General-purpose MCP agents useful for a wide range of queries.
# These are preferred over arbitrary MCP agents in fallback scenarios.
GENERAL_PURPOSE_AGENTS = {"mcp-filesystem", "mcp-memory", "mcp-git"}

# Providers that do NOT support native function/tool calling.
# All other providers (OpenAI, Anthropic, Gemini, Mistral, Azure, Groq, Cohere,
# Bedrock, DeepSeek, xAI, Together, Qwen, Moonshot via LiteLLM, vLLM partial)
# support native tools via LiteLLM's unified interface.
_TEXT_ONLY_PROVIDERS: frozenset[str] = frozenset({"ollama", "ollama_chat"})

# Valid JSON Schema Draft 2020-12 keywords for tool input schemas.
# Anything outside this set at the top level is stripped to prevent
# Anthropic API rejections ("JSON schema is invalid").
_VALID_SCHEMA_KEYS: frozenset[str] = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "allOf",
        "oneOf",
        "not",
        "enum",
        "const",
        "default",
        "description",
        "format",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
        "if",
        "then",
        "else",
        "$defs",
        "$ref",
        "prefixItems",
        "contains",
        "patternProperties",
        "dependentRequired",
        "dependentSchemas",
        "propertyNames",
        "unevaluatedItems",
        "unevaluatedProperties",
        "$schema",
        "$id",
        "$anchor",
        "$dynamicRef",
        "$dynamicAnchor",
        "$comment",
        "$vocabulary",
        "deprecated",
        "readOnly",
        "writeOnly",
        "examples",
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
        "title",
    }
)

def _sanitize_tool_schema(
    schema: dict[str, Any] | None,
    tool_name: str = "unknown",
) -> dict[str, Any]:
    """Sanitize a tool input schema for Anthropic API compatibility.

    Ensures the schema is valid JSON Schema Draft 2020-12 by:
    1. Guaranteeing ``type`` and ``properties`` are present.
    2. Resolving ``$ref`` references from ``$defs``/``definitions`` inline.
    3. **Recursively** stripping non-JSON-Schema keys at all nesting levels.
    4. Removing empty ``required: []`` arrays (recursively).
    5. Ensuring all property values are schema objects (not bare strings).

    If the input is unsalvageable, returns a minimal valid schema.

    Args:
        schema: Raw JSON Schema dict from an MCP tool or agent capability.
        tool_name: Tool name for diagnostics when schema is replaced.
    """
    if not schema or not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    # Resolve $ref references inline so Anthropic doesn't have to handle them.
    defs = schema.get("$defs") or schema.get("definitions") or {}
    if defs:
        schema = _resolve_refs(schema, defs)

    # Recursively sanitize the entire schema tree
    schema = _deep_sanitize_schema(schema)

    # Ensure required top-level keys
    if "type" not in schema:
        schema["type"] = "object"
    if schema["type"] == "object" and "properties" not in schema:
        schema["properties"] = {}

    # Deep validation: catch remaining issues that recursive sanitization missed.
    try:
        import jsonschema

        jsonschema.validators.Draft202012Validator.check_schema(schema)
    except Exception:
        logger.warning(
            "[THINKING] Tool '%s' schema failed Draft 2020-12 validation, "
            "replacing with minimal schema. Original keys: %s",
            tool_name,
            list(schema.keys()),
        )
        schema = {"type": "object", "properties": {}}

    return schema

def _deep_sanitize_schema(node: Any) -> Any:
    """Recursively sanitize a JSON Schema node.

    At every dict level that looks like a schema object:
    - Strips keys not in ``_VALID_SCHEMA_KEYS``
    - Removes empty ``required: []``
    - Converts bare-string property values to ``{"type": "string"}``
    - Recurses into ``properties``, ``items``, ``anyOf``, ``oneOf``,
      ``allOf``, ``not``, ``additionalProperties``, ``if``/``then``/``else``,
      ``prefixItems``, ``contains``, ``patternProperties``, etc.

    Non-dict/list values pass through unchanged.
    """
    if isinstance(node, list):
        return [_deep_sanitize_schema(item) for item in node]

    if not isinstance(node, dict):
        return node

    # Strip non-JSON-Schema keys
    cleaned: dict[str, Any] = {}
    for k, v in node.items():
        if k not in _VALID_SCHEMA_KEYS:
            continue

        # Keys whose values are sub-schemas (recurse into them)
        if k in (
            "items",
            "additionalProperties",
            "not",
            "if",
            "then",
            "else",
            "contains",
            "propertyNames",
            "unevaluatedItems",
            "unevaluatedProperties",
            "contentSchema",
        ):
            if isinstance(v, dict):
                cleaned[k] = _deep_sanitize_schema(v)
            elif isinstance(v, bool):
                # `additionalProperties: false` is valid JSON Schema
                cleaned[k] = v
            else:
                cleaned[k] = v

        # Keys whose values are arrays of sub-schemas
        elif k in ("anyOf", "allOf", "oneOf", "prefixItems"):
            if isinstance(v, list):
                cleaned[k] = [_deep_sanitize_schema(item) for item in v]
            else:
                cleaned[k] = v

        # Properties: dict of name -> sub-schema
        elif k in ("properties", "patternProperties", "dependentSchemas", "$defs"):
            if isinstance(v, dict):
                sanitized_props: dict[str, Any] = {}
                for prop_name, prop_val in v.items():
                    if isinstance(prop_val, dict):
                        sanitized_props[prop_name] = _deep_sanitize_schema(prop_val)
                    elif isinstance(prop_val, str):
                        # Bare string type hint → proper schema object
                        sanitized_props[prop_name] = {"type": "string", "description": prop_name}
                    elif isinstance(prop_val, bool):
                        # `{"propName": true}` is valid (allows anything)
                        sanitized_props[prop_name] = prop_val  # type: ignore[assignment]
                    else:
                        sanitized_props[prop_name] = {"type": "string", "description": prop_name}
                cleaned[k] = sanitized_props
            else:
                cleaned[k] = v

        # `required` — remove if empty
        elif k == "required":
            if v:  # Non-empty list
                cleaned[k] = v
            # else: skip empty required arrays

        # All other valid keys: pass through as-is
        else:
            cleaned[k] = v

    return cleaned

def _resolve_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively resolve $ref pointers against a $defs dict.

    Handles ``#/$defs/Name`` and ``#/definitions/Name`` patterns.
    Unresolvable refs are replaced with ``{"type": "object"}``.
    Limits recursion depth to 10 to prevent infinite loops.
    """

    def _resolve(obj: Any, depth: int = 0) -> Any:
        if depth > 10:
            return {"type": "object"}
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_path = obj["$ref"]
                # Extract definition name from #/$defs/Name or #/definitions/Name
                for prefix in ("#/$defs/", "#/definitions/"):
                    if ref_path.startswith(prefix):
                        def_name = ref_path[len(prefix) :]
                        if def_name in defs:
                            resolved = _resolve(dict(defs[def_name]), depth + 1)
                            # Merge any sibling keys (Draft 2020-12 allows this)
                            merged = {k: v for k, v in obj.items() if k != "$ref"}
                            merged.update(resolved)
                            return merged
                # Unresolvable ref
                return {"type": "object"}
            return {k: _resolve(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve(item, depth + 1) for item in obj]
        return obj

    result = _resolve(node)
    # Remove $defs/definitions from result since refs are now inlined
    if isinstance(result, dict):
        result.pop("$defs", None)
        result.pop("definitions", None)
    return result

class OrchestrationThinkingProvider:
    """Provides LLM-based orchestration reasoning.

    Uses get_configured_llm() to respect user's LLM settings.
    """

    def __init__(
        self,
        llm: "LLM | None" = None,
        on_cost_event: Callable[[ChatEvent], None] | None = None,
    ):
        """Initialize with optional explicit LLM and cost event callback.

        Args:
            llm: Explicit LLM instance. If None, uses get_configured_llm().
            on_cost_event: Optional callback invoked with a cost_update ChatEvent
                after each LLM call.  The event contains prompt_tokens,
                completion_tokens, and total_tokens in its metadata.
        """
        self._explicit_llm = llm
        self._on_cost_event = on_cost_event
        self._last_available_agents: list[AgentCard] = []
        self._session_tier_override: "ModelTier | None" = None  # Runtime adaptive fallback
        self._cached_tools_key: tuple[str, ...] | None = None
        self._cached_tools: list[dict] | None = None

    def _get_environment_info(self, context: dict[str, Any] | None = None) -> str:
        """Get environment information for the LLM.

        Provides context about the system so the LLM can make informed decisions
        about paths, user info, etc.

        Args:
            context: Optional context dict that may contain user_id

        Returns:
            Formatted environment info string
        """
        import os
        import pwd

        lines = []

        # Get current user's home directory
        try:
            home_dir = os.path.expanduser("~")
            username = pwd.getpwuid(os.getuid()).pw_name
            lines.append(f"- Current user: {username}")
            lines.append(f"- Home directory: {home_dir}")
            lines.append(f"- Desktop path: {home_dir}/Desktop")
            lines.append(f"- Documents path: {home_dir}/Documents")
        except Exception:
            lines.append("- Home directory: Unable to determine")

        # Get current working directory
        try:
            cwd = os.getcwd()
            lines.append(f"- Working directory: {cwd}")
        except Exception:
            pass

        # Add user_id from context if available
        if context and context.get("user_id"):
            lines.append(f"- User ID: {context['user_id']}")

        return "\n".join(lines) if lines else "Environment info not available"

    def _get_llm(self) -> "LLM":
        """Get LLM instance, using user config if not explicitly set.

        When an explicit LLM was injected via __init__, returns it directly.
        Otherwise, calls get_configured_llm() fresh each time so that
        changes made on the Settings page take effect immediately without
        a container restart (same pattern as FlowPlanner.llm property).
        """
        if self._explicit_llm:
            return self._explicit_llm
        from core.providers.llm_adapter import get_configured_llm

        return get_configured_llm()

    def _supports_native_tools(self) -> bool:
        """Check if the current LLM provider supports native function calling.

        Checks are layered:
        1. Config toggle (native_tools_enabled) -- global kill switch
        2. Explicit capability method on LLM instance (future-proofing)
        3. Provider denylist -- Ollama is the only confirmed text-only provider

        The check inspects the model string prefix (e.g. 'ollama/llama3' -> 'ollama')
        to determine the provider. Models without a prefix default to 'openai'.

        Provider audit (Phase 101):
        - VLLMBaseLLM: Fixed in Phase 101 (2-path routing: CrewAI + orchestrator)
        - LiteLLM (via litellm.completion): Returns tool_calls natively;
          _call_llm dict handler catches and converts via _convert_tool_calls_to_json
        - local_connector: Connection test / model discovery only, no LLM calls
        - adk_adapter: Uses its own litellm tool-calling loop (_MAX_TOOL_ITERATIONS)
        - agents/llm.py: Factory only, delegates to VLLMBaseLLM or CrewAI LLM
        """
        from core.orchestrator.config import get_orchestration_config

        config = get_orchestration_config()
        if not config.native_tools_enabled:
            logger.info(
                "[THINKING] Native tool calling disabled via config (native_tools_enabled=False)"
            )
            return False

        llm = self._get_llm()
        # Check for explicit capability method first (future-proofing)
        if hasattr(llm, "supports_function_calling"):
            return llm.supports_function_calling()
        # Use explicit provider attribute (set by llm.py factory)
        provider = getattr(llm, "dryade_provider", None)
        if provider is None:
            # Backward compat: extract from model string
            model = getattr(llm, "model", "") or ""
            provider = model.split("/")[0].lower() if "/" in model else ""
        return provider not in _TEXT_ONLY_PROVIDERS

    def _is_vllm_model(self) -> bool:
        """Check if the current LLM is a vLLM-served model.

        Checks dryade_provider attribute first, then falls back to
        class name (VLLMBaseLLM) or model string prefix (vllm/).
        """
        llm = self._get_llm()
        provider = getattr(llm, "dryade_provider", None)
        if provider == "vllm":
            return True
        # Backward compat fallbacks
        if "vllm" in type(llm).__name__.lower():
            return True
        model_str = getattr(llm, "model", "") or ""
        return model_str.lower().startswith("vllm/")

    def _downgrade_tier_for_session(self) -> None:
        """Downgrade the effective tier for this session after a tool-calling failure.

        On first call, reads the current auto-detected tier from ModelDetector.
        Each subsequent call drops one level: FRONTIER -> STRONG -> MODERATE -> WEAK.
        WEAK is the floor -- calling this at WEAK is a no-op.

        The downgrade is stored on this provider instance (_session_tier_override),
        NOT in the global ModelDetector cache, so it is session-scoped.
        """
        from core.orchestrator.model_detection import ModelDetector, get_model_detector

        current = self._session_tier_override
        if current is None:
            # First downgrade: get current tier from detector
            llm = self._get_llm()
            provider_hint = getattr(llm, "dryade_provider", None)
            profile = get_model_detector().get_model_tier(llm, provider_hint=provider_hint)
            current = profile.tier

        new_tier = ModelDetector.downgrade_tier(current)
        if new_tier != current:
            logger.warning(
                "[THINKING] Runtime tier downgrade: %s -> %s (tool-calling failure detected)",
                current.value,
                new_tier.value,
            )
            self._session_tier_override = new_tier

    def _build_tools_for_agents(self, agents: list[AgentCard]) -> list[dict] | None:
        """Build OpenAI-format tool definitions from agent capabilities, with caching.

        Cache key is a sorted tuple of agent names. Within a single orchestrate()
        call chain, the agent set is stable, so the cache avoids rebuilding
        the same tool list on every ReAct iteration.

        Args:
            agents: List of AgentCard objects with capabilities.

        Returns:
            List of tool dicts in OpenAI format, or None if no tools found.
        """
        agent_key = tuple(sorted(a.name for a in agents))
        if self._cached_tools_key == agent_key:
            logger.debug("[THINKING] Tool list cache hit (%d agents)", len(agents))
            return self._cached_tools

        tools: list[dict] = []
        for agent in agents:
            for cap in getattr(agent, "capabilities", []) or []:
                cap_name = cap.name if hasattr(cap, "name") else str(cap)
                cap_desc = cap.description if hasattr(cap, "description") else ""
                input_schema = cap.input_schema if hasattr(cap, "input_schema") else None
                # Sanitize schema for Anthropic API compatibility (SDK 0.73+).
                # Handles missing type/properties, $ref resolution, invalid
                # property values, and non-JSON-Schema keys (recursively).
                parameters = _sanitize_tool_schema(input_schema, tool_name=cap_name)

                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": cap_name,
                            "description": cap_desc or f"Tool from {agent.name}",
                            "parameters": parameters,
                        },
                    }
                )

        result = tools if tools else None
        self._cached_tools_key = agent_key
        self._cached_tools = result
        logger.debug("[THINKING] Tool list cache miss, built %d tools", len(tools))
        return result

    def _filter_agents_by_router(
        self,
        agents: list[AgentCard],
        router_hints: list[dict] | None,
        max_servers: int = 5,
    ) -> list[AgentCard]:
        """Filter agent list using router's server recommendations.

        Non-MCP agents (CrewAI, LangGraph, etc.) are always included --
        they have no individual tools to filter and may be needed for delegation.

        MCP agents are included only if their server appeared in the router results.

        When no MCP agents survive filtering, returns a bounded fallback set
        (general-purpose agents + up to MAX_FALLBACK_AGENTS) instead of all agents.
        """
        # Collect non-MCP agents (always included)
        non_mcp: list[AgentCard] = [a for a in agents if a.framework.value != "mcp"]
        mcp_agents: list[AgentCard] = [a for a in agents if a.framework.value == "mcp"]

        # If no router hints, use bounded fallback instead of returning all agents
        if not router_hints:
            if not mcp_agents:
                return non_mcp
            fallback = self._bounded_mcp_fallback(mcp_agents)
            logger.info(
                "[THINKING] Router filter: no hints available, using %d general-purpose MCP agents "
                "(bounded from %d total)",
                len(fallback),
                len(mcp_agents),
            )
            return non_mcp + fallback

        # Extract unique server names from router hints, capped at max_servers
        hint_servers: set[str] = set()
        for h in router_hints:
            server = h.get("server", "")
            if server:
                hint_servers.add(server)
            if len(hint_servers) >= max_servers:
                break

        # Filter MCP agents by router-recommended servers
        matched_mcp: list[AgentCard] = [a for a in mcp_agents if a.name in hint_servers]

        # If no MCP agents survived filtering, use bounded fallback (NOT all agents)
        if not matched_mcp and mcp_agents:
            fallback = self._bounded_mcp_fallback(mcp_agents)
            logger.info(
                "[THINKING] Router filter: no MCP agents matched hints %s, "
                "using %d general-purpose agents (bounded from %d total)",
                hint_servers,
                len(fallback),
                len(mcp_agents),
            )
            return non_mcp + fallback

        filtered = non_mcp + matched_mcp
        if len(filtered) < len(agents):
            logger.info(
                f"[THINKING] Router filter: {len(agents)} agents -> {len(filtered)} "
                f"(servers: {hint_servers})"
            )
        return filtered

    @staticmethod
    def _bounded_mcp_fallback(mcp_agents: list[AgentCard]) -> list[AgentCard]:
        """Return a bounded set of general-purpose MCP agents for fallback.

        Prefers agents in GENERAL_PURPOSE_AGENTS, then fills up to
        MAX_FALLBACK_AGENTS from the full MCP agent list.
        """
        fallback: list[AgentCard] = []
        remaining: list[AgentCard] = []

        for agent in mcp_agents:
            if agent.name in GENERAL_PURPOSE_AGENTS:
                fallback.append(agent)
            else:
                remaining.append(agent)

        # Fill up to MAX_FALLBACK_AGENTS if general-purpose set is too small
        slots_left = MAX_FALLBACK_AGENTS - len(fallback)
        if slots_left > 0:
            fallback.extend(remaining[:slots_left])

        return fallback

    async def _call_llm(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ) -> tuple[str, str | None]:
        """Call LLM and return response content and optional reasoning.

        Runs the synchronous LLM call in a thread to avoid blocking the event loop.
        After each call, extracts token usage and emits a cost_update event
        via the on_cost_event callback (if set).

        Uses the request queue to bound concurrent LLM requests and prevent
        connection pool exhaustion (BUG-011).

        Returns:
            Tuple of (content, reasoning_content).
            reasoning_content is None if no reasoning was provided.
        """

        from core.extensions.request_queue import get_request_queue

        # Acquire a slot from the request queue before making the LLM call.
        # This prevents unbounded concurrent requests from exhausting httpx
        # connection pools and causing backend unhealthiness.
        queue = get_request_queue()
        acquired = await queue.acquire()
        if not acquired:
            raise RuntimeError(
                "LLM request queue full or timeout - server overloaded, please retry"
            )

        try:
            return await self._call_llm_inner(messages, tools=tools)
        finally:
            await queue.release()

    async def _call_llm_inner(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ) -> tuple[str, str | None]:
        """Inner LLM call implementation (called after queue slot acquired)."""
        import asyncio

        llm = self._get_llm()

        # Snapshot cumulative token usage before the call so we can
        # compute a per-call delta afterwards.  CrewAI LLM (and its
        # BaseLLM subclasses) track cumulative usage in _token_usage.
        usage_before: dict[str, int] | None = None
        if hasattr(llm, "_token_usage") and isinstance(llm._token_usage, dict):
            usage_before = dict(llm._token_usage)

        # Compute prompt size for fallback estimation
        prompt_char_len = sum(len(m.get("content", "")) for m in messages)

        # Run sync LLM call in thread to avoid blocking event loop
        if hasattr(llm, "call"):
            call_kwargs: dict[str, Any] = {"messages": messages}
            if tools:
                # Dump tool schemas for debugging schema validation errors.
                # Writes to /tmp/dryade-tools-debug.json on every LLM call
                # so the last failing payload is always inspectable.
                try:
                    import json as _json
                    from pathlib import Path

                    Path("/tmp/dryade-tools-debug.json").write_text(
                        _json.dumps(
                            [
                                {
                                    "index": i,
                                    "name": t.get("function", {}).get("name", "?"),
                                    "parameters": t.get("function", {}).get("parameters", {}),
                                }
                                for i, t in enumerate(tools)
                            ],
                            indent=2,
                        )
                    )
                except Exception:
                    pass
                call_kwargs["tools"] = tools
            response = await asyncio.to_thread(llm.call, **call_kwargs)
        elif hasattr(llm, "invoke"):
            response = await asyncio.to_thread(llm.invoke, messages)
        else:
            response = await asyncio.to_thread(lambda: str(llm.generate([messages])))

        # Handle dict response from vLLM reasoning models
        reasoning_content = None
        if isinstance(response, dict):
            # --- vLLM response validation for dict path (Phase 118.2) ---
            from core.orchestrator.config import get_orchestration_config

            _cfg = get_orchestration_config()
            if _cfg.vllm_validator_enabled and self._is_vllm_model():
                from core.orchestrator.vllm_validator import VLLMResponseValidator

                _available_tools: list[str] | None = None
                if tools:
                    _available_tools = [
                        t.get("function", {}).get("name", "") for t in tools if t.get("function")
                    ]
                _validator = VLLMResponseValidator(available_tools=_available_tools)
                _vresult = _validator.validate(response)
                if _vresult.repaired:
                    logger.info(f"[THINKING] vLLM dict response repaired: {_vresult.failure_mode}")
                    if _vresult.repaired_tool_calls:
                        response["tool_calls"] = _vresult.repaired_tool_calls
                    if _vresult.repaired_content is not None:
                        response["content"] = _vresult.repaired_content
                elif not _vresult.valid:
                    logger.warning(
                        f"[THINKING] vLLM dict response invalid: {_vresult.failure_mode}"
                    )
                    self._emit_cost_from_llm(llm, usage_before, prompt_char_len, "")
                    return (
                        f"[VLLM_ERROR:{_vresult.failure_mode}] Response validation failed",
                        response.get("reasoning_content"),
                    )

            # Handle native tool calling responses (vLLM function calling)
            if response.get("tool_calls"):
                try:
                    content = self._convert_tool_calls_to_json(response)
                    reasoning_content = response.get("reasoning_content") or response.get(
                        "reasoning"
                    )
                    self._emit_cost_from_llm(llm, usage_before, prompt_char_len, content)
                    return content, reasoning_content
                except (TypeError, AttributeError) as e:
                    # Malformed tool_calls structure -- downgrade tier for next iteration
                    if tools:
                        self._downgrade_tier_for_session()
                        logger.warning("[THINKING] Tool-call failure (exception): %s", e)
                    raise

            # Handle reasoning model responses
            reasoning_content = response.get("reasoning_content") or response.get("reasoning")
            content = response.get("content", "")
            if reasoning_content:
                logger.debug(
                    f"[THINKING] Received reasoning from LLM: {reasoning_content[:100]}..."
                )

            # Runtime adaptive fallback: detect tool-calling failure in dict responses
            if tools:
                _dict_content = response.get("content")
                _dict_tool_calls = response.get("tool_calls")
                if _dict_content is None and not _dict_tool_calls:
                    # Model returned nothing useful when tools were expected
                    self._downgrade_tier_for_session()
                    logger.warning("[THINKING] Tool-call failure: content=None, no tool_calls")
        elif isinstance(response, str):
            content = response
        else:
            content = str(response)

        json_content = self._extract_json_from_response(content)
        self._emit_cost_from_llm(llm, usage_before, prompt_char_len, content)

        # Runtime adaptive fallback: detect tool-calling failure in string/content path
        if tools and isinstance(content, str):
            _stripped = content.strip()
            if _stripped == "" or _stripped.startswith("[VLLM_ERROR:"):
                self._downgrade_tier_for_session()
                logger.warning(
                    "[THINKING] Tool-call failure: empty/error content with tools requested"
                )

        # --- vLLM response validation for string/content path (Phase 118.2) ---
        from core.orchestrator.config import get_orchestration_config

        _cfg_str = get_orchestration_config()
        if _cfg_str.vllm_validator_enabled and self._is_vllm_model():
            from core.orchestrator.vllm_validator import VLLMResponseValidator

            _available_tools_str: list[str] | None = None
            if tools:
                _available_tools_str = [
                    t.get("function", {}).get("name", "") for t in tools if t.get("function")
                ]
            _validator_str = VLLMResponseValidator(available_tools=_available_tools_str)
            _validator_input = {
                "content": json_content,
                "reasoning_content": reasoning_content,
                "tool_calls": None,
            }
            _vresult_str = _validator_str.validate(_validator_input)
            if _vresult_str.repaired:
                logger.info(
                    f"[THINKING] vLLM response repaired: failure_mode={_vresult_str.failure_mode}"
                )
                if _vresult_str.repaired_content is not None:
                    json_content = _vresult_str.repaired_content
                if _vresult_str.repaired_tool_calls:
                    import json as _json_mod

                    json_content = _json_mod.dumps(_vresult_str.repaired_tool_calls)
            elif not _vresult_str.valid:
                logger.warning(
                    f"[THINKING] vLLM response invalid: failure_mode={_vresult_str.failure_mode}"
                )
                return (
                    f"[VLLM_ERROR:{_vresult_str.failure_mode}] Response validation failed",
                    reasoning_content,
                )

        return json_content, reasoning_content

    async def _stream_llm(
        self,
        messages: list[dict],
        on_token: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
        merge_thinking: bool = False,
    ) -> tuple[str, str, int]:
        """Stream LLM response token-by-token.

        Like _call_llm() but delivers tokens incrementally via callbacks.
        Falls back to _call_llm() + single token burst if streaming fails.

        Handles both VLLMBaseLLM (via astream()) and LiteLLM (via
        litellm.acompletion(stream=True)).  For vLLM reasoning models,
        routes reasoning_content to on_thinking and content to on_token.

        Uses the request queue to bound concurrent LLM requests (BUG-011).

        Args:
            messages: Chat messages for the LLM.
            on_token: Callback for content tokens.
            on_thinking: Callback for reasoning/thinking tokens.
            cancel_event: When set, streaming stops gracefully.
            merge_thinking: When True, reasoning tokens are treated as content
                (routed to on_token and accumulated in full_content). Use for
                INSTANT tier where models may return the answer in
                reasoning_content instead of content.

        Returns:
            Tuple of (full_accumulated_content, full_accumulated_reasoning, estimated_completion_tokens).
        """
        from core.extensions.request_queue import get_request_queue

        queue = get_request_queue()
        acquired = await queue.acquire()
        if not acquired:
            raise RuntimeError(
                "LLM request queue full or timeout - server overloaded, please retry"
            )
        try:
            return await self._stream_llm_inner(
                messages,
                on_token=on_token,
                on_thinking=on_thinking,
                cancel_event=cancel_event,
                merge_thinking=merge_thinking,
            )
        finally:
            await queue.release()

    async def _stream_llm_inner(
        self,
        messages: list[dict],
        on_token: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
        merge_thinking: bool = False,
    ) -> tuple[str, str, int]:
        """Inner streaming implementation (called after queue slot acquired)."""
        llm = self._get_llm()
        full_content = ""
        full_reasoning = ""

        try:
            if hasattr(llm, "astream"):
                # VLLMBaseLLM path - uses native async streaming
                async for chunk in llm.astream(messages, enable_thinking=True):
                    if cancel_event and cancel_event.is_set():
                        break

                    if isinstance(chunk, dict):
                        if chunk.get("type") == "reasoning":
                            if merge_thinking:
                                # Treat reasoning as content (INSTANT tier)
                                token = chunk.get("content", "")
                                if token:
                                    full_content += token
                                    if on_token:
                                        on_token(token)
                            else:
                                full_reasoning += chunk.get("content", "")
                                if on_thinking:
                                    on_thinking(chunk["content"])
                        else:
                            # Content tokens -> on_token
                            token = chunk.get("content", "")
                            if token:
                                full_content += token
                                if on_token:
                                    on_token(token)
                    elif isinstance(chunk, str):
                        # Backward-compatible plain string yield
                        if chunk:
                            full_content += chunk
                            if on_token:
                                on_token(chunk)
            else:
                # LiteLLM path - extract connection info from CrewAI LLM wrapper
                import litellm

                model = getattr(llm, "model", None) or getattr(llm, "model_name", "unknown")
                api_key = getattr(llm, "api_key", None)
                base_url = getattr(llm, "base_url", None) or getattr(llm, "api_base", None)

                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                }
                if api_key:
                    kwargs["api_key"] = api_key
                if base_url:
                    kwargs["base_url"] = base_url

                response = await litellm.acompletion(**kwargs)
                async for chunk in response:
                    if cancel_event and cancel_event.is_set():
                        break

                    choices = getattr(chunk, "choices", None) or []
                    if choices:
                        delta = choices[0].delta
                        # Handle reasoning_content (vLLM reasoning models via LiteLLM)
                        reasoning_token = getattr(delta, "reasoning_content", None)
                        if reasoning_token:
                            if merge_thinking:
                                full_content += reasoning_token
                                if on_token:
                                    on_token(reasoning_token)
                            else:
                                full_reasoning += reasoning_token
                                if on_thinking:
                                    on_thinking(reasoning_token)
                        # Handle content tokens
                        token = getattr(delta, "content", None) or ""
                        if token:
                            full_content += token
                            if on_token:
                                on_token(token)

        except Exception as e:
            # Connection errors: don't fall back to _call_llm (it will also fail)
            if hasattr(e, "error_type") and e.error_type in ("timeout", "connection", "network"):
                logger.warning(
                    f"[THINKING] Streaming failed due to connection error ({e.error_type}), not retrying"
                )
                raise
            logger.exception("[THINKING] Streaming failed, falling back to blocking call")
            # Fallback: blocking _call_llm_inner() + emit as single burst.
            # Use _inner to avoid re-acquiring the request queue slot (already held).
            # Preserve any partial content already accumulated during streaming.
            content, reasoning = await self._call_llm_inner(messages)
            if reasoning:
                if merge_thinking:
                    full_content += reasoning + (content or "")
                    if on_token:
                        on_token(reasoning)
                else:
                    full_reasoning += reasoning
                    if on_thinking:
                        on_thinking(reasoning)
            if content and on_token:
                on_token(content)
            if content and not merge_thinking:
                full_content += content

        # Estimate completion tokens from accumulated content (~4 chars/token)
        est_tokens = max(1, len(full_content) // 4) if full_content else 0
        return full_content, full_reasoning, est_tokens

    def _emit_cost_from_llm(
        self,
        llm: Any,
        usage_before: dict[str, int] | None,
        prompt_char_len: int,
        content: str,
    ) -> None:
        """Extract token usage from the LLM and emit a cost_update event.

        Tries three strategies in order:
        1. Delta from CrewAI's cumulative _token_usage (real counts).
        2. Direct usage attribute on the response (future-proofing).
        3. Character-length estimation (~4 chars per token) as fallback.

        Args:
            llm: The LLM instance that was just called.
            usage_before: Snapshot of _token_usage before the call, or None.
            prompt_char_len: Total character length of prompt messages.
            content: The response content string.
        """
        if not self._on_cost_event:
            return

        prompt_tokens = 0
        completion_tokens = 0

        # Strategy 1: Compute delta from CrewAI's cumulative tracking
        if usage_before is not None and hasattr(llm, "_token_usage"):
            usage_after = llm._token_usage
            prompt_tokens = usage_after.get("prompt_tokens", 0) - usage_before.get(
                "prompt_tokens", 0
            )
            completion_tokens = usage_after.get("completion_tokens", 0) - usage_before.get(
                "completion_tokens", 0
            )

        # Strategy 2 (fallback): Estimate from character length
        # ~4 characters per token is a common heuristic for English text
        if prompt_tokens <= 0 and completion_tokens <= 0:
            prompt_tokens = max(1, prompt_char_len // 4)
            completion_tokens = max(1, len(content) // 4) if content else 0
            logger.debug(
                f"[THINKING] Using estimated token counts: "
                f"prompt={prompt_tokens}, completion={completion_tokens}"
            )

        if prompt_tokens > 0 or completion_tokens > 0:
            cost_event = emit_cost_update(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            try:
                self._on_cost_event(cost_event)
            except Exception:
                logger.debug("[THINKING] Failed to emit cost_update event", exc_info=True)

    def _extract_json_from_response(self, content: str | None) -> str:
        """Extract JSON from LLM response, handling various formats.

        Handles:
        - Markdown code blocks (```json ... ``` or ``` ... ```)
        - Raw JSON objects { ... }
        - Text before/after JSON
        - None input (returns empty string)
        """

        if content is None:
            return ""
        content = content.strip()

        # Try markdown code blocks first
        if "```json" in content:
            parts = content.split("```json")
            if len(parts) > 1:
                json_part = parts[1].split("```")[0]
                return json_part.strip()

        if "```" in content:
            parts = content.split("```")
            if len(parts) > 1:
                json_part = parts[1].split("```")[0]
                return json_part.strip()

        # Try to find JSON object in the content
        # Look for { ... } pattern, handling nested braces
        brace_start = content.find("{")
        if brace_start != -1:
            depth = 0
            for i, char in enumerate(content[brace_start:], start=brace_start):
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return content[brace_start : i + 1].strip()

        # No JSON found, return as-is (will fail JSON parsing with informative error)
        return content.strip()

    def _parse_thinking_json(self, content: str, reasoning: str | None) -> dict:
        """Parse JSON from LLM response, falling back to reasoning_content.

        vLLM reasoning models sometimes put the structured JSON response
        inside reasoning_content instead of content. This method tries
        content first, then falls back to extracting JSON from reasoning.

        Args:
            content: The primary content string from _call_llm.
            reasoning: The reasoning_content string from _call_llm (may be None).

        Returns:
            Parsed dict from the JSON response.

        Raises:
            json.JSONDecodeError: If neither source contains valid JSON.
        """
        # Try content first (normal case)
        if content and content.strip():
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass

        # Fall back to reasoning_content (vLLM reasoning model case)
        if reasoning:
            extracted = self._extract_json_from_response(reasoning)
            if extracted:
                try:
                    parsed = json.loads(extracted)
                    logger.info("[THINKING] Recovered JSON from reasoning_content")
                    return parsed
                except json.JSONDecodeError:
                    pass

        # Neither worked -- raise with useful context
        preview = content[:200] if content else "(empty)"
        raise json.JSONDecodeError(
            f"No valid JSON in content or reasoning. Content preview: {preview}",
            content or "",
            0,
        )

    def _extract_agent_from_reasoning(
        self,
        reasoning: str,
        available_agents: list[AgentCard],
    ) -> tuple[str, str] | None:
        """Try to extract agent and task from reasoning text.

        Used as fallback when JSON parsing fails but we have LLM reasoning.
        """
        reasoning_lower = reasoning.lower()

        # Try to match agent names mentioned in reasoning
        for agent in available_agents:
            name_lower = agent.name.lower()
            # Match full name or name without mcp- prefix
            names_to_check = [name_lower]
            if name_lower.startswith("mcp-"):
                names_to_check.append(name_lower[4:])

            for name in names_to_check:
                if name not in reasoning_lower:
                    continue

                # Try to match a specific tool from capabilities
                for cap in getattr(agent, "capabilities", []) or []:
                    cap_name = cap.name if hasattr(cap, "name") else str(cap)
                    if cap_name.lower() in reasoning_lower:
                        return (agent.name, cap_name)

                # Fall back to action verb matching
                action_map = {
                    ("list", "directory"): "list_directory",
                    ("list", "dir"): "list_directory",
                    ("read", "file"): "read_file",
                    ("search",): "search_files",
                    ("find",): "search_files",
                    ("git",): "git_status",
                }
                for verbs, tool_name in action_map.items():
                    if all(v in reasoning_lower for v in verbs):
                        return (agent.name, tool_name)

                return (agent.name, f"Execute task based on reasoning: {reasoning[:200]}")

        return None

    def _fill_missing_required_params(self, tool_name: str, arguments: dict) -> dict:
        """Fill missing required parameters with sensible defaults.

        When the LLM omits required parameters from a tool call (common with
        local models like vLLM), inject reasonable defaults to prevent
        validation errors on the MCP server side.
        """
        # Known tool defaults for common MCP tools
        TOOL_DEFAULTS = {
            "git_diff": {"target": "HEAD"},
            "git_log": {"max_count": 10},
            "search_files": {"path": "."},
            "list_directory": {"path": "."},
            "read_file": {},  # no sensible default for path
        }

        defaults = TOOL_DEFAULTS.get(tool_name, {})
        filled = dict(arguments)
        injected = []

        for param, default_value in defaults.items():
            if param not in filled:
                filled[param] = default_value
                injected.append(f"{param}={default_value}")

        if injected:
            logger.warning(
                f"[THINKING] Injected missing required params for {tool_name}: "
                f"{', '.join(injected)}"
            )

        return filled

    def _convert_tool_calls_to_json(self, response: dict) -> str:
        """Convert native tool_calls response into orchestration JSON string.

        Takes the first tool call since the orchestrator executes one step at a time.
        """
        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            return ""
        tc = tool_calls[0]
        func = tc.get("function", {})
        tool_name = func.get("name", "")
        try:
            arguments = json.loads(func.get("arguments", "{}"))
        except json.JSONDecodeError:
            arguments = {}
        # BUG-004: Fill missing required parameters with sensible defaults
        arguments = self._fill_missing_required_params(tool_name, arguments)
        return json.dumps(
            {
                "reasoning": f"Native tool call: {tool_name}",
                "reasoning_summary": f"Calling {tool_name}",
                "is_final": False,
                "task": {
                    "agent_name": "",  # Resolved by _resolve_agent_for_tool in _build_task_from_data
                    "description": f"Call {tool_name}",
                    "tool": tool_name,
                    "arguments": arguments,
                },
            }
        )

    def _resolve_agent_for_tool(self, tool_name: str) -> str | None:
        """Resolve which agent owns a tool by searching available agents' capabilities."""
        for agent in self._last_available_agents:
            for cap in getattr(agent, "capabilities", []) or []:
                cap_name = cap.name if hasattr(cap, "name") else str(cap)
                if cap_name == tool_name:
                    return agent.name
        return None

    def _build_task_from_data(
        self, task_data: dict, context: dict[str, Any] | None
    ) -> OrchestrationTask:
        """Build an OrchestrationTask from parsed JSON task data."""
        agent_name = task_data.get("agent_name", "")

        # Resolve agent from tool name when agent_name is empty
        if not agent_name and task_data.get("tool"):
            agent_name = self._resolve_agent_for_tool(task_data["tool"]) or ""

        task_context = dict(context or {})
        if task_data.get("tool"):
            task_context["tool"] = task_data["tool"]
        if task_data.get("arguments"):
            task_context["arguments"] = task_data["arguments"]

        return OrchestrationTask(
            agent_name=agent_name,
            description=task_data.get("description", ""),
            context=task_context,
            is_critical=task_data.get("is_critical", False),
            tool=task_data.get("tool"),
            arguments=task_data.get("arguments", {}),
        )

    def _build_thought_from_data(
        self,
        data: dict,
        context: dict[str, Any] | None,
        external_reasoning: str | None,
    ) -> OrchestrationThought:
        """Build an OrchestrationThought from parsed JSON response data."""
        task = None
        if data.get("task"):
            task = self._build_task_from_data(data["task"], context)

        parallel_tasks = None
        if data.get("parallel_tasks"):
            parallel_tasks = [
                self._build_task_from_data(t, context) for t in data["parallel_tasks"]
            ]

        # Prefer LLM's native reasoning over JSON-structured reasoning
        reasoning = external_reasoning or data.get("reasoning", "")

        return OrchestrationThought(
            reasoning=reasoning,
            reasoning_summary=data.get("reasoning_summary"),
            is_final=data.get("is_final", False),
            needs_clarification=data.get("needs_clarification", False),
            answer=data.get("answer"),
            task=task,
            parallel_tasks=parallel_tasks,
            delegate_to=data.get("delegate_to"),
            subtask=data.get("subtask"),
        )

    async def orchestrate_think(
        self,
        goal: str,
        observations: list[OrchestrationObservation],
        available_agents: list[AgentCard],
        observation_history: "ObservationHistory",
        context: dict[str, Any] | None = None,
        lightweight: bool = False,
    ) -> OrchestrationThought:
        """Generate next orchestration action.

        Args:
            goal: What we're trying to achieve
            observations: Results from previous actions
            available_agents: Agents available for use
            context: Additional context
            observation_history: ObservationHistory for optimized context
                formatting with sliding-window summarization.
            lightweight: When True, uses compact agent roster (names and
                descriptions only) instead of full tool schemas, and
                appends LIGHTWEIGHT_AGENT_ADDENDUM to the system prompt.
                Intended for the first ReAct step where full schemas
                are unnecessary.

        Returns:
            OrchestrationThought with reasoning and next action
        """
        # --- Phase 107: Router filtering + double-definition elimination ---
        from core.orchestrator.config import get_orchestration_config

        config = get_orchestration_config()

        # --- Adaptive model-aware routing (Phase 115.4) ---
        model_profile = None
        strategy = None
        if config.adaptive_routing_enabled:
            from core.orchestrator.model_detection import ModelTier, get_model_detector
            from core.orchestrator.routing_strategy import get_strategy_for_tier

            detector = get_model_detector()

            # Allow operator override via config
            if config.model_tier_override:
                try:
                    override_tier = ModelTier(config.model_tier_override)
                    from core.orchestrator.model_detection import ModelProfile

                    model_profile = ModelProfile(
                        tier=override_tier,
                        supports_tools=override_tier != ModelTier.WEAK,
                        supports_structured_output=override_tier
                        in (ModelTier.STRONG, ModelTier.FRONTIER),
                        calibration_score=detector._tier_to_score(override_tier),
                        model_key=f"override/{config.model_tier_override}",
                    )
                except ValueError:
                    logger.warning(
                        f"[THINKING] Invalid model_tier_override: {config.model_tier_override}, "
                        "using auto-detection"
                    )

            if model_profile is None:
                _llm = self._get_llm()
                _provider_hint = getattr(_llm, "dryade_provider", None)
                model_profile = detector.get_model_tier(_llm, provider_hint=_provider_hint)

            # Apply session-scoped tier downgrade if active (runtime adaptive fallback)
            if self._session_tier_override is not None:
                from core.orchestrator.model_detection import ModelProfile

                model_profile = ModelProfile(
                    tier=self._session_tier_override,
                    supports_tools=self._session_tier_override
                    in (ModelTier.FRONTIER, ModelTier.STRONG),
                    supports_structured_output=self._session_tier_override == ModelTier.FRONTIER,
                    calibration_score=detector._tier_to_score(self._session_tier_override),
                    model_key=model_profile.model_key,
                    max_tokens=model_profile.max_tokens,
                )
                logger.warning(
                    "[THINKING] Session tier override active: %s (original: auto-detected)",
                    self._session_tier_override.value,
                )

            strategy = get_strategy_for_tier(model_profile.tier)
            logger.info(
                f"[THINKING] Model tier: {model_profile.tier.value}, "
                f"strategy: {strategy.__class__.__name__}"
            )

        # Determine if native tools will be used
        use_native = not lightweight and self._supports_native_tools()

        # Filter agents by router results (only for orchestrate_think, not plan/failure)
        router_hints = (context or {}).get("_router_hints")
        if config.router_filter_enabled:
            # _filter_agents_by_router handles both populated and None/empty hints
            # with bounded fallback (never returns all agents)
            filtered_agents = self._filter_agents_by_router(
                available_agents, router_hints, max_servers=config.router_filter_max_servers
            )
            if not router_hints:
                logger.warning(
                    "[THINKING] Router filter enabled but router_hints is empty/None. "
                    "Using bounded fallback (%d agents from %d total). "
                    "Qdrant may have empty collections -- check embedding indexing. "
                    "To disable: DRYADE_ROUTER_FILTER_ENABLED=false",
                    len(filtered_agents),
                    len(available_agents),
                )
        else:
            filtered_agents = available_agents

        if use_native:
            # Native format carries structured tool definitions.
            # System prompt only needs lightweight roster for agent awareness.
            # This eliminates the ~12,500 token XML duplication.
            agents_xml = _format_agents_xml(available_agents, lightweight=True)
        else:
            # Text-only providers: full XML schemas needed, but still filter
            agents_xml = _format_agents_xml(filtered_agents, lightweight=lightweight)

        observations_xml = observation_history.format_for_llm()
        environment_info = self._get_environment_info(context)

        # Get knowledge sources summary for system prompt (Phase 99.3)
        knowledge_sources_summary = (context or {}).get("_knowledge_sources_summary", "")
        if knowledge_sources_summary:
            knowledge_section = (
                f"## Knowledge Sources\n"
                f"You have access to {len(knowledge_sources_summary.splitlines())} "
                f"knowledge document(s):\n{knowledge_sources_summary}\n\n"
            )
        else:
            knowledge_section = ""

        system_prompt = ORCHESTRATE_SYSTEM_PROMPT.format(
            agents_xml=agents_xml,
            environment_info=environment_info,
            knowledge_section=knowledge_section,
        )
        if lightweight:
            system_prompt += LIGHTWEIGHT_AGENT_ADDENDUM

        # Memory block injection (Phase 115.3)
        if config.memory_blocks_enabled:
            conversation_id = (context or {}).get("conversation_id", "")
            if conversation_id:
                try:
                    from core.orchestrator.memory_tools import get_memory_block_store

                    memory_xml = get_memory_block_store().compile_to_prompt(conversation_id)
                    if memory_xml:
                        system_prompt += f"\n\n{memory_xml}"
                        logger.info(
                            f"[THINKING] Injected memory blocks ({len(memory_xml)} chars) "
                            f"for conversation {conversation_id[:8]}..."
                        )
                except Exception as e:
                    logger.warning(f"[THINKING] Failed to inject memory blocks: {e}")

        # Put observations in the USER message for visibility (avoids "lost in middle" problem)
        if observations:
            user_content = f"""COMPLETED ACTIONS:
{observations_xml}

Based on the completed actions above, either:
- Return is_final=true with the answer (if goal achieved)
- Or specify the next action needed

USER GOAL: {goal}"""
        else:
            user_content = f"USER GOAL: {goal}"

        # Knowledge context injection (Phase 94.1)
        knowledge_ctx = (context or {}).get("_knowledge_context")
        if knowledge_ctx:
            user_content += (
                f"\n\nRELEVANT KNOWLEDGE (use ONLY if directly related to the question — "
                f"ignore if the question can be answered from general knowledge):\n{knowledge_ctx}"
            )

        # Inject router hints on first step only (when no observations yet)
        # These are additive hints, not mandates -- the LLM may choose differently
        # router_hints already read above for filtering (Phase 107)
        if router_hints and not observations:
            hints_lines = []
            for h in router_hints[:3]:
                hints_lines.append(f"- {h['tool_name']} ({h['server']}): score={h['score']}")
            user_content += "\n\nTOOL ROUTING HINTS (semantic match):\n" + "\n".join(hints_lines)

        # Build conversation history messages for LLM context
        history_messages = []
        raw_history = (context or {}).get("history", [])
        if raw_history:
            budget = config.history_budget_chars
            used = 0
            for msg in reversed(raw_history):  # Most recent first for budget priority
                msg_len = len(msg.get("content", ""))
                if used + msg_len > budget:
                    break
                history_messages.insert(0, msg)  # Maintain chronological order
                used += msg_len
            if history_messages:
                logger.info(
                    f"[THINKING] Including {len(history_messages)} history messages "
                    f"({used} chars) in orchestration context"
                )

        messages = [
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": user_content},
        ]

        # Log what we're sending to the LLM for debugging
        logger.info(
            f"[THINKING] Prompt sizes: agents_xml={len(agents_xml)} chars, "
            f"observations_xml={len(observations_xml)} chars, "
            f"total_system_prompt={len(system_prompt)} chars"
        )
        logger.info(f"[THINKING] Observations count: {len(observations)}")
        if observations:
            logger.info(
                f"[THINKING] First observation: status={observations[0].success}, result_len={len(str(observations[0].result)) if observations[0].result else 0}"
            )

        # Store available agents for _resolve_agent_for_tool
        self._last_available_agents = available_agents

        # Build native tools for capable providers (Phase 99/107 -- native tool calling + filtering)
        native_tools: list[dict] | None = None
        if use_native:
            # Build native tools from FILTERED agent set
            native_tools = self._build_tools_for_agents(filtered_agents)
            # Phase 115.4: Apply strategy-based tool filtering
            if strategy and native_tools:
                meta_hint = (context or {}).get("_meta_action_hint", False)
                native_tools = strategy.select_tools(native_tools, meta_hint)

            if native_tools:
                total_caps = sum(
                    len(getattr(a, "capabilities", []) or []) for a in available_agents
                )
                logger.info(
                    f"[THINKING] Using native tool calling with {len(native_tools)} tools "
                    f"(filtered from {total_caps} total)"
                )
            else:
                logger.info("[THINKING] Using text-based JSON fallback (no native tools)")
        else:
            logger.info("[THINKING] Using text-based JSON fallback (no native tools)")

        # Phase 167: Always inject self-mod tools for all function-calling providers
        # (language-agnostic detection -- replaces Phase 115.1 meta_hint conditional inject).
        # Skip only for weak-tier models that can barely handle tool calling.
        meta_hint = (context or {}).get("_meta_action_hint", False)
        if native_tools is not None and config.self_mod_tools_enabled:
            is_weak = strategy is not None and strategy.should_force_fallback()
            if not is_weak:
                from core.orchestrator.self_mod_tools import get_self_mod_tools

                # Use strategy-selected variant (Phase 115.4) or "detailed" default
                variant = strategy.get_tool_description_variant() if strategy else "detailed"
                self_mod_tools = get_self_mod_tools(variant)

                # Phase 174.5: Only inject factory_create when meta_hint is active.
                # With 50+ tools visible, 8B models confuse factory_create with
                # existing domain agents (e.g., "HIPAA query" → factory_create
                # instead of healthcare agent). Memory/config tools stay always-on.
                if not meta_hint:
                    self_mod_tools = [
                        t
                        for t in self_mod_tools
                        if t.get("function", {}).get("name") != "factory_create"
                    ]

                native_tools = list(native_tools) + self_mod_tools
                logger.info(
                    f"[THINKING] Injected {len(self_mod_tools)} self-mod tools "
                    f"({'with' if meta_hint else 'without'} factory_create)"
                )
                # Signal to ComplexHandler that self-mod tools were available to the LLM
                # (used by fallback guard to suppress text-only-path fallback)
                if context is not None:
                    context["_self_mod_tools_injected"] = True

                # Enforce total tool count ceiling after self-mod tools are added.
                # The strategy cap applies to regular agent tools, but self-mod tools
                # are appended afterwards and can push the total over the intended
                # maximum. Cap at 128 to stay well within provider limits while
                # still supporting any realistic tool roster.
                _max_total_tools = 128
                if len(native_tools) > _max_total_tools:
                    native_tools = native_tools[:_max_total_tools]
                    logger.info(
                        f"[THINKING] Tool count capped at {_max_total_tools} "
                        f"(total tool count ceiling enforced)"
                    )
        elif native_tools is None:
            # Text-only provider (Ollama): native tools not available.
            # Self-mod tools require native tool calling. The fallback path in
            # ComplexHandler will handle this case via _handle_meta_action() when
            # meta_hint is active (Phase 115.2). _self_mod_tools_injected is NOT set.
            if meta_hint:
                logger.info(
                    "[THINKING] Meta-action hint active but native tools unavailable, "
                    "will rely on fallback path"
                )

        # Phase 115.4: Few-shot example injection
        # Phase 167: removed meta_hint gate -- inject whenever strategy provides examples
        _few_shot_injected = 0
        if config.few_shot_enabled and strategy and strategy.get_few_shot_count() > 0:
            from core.orchestrator.few_shot_library import get_few_shot_library

            library = get_few_shot_library()
            examples = library.get_examples(limit=strategy.get_few_shot_count())
            if examples:
                _few_shot_injected = len(examples)
                few_shot_text = library.format_for_prompt(examples)
                messages[-1]["content"] += f"\n\n{few_shot_text}"
                logger.info(
                    f"[THINKING] Injected {len(examples)} few-shot examples "
                    f"(strategy: {strategy.__class__.__name__})"
                )

        # --- Routing explainability (Phase 115.5) ---
        if config.routing_explainability_enabled:
            try:
                from core.orchestrator.explainability import (
                    build_routing_explanation,
                    format_explanation_for_log,
                )

                _tools_total = sum(
                    len(getattr(a, "capabilities", []) or []) for a in available_agents
                )
                _tools_after = len(native_tools) if native_tools else _tools_total

                explanation = build_routing_explanation(
                    model_name=model_profile.model_key if model_profile else "unknown",
                    model_tier=model_profile.tier.value if model_profile else "unknown",
                    strategy_name=strategy.__class__.__name__ if strategy else "none",
                    tools_total=_tools_total,
                    tools_after_filter=_tools_after,
                    description_variant=(
                        strategy.get_tool_description_variant() if strategy else "detailed"
                    ),
                    few_shot_count=_few_shot_injected,
                    few_shot_categories=[],
                    middleware_hooks_fired=[],
                    meta_action_hint=meta_hint,
                    feature_flags={
                        "adaptive_routing": config.adaptive_routing_enabled,
                        "middleware": config.middleware_enabled,
                        "few_shot": config.few_shot_enabled,
                        "optimization": config.optimization_enabled,
                    },
                )
                logger.debug(format_explanation_for_log(explanation))
            except Exception:
                logger.debug("[ROUTING-EXPLAIN] Failed to build explanation", exc_info=True)

        try:
            content, llm_reasoning = await self._call_llm(messages, tools=native_tools)

            # Log LLM response for debugging
            logger.info(
                f"[THINKING] LLM response preview: {content[:200] if content else '(empty)'}..."
            )

            # If LLM provided reasoning (e.g., vLLM thinking models), use it
            # Otherwise we'll use the structured reasoning from JSON response
            external_reasoning = llm_reasoning

            data = self._parse_thinking_json(content, llm_reasoning)

            # Log the parsed decision
            logger.info(
                f"[THINKING] LLM decision: is_final={data.get('is_final')}, "
                f"has_task={bool(data.get('task'))}, has_parallel={bool(data.get('parallel_tasks'))}"
            )

            return self._build_thought_from_data(data, context, external_reasoning)

        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse orchestration response as JSON: {e}\n"
                f"Raw content (first 500 chars): {content[:500] if content else '(empty)'}\n"
                f"LLM reasoning (first 500 chars): {llm_reasoning[:500] if llm_reasoning else '(none)'}"
            )

            # If we have reasoning but empty/invalid content, try to extract agent intent
            if llm_reasoning and not content:
                # Try to find an MCP agent mentioned in the reasoning
                agent_match = self._extract_agent_from_reasoning(llm_reasoning, available_agents)
                if agent_match:
                    agent_name, task_desc = agent_match
                    logger.info(
                        f"[THINKING] Extracted intent from reasoning: agent={agent_name}, task={task_desc}"
                    )
                    return OrchestrationThought(
                        reasoning=llm_reasoning,
                        reasoning_summary=f"Using {agent_name}",
                        is_final=False,
                        task=OrchestrationTask(
                            agent_name=agent_name,
                            description=task_desc,
                            context=context or {},
                            is_critical=False,
                        ),
                    )

            # Try to provide a helpful response based on what the LLM actually said
            # Some vLLM models respond conversationally instead of JSON
            if len(content) > 50 and not content.startswith("{"):
                # Check if content looks like JSON reasoning that failed to parse
                # (e.g., starts with {"reasoning" or contains "is_final")
                sanitized = content[:2000]
                if content.lstrip().startswith('{"reasoning"') or '"is_final"' in content[:500]:
                    # Try to extract just the answer field from the JSON-like content
                    try:
                        partial = json.loads(content)
                        if isinstance(partial, dict) and partial.get("answer"):
                            sanitized = partial["answer"]
                    except (json.JSONDecodeError, TypeError):
                        # Extraction failed -- use generic error instead of raw JSON
                        sanitized = (
                            "I encountered an issue processing the request. Please try rephrasing."
                        )
                # LLM gave a conversational response, use it directly
                return OrchestrationThought(
                    reasoning=llm_reasoning
                    or "LLM responded conversationally instead of structured JSON",
                    is_final=True,
                    answer=sanitized,
                )
            return OrchestrationThought(
                reasoning=llm_reasoning
                or f"Failed to parse LLM response: {content[:200] if content else '(empty)'}",
                is_final=True,
                answer="I encountered an issue processing the request. Please try rephrasing.",
            )
        except Exception as e:
            if hasattr(e, "error_type") and e.error_type in (
                "timeout",
                "connection",
                "http",
                "network",
            ):
                logger.warning(f"[THINKING] LLM connection failed ({e.error_type}): {e}")
                return OrchestrationThought(
                    reasoning=f"LLM connection error ({e.error_type}): {str(e)}",
                    is_final=True,
                    answer=(
                        "I'm unable to reach the language model service. "
                        "Please check that vLLM is running and try again."
                    ),
                )
            logger.exception(f"Orchestration thinking failed: {e}")
            return OrchestrationThought(
                reasoning=f"Error: {str(e)}",
                is_final=True,
                answer=f"Orchestration error: {type(e).__name__}",
            )

    async def failure_think(
        self,
        agent_name: str,
        task_description: str,
        error: str,
        retry_count: int,
        max_retries: int,
        is_critical: bool,
        available_agents: list[AgentCard],
        failure_depth: int = 0,
    ) -> OrchestrationThought:
        """Generate failure handling decision.

        Per user decision: Intelligent fallback - LLM decides retry/skip/escalate.

        Args:
            agent_name: Agent that failed
            task_description: What task failed
            error: Error message
            retry_count: Current retry count
            max_retries: Maximum retries allowed
            is_critical: Whether task is critical
            available_agents: Available agents for alternatives
            failure_depth: Cascading failure depth (0 = first failure).
                Higher depth biases toward more aggressive recovery
                (DECOMPOSE at 1-2, ABORT at 3+).

        Returns:
            OrchestrationThought with failure_action set
        """
        agents_xml = _format_agents_xml(available_agents)

        system_prompt = FAILURE_SYSTEM_PROMPT.format(
            agent_name=agent_name,
            task_description=task_description,
            error=error,
            retry_count=retry_count,
            max_retries=max_retries,
            is_critical=str(is_critical).lower(),
            agents_xml=agents_xml,
            failure_depth=failure_depth,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Decide how to handle this failure."},
        ]

        try:
            content, llm_reasoning = await self._call_llm(messages)
            data = self._parse_thinking_json(content, llm_reasoning)

            action_str = data.get("failure_action", "escalate").lower()
            try:
                failure_action = FailureAction(action_str)
            except ValueError:
                failure_action = FailureAction.ESCALATE

            # Prefer LLM's native reasoning over JSON-structured reasoning
            reasoning = llm_reasoning or data.get("reasoning", "")

            return OrchestrationThought(
                reasoning=reasoning,
                is_final=False,
                failure_action=failure_action,
                alternative_agent=data.get("alternative_agent"),
                escalation_question=data.get("escalation_question"),
            )

        except Exception as e:
            logger.exception(f"Failure thinking failed: {e}")
            # Default to escalation on error
            return OrchestrationThought(
                reasoning=f"Error determining failure action: {str(e)}",
                is_final=False,
                failure_action=FailureAction.ESCALATE,
                escalation_question=f"Task '{task_description}' failed with error: {error}. How would you like to proceed?",
            )

    async def manager_think(
        self,
        goal: str,
        progress: list[dict[str, Any]],
        specialists: list[AgentCard],
    ) -> OrchestrationThought:
        """Generate hierarchical manager delegation decision.

        Args:
            goal: Overall goal to achieve
            progress: Results from specialist delegations
            specialists: Available specialist agents

        Returns:
            OrchestrationThought with delegation decision
        """
        specialists_xml = _format_agents_xml(specialists)

        # Format progress
        if not progress:
            progress_xml = "<progress>No delegations yet</progress>"
        else:
            lines = ["<progress>"]
            for p in progress:
                lines.append(f'  <delegation agent="{p.get("agent", "unknown")}">')
                lines.append(f"    <task>{p.get('task', '')}</task>")
                lines.append(f"    <result>{str(p.get('result', ''))[:300]}</result>")
                lines.append(f"    <validation>{p.get('validation', 'pending')}</validation>")
                lines.append("  </delegation>")
            lines.append("</progress>")
            progress_xml = "\n".join(lines)

        system_prompt = MANAGER_SYSTEM_PROMPT.format(
            specialists_xml=specialists_xml,
            progress_xml=progress_xml,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Goal: {goal}"},
        ]

        try:
            content, llm_reasoning = await self._call_llm(messages)
            data = self._parse_thinking_json(content, llm_reasoning)

            # Prefer LLM's native reasoning over JSON-structured reasoning
            reasoning = llm_reasoning or data.get("reasoning", "")

            return OrchestrationThought(
                reasoning=reasoning,
                reasoning_summary=data.get("reasoning_summary"),
                is_final=data.get("is_final", False),
                answer=data.get("answer"),
                delegate_to=data.get("delegate_to"),
                subtask=data.get("subtask"),
            )

        except Exception as e:
            logger.exception(f"Manager thinking failed: {e}")
            return OrchestrationThought(
                reasoning=f"Error: {str(e)}",
                is_final=True,
                answer=f"Manager error: {type(e).__name__}",
            )

    # -----------------------------------------------------------------
    # Token-level streaming for final answers
    # -----------------------------------------------------------------

    async def _stream_final_answer(
        self,
        goal: str,
        observations: list[OrchestrationObservation],
        observation_history: "ObservationHistory",
        context: dict[str, Any] | None = None,
        on_token: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> tuple[str, str, int]:
        """Stream the final answer token-by-token from the LLM.

        Called instead of _call_llm() when the orchestrator already knows
        it needs a final answer (is_final=true) and the caller provided
        an on_token callback.

        Delegates to _stream_llm() with merge_thinking=False so that
        reasoning tokens go to the thinking panel (on_thinking) and content
        tokens go to the chat bubble (on_token). This prevents reasoning
        from leaking into the user-visible message.

        If the model puts the entire answer in reasoning_content (no content
        tokens at all), a fallback re-emits reasoning as content -- same
        pattern as the INSTANT tier BUG-003 fix.

        Args:
            goal: The original user goal.
            observations: Results from previous actions.
            observation_history: ObservationHistory for formatted context.
            context: Optional execution context.
            on_token: Callback invoked with each content token.
            on_thinking: Callback invoked with reasoning/thinking tokens.
            cancel_event: When set, streaming stops gracefully.

        Returns:
            Tuple of (full_accumulated_content, full_accumulated_reasoning, estimated_completion_tokens).
        """
        observations_xml = observation_history.format_for_llm()

        # Build user content with observations and goal
        user_content = ""
        if observations_xml.strip():
            user_content += f"COMPLETED ACTIONS:\n{observations_xml}\n\n"

        # Include knowledge context so the final answer has access to RAG results
        knowledge_ctx = (context or {}).get("_knowledge_context")
        if knowledge_ctx:
            user_content += (
                "RELEVANT KNOWLEDGE (use ONLY if directly related to the question — "
                f"ignore if the question can be answered from general knowledge):\n{knowledge_ctx}\n\n"
            )

        user_content += f"USER GOAL: {goal}\n\nProvide a clear, helpful response."

        messages = [
            {
                "role": "system",
                "content": FINAL_ANSWER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

        # Delegate to _stream_llm with merge_thinking=False.
        # Reasoning tokens go to on_thinking (thinking panel), content tokens
        # go to on_token (chat bubble). This prevents reasoning from leaking
        # into the user-visible message.
        # If the model puts the entire answer in reasoning_content (no content),
        # the fallback below re-emits reasoning as content.
        content, reasoning, est_tokens = await self._stream_llm(
            messages=messages,
            on_token=on_token,
            on_thinking=on_thinking,
            cancel_event=cancel_event,
            merge_thinking=False,
        )

        # Reasoning fallback: if model put entire answer in reasoning_content
        # (no content tokens at all), use reasoning as the content.
        # Same pattern as INSTANT tier BUG-003 fix.
        if not content and reasoning:
            logger.info(
                "[THINKING] Final answer: no content tokens, using reasoning as content (%d chars)",
                len(reasoning),
            )
            content = reasoning
            if on_token:
                on_token(reasoning)

        return content, reasoning, est_tokens

    # -----------------------------------------------------------------
    # Planning layer thinking methods
    # -----------------------------------------------------------------

    async def plan_think(
        self,
        goal: str,
        available_agents: list[AgentCard],
        context: dict[str, Any] | None = None,
        memory_context: str | None = None,
    ) -> ExecutionPlan:
        """Generate a DAG-based execution plan from a user goal.

        Calls the LLM with PLAN_SYSTEM_PROMPT and available agents,
        parses the response into an ExecutionPlan with PlanStep objects.

        On JSON parse failure, returns a single-step REACT fallback plan
        so the goal can still be attempted.

        Args:
            goal: Natural language goal to decompose.
            available_agents: Currently registered agents.
            context: Optional context dict (used for environment info).
            memory_context: Optional relevant memory context string.

        Returns:
            ExecutionPlan with topologically-sorted execution_order.
        """
        agents_xml = _format_agents_xml(available_agents)

        system_content = PLAN_SYSTEM_PROMPT.format(agents_xml=agents_xml)
        if context:
            env_info = self._get_environment_info(context)
            system_content += f"\n\n## Environment\n{env_info}"
        if memory_context:
            system_content += f"\n\n## Relevant Memory\n{memory_context}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Create an execution plan for: {goal}"},
        ]

        try:
            content, _reasoning = await self._call_llm(messages)
            data = self._parse_thinking_json(content, _reasoning)

            steps: list[PlanStep] = []
            for s in data.get("steps", []):
                steps.append(
                    PlanStep(
                        id=s.get("id", f"step-{len(steps) + 1}"),
                        agent_name=s.get("agent_name", ""),
                        task=s.get("task", ""),
                        depends_on=s.get("depends_on", []),
                        expected_output=s.get("expected_output", ""),
                        is_critical=s.get("is_critical", True),
                        estimated_duration_seconds=s.get("estimated_duration_seconds", 30),
                    )
                )

            if not steps:
                raise ValueError("LLM returned zero steps")

            plan = ExecutionPlan(
                id=str(uuid4()),
                goal=goal,
                steps=steps,
            )
            plan.compute_execution_order()

            logger.info(
                f"[THINKING] Plan generated: {len(steps)} steps, "
                f"{len(plan.execution_order)} waves, "
                f"est {plan.total_estimated_seconds}s"
            )
            return plan

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(
                f"[THINKING] Plan generation failed ({type(e).__name__}: {e}), "
                "falling back to single-step REACT plan"
            )
            # Fallback: single-step plan that runs the goal through the ReAct loop
            fallback_step = PlanStep(
                id="step-1",
                agent_name="",  # Let the base orchestrator pick
                task=goal,
                is_critical=True,
                estimated_duration_seconds=60,
            )
            plan = ExecutionPlan(
                id=str(uuid4()),
                goal=goal,
                steps=[fallback_step],
            )
            plan.compute_execution_order()
            return plan

    async def replan_think(
        self,
        original_plan: ExecutionPlan,
        failed_steps: list[PlanStep],
        completed_results: dict[str, Any],
        available_agents: list[AgentCard],
        context: dict[str, Any] | None = None,
    ) -> ExecutionPlan | None:
        """Revise an execution plan after step failures.

        Generates a new plan that preserves completed work and works
        around failed steps.  Returns None if replanning fails.

        Args:
            original_plan: The plan that encountered failures.
            failed_steps: Steps that failed during execution.
            completed_results: Dict of step_id -> result for completed steps.
            available_agents: Currently registered agents.
            context: Optional context dict.

        Returns:
            New ExecutionPlan or None if replanning failed.
        """
        _ = context  # Reserved for future environment injection
        agents_xml = _format_agents_xml(available_agents)

        # Build completed steps summary
        completed_ids = [s.id for s in original_plan.steps if s.status == StepStatus.COMPLETED]
        completed_steps_str = ", ".join(completed_ids) if completed_ids else "none"

        # Build failed steps summary
        failed_ids = [s.id for s in failed_steps]
        failed_steps_str = ", ".join(failed_ids) if failed_ids else "none"

        # Build completed results (truncated)
        results_lines = []
        for step_id, result in completed_results.items():
            result_str = str(result)[:500]
            results_lines.append(f"- {step_id}: {result_str}")
        completed_results_str = "\n".join(results_lines) if results_lines else "none"

        # Build failure details
        failure_lines = []
        for step in failed_steps:
            failure_lines.append(f"- {step.id}: {step.error or 'Unknown error'}")
        failure_details_str = "\n".join(failure_lines) if failure_lines else "none"

        system_content = REPLAN_SYSTEM_PROMPT.format(
            goal=original_plan.goal,
            completed_steps=completed_steps_str,
            failed_steps=failed_steps_str,
            completed_results=completed_results_str,
            failure_details=failure_details_str,
            agents_xml=agents_xml,
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "Create a revised execution plan."},
        ]

        try:
            content, _reasoning = await self._call_llm(messages)
            data = self._parse_thinking_json(content, _reasoning)

            steps: list[PlanStep] = []
            for s in data.get("steps", []):
                step_id = s.get("id", f"replan-{len(steps) + 1}")
                step = PlanStep(
                    id=step_id,
                    agent_name=s.get("agent_name", ""),
                    task=s.get("task", ""),
                    depends_on=s.get("depends_on", []),
                    expected_output=s.get("expected_output", ""),
                    is_critical=s.get("is_critical", True),
                    estimated_duration_seconds=s.get("estimated_duration_seconds", 30),
                )
                # Preserve completed status for steps carried over
                if step_id in completed_ids:
                    step.status = StepStatus.COMPLETED
                    step.result = completed_results.get(step_id)
                steps.append(step)

            if not steps:
                return None

            new_plan = ExecutionPlan(
                id=str(uuid4()),
                goal=original_plan.goal,
                steps=steps,
                replan_count=original_plan.replan_count + 1,
            )
            new_plan.compute_execution_order()

            logger.info(
                f"[THINKING] Replan #{new_plan.replan_count}: "
                f"{len(steps)} steps, {len(new_plan.execution_order)} waves"
            )
            return new_plan

        except Exception as e:
            logger.warning(
                f"[THINKING] Replanning failed ({type(e).__name__}: {e}), returning None to abort"
            )
            return None

    async def judge_think(
        self,
        tool_output: str,
        task_description: str,
        tool_name: str = "",
        task_context: str = "",
    ) -> dict:
        """Evaluate tool output quality using LLM-as-judge.

        Calls a (potentially smaller/cheaper) LLM to score tool output
        against 4 quality dimensions: intent, grounding, completeness,
        and tool_appropriateness.

        Uses judge_model from config when available, otherwise falls
        back to the main model.

        Args:
            tool_output: The string representation of the tool's result.
            task_description: What the task was supposed to accomplish.
            tool_name: Name of the tool that produced the output.
            task_context: Additional context (truncated) for grounding.

        Returns:
            Parsed dict with "scores" list and "overall_summary".

        Raises:
            json.JSONDecodeError: If LLM response cannot be parsed.
            Exception: On LLM call failure (caller should handle gracefully).
        """
        # Truncate tool output to avoid blowing context budget
        truncated_output = tool_output[:4000] if len(tool_output) > 4000 else tool_output
        truncated_context = task_context[:2000] if len(task_context) > 2000 else task_context

        system_prompt = JUDGE_SYSTEM_PROMPT.format(
            task_description=task_description,
            tool_name=tool_name or "unknown",
            task_context=truncated_context or "No additional context",
            tool_output=truncated_output,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Evaluate the tool output quality."},
        ]

        # Use judge-specific model if configured.
        # IMPORTANT: Do NOT mutate self._explicit_llm -- it's shared across
        # concurrent async callers. Instead, create a local LLM instance
        # and call it directly via asyncio.to_thread, bypassing _call_llm.
        from core.orchestrator.config import get_orchestration_config

        cfg = get_orchestration_config()

        if cfg.judge_model:
            try:
                from crewai import LLM

                local_judge_llm = LLM(model=cfg.judge_model)
                raw_response = await asyncio.to_thread(local_judge_llm.call, messages)
                content = raw_response if isinstance(raw_response, str) else str(raw_response)
                data = self._parse_thinking_json(content, "")
                return data
            except Exception as e:
                logger.warning(
                    "[THINKING] Judge model '%s' failed, falling back to main model: %s",
                    cfg.judge_model,
                    e,
                )
                # Fall through to use main model via _call_llm

        content, llm_reasoning = await self._call_llm(messages)
        data = self._parse_thinking_json(content, llm_reasoning)
        return data

    async def synthesize_think(
        self,
        goal: str,
        step_results: dict[str, Any],
        on_token: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> str:
        """Combine multi-step results into a coherent final answer.

        When *on_token* is provided the synthesis is streamed token-by-token
        via ``_stream_llm()`` so the frontend receives incremental output.
        Without *on_token* the method falls back to the blocking
        ``_call_llm()`` path for backward compatibility.

        Args:
            goal: The original user goal.
            step_results: Dict of step_id -> result string.
            on_token: Optional callback invoked with each content token
                during streaming synthesis.
            on_thinking: Optional callback invoked with reasoning/thinking
                tokens (vLLM reasoning models).
            cancel_event: When set, streaming stops gracefully.

        Returns:
            Synthesized answer as free text.
        """
        results_lines = []
        for step_id, result in step_results.items():
            result_str = str(result)[:1000]
            results_lines.append(f"### {step_id}\n{result_str}")
        step_results_str = "\n\n".join(results_lines) if results_lines else "No results."

        system_content = SYNTHESIZE_SYSTEM_PROMPT.format(
            goal=goal,
            step_results=step_results_str,
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "Synthesize the results into a final answer."},
        ]

        if on_token:
            # Stream synthesis token-by-token.
            # merge_thinking=True ensures reasoning models (vLLM) that put
            # the answer in reasoning_content still route it to on_token
            # (main content area) instead of only on_thinking.
            content, _reasoning, est_tokens = await self._stream_llm(
                messages=messages,
                on_token=on_token,
                on_thinking=on_thinking,
                cancel_event=cancel_event,
                merge_thinking=True,
            )
            # Emit cost estimate for the streaming call
            if self._on_cost_event:
                prompt_char_len = sum(len(m.get("content", "")) for m in messages)
                prompt_tokens = max(1, prompt_char_len // 4)
                cost_event = emit_cost_update(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=est_tokens,
                )
                try:
                    self._on_cost_event(cost_event)
                except Exception:
                    pass
            return content
        else:
            # Blocking fallback for callers without streaming
            content, _reasoning = await self._call_llm(messages)
            return content
