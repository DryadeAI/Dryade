"""Failure pipeline Prometheus metrics and SLO constants.

Phase 118.10 observability foundation. Defines Prometheus counters,
histograms, and gauges for every stage of the failure handling pipeline
(classification, recovery, circuit breaker, soft failure, middleware,
prevention, LLM cost). All metrics auto-export via the global
prometheus_client registry at the existing /metrics endpoint.

Helper functions wrap all metric recording in try/except to ensure
metrics collection never breaks orchestration (fail-open semantics).
"""

from prometheus_client import Counter, Gauge, Histogram

__all__ = [
    # SLO constants
    "SLO_FAILURE_DETECTION_MS",
    "SLO_RECOVERY_DECISION_DETERMINISTIC_MS",
    "SLO_RECOVERY_DECISION_LLM_MS",
    "SLO_CIRCUIT_BREAKER_TRIP_MS",
    # Helper functions
    "record_failure_classification",
    "record_failure_recovery",
    "record_circuit_breaker_trip",
    "update_circuit_breaker_state",
    "update_tool_failure_rate",
    "record_failure_llm_call",
    "record_prevention_check",
    "record_soft_failure",
    "record_failure_middleware",
    "record_classifier_accuracy",
]

# ---------------------------------------------------------------------------
# SLO definitions (milliseconds)
# ---------------------------------------------------------------------------

SLO_FAILURE_DETECTION_MS = 100  # Deterministic classification
SLO_RECOVERY_DECISION_DETERMINISTIC_MS = 500  # Deterministic recovery
SLO_RECOVERY_DECISION_LLM_MS = 5000  # LLM-based recovery decision
SLO_CIRCUIT_BREAKER_TRIP_MS = 1000  # Circuit breaker trip latency

# ---------------------------------------------------------------------------
# 1. Classification metrics
# ---------------------------------------------------------------------------

FAILURE_CLASSIFICATION_TOTAL = Counter(
    "dryade_failure_classification_total",
    "Total failure classification events",
    ["tier", "category", "action"],
)

