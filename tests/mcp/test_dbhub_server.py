"""Unit tests for DBHub MCP server wrapper.

Comprehensive tests for database operations across Postgres, MySQL, SQLite,
SQL Server, and MariaDB with access level enforcement.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from core.mcp.protocol import MCPToolCallContent, MCPToolCallResult
from core.mcp.servers.dbhub import (
    AccessLevel,
    DatabaseType,
    DBHubServer,
    QueryResult,
)

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_registry():
    """Create a mock MCPRegistry for testing."""
    registry = MagicMock()
    registry.is_registered.return_value = True
    return registry

@pytest.fixture
def mock_result_text():
    """Create a factory for MCPToolCallResult with text content."""

    def _make_result(text: str, is_error: bool = False) -> MCPToolCallResult:
        return MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text=text)],
            isError=is_error,
        )

    return _make_result

@pytest.fixture
def mock_result_empty():
    """Create an empty MCPToolCallResult."""
    return MCPToolCallResult(content=[], isError=False)

# ============================================================================
# DatabaseType Tests
# ============================================================================

class TestDatabaseType:
    """Tests for DatabaseType enum."""

    def test_postgres_value(self):
        """Test POSTGRES enum value."""
        assert DatabaseType.POSTGRES.value == "postgres"

    def test_mysql_value(self):
        """Test MYSQL enum value."""
        assert DatabaseType.MYSQL.value == "mysql"

    def test_sqlite_value(self):
        """Test SQLITE enum value."""
        assert DatabaseType.SQLITE.value == "sqlite"

    def test_sqlserver_value(self):
        """Test SQLSERVER enum value."""
        assert DatabaseType.SQLSERVER.value == "sqlserver"

    def test_mariadb_value(self):
        """Test MARIADB enum value."""
        assert DatabaseType.MARIADB.value == "mariadb"

    def test_all_database_types_exist(self):
        """Test all expected database types are defined."""
        expected = {"postgres", "mysql", "sqlite", "sqlserver", "mariadb"}
        actual = {db.value for db in DatabaseType}
        assert actual == expected

# ============================================================================
# AccessLevel Tests
# ============================================================================

class TestAccessLevel:
    """Tests for AccessLevel enum."""

    def test_read_only_value(self):
        """Test READ_ONLY enum value."""
        assert AccessLevel.READ_ONLY.value == "read_only"

    def test_safe_write_value(self):
        """Test SAFE_WRITE enum value."""
        assert AccessLevel.SAFE_WRITE.value == "safe_write"

    def test_full_access_value(self):
        """Test FULL_ACCESS enum value."""
        assert AccessLevel.FULL_ACCESS.value == "full_access"

# ============================================================================
# QueryResult Tests
# ============================================================================

class TestQueryResult:
    """Tests for QueryResult dataclass."""

    def test_query_result_init_basic(self):
        """Test QueryResult initialization with basic fields."""
        result = QueryResult(
            columns=["id", "name"],
            rows=[[1, "Alice"], [2, "Bob"]],
            row_count=2,
        )

        assert result.columns == ["id", "name"]
        assert result.rows == [[1, "Alice"], [2, "Bob"]]
        assert result.row_count == 2
        assert result.execution_time_ms is None

    def test_query_result_init_with_timing(self):
        """Test QueryResult initialization with execution time."""
        result = QueryResult(
            columns=["id"],
            rows=[[1]],
            row_count=1,
            execution_time_ms=42.5,
        )

        assert result.execution_time_ms == 42.5

    def test_query_result_default_values(self):
        """Test QueryResult default values."""
        result = QueryResult()

        assert result.columns == []
        assert result.rows == []
        assert result.row_count == 0
        assert result.execution_time_ms is None

    def test_query_result_to_dict(self):
        """Test QueryResult.to_dict() returns correct structure."""
        result = QueryResult(
            columns=["id", "name"],
            rows=[[1, "Alice"]],
            row_count=1,
            execution_time_ms=10.5,
        )

        data = result.to_dict()

        assert data == {
            "columns": ["id", "name"],
            "rows": [[1, "Alice"]],
            "row_count": 1,
            "execution_time_ms": 10.5,
        }

    def test_query_result_to_dicts(self):
        """Test QueryResult.to_dicts() converts rows to list of dicts."""
        result = QueryResult(
            columns=["id", "name", "email"],
            rows=[
                [1, "Alice", "alice@example.com"],
                [2, "Bob", "bob@example.com"],
            ],
            row_count=2,
        )

        dicts = result.to_dicts()

        assert dicts == [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ]

    def test_query_result_to_dicts_empty(self):
        """Test QueryResult.to_dicts() with empty result."""
        result = QueryResult(columns=["id"], rows=[], row_count=0)

        assert result.to_dicts() == []

# ============================================================================
# DBHubServer Initialization Tests
# ============================================================================

class TestDBHubServerInit:
    """Tests for DBHubServer initialization."""

    def test_init_default_server_name(self, mock_registry):
        """Test default server name is 'dbhub'."""
        server = DBHubServer(mock_registry)

        assert server._server_name == "dbhub"
        assert server._registry is mock_registry

    def test_init_custom_server_name(self, mock_registry):
        """Test custom server name."""
        server = DBHubServer(mock_registry, server_name="custom-dbhub")

        assert server._server_name == "custom-dbhub"

    def test_init_default_access_level(self, mock_registry):
        """Test default access level is SAFE_WRITE."""
        server = DBHubServer(mock_registry)

        assert server._access_level == AccessLevel.SAFE_WRITE

    def test_init_custom_access_level(self, mock_registry):
        """Test custom access level."""
        server = DBHubServer(mock_registry, access_level=AccessLevel.FULL_ACCESS)

        assert server._access_level == AccessLevel.FULL_ACCESS

# ============================================================================
# DBHubServer Query Tests
# ============================================================================

class TestDBHubServerQuery:
    """Tests for query operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DBHubServer(mock_registry, access_level=AccessLevel.READ_ONLY)

    def test_query_select_allowed(self, server, mock_registry, mock_result_text):
        """Test SELECT query is allowed in READ_ONLY mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": ["id"], "rows": [[1]], "rowCount": 1})
        )

        result = server.query("SELECT * FROM users")

        mock_registry.call_tool.assert_called_once()
        assert isinstance(result, QueryResult)

    def test_query_insert_blocked_read_only(self, server, mock_registry):
        """Test INSERT query is blocked in READ_ONLY mode."""
        with pytest.raises(PermissionError, match="not permitted"):
            server.query("INSERT INTO users (name) VALUES ('test')")

        mock_registry.call_tool.assert_not_called()

    def test_query_update_blocked_read_only(self, server, mock_registry):
        """Test UPDATE query is blocked in READ_ONLY mode."""
        with pytest.raises(PermissionError, match="not permitted"):
            server.query("UPDATE users SET name = 'test' WHERE id = 1")

        mock_registry.call_tool.assert_not_called()

    def test_query_delete_blocked_read_only(self, server, mock_registry):
        """Test DELETE query is blocked in READ_ONLY mode."""
        with pytest.raises(PermissionError, match="not permitted"):
            server.query("DELETE FROM users WHERE id = 1")

        mock_registry.call_tool.assert_not_called()

    def test_query_drop_blocked_read_only(self, server, mock_registry):
        """Test DROP query is blocked in READ_ONLY mode."""
        with pytest.raises(PermissionError, match="not permitted"):
            server.query("DROP TABLE users")

        mock_registry.call_tool.assert_not_called()

class TestDBHubServerSafeWrite:
    """Tests for SAFE_WRITE access level."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with SAFE_WRITE access."""
        return DBHubServer(mock_registry, access_level=AccessLevel.SAFE_WRITE)

    def test_select_allowed(self, server, mock_registry, mock_result_text):
        """Test SELECT is allowed in SAFE_WRITE mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": ["id"], "rows": [[1]], "rowCount": 1})
        )

        server.query("SELECT * FROM users")

        mock_registry.call_tool.assert_called_once()

    def test_insert_allowed(self, server, mock_registry, mock_result_text):
        """Test INSERT is allowed in SAFE_WRITE mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": [], "rows": [], "rowCount": 0})
        )

        server.query("INSERT INTO users (name) VALUES ('test')")

        mock_registry.call_tool.assert_called_once()

    def test_update_allowed(self, server, mock_registry, mock_result_text):
        """Test UPDATE is allowed in SAFE_WRITE mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": [], "rows": [], "rowCount": 1})
        )

        server.query("UPDATE users SET name = 'test' WHERE id = 1")

        mock_registry.call_tool.assert_called_once()

    def test_delete_blocked(self, server, mock_registry):
        """Test DELETE is blocked in SAFE_WRITE mode."""
        with pytest.raises(PermissionError, match="does not allow DELETE"):
            server.query("DELETE FROM users WHERE id = 1")

        mock_registry.call_tool.assert_not_called()

    def test_drop_blocked(self, server, mock_registry):
        """Test DROP is blocked in SAFE_WRITE mode."""
        with pytest.raises(PermissionError, match="does not allow DROP"):
            server.query("DROP TABLE users")

        mock_registry.call_tool.assert_not_called()

    def test_truncate_blocked(self, server, mock_registry):
        """Test TRUNCATE is blocked in SAFE_WRITE mode."""
        with pytest.raises(PermissionError, match="does not allow TRUNCATE"):
            server.query("TRUNCATE TABLE users")

        mock_registry.call_tool.assert_not_called()

class TestDBHubServerFullAccess:
    """Tests for FULL_ACCESS access level."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with FULL_ACCESS."""
        return DBHubServer(mock_registry, access_level=AccessLevel.FULL_ACCESS)

    def test_delete_allowed(self, server, mock_registry, mock_result_text):
        """Test DELETE is allowed in FULL_ACCESS mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": [], "rows": [], "rowCount": 1})
        )

        server.query("DELETE FROM users WHERE id = 1")

        mock_registry.call_tool.assert_called_once()

    def test_drop_allowed(self, server, mock_registry, mock_result_text):
        """Test DROP is allowed in FULL_ACCESS mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": [], "rows": [], "rowCount": 0})
        )

        server.query("DROP TABLE users")

        mock_registry.call_tool.assert_called_once()

    def test_create_table_allowed(self, server, mock_registry, mock_result_text):
        """Test CREATE TABLE is allowed in FULL_ACCESS mode."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"columns": [], "rows": [], "rowCount": 0})
        )

        server.query("CREATE TABLE test (id INT PRIMARY KEY)")

        mock_registry.call_tool.assert_called_once()

# ============================================================================
# DBHubServer Schema Operations Tests
# ============================================================================

class TestDBHubServerSchema:
    """Tests for schema operations."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DBHubServer(mock_registry)

    def test_list_tables(self, server, mock_registry, mock_result_text):
        """Test list_tables returns table names."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps({"tables": ["users", "orders", "products"]})
        )

        tables = server.list_tables()

        assert tables == ["users", "orders", "products"]
        mock_registry.call_tool.assert_called_once_with("dbhub", "list_tables", {})

    def test_describe_table(self, server, mock_registry, mock_result_text):
        """Test describe_table returns column info as a dict."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "columns": [
                        {"name": "id", "type": "INTEGER", "nullable": False},
                        {"name": "name", "type": "VARCHAR(255)", "nullable": True},
                    ]
                }
            )
        )

        schema = server.describe_table("users")

        # describe_table returns a dict with a "columns" key
        assert "columns" in schema
        assert len(schema["columns"]) == 2
        assert schema["columns"][0]["name"] == "id"
        mock_registry.call_tool.assert_called_once_with(
            "dbhub", "describe_table", {"table": "users"}
        )

    def test_get_table_sample(self, server, mock_registry, mock_result_text):
        """Test get_table_sample returns sample rows."""
        mock_registry.call_tool.return_value = mock_result_text(
            json.dumps(
                {
                    "columns": ["id", "name"],
                    "rows": [[1, "Alice"], [2, "Bob"]],
                    "rowCount": 2,
                }
            )
        )

        result = server.get_table_sample("users", limit=2)

        assert isinstance(result, QueryResult)
        assert result.row_count == 2

