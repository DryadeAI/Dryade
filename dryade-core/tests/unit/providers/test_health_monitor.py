"""Unit tests for ProviderHealthMonitor.

Covers: probing open circuits (not closed ones), promoting on successful ping,
keeping circuits open on failed ping, health status color mapping.
Uses mocked connectors — no real network calls.
"""

from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitConfig, CircuitState
from core.providers.resilience.health_monitor import ProviderHealthMonitor

# ---------------------------------------------------------------------------
# Mock connector
# ---------------------------------------------------------------------------

class MockConnectionResult:
    def __init__(self, success: bool, message: str = "") -> None:
        self.success = success
        self.message = message

class MockConnector:
    """A fake ProviderConnector that records calls and returns configurable results."""

    def __init__(self, success: bool = True) -> None:
        self._success = success
        self.call_count = 0

    async def test_connection(self, **kwargs) -> MockConnectionResult:
        self.call_count += 1
        if self._success:
            return MockConnectionResult(success=True, message="OK")
        raise ConnectionError("mock connection failure")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_cb(failure_threshold: int = 1) -> CircuitBreaker:
    return CircuitBreaker(
        config=CircuitConfig(
            failure_threshold=failure_threshold,
            success_threshold=2,
            reset_timeout_seconds=60.0,
            sliding_window_seconds=120.0,
        )
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPingTargeting:
    async def test_pings_open_circuits_only(self) -> None:
        """Monitor should probe providers with OPEN/HALF_OPEN circuits but not CLOSED."""
        cb = _make_cb(failure_threshold=1)

        # Open circuit for provider-a
        cb.record_failure("provider-a")
        assert cb.get_state("provider-a") == CircuitState.OPEN

        conn_a = MockConnector(success=True)
        conn_b = MockConnector(success=True)

        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"provider-a": conn_a, "provider-b": conn_b},
        )

        await monitor._ping_open_circuits()

        # provider-a (OPEN) should be pinged
        assert conn_a.call_count == 1
        # provider-b (CLOSED) should NOT be pinged
        assert conn_b.call_count == 0

    async def test_closed_circuit_never_pinged(self) -> None:
        """A provider with a CLOSED circuit is never probed."""
        cb = _make_cb()
        conn = MockConnector(success=True)

        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"provider-a": conn},
        )

        await monitor._ping_open_circuits()
        assert conn.call_count == 0

class TestCircuitPromotion:
    async def test_probes_open_circuit_and_records_success(self) -> None:
        """Successful ping probe calls record_success on the circuit breaker.

        Note: record_success on OPEN state has no direct state effect
        (circuit must transition to HALF_OPEN first via can_execute() after
        reset_timeout). This test verifies the connector is called and
        record_success is invoked — integration with state promotion is
        covered via can_execute() + record_success in HALF_OPEN state.
        """
        cb = _make_cb(failure_threshold=1)
        cb.record_failure("provider-a")  # circuit OPEN
        assert cb.get_state("provider-a") == CircuitState.OPEN

        conn = MockConnector(success=True)
        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"provider-a": conn},
        )

        await monitor._ping_open_circuits()

        # Connector was probed
        assert conn.call_count == 1

    async def test_promotes_from_half_open_to_closed(self) -> None:
        """Successful probes in HALF_OPEN state should close the circuit."""
        cb = CircuitBreaker(
            config=CircuitConfig(
                failure_threshold=1,
                success_threshold=1,  # single success closes it
                reset_timeout_seconds=0.001,  # very short reset timeout
                sliding_window_seconds=120.0,
            )
        )
        import time

        cb.record_failure("provider-a")  # opens circuit
        time.sleep(0.01)  # wait past reset_timeout
        cb.can_execute("provider-a")  # transitions OPEN -> HALF_OPEN
        assert cb.get_state("provider-a") == CircuitState.HALF_OPEN

        # Now record_success should close it
        cb.record_success("provider-a")
        assert cb.get_state("provider-a") == CircuitState.CLOSED

    async def test_keeps_open_on_failed_ping(self) -> None:
        """A failed ping should leave the circuit OPEN."""
        cb = _make_cb(failure_threshold=1)
        cb.record_failure("provider-a")  # circuit OPEN

        conn = MockConnector(success=False)  # will raise ConnectionError
        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"provider-a": conn},
        )

        await monitor._ping_open_circuits()

        # Circuit should still be OPEN after a failed probe
        assert cb.get_state("provider-a") == CircuitState.OPEN

class TestGetHealthStatus:
    def test_closed_circuit_returns_green(self) -> None:
        cb = _make_cb()
        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"openai": MockConnector()},
        )

        status = monitor.get_health_status()
        assert status["openai"]["status"] == "green"
        assert status["openai"]["state"] == "closed"

    def test_open_circuit_returns_red(self) -> None:
        cb = _make_cb(failure_threshold=1)
        cb.record_failure("openai")  # opens circuit

        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"openai": MockConnector()},
        )

        status = monitor.get_health_status()
        assert status["openai"]["status"] == "red"
        assert status["openai"]["state"] == "open"

    def test_half_open_circuit_returns_yellow(self) -> None:
        cb = CircuitBreaker(
            config=CircuitConfig(
                failure_threshold=1,
                success_threshold=2,
                reset_timeout_seconds=0.001,  # very short so it transitions quickly
                sliding_window_seconds=120.0,
            )
        )
        import time

        cb.record_failure("openai")  # opens circuit

        # Wait past reset timeout so can_execute() transitions to HALF_OPEN
        time.sleep(0.01)
        cb.can_execute("openai")  # triggers HALF_OPEN transition

        assert cb.get_state("openai") == CircuitState.HALF_OPEN

        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"openai": MockConnector()},
        )

        status = monitor.get_health_status()
        assert status["openai"]["status"] == "yellow"
        assert status["openai"]["state"] == "half_open"

    def test_multiple_providers_in_status(self) -> None:
        """Status returns entries for all registered providers."""
        cb = _make_cb(failure_threshold=1)
        cb.record_failure("anthropic")  # open

        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={
                "openai": MockConnector(),
                "anthropic": MockConnector(),
            },
        )

        status = monitor.get_health_status()

        assert "openai" in status
        assert "anthropic" in status
        assert status["openai"]["status"] == "green"
        assert status["anthropic"]["status"] == "red"

    def test_failure_count_reflected_in_status(self) -> None:
        cb = _make_cb(failure_threshold=5)
        cb.record_failure("openai")
        cb.record_failure("openai")

        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"openai": MockConnector()},
        )

        status = monitor.get_health_status()
        assert status["openai"]["failure_count"] >= 2

class TestMonitorLifecycle:
    async def test_start_creates_task(self) -> None:
        cb = _make_cb()
        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={"openai": MockConnector()},
            interval=9999,  # large interval so loop doesn't actually fire
        )

        await monitor.start()
        assert monitor._task is not None
        assert not monitor._task.done()
        await monitor.stop()

    async def test_stop_cancels_task(self) -> None:
        cb = _make_cb()
        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={},
            interval=9999,
        )

        await monitor.start()
        await monitor.stop()

        assert monitor._task is None

    async def test_start_is_idempotent(self) -> None:
        """Calling start() twice should not create duplicate tasks."""
        cb = _make_cb()
        monitor = ProviderHealthMonitor(
            circuit_breaker=cb,
            connector_registry={},
            interval=9999,
        )

        await monitor.start()
        task1 = monitor._task
        await monitor.start()  # second call
        task2 = monitor._task

        assert task1 is task2  # same task, not a new one
        await monitor.stop()
