"""Rule-based and LLM-driven config generation for the Agent Factory.

Two-tier architecture:
  1. Fast path: keyword matching via select_framework() for clear-cut goals.
  2. LLM fallback: select_framework_llm() for ambiguous goals, plus
     framework-specific config enrichment via generate_config().

All LLM calls have rule-based fallbacks so config generation never fails
even when the LLM is unavailable.
"""

import logging
import re

from core.factory._llm import call_llm_json
from core.factory.models import _VALID_FRAMEWORKS

logger = logging.getLogger(__name__)

__all__ = ["select_framework", "select_framework_llm", "generate_config"]

# ---------------------------------------------------------------------------
# Keyword sets for rule-based framework selection (priority order)
# ---------------------------------------------------------------------------

_TOOL_KEYWORDS = frozenset(
    {"tool", "function", "utility", "convert", "calculate", "parse", "format", "validate"}
)
_SKILL_KEYWORDS = frozenset(
    {"skill", "prompt", "instruction", "guide", "template", "checklist", "procedure"}
)
_WORKFLOW_KEYWORDS = frozenset(
    {"workflow", "pipeline", "state machine", "multi-step", "orchestrate", "chain"}
)
_COLLAB_KEYWORDS = frozenset({"team", "collaborate", "roles", "crew", "delegation", "multi-agent"})
_GOOGLE_KEYWORDS = frozenset({"google", "gemini", "vertex", "gcp", "adk"})
_SERVER_KEYWORDS = frozenset({"server", "api", "endpoint", "service", "daemon", "background"})

# Stop words stripped during name derivation
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "for",
        "of",
        "in",
        "on",
        "at",
        "by",
        "with",
        "and",
        "or",
        "is",
        "it",
        "that",
        "this",
        "be",
        "do",
        "create",
        "build",
        "make",
        "write",
    }
)

# Name pattern from CreationRequest
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

# Word extraction for name derivation
_WORD_RE = re.compile(r"[a-z0-9]+")

# ---------------------------------------------------------------------------
# Static fallback: common MCP package names
# ---------------------------------------------------------------------------

_COMMON_PACKAGES: dict[str, str] = {
    "websearch": "@anthropic/brave-search",
    "web_search": "@anthropic/brave-search",
    "brave": "@anthropic/brave-search",
    "filesystem": "@anthropic/filesystem",
    "files": "@anthropic/filesystem",
    "git": "@anthropic/git",
    "github": "@anthropic/github",
    "memory": "@anthropic/memory",
    "postgres": "@anthropic/postgres",
    "sqlite": "@anthropic/sqlite",
    "puppeteer": "@anthropic/puppeteer",
    "browser": "@anthropic/puppeteer",
    "fetch": "@anthropic/fetch",
    "context7": "context7",
}

# ---------------------------------------------------------------------------
# Rule-based framework selection (fast path)
# ---------------------------------------------------------------------------

def select_framework(goal: str) -> tuple[str, str, str]:
    """Select artifact type and framework from the goal using keyword matching.

    Priority order: tool -> skill -> google -> workflow -> collab -> default.
    For tools, distinguishes mcp_function vs mcp_server based on server keywords.

    Args:
        goal: Natural-language description of what to create.

    Returns:
        Tuple of (artifact_type_str, framework, reasoning) where artifact_type_str
        is one of "agent", "tool", or "skill".
    """
    lower = goal.lower()
    words = set(lower.split())

    # Also check for multi-word keywords (e.g. "state machine", "multi-step")
    # by scanning the full lowered string
    def _has_keyword(kws: frozenset[str]) -> bool:
        for kw in kws:
            if " " in kw:
                if kw in lower:
                    return True
            elif kw in words:
                return True
        return False

    # 1. Tool detection (highest priority for explicit tool requests)
    if _has_keyword(_TOOL_KEYWORDS):
        if _has_keyword(_SERVER_KEYWORDS):
            return ("tool", "mcp_server", f"Keyword match: server-style tool in '{goal}'")
        return ("tool", "mcp_function", f"Keyword match: function tool in '{goal}'")

    # 2. Skill detection
    if _has_keyword(_SKILL_KEYWORDS):
        return ("skill", "skill", f"Keyword match: skill in '{goal}'")

    # 3. Google/ADK detection
    if _has_keyword(_GOOGLE_KEYWORDS):
        return ("agent", "adk", f"Keyword match: Google/ADK in '{goal}'")

    # 4. Workflow/pipeline detection -> langchain (state graph)
    if _has_keyword(_WORKFLOW_KEYWORDS):
        return ("agent", "langchain", f"Keyword match: workflow/pipeline in '{goal}'")

    # 5. Collaboration/crew detection -> crewai
    if _has_keyword(_COLLAB_KEYWORDS):
        return ("agent", "crewai", f"Keyword match: collaboration/crew in '{goal}'")

    # 6. Standalone server detection (server goals without explicit tool keywords)
    if _has_keyword(_SERVER_KEYWORDS):
        return ("tool", "mcp_server", f"Keyword match: server/API in '{goal}'")

    # 7. Default: custom agent
    return ("agent", "custom", f"No keyword match, defaulting to custom agent for '{goal}'")

