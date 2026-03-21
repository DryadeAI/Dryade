"""SLO timing assertion tests for the failure pipeline.

Verifies that deterministic classification, circuit breaker trips,
and recovery decisions complete within the SLO targets defined in
core/orchestrator/failure_metrics.py.

All timing assertions use a 3x multiplier for CI safety to avoid
flaky failures on slow/shared CI runners.
"""

import statistics
import time

from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitConfig, CircuitState
from core.orchestrator.failure_classifier import FailureClassifier
from core.orchestrator.failure_metrics import (
    SLO_CIRCUIT_BREAKER_TRIP_MS,
    SLO_FAILURE_DETECTION_MS,
    SLO_RECOVERY_DECISION_DETERMINISTIC_MS,
)
from core.orchestrator.models import (
    ErrorCategory,
    ToolError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_error(
    message: str,
    error_type: str = "RuntimeError",
    http_status: int | None = None,
) -> ToolError:
    """Create a ToolError for timing tests."""
    return ToolError(
        tool_name="test-tool",
        server_name="test-server",
        error_type=error_type,
        message=message,
        http_status=http_status,
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_slo_deterministic_classification_under_100ms():
    """Each classification completes in < SLO_FAILURE_DETECTION_MS * 3."""
    errors = [
        _make_tool_error("tool timed out", error_type="TimeoutError"),
        _make_tool_error("HTTP 429 Too Many Requests", http_status=429),
        _make_tool_error("HTTP 401 Unauthorized", http_status=401),
        _make_tool_error("Connection refused", error_type="ConnectionError"),
        _make_tool_error("HTTP 400 Bad Request", http_status=400),
    ]

    threshold_ms = SLO_FAILURE_DETECTION_MS * 3  # 300ms CI safety

    for error in errors:
        start = time.perf_counter()
        classification = FailureClassifier.classify(error)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"Classify '{error.message}': {elapsed_ms:.2f}ms -> {classification.category.value}")
        assert elapsed_ms < threshold_ms, (
            f"Classification of '{error.message}' took {elapsed_ms:.1f}ms, "
            f"SLO target is {SLO_FAILURE_DETECTION_MS}ms (threshold {threshold_ms}ms)"
        )
        # Deterministic classifications should have confidence 1.0
        assert classification.confidence == 1.0

def test_slo_circuit_breaker_trip_under_1s():
    """Circuit breaker trips in < SLO_CIRCUIT_BREAKER_TRIP_MS * 3 after threshold failures."""
    threshold_ms = SLO_CIRCUIT_BREAKER_TRIP_MS * 3  # 3000ms CI safety

    cb = CircuitBreaker(config=CircuitConfig(failure_threshold=3))

    start = time.perf_counter()
    for _ in range(3):
        cb.record_failure("test-server")
    elapsed_ms = (time.perf_counter() - start) * 1000

    state = cb.get_state("test-server")

    print(f"Circuit breaker trip: {elapsed_ms:.2f}ms -> {state.value}")
    assert state == CircuitState.OPEN, f"Expected OPEN, got {state.value}"
    assert elapsed_ms < threshold_ms, (
        f"Circuit breaker trip took {elapsed_ms:.1f}ms, "
        f"SLO target is {SLO_CIRCUIT_BREAKER_TRIP_MS}ms (threshold {threshold_ms}ms)"
    )

def test_slo_deterministic_recovery_decision_under_500ms():
    """Full deterministic path (classify + check suggested_action) < SLO * 3."""
    threshold_ms = SLO_RECOVERY_DECISION_DETERMINISTIC_MS * 3  # 1500ms CI safety

    error = _make_tool_error("HTTP 429 Too Many Requests", http_status=429)

    start = time.perf_counter()
    classification = FailureClassifier.classify(error)
    # Simulate recovery decision: check suggested_action
    action = classification.suggested_action
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"Recovery decision: {elapsed_ms:.2f}ms -> {action.value}")
    assert elapsed_ms < threshold_ms, (
        f"Deterministic recovery decision took {elapsed_ms:.1f}ms, "
        f"SLO target is {SLO_RECOVERY_DECISION_DETERMINISTIC_MS}ms (threshold {threshold_ms}ms)"
    )

def test_slo_all_classifications_deterministic():
    """ALL Tier 1 classifications return confidence == 1.0 and valid ErrorCategory."""
    # One error per classification priority to cover all rule types
    test_cases = [
        # Priority 1: HTTP status code
        (_make_tool_error("server error", http_status=500), ErrorCategory.TRANSIENT),
        (_make_tool_error("rate limited", http_status=429), ErrorCategory.RATE_LIMIT),
        (_make_tool_error("unauthorized", http_status=401), ErrorCategory.AUTH),
        (_make_tool_error("forbidden", http_status=403), ErrorCategory.AUTH),
        # Priority 2: Exception type
        (_make_tool_error("timeout", error_type="TimeoutError"), ErrorCategory.TRANSIENT),
        (_make_tool_error("conn error", error_type="ConnectionError"), ErrorCategory.CONNECTION),
        (_make_tool_error("parse error", error_type="JSONDecodeError"), ErrorCategory.PARSE_ERROR),
        # Priority 3: Message patterns
        (_make_tool_error("rate limit exceeded"), ErrorCategory.RATE_LIMIT),
        (_make_tool_error("unauthorized access"), ErrorCategory.AUTH),
        (_make_tool_error("permission denied"), ErrorCategory.PERMISSION),
        (_make_tool_error("context length exceeded"), ErrorCategory.CONTEXT_OVERFLOW),
        (_make_tool_error("connection refused"), ErrorCategory.CONNECTION),
    ]

    for error, expected_category in test_cases:
        classification = FailureClassifier.classify(error)
        assert classification.confidence == 1.0, (
            f"Expected confidence 1.0 for '{error.message}' "
            f"(type={error.error_type}), got {classification.confidence}"
        )
        assert classification.category == expected_category, (
            f"Expected {expected_category.value} for '{error.message}', "
            f"got {classification.category.value}"
        )

def test_slo_timing_with_repeated_measurements():
    """p99 latency of 100 classifications < SLO_FAILURE_DETECTION_MS."""
    error = _make_tool_error("HTTP 429 Too Many Requests", http_status=429)

    measurements_ms: list[float] = []
    for _ in range(100):
        start = time.perf_counter()
        FailureClassifier.classify(error)
        elapsed_ms = (time.perf_counter() - start) * 1000
        measurements_ms.append(elapsed_ms)

    quantiles = statistics.quantiles(measurements_ms, n=100)
    p99 = quantiles[98]  # 99th percentile
    median = statistics.median(measurements_ms)

    print(f"Classification p99: {p99:.3f}ms, median: {median:.3f}ms")
    assert p99 < SLO_FAILURE_DETECTION_MS, (
        f"p99 latency {p99:.3f}ms exceeds SLO target of {SLO_FAILURE_DETECTION_MS}ms"
    )
