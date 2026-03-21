"""Natural Language Query Interface.

Provides natural language to SQL conversion with preview and confirmation
pattern for safe database operations. Follows SQL preview pattern similar
to DBeaver/DataGrip UX per CONTEXT.md decisions.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.mcp.servers.dbhub import DBHubServer

class QueryState(Enum):
    """State of a natural language query.

    Tracks the lifecycle of a query from input through execution:

    - PENDING: Natural language received, not yet converted to SQL
    - PREVIEW: SQL generated and displayed, awaiting user confirmation
    - CONFIRMED: User confirmed, ready to execute
    - EXECUTED: Query has been executed, results available
    - REJECTED: User rejected the generated SQL
    - ERROR: An error occurred during processing

    Example:
        >>> state = QueryState.PREVIEW
        >>> print(f"Query is in {state.value} state")
        Query is in preview state
    """

    PENDING = "pending"
    PREVIEW = "preview"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    REJECTED = "rejected"
    ERROR = "error"

@dataclass
class NLQuery:
    """Natural language query with SQL preview.

    Tracks the lifecycle of a natural language query from input
    through SQL generation, confirmation, and execution.

    Attributes:
        id: Unique identifier for this query.
        natural_language: The original natural language question.
        generated_sql: The SQL generated from the natural language (None until generated).
        state: Current state of the query in its lifecycle.
        result: QueryResult after execution (None until executed).
        error: Error message if state is ERROR.
        metadata: Additional metadata about the query processing.

    Example:
        >>> query = NLQuery(
        ...     id="q-123",
        ...     natural_language="Show me all users",
        ...     generated_sql="SELECT * FROM users LIMIT 100",
        ...     state=QueryState.PREVIEW
        ... )
        >>> print(query.to_dict())
        {'id': 'q-123', 'natural_language': 'Show me all users', ...}
    """

    id: str
    natural_language: str
    generated_sql: str | None = None
    state: QueryState = QueryState.PENDING
    result: Any = None  # QueryResult after execution
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert query to dictionary format.

        Returns:
            Dictionary containing all query fields, with result
            converted to dict if present.
        """
        return {
            "id": self.id,
            "natural_language": self.natural_language,
            "generated_sql": self.generated_sql,
            "state": self.state.value,
            "result": self.result.to_dict() if self.result else None,
            "error": self.error,
            "metadata": self.metadata,
        }

