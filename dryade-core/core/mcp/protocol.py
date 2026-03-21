"""MCP Protocol Type Definitions.

Pydantic models for Model Context Protocol (MCP) messages and data structures.
These types provide type safety for MCP client-server communication.

Based on MCP specification version 2024-11-05.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Basic JSON-RPC Types
# ============================================================================

class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request message."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None

class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response message."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: MCPError | None = None

class JSONRPCNotification(BaseModel):
    """JSON-RPC 2.0 notification (no response expected)."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None

# ============================================================================
# MCP Error Types
# ============================================================================

class MCPErrorCode(int, Enum):
    """Standard JSON-RPC and MCP error codes."""

    # JSON-RPC standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP-specific errors
    REQUEST_CANCELLED = -32800
    CONTENT_TOO_LARGE = -32801

class MCPError(BaseModel):
    """MCP error information."""

    code: int
    message: str
    data: Any | None = None

# ============================================================================
# Tool Types
# ============================================================================

class MCPToolInputSchema(BaseModel):
    """JSON Schema describing a tool's input parameters."""

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    additionalProperties: bool | None = None  # noqa: N815

class MCPTool(BaseModel):
    """Definition of an MCP tool.

    Tools are functions that the client can request the server to execute.
    """

    name: str
    description: str = ""
    inputSchema: MCPToolInputSchema = Field(  # noqa: N815
        default_factory=MCPToolInputSchema
    )

class MCPToolCallContent(BaseModel):
    """Content item in a tool call result."""

    type: str = "text"  # "text", "image", "resource"
    text: str | None = None
    data: str | None = None  # Base64 for binary content
    mimeType: str | None = None  # noqa: N815

class MCPToolCallResult(BaseModel):
    """Result of a tool call.

    The result contains a list of content items that can be text,
    images, or embedded resources.
    """

    content: list[MCPToolCallContent] = Field(default_factory=list)
    isError: bool = False  # noqa: N815

# ============================================================================
# Resource Types
# ============================================================================

class MCPResource(BaseModel):
    """Definition of an MCP resource.

    Resources are read-only data sources that the client can access.
    """

    uri: str
    name: str
    description: str = ""
    mimeType: str | None = None  # noqa: N815

class MCPResourceContents(BaseModel):
    """Contents of a resource."""

    uri: str
    mimeType: str | None = None  # noqa: N815
    text: str | None = None
    blob: str | None = None  # Base64 encoded

# ============================================================================
# Prompt Types
# ============================================================================

class MCPPromptArgument(BaseModel):
    """Argument definition for a prompt template."""

    name: str
    description: str = ""
    required: bool = False

class MCPPrompt(BaseModel):
    """Definition of an MCP prompt template.

    Prompts are reusable templates that can be filled with arguments.
    """

    name: str
    description: str = ""
    arguments: list[MCPPromptArgument] = Field(default_factory=list)

class MCPPromptMessage(BaseModel):
    """Message in a prompt response."""

    role: str  # "user" or "assistant"
    content: MCPToolCallContent

# ============================================================================
# Server Capabilities and Initialization
# ============================================================================

class MCPToolsCapability(BaseModel):
    """Server's tool capabilities."""

    listChanged: bool = False  # noqa: N815

class MCPResourcesCapability(BaseModel):
    """Server's resource capabilities."""

    subscribe: bool = False
    listChanged: bool = False  # noqa: N815

class MCPPromptsCapability(BaseModel):
    """Server's prompt capabilities."""

    listChanged: bool = False  # noqa: N815

class MCPLoggingCapability(BaseModel):
    """Server's logging capabilities."""

    pass

class MCPServerCapabilities(BaseModel):
    """Capabilities advertised by an MCP server.

    Indicates which features the server supports.
    """

    tools: MCPToolsCapability | None = None
    resources: MCPResourcesCapability | None = None
    prompts: MCPPromptsCapability | None = None
    logging: MCPLoggingCapability | None = None

class MCPServerInfo(BaseModel):
    """Information about the MCP server."""

    name: str
    version: str

class MCPInitializeResult(BaseModel):
    """Result of the initialize request.

    Contains the protocol version and server capabilities.
    """

    protocolVersion: str  # noqa: N815
    capabilities: MCPServerCapabilities = Field(default_factory=MCPServerCapabilities)
    serverInfo: MCPServerInfo | None = None  # noqa: N815

# ============================================================================
# Client Info Types
# ============================================================================

class MCPClientInfo(BaseModel):
    """Information about the MCP client."""

    name: str
    version: str

class MCPClientCapabilities(BaseModel):
    """Capabilities advertised by the MCP client."""

    roots: dict[str, Any] | None = None
    sampling: dict[str, Any] | None = None

class MCPInitializeParams(BaseModel):
    """Parameters for the initialize request."""

    protocolVersion: str  # noqa: N815
    capabilities: MCPClientCapabilities = Field(default_factory=MCPClientCapabilities)
    clientInfo: MCPClientInfo  # noqa: N815

# ============================================================================
# List Response Types
# ============================================================================

class MCPToolsListResult(BaseModel):
    """Result of tools/list request."""

    tools: list[MCPTool] = Field(default_factory=list)
    nextCursor: str | None = None  # noqa: N815

class MCPResourcesListResult(BaseModel):
    """Result of resources/list request."""

    resources: list[MCPResource] = Field(default_factory=list)
    nextCursor: str | None = None  # noqa: N815

class MCPPromptsListResult(BaseModel):
    """Result of prompts/list request."""

    prompts: list[MCPPrompt] = Field(default_factory=list)
    nextCursor: str | None = None  # noqa: N815
