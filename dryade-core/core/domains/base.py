"""Domain Configuration Models.

Defines the structure for domain plugins with agents, tools, and MCP configurations.
Target: ~80 LOC
"""

from typing import Any

from pydantic import BaseModel, Field

class StateMapping(BaseModel):
    """State export/require configuration for a tool."""

    exports: dict[str, str] = Field(default_factory=dict)  # result_key -> context_key
    requires: list[str] = Field(default_factory=list)  # context_keys needed

class ToolConfig(BaseModel):
    """Configuration for a domain tool."""

    name: str
    description: str
    mcp_tool: str  # Maps to MCP server tool name
    parameters: dict[str, Any] = Field(default_factory=dict)  # JSON Schema for params
    state: StateMapping = Field(default_factory=StateMapping)

class AgentConfig(BaseModel):
    """Configuration for a domain agent."""

    name: str
    role: str
    goal: str
    backstory: str = ""
    tools: list[str] = Field(default_factory=list)  # References to tool names
    llm_config: dict[str, Any] = Field(default_factory=dict)  # Optional LLM overrides
    delegation: bool = False  # Allow delegation to other agents

class CrewConfig(BaseModel):
    """Configuration for a pre-defined crew."""

    name: str
    description: str
    agents: list[str]  # Agent names to include
    process: str = "sequential"  # sequential, hierarchical
    manager_agent: str | None = None  # For hierarchical process

class FlowConfig(BaseModel):
    """Configuration for a pre-defined flow."""

    name: str
    description: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)  # Flow node definitions
    edges: list[dict[str, Any]] = Field(default_factory=list)  # Flow edge definitions

class DomainConfig(BaseModel):
    """Complete domain plugin configuration.

    Loaded from YAML files in domains/<name>/domain.yaml
    """

    name: str
    description: str = ""
    version: str = "1.0.0"

    # MCP server connection
    mcp_server: str | None = None  # URL to MCP server (supports ${ENV_VAR})

    # Domain components
    tools: list[ToolConfig] = Field(default_factory=list)
    agents: list[AgentConfig] = Field(default_factory=list)
    crews: list[CrewConfig] = Field(default_factory=list)
    flows: list[FlowConfig] = Field(default_factory=list)

    # Default context values for this domain
    default_context: dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic configuration for domain config."""

        extra = "allow"  # Allow additional fields for extensibility