# ---------------------------------------------------------------------------
# LLM-based framework selection (fallback for ambiguous goals)
# ---------------------------------------------------------------------------

async def select_framework_llm(goal: str) -> tuple[str, str, str]:
    """Select framework using LLM for ambiguous goals where keywords are insufficient.

    Args:
        goal: Natural-language description of what to create.

    Returns:
        Tuple of (artifact_type_str, framework, reasoning).
    """
    valid_fws = sorted(_VALID_FRAMEWORKS - {"a2a"})  # a2a is interop, not user-facing
    prompt = (
        f"Given this user goal, choose the best framework to create it.\n\n"
        f"Goal: {goal}\n\n"
        f"Valid frameworks: {', '.join(valid_fws)}\n\n"
        f"For each framework:\n"
        f"- crewai: Multi-agent collaboration with roles and delegation\n"
        f"- langchain: Stateful pipelines, workflows, chains, state machines\n"
        f"- adk: Google/Vertex/Gemini-based agents\n"
        f"- custom: General-purpose Python agent (default fallback)\n"
        f"- mcp_function: Single-purpose tool/function\n"
        f"- mcp_server: Tool server exposing multiple endpoints\n"
        f"- skill: Reusable prompt template / instruction set\n\n"
        f"Respond with JSON containing exactly these keys:\n"
        f'{{"artifact_type": "agent"|"tool"|"skill", '
        f'"framework": "<one of the valid frameworks>", '
        f'"reasoning": "<brief explanation>"}}'
    )

    try:
        result = await call_llm_json(
            prompt,
            system="You are a framework selection expert. Respond ONLY with valid JSON.",
        )

        artifact_type = result.get("artifact_type", "agent")
        framework = result.get("framework", "custom")
        reasoning = result.get("reasoning", "LLM selected framework")

        # Validate against known frameworks
        if framework not in _VALID_FRAMEWORKS:
            logger.warning("LLM selected unknown framework '%s', falling back to custom", framework)
            framework = "custom"

        # Validate artifact type
        if artifact_type not in ("agent", "tool", "skill"):
            artifact_type = "agent"

        return (artifact_type, framework, reasoning)

    except Exception:
        logger.warning("LLM framework selection failed for goal: %.200s", goal)
        return ("agent", "custom", "LLM selection failed, defaulting to custom")

# ---------------------------------------------------------------------------
# Name derivation
# ---------------------------------------------------------------------------

def _derive_name(goal: str) -> str:
    """Extract a snake_case name from the goal string.

    Takes first 3-4 significant words (skipping articles and prepositions),
    lowercases, joins with underscores, and truncates to 64 characters.

    Args:
        goal: Natural-language description.

    Returns:
        A slug-style name matching ``^[a-z][a-z0-9_-]*$``.
    """
    lower = goal.lower()
    words = _WORD_RE.findall(lower)
    significant = [w for w in words if w not in _STOP_WORDS]

    # Take first 4 significant words
    slug_words = significant[:4] if significant else ["artifact"]
    name = "_".join(slug_words)[:64]

    # Ensure valid pattern
    if not _NAME_RE.match(name):
        name = "artifact"

    return name

# ---------------------------------------------------------------------------
# Confidence estimation for framework selection
# ---------------------------------------------------------------------------

