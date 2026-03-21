"""ProviderHealthMonitor — background task that pings open circuits.

Runs on a configurable interval (default 60s). For each provider whose
circuit is OPEN or HALF_OPEN, attempts a test_connection() probe. On
success, records success to the circuit breaker (may close it). On
failure, leaves circuit open for the next cycle.
"""

import asyncio
import logging

from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitState

__all__ = [
    "ProviderHealthMonitor",
]

logger = logging.getLogger(__name__)

class ProviderHealthMonitor:
    """Background task that pings open circuits to detect provider recovery.

    Usage::

        monitor = ProviderHealthMonitor(circuit_breaker, connector_registry)
        await monitor.start()
        # ... app running ...
        await monitor.stop()

    Args:
        circuit_breaker: Shared CircuitBreaker instance (PROVIDER_CIRCUIT_BREAKER).
        connector_registry: Dict mapping provider name -> ProviderConnector instance.
        interval: Seconds between health check cycles (default 60).
    """

    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        connector_registry: dict,
        interval: float = 60.0,
    ) -> None:
        self._cb = circuit_breaker
        self._connector_registry = connector_registry
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background health monitoring loop."""
        if self._task is not None and not self._task.done():
            logger.debug("ProviderHealthMonitor already running")
            return

        self._task = asyncio.create_task(self._loop(), name="provider-health-monitor")
        logger.info(
            f"ProviderHealthMonitor started (interval={self._interval:.0f}s, "
            f"providers={list(self._connector_registry.keys())})"
        )

    async def stop(self) -> None:
        """Stop the background health monitoring loop."""
        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("ProviderHealthMonitor stopped")

    async def _loop(self) -> None:
        """Health check loop — runs indefinitely until cancelled."""
        while True:
            await asyncio.sleep(self._interval)
            await self._ping_open_circuits()

    async def _ping_open_circuits(self) -> None:
        """Probe each provider with an open or half-open circuit."""
        for provider_name, connector in self._connector_registry.items():
            # We track circuits by "provider:model" key, but health monitor
            # tracks by provider name. Use the provider name as the CB key
            # for health pinging purposes.
            state = self._cb.get_state(provider_name)

            if state == CircuitState.CLOSED:
                # Circuit healthy — no probe needed
                continue

            logger.debug("Probing %s (circuit=%s)", provider_name, state.value)

            try:
                result = await connector.test_connection()
                if result.success:
                    self._cb.record_success(provider_name)
                    logger.info("Provider %s recovered (circuit probe succeeded)", provider_name)
                else:
                    logger.debug("Provider %s probe failed: %s", provider_name, result.message)
            except Exception as exc:
                logger.debug("Provider %s probe raised exception: %s", provider_name, exc)
                # Leave circuit open — retry next cycle

    def get_health_status(self) -> dict[str, dict]:
        """Return health status for all known providers.

        Returns:
            Dict mapping provider_name -> {
                "status": "green" | "yellow" | "red",
                "state": "closed" | "open" | "half_open",
                "failure_count": int,
                "last_failure_time": float | None,
            }
        """
        status = {}

        for provider_name in self._connector_registry:
            stats = self._cb._get_stats(provider_name)

            if stats.state == CircuitState.CLOSED:
                color = "green"
            elif stats.state == CircuitState.HALF_OPEN:
                color = "yellow"
            else:
                color = "red"

            status[provider_name] = {
                "status": color,
                "state": stats.state.value,
                "failure_count": stats.failure_count,
                "last_failure_time": stats.last_failure_time if stats.last_failure_time else None,
            }

        return status
