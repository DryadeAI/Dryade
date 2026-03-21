"""Pydantic models for slot registration."""

from typing import Any

from pydantic import BaseModel, Field


class SlotRegistration(BaseModel):
    """A registered slot component."""

    plugin_name: str = Field(..., description="Name of the plugin providing this component")
    component_name: str = Field(
        ..., description="Export name of the component in the plugin's UI bundle"
    )
    priority: int = Field(default=100, description="Render priority (lower = earlier). Default 100")
    props: dict[str, Any] = Field(
        default_factory=dict, description="Additional props passed to component"
    )

class SlotRegistrationRequest(BaseModel):
    """Request to register a slot component."""

    slot: str = Field(..., description="Slot name (e.g., 'workflow-sidebar')")
    component_name: str = Field(..., description="Export name of the component")
    priority: int = Field(default=100, description="Render priority")
    props: dict[str, Any] = Field(default_factory=dict)

class SlotRegistrationResponse(BaseModel):
    """Response for slot registration list."""

    slot: str
    registrations: list[SlotRegistration]
