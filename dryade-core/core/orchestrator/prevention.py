"""Pre-execution prevention pipeline for Dryade orchestrator.

Composable checks that catch errors before they happen: tool schema
mismatches, dead MCP servers, unreachable models, recurring failure
patterns.  All checks are fail-open -- pipeline errors never block
tool execution.

Classes:
    PreventionVerdict   -- PASS / FAIL / WARN enum.
    PreventionResult    -- Dataclass carrying verdict + metadata.
    SchemaValidator     -- Validates tool arguments against MCP inputSchema.
    ConnectivityProbe   -- Probes MCP server health lazily (once per server per session).
    ModelReachabilityCheck -- Probes the LLM endpoint with a lightweight HTTP GET.
    PromptOptimizer     -- Compiles deterministic prevention hints from failure history.
    PreventionPipeline  -- Orchestrates all checks behind feature flags.

Plan: 118.9-01
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

# jsonschema: optional dependency, graceful degradation
try:
    from jsonschema import ValidationError, validate
except ImportError:
    validate = None  # type: ignore[assignment]
    ValidationError = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

__all__ = [
    "PreventionVerdict",
    "PreventionResult",
    "SchemaValidator",
    "ConnectivityProbe",
    "ModelReachabilityCheck",
    "PromptOptimizer",
    "PreventionPipeline",
    "get_prevention_pipeline",
]

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class PreventionVerdict(str, Enum):
    """Outcome of a single prevention check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"

@dataclass
class PreventionResult:
    """Result of a single prevention check."""

    verdict: PreventionVerdict
    check_name: str
    reason: str = ""
    metadata: dict[str, Any] | None = None
    duration_ms: float = 0.0

# ---------------------------------------------------------------------------
# SchemaValidator
# ---------------------------------------------------------------------------