def _estimate_confidence(
    artifact_type: str,
    framework: str,
    goal: str,
    reasoning: str,
) -> float:
    """Estimate confidence that the keyword-based framework selection is correct.

    Considers multiple signals:
    - Keyword match count: More matching keywords = higher confidence
    - Goal specificity: Longer, more detailed goals = higher confidence
    - Framework-goal alignment: Certain frameworks strongly match certain patterns
    - Ambiguity: Goals that match multiple framework keywords = lower confidence

    Args:
        artifact_type: Selected artifact type ("agent", "tool", "skill").
        framework: Selected framework identifier.
        goal: Original user goal string.
        reasoning: Reasoning string from select_framework().

    Returns:
        Float in [0.0, 1.0] representing selection confidence.
    """
    score = 0.5  # Base confidence for any keyword match

    lower = goal.lower()
    words = set(lower.split())

    # Signal 1: Keyword match count (more matches = higher confidence)
    keyword_sets = {
        "mcp_function": _TOOL_KEYWORDS,
        "mcp_server": _TOOL_KEYWORDS | _SERVER_KEYWORDS,
        "skill": _SKILL_KEYWORDS,
        "crewai": _COLLAB_KEYWORDS,
        "langchain": _WORKFLOW_KEYWORDS,
        "adk": _GOOGLE_KEYWORDS,
        "custom": frozenset(),
    }
    matched_kws = keyword_sets.get(framework, frozenset())
    match_count = sum(1 for kw in matched_kws if kw in words or kw in lower)
    if match_count >= 3:
        score += 0.25
    elif match_count >= 2:
        score += 0.15
    elif match_count >= 1:
        score += 0.05

    # Signal 2: Goal specificity (word count)
    word_count = len(words)
    if word_count >= 10:
        score += 0.1  # Detailed goal
    elif word_count <= 3:
        score -= 0.15  # Very terse, likely ambiguous

    # Signal 3: Ambiguity -- check if other frameworks also match
    competing = 0
    all_keyword_sets = [
        _TOOL_KEYWORDS,
        _SKILL_KEYWORDS,
        _WORKFLOW_KEYWORDS,
        _COLLAB_KEYWORDS,
        _GOOGLE_KEYWORDS,
        _SERVER_KEYWORDS,
    ]
    for kset in all_keyword_sets:
        if kset is not matched_kws and any(kw in words or kw in lower for kw in kset):
            competing += 1
    if competing >= 2:
        score -= 0.2  # High ambiguity
    elif competing == 1:
        score -= 0.1

    # Signal 4: "custom" default = low confidence unless goal is very short
    if framework == "custom" and "No keyword match" in reasoning:
        score = 0.3  # Low confidence for default fallback

    return max(0.0, min(1.0, score))

# ---------------------------------------------------------------------------
# Base config builder
# ---------------------------------------------------------------------------

def _build_base_config(goal: str, name: str, framework: str) -> dict:
    """Construct the base config dict common to all frameworks.

    Args:
        goal: Original user goal.
        name: Derived artifact name.
        framework: Selected framework identifier.

    Returns:
        Base config dict with common keys.
    """
    return {
        "name": name,
        "description": goal,
        "goal": goal,
        "version": "1.0.0",
        "framework": framework,
        "factory_created": True,
        "original_goal": goal,
    }

# ---------------------------------------------------------------------------
# Available capabilities context for LLM prompts
# ---------------------------------------------------------------------------

def _get_available_capabilities_context() -> str:
    """Get a summary of available MCP servers and tools for LLM prompt context.

    Returns an empty string if capability information is unavailable.
    """
    lines: list[str] = []
    try:
        from core.mcp.tool_index import get_tool_index

        tool_index = get_tool_index()
        all_tools = tool_index.to_manifest()
        if all_tools:
            lines.append("Available MCP tools in this system:")
            for tool in all_tools[:30]:  # Cap at 30 to avoid prompt bloat
                desc = tool.get("description", "")[:80]
                lines.append(f"  - {tool.get('name', '?')}: {desc}")
    except (ImportError, Exception):
        pass

    try:
        from core.orchestrator.capability_registry import get_capability_registry

        cap_reg = get_capability_registry()
        caps = cap_reg.list_all()
        if caps:
            agent_caps = [c for c in caps if c.source == "agent"]
            if agent_caps:
                lines.append("Available agents:")
                for c in agent_caps[:15]:
                    lines.append(f"  - {c.name}: {c.description_short}")
    except (ImportError, Exception):
        pass

    return "\n".join(lines) if lines else ""

# ---------------------------------------------------------------------------
# LLM enrichment: agent configs
# ---------------------------------------------------------------------------

