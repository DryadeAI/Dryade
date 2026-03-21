"""Model Context Protocol (MCP) integration.

Provides MCP servers, clients, and tools for interacting with external
services via the Model Context Protocol standard.

Exports:
    Protocol types for MCP messages and data structures.
    StdioTransport for communicating with local MCP servers via stdio.
    MCPServerConfig for server configuration.
    MCPRegistry for server lifecycle management.
"""

from core.mcp.adapter import (
    MCPAgentAdapter,
    create_mcp_agent,
)
from core.mcp.autoload import (
    get_enabled_mcp_servers,
    load_mcp_config,
    register_mcp_agents,
    unregister_mcp_agents,
)
from core.mcp.config import (
    MCPServerConfig,
    MCPServerTransport,
    get_default_servers,
    load_config,
    load_config_from_file,
    load_configs_from_directory,
)
from core.mcp.credentials import (
    CredentialManager,
    get_credential_manager,
)
from core.mcp.embeddings import (
    EmbeddingResult,
    ToolEmbeddingStore,
    get_tool_embedding_store,
    reset_tool_embedding_store,
)
from core.mcp.hierarchical_router import (
    HierarchicalToolRouter,
    RouteResult,
    get_hierarchical_router,
    reset_hierarchical_router,
)
from core.mcp.http_transport import HttpSseTransport
from core.mcp.nl_query import (
    NLQuery,
    NLQueryInterface,
    QueryState,
)
from core.mcp.protocol import (
    MCPError,
    MCPErrorCode,
    MCPInitializeParams,
    MCPInitializeResult,
    MCPPrompt,
    MCPPromptArgument,
    MCPPromptMessage,
    MCPPromptsCapability,
    MCPPromptsListResult,
    MCPResource,
    MCPResourceContents,
    MCPResourcesCapability,
    MCPResourcesListResult,
    MCPServerCapabilities,
    MCPServerInfo,
    MCPTool,
    MCPToolCallContent,
    MCPToolCallResult,
    MCPToolInputSchema,
    MCPToolsCapability,
    MCPToolsListResult,
)
from core.mcp.registry import (
    MCPRegistry,
    MCPRegistryError,
    get_registry,
    reset_registry,
)
from core.mcp.servers import (
    AccessLevel,
    Alert,
    AlertAccessLevel,
    Dashboard,
    DatabaseType,
    DataSource,
    DBHubServer,
    DocumentContent,
    DocumentOpsServer,
    DocumentType,
    Entity,
    FilesystemServer,
    GitServer,
    GrafanaQueryResult,
    GrafanaServer,
    MemoryServer,
    PDFDocument,
    PDFPage,
    PDFReaderServer,
    QueryResult,
    Relation,
    SpreadsheetData,
    TimeRange,
)
from core.mcp.stdio_transport import (
    MCPServerStatus,
    MCPTimeoutError,
    MCPTransportError,
    StdioTransport,
)
from core.mcp.tool_index import (
    DetailLevel,
    SearchMode,
    SearchResult,
    ToolEntry,
    ToolIndex,
    get_tool_index,
    reset_tool_index,
)
from core.mcp.tool_wrapper import (
    MCPToolWrapper,
    extract_mcp_text,
)

__all__ = [
    # Configuration
    "MCPServerConfig",
    "MCPServerTransport",
    "get_default_servers",
    "load_config",
    "load_config_from_file",
    "load_configs_from_directory",
    # Protocol types
    "MCPError",
    "MCPErrorCode",
    "MCPInitializeParams",
    "MCPInitializeResult",
    "MCPPrompt",
    "MCPPromptArgument",
    "MCPPromptMessage",
    "MCPPromptsCapability",
    "MCPPromptsListResult",
    "MCPResource",
    "MCPResourceContents",
    "MCPResourcesCapability",
    "MCPResourcesListResult",
    "MCPServerCapabilities",
    "MCPServerInfo",
    "MCPTool",
    "MCPToolCallContent",
    "MCPToolCallResult",
    "MCPToolInputSchema",
    "MCPToolsCapability",
    "MCPToolsListResult",
    # Transport
    "MCPServerStatus",
    "MCPTimeoutError",
    "MCPTransportError",
    "StdioTransport",
    "HttpSseTransport",
    # Registry
    "MCPRegistry",
    "MCPRegistryError",
    "get_registry",
    "reset_registry",
    # Adapter
    "MCPAgentAdapter",
    "create_mcp_agent",
    # Server Wrappers
    "FilesystemServer",
    "GitServer",
    "MemoryServer",
    "Entity",
    "Relation",
    # Database Server
    "DBHubServer",
    "DatabaseType",
    "AccessLevel",
    "QueryResult",
    # Observability (Grafana)
    "GrafanaServer",
    "AlertAccessLevel",
    "Dashboard",
    "Alert",
    "DataSource",
    "GrafanaQueryResult",
    "TimeRange",
    # Credentials
    "CredentialManager",
    "get_credential_manager",
    # Document Processing
    "PDFReaderServer",
    "PDFDocument",
    "PDFPage",
    "DocumentOpsServer",
    "DocumentType",
    "DocumentContent",
    "SpreadsheetData",
    # Natural Language Query
    "NLQueryInterface",
    "NLQuery",
    "QueryState",
    # Autoload
    "register_mcp_agents",
    "unregister_mcp_agents",
    "get_enabled_mcp_servers",
    "load_mcp_config",
    # Tool Wrapper
    "MCPToolWrapper",
    "extract_mcp_text",
    # Tool Index
    "DetailLevel",
    "SearchMode",
    "SearchResult",
    "ToolEntry",
    "ToolIndex",
    "get_tool_index",
    "reset_tool_index",
    # Embeddings
    "EmbeddingResult",
    "ToolEmbeddingStore",
    "get_tool_embedding_store",
    "reset_tool_embedding_store",
    # Hierarchical Router
    "HierarchicalToolRouter",
    "RouteResult",
    "get_hierarchical_router",
    "reset_hierarchical_router",
]
