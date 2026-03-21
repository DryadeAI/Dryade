"""DBHub MCP Server wrapper.

Provides typed Python interface for @bytebase/dbhub MCP server
supporting multiple database types with configurable access levels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry

class DatabaseType(Enum):
    """Supported database types for DBHub.

    DBHub supports connecting to various database systems through
    a unified interface using DSN connection strings.

    Example:
        >>> db_type = DatabaseType.POSTGRES
        >>> print(f"Using {db_type.value} database")
        Using postgres database
    """

    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    SQLSERVER = "sqlserver"
    MARIADB = "mariadb"

class AccessLevel(Enum):
    """Database access level configuration.

    Controls which SQL operations are permitted for security.
    Use appropriate level based on use case:

    - READ_ONLY: For analytics, reporting, read-only agents
    - SAFE_WRITE: For applications that modify data but shouldn't alter schema
    - FULL_ACCESS: For admin operations (use with caution)

    Example:
        >>> access = AccessLevel.SAFE_WRITE
        >>> print(f"Access level: {access.value}")
        Access level: safe_write
    """

    READ_ONLY = "read_only"  # SELECT only
    SAFE_WRITE = "safe_write"  # SELECT, INSERT, UPDATE (no DELETE, no DDL)
    FULL_ACCESS = "full_access"  # All operations (requires confirmation)

@dataclass
class QueryResult:
    """Result from database query execution.

    Provides structured access to query results with column names,
    row data, and optional execution metrics.

    Attributes:
        columns: List of column names in result order.
        rows: List of rows, each row is a list of values.
        row_count: Number of rows returned.
        execution_time_ms: Query execution time in milliseconds (if available).

    Example:
        >>> result = QueryResult(
        ...     columns=["id", "name"],
        ...     rows=[[1, "Alice"], [2, "Bob"]],
        ...     row_count=2
        ... )
        >>> for row in result.rows:
        ...     print(dict(zip(result.columns, row)))
        {'id': 1, 'name': 'Alice'}
        {'id': 2, 'name': 'Bob'}
    """

    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary format.

        Returns:
            Dict containing columns, rows, row_count, and execution_time_ms.
        """
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_dicts(self) -> list[dict[str, Any]]:
        """Convert rows to list of dictionaries.

        Each row becomes a dict mapping column names to values,
        which is often more convenient for processing.

        Returns:
            List of dicts, one per row.

        Example:
            >>> result.to_dicts()
            [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
        """
        return [dict(zip(self.columns, row, strict=False)) for row in self.rows]

