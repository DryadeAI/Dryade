"""MCP Server Wrappers.

Typed Python wrappers for official MCP servers providing ergonomic
interfaces instead of raw call_tool() with dictionaries.

Each server wrapper:
- Provides typed methods for all available tools
- Delegates to MCPRegistry for actual MCP communication
- Includes Google-style docstrings with usage examples

Available Servers:
    FilesystemServer: Secure file operations with directory access control.
    GitServer: Git repository operations (status, diff, commit, branch, etc.).
    MemoryServer: Knowledge graph operations for persistent agent memory.
    DBHubServer: Database operations for Postgres, MySQL, SQLite, SQL Server, MariaDB.
    GrafanaServer: Observability integration (dashboards, alerts, queries).
    PDFReaderServer: PDF extraction (text, tables, images, structure).
    DocumentOpsServer: Office format operations (DOCX, XLSX, PPTX, CSV, Markdown).

Helper Classes:
    Entity: Knowledge graph entity for MemoryServer.
    Relation: Knowledge graph relation for MemoryServer.
    QueryResult: Structured result from database queries.
    DatabaseType: Enum of supported database types.
    AccessLevel: Database access level configuration.
    Dashboard: Grafana dashboard metadata.
    Alert: Grafana alert instance.
    DataSource: Grafana data source.
    TimeRange: Time range for Prometheus/Loki queries.
    GrafanaQueryResult: Query result from Prometheus/Loki.
    AlertAccessLevel: Alert management access level enum.
    PDFDocument: Extracted PDF document with pages.
    PDFPage: Single extracted PDF page.
    DocumentContent: Extracted document content.
    DocumentType: Supported document type enum.
    SpreadsheetData: Extracted spreadsheet data.
    ImageGenResult: Result from image generation.
    ImageData: Single generated image data.

Example:
    >>> from core.mcp import get_registry, MCPServerConfig
    >>> from core.mcp.servers import FilesystemServer, GitServer, MemoryServer, DBHubServer
    >>>
    >>> registry = get_registry()
    >>> # Register servers...
    >>> fs = FilesystemServer(registry)
    >>> git = GitServer(registry)
    >>> memory = MemoryServer(registry)
    >>> db = DBHubServer(registry)
"""

from core.mcp.servers.context7 import (
    Context7Server,
    DocChunk,
    LibraryInfo,
    create_context7_server,
)
from core.mcp.servers.dbhub import (
    AccessLevel,
    DatabaseType,
    DBHubServer,
    QueryResult,
)
from core.mcp.servers.document_ops import (
    DocumentContent,
    DocumentOpsServer,
    DocumentType,
    SpreadsheetData,
)
from core.mcp.servers.filesystem import FilesystemServer
from core.mcp.servers.git import GitServer
from core.mcp.servers.github import (
    GitHubIssue,
    GitHubPR,
    GitHubRepo,
    GitHubServer,
    create_github_server,
)
from core.mcp.servers.grafana import (
    Alert,
    AlertAccessLevel,
    Dashboard,
    DataSource,
    GrafanaServer,
    TimeRange,
)
from core.mcp.servers.grafana import (
    QueryResult as GrafanaQueryResult,
)
from core.mcp.servers.image_gen import ImageData, ImageGenResult, ImageGenServer
from core.mcp.servers.linear import (
    LinearIssue,
    LinearProject,
    LinearServer,
    LinearTeam,
    create_linear_server,
)
from core.mcp.servers.memory import Entity, MemoryServer, Relation
from core.mcp.servers.pdf_reader import (
    PDFDocument,
    PDFPage,
    PDFReaderServer,
)
from core.mcp.servers.playwright import (
    AccessibilityNode,
    BrowserSession,
    PlaywrightServer,
    Screenshot,
    create_playwright_server,
)

__all__ = [
    # Filesystem
    "FilesystemServer",
    # Git
    "GitServer",
    # Memory
    "MemoryServer",
    "Entity",
    "Relation",
    # Database
    "DBHubServer",
    "DatabaseType",
    "AccessLevel",
    "QueryResult",
    # Grafana (Observability)
    "GrafanaServer",
    "AlertAccessLevel",
    "Dashboard",
    "Alert",
    "DataSource",
    "GrafanaQueryResult",
    "TimeRange",
    # PDF
    "PDFReaderServer",
    "PDFDocument",
    "PDFPage",
    # Documents
    "DocumentOpsServer",
    "DocumentType",
    "DocumentContent",
    "SpreadsheetData",
    # Playwright (Browser Automation)
    "PlaywrightServer",
    "create_playwright_server",
    "Screenshot",
    "BrowserSession",
    "AccessibilityNode",
    # GitHub
    "GitHubServer",
    "create_github_server",
    "GitHubRepo",
    "GitHubIssue",
    "GitHubPR",
    # Context7 (Library Documentation)
    "Context7Server",
    "create_context7_server",
    "LibraryInfo",
    "DocChunk",
    # Linear (Issue Tracking)
    "LinearServer",
    "create_linear_server",
    "LinearIssue",
    "LinearProject",
    "LinearTeam",
    # Image Generation
    "ImageGenServer",
    "ImageGenResult",
    "ImageData",
]
