# DBHub MCP Server

| Property | Value |
|----------|-------|
| Package | `@bytebase/dbhub` |
| Category | Enterprise |
| Default | Disabled (requires credentials) |
| Transport | STDIO |
| Edition | Enterprise |

## Overview

DBHub provides database operations for multiple database types through a unified interface. It enables AI agents to query, inspect, and modify databases with full schema awareness.

### Supported Databases

- **PostgreSQL** - Full support including JSON types
- **MySQL** - Full support including stored procedures
- **SQLite** - File-based database support
- **SQL Server** - Microsoft SQL Server support
- **MariaDB** - MySQL-compatible with MariaDB extensions

### Key Features

- Execute SELECT queries with result streaming
- Execute INSERT, UPDATE, DELETE statements
- Inspect database and table schemas
- List and describe tables
- Sample data from tables

## Setup Instructions

### Step 1: Prepare Connection String (DSN)

Each database type requires a specific DSN format:

```bash
# PostgreSQL
DBHUB_DSN=postgres://user:password@host:5432/database

# MySQL
DBHUB_DSN=mysql://user:password@host:3306/database

# SQLite (absolute path)
DBHUB_DSN=sqlite:///path/to/database.db

# SQLite (relative path)
DBHUB_DSN=sqlite:./data/database.db

# SQL Server
DBHUB_DSN=sqlserver://user:password@host:1433/database

# MariaDB
DBHUB_DSN=mariadb://user:password@host:3306/database
```

### Step 2: Configure Environment

Add your DSN to the `.env` file:

```bash
# .env file
DBHUB_DSN=postgres://myuser:mypass@localhost:5432/mydb
```

### Step 3: Enable Server

Edit `config/mcp_servers.yaml`:

```yaml
dbhub:
  enabled: true
```

## Configuration

Full configuration in `config/mcp_servers.yaml`:

```yaml
dbhub:
  enabled: false
  command:
    - npx
    - -y
    - '@bytebase/dbhub'
  env:
    DSN: ${DBHUB_DSN}
  description: Database operations for Postgres, MySQL, SQLite, SQL Server, MariaDB
  auto_restart: true
  max_restarts: 3
  timeout: 60.0
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | false | Enable/disable the server |
| `auto_restart` | boolean | true | Restart on crash |
| `max_restarts` | integer | 3 | Maximum restart attempts |
| `timeout` | float | 60.0 | Operation timeout in seconds |

## Tool Reference

### query

Execute SELECT queries and return results.

| Property | Value |
|----------|-------|
| Parameters | `sql: string` |
| Returns | `QueryResult` with rows and columns |
| Purpose | Read data from database |

**Example:**

```python
result = registry.call_tool("dbhub", "query", {
    "sql": "SELECT id, name, email FROM users WHERE active = true LIMIT 10"
})
# Returns: {"rows": [...], "columns": ["id", "name", "email"]}
```

### execute

Execute write statements (INSERT, UPDATE, DELETE).

| Property | Value |
|----------|-------|
| Parameters | `sql: string` |
| Returns | `int` (affected rows count) |
| Purpose | Modify data in database |

**Example:**

```python
affected = registry.call_tool("dbhub", "execute", {
    "sql": "UPDATE users SET last_login = NOW() WHERE id = 1"
})
# Returns: 1 (one row affected)
```

### get_schema

Retrieve database or table schema information.

| Property | Value |
|----------|-------|
| Parameters | `table?: string` (optional) |
| Returns | Schema object |
| Purpose | Inspect database structure |

**Example:**

```python
# Get entire database schema
schema = registry.call_tool("dbhub", "get_schema", {})

# Get specific table schema
users_schema = registry.call_tool("dbhub", "get_schema", {
    "table": "users"
})
```

### list_tables

List all tables in the connected database.

| Property | Value |
|----------|-------|
| Parameters | (none) |
| Returns | `string[]` |
| Purpose | Discover available tables |

**Example:**

```python
tables = registry.call_tool("dbhub", "list_tables", {})
# Returns: ["users", "orders", "products", "categories"]
```

### describe_table

Get detailed column definitions for a table.

| Property | Value |
|----------|-------|
| Parameters | `table: string` |
| Returns | Column definitions object |
| Purpose | Inspect table structure |

**Example:**

```python
columns = registry.call_tool("dbhub", "describe_table", {
    "table": "users"
})
# Returns column names, types, nullability, defaults, constraints
```

### get_table_sample

Retrieve sample rows from a table.

| Property | Value |
|----------|-------|
| Parameters | `table: string`, `limit?: int` (default: 10) |
| Returns | `QueryResult` |
| Purpose | Preview table data |

**Example:**

```python
sample = registry.call_tool("dbhub", "get_table_sample", {
    "table": "orders",
    "limit": 5
})
# Returns 5 sample rows from orders table
```

## Python Wrapper Usage

The typed Python wrapper provides a more ergonomic interface:

```python
from core.mcp import get_registry
from core.mcp.servers import DBHubServer

