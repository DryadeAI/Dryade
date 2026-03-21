# MCP Debugging and Troubleshooting Guide

This guide covers how to diagnose and resolve common MCP issues.

## Overview

MCP troubleshooting typically involves:

1. **Server Status** - Is the server running?
2. **Tool Discovery** - Are tools available?
3. **Communication** - Is the transport working?
4. **Authentication** - Are credentials configured?

## Diagnostic Tools

### Check Server Status

**Via API:**

```bash
# List all servers and their status
curl http://localhost:8000/api/mcp/servers

# Check specific server
curl http://localhost:8000/api/mcp/servers/filesystem
```

**Response:**

```json
{
  "name": "filesystem",
  "status": "running",
  "tools_count": 14,
  "uptime_seconds": 3600
}
```

**Via Python:**

```python
from core.mcp import get_registry
from core.mcp.stdio_transport import MCPServerStatus

registry = get_registry()

# Get server status
status = registry.get_status("filesystem")
print(f"Status: {status.value}")

# Check if running
print(f"Running: {registry.is_running('filesystem')}")

# Check health
print(f"Healthy: {registry.check_health('filesystem')}")
```

**Possible Statuses:**

| Status | Description |
|--------|-------------|
| `running` / `healthy` | Server is operational |
| `stopped` | Server is not running |
| `starting` | Server is initializing |
| `error` / `unhealthy` | Server crashed or failed |
| `restarting` | Server is restarting |

### List Available Tools

```python
from core.mcp import get_registry

registry = get_registry()

# List tools from a server
tools = registry.list_tools("filesystem")
for tool in tools:
    print(f"Tool: {tool.name}")
    print(f"  Description: {tool.description}")
    print(f"  Schema: {tool.inputSchema.model_dump()}")
```

### Health Summary

```python
from core.mcp import get_registry

registry = get_registry()

# Get full health summary
summary = registry.get_health_summary()
print(f"Registered: {summary['total_registered']}")
print(f"Running: {summary['total_running']}")
print(f"Healthy: {summary['total_healthy']}")

for name, info in summary['servers'].items():
    print(f"  {name}: {info['status']} ({info['tool_count']} tools)")
```

## Common Issues and Solutions

### Issue: Server Won't Start

**Symptoms:**
- Status shows "stopped" or "error"
- Logs show "Failed to start MCP server"

**Diagnose:**

```bash
# Check if command works manually
npx -y @modelcontextprotocol/server-filesystem /tmp

# Check Node.js version (needs 18+)
node --version

# Check for npm issues
npm cache clean --force
npm ls @modelcontextprotocol/server-filesystem
```

**Solutions:**
- Install Node.js 18+
- Clear npm cache
- Check network connectivity for npm packages
- Verify command syntax in `config/mcp_servers.yaml`

### Issue: Authentication Errors

**Symptoms:**
- "Unauthorized", "Invalid credentials", "API key invalid"
- Tool calls fail with 401/403 errors

**Diagnose:**

```bash
# Check environment variable is set
echo $GITHUB_TOKEN
printenv | grep -E "(GITHUB|LINEAR|GRAFANA|DBHUB)"

# Check .env file
grep -E "(TOKEN|KEY|DSN)" .env
```

**Via Python:**

```python
import os

# Check environment variables
env_vars = ["GITHUB_TOKEN", "LINEAR_API_KEY", "GRAFANA_API_KEY", "DBHUB_DSN"]
for var in env_vars:
    value = os.getenv(var)
    if value:
        print(f"{var}: set ({len(value)} chars)")
    else:
        print(f"{var}: NOT SET")
```

**Solutions:**
- Ensure `.env` file exists and is loaded
- Check token/key format matches requirements
- Verify token has required scopes/permissions
- Check token expiration
- Restart application after `.env` changes

### Issue: Tool Execution Timeout

**Symptoms:**
- MCPTimeoutError in logs
- Tool calls hang then fail

**Diagnose:**

