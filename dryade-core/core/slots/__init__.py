"""Slot registration system for plugin UI components.

Slots allow plugins to inject React components into predefined
locations in host pages (WorkflowPage, ChatPage, Dashboard, etc.).

Usage in plugins:
    from core.slots import slot_registry, SlotName

    class MyPlugin(PluginProtocol):
        def register(self, registry):
            slot_registry.register(
                slot=SlotName.WORKFLOW_SIDEBAR,
                plugin_name=self.name,
                component_name="MySidebarPanel",
                priority=100,
            )

        def shutdown(self):
            slot_registry.unregister(self.name)
"""

from core.slots.models import SlotRegistration, SlotRegistrationRequest
from core.slots.registry import SlotName, slot_registry

__all__ = [
    "SlotName",
    "SlotRegistration",
    "SlotRegistrationRequest",
    "slot_registry",
]
