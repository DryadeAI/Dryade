"""Dynamic Flow Planner - LLM-generated execution flows.

Analyzes user prompts and available agents to generate optimal execution plans.
Uses the same FlowDefinition schema as static YAML flows for unified execution.

Target: ~200 LOC
"""

import json
import logging
from typing import Any

import httpx

from core.adapters import list_agents
from core.domains.base import FlowConfig
from core.ee.plugin_capabilities import PluginCapability, get_capability_registry
from core.mcp.registry import get_registry
from core.orchestrator.models import ExecutionPlan, PlanNode

logger = logging.getLogger("dryade.planner")

class LLMUnavailableError(Exception):
    """Raised when the LLM backend is unreachable or timed out.

    This is an infrastructure error, NOT a plan generation failure.
    Callers should return HTTP 503 to the user, not a fake fallback plan.
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error

async def _get_clarification_from_plugin(
    user_request: str,
    capabilities: list[dict],
) -> dict | None:
    """Query clarification plugin if available.

    Calls the plugin API unconditionally — the plugin's own route-level
    route-level auth handles access control. The planner
    does not make tier-based feature decisions.

    Returns:
        - dict from plugin API (form schema) when clarification is needed
        - None if no plugin, insufficient tier (403), or error (proceed with best-guess)
    """
    registry = get_capability_registry()
    providers = registry.get_providers(PluginCapability.CLARIFICATION_PROVIDER)

    if not providers:
        return None

    provider = providers[0]
    api_endpoint = provider.api_endpoint  # e.g., "/api/clarify"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:8000{api_endpoint}/form/generate",
                json={
                    "user_request": user_request,
                    "clarification_questions": [],
                    "capabilities": capabilities,
                },
                timeout=30.0,
            )
            if response.status_code == 200:
                return response.json()
            # 403 = tier insufficient, other errors = plugin issue
            # Either way, proceed with best-guess LLM plan
            if response.status_code == 403:
                logger.debug(
                    "[PLANNER] Clarification plugin returned 403 (tier insufficient), skipping"
                )
            else:
                logger.debug(
                    f"[PLANNER] Clarification plugin returned {response.status_code}, skipping"
                )
            return None
    except Exception:
        # On any error, proceed with best-guess silently
        return None

class FlowPlanner:
    """Generates execution flows from natural language prompts.

    Uses LLM to analyze:
    - User intent
    - Available agents and their capabilities
    - Optimal execution order
    - Dependencies between tasks
    """

    def __init__(self, llm=None):
        """Initialize the flow planner.

        Args:
            llm: Optional LLM instance. If None, will be lazily initialized.
        """
        self._llm = llm

    @property
    def llm(self):
        """Get an LLM instance for the current request.

        If an explicit LLM was passed to __init__, return it directly.
        Otherwise, create a fresh instance every time so it picks up the
        current user's LLM configuration from contextvars (set by
        LLMContextMiddleware). Caching the auto-created instance would
        use stale config (e.g. wrong base_url) when the user changes
        their provider/endpoint in Settings.
        """
        if self._llm is not None:
            return self._llm

        from core.config import get_settings
        from core.providers.llm_adapter import get_configured_llm

        settings = get_settings()
        # Plan generation needs more time - use planner-specific timeout
        timeout = settings.llm_planner_timeout
        llm = get_configured_llm(timeout=timeout)
        logger.debug(f"[PLANNER] Created LLM with {timeout}s timeout for plan generation")
        return llm

    @staticmethod
    def _extract_json_text(response_text: str) -> str:
        """Extract JSON from LLM response, handling think tags and markdown."""
        # Handle thinking tags (common in reasoning models like DeepSeek, Qwen)
        if "<think>" in response_text and "</think>" in response_text:
            response_text = response_text.split("</think>")[-1].strip()
        # Handle markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        # Try to find JSON object if response has preamble text
        response_text = response_text.strip()
        if not response_text.startswith("{"):
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                response_text = response_text[start_idx : end_idx + 1]
        return response_text.strip()

    @staticmethod
    def _safe_json_loads(text: str) -> dict:
        """Parse JSON with tolerance for control characters.

        Small models (Ministral-8B) produce unescaped newlines/tabs inside
        JSON string values which cause ``json.JSONDecodeError``.
        Falls back to ``strict=False`` parsing.
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # strict=False allows control characters in strings
            return json.loads(text, strict=False)

    def get_available_capabilities(self) -> list[dict[str, Any]]:
        """Get all available agents and their tools.

        For MCP agents, also fetches the actual MCP tool definitions
        (name + required parameters) from the registry so the LLM
        can generate tool/arguments fields in plan nodes.
        """
        logger.info("[PLANNER] Fetching available agents and capabilities")
        cards = list_agents()
        capabilities = []

        for card in cards:
            cap_dict: dict[str, Any] = {
                "agent": card.name,
                "description": card.description,
                "tools": [
                    {"name": cap.name, "description": cap.description}
                    for cap in (card.capabilities or [])
                ],
                "framework": card.framework.value if card.framework else "crewai",
            }

            # For MCP agents, enrich with actual tool definitions from the registry
            if card.framework and card.framework.value == "mcp":
                mcp_tools = self._get_mcp_tools_for_agent(card.name)
                if mcp_tools:
                    cap_dict["tools"] = mcp_tools

            capabilities.append(cap_dict)

        logger.info(
            f"[PLANNER] Found {len(capabilities)} available agents: {[c['agent'] for c in capabilities]}"
        )
        return capabilities

    @staticmethod
    def _get_mcp_tools_for_agent(agent_name: str) -> list[dict[str, Any]]:
        """Fetch MCP tool definitions for an agent from the registry.

        Derives the server name by stripping the 'mcp-' prefix.
        Returns a list of {name, required_params} dicts, or an empty
        list if the server is not running or unreachable.
        """
        server_name = agent_name.removeprefix("mcp-")
        try:
            registry = get_registry()
            if not registry.is_registered(server_name):
                return []
            tools = registry.list_tools(server_name)
            return [
                {
                    "name": tool.name,
                    "required_params": list(tool.inputSchema.required),
                }
                for tool in tools
            ]
        except Exception as e:
            logger.debug(f"[PLANNER] Could not fetch MCP tools for '{agent_name}': {e}")
            return []

    def _build_planning_prompt(self, user_request: str, capabilities: list[dict]) -> str:
        """Build the prompt for plan generation."""
        # Separate domain agents from MCP tool agents for clear guidance
        domain_agents = [c for c in capabilities if c.get("framework") != "mcp"]
        mcp_agents = [c for c in capabilities if c.get("framework") == "mcp"]

        domain_json = json.dumps(domain_agents, indent=2) if domain_agents else "[]"
        mcp_json = json.dumps(mcp_agents, indent=2) if mcp_agents else "[]"

        agent_names = [c["agent"] for c in capabilities]
        agent_names_str = ", ".join(f'"{n}"' for n in agent_names)

        return f"""You are an execution planner. Given a user request and available agents, generate an optimal execution plan.

## Domain Agents (intelligent, use for the actual work)
These agents understand their domain and handle complex tasks autonomously. ALWAYS prefer these for the core task.
{domain_json}

## MCP Tool Agents (low-level, use ONLY for infrastructure/prerequisites)
These are raw tool wrappers. Use them ONLY for prerequisite steps like locating files, listing directories, or reading data that a domain agent needs as input. NEVER use an MCP agent when a domain agent covers the same area.
Example: use mcp-filesystem to find a file path, then pass that path to a domain agent for processing.
{mcp_json}

## User Request
{user_request}

## Instructions
1. Analyze what the user wants to accomplish
2. ALWAYS prefer domain agents for the core task — they are intelligent and autonomous
3. Use MCP agents ONLY for prerequisite steps (finding files, gathering data) that feed into domain agents
4. NEVER use an mcp-* agent when a domain agent covers the same capability (e.g. prefer the domain agent over the raw MCP agent for coverage analysis)
5. Define the execution order (consider dependencies between steps)
6. For each step, specify which agent, what task, and what it depends on

If the request is ambiguous, make reasonable assumptions and proceed with a best-guess plan.

## CRITICAL: Agent Names
You MUST use EXACT agent names from the list above. The valid agent names are:
{agent_names_str}
Do NOT invent or modify agent names. Copy them exactly as shown.

## CRITICAL: MCP Agent Tool & Arguments
For MCP agents (names starting with "mcp-"), you MUST specify:
- "tool": the EXACT tool name from the agent's tools list above
- "arguments": a dict with the required parameters for that tool
- Use "{{{{{{"step_N"}}}}}}" syntax in argument values to reference outputs from previous steps
For domain agents (non-MCP), OMIT "tool" and "arguments" — they handle routing internally.

## Output Format (JSON only, no markdown)
{{
  "name": "plan_name",
  "description": "Brief description of what this plan accomplishes",
  "reasoning": "Why you chose this approach",
  "confidence": 0.0-1.0,
  "nodes": [
    {{
      "id": "step_1",
      "agent": "exact_agent_name_from_list_above",
      "task": "Detailed task description for the agent",
      "depends_on": [],
      "expected_output": "What this step should produce",
      "tool": "exact_tool_name (REQUIRED for mcp-* agents, omit for domain agents)",
      "arguments": {{"param1": "value1"}}
    }}
  ]
}}

Generate the execution plan:"""

    async def generate_plan(
        self, user_request: str, context: dict[str, Any] | None = None
    ) -> ExecutionPlan | dict:
        """Generate an execution plan from user request.

        Args:
            user_request: Natural language description of what to do
            context: Optional context (conversation history, state, etc.)

        Returns:
            ExecutionPlan with ordered nodes, or dict with form from clarification.
        """
        logger.info(f"[PLANNER] Starting plan generation for request: {user_request[:100]}...")

        capabilities = self.get_available_capabilities()

        if not capabilities:
            logger.warning("[PLANNER] No agents available, returning empty plan")
            return ExecutionPlan.from_nodes(
                name="empty_plan",
                description="No agents available",
                nodes=[],
                reasoning="No agents registered in the system",
                confidence=0.0,
            )

        # Check for clarification plugin first (Team/Enterprise only)
        plugin_result = await _get_clarification_from_plugin(user_request, capabilities)
        if plugin_result is not None:
            # Safety: never let an upgrade_prompt block plan generation
            if isinstance(plugin_result, dict) and plugin_result.get("upgrade_prompt"):
                logger.warning(
                    "[PLANNER] Ignoring upgrade_prompt from clarification plugin "
                    "(should not block plan generation)"
                )
            else:
                # Plugin returned actual form schema from Team/Enterprise clarification
                return plugin_result

        # No clarification plugin or plugin returned None - generate best-guess plan
        logger.info(f"[PLANNER] Building planning prompt with {len(capabilities)} agents")

        # Guard against prompt overflow on small-context models (e.g. 8K).
        # Estimate tokens at ~4 chars/token. If the prompt would exceed 70%
        # of the model's max context, progressively truncate each agent's
        # tool list until it fits.
        max_context_tokens = 8192  # conservative default
        try:
            llm = self.llm
            # Try to get the model's context window (NOT max_tokens which is output limit)
            # Priority: _max_model_len (vLLM cached) > num_ctx > context_length
            for attr in ("_max_model_len", "num_ctx", "context_length"):
                val = getattr(llm, attr, None)
                if val and isinstance(val, int) and val > 0:
                    max_context_tokens = val
                    break
            else:
                # Fallback: try querying vLLM for max_model_len
                if hasattr(llm, "_get_max_model_len"):
                    val = llm._get_max_model_len()
                    if val and isinstance(val, int) and val > 0:
                        max_context_tokens = val
        except Exception:
            pass

        budget_chars = int(max_context_tokens * 4 * 0.70)  # 70% of context in chars
        prompt = self._build_planning_prompt(user_request, capabilities)

        if len(prompt) > budget_chars and capabilities:
            logger.warning(
                f"[PLANNER] Prompt too large ({len(prompt)} chars, budget {budget_chars}). "
                "Truncating tool lists to fit model context."
            )
            # Progressively trim tools from each agent until prompt fits
            trimmed = [dict(c) for c in capabilities]
            # First pass: cap each agent's tools at 5
            max_tools = 5
            while len(prompt) > budget_chars and max_tools >= 0:
                for cap in trimmed:
                    tools = cap.get("tools", [])
                    if len(tools) > max_tools:
                        cap["tools"] = tools[:max_tools]
                prompt = self._build_planning_prompt(user_request, trimmed)
                if len(prompt) <= budget_chars:
                    break
                max_tools -= 1

            # Second pass: if still too large, drop MCP agents entirely
            if len(prompt) > budget_chars:
                trimmed = [c for c in trimmed if c.get("framework") != "mcp"]
                prompt = self._build_planning_prompt(user_request, trimmed)

            logger.info(
                f"[PLANNER] Prompt trimmed to {len(prompt)} chars "
                f"({len(trimmed)} agents, budget {budget_chars})"
            )

        logger.debug(f"[PLANNER] Prompt length: {len(prompt)} characters")

        messages = [{"role": "user", "content": prompt}]
        if context and "history" in context:
            logger.info(
                f"[PLANNER] Including {len(context['history'])} messages from conversation history"
            )
            messages = context["history"] + messages

        logger.info("[PLANNER] Calling LLM for plan generation")

        # Call LLM with error handling
        # Infrastructure errors (connectivity, timeout) are raised as LLMUnavailableError
        # so the route handler can return HTTP 503 instead of a fake plan.
        try:
            response = self.llm.call(messages)
            logger.debug(f"[PLANNER] LLM response length: {len(str(response))} characters")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error(f"[PLANNER] ✗ LLM unreachable: {type(e).__name__}: {e}", exc_info=True)
            raise LLMUnavailableError(
                f"LLM service is unavailable ({type(e).__name__}). "
                "Please check that the LLM server is running and reachable.",
                original_error=e,
            ) from e
        except TimeoutError as e:
            from core.config import get_settings

            timeout = get_settings().llm_planner_timeout
            logger.error(f"[PLANNER] ✗ LLM call timed out after {timeout} seconds")
            raise LLMUnavailableError(
                f"LLM request timed out after {timeout} seconds. "
                "The LLM server may be overloaded or unresponsive.",
                original_error=e,
            ) from e
        except Exception as e:
            logger.error(f"[PLANNER] ✗ LLM call failed: {type(e).__name__}: {e}", exc_info=True)
            raise LLMUnavailableError(
                f"LLM call failed unexpectedly: {type(e).__name__}: {e}",
                original_error=e,
            ) from e

        # Parse LLM response
        try:
            # Handle dict response from reasoning models (vLLM returns {reasoning_content, content})
            if isinstance(response, dict):
                logger.info(
                    "[PLANNER] Response is dict (reasoning model), extracting content field"
                )
                if "reasoning_content" in response:
                    logger.debug(
                        f"[PLANNER] Reasoning: {str(response.get('reasoning_content', ''))[:200]}..."
                    )
                response_text = response.get("content", "")
            else:
                response_text = str(response)

            logger.info(f"[PLANNER] LLM response content (first 500 chars): {response_text[:500]}")

            response_text = self._extract_json_text(response_text)
            plan_data = self._safe_json_loads(response_text)

            nodes = [PlanNode(**n) for n in plan_data.get("nodes", [])]
            plan = ExecutionPlan.from_nodes(
                name=plan_data.get("name", "unnamed_plan"),
                description=plan_data.get("description", ""),
                nodes=nodes,
                reasoning=plan_data.get("reasoning", ""),
                confidence=plan_data.get("confidence", 0.0),
            )

            logger.info(f"[PLANNER] ✓ Generated plan '{plan.name}' with {len(plan.nodes)} nodes")
            logger.info(f"[PLANNER] Plan description: {plan.description}")
            logger.info(f"[PLANNER] Plan reasoning: {plan.reasoning}")
            logger.info(f"[PLANNER] Plan confidence: {plan.confidence:.2f}")

            for i, node in enumerate(plan.nodes, 1):
                deps_str = f", depends on: {node.depends_on}" if node.depends_on else ""
                logger.info(f"[PLANNER]   Node {i}: {node.id} -> {node.agent}{deps_str}")
                logger.debug(f"[PLANNER]     Task: {node.task[:100]}...")

            return plan

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Fallback: create simple sequential plan
            logger.error(f"[PLANNER] ✗ Failed to parse LLM response: {str(e)}")
            logger.warning(
                f"[PLANNER] Response text after extraction: {response_text[:300] if response_text else 'empty'}..."
            )
            logger.warning("[PLANNER] Using fallback plan with single agent")

            fallback = ExecutionPlan.from_nodes(
                name="fallback_plan",
                description=f"Execute request: {user_request[:50]}...",
                nodes=[
                    PlanNode(
                        id="step_1",
                        agent=capabilities[0]["agent"] if capabilities else "unknown",
                        task=user_request,
                        expected_output="Task result",
                    )
                ],
                reasoning=f"LLM parsing failed: {str(e)}. Using fallback.",
                confidence=0.3,
            )

            logger.info(f"[PLANNER] Fallback plan: 1 node using agent '{fallback.nodes[0].agent}'")
            return fallback

    async def modify_plan(
        self,
        existing_plan: ExecutionPlan,
        modification_request: str,
        context: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """Modify an existing execution plan based on user feedback.

        Sends the current plan structure + the user's modification request to the LLM,
        which returns an updated plan preserving unchanged parts.

        Args:
            existing_plan: The current plan to modify
            modification_request: What the user wants changed
            context: Optional context (conversation history, etc.)

        Returns:
            Updated ExecutionPlan
        """
        logger.info(
            f"[PLANNER] Modifying plan '{existing_plan.name}' based on: "
            f"{modification_request[:100]}..."
        )

        capabilities = self.get_available_capabilities()

        # For modify_plan: only include agent names and brief descriptions, skip tools
        # This drastically reduces prompt size
        capabilities_brief = [
            {"agent": c["agent"], "framework": c.get("framework", ""), "description": c.get("description", "")[:100]}
            for c in capabilities
        ]
        capabilities_json = json.dumps(capabilities_brief, indent=2)

        agent_names = [c["agent"] for c in capabilities]
        agent_names_str = ", ".join(f'"{n}"' for n in agent_names)

        # Serialize existing plan for the LLM
        existing_plan_json = json.dumps(
            {
                "name": existing_plan.name,
                "description": existing_plan.description,
                "nodes": [
                    {
                        "id": n.id,
                        "agent": n.agent,
                        "task": n.task,
                        "depends_on": n.depends_on,
                        "expected_output": n.expected_output,
                        **({"tool": n.tool} if n.tool else {}),
                        **({"arguments": n.arguments} if n.arguments else {}),
                    }
                    for n in existing_plan.nodes
                ],
            },
            indent=2,
        )

        prompt = f"""You are an execution planner. You have an existing plan and the user wants modifications.

## Available Agents and Tools
{capabilities_json}

## Current Plan
{existing_plan_json}

## User's Modification Request
{modification_request}

## Instructions
1. Apply the user's requested changes to the existing plan
2. Preserve parts of the plan that are NOT affected by the change
3. Update dependencies if the modification affects execution order
4. Keep the same plan name unless the change fundamentally alters the plan's purpose

## CRITICAL: Agent Names
You MUST use EXACT agent names from the list above. The valid agent names are:
{agent_names_str}
Do NOT invent or modify agent names. Copy them exactly as shown.

## CRITICAL: MCP Agent Tool & Arguments
For MCP agents (names starting with "mcp-"), you MUST specify:
- "tool": the EXACT tool name from the agent's tools list above
- "arguments": a dict with the required parameters for that tool
For domain agents (non-MCP), OMIT "tool" and "arguments".

## Output Format (JSON only, no markdown)
{{
  "name": "plan_name",
  "description": "Updated description",
  "reasoning": "What was changed and why",
  "confidence": 0.0-1.0,
  "nodes": [
    {{
      "id": "step_1",
      "agent": "exact_agent_name_from_list_above",
      "task": "Detailed task description",
      "depends_on": [],
      "expected_output": "What this step should produce",
      "tool": "exact_tool_name (REQUIRED for mcp-* agents, omit for domain agents)",
      "arguments": {{"param1": "value1"}}
    }}
  ]
}}

Generate the modified execution plan:"""

        messages = [{"role": "user", "content": prompt}]
        if context and "history" in context:
            messages = context["history"][-6:] + messages

        try:
            response = self.llm.call(messages)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMUnavailableError(
                f"LLM service is unavailable ({type(e).__name__}).",
                original_error=e,
            ) from e
        except Exception as e:
            raise LLMUnavailableError(
                f"LLM call failed: {type(e).__name__}: {e}",
                original_error=e,
            ) from e

        # Parse response
        try:
            if isinstance(response, dict):
                response_text = response.get("content", "")
            else:
                response_text = str(response)

            response_text = self._extract_json_text(response_text)
            plan_data = self._safe_json_loads(response_text)

            nodes = [PlanNode(**n) for n in plan_data.get("nodes", [])]
            modified_plan = ExecutionPlan.from_nodes(
                name=plan_data.get("name", "unnamed_plan"),
                description=plan_data.get("description", ""),
                nodes=nodes,
                reasoning=plan_data.get("reasoning", ""),
                confidence=plan_data.get("confidence", 0.0),
            )

            logger.info(
                f"[PLANNER] Modified plan '{modified_plan.name}' "
                f"with {len(modified_plan.nodes)} nodes"
            )
            return modified_plan

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"[PLANNER] Failed to parse modified plan: {e}")
            logger.warning("[PLANNER] Returning original plan unchanged")
            return existing_plan

    def plan_to_flow(self, plan: ExecutionPlan) -> FlowConfig:
        """Convert ExecutionPlan to FlowConfig for unified execution.

        NOTE (GAP-P6/P13): Currently unused in production. Plan execution uses
        _execute_plan_background() in plans.py directly. Kept for potential
        future execution unification. The scenario execution pipeline
        (workflow_scenarios.py) is the primary execution path.
        """
        logger.info(f"[PLANNER] Converting plan '{plan.name}' to FlowConfig")

        nodes = []
        edges = []

        for node in plan.nodes:
            nodes.append(
                {
                    "id": node.id,
                    "type": "task",
                    "agent": node.agent,
                    "task": node.task,
                }
            )

            for dep in node.depends_on:
                edges.append(
                    {
                        "source": dep,
                        "target": node.id,
                    }
                )
                logger.debug(f"[PLANNER]   Added edge: {dep} -> {node.id}")

        flow = FlowConfig(
            name=plan.name,
            description=plan.description,
            nodes=nodes,
            edges=edges,
        )

        logger.info(
            f"[PLANNER] ✓ Created FlowConfig with {len(nodes)} nodes and {len(edges)} edges"
        )
        return flow

    async def validate_plan(self, plan: ExecutionPlan) -> tuple[bool, list[str]]:
        """Validate that a plan can be executed with enhanced checks.

        Returns:
            (is_valid, list of issues)
        """
        logger.info(f"[PLANNER] Validating plan '{plan.name}' with enhanced validation")

        issues = []
        warnings = []
        agent_cards = list_agents()
        available_agents = {card.name: card for card in agent_cards}
        logger.debug(f"[PLANNER] Available agents for validation: {list(available_agents.keys())}")

        # 1. Check depth limit (max 20 nodes)
        MAX_NODES = 20
        if len(plan.nodes) > MAX_NODES:
            issue = f"Plan exceeds maximum depth: {len(plan.nodes)} nodes (max {MAX_NODES})"
            issues.append(issue)
            logger.error(f"[PLANNER] ✗ Validation issue: {issue}")
        elif len(plan.nodes) > 15:
            warning = f"Plan has {len(plan.nodes)} nodes (>15), may be complex to execute"
            warnings.append(warning)
            logger.warning(f"[PLANNER] ⚠ Validation warning: {warning}")

        # 2. Check agent availability
        for node in plan.nodes:
            if node.agent not in available_agents:
                issue = f"Agent '{node.agent}' not found"
                issues.append(issue)
                logger.warning(f"[PLANNER] ✗ Validation issue: {issue}")

            # Check dependencies exist
            for dep in node.depends_on:
                if not any(n.id == dep for n in plan.nodes):
                    issue = f"Dependency '{dep}' not found for node '{node.id}'"
                    issues.append(issue)
                    logger.warning(f"[PLANNER] ✗ Validation issue: {issue}")

        # 3. Check for circular dependencies
        visited = set()

        def has_cycle(node_id: str, path: set) -> bool:
            if node_id in path:
                return True
            if node_id in visited:
                return False
            visited.add(node_id)
            path.add(node_id)
            node = next((n for n in plan.nodes if n.id == node_id), None)
            if node:
                for dep in node.depends_on:
                    if has_cycle(dep, path.copy()):
                        return True
            return False

        for node in plan.nodes:
            if has_cycle(node.id, set()):
                issue = f"Circular dependency detected involving '{node.id}'"
                issues.append(issue)
                logger.error(f"[PLANNER] ✗ Validation issue: {issue}")
                break

        # 4. Tool compatibility checking (best-effort)
        # Extract likely tool requirements from task descriptions
        for node in plan.nodes:
            if node.agent in available_agents:
                card = available_agents[node.agent]
                task_lower = node.task.lower()

                # Check for common tool patterns
                tool_requirements = []
                if "file" in task_lower or "read" in task_lower or "write" in task_lower:
                    tool_requirements.append("file_operations")
                if "search" in task_lower or "query" in task_lower:
                    tool_requirements.append("search")
                if "api" in task_lower or "http" in task_lower or "request" in task_lower:
                    tool_requirements.append("http")
                if "database" in task_lower or "sql" in task_lower:
                    tool_requirements.append("database")

                # Check if agent has any capabilities
                if tool_requirements and not card.capabilities:
                    warning = f"Node '{node.id}' requires tools ({', '.join(tool_requirements)}) but agent '{node.agent}' has no listed capabilities"
                    warnings.append(warning)
                    logger.warning(f"[PLANNER] ⚠ Validation warning: {warning}")

        # 5. Cost estimation (approximate based on node count)
        # Assume ~$0.01 per node execution (rough estimate)
        estimated_cost = len(plan.nodes) * 0.01
        if estimated_cost > 0.50:
            warning = f"Estimated cost: ${estimated_cost:.2f} (high complexity plan with {len(plan.nodes)} nodes)"
            warnings.append(warning)
            logger.warning(f"[PLANNER] ⚠ Cost estimation: {warning}")

        # 6. Check for potential timeout issues
        # Plans with >10 nodes may take significant time
        if len(plan.nodes) > 10:
            warning = f"Plan has {len(plan.nodes)} nodes, may take several minutes to execute"
            warnings.append(warning)
            logger.warning(f"[PLANNER] ⚠ Execution time warning: {warning}")

        # Log warnings
        if warnings:
            logger.info(f"[PLANNER] Plan has {len(warnings)} warnings (non-blocking):")
            for warning in warnings:
                logger.info(f"[PLANNER]   ⚠ {warning}")

        is_valid = len(issues) == 0
        if is_valid:
            logger.info(f"[PLANNER] ✓ Plan validation passed ({len(warnings)} warnings)")
        else:
            logger.error(f"[PLANNER] ✗ Plan validation failed with {len(issues)} issues")
            for issue in issues:
                logger.error(f"[PLANNER]   - {issue}")

        return is_valid, issues

    def suggest_alternative_agent(self, unavailable_agent: str, _task: str) -> str | None:
        """Suggest an alternative agent when the requested one is unavailable.

        Args:
            unavailable_agent: The agent that couldn't be used
            _task: The task description

        Returns:
            Alternative agent name or None
        """
        logger.info(f"[PLANNER] Looking for alternative to agent '{unavailable_agent}'")

        # Get all available agents
        agent_cards = list_agents()
        if not agent_cards:
            logger.warning("[PLANNER] No agents available for alternative suggestion")
            return None

        # Simple heuristic: pick the first available agent
        # In a more sophisticated implementation, could use LLM to match capabilities
        alternative = agent_cards[0].name
        logger.info(f"[PLANNER] Suggesting alternative agent: '{alternative}'")

        return alternative

    async def simplify_plan(self, plan: ExecutionPlan, reason: str = "") -> ExecutionPlan:
        """Simplify a complex plan by reducing nodes or dependencies.

        Args:
            plan: The plan to simplify
            reason: Reason for simplification (e.g., "too many nodes")

        Returns:
            Simplified plan
        """
        logger.info(f"[PLANNER] Simplifying plan '{plan.name}': {reason}")

        if len(plan.nodes) <= 3:
            logger.warning("[PLANNER] Plan already simple (≤3 nodes), no simplification needed")
            return plan

        # Strategy: Keep only nodes without dependencies (parallel execution)
        # or nodes with minimal dependencies
        simplified_nodes = []

        # First pass: keep nodes with no dependencies
        for node in plan.nodes:
            if not node.depends_on:
                simplified_nodes.append(node)

        # If we got nothing, take first 3 nodes and clear dependencies
        if not simplified_nodes:
            logger.warning("[PLANNER] All nodes have dependencies, taking first 3 nodes")
            simplified_nodes = plan.nodes[:3]
            for node in simplified_nodes:
                node.depends_on = []

        # Limit to 5 nodes maximum
        simplified_nodes = simplified_nodes[:5]

        simplified_plan = ExecutionPlan.from_nodes(
            name=f"{plan.name}_simplified",
            description=f"Simplified version: {plan.description}",
            nodes=simplified_nodes,
            reasoning=f"Simplified from {len(plan.nodes)} to {len(simplified_nodes)} nodes due to: {reason}",
            confidence=max(0.0, plan.confidence - 0.2),  # Lower confidence for simplified plan
        )

        logger.info(
            f"[PLANNER] ✓ Simplified plan from {len(plan.nodes)} to {len(simplified_nodes)} nodes"
        )
        return simplified_plan

    async def retry_node(self, node: PlanNode, error: str, _plan: ExecutionPlan) -> PlanNode | None:
        """Generate a retry strategy for a failed node.

        Args:
            node: The node that failed
            error: Error message from the failure
            _plan: The full plan for context

        Returns:
            Modified node for retry or None if retry not recommended
        """
        logger.info(f"[PLANNER] Generating retry strategy for node '{node.id}'")
        logger.debug(f"[PLANNER] Error: {error}")

        # Check error type for retry strategy
        error_lower = error.lower()

        # Transient errors: retry with same configuration
        if any(
            keyword in error_lower
            for keyword in ["timeout", "connection", "temporary", "unavailable"]
        ):
            logger.info("[PLANNER] Transient error detected, recommending direct retry")
            return node

        # Agent not found: suggest alternative
        if "not found" in error_lower or "unavailable" in error_lower:
            alternative = self.suggest_alternative_agent(node.agent, node.task)
            if alternative:
                logger.info(f"[PLANNER] Agent unavailable, suggesting alternative: {alternative}")
                retry_node = PlanNode(
                    id=f"{node.id}_retry",
                    agent=alternative,
                    task=node.task,
                    depends_on=node.depends_on,
                    expected_output=node.expected_output,
                )
                return retry_node

        # Tool/capability errors: simplify task
        if any(keyword in error_lower for keyword in ["tool", "capability", "permission"]):
            logger.info("[PLANNER] Tool/capability error, recommending task simplification")
            # Could modify task description to be simpler, but for now just log
            logger.warning(f"[PLANNER] Manual intervention may be needed for node '{node.id}'")
            return None

        # Unknown error: recommend manual review
        logger.warning("[PLANNER] Unknown error type, manual review recommended")
        return None

# Global planner instance
_planner: FlowPlanner | None = None

def get_planner() -> FlowPlanner:
    """Get or create global planner instance."""
    global _planner
    if _planner is None:
        _planner = FlowPlanner()
    return _planner

async def generate_execution_plan(
    user_request: str, context: dict[str, Any] | None = None
) -> ExecutionPlan | dict:
    """Convenience function to generate a plan.

    Returns:
        ExecutionPlan with ordered nodes, or dict from plugin.
    """
    planner = get_planner()
    return await planner.generate_plan(user_request, context)