async def _enrich_agent_config(config: dict, framework: str, goal: str) -> dict:
    """Enrich agent config with framework-specific fields via LLM.

    Falls back to rule-based defaults when LLM is unavailable.

    Args:
        config: Base config dict to enrich (mutated in place).
        framework: Framework identifier (crewai, langchain, adk, custom).
        goal: Original user goal for prompt context.

    Returns:
        The enriched config dict.
    """
    name = config.get("name", "agent")

    framework_prompts = {
        "crewai": (
            f"Generate a CrewAI agent configuration for this goal: {goal}\n\n"
            f"Respond with JSON containing:\n"
            f'{{"routing_description": "<1-2 sentence routing-quality description>", "role": "<agent role>", "backstory": "<agent backstory>", '
            f'"tools": ["<tool1>", ...], "mcp_servers": ["<server1>", ...], '
            f'"allow_delegation": true|false, '
            f'"capabilities": ["<capability1>", ...]}}'
        ),
        "langchain": (
            f"Generate a LangChain agent configuration for this goal: {goal}\n\n"
            f"Respond with JSON containing:\n"
            f'{{"routing_description": "<1-2 sentence routing-quality description>", '
            f'"system_prompt": "<system prompt>", '
            f'"tools": ["<tool1>", ...], "mcp_servers": ["<server1>", ...], '
            f'"streaming": true|false, '
            f'"use_prebuilt": true|false, '
            f'"extra_state_fields": {{"field_name": "field_type", ...}}, '
            f'"capabilities": ["<capability1>", ...]}}'
        ),
        "adk": (
            f"Generate a Google ADK agent configuration for this goal: {goal}\n\n"
            f"Respond with JSON containing:\n"
            f'{{"routing_description": "<1-2 sentence routing-quality description>", "instruction": "<agent instruction>", '
            f'"model": "<model name>", '
            f'"tools": ["<tool1>", ...], "mcp_servers": ["<server1>", ...], '
            f'"capabilities": ["<capability1>", ...]}}'
        ),
        "custom": (
            f"Generate a custom Python agent configuration for this goal: {goal}\n\n"
            f"Respond with JSON containing:\n"
            f'{{"routing_description": "<1-2 sentence routing-quality description>", '
            f'"tools": ["<tool1>", ...], "mcp_servers": ["<server1>", ...], '
            f'"capabilities": ["<capability1>", ...]}}'
        ),
    }

    prompt = framework_prompts.get(framework, framework_prompts["custom"])

    # Inject available capabilities so LLM uses real tool/server names
    capabilities_ctx = _get_available_capabilities_context()
    if capabilities_ctx:
        prompt += (
            f"\n\nFor reference, here are the capabilities already available "
            f"in this system (use exact names if referencing them):\n{capabilities_ctx}\n"
        )

    system = f"You are an expert AI agent architect. Generate configuration for a {framework} agent. Respond ONLY with valid JSON."

    try:
        enrichment = await call_llm_json(prompt, system=system)
        config.update(enrichment)
    except Exception:
        logger.warning("LLM agent enrichment failed for '%s', using rule-based defaults", name)
        # Rule-based defaults per framework
        if framework == "crewai":
            config.update(
                {
                    "role": name.replace("_", " ").title(),
                    "backstory": f"An agent specialized in: {goal}",
                    "tools": [],
                    "mcp_servers": [],
                    "allow_delegation": False,
                    "capabilities": [],
                }
            )
        elif framework == "langchain":
            config.update(
                {
                    "system_prompt": f"You are a helpful assistant. Your task: {goal}",
                    "tools": [],
                    "mcp_servers": [],
                    "streaming": True,
                    "use_prebuilt": True,
                    "extra_state_fields": {},
                    "capabilities": [],
                }
            )
        elif framework == "adk":
            config.update(
                {
                    "instruction": f"Your task: {goal}",
                    "model": "gemini-2.0-flash",
                    "tools": [],
                    "mcp_servers": [],
                    "capabilities": [],
                }
            )
        else:
            config.update(
                {
                    "tools": [],
                    "mcp_servers": [],
                    "capabilities": [],
                }
            )

    return config

# ---------------------------------------------------------------------------
# LLM enrichment: tool configs
# ---------------------------------------------------------------------------

