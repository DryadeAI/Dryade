"""LLM Provider Resilience module.

Provides automatic failover across LLM providers using a configurable
fallback chain. When a provider fails (timeout, rate limit, server error),
the FailoverEngine transparently tries the next provider in the user's chain.

Key components:

    FallbackChain / FallbackChainEntry
        Serializable ordered list of (provider, model) pairs.

    execute_with_fallback()
        Async function that iterates the chain, skipping open circuits,
        and fails over on retryable errors.

    PROVIDER_CIRCUIT_BREAKER
        Module-level CircuitBreaker with aggressive settings (1 failure opens,
        60s reset). Shared across all provider call sites.

    ProviderHealthMonitor
        Background task that pings open circuits every 60s using
        ProviderConnector.test_connection(). Promotes circuits to CLOSED
        on success.

    FailoverEvent / log_failover_event()
        Structured logging for provider failover events.

    AllProvidersExhaustedError
        Raised when all providers in the chain have failed.
"""

# Aliases for ergonomic import compatibility
# "FailoverEngine" is a module-level alias for the module that provides execute_with_fallback
import core.providers.resilience.failover_engine as FailoverEngine  # noqa: N814
from core.providers.resilience.events import FailoverEvent, log_failover_event
from core.providers.resilience.failover_engine import (
    PROVIDER_CIRCUIT_BREAKER,
    AllProvidersExhaustedError,
    execute_with_fallback,
)
from core.providers.resilience.fallback_chain import (
    FallbackChain,
    FallbackChainEntry,
    get_fallback_chain,
    resolve_chain_configs,
    save_fallback_chain,
)
from core.providers.resilience.health_monitor import ProviderHealthMonitor

# "HealthMonitor" is a class alias for ProviderHealthMonitor
HealthMonitor = ProviderHealthMonitor

__all__ = [
    # Failover chain types
    "FallbackChainEntry",
    "FallbackChain",
    # Chain persistence
    "get_fallback_chain",
    "save_fallback_chain",
    "resolve_chain_configs",
    # Failover engine
    "execute_with_fallback",
    "AllProvidersExhaustedError",
    "PROVIDER_CIRCUIT_BREAKER",
    "FailoverEngine",
    # Health monitoring
    "ProviderHealthMonitor",
    "HealthMonitor",
    # Event logging
    "FailoverEvent",
    "log_failover_event",
]