```python
from core.mcp import get_registry

registry = get_registry()
config = registry.get_config("playwright")
print(f"Timeout: {config.timeout}")
```

**Solutions:**

Increase timeout in config:

```yaml
# config/mcp_servers.yaml
servers:
  playwright:
    timeout: 120.0  # Increase from 30.0
```

Other approaches:
- Check server process CPU/memory usage
- Reduce operation complexity
- Check network latency for HTTP transport

### Issue: Server Not Found / Not Registered

**Symptoms:**
- MCPRegistryError: Server 'x' not registered
- 404 on `/api/mcp/servers/x`

**Diagnose:**

```python
from core.mcp import get_registry

registry = get_registry()

# List all registered servers
servers = registry.list_servers()
print(f"Registered servers: {servers}")

# Check specific server
print(f"Is 'github' registered: {registry.is_registered('github')}")
```

**Solutions:**
- Check `config/mcp_servers.yaml` has server entry
- Verify `enabled: true` in config
- Restart application to reload config
- Check for YAML syntax errors

### Issue: Tool Returns Empty Result

**Symptoms:**
- `result.content` is empty
- Tool "succeeded" but no data

**Diagnose:**

```python
from core.mcp import get_registry

registry = get_registry()

result = registry.call_tool("filesystem", "read_text_file", {"path": "/tmp/test.txt"})
print(f"Content count: {len(result.content)}")
print(f"Is error: {result.isError}")
print(f"Raw result: {result}")
```

**Solutions:**
- Check tool arguments match schema
- Verify input data exists (file, database record, etc.)
- Check server logs for errors
- Validate argument types (string vs int, etc.)

### Issue: Tool Schema Mismatch

**Symptoms:**
- "Invalid arguments" error
- Validation errors in logs

**Diagnose:**

```python
from core.mcp import get_registry

registry = get_registry()

# Get tool schema
tools = registry.list_tools("filesystem")
for tool in tools:
    if tool.name == "read_text_file":
        print(f"Schema: {tool.inputSchema.model_dump()}")
```

**Solutions:**
- Match argument names exactly
- Use correct types (string, integer, array, object)
- Include all required fields
- Remove unsupported optional fields

## Reading Logs

### Application Logs

```bash
# Dryade logs
tail -f logs/api.log | grep -i mcp

# Filter by server
tail -f logs/api.log | grep "MCP.*filesystem"

# Filter by error level
tail -f logs/api.log | grep -E "(ERROR|WARNING).*mcp"
```

### Docker Logs

```bash
# All logs
docker logs dryade-api 2>&1 | grep -i mcp

# Follow logs
docker logs -f dryade-api 2>&1 | grep -i mcp

# Last 100 lines
docker logs --tail 100 dryade-api 2>&1 | grep -i mcp
```

### Key Log Patterns

| Pattern | Meaning |
|---------|---------|
| `MCP server started: X` | Server successfully started |
| `Auto-starting MCP server` | Lazy-start triggered |
| `MCP tool call: X/Y` | Tool being called |
| `MCP error:` | Something went wrong |
| `MCP timeout:` | Operation timed out |
| `MCP transport error:` | Communication failed |

## Debugging Tool Calls

### Enable Debug Logging

```python
import logging

# Enable debug logging for MCP
logging.getLogger("core.mcp").setLevel(logging.DEBUG)

# Make a call - will show detailed logs
from core.mcp import get_registry
registry = get_registry()
result = registry.call_tool("filesystem", "list_directory", {"path": "/tmp"})
```

### Trace Tool Execution

```python
from core.mcp.tool_wrapper import MCPToolWrapper

# Use wrapper for built-in tracing
wrapper = MCPToolWrapper("filesystem", "list_directory", "List directory")
result = wrapper.call(path="/tmp")
# Traces are recorded automatically
```

### Check Metrics

```bash
# Prometheus metrics
curl http://localhost:8000/metrics | grep mcp

# Key metrics:
# - mcp_tool_calls_total
# - mcp_tool_call_duration_seconds
# - mcp_server_status
```

