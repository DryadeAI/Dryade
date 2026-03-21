"""Per-MCP-server Circuit Breaker for preventing cascading failures.

Tracks per-server state (CLOSED/OPEN/HALF_OPEN) independently.
Uses a sliding window for failure counting and time.monotonic()
for clock-change immunity.

Thread-safe for concurrent async usage via threading.Lock.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = [
    "CircuitState",
    "CircuitConfig",
    "CircuitStats",
    "CircuitBreaker",
]

class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitConfig:
    """Configuration for the circuit breaker.

    Attributes:
        failure_threshold: Consecutive failures within the sliding window
            before the circuit opens.
        success_threshold: Consecutive successes in HALF_OPEN before
            the circuit closes again.
        reset_timeout_seconds: Seconds to wait in OPEN before allowing
            a probe request (HALF_OPEN).
        sliding_window_seconds: Window size for counting recent failures.
            Failures older than this are expired.
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    reset_timeout_seconds: float = 60.0
    sliding_window_seconds: float = 120.0

@dataclass
class CircuitStats:
    """Per-server circuit breaker statistics."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = 0.0
    total_rejections: int = 0
    failure_timestamps: list[float] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"CircuitStats(state={self.state.value}, "
            f"failures={self.failure_count}, "
            f"successes={self.success_count}, "
            f"rejections={self.total_rejections})"
        )

class CircuitBreaker:
    """Per-MCP-server circuit breaker with sliding window failure tracking.

    Each MCP server is tracked independently. When a server accumulates
    ``failure_threshold`` failures within ``sliding_window_seconds``, the
    circuit opens and immediately rejects calls for ``reset_timeout_seconds``.
    After the timeout, a single probe call is allowed (HALF_OPEN); if
    ``success_threshold`` consecutive successes occur the circuit closes.

    Thread-safe: all mutations are protected by a single ``threading.Lock``.

    Usage::

        cb = CircuitBreaker()

        if cb.can_execute("my-mcp-server"):
            try:
                result = await call_server("my-mcp-server")
                cb.record_success("my-mcp-server")
            except Exception:
                cb.record_failure("my-mcp-server")
        else:
            # Circuit open -- fast-fail
            ...
    """

    def __init__(self, config: CircuitConfig | None = None) -> None:
        self._config = config or CircuitConfig()
        self._servers: dict[str, CircuitStats] = {}
        self._lock = threading.Lock()

    # -- Public API ----------------------------------------------------------

    def can_execute(self, server_name: str) -> bool:
        """Check if a call to the given server should proceed.

        Side effects:
        - OPEN past timeout -> transitions to HALF_OPEN, returns True.
        - OPEN not past timeout -> increments total_rejections, returns False.
        """
        with self._lock:
            stats = self._ensure_server(server_name)

            if stats.state == CircuitState.CLOSED:
                return True

            if stats.state == CircuitState.OPEN:
                elapsed = time.monotonic() - stats.last_failure_time
                if elapsed >= self._config.reset_timeout_seconds:
                    self._transition(stats, server_name, CircuitState.HALF_OPEN)
                    return True
                stats.total_rejections += 1
                return False

            # HALF_OPEN -- allow probe
            return True

    def record_success(self, server_name: str) -> None:
        """Record a successful call to the given server.

        - CLOSED: resets failure count and clears failure timestamps.
        - HALF_OPEN: increments success count; transitions to CLOSED
          when ``success_threshold`` is met.
        """
        with self._lock:
            stats = self._ensure_server(server_name)

            if stats.state == CircuitState.CLOSED:
                stats.failure_count = 0
                stats.failure_timestamps.clear()
                return

            if stats.state == CircuitState.HALF_OPEN:
                stats.success_count += 1
                if stats.success_count >= self._config.success_threshold:
                    self._transition(stats, server_name, CircuitState.CLOSED)
                    stats.failure_count = 0
                    stats.success_count = 0
                    stats.failure_timestamps.clear()

    def record_failure(self, server_name: str) -> None:
        """Record a failed call to the given server.

        - CLOSED: appends failure timestamp, expires old ones, checks
          threshold. Transitions to OPEN if threshold is met.
        - HALF_OPEN: immediately transitions to OPEN (any probe failure
          reopens the circuit).
        - OPEN: no state change (already open).
        """
        now = time.monotonic()

        with self._lock:
            stats = self._ensure_server(server_name)
            stats.last_failure_time = now

            if stats.state == CircuitState.HALF_OPEN:
                self._transition(stats, server_name, CircuitState.OPEN)
                return

            if stats.state == CircuitState.OPEN:
                # Already open -- nothing to do
                return

            # CLOSED state: sliding window logic
            stats.failure_timestamps.append(now)
            self._expire_old_failures(stats, now)
            stats.failure_count = len(stats.failure_timestamps)

            if stats.failure_count >= self._config.failure_threshold:
                self._transition(stats, server_name, CircuitState.OPEN)
                # Phase 118.10: Emit threshold trip metric
                try:
                    from core.orchestrator.failure_metrics import record_circuit_breaker_trip

                    record_circuit_breaker_trip(server_name, "threshold")
                except Exception:
                    pass

    def inject_external_failure_rate(
        self, server_name: str, failure_rate: float, threshold: float = 0.7
    ) -> bool:
        """Pre-emptively open circuit based on external failure rate data.

        Used by the failure learning system to open circuits for servers
        with persistently high historical failure rates, even if the
        in-memory sliding window hasn't accumulated enough failures yet.

        Args:
            server_name: MCP server to evaluate.
            failure_rate: Historical failure rate (0.0-1.0) from FailureHistoryStore.
            threshold: Rate above which the circuit should open.

        Returns:
            True if the circuit was opened (rate >= threshold and circuit was CLOSED),
            False otherwise (already open, or rate below threshold).
        """
        if failure_rate < threshold:
            return False

        with self._lock:
            stats = self._ensure_server(server_name)
            if stats.state != CircuitState.CLOSED:
                return False  # Already open or half-open
            logger.warning(
                "Circuit pre-emptively OPEN for server '%s' "
                "(historical failure_rate=%.2f >= threshold=%.2f)",
                server_name,
                failure_rate,
                threshold,
            )
            self._transition(stats, server_name, CircuitState.OPEN)
            # Phase 118.10: Emit preemptive trip metric
            try:
                from core.orchestrator.failure_metrics import record_circuit_breaker_trip

                record_circuit_breaker_trip(server_name, "preemptive")
            except Exception:
                pass
            return True

    def get_state(self, server_name: str) -> CircuitState:
        """Get the current circuit state for a server.

        Returns ``CircuitState.CLOSED`` for unknown (untracked) servers.
        """
        with self._lock:
            stats = self._servers.get(server_name)
            if stats is None:
                return CircuitState.CLOSED
            return stats.state

    def get_all_states(self) -> dict[str, CircuitState]:
        """Get all tracked server states.

        Returns a snapshot dict mapping server name -> CircuitState.
        """
        with self._lock:
            return {name: stats.state for name, stats in self._servers.items()}

    def reset(self, server_name: str) -> None:
        """Reset circuit state for a server back to CLOSED.

        Clears all failure history, success counts, and rejection counters.
        """
        with self._lock:
            stats = self._ensure_server(server_name)
            stats.state = CircuitState.CLOSED
            stats.failure_count = 0
            stats.success_count = 0
            stats.last_failure_time = 0.0
            stats.last_state_change = time.monotonic()
            stats.total_rejections = 0
            stats.failure_timestamps.clear()
            logger.info("Circuit breaker reset for server '%s'", server_name)

    # -- Internal helpers (exposed for testing) ------------------------------

    def _get_stats(self, server_name: str) -> CircuitStats:
        """Return internal CircuitStats for a server (for testing/observability)."""
        with self._lock:
            return self._ensure_server(server_name)

    # -- Private helpers -----------------------------------------------------

    def _ensure_server(self, server_name: str) -> CircuitStats:
        """Get or create stats for a server. Caller must hold ``_lock``."""
        if server_name not in self._servers:
            self._servers[server_name] = CircuitStats(
                last_state_change=time.monotonic(),
            )
        return self._servers[server_name]

    def _expire_old_failures(self, stats: CircuitStats, now: float) -> None:
        """Remove failure timestamps outside the sliding window.

        Caller must hold ``_lock``.
        """
        cutoff = now - self._config.sliding_window_seconds
        stats.failure_timestamps = [ts for ts in stats.failure_timestamps if ts > cutoff]

    def _transition(self, stats: CircuitStats, server_name: str, new_state: CircuitState) -> None:
        """Transition a server's circuit to a new state.

        Caller must hold ``_lock``.
        """
        old_state = stats.state
        stats.state = new_state
        stats.last_state_change = time.monotonic()

        if new_state == CircuitState.HALF_OPEN:
            stats.success_count = 0

        if new_state == CircuitState.OPEN:
            logger.warning(
                "Circuit OPEN for server '%s' (was %s, failures=%d)",
                server_name,
                old_state.value,
                stats.failure_count,
            )
        elif new_state == CircuitState.HALF_OPEN:
            logger.info(
                "Circuit HALF_OPEN for server '%s' (probe allowed)",
                server_name,
            )
        elif new_state == CircuitState.CLOSED:
            logger.info(
                "Circuit CLOSED for server '%s' (recovered)",
                server_name,
            )

        # Phase 118.10: Emit circuit breaker state gauge
        try:
            from core.orchestrator.failure_metrics import update_circuit_breaker_state

            update_circuit_breaker_state(server_name, new_state.value)
        except Exception:
            pass
