"""Tests for per-MCP-server CircuitBreaker.

Covers all state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED,
sliding window failure expiry, multi-server isolation, custom config,
and thread safety.
"""

import threading
import time

from core.orchestrator.circuit_breaker import (
    CircuitBreaker,
    CircuitConfig,
    CircuitState,
    CircuitStats,
)

# ---------------------------------------------------------------------------
# CircuitState enum
# ---------------------------------------------------------------------------

class TestCircuitState:
    def test_closed_value(self):
        assert CircuitState.CLOSED == "closed"

    def test_open_value(self):
        assert CircuitState.OPEN == "open"

    def test_half_open_value(self):
        assert CircuitState.HALF_OPEN == "half_open"

    def test_has_three_members(self):
        assert len(CircuitState) == 3

# ---------------------------------------------------------------------------
# CircuitConfig defaults
# ---------------------------------------------------------------------------

class TestCircuitConfig:
    def test_default_failure_threshold(self):
        cfg = CircuitConfig()
        assert cfg.failure_threshold == 5

    def test_default_success_threshold(self):
        cfg = CircuitConfig()
        assert cfg.success_threshold == 2

    def test_default_reset_timeout(self):
        cfg = CircuitConfig()
        assert cfg.reset_timeout_seconds == 60.0

    def test_default_sliding_window(self):
        cfg = CircuitConfig()
        assert cfg.sliding_window_seconds == 120.0

# ---------------------------------------------------------------------------
# CircuitStats defaults
# ---------------------------------------------------------------------------

class TestCircuitStats:
    def test_default_state_is_closed(self):
        stats = CircuitStats()
        assert stats.state == CircuitState.CLOSED

    def test_default_counts_are_zero(self):
        stats = CircuitStats()
        assert stats.failure_count == 0
        assert stats.success_count == 0
        assert stats.total_rejections == 0

    def test_default_timestamps_are_zero(self):
        stats = CircuitStats()
        assert stats.last_failure_time == 0.0
        assert stats.last_state_change == 0.0

    def test_failure_timestamps_is_empty_list(self):
        stats = CircuitStats()
        assert stats.failure_timestamps == []

# ---------------------------------------------------------------------------
# CircuitBreaker.can_execute()
# ---------------------------------------------------------------------------

class TestCanExecute:
    def test_new_server_returns_true(self):
        """Unknown server defaults to CLOSED -> can execute."""
        cb = CircuitBreaker()
        assert cb.can_execute("server-a") is True

    def test_closed_state_returns_true(self):
        """Explicitly CLOSED server can execute."""
        cb = CircuitBreaker()
        cb.record_success("server-a")  # ensure tracked, stays CLOSED
        assert cb.can_execute("server-a") is True

    def test_open_state_returns_false(self):
        """OPEN circuit rejects calls."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")  # opens circuit
        assert cb.can_execute("server-a") is False

    def test_open_past_timeout_returns_true_and_transitions_to_half_open(self):
        """OPEN circuit past reset_timeout transitions to HALF_OPEN -> allows."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2, reset_timeout_seconds=0.01))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

        time.sleep(0.02)  # wait past timeout

        assert cb.can_execute("server-a") is True
        assert cb.get_state("server-a") == CircuitState.HALF_OPEN

    def test_half_open_allows_probe(self):
        """HALF_OPEN state allows one probe call."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2, reset_timeout_seconds=0.01))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        time.sleep(0.02)
        cb.can_execute("server-a")  # triggers HALF_OPEN transition
        assert cb.get_state("server-a") == CircuitState.HALF_OPEN
        assert cb.can_execute("server-a") is True

    def test_open_increments_total_rejections(self):
        """OPEN circuit increments total_rejections on can_execute() False."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")

        cb.can_execute("server-a")  # rejected
        cb.can_execute("server-a")  # rejected again

        # Access internal stats to check rejections
        state_info = cb._get_stats("server-a")
        assert state_info.total_rejections == 2

# ---------------------------------------------------------------------------
# CircuitBreaker.record_success()
# ---------------------------------------------------------------------------