registry = get_registry()
db = DBHubServer(registry)

# List all tables
tables = db.list_tables()
print(f"Tables: {tables}")

# Describe table structure
columns = db.describe_table("users")
for col in columns:
    print(f"  {col['name']}: {col['type']}")

# Query data with type-safe results
result = db.query("""
    SELECT u.name, COUNT(o.id) as order_count
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    WHERE u.created_at > '2024-01-01'
    GROUP BY u.id, u.name
    ORDER BY order_count DESC
    LIMIT 10
""")

for row in result.rows:
    print(f"{row['name']}: {row['order_count']} orders")

# Execute updates
affected = db.execute("""
    UPDATE users
    SET status = 'inactive'
    WHERE last_login < NOW() - INTERVAL '90 days'
""")
print(f"Deactivated {affected} users")

# Get sample data
sample = db.get_table_sample("products", limit=3)
```

## Use Cases

### Data Analysis

```python
# Analyze order patterns
result = db.query("""
    SELECT
        DATE_TRUNC('month', created_at) as month,
        COUNT(*) as orders,
        SUM(total) as revenue
    FROM orders
    WHERE status = 'completed'
    GROUP BY month
    ORDER BY month DESC
    LIMIT 12
""")
```

### Schema Discovery

```python
# Explore unknown database
tables = db.list_tables()
for table in tables:
    print(f"\n{table}:")
    columns = db.describe_table(table)
    for col in columns:
        print(f"  {col['name']}: {col['type']}")
```

### Data Validation

```python
# Check for data quality issues
result = db.query("""
    SELECT 'null_emails' as issue, COUNT(*) as count
    FROM users WHERE email IS NULL
    UNION ALL
    SELECT 'duplicate_emails', COUNT(*) - COUNT(DISTINCT email)
    FROM users
    UNION ALL
    SELECT 'invalid_status', COUNT(*)
    FROM orders WHERE status NOT IN ('pending', 'completed', 'cancelled')
""")
```

## Security Considerations

### Use Read-Only Credentials

When possible, configure DBHub with read-only database credentials:

```sql
-- PostgreSQL: Create read-only user
CREATE USER dbhub_reader WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE mydb TO dbhub_reader;
GRANT USAGE ON SCHEMA public TO dbhub_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dbhub_reader;
```

### Never Expose DSN in Logs

The DSN contains credentials. Ensure logging configuration masks sensitive environment variables.

### Audit Query Execution

Enable query logging on your database server to audit all queries executed through DBHub.

### Connection Security

- Use SSL/TLS connections when available
- Consider network isolation (VPN, private subnets)
- Rotate credentials regularly

## Troubleshooting

### Connection Refused

```
Error: Connection refused
```

**Causes:**
- Database server not running
- Incorrect host or port in DSN
- Firewall blocking connection

**Solutions:**
1. Verify database server is running
2. Check host and port in DSN
3. Test connection with database client (psql, mysql)
4. Check firewall rules

### Authentication Failed

```
Error: Authentication failed for user 'myuser'
```

**Causes:**
- Incorrect username or password in DSN
- User not authorized for database
- Password contains special characters not properly escaped

**Solutions:**
1. Verify credentials with database client
2. URL-encode special characters in password
3. Check user privileges

### Database Not Found

```
Error: Database 'mydb' does not exist
```

**Causes:**
- Database name misspelled in DSN
- Database not yet created
- Case sensitivity (PostgreSQL)

**Solutions:**
1. List available databases
2. Create database if needed
3. Check case of database name

### Query Timeout

```
Error: Query timeout after 60s
```

**Causes:**
- Complex query taking too long
- Missing indexes
- Large result set

**Solutions:**
1. Add LIMIT clause to queries
2. Create appropriate indexes
3. Increase timeout in configuration
4. Optimize query

## Related Documentation

- [MCP Overview](../README.md)
- [Tool Inventory](../INVENTORY.md)
- [Agent Integration](../integration/agent-integration.md)