class DBHubServer:
    """Typed wrapper for @bytebase/dbhub MCP server.

    Provides typed Python methods for database operations across
    Postgres, MySQL, SQLite, SQL Server, and MariaDB.
    Delegates to MCPRegistry for actual MCP communication.

    DBHub is a zero-dependency, token-efficient MCP server for database
    operations. It supports schema introspection, query execution, and
    table sampling across multiple database types.

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> registry = get_registry()
        >>> config = MCPServerConfig(
        ...     name="dbhub",
        ...     command=["npx", "-y", "@bytebase/dbhub"],
        ...     env={"DBHUB_DSN": "postgres://user:pass@localhost:5432/db"}
        ... )
        >>> registry.register(config)
        >>> db = DBHubServer(registry)
        >>> result = db.query("SELECT * FROM users LIMIT 10")
        >>> for row in result.to_dicts():
        ...     print(row)

    Access Control:
        The wrapper enforces access level restrictions before sending
        queries to the MCP server:

        - READ_ONLY: Only SELECT, SHOW, DESCRIBE, EXPLAIN allowed
        - SAFE_WRITE: Above + INSERT, UPDATE (no DELETE, DROP, TRUNCATE, ALTER, CREATE)
        - FULL_ACCESS: All operations permitted

    Connection Setup:
        DBHub uses DSN (Data Source Name) connection strings:

        - Postgres: postgres://user:password@host:port/database
        - MySQL: mysql://user:password@host:port/database
        - SQLite: sqlite:///path/to/database.db
        - SQL Server: sqlserver://user:password@host:port/database
        - MariaDB: mariadb://user:password@host:port/database
    """

    def __init__(
        self,
        registry: MCPRegistry,
        server_name: str = "dbhub",
        access_level: AccessLevel = AccessLevel.SAFE_WRITE,
    ) -> None:
        """Initialize DBHubServer wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the dbhub server in registry (default: "dbhub").
            access_level: Database access level restriction (default: SAFE_WRITE).
                Controls which SQL operations are permitted.

        Example:
            >>> from core.mcp import get_registry
            >>> registry = get_registry()
            >>> # Create read-only connection for analytics
            >>> db_readonly = DBHubServer(registry, access_level=AccessLevel.READ_ONLY)
            >>> # Create with write access for application use
            >>> db_write = DBHubServer(registry, access_level=AccessLevel.SAFE_WRITE)
        """
        self._registry = registry
        self._server_name = server_name
        self._access_level = access_level

    @property
    def access_level(self) -> AccessLevel:
        """Get the current access level.

        Returns:
            Current AccessLevel setting.
        """
        return self._access_level

    def query(self, sql: str) -> QueryResult:
        """Execute a SELECT query and return structured results.

        Args:
            sql: SQL SELECT statement to execute.

        Returns:
            QueryResult containing columns, rows, and metadata.

        Raises:
            PermissionError: If sql violates access level restrictions.
            MCPTransportError: If query execution fails.

        Example:
            >>> result = db.query("SELECT id, name FROM users WHERE active = true")
            >>> print(f"Found {result.row_count} users")
            >>> for user in result.to_dicts():
            ...     print(user['name'])
        """
        self._validate_access(sql)

        result = self._registry.call_tool(self._server_name, "query", {"sql": sql})
        text = self._extract_text(result)

        if not text:
            return QueryResult(columns=[], rows=[], row_count=0)

        try:
            data = json.loads(text)
            return QueryResult(
                columns=data.get("columns", []),
                rows=data.get("rows", []),
                row_count=len(data.get("rows", [])),
                execution_time_ms=data.get("execution_time_ms"),
            )
        except json.JSONDecodeError:
            # Fallback for plain text response
            return QueryResult(
                columns=["result"],
                rows=[[text]],
                row_count=1,
            )

    def execute(self, sql: str) -> int:
        """Execute a write statement (INSERT, UPDATE, DELETE).

        Args:
            sql: SQL write statement to execute.

        Returns:
            Number of affected rows.

        Raises:
            PermissionError: If sql violates access level restrictions.
            MCPTransportError: If execution fails.

        Example:
            >>> affected = db.execute("UPDATE users SET status = 'active' WHERE id = 1")
            >>> print(f"Updated {affected} rows")
        """
        self._validate_access(sql)

        result = self._registry.call_tool(self._server_name, "execute", {"sql": sql})
        text = self._extract_text(result)

        if not text:
            return 0

        try:
            data = json.loads(text)
            return data.get("affected_rows", data.get("rowsAffected", 0))
        except json.JSONDecodeError:
            # Try to parse "X rows affected" format
            if "row" in text.lower():
                parts = text.split()
                for _i, part in enumerate(parts):
                    if part.isdigit():
                        return int(part)
            return 0

    def get_schema(self, table: str | None = None) -> dict[str, Any]:
        """Get database or table schema information.

        When called without arguments, returns the full database schema.
        When a table name is provided, returns schema for that specific table.

        Args:
            table: Optional table name to get schema for. If None, returns
                full database schema.

        Returns:
            Dict containing schema information:
            - For database: {"tables": [...], "views": [...]}
            - For table: {"columns": [...], "indexes": [...], "constraints": [...]}

        Raises:
            MCPTransportError: If schema retrieval fails.

        Example:
            >>> # Get full database schema
            >>> schema = db.get_schema()
            >>> print(f"Tables: {len(schema.get('tables', []))}")
            >>> # Get specific table schema
            >>> users_schema = db.get_schema("users")
            >>> for col in users_schema.get('columns', []):
            ...     print(f"{col['name']}: {col['type']}")
        """
        args: dict[str, Any] = {}
        if table:
            args["table"] = table

        result = self._registry.call_tool(self._server_name, "get_schema", args)
        text = self._extract_text(result)

        if not text:
            return {}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def list_tables(self) -> list[str]:
        """List all tables in the database.

        Returns:
            List of table names.

        Raises:
            MCPTransportError: If listing fails.

        Example:
            >>> tables = db.list_tables()
            >>> print(f"Found {len(tables)} tables: {', '.join(tables)}")
        """
        result = self._registry.call_tool(self._server_name, "list_tables", {})
        text = self._extract_text(result)

        if not text:
            return []

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            return data.get("tables", [])
        except json.JSONDecodeError:
            # Fallback for newline-separated list
            return [t.strip() for t in text.strip().split("\n") if t.strip()]

    def describe_table(self, table: str) -> dict[str, Any]:
        """Get detailed table structure information.

        Returns column definitions, data types, constraints, indexes,
        and foreign key relationships for the specified table.

        Args:
            table: Name of the table to describe.

        Returns:
            Dict containing table structure:
            - columns: List of column definitions
            - primary_key: Primary key column(s)
            - indexes: List of index definitions
            - foreign_keys: List of foreign key relationships

        Raises:
            MCPTransportError: If description fails.

        Example:
            >>> info = db.describe_table("users")
            >>> for col in info.get('columns', []):
            ...     nullable = "NULL" if col.get('nullable') else "NOT NULL"
            ...     print(f"{col['name']} {col['type']} {nullable}")
        """
        result = self._registry.call_tool(self._server_name, "describe_table", {"table": table})
        text = self._extract_text(result)

        if not text:
            return {}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def get_table_sample(self, table: str, limit: int = 10) -> QueryResult:
        """Get sample rows from a table.

        Useful for data exploration and understanding table structure
        without writing custom queries.

        Args:
            table: Name of the table to sample.
            limit: Maximum number of rows to return (default: 10).

        Returns:
            QueryResult containing sample rows.

        Raises:
            MCPTransportError: If sampling fails.

        Example:
            >>> sample = db.get_table_sample("orders", limit=5)
            >>> print(f"Columns: {sample.columns}")
            >>> for row in sample.to_dicts():
            ...     print(row)
        """
        result = self._registry.call_tool(
            self._server_name,
            "get_table_sample",
            {"table": table, "limit": limit},
        )
        text = self._extract_text(result)

        if not text:
            return QueryResult(columns=[], rows=[], row_count=0)

        try:
            data = json.loads(text)
            return QueryResult(
                columns=data.get("columns", []),
                rows=data.get("rows", []),
                row_count=len(data.get("rows", [])),
            )
        except json.JSONDecodeError:
            return QueryResult(
                columns=["result"],
                rows=[[text]],
                row_count=1,
            )

    def _validate_access(self, sql: str) -> None:
        """Validate SQL against access level restrictions.

        Performs client-side validation before sending queries to ensure
        SQL operations are permitted by the configured access level.

        Args:
            sql: SQL statement to validate.

        Raises:
            PermissionError: If SQL violates access level restrictions.
        """
        sql_upper = sql.strip().upper()

        # Determine the SQL operation type
        sql_parts = sql_upper.split()
        if not sql_parts:
            raise PermissionError("Empty SQL statement")

        operation = sql_parts[0]

        if self._access_level == AccessLevel.READ_ONLY:
            allowed_read = ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "WITH")
            if operation not in allowed_read:
                raise PermissionError(
                    f"Access level {self._access_level.value} only allows read operations. "
                    f"'{operation}' is not permitted."
                )

        elif self._access_level == AccessLevel.SAFE_WRITE:
            # Disallow DELETE, DROP, TRUNCATE, ALTER, CREATE
            forbidden = ("DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE")
            if operation in forbidden:
                raise PermissionError(
                    f"Access level {self._access_level.value} does not allow {operation}. "
                    "Use FULL_ACCESS for destructive operations."
                )

        # FULL_ACCESS allows everything

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool call result.

        Returns:
            Text content from the first text item, or empty string.
        """
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""