async def _enrich_tool_config(config: dict, framework: str, goal: str) -> dict:
    """Enrich tool config with framework-specific fields via LLM.

    Falls back to placeholder implementation when LLM is unavailable.

    Args:
        config: Base config dict to enrich (mutated in place).
        framework: Framework identifier (mcp_function or mcp_server).
        goal: Original user goal for prompt context.

    Returns:
        The enriched config dict.
    """
    if framework == "mcp_function":
        prompt = (
            f"Generate an MCP function tool configuration for this goal: {goal}\n\n"
            f"Respond with JSON containing:\n"
            f'{{"routing_description": "<1-2 sentence routing-quality description>", "tool_name": "<function_name>", '
            f'"params": [{{"name": "<param>", "type": "<type>", "description": "<desc>"}}], '
            f'"return_type": "<type>", '
            f'"implementation": "<python code body>"}}'
        )
    else:  # mcp_server
        prompt = (
            f"Generate an MCP server tool configuration for this goal: {goal}\n\n"
            f"Respond with JSON containing:\n"
            f'{{"routing_description": "<1-2 sentence routing-quality description>", '
            f'"server_name": "<server_name>", '
            f'"tools": [{{"name": "<tool>", "description": "<desc>", '
            f'"params": [{{"name": "<p>", "type": "<t>"}}], '
            f'"implementation": "<python code>"}}], '
            f'"has_lifespan": true|false, '
            f'"lifespan_init": "<python code for startup>" or null, '
            f'"lifespan_cleanup": "<python code for shutdown>" or null, '
            f'"resources": [{{"uri": "<uri>", "name": "<name>", "description": "<desc>", '
            f'"implementation": "<python code>"}}] or [], '
            f'"prompts": [{{"name": "<name>", "description": "<desc>", '
            f'"params": [{{"name": "<p>", "type": "<t>"}}], '
            f'"implementation": "<python code>"}}] or [], '
            f'"auth_config": null}}'
        )

    # Inject available capabilities so LLM uses real tool/server names
    capabilities_ctx = _get_available_capabilities_context()
    if capabilities_ctx:
        prompt += (
            f"\n\nFor reference, here are the capabilities already available "
            f"in this system (use exact names if referencing them):\n{capabilities_ctx}\n"
        )

    system = f"You are an expert tool developer. Generate configuration for an MCP {framework.replace('mcp_', '')}. Respond ONLY with valid JSON."

    try:
        enrichment = await call_llm_json(prompt, system=system)
        config.update(enrichment)
    except Exception:
        logger.warning("LLM tool enrichment failed, using placeholder defaults")
        if framework == "mcp_function":
            config.update(
                {
                    "tool_name": config.get("name", "my_tool"),
                    "params": [],
                    "return_type": "str",
                    "implementation": "return 'Not yet implemented'",
                }
            )
        else:
            config.update(
                {
                    "server_name": config.get("name", "my_server"),
                    "tools": [
                        {
                            "name": "default_tool",
                            "description": goal,
                            "params": [],
                            "implementation": "return 'Not yet implemented'",
                        }
                    ],
                    "has_lifespan": False,
                    "lifespan_init": None,
                    "lifespan_cleanup": None,
                    "resources": [],
                    "prompts": [],
                    "auth_config": None,
                }
            )

    return config

# ---------------------------------------------------------------------------
# LLM enrichment: skill configs
# ---------------------------------------------------------------------------

async def _enrich_skill_config(config: dict, goal: str) -> dict:
    """Enrich skill config with LLM-generated fields.

    Falls back to the goal as instructions with a generic category.

    Args:
        config: Base config dict to enrich (mutated in place).
        goal: Original user goal for prompt context.

    Returns:
        The enriched config dict.
    """
    prompt = (
        f"Generate a skill configuration for this goal: {goal}\n\n"
        f"A skill is a reusable prompt template/instruction set.\n"
        f"Respond with JSON containing:\n"
        f'{{"routing_description": "<1-2 sentence routing-quality description>", "skill_name": "<namespace.skill_name>", '
        f'"instructions": "<markdown body with the full skill instructions>", '
        f'"emoji": "<single emoji>", '
        f'"category": "<category>", '
        f'"user_invocable": true|false, '
        f'"requires": ["<dependency1>", ...]}}'
    )
    # Inject available capabilities so LLM uses real tool/server names
    capabilities_ctx = _get_available_capabilities_context()
    if capabilities_ctx:
        prompt += (
            f"\n\nFor reference, here are the capabilities already available "
            f"in this system (use exact names if referencing them):\n{capabilities_ctx}\n"
        )

    system = "You are an expert skill designer. Generate a complete, useful skill configuration. Respond ONLY with valid JSON."

    try:
        enrichment = await call_llm_json(prompt, system=system)
        config.update(enrichment)
    except Exception:
        logger.warning("LLM skill enrichment failed, using rule-based defaults")
        config.update(
            {
                "skill_name": f"general.{config.get('name', 'skill')}",
                "instructions": goal,
                "emoji": "",
                "category": "general",
                "user_invocable": True,
                "requires": [],
            }
        )

    return config