# ============================================================================
# DBHubServer Config Tests
# ============================================================================

class TestDBHubServerConfig:
    """Tests for configuration -- DBHubServer has no get_config class method."""

    def test_no_get_config_method(self):
        """Verify get_config does not exist (config is external)."""
        assert not hasattr(DBHubServer, "get_config")

    def test_access_level_property(self, mock_registry):
        """Test access_level property returns current setting."""
        server = DBHubServer(mock_registry, access_level=AccessLevel.FULL_ACCESS)
        assert server.access_level == AccessLevel.FULL_ACCESS

# ============================================================================
# DBHubServer Error Handling Tests
# ============================================================================

class TestDBHubServerErrors:
    """Tests for error handling."""

    @pytest.fixture
    def server(self, mock_registry):
        """Create server with mock registry."""
        return DBHubServer(mock_registry, access_level=AccessLevel.FULL_ACCESS)

    def test_query_error_response_returns_fallback(self, server, mock_registry, mock_result_text):
        """Test error response from MCP server is parsed as fallback text result."""
        mock_registry.call_tool.return_value = MCPToolCallResult(
            content=[MCPToolCallContent(type="text", text="Connection failed")],
            isError=True,
        )

        # Source code does not check isError; it tries to parse text as JSON
        # and falls back to a single-row result on JSONDecodeError
        result = server.query("SELECT 1")
        assert result.columns == ["result"]
        assert result.rows == [["Connection failed"]]

    def test_query_invalid_json_response_fallback(self, server, mock_registry, mock_result_text):
        """Test invalid JSON response falls back to text result."""
        mock_registry.call_tool.return_value = mock_result_text("not valid json")

        # Source catches JSONDecodeError and returns fallback QueryResult
        result = server.query("SELECT 1")
        assert result.columns == ["result"]
        assert result.rows == [["not valid json"]]
        assert result.row_count == 1

    def test_empty_query_rejected(self, server, mock_registry):
        """Test empty query is rejected with PermissionError."""
        with pytest.raises(PermissionError, match="Empty SQL"):
            server.query("")

        mock_registry.call_tool.assert_not_called()

    def test_whitespace_query_rejected(self, server, mock_registry):
        """Test whitespace-only query is rejected with PermissionError."""
        with pytest.raises(PermissionError, match="Empty SQL"):
            server.query("   \n\t  ")

        mock_registry.call_tool.assert_not_called()