## Restarting Servers

### Via API

```bash
# Restart all MCP servers
curl -X POST http://localhost:8000/api/mcp/restart

# Restart specific server
curl -X POST http://localhost:8000/api/mcp/servers/filesystem/restart
```

### Via Python

```python
from core.mcp import get_registry

registry = get_registry()

# Stop and start
registry.stop("filesystem")
registry.start("filesystem")

# Or just restart (if running)
if registry.is_running("filesystem"):
    registry.stop("filesystem")
registry.start("filesystem")
```

### Full Registry Restart

```python
from core.mcp import get_registry

registry = get_registry()

# Shutdown all servers
registry.shutdown()

# Start all enabled servers
results = registry.start_all()
for name, error in results.items():
    if error:
        print(f"Failed to start {name}: {error}")
    else:
        print(f"Started {name}")
```

## Verifying Tool Schemas

```python
from core.mcp import get_registry

registry = get_registry()
tools = registry.list_tools("filesystem")

for tool in tools:
    print(f"Tool: {tool.name}")
    print(f"  Description: {tool.description}")
    schema = tool.inputSchema.model_dump()
    print(f"  Required: {schema.get('required', [])}")
    for prop, details in schema.get('properties', {}).items():
        print(f"  - {prop}: {details.get('type')} - {details.get('description', '')}")
    print()
```

## Testing Tools Manually

### Quick Test Script

```python
#!/usr/bin/env python3
"""Quick MCP tool test script."""

from core.mcp import get_registry

registry = get_registry()

# 1. Check server is running
server = "filesystem"
status = registry.get_status(server)
print(f"1. Status: {status.value}")

# 2. List available tools
tools = registry.list_tools(server)
print(f"2. Tools: {[t.name for t in tools]}")

# 3. Call a tool
result = registry.call_tool(
    server,
    "list_directory",
    {"path": "/tmp"}
)
print(f"3. Result: {result.content[0].text if result.content else 'empty'}")
```

### Validate Tool Arguments

```python
from core.mcp import get_registry

registry = get_registry()

# Validate before calling
exists, server, suggestions = registry.validate_tool("github_opn")
if not exists:
    print(f"Tool not found. Did you mean: {suggestions}")
else:
    print(f"Tool exists on server: {server}")
```

## Error Reference

| Error | Cause | Solution |
|-------|-------|----------|
| `MCPRegistryError` | Server not registered | Check config, enable server |
| `MCPTransportError` | Communication failed | Check server process, restart |
| `MCPTimeoutError` | Operation too slow | Increase timeout, simplify operation |
| "Command not found" | Missing dependency | Install Node.js/Python package |
| "Permission denied" | Access control | Check file/network permissions |
| "Invalid arguments" | Schema mismatch | Check tool inputSchema |
| "Server crashed" | Runtime error | Check server logs, restart |
| "Connection refused" | HTTP transport failed | Check URL and network |

## Environment Variables Reference

| Variable | Server | Description |
|----------|--------|-------------|
| `GITHUB_TOKEN` | github | GitHub personal access token |
| `LINEAR_API_KEY` | linear | Linear API key |
| `GRAFANA_URL` | grafana | Grafana instance URL |
| `GRAFANA_API_KEY` | grafana | Grafana API key |
| `DBHUB_DSN` | dbhub | Database connection string |
| `DRYADE_MOCK_MODE` | all | Set to "true" for mock responses |

## Getting Help

1. **Check server-specific documentation** in `/docs/mcp/servers/`
2. **Review MCP protocol specification** at https://modelcontextprotocol.io
3. **Enable debug logging** and capture output
4. **Check GitHub issues** for similar problems
5. **Test manually** with the quick test script

## Related Documentation

- [Agent Integration](/docs/mcp/integration/agent-integration.md) - Using MCP with agents
- [Adding Servers](/docs/mcp/integration/adding-servers.md) - How to add new MCP servers
- [Server Documentation](/docs/mcp/servers/) - Individual server references