# ---------------------------------------------------------------------------
# Primary public API: generate_config
# ---------------------------------------------------------------------------

async def generate_config(
    goal: str,
    name: str | None = None,
    framework: str | None = None,
    artifact_type: str | None = None,
) -> dict:
    """Generate a complete config dict for scaffold_artifact().

    Two-tier selection:
      1. If framework not provided, use keyword matching (fast path).
      2. If fast path returns "custom" and the goal is substantive (>20 chars),
         try LLM-based selection for better accuracy.

    Then enriches the config with framework-specific fields via LLM,
    falling back to rule-based defaults on any error.

    Args:
        goal: Natural-language description of what to create.
        name: Optional artifact name (derived from goal if omitted).
        framework: Optional explicit framework selection.
        artifact_type: Optional explicit artifact type ("agent", "tool", "skill").

    Returns:
        Complete config dict ready for scaffold_artifact().
    """
    # --- Framework selection ---
    if framework and artifact_type:
        reasoning = f"Explicit selection: {artifact_type}/{framework}"
        sel_type = artifact_type
        sel_fw = framework
    elif framework:
        # Infer artifact type from framework
        if framework in ("mcp_function", "mcp_server"):
            sel_type = "tool"
        elif framework == "skill":
            sel_type = "skill"
        else:
            sel_type = "agent"
        sel_fw = framework
        reasoning = f"Framework explicit ({framework}), type inferred as {sel_type}"
    else:
        # Keyword-based fast path
        sel_type, sel_fw, reasoning = select_framework(goal)

        # Confidence-based LLM fallback
        confidence = _estimate_confidence(sel_type, sel_fw, goal, reasoning)
        if confidence < 0.7:
            llm_type, llm_fw, llm_reason = await select_framework_llm(goal)
            if llm_fw != "custom":
                sel_type, sel_fw, reasoning = llm_type, llm_fw, llm_reason

    # Override artifact_type if explicitly provided
    if artifact_type:
        sel_type = artifact_type

    # Phase 174.5: Resolve type/framework mismatches.
    # The LLM may set artifact_type="agent" but keywords select mcp_function
    # (a tool-only framework). Fall back to "custom" for agents.
    _AGENT_FRAMEWORKS = {"custom", "crewai", "langchain", "adk"}
    _TOOL_FRAMEWORKS = {"mcp_function", "mcp_server"}
    if sel_type == "agent" and sel_fw in _TOOL_FRAMEWORKS:
        logger.info(
            "Framework %s is tool-only but artifact_type=agent, falling back to custom",
            sel_fw,
        )
        sel_fw = "custom"
    elif sel_type == "tool" and sel_fw in _AGENT_FRAMEWORKS - {"custom"}:
        logger.info(
            "Framework %s is agent-only but artifact_type=tool, falling back to mcp_function",
            sel_fw,
        )
        sel_fw = "mcp_function"

    # --- Name derivation ---
    if not name:
        name = _derive_name(goal)

    # --- Build base config ---
    config = _build_base_config(goal, name, sel_fw)
    config["artifact_type"] = sel_type
    config["selection_reasoning"] = reasoning

    # --- Best-effort common packages matching (static fallback) ---
    # When the framework involves MCP, pre-populate mcp_servers with
    # known package names that match keywords in the goal.  The LLM
    # enrichment may override or extend these later.
    if sel_fw in ("mcp_function", "mcp_server") or sel_type != "skill":
        lower_goal = goal.lower()
        matched_packages: list[str] = []
        for keyword, package in _COMMON_PACKAGES.items():
            if keyword in lower_goal and package not in matched_packages:
                matched_packages.append(package)
        if matched_packages:
            config["mcp_servers"] = matched_packages

    # --- Framework-specific enrichment ---
    if sel_type == "tool":
        config = await _enrich_tool_config(config, sel_fw, goal)
    elif sel_type == "skill":
        config = await _enrich_skill_config(config, goal)
    else:
        config = await _enrich_agent_config(config, sel_fw, goal)

    # Upgrade description with routing-quality version if LLM provided one
    routing_desc = config.pop("routing_description", None)
    if routing_desc and len(routing_desc) > 20:
        config["description"] = routing_desc

    # Validate description quality (minimum 20 chars)
    desc = config.get("description", "")
    if len(desc) < 20:
        config["description"] = (
            f"{config.get('name', 'artifact').replace('_', ' ').title()}: "
            f"{config.get('goal', desc)}"
        )

    return config
