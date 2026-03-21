# Copyright (c) 2025-2026 Dryade SAS
# Licensed under the Dryade Enterprise Edition License. See LICENSE_EE.md.

"""Plugin Capability Registry.

Provides cross-plugin discovery without direct imports.

Problem: Plugins are isolated. kpi_monitor needs to know which plugins
provide analytics data but cannot import templates code.

Solution: Plugins register capabilities at startup. Other plugins query the
registry at runtime to discover providers.

Thread-safe singleton pattern matches core/adapters/registry.py.

Usage:
    # In plugin register() method:
    from core.ee.plugin_capabilities import (
        CapabilityRegistration,
        PluginCapability,
        get_capability_registry,
    )

    registry = get_capability_registry()
    registry.register(CapabilityRegistration(
        plugin_name="templates",
        capability=PluginCapability.ANALYTICS_PROVIDER,
        api_endpoint="/api/templates",
        metadata={"dimensions": ["organization", "template"]}
    ))

    # In kpi_monitor:
    providers = registry.get_providers(PluginCapability.ANALYTICS_PROVIDER)
    for p in providers:
        # Call p.api_endpoint to fetch analytics
"""

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class PluginCapability(Enum):
    """Capabilities that plugins can advertise.

    Used for runtime discovery between isolated plugins.
    """

    # Plugin provides analytics data via API (usage metrics, trends, etc.)
    ANALYTICS_PROVIDER = "analytics_provider"

    # Plugin provides a cost grouping dimension (e.g., by project, by user)
    COST_DIMENSION = "cost_dimension"

    # Plugin exposes Prometheus-style metrics for scraping
    METRICS_SOURCE = "metrics_source"

    # Plugin provides clarification for planner requests
    CLARIFICATION_PROVIDER = "clarification_provider"

@dataclass
class CapabilityRegistration:
    """Registration record for a plugin capability.

    Attributes:
        plugin_name: Unique name of the plugin
        capability: Which capability the plugin provides
        api_endpoint: Base API endpoint for this capability
        metadata: Additional info (supported dimensions, metrics, sub-endpoints)
    """

    plugin_name: str
    capability: PluginCapability
    api_endpoint: str
    metadata: dict = field(default_factory=dict)

class PluginCapabilityRegistry:
    """Thread-safe registry for plugin capabilities.

    Plugins register capabilities during startup. Other plugins query
    the registry at runtime to discover providers without direct imports.

    This enables loose coupling between plugins that would otherwise need
    to import each other's code directly.
    """

    def __init__(self):
        """Initialize empty registry with thread lock."""
        self._registrations: list[CapabilityRegistration] = []
        self._lock = threading.Lock()

    def register(self, registration: CapabilityRegistration) -> None:
        """Register a plugin capability.

        Thread-safe. Logs a warning if the same plugin registers the same
        capability twice (idempotent - second registration is ignored).

        Args:
            registration: Capability registration details
        """
        with self._lock:
            # Check for duplicate registration
            for existing in self._registrations:
                if (
                    existing.plugin_name == registration.plugin_name
                    and existing.capability == registration.capability
                ):
                    logger.debug(
                        f"Plugin '{registration.plugin_name}' already registered "
                        f"capability {registration.capability.value}, skipping"
                    )
                    return

            self._registrations.append(registration)
            logger.info(
                f"Plugin '{registration.plugin_name}' registered capability "
                f"{registration.capability.value} at {registration.api_endpoint}"
            )

    def unregister(self, plugin_name: str) -> int:
        """Unregister all capabilities for a plugin.

        Thread-safe.

        Args:
            plugin_name: Name of the plugin to unregister

        Returns:
            Number of capabilities removed
        """
        with self._lock:
            initial_count = len(self._registrations)
            self._registrations = [r for r in self._registrations if r.plugin_name != plugin_name]
            removed = initial_count - len(self._registrations)
            if removed > 0:
                logger.info(f"Unregistered {removed} capability(ies) for plugin '{plugin_name}'")
            return removed

    def get_providers(self, capability: PluginCapability) -> list[CapabilityRegistration]:
        """Get all plugins that provide a specific capability.

        Thread-safe.

        Args:
            capability: The capability to query

        Returns:
            List of registrations for plugins providing this capability
        """
        with self._lock:
            return [r for r in self._registrations if r.capability == capability]

    def has_capability(self, capability: PluginCapability) -> bool:
        """Check if any plugin provides a capability.

        Thread-safe.

        Args:
            capability: The capability to check

        Returns:
            True if at least one plugin provides this capability
        """
        with self._lock:
            return any(r.capability == capability for r in self._registrations)

    def get_all_registrations(self) -> list[CapabilityRegistration]:
        """Get all capability registrations.

        Thread-safe.

        Returns:
            Copy of all registrations
        """
        with self._lock:
            return list(self._registrations)

    def clear(self) -> None:
        """Clear all registrations.

        Thread-safe. Useful for testing.
        """
        with self._lock:
            self._registrations.clear()
            logger.debug("Capability registry cleared")

    def __len__(self) -> int:
        """Return number of registered capabilities."""
        with self._lock:
            return len(self._registrations)

# Global singleton instance
_capability_registry: PluginCapabilityRegistry | None = None
_singleton_lock = threading.Lock()

def get_capability_registry() -> PluginCapabilityRegistry:
    """Get or create the global capability registry singleton.

    Thread-safe initialization.

    Returns:
        Global PluginCapabilityRegistry instance
    """
    global _capability_registry
    if _capability_registry is None:
        with _singleton_lock:
            # Double-check locking pattern
            if _capability_registry is None:
                _capability_registry = PluginCapabilityRegistry()
                logger.debug("Created plugin capability registry singleton")
    return _capability_registry

def reset_capability_registry() -> None:
    """Reset the global registry to None.

    Useful for testing to ensure clean state between tests.
    """
    global _capability_registry
    with _singleton_lock:
        _capability_registry = None
        logger.debug("Reset plugin capability registry singleton")
