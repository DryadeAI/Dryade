# MCP (Model Context Protocol) Integration

Dryade integrates Model Context Protocol (MCP) servers to provide agents with standardized tool access. MCP enables agents to interact with external systems, manipulate files, query databases, and automate browsers through a unified protocol.

## What is MCP?

Model Context Protocol (MCP) is an open standard for connecting AI assistants to external tools and data sources. It provides:

- **Standardized tool protocol**: Consistent JSON-RPC interface for all tools
- **Multi-server support**: Run multiple MCP servers simultaneously
- **Agent integration**: Tools appear as native agent capabilities
- **Language agnostic**: Servers can be written in any language (Node.js, Python, etc.)

## Quick Start

### Check Which Servers Are Enabled

```bash
curl http://localhost:8000/api/mcp/servers
```

Response:
```json
{
  "servers": {
    "filesystem": {"status": "healthy", "tool_count": 14},
    "git": {"status": "healthy", "tool_count": 12},
    "memory": {"status": "healthy", "tool_count": 9}
  },
  "total_registered": 11,
  "total_running": 6,
  "total_healthy": 6
}
```

### List Available Tools

```bash
curl http://localhost:8000/api/mcp/servers/filesystem/tools
```

### Use Tools in Python

```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

# Get the global MCP registry
registry = get_registry()

# Use typed wrapper for filesystem operations
fs = FilesystemServer(registry)
content = fs.read_text_file("/tmp/example.txt")
entries = fs.list_directory("/tmp")

# Or call tools directly via registry
result = registry.call_tool("filesystem", "read_text_file", {"path": "/tmp/example.txt"})
print(result.content[0].text)
```

### Search for Tools

```python
from core.mcp import get_registry

registry = get_registry()
results = registry.search_tools("read file", top_k=5)
for r in results:
    print(f"{r['server']}/{r['name']}: {r['description']}")
```

## Server Categories

### Core Servers (No Credentials Required)

These servers are enabled by default and provide fundamental capabilities.

| Server | Tools | Description | Documentation |
|--------|-------|-------------|---------------|
| [filesystem](servers/filesystem.md) | 14 | Secure file operations with directory access control | Read, write, edit files |
| [git](servers/git.md) | 12 | Git repository operations | Status, diff, commit, branch |
| [memory](servers/memory.md) | 9 | Knowledge graph for persistent agent memory | Entities, relations, search |

### Developer Productivity Servers (Some Require Credentials)

These servers enhance developer workflows. Enable as needed.

| Server | Tools | Description | Credentials |
|--------|-------|-------------|-------------|
| [github](servers/github.md) | ~20 | GitHub API integration | `GITHUB_TOKEN` |
| [playwright](servers/playwright.md) | ~12 | Browser automation | None |
| [context7](servers/context7.md) | 2 | Library documentation lookup | None |
| [linear](servers/linear.md) | ~10 | Issue tracking with Linear | `LINEAR_API_KEY` |

### Enterprise Servers (Advanced Integration)

These servers provide enterprise-grade capabilities.

| Server | Tools | Description | Credentials |
|--------|-------|-------------|-------------|
| [dbhub](servers/dbhub.md) | 6 | Database operations (Postgres, MySQL, SQLite) | `DBHUB_DSN` |
| [grafana](servers/grafana.md) | ~15 | Observability integration | `GRAFANA_URL`, `GRAFANA_API_KEY` |

### Document Processing Servers

These servers handle document extraction and processing.

| Server | Tools | Description | Credentials |
|--------|-------|-------------|-------------|
| [pdf-reader](servers/pdf-reader.md) | 6 | PDF extraction (text, tables, images) | None |
| [document-ops](servers/document-ops.md) | ~8 | Office formats (XLSX, DOCX, PPTX) | None |

### Custom Servers (Dryade-Specific)

| Server | Tools | Description | Credentials |
|--------|-------|-------------|-------------|


## Documentation Navigation

| Document | Description |
|----------|-------------|
| [INVENTORY.md](INVENTORY.md) | Complete tool inventory (130+ tools across 12 servers) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical architecture reference |
| [servers/](servers/) | Per-server detailed documentation |
| [integration/agent-integration.md](integration/agent-integration.md) | Using MCP tools with agents |
| [integration/adding-servers.md](integration/adding-servers.md) | How to add new MCP servers |
| [integration/debugging.md](integration/debugging.md) | Troubleshooting guide |

## Configuration

### Server Configuration File

MCP servers are configured in `config/mcp_servers.yaml`:

```yaml
servers:
  filesystem:
    enabled: true
    command:
      - npx
      - -y
      - '@modelcontextprotocol/server-filesystem'
      - $HOME
      - /tmp
    description: Secure file operations with directory access control
    auto_restart: true
    max_restarts: 3
    timeout: 30.0
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Whether to start this server |
| `command` | list | required | Command to run the server |
| `env` | dict | {} | Environment variables |
| `description` | string | "" | Human-readable description |
| `auto_restart` | bool | false | Restart on crash |
| `max_restarts` | int | 3 | Maximum restart attempts |
| `timeout` | float | 30.0 | Request timeout in seconds |
| `startup_delay` | float | 2.0 | Delay after starting before initialize |

### Enabling a Server

1. **Edit configuration**:
   ```yaml
   github:
     enabled: true  # Change from false to true
   ```

2. **Set required environment variables** (if any):
   ```bash
   export GITHUB_TOKEN=ghp_your_token_here
   ```

3. **Restart the API** or call:
   ```bash
   curl -X POST http://localhost:8000/api/mcp/reload
   ```

### Environment Variable Pattern

Servers that require credentials use environment variable expansion:

```yaml
github:
  env:
    GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}
```

Set the environment variable before starting Dryade:
```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

## API Reference

### List Servers

```
GET /api/mcp/servers
```

### Get Server Status

```
GET /api/mcp/servers/{name}
```

### List Server Tools

```
GET /api/mcp/servers/{name}/tools
```

### Call Tool

```
POST /api/mcp/servers/{name}/tools/{tool}
Content-Type: application/json

{"path": "/tmp/test.txt"}
```

### Search Tools

```
GET /api/mcp/tools/search?q=read+file&top_k=10
```

### Restart Server

```
POST /api/mcp/servers/{name}/restart
```

## Health Monitoring

The MCP registry provides health monitoring for all servers:

```python
from core.mcp import get_registry

registry = get_registry()
health = registry.get_health_summary()

print(f"Total registered: {health['total_registered']}")
print(f"Total running: {health['total_running']}")
print(f"Total healthy: {health['total_healthy']}")

for name, info in health['servers'].items():
    print(f"  {name}: {info['status']} ({info['tool_count']} tools)")
```

Prometheus metrics are also available at `/metrics`:
- `dryade_mcp_server_status{server="filesystem"}` - Server status gauge
- `dryade_mcp_server_restarts_total{server="filesystem"}` - Restart counter

## See Also

- [MCP Protocol Specification](https://modelcontextprotocol.io/docs)
- [Dryade Agent Documentation](../agents/README.md)
- [Plugin System](../frontend/PLUGIN-DEVELOPMENT.md)