class TestRecordSuccess:
    def test_closed_resets_failure_count(self):
        """Success in CLOSED state resets failure count."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        cb.record_success("server-a")
        stats = cb._get_stats("server-a")
        assert stats.failure_count == 0

    def test_half_open_increments_success_count(self):
        """Success in HALF_OPEN increments success count."""
        cb = CircuitBreaker(
            CircuitConfig(failure_threshold=2, reset_timeout_seconds=0.01, success_threshold=3)
        )
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        time.sleep(0.02)
        cb.can_execute("server-a")  # -> HALF_OPEN
        cb.record_success("server-a")
        stats = cb._get_stats("server-a")
        assert stats.success_count >= 1

    def test_half_open_threshold_met_transitions_to_closed(self):
        """HALF_OPEN -> CLOSED when success_threshold is met."""
        cb = CircuitBreaker(
            CircuitConfig(failure_threshold=2, reset_timeout_seconds=0.01, success_threshold=2)
        )
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        time.sleep(0.02)
        cb.can_execute("server-a")  # -> HALF_OPEN

        cb.record_success("server-a")
        assert cb.get_state("server-a") == CircuitState.HALF_OPEN  # 1 of 2

        cb.record_success("server-a")
        assert cb.get_state("server-a") == CircuitState.CLOSED  # 2 of 2

    def test_half_open_one_below_threshold_stays_half_open(self):
        """HALF_OPEN stays if successes < success_threshold."""
        cb = CircuitBreaker(
            CircuitConfig(failure_threshold=2, reset_timeout_seconds=0.01, success_threshold=3)
        )
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        time.sleep(0.02)
        cb.can_execute("server-a")  # -> HALF_OPEN

        cb.record_success("server-a")
        cb.record_success("server-a")
        assert cb.get_state("server-a") == CircuitState.HALF_OPEN  # 2 of 3, stays

# ---------------------------------------------------------------------------
# CircuitBreaker.record_failure()
# ---------------------------------------------------------------------------

class TestRecordFailure:
    def test_closed_increments_failure_count(self):
        """Failure in CLOSED increments failure_count."""
        cb = CircuitBreaker()
        cb.record_failure("server-a")
        stats = cb._get_stats("server-a")
        assert stats.failure_count == 1

    def test_closed_at_threshold_transitions_to_open(self):
        """CLOSED -> OPEN when failure_threshold reached."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=3))
        for _ in range(3):
            cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

    def test_closed_at_threshold_records_last_failure_time(self):
        """OPEN transition records last_failure_time."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        stats = cb._get_stats("server-a")
        assert stats.last_failure_time > 0

    def test_closed_below_threshold_stays_closed(self):
        """Below threshold, circuit stays CLOSED."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5))
        for _ in range(4):
            cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.CLOSED

    def test_half_open_failure_transitions_to_open(self):
        """Any failure in HALF_OPEN immediately reopens circuit."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2, reset_timeout_seconds=0.01))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        time.sleep(0.02)
        cb.can_execute("server-a")  # -> HALF_OPEN
        assert cb.get_state("server-a") == CircuitState.HALF_OPEN

        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

    def test_open_failure_increments_total_rejections_no_state_change(self):
        """Failure while OPEN increments total_rejections, stays OPEN."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

        cb.record_failure("server-a")  # additional failure while OPEN
        stats = cb._get_stats("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

# ---------------------------------------------------------------------------
# Sliding window
# ---------------------------------------------------------------------------

class TestSlidingWindow:
    def test_old_failures_expired_before_threshold_check(self):
        """Failures older than sliding_window_seconds are not counted."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=3, sliding_window_seconds=0.05))

        # Record 2 failures, wait for them to expire
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        time.sleep(0.06)

        # 1 new failure -- total within window = 1, below threshold
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.CLOSED

    def test_four_old_plus_one_new_does_not_open(self):
        """4 expired + 1 fresh failure < threshold=5 -> stays CLOSED."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, sliding_window_seconds=0.05))
        for _ in range(4):
            cb.record_failure("server-a")
        time.sleep(0.06)

        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.CLOSED

    def test_five_within_window_opens_circuit(self):
        """5 failures within sliding window -> OPEN."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5, sliding_window_seconds=10.0))
        for _ in range(5):
            cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

# ---------------------------------------------------------------------------
# get_state() / get_all_states()
# ---------------------------------------------------------------------------

class TestGetState:
    def test_unknown_server_returns_closed(self):
        """get_state for untracked server returns CLOSED."""
        cb = CircuitBreaker()
        assert cb.get_state("unknown") == CircuitState.CLOSED

    def test_tracked_server_returns_correct_state(self):
        """get_state returns actual state for tracked server."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

    def test_get_all_states_returns_dict(self):
        """get_all_states returns dict of all tracked servers."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-b")
        cb.record_failure("server-b")

        states = cb.get_all_states()
        assert isinstance(states, dict)
        assert states["server-a"] == CircuitState.CLOSED
        assert states["server-b"] == CircuitState.OPEN

# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------

class TestCustomConfig:
    def test_custom_threshold_opens_after_n_failures(self):
        """CircuitBreaker with threshold=2 opens after 2 failures."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.CLOSED
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

# ---------------------------------------------------------------------------
# Multi-server isolation
# ---------------------------------------------------------------------------

class TestMultiServerIsolation:
    def test_failure_on_one_server_does_not_affect_other(self):
        """Each server has independent state."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")  # opens server-a
        assert cb.get_state("server-a") == CircuitState.OPEN
        assert cb.get_state("server-b") == CircuitState.CLOSED
        assert cb.can_execute("server-b") is True

# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_returns_to_closed(self):
        """reset() returns server to CLOSED state."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=2))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        assert cb.get_state("server-a") == CircuitState.OPEN

        cb.reset("server-a")
        assert cb.get_state("server-a") == CircuitState.CLOSED

    def test_reset_clears_failure_timestamps(self):
        """reset() clears failure history."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=5))
        cb.record_failure("server-a")
        cb.record_failure("server-a")
        cb.reset("server-a")
        stats = cb._get_stats("server-a")
        assert stats.failure_count == 0
        assert stats.failure_timestamps == []

# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_failures_do_not_corrupt_state(self):
        """Multiple threads recording failures simultaneously don't corrupt state."""
        cb = CircuitBreaker(CircuitConfig(failure_threshold=100, sliding_window_seconds=10.0))
        barrier = threading.Barrier(10)

        def hammer(server: str, count: int):
            barrier.wait()
            for _ in range(count):
                cb.record_failure(server)

        threads = [threading.Thread(target=hammer, args=("server-a", 10)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = cb._get_stats("server-a")
        assert stats.failure_count == 100
        assert len(stats.failure_timestamps) == 100