class SchemaValidator:
    """Validates tool arguments against MCP inputSchema.

    Uses ``jsonschema.validate`` if available, otherwise returns PASS
    (fail-open graceful degradation).  Applies null-sanitization before
    validation to match the adapter.py:306 pattern -- LLMs frequently
    generate ``null`` for optional fields which would otherwise cause
    false-positive validation failures.
    """

    def validate_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        schema: dict[str, Any],
    ) -> PreventionResult:
        """Validate *arguments* against JSON *schema*.

        Returns:
            PreventionResult with PASS on valid / missing jsonschema,
            FAIL on validation error, or PASS on unexpected error (fail-open).
        """
        start = time.monotonic()
        try:
            if validate is None:
                return PreventionResult(
                    verdict=PreventionVerdict.PASS,
                    check_name="schema_validator",
                    reason="jsonschema not available",
                    duration_ms=_elapsed_ms(start),
                )

            # Null-sanitize: strip keys with None values (matches adapter.py:306)
            sanitized = {k: v for k, v in arguments.items() if v is not None}

            validate(instance=sanitized, schema=schema)

            return PreventionResult(
                verdict=PreventionVerdict.PASS,
                check_name="schema_validator",
                reason="arguments valid",
                duration_ms=_elapsed_ms(start),
            )
        except ValidationError as e:
            failed_path = list(e.path) if e.path else []
            return PreventionResult(
                verdict=PreventionVerdict.FAIL,
                check_name="schema_validator",
                reason=(
                    f"Tool '{tool_name}' schema validation failed: {e.message} (path={failed_path})"
                ),
                metadata={
                    "tool_name": tool_name,
                    "failed_path": failed_path,
                    "validator": e.validator,
                    "schema_path": list(e.schema_path) if e.schema_path else [],
                },
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            logger.warning("SchemaValidator unexpected error (fail-open): %s", exc)
            return PreventionResult(
                verdict=PreventionVerdict.PASS,
                check_name="schema_validator",
                reason=f"unexpected error (fail-open): {exc}",
                duration_ms=_elapsed_ms(start),
            )

# ---------------------------------------------------------------------------
# ConnectivityProbe
# ---------------------------------------------------------------------------

class ConnectivityProbe:
    """Probes MCP server health lazily -- once per server per session.

    The probe only fires on the first tool call to a given server within
    a session, NOT at orchestrate() start.  If the server is already
    running, the probe is a no-op.
    """

    def __init__(self, registry: Any) -> None:
        """Create a probe backed by *registry* (MCPRegistry instance)."""
        self._registry = registry
        self._probed_servers: set[str] = set()

    async def probe_server(self, server_name: str) -> PreventionResult:
        """Probe *server_name* for connectivity.

        Returns PASS if the server is already running or if a lazy start
        succeeds.  Returns FAIL if the server cannot be reached.  A server
        that has already been probed this session is skipped.
        """
        start = time.monotonic()
        try:
            if server_name in self._probed_servers:
                return PreventionResult(
                    verdict=PreventionVerdict.PASS,
                    check_name="connectivity_probe",
                    reason="already probed this session",
                    duration_ms=_elapsed_ms(start),
                )

            # Fast pre-check: already running?
            if self._registry.is_running(server_name):
                self._probed_servers.add(server_name)
                return PreventionResult(
                    verdict=PreventionVerdict.PASS,
                    check_name="connectivity_probe",
                    reason=f"server '{server_name}' already running",
                    duration_ms=_elapsed_ms(start),
                )

            # Trigger lazy-start via list_tools
            tools = self._registry.list_tools(server_name)
            self._probed_servers.add(server_name)
            return PreventionResult(
                verdict=PreventionVerdict.PASS,
                check_name="connectivity_probe",
                reason=f"server '{server_name}' started successfully",
                metadata={"tool_count": len(tools)},
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            # Do NOT add to probed set so it can be retried
            return PreventionResult(
                verdict=PreventionVerdict.FAIL,
                check_name="connectivity_probe",
                reason=f"server '{server_name}' unreachable: {exc}",
                duration_ms=_elapsed_ms(start),
            )

    def reset(self) -> None:
        """Clear the probed-servers set (for new sessions)."""
        self._probed_servers.clear()

# ---------------------------------------------------------------------------
# ModelReachabilityCheck
# ---------------------------------------------------------------------------

class ModelReachabilityCheck:
    """Probes the LLM endpoint with a lightweight HTTP GET.

    Only probes when ``OPENAI_BASE_URL`` is set (i.e. local / self-hosted
    endpoints).  Cloud API endpoints are assumed reachable.  Results are
    cached for 60 seconds.
    """

    _CACHE_TTL_SECONDS: float = 60.0

    def __init__(self) -> None:
        self._last_check_time: float = 0.0
        self._last_result: PreventionResult | None = None

    async def check(self) -> PreventionResult:
        """Probe the LLM endpoint for reachability.

        Returns cached result if within 60s of the last successful probe.
        """
        start = time.monotonic()
        try:
            # Check cache
            if (
                self._last_result is not None
                and (time.monotonic() - self._last_check_time) < self._CACHE_TTL_SECONDS
            ):
                return self._last_result

            from core.config import get_settings

            base_url = get_settings().llm_base_url.strip()

            import httpx

            # base_url typically ends with /v1; append /models directly
            url = f"{base_url.rstrip('/')}/models"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                result = PreventionResult(
                    verdict=PreventionVerdict.PASS,
                    check_name="model_reachability",
                    reason="LLM endpoint reachable",
                    metadata={"status_code": resp.status_code, "url": url},
                    duration_ms=_elapsed_ms(start),
                )
            else:
                result = PreventionResult(
                    verdict=PreventionVerdict.FAIL,
                    check_name="model_reachability",
                    reason=f"LLM endpoint returned status {resp.status_code}",
                    metadata={"status_code": resp.status_code, "url": url},
                    duration_ms=_elapsed_ms(start),
                )

            self._update_cache(result)
            return result

        except Exception as exc:
            import httpx as _httpx

            if isinstance(exc, (_httpx.ConnectError, _httpx.TimeoutException)):
                result = PreventionResult(
                    verdict=PreventionVerdict.FAIL,
                    check_name="model_reachability",
                    reason=f"LLM endpoint unreachable: {type(exc).__name__}",
                    duration_ms=_elapsed_ms(start),
                )
                self._update_cache(result)
                return result

            # Truly unexpected -- fail-open
            logger.warning("ModelReachabilityCheck unexpected error (fail-open): %s", exc)
            return PreventionResult(
                verdict=PreventionVerdict.PASS,
                check_name="model_reachability",
                reason=f"unexpected error (fail-open): {exc}",
                duration_ms=_elapsed_ms(start),
            )

    def _update_cache(self, result: PreventionResult) -> None:
        self._last_result = result
        self._last_check_time = time.monotonic()

# ---------------------------------------------------------------------------
# PromptOptimizer
# ---------------------------------------------------------------------------

# Error category -> mitigation mapping (deterministic, no LLM calls)
_MITIGATION_MAP: dict[str, str] = {
    "PERMISSION": "verify paths are within allowed directories",
    "TIMEOUT": "use simpler queries or smaller inputs",
    "SCHEMA": "double-check argument types",
    "NOT_FOUND": "verify the resource exists before referencing it",
    "CONNECTION": "check server connectivity before calling",
    "RATE_LIMIT": "add delays between calls or batch requests",
    "AUTH": "ensure credentials are configured correctly",
    "PARSE": "simplify the input format",
    "INTERNAL": "try with different parameters",
    "VALIDATION": "double-check argument types and formats",
    "UNKNOWN": "review the tool documentation for usage patterns",
}

class PromptOptimizer:
    """Compiles deterministic prevention hints from failure history patterns.

    Zero LLM calls -- pure data analysis.  Examines historical failure
    rates and recurring error categories to produce actionable hints that
    are injected into the system prompt.  Results are TTL-cached.
    """

    def __init__(self, store: Any, detector: Any) -> None:
        """Create optimizer backed by *store* (FailureHistoryStore) and *detector* (PatternDetector)."""
        self._store = store
        self._detector = detector
        self._cached_hints: list[str] = []
        self._last_compiled: float = 0.0

    def compile_hints(
        self,
        max_hints: int = 5,
        ttl_seconds: float = 300.0,
    ) -> list[str]:
        """Compile prevention hints from failure history.

        Returns a list of human-readable hint strings (up to *max_hints*).
        Cached for *ttl_seconds*.
        """
        try:
            if self._cached_hints and (time.monotonic() - self._last_compiled) < ttl_seconds:
                return self._cached_hints

            failing_tools = self._detector.detect_high_failure_tools(
                threshold=0.4,
                window_hours=24,
            )

            hints: list[str] = []
            for tool_info in failing_tools[:max_hints]:
                tool_name = tool_info["tool_name"]
                rate = tool_info["failure_rate"]

                # Get recurring error categories for this tool
                errors = self._detector.detect_recurring_errors(tool_name)
                if errors:
                    categories = ", ".join(e["error_category"] for e in errors[:3])
                    # Pick mitigation from the top error category
                    top_cat = errors[0]["error_category"]
                    mitigation = _MITIGATION_MAP.get(
                        top_cat, "review the tool documentation for usage patterns"
                    )
                else:
                    categories = "various"
                    mitigation = "review the tool documentation for usage patterns"

                hint = (
                    f"When using {tool_name}, be aware it has a {rate:.0%} failure rate. "
                    f"Common errors: {categories}. "
                    f"Consider: {mitigation}."
                )
                hints.append(hint)

            self._cached_hints = hints
            self._last_compiled = time.monotonic()
            return hints

        except Exception as exc:
            logger.warning("PromptOptimizer.compile_hints error (fail-open): %s", exc)
            return []

# ---------------------------------------------------------------------------
# PreventionPipeline
# ---------------------------------------------------------------------------

class PreventionPipeline:
    """Orchestrates all pre-execution checks behind feature flags.

    Holds instances of all 4 check classes as lazy properties.  Public
    methods delegate to the appropriate check and return ``None`` if the
    corresponding feature flag is disabled.
    """

    def __init__(self) -> None:
        self._schema_validator_instance: SchemaValidator | None = None
        self._connectivity_probe_instance: ConnectivityProbe | None = None
        self._model_reachability_instance: ModelReachabilityCheck | None = None
        self._prompt_optimizer_instance: PromptOptimizer | None = None
        self._prompt_optimizer_init_attempted: bool = False
        self._connectivity_probe_init_attempted: bool = False

    # -- Lazy properties -------------------------------------------------------

    @property
    def _schema_validator(self) -> SchemaValidator:
        if self._schema_validator_instance is None:
            self._schema_validator_instance = SchemaValidator()
        return self._schema_validator_instance

    @property
    def _connectivity_probe(self) -> ConnectivityProbe | None:
        if (
            self._connectivity_probe_instance is None
            and not self._connectivity_probe_init_attempted
        ):
            self._connectivity_probe_init_attempted = True
            try:
                from core.mcp.registry import get_registry

                self._connectivity_probe_instance = ConnectivityProbe(get_registry())
            except Exception as exc:
                logger.warning("ConnectivityProbe unavailable: %s", exc)
        return self._connectivity_probe_instance

    @property
    def _model_reachability(self) -> ModelReachabilityCheck:
        if self._model_reachability_instance is None:
            self._model_reachability_instance = ModelReachabilityCheck()
        return self._model_reachability_instance

    @property
    def _prompt_optimizer(self) -> PromptOptimizer | None:
        if self._prompt_optimizer_instance is None and not self._prompt_optimizer_init_attempted:
            self._prompt_optimizer_init_attempted = True
            try:
                from core.orchestrator.config import get_orchestration_config

                cfg = get_orchestration_config()
                if not cfg.failure_learning_enabled:
                    return None

                from core.orchestrator.failure_history import (
                    FailureHistoryStore,
                    PatternDetector,
                )

                store = FailureHistoryStore()
                detector = PatternDetector(store)
                self._prompt_optimizer_instance = PromptOptimizer(store, detector)
            except Exception as exc:
                logger.warning("PromptOptimizer unavailable: %s", exc)
        return self._prompt_optimizer_instance

    # -- Config helpers --------------------------------------------------------

    @staticmethod
    def _get_config() -> Any:
        from core.orchestrator.config import get_orchestration_config

        return get_orchestration_config()

    # -- Public methods --------------------------------------------------------

    def validate_tool_schema(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> PreventionResult | None:
        """Validate tool arguments against the MCP inputSchema.

        Returns ``None`` if schema validation is disabled or the schema
        cannot be retrieved.
        """
        cfg = self._get_config()
        if not cfg.prevention_enabled or not cfg.schema_validation_enabled:
            return None

        schema = self._get_tool_schema(server_name, tool_name)
        if schema is None:
            return None

        result = self._schema_validator.validate_arguments(tool_name, arguments, schema)
        try:
            from core.orchestrator.failure_metrics import record_prevention_check

            record_prevention_check(check_name=result.check_name, verdict=result.verdict.value)
        except Exception:
            pass
        return result

    async def probe_connectivity(self, server_name: str) -> PreventionResult | None:
        """Probe MCP server connectivity (once per server per session).

        Returns ``None`` if the connectivity probe is disabled or unavailable.
        """
        cfg = self._get_config()
        if not cfg.prevention_enabled or not cfg.connectivity_probe_enabled:
            return None

        probe = self._connectivity_probe
        if probe is None:
            return None

        result = await probe.probe_server(server_name)
        try:
            from core.orchestrator.failure_metrics import record_prevention_check

            record_prevention_check(check_name=result.check_name, verdict=result.verdict.value)
        except Exception:
            pass
        return result

    async def check_model_reachability(self) -> PreventionResult | None:
        """Check LLM endpoint reachability.

        Returns ``None`` if the model reachability check is disabled.
        """
        cfg = self._get_config()
        if not cfg.prevention_enabled or not cfg.model_reachability_enabled:
            return None

        result = await self._model_reachability.check()
        try:
            from core.orchestrator.failure_metrics import record_prevention_check

            record_prevention_check(check_name=result.check_name, verdict=result.verdict.value)
        except Exception:
            pass
        return result

    def get_prompt_hints(self) -> list[str]:
        """Get deterministic prevention hints from failure history.

        Returns an empty list if prompt optimization is disabled or
        failure learning is not enabled.
        """
        cfg = self._get_config()
        if not cfg.prevention_enabled or not cfg.prompt_optimization_enabled:
            return []

        optimizer = self._prompt_optimizer
        if optimizer is None:
            return []

        return optimizer.compile_hints()

    # -- Private helpers -------------------------------------------------------

    def _get_tool_schema(self, server_name: str, tool_name: str) -> dict[str, Any] | None:
        """Retrieve the JSON schema for a tool from the MCP registry.

        Returns ``None`` on any error (fail-open).
        """
        try:
            from core.mcp.registry import get_registry

            registry = get_registry()
            tools = registry.list_tools(server_name)
            for tool in tools:
                if tool.name == tool_name:
                    schema = tool.inputSchema
                    return {
                        "type": schema.type,
                        "properties": schema.properties,
                        "required": schema.required,
                    }
            return None
        except Exception as exc:
            logger.warning(
                "Failed to get schema for %s/%s (fail-open): %s",
                server_name,
                tool_name,
                exc,
            )
            return None

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pipeline_instance: PreventionPipeline | None = None

def get_prevention_pipeline() -> PreventionPipeline:
    """Get the global PreventionPipeline singleton."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = PreventionPipeline()
    return _pipeline_instance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _elapsed_ms(start: float) -> float:
    """Milliseconds elapsed since *start* (time.monotonic)."""
    return (time.monotonic() - start) * 1000.0
