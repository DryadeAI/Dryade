"""Orchestration configuration -- single source of truth for all constants.

Replaces scattered os.environ.get() calls and hardcoded magic numbers
across observation.py, orchestrator.py, thinking/provider.py, and handlers.
"""

from pydantic import Field
from pydantic_settings import BaseSettings

class OrchestrationConfig(BaseSettings):
    """Orchestration subsystem configuration.

    All values have defaults matching current behavior.
    Override via environment variables.
    """

    # --- Feature flags (from handler env vars) ---
    planning_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_PLANNING_ENABLED",
    )
    tier_instant_enabled: bool = Field(
        default=False,
        validation_alias="DRYADE_TIER_INSTANT_ENABLED",
    )
    tier_simple_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_TIER_SIMPLE_ENABLED",
    )
    tier_simple_router_confirm: bool = Field(
        default=False,
        validation_alias="DRYADE_TIER_SIMPLE_ROUTER_CONFIRM",
    )

    # --- Native tool calling ---
    native_tools_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_NATIVE_TOOLS_ENABLED",
        description="Enable native LLM tool calling. When False, orchestrator uses text-based JSON fallback.",
    )

    # --- Router-based tool filtering (Phase 107) ---
    router_filter_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_ROUTER_FILTER_ENABLED",
        description="Filter tools by semantic router results before sending to LLM. Reduces token count ~90%.",
    )
    router_filter_max_servers: int = Field(
        default=5,
        validation_alias="DRYADE_ROUTER_FILTER_MAX_SERVERS",
        description="Maximum number of MCP servers to include from router results. Non-MCP agents always included.",
    )

    # --- Self-modification tools (Phase 115.1) ---
    self_mod_tools_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_SELF_MOD_TOOLS_ENABLED",
        description="Enable self-modification tools (create, memory_delete, modify_config, etc.) in orchestrator.",
    )
    meta_action_fallback_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_META_ACTION_FALLBACK_ENABLED",
        description="Enable fallback to programmatic escalation when LLM ignores self-mod tools.",
    )
    routing_metrics_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_ROUTING_METRICS_ENABLED",
        description="Enable routing metrics collection for self-modification pipeline.",
    )

    # --- Memory blocks (Phase 115.3) ---
    memory_blocks_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_MEMORY_BLOCKS_ENABLED",
        description="Enable agent-scoped memory blocks compiled into system prompts.",
    )
    memory_blocks_max_total_chars: int = Field(
        default=10000,
        validation_alias="DRYADE_MEMORY_BLOCKS_MAX_TOTAL_CHARS",
        description="Maximum total chars across all memory blocks for one agent.",
    )

    # --- Reflection (Phase 115.3) ---
    reflection_mode: str = Field(
        default="on_failure",
        validation_alias="DRYADE_REFLECTION_MODE",
        description="Reflection mode: 'off', 'on_failure', or 'always'.",
    )

    # --- Action autonomy (Phase 115.3) ---
    action_autonomy_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_ACTION_AUTONOMY_ENABLED",
        description="Enable per-action autonomy levels for self-modification tools.",
    )

    # --- Adaptive routing (Phase 115.4) ---
    adaptive_routing_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_ADAPTIVE_ROUTING_ENABLED",
        description="Enable adaptive model-aware routing strategies.",
    )
    model_tier_override: str | None = Field(
        default=None,
        validation_alias="DRYADE_MODEL_TIER_OVERRIDE",
        description="Override auto-detected model tier (weak/moderate/strong/frontier).",
    )
    middleware_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_MIDDLEWARE_ENABLED",
        description="Enable composable middleware hooks.",
    )
    few_shot_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_FEW_SHOT_ENABLED",
        description="Enable few-shot example injection for routing.",
    )

    # --- Optimization pipeline (Phase 115.5) ---
    optimization_enabled: bool = Field(
        default=False,
        validation_alias="DRYADE_OPTIMIZATION_ENABLED",
        description="Enable autonomous routing optimization pipeline (DSPy-inspired).",
    )
    optimization_interval_minutes: int = Field(
        default=60,
        validation_alias="DRYADE_OPTIMIZATION_INTERVAL_MINUTES",
        description="How often the optimization loop checks for new metrics.",
    )
    optimization_min_metrics: int = Field(
        default=50,
        validation_alias="DRYADE_OPTIMIZATION_MIN_METRICS",
        description="Minimum new metrics before triggering an optimization cycle.",
    )
    prompt_versioning_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_PROMPT_VERSIONING_ENABLED",
        description="Enable version-controlled prompt management with rollback.",
    )
    routing_explainability_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_ROUTING_EXPLAINABILITY_ENABLED",
        description="Enable routing decision explainability in API responses.",
    )

    # --- Circuit breaker (Phase 118.2) ---
    circuit_breaker_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_CIRCUIT_BREAKER_ENABLED",
        description="Enable per-MCP-server circuit breaker to prevent cascading failures from dead servers.",
    )

    # --- vLLM response validator (Phase 118.2) ---
    vllm_validator_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_VLLM_VALIDATOR_ENABLED",
        description="Enable deterministic vLLM response validation and repair for 7 known failure modes.",
    )

    # --- Soft failure detection (Phase 118.4) ---
    soft_failure_detection_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_SOFT_FAILURE_DETECTION_ENABLED",
        description="Enable deterministic heuristic-based soft failure detection for empty results, "
        "loops, truncation, size anomalies, and relevance scoring.",
    )

    # --- Checkpoint / rollback (Phase 118.5) ---
    checkpoint_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_CHECKPOINT_ENABLED",
        description="Enable in-memory state checkpoints before tool execution for rollback recovery.",
    )
    persistent_checkpoint_enabled: bool = Field(
        default=False,
        validation_alias="DRYADE_PERSISTENT_CHECKPOINT_ENABLED",
        description="Enable persistent checkpoints for cross-restart recovery. Requires checkpoint_enabled.",
    )
    checkpoint_max_snapshots: int = Field(
        default=20,
        validation_alias="DRYADE_CHECKPOINT_MAX_SNAPSHOTS",
        description="Maximum in-memory checkpoint snapshots per execution (ring buffer).",
    )

    # --- LLM-as-judge output validation (Phase 118.6) ---
    judge_enabled: bool = Field(
        default=False,  # Off by default -- costs extra LLM calls
        validation_alias="DRYADE_JUDGE_ENABLED",
        description="Enable LLM-as-judge output validation after heuristic soft failure checks pass.",
    )
    judge_score_threshold: float = Field(
        default=0.6,
        validation_alias="DRYADE_JUDGE_SCORE_THRESHOLD",
        description="Minimum overall score (0.0-1.0) for judge verdict to pass. Below this = soft failure.",
    )
    judge_model: str | None = Field(
        default=None,
        validation_alias="DRYADE_JUDGE_MODEL",
        description="Optional smaller/cheaper model for judge calls (e.g., 'gpt-3.5-turbo'). None = use main model.",
    )

    # --- Failure middleware (Phase 118.8) ---
    failure_middleware_enabled: bool = Field(
        default=False,
        validation_alias="DRYADE_FAILURE_MIDDLEWARE_ENABLED",
        description="Enable composable failure handling middleware pipeline with pre/post failure hooks and custom recovery strategies.",
    )

    # --- Failure learning (Phase 118.7) ---
    failure_learning_enabled: bool = Field(
        default=False,
        validation_alias="DRYADE_FAILURE_LEARNING_ENABLED",
        description="Enable failure history recording and adaptive retry strategies. "
        "Writes to database on every failure when enabled.",
    )
    failure_history_retention_days: int = Field(
        default=30,
        validation_alias="DRYADE_FAILURE_HISTORY_RETENTION_DAYS",
        description="Days to retain failure history records. Older records are purged on startup.",
    )
    preemptive_circuit_break_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_PREEMPTIVE_CIRCUIT_BREAK_ENABLED",
        description="Enable pre-emptive circuit breaking based on historical failure rates. "
        "Requires failure_learning_enabled.",
    )

    # --- Prevention layer (Phase 118.9) ---
    prevention_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_PREVENTION_ENABLED",
        description="Enable pre-execution prevention checks (schema validation, connectivity probes, model reachability).",
    )
    schema_validation_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_SCHEMA_VALIDATION_ENABLED",
        description="Enable tool argument schema validation against MCP inputSchema before execution. Requires prevention_enabled.",
    )
    connectivity_probe_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_CONNECTIVITY_PROBE_ENABLED",
        description="Enable per-session MCP server connectivity probes before first tool call. Requires prevention_enabled.",
    )
    model_reachability_enabled: bool = Field(
        default=True,
        validation_alias="DRYADE_MODEL_REACHABILITY_ENABLED",
        description="Enable LLM endpoint reachability check at orchestration start. Only probes local endpoints (OPENAI_BASE_URL). Requires prevention_enabled.",
    )
    prompt_optimization_enabled: bool = Field(
        default=False,
        validation_alias="DRYADE_PROMPT_OPTIMIZATION_ENABLED",
        description="Enable DSPy-inspired prompt optimization from failure history patterns. Requires prevention_enabled and failure_learning_enabled.",
    )

    # --- Timeout / retry (from orchestrator.py) ---
    agent_timeout: int = Field(
        default=120,
        validation_alias="DRYADE_AGENT_TIMEOUT",
    )
    mcp_tool_timeout: int = Field(
        default=60,
        validation_alias="DRYADE_MCP_TOOL_TIMEOUT",
        description="Timeout in seconds for individual MCP tool calls. Prevents indefinite hangs on unresponsive MCP servers.",
    )
    max_retries: int = 3

    # --- Observation history (from observation.py class constants) ---
    obs_window_size: int = 3
    obs_summary_max_chars: int = 120
    obs_max_observations: int = 50
    obs_facts_max_count: int = 20
    obs_result_max_chars: int = Field(
        default=51200,  # 50KB
        validation_alias="DRYADE_OBS_RESULT_MAX_CHARS",
        description="Maximum chars for observation result storage. Prevents memory waste from large tool outputs.",
    )

    # --- Context budgets (from thinking.py and orchestrate_handler.py) ---
    history_budget_chars: int = 2000

    # --- Context overflow detection (Phase 118.3) ---
    max_context_chars: int = Field(
        default=100000,
        validation_alias="DRYADE_MAX_CONTEXT_CHARS",
        description="Maximum context chars before triggering proactive compression. 85% of this triggers compress_aggressive.",
    )

def get_orchestration_config() -> OrchestrationConfig:
    """Get orchestration config.

    Creates a fresh instance each call so env var changes take effect
    immediately (important for feature flag toggles and tests).
    BaseSettings construction is cheap -- just reads os.environ.
    """
    return OrchestrationConfig()

# Keys that can be modified at runtime via the modify_config escalation action.
# Security-sensitive keys (e.g., native_tools_enabled, router_filter_enabled)
# are deliberately excluded.
MUTABLE_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "planning_enabled",
        "tier_instant_enabled",
        "tier_simple_enabled",
        "router_filter_max_servers",
        "self_mod_tools_enabled",
        "meta_action_fallback_enabled",
        "routing_metrics_enabled",
        "memory_blocks_enabled",
        "memory_blocks_max_total_chars",
        "optimization_enabled",
        "optimization_interval_minutes",
        "optimization_min_metrics",
        "prompt_versioning_enabled",
        "routing_explainability_enabled",
        "judge_enabled",
        "judge_score_threshold",
        "failure_learning_enabled",
        "failure_middleware_enabled",
        "prevention_enabled",
        "schema_validation_enabled",
        "connectivity_probe_enabled",
        "model_reachability_enabled",
        "prompt_optimization_enabled",
    }
)
