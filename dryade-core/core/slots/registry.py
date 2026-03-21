"""Backend slot registry for plugin UI components.

This registry tracks which plugins have registered components for which slots.
The frontend queries this registry to discover what to render.
"""

import logging
from enum import Enum
from threading import Lock
from typing import Any

from core.slots.models import SlotRegistration

logger = logging.getLogger(__name__)

class SlotName(str, Enum):
    """Predefined UI slot names.

    These are the only valid slot locations where plugins can inject components.
    """

    WORKFLOW_SIDEBAR = "workflow-sidebar"
    WORKFLOW_TOOLBAR = "workflow-toolbar"
    DASHBOARD_WIDGET = "dashboard-widget"
    CHAT_PANEL = "chat-panel"
    SETTINGS_SECTION = "settings-section"
    AGENT_DETAIL_PANEL = "agent-detail-panel"
    NAV_FOOTER = "nav-footer"
    MODAL_EXTENSION = "modal-extension"

class SlotRegistryClass:
    """Singleton registry for slot registrations.

    Thread-safe for concurrent plugin registration/unregistration.
    """

    def __init__(self) -> None:
        self._slots: dict[SlotName, list[SlotRegistration]] = {slot: [] for slot in SlotName}
        self._lock = Lock()

    def register(
        self,
        slot: SlotName,
        plugin_name: str,
        component_name: str,
        priority: int = 100,
        props: dict[str, Any] | None = None,
    ) -> None:
        """Register a component for a slot.

        Args:
            slot: Target slot name
            plugin_name: Name of the registering plugin
            component_name: Export name of the component in the plugin's UI bundle
            priority: Render priority (lower = earlier). Default 100
            props: Additional props passed to the component
        """
        registration = SlotRegistration(
            plugin_name=plugin_name,
            component_name=component_name,
            priority=priority,
            props=props or {},
        )

        with self._lock:
            self._slots[slot].append(registration)
            # Sort by priority (ascending)
            self._slots[slot].sort(key=lambda r: r.priority)

        logger.info(
            f"Registered slot component: {plugin_name}.{component_name} -> {slot.value} (priority={priority})"
        )

    def unregister(self, plugin_name: str) -> int:
        """Unregister all slot components for a plugin.

        Called when a plugin is disabled or unloaded.

        Args:
            plugin_name: Name of the plugin to unregister

        Returns:
            Number of registrations removed
        """
        removed = 0
        with self._lock:
            for slot in SlotName:
                before = len(self._slots[slot])
                self._slots[slot] = [r for r in self._slots[slot] if r.plugin_name != plugin_name]
                removed += before - len(self._slots[slot])

        if removed > 0:
            logger.info(f"Unregistered {removed} slot component(s) for plugin: {plugin_name}")

        return removed

    def get_slot_registrations(self, slot: SlotName) -> list[SlotRegistration]:
        """Get all registrations for a slot, sorted by priority."""
        with self._lock:
            return list(self._slots[slot])

    def get_all_slots(self) -> dict[str, list[SlotRegistration]]:
        """Get all slot registrations.

        Returns:
            Dict mapping slot name strings to registration lists
        """
        with self._lock:
            return {
                slot.value: list(regs)
                for slot, regs in self._slots.items()
                if regs  # Only include non-empty slots
            }

    def get_plugin_slots(self, plugin_name: str) -> dict[str, list[SlotRegistration]]:
        """Get all slot registrations for a specific plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Dict mapping slot names to this plugin's registrations
        """
        with self._lock:
            result: dict[str, list[SlotRegistration]] = {}
            for slot, regs in self._slots.items():
                plugin_regs = [r for r in regs if r.plugin_name == plugin_name]
                if plugin_regs:
                    result[slot.value] = plugin_regs
            return result

    def clear(self) -> None:
        """Clear all registrations. For testing only."""
        with self._lock:
            for slot in SlotName:
                self._slots[slot] = []
        logger.warning("Slot registry cleared")

# Singleton instance
slot_registry = SlotRegistryClass()