FAILURE_CLASSIFICATION_LATENCY = Histogram(
    "dryade_failure_classification_seconds",
    "Failure classification latency in seconds",
    ["tier"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

# ---------------------------------------------------------------------------
# 2. Recovery metrics
# ---------------------------------------------------------------------------

FAILURE_RECOVERY_TOTAL = Counter(
    "dryade_failure_recovery_total",
    "Total failure recovery attempts",
    ["action", "success", "agent_name"],
)

FAILURE_RECOVERY_LATENCY = Histogram(
    "dryade_failure_recovery_seconds",
    "Failure recovery duration in seconds",
    ["action"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ---------------------------------------------------------------------------
# 3. Circuit breaker metrics
# ---------------------------------------------------------------------------

CIRCUIT_BREAKER_TRIPS_TOTAL = Counter(
    "dryade_circuit_breaker_trips_total",
    "Total circuit breaker trip events",
    ["server_name", "trigger"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "dryade_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["server_name"],
)

# State enum to numeric mapping for circuit breaker gauge
_CIRCUIT_STATE_VALUES = {"closed": 0, "open": 1, "half_open": 2}

# ---------------------------------------------------------------------------
# 4. Per-tool failure rate
# ---------------------------------------------------------------------------

TOOL_FAILURE_RATE = Gauge(
    "dryade_tool_failure_rate",
    "Per-tool failure rate (0.0-1.0)",
    ["tool_name"],
)

# ---------------------------------------------------------------------------
# 5. LLM cost for failure handling
# ---------------------------------------------------------------------------

FAILURE_LLM_CALLS_TOTAL = Counter(
    "dryade_failure_llm_calls_total",
    "Total LLM calls for failure handling",
    ["call_type"],
)

# ---------------------------------------------------------------------------
# 6. Prevention metrics
# ---------------------------------------------------------------------------

PREVENTION_CHECK_TOTAL = Counter(
    "dryade_prevention_check_total",
    "Total prevention check results",
    ["check_name", "verdict"],
)

# ---------------------------------------------------------------------------
# 7. Soft failure metrics
# ---------------------------------------------------------------------------

SOFT_FAILURE_TOTAL = Counter(
    "dryade_soft_failure_total",
    "Total soft failure detections by check type",
    ["check_type"],
)

# ---------------------------------------------------------------------------
# 8. Middleware metrics
# ---------------------------------------------------------------------------

FAILURE_MIDDLEWARE_TOTAL = Counter(
    "dryade_failure_middleware_total",
    "Total failure middleware hook invocations",
    ["hook_type", "success"],
)

# ---------------------------------------------------------------------------
# 9. Classifier accuracy metrics
# ---------------------------------------------------------------------------

FAILURE_CLASSIFIER_ACCURACY_TOTAL = Counter(
    "dryade_failure_classifier_accuracy_total",
    "Classifier accuracy tracking (whether suggested action resolved the failure)",
    ["category", "outcome"],
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
# Each helper is wrapped in try/except to ensure metrics recording never
# breaks orchestration flow (fail-open semantics).
# ---------------------------------------------------------------------------

def record_failure_classification(
    tier: str, category: str, action: str, duration_seconds: float
) -> None:
    """Record a failure classification event.

    Args:
        tier: Classification tier ("deterministic" or "llm").
        category: ErrorCategory value (e.g. "transient", "auth").
        action: FailureAction value (e.g. "retry", "escalate").
        duration_seconds: Time taken to classify.
    """
    try:
        FAILURE_CLASSIFICATION_TOTAL.labels(tier=tier, category=category, action=action).inc()
        FAILURE_CLASSIFICATION_LATENCY.labels(tier=tier).observe(duration_seconds)
    except Exception:
        pass  # Metrics must never break orchestration

def record_failure_recovery(
    action: str,
    success: bool,
    duration_seconds: float,
    agent_name: str = "",
) -> None:
    """Record a failure recovery attempt.

    Args:
        action: FailureAction value (e.g. "retry", "alternative").
        success: Whether recovery succeeded.
        duration_seconds: Time taken for recovery.
        agent_name: Name of agent involved (empty string if N/A).
    """
    try:
        FAILURE_RECOVERY_TOTAL.labels(
            action=action, success=str(success).lower(), agent_name=agent_name
        ).inc()
        FAILURE_RECOVERY_LATENCY.labels(action=action).observe(duration_seconds)
    except Exception:
        pass  # Metrics must never break orchestration

def record_circuit_breaker_trip(server_name: str, trigger: str) -> None:
    """Record a circuit breaker trip event.

    Args:
        server_name: MCP server name.
        trigger: Trip trigger ("threshold" or "preemptive").
    """
    try:
        CIRCUIT_BREAKER_TRIPS_TOTAL.labels(server_name=server_name, trigger=trigger).inc()
    except Exception:
        pass  # Metrics must never break orchestration

def update_circuit_breaker_state(server_name: str, state_str: str) -> None:
    """Update the circuit breaker state gauge.

    Args:
        server_name: MCP server name.
        state_str: State string ("closed", "open", or "half_open").
    """
    try:
        CIRCUIT_BREAKER_STATE.labels(server_name=server_name).set(
            _CIRCUIT_STATE_VALUES.get(state_str, -1)
        )
    except Exception:
        pass  # Metrics must never break orchestration

def update_tool_failure_rate(tool_name: str, rate: float) -> None:
    """Update the per-tool failure rate gauge.

    Args:
        tool_name: Tool name.
        rate: Failure rate (0.0-1.0).
    """
    try:
        TOOL_FAILURE_RATE.labels(tool_name=tool_name).set(rate)
    except Exception:
        pass  # Metrics must never break orchestration

def record_failure_llm_call(call_type: str) -> None:
    """Record an LLM call made for failure handling.

    Args:
        call_type: Type of LLM call ("failure_think", "judge_think",
                   or "replan_think").
    """
    try:
        FAILURE_LLM_CALLS_TOTAL.labels(call_type=call_type).inc()
    except Exception:
        pass  # Metrics must never break orchestration

def record_prevention_check(check_name: str, verdict: str) -> None:
    """Record a prevention check result.

    Args:
        check_name: Name of the prevention check.
        verdict: Check verdict ("pass", "fail", or "warn").
    """
    try:
        PREVENTION_CHECK_TOTAL.labels(check_name=check_name, verdict=verdict).inc()
    except Exception:
        pass  # Metrics must never break orchestration

def record_soft_failure(check_type: str) -> None:
    """Record a soft failure detection.

    Args:
        check_type: Type of soft failure ("empty_result", "loop_detected",
                    "truncation", "size_anomaly", or "low_relevance").
    """
    try:
        SOFT_FAILURE_TOTAL.labels(check_type=check_type).inc()
    except Exception:
        pass  # Metrics must never break orchestration

def record_failure_middleware(hook_type: str, success: bool) -> None:
    """Record a failure middleware hook invocation.

    Args:
        hook_type: Hook type ("pre_failure", "post_failure", or "on_recovery").
        success: Whether the hook executed successfully.
    """
    try:
        FAILURE_MIDDLEWARE_TOTAL.labels(hook_type=hook_type, success=str(success).lower()).inc()
    except Exception:
        pass  # Metrics must never break orchestration

def record_classifier_accuracy(category: str, outcome: str) -> None:
    """Record classifier accuracy tracking.

    Tracks whether the classifier's suggested action actually resolved
    the failure, enabling accuracy measurement over time.

    Args:
        category: ErrorCategory value (e.g. "transient", "auth").
        outcome: Resolution outcome ("resolved", "escalated", or "failed").
    """
    try:
        FAILURE_CLASSIFIER_ACCURACY_TOTAL.labels(category=category, outcome=outcome).inc()
    except Exception:
        pass  # Metrics must never break orchestration