class NLQueryInterface:
    """Natural language to SQL query interface.

    Converts natural language questions to SQL, shows preview to user,
    and only executes after confirmation. Follows the SQL preview pattern
    similar to DBeaver/DataGrip UX.

    The interface implements a safe query workflow:
    1. User asks a question in natural language
    2. Interface generates SQL and shows preview
    3. User confirms or rejects the SQL
    4. Only confirmed queries are executed

    This pattern prevents accidental data modification and gives users
    visibility into the exact SQL being executed.

    Example:
        >>> from core.mcp import get_registry, MCPServerConfig
        >>> from core.mcp.servers.dbhub import DBHubServer
        >>> registry = get_registry()
        >>> # ... register dbhub server ...
        >>> db = DBHubServer(registry)
        >>> nl = NLQueryInterface(db)
        >>> query = nl.ask("Show me all users who signed up last month")
        >>> print(f"Generated SQL: {query.generated_sql}")
        >>> if user_confirms():
        ...     result = nl.confirm_and_execute(query.id)

    Attributes:
        _db: The DBHubServer instance used for query execution.
        _sql_generator: Function that generates SQL from natural language.
        _queries: Dictionary of query_id -> NLQuery for tracking queries.
        _schema_cache: Cached database schema for SQL generation.
    """

    def __init__(
        self,
        db_server: DBHubServer,
        sql_generator: Callable[[str, dict[str, Any]], str] | None = None,
    ) -> None:
        """Initialize NLQueryInterface.

        Args:
            db_server: DBHubServer instance for query execution.
            sql_generator: Optional custom function to generate SQL from NL.
                Signature: (natural_language: str, schema: dict) -> str
                If not provided, uses a basic pattern-matching approach.

        Example:
            >>> db = DBHubServer(registry)
            >>> nl = NLQueryInterface(db)
            >>> # Or with a custom SQL generator
            >>> def llm_generator(nl: str, schema: dict) -> str:
            ...     return call_llm_for_sql(nl, schema)
            >>> nl = NLQueryInterface(db, sql_generator=llm_generator)
        """
        self._db = db_server
        self._sql_generator = sql_generator or self._default_sql_generator
        self._queries: dict[str, NLQuery] = {}
        self._schema_cache: dict[str, Any] | None = None

    def ask(
        self,
        natural_language: str,
        context: dict[str, Any] | None = None,
    ) -> NLQuery:
        """Convert natural language to SQL and create a preview.

        Takes a natural language question, generates the corresponding SQL,
        and returns an NLQuery in PREVIEW state. The query must be confirmed
        before execution.

        Args:
            natural_language: The natural language question to convert.
            context: Optional additional context for SQL generation, such as
                specific table names or filter hints.

        Returns:
            NLQuery with generated_sql populated and state set to PREVIEW.
            If an error occurs during generation, state will be ERROR.

        Example:
            >>> query = nl.ask("How many orders were placed last week?")
            >>> print(f"SQL: {query.generated_sql}")
            >>> print(f"State: {query.state.value}")  # "preview"
        """
        query_id = str(uuid.uuid4())[:8]
        query = NLQuery(
            id=query_id,
            natural_language=natural_language,
            metadata=context or {},
        )

        try:
            # Ensure schema is cached
            if self._schema_cache is None:
                self.refresh_schema()

            # Generate SQL
            generated_sql = self._sql_generator(
                natural_language,
                self._schema_cache or {},
            )
            query.generated_sql = generated_sql
            query.state = QueryState.PREVIEW

        except Exception as e:
            query.state = QueryState.ERROR
            query.error = str(e)

        self._queries[query_id] = query
        return query

    def confirm_and_execute(self, query_id: str) -> NLQuery:
        """Confirm and execute a previewed query.

        Marks the query as confirmed and executes it against the database.
        Only queries in PREVIEW state can be confirmed and executed.

        Args:
            query_id: The ID of the query to confirm and execute.

        Returns:
            NLQuery with result populated and state set to EXECUTED.
            If an error occurs, state will be ERROR.

        Raises:
            KeyError: If query_id doesn't exist.
            ValueError: If query is not in PREVIEW state.

        Example:
            >>> query = nl.ask("Show all products")
            >>> # User reviews the SQL and confirms
            >>> result = nl.confirm_and_execute(query.id)
            >>> print(f"Rows: {result.result.row_count}")
        """
        query = self._queries.get(query_id)
        if query is None:
            raise KeyError(f"Query {query_id} not found")

        if query.state != QueryState.PREVIEW:
            raise ValueError(
                f"Query must be in PREVIEW state to execute, current state: {query.state.value}"
            )

        try:
            query.state = QueryState.CONFIRMED
            result = self._db.query(query.generated_sql or "")
            query.result = result
            query.state = QueryState.EXECUTED

        except Exception as e:
            query.state = QueryState.ERROR
            query.error = str(e)

        return query

    def reject(self, query_id: str, reason: str = "") -> NLQuery:
        """Reject a previewed query.

        Marks the query as rejected, preventing execution.
        Only queries in PREVIEW state can be rejected.

        Args:
            query_id: The ID of the query to reject.
            reason: Optional reason for rejection.

        Returns:
            NLQuery with state set to REJECTED.

        Raises:
            KeyError: If query_id doesn't exist.
            ValueError: If query is not in PREVIEW state.

        Example:
            >>> query = nl.ask("Delete all orders")
            >>> # User reviews and rejects the destructive SQL
            >>> rejected = nl.reject(query.id, "Too dangerous")
            >>> print(f"State: {rejected.state.value}")  # "rejected"
        """
        query = self._queries.get(query_id)
        if query is None:
            raise KeyError(f"Query {query_id} not found")

        if query.state != QueryState.PREVIEW:
            raise ValueError(
                f"Query must be in PREVIEW state to reject, current state: {query.state.value}"
            )

        query.state = QueryState.REJECTED
        if reason:
            query.metadata["rejection_reason"] = reason

        return query

    def get_query(self, query_id: str) -> NLQuery | None:
        """Get a query by its ID.

        Args:
            query_id: The ID of the query to retrieve.

        Returns:
            The NLQuery if found, None otherwise.

        Example:
            >>> query = nl.get_query("abc12345")
            >>> if query:
            ...     print(f"State: {query.state.value}")
        """
        return self._queries.get(query_id)

    def list_queries(self, state: QueryState | None = None) -> list[NLQuery]:
        """List all queries, optionally filtered by state.

        Args:
            state: If provided, only return queries in this state.
                If None, returns all queries.

        Returns:
            List of NLQuery objects matching the filter criteria.

        Example:
            >>> # Get all pending queries
            >>> pending = nl.list_queries(QueryState.PENDING)
            >>> # Get all queries
            >>> all_queries = nl.list_queries()
        """
        if state is None:
            return list(self._queries.values())
        return [q for q in self._queries.values() if q.state == state]

    def refresh_schema(self) -> dict[str, Any]:
        """Refresh the cached database schema.

        Fetches the current schema from the database and updates
        the internal cache. Called automatically on first query
        if cache is empty.

        Returns:
            Dictionary containing the database schema.

        Example:
            >>> schema = nl.refresh_schema()
            >>> print(f"Tables: {schema.get('tables', [])}")
        """
        self._schema_cache = self._db.get_schema()
        return self._schema_cache

    def clear_queries(self) -> None:
        """Clear all tracked queries.

        Removes all queries from the internal tracking dictionary.
        Useful for cleaning up after a session.

        Example:
            >>> nl.clear_queries()
            >>> assert len(nl.list_queries()) == 0
        """
        self._queries.clear()

    def _default_sql_generator(
        self,
        natural_language: str,
        schema: dict[str, Any],
    ) -> str:
        """Generate SQL from natural language using basic patterns.

        This is a simple implementation that handles common query patterns.
        For production use, integrate with an LLM for more accurate
        and comprehensive SQL generation.

        Args:
            natural_language: The natural language question.
            schema: Database schema containing table information.

        Returns:
            Generated SQL query string.

        Raises:
            ValueError: If no tables are available in the schema.

        Note:
            This basic implementation supports:
            - count queries ("count", "how many")
            - list all queries ("show all", "list all", "get all")
            - basic select with limit

            For complex queries involving joins, aggregations, or
            specific conditions, use a custom sql_generator with LLM.
        """
        nl = natural_language.lower().strip()
        tables = schema.get("tables", [])

        # Find table name in query
        table = None
        for t in tables:
            if isinstance(t, str) and t.lower() in nl:
                table = t
                break
            elif isinstance(t, dict) and t.get("name", "").lower() in nl:
                table = t.get("name")
                break

        if not table:
            if tables:
                # Use first table as default
                t = tables[0]
                table = t if isinstance(t, str) else t.get("name", "table")
            else:
                raise ValueError(
                    "No table found in query and schema is empty. "
                    "Please specify a table or ensure database has tables."
                )

        # Basic pattern matching for common query types
        if "count" in nl or "how many" in nl:
            return f"SELECT COUNT(*) FROM {table}"
        elif any(p in nl for p in ("show all", "list all", "get all", "fetch all")):
            return f"SELECT * FROM {table} LIMIT 100"
        elif "latest" in nl or "recent" in nl:
            return f"SELECT * FROM {table} ORDER BY id DESC LIMIT 10"
        elif "first" in nl:
            return f"SELECT * FROM {table} ORDER BY id ASC LIMIT 10"
        else:
            return f"SELECT * FROM {table} LIMIT 10"
