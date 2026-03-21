"""Performance regression tests for the failure pipeline.

Measures latency of complete failure handling paths to catch major
regressions in future changes. Uses generous bounds (5-10x SLO
targets) to avoid CI flakiness while still catching regressions.

All tests use time.perf_counter() and print actual timings for
debugging. Each test has @pytest.mark.timeout(30) as a hard ceiling.
"""

import time

import pytest

from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitConfig, CircuitState
from core.orchestrator.failure_classifier import FailureClassifier
from core.orchestrator.failure_metrics import (
    SLO_RECOVERY_DECISION_DETERMINISTIC_MS,
)
from core.orchestrator.models import (
    ToolError,
)
from core.orchestrator.soft_failure_detector import (
    ExecutionTracker,
    SoftFailureDetector,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_error(
    message: str,
    error_type: str = "RuntimeError",
    http_status: int | None = None,
    tool_name: str = "perf-tool",
    server_name: str = "perf-server",
) -> ToolError:
    """Create a ToolError for performance tests."""
    return ToolError(
        tool_name=tool_name,
        server_name=server_name,
        error_type=error_type,
        message=message,
        http_status=http_status,
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.timeout(30)
def test_perf_classify_many_errors_in_bulk():
    """Classify 100 errors: total < 1s, no single classification > 50ms."""
    errors = [
        _make_tool_error(
            f"Error {i}", http_status=(429 if i % 3 == 0 else 500 if i % 3 == 1 else None)
        )
        for i in range(100)
    ]

    max_single_ms = 0.0
    start = time.perf_counter()
    for error in errors:
        t0 = time.perf_counter()
        FailureClassifier.classify(error)
        elapsed_single = (time.perf_counter() - t0) * 1000
        max_single_ms = max(max_single_ms, elapsed_single)
    total_ms = (time.perf_counter() - start) * 1000

    print(f"Elapsed: {total_ms:.1f}ms total, {max_single_ms:.2f}ms max single")
    assert total_ms < 1000, f"Bulk classification took {total_ms:.1f}ms, expected <1000ms"
    assert max_single_ms < 50, f"Single classification took {max_single_ms:.2f}ms, expected <50ms"

@pytest.mark.timeout(30)
def test_perf_circuit_breaker_under_load():
    """Record 1000 failures across 10 servers: total < 5s, all OPEN."""
    cb = CircuitBreaker(config=CircuitConfig(failure_threshold=5))

    servers = [f"server-{i}" for i in range(10)]

    start = time.perf_counter()
    for _ in range(100):
        for server in servers:
            cb.record_failure(server)
    total_ms = (time.perf_counter() - start) * 1000

    print(f"Elapsed: {total_ms:.1f}ms for 1000 failures across 10 servers")
    assert total_ms < 5000, f"Circuit breaker load test took {total_ms:.1f}ms, expected <5000ms"

    # All servers should be OPEN after 100 failures each (threshold=5)
    for server in servers:
        state = cb.get_state(server)
        assert state == CircuitState.OPEN, f"Expected {server} OPEN, got {state.value}"

@pytest.mark.timeout(30)
def test_perf_soft_failure_detector_throughput():
    """SoftFailureDetector.detect() 100 times with various results: total < 2s."""
    detector = SoftFailureDetector()
    tracker = ExecutionTracker()

    results = [
        ("", "find files"),  # empty
        ("done", "complete task"),  # valid short
        ("x" * 1000, "analyze data"),  # normal
        (None, "fetch resource"),  # None
        ('{"data": [1, 2, 3', "parse JSON"),  # truncated
    ]

    start = time.perf_counter()
    for i in range(100):
        result_val, task_desc = results[i % len(results)]
        detector.detect(
            result_value=result_val,
            task_description=task_desc,
            tool_name=f"tool-{i}",
            tracker=tracker,
            arguments={"query": f"test-{i}"},
        )
        tracker.record(f"tool-{i}", {"query": f"test-{i}"})
    total_ms = (time.perf_counter() - start) * 1000

    print(f"Elapsed: {total_ms:.1f}ms for 100 soft failure detections")
    assert total_ms < 2000, f"Soft failure detector took {total_ms:.1f}ms, expected <2000ms"

@pytest.mark.timeout(30)
def test_perf_prevention_pipeline_latency():
    """PreventionPipeline scaffold (checks disabled): 50 runs < 1s."""
    from core.orchestrator.prevention import PreventionPipeline

    pipeline = PreventionPipeline()

    start = time.perf_counter()
    for _ in range(50):
        # validate_tool_schema with prevention disabled returns None (fast path)
        result = pipeline.validate_tool_schema("test-server", "test-tool", {"arg": "val"})
        # get_prompt_hints with prevention disabled returns [] (fast path)
        hints = pipeline.get_prompt_hints()
    total_ms = (time.perf_counter() - start) * 1000

    print(f"Elapsed: {total_ms:.1f}ms for 50 prevention pipeline runs (disabled checks)")
    assert total_ms < 1000, f"Prevention pipeline took {total_ms:.1f}ms, expected <1000ms"

@pytest.mark.timeout(30)
def test_perf_full_classify_and_recover_path():
    """Full deterministic path (classify + check action) x50: p95 < SLO * 5."""
    threshold_ms = SLO_RECOVERY_DECISION_DETERMINISTIC_MS * 5  # 2500ms

    measurements_ms: list[float] = []
    for i in range(50):
        # Alternate between different error types
        if i % 3 == 0:
            error = _make_tool_error("HTTP 429", http_status=429)
        elif i % 3 == 1:
            error = _make_tool_error("timeout", error_type="TimeoutError")
        else:
            error = _make_tool_error("connection refused")

        start = time.perf_counter()
        classification = FailureClassifier.classify(error)
        action = classification.suggested_action
        # Simulate: if RETRY, a simple decision check
        if action.value == "retry":
            _ = classification.category.value
        elapsed_ms = (time.perf_counter() - start) * 1000
        measurements_ms.append(elapsed_ms)

    measurements_ms.sort()
    p95_idx = int(len(measurements_ms) * 0.95) - 1
    p95 = measurements_ms[p95_idx]
    avg = sum(measurements_ms) / len(measurements_ms)

    print(f"Elapsed: p95={p95:.3f}ms, avg={avg:.3f}ms for full classify+recover path")
    assert p95 < threshold_ms, (
        f"p95 latency {p95:.3f}ms exceeds threshold {threshold_ms}ms "
        f"(SLO={SLO_RECOVERY_DECISION_DETERMINISTIC_MS}ms * 5)"
    )

@pytest.mark.timeout(30)
def test_perf_observation_history_with_large_context():
    """Add 100 observations (1000 chars each), format_for_llm: < 2s."""
    from core.orchestrator.models import OrchestrationObservation
    from core.orchestrator.observation import ObservationHistory

    history = ObservationHistory()

    # Add 100 observations with 1000-char results
    for i in range(100):
        obs = OrchestrationObservation(
            agent_name=f"agent-{i % 5}",
            task=f"Process data batch {i}",
            result="x" * 1000,
            success=i % 4 != 0,  # 75% success rate
            duration_ms=i * 10,
        )
        history.add(obs)

    start = time.perf_counter()
    formatted = history.format_for_llm()
    total_ms = (time.perf_counter() - start) * 1000

    print(f"Elapsed: {total_ms:.1f}ms to format 100 observations ({len(formatted)} chars)")
    assert total_ms < 2000, f"format_for_llm took {total_ms:.1f}ms, expected <2000ms"
    assert len(formatted) > 0, "Formatted output should not be empty"
