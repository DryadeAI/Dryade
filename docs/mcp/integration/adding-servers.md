# Adding New MCP Servers

This guide covers how to add new MCP servers to the Dryade system.

## Overview

There are two approaches to adding MCP servers:

1. **External MCP Server**: Add an existing npm package that implements MCP protocol
2. **Custom Python Server**: Create a Dryade-specific server in Python

Both approaches use the same configuration system and integrate with the agent registry.

## Adding an External MCP Server

### Step 1: Find or Create an MCP Server

**Official MCP Servers:**
- Browse: https://modelcontextprotocol.io/servers
- npm: `npm search mcp-server`

**Requirements:**
- Must implement MCP protocol over STDIO or HTTP/SSE
- Should have documented tool schemas

### Step 2: Add Configuration

Add the server to `config/mcp_servers.yaml`:

```yaml
# config/mcp_servers.yaml
servers:
  my_new_server:
    enabled: true
    command:
      - npx
      - -y
      - '@scope/mcp-server-name'
    description: "Description of what this server does"
    auto_restart: true
    max_restarts: 3
    timeout: 30.0
```

**Configuration Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | false | Enable server registration |
| `command` | list | required | Command to start server |
| `description` | string | - | Human-readable description |
| `auto_restart` | bool | true | Auto-restart on crash |
| `max_restarts` | int | 3 | Maximum restart attempts |
| `timeout` | float | 30.0 | Tool call timeout in seconds |
| `startup_delay` | float | 2.0 | Delay after start before ready |
| `env` | dict | {} | Environment variables |
| `transport` | string | "stdio" | Transport type: stdio or http |

### Step 3: Add Credentials (if needed)

For servers requiring authentication, add environment variables:

```yaml
# config/mcp_servers.yaml
servers:
  my_new_server:
    enabled: true
    command:
      - npx
      - -y
      - '@scope/mcp-server-name'
    env:
      API_KEY: ${MY_SERVER_API_KEY}
      API_SECRET: ${MY_SERVER_API_SECRET}
```

Then set the environment variables in `.env`:

```bash
# .env
MY_SERVER_API_KEY=your_key_here
MY_SERVER_API_SECRET=your_secret_here
```

**Note:** Environment variables use `${VAR}` syntax for expansion.

### Step 4: Test the Server

```bash
# Start Dryade and check server status
curl http://localhost:8000/api/mcp/servers

# List tools from new server
curl http://localhost:8000/api/mcp/servers/my_new_server/tools

# Call a tool
curl -X POST http://localhost:8000/api/mcp/servers/my_new_server/tools/tool_name \
  -H "Content-Type: application/json" \
  -d '{"arg1": "value1"}'
```

**Via Python:**

```python
from core.mcp import get_registry

registry = get_registry()

# Check server is registered
assert registry.is_registered("my_new_server")

# List tools
tools = registry.list_tools("my_new_server")
for tool in tools:
    print(f"{tool.name}: {tool.description}")

# Call a tool
result = registry.call_tool("my_new_server", "tool_name", {"arg1": "value1"})
print(result.content[0].text)
```

## Creating a Typed Python Wrapper (Recommended)

Typed wrappers provide IDE autocompletion and type safety.

### Step 1: Create Wrapper File

```python
# core/mcp/servers/my_new_server.py
"""MyNewServer MCP Server wrapper.

Provides typed Python interface for @scope/mcp-server-name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.mcp.protocol import MCPToolCallResult
    from core.mcp.registry import MCPRegistry


class MyNewServer:
    """Typed wrapper for @scope/mcp-server-name MCP server.

    Example:
        >>> from core.mcp import get_registry
        >>> from core.mcp.servers import MyNewServer
        >>> registry = get_registry()
        >>> server = MyNewServer(registry)
        >>> result = server.some_tool("arg")
    """

    def __init__(self, registry: MCPRegistry, server_name: str = "my_new_server") -> None:
        """Initialize wrapper.

        Args:
            registry: MCP registry for server communication.
            server_name: Name of the server in registry.
        """
        self._registry = registry
        self._server_name = server_name

    def some_tool(self, param1: str, param2: int = 10) -> str:
        """Description of what this tool does.

        Args:
            param1: Description of param1.
            param2: Description of param2 (default: 10).

        Returns:
            Description of return value.

        Raises:
            MCPTransportError: If communication fails.
        """
        result = self._registry.call_tool(
            self._server_name,
            "some_tool",
            {"param1": param1, "param2": param2}
        )
        return self._extract_text(result)

    def another_tool(self, data: dict) -> dict:
        """Another tool that returns structured data.

        Args:
            data: Input data dictionary.

        Returns:
            Processed data as dictionary.
        """
        import json
        result = self._registry.call_tool(
            self._server_name,
            "another_tool",
            {"data": data}
        )
        text = self._extract_text(result)
        return json.loads(text) if text else {}

    def _extract_text(self, result: MCPToolCallResult) -> str:
        """Extract text content from MCP tool result."""
        if result.content:
            for item in result.content:
                if item.type == "text" and item.text:
                    return item.text
        return ""
```

### Step 2: Export Wrapper

Add the wrapper to the package exports:

```python
# core/mcp/servers/__init__.py
from core.mcp.servers.filesystem import FilesystemServer
from core.mcp.servers.git import GitServer
from core.mcp.servers.memory import MemoryServer
# ... existing exports ...
from core.mcp.servers.my_new_server import MyNewServer

__all__ = [
    "FilesystemServer",
    "GitServer",
    "MemoryServer",
    # ... existing exports ...
    "MyNewServer",
]
```

### Step 3: Add Description for Agent Adapter

Add a description to `SERVER_DESCRIPTIONS` in `core/mcp/adapter.py`:

```python
# core/mcp/adapter.py
SERVER_DESCRIPTIONS: dict[str, str] = {
    "github": "GitHub integration for repositories, issues, pull requests, and code search",
    "context7": "Library documentation lookup for up-to-date API references",
    # ... existing entries ...
    "my_new_server": "Description for agent card",
}
```

## Creating a Custom Python MCP Server

For Dryade-specific servers, create a custom Python implementation.

### Step 1: Create Server Directory

```
core/mcp/my_server/
├── __init__.py
├── __main__.py    # Entry point
├── server.py      # Server implementation
└── tools.py       # Tool definitions
```

### Step 2: Define Tools

```python
# core/mcp/my_server/tools.py
"""Tool definitions for my_server."""

from typing import Any

TOOLS = [
    {
        "name": "my_tool",
        "description": "What this tool does",
        "inputSchema": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Description of param1"
                },
                "param2": {
                    "type": "integer",
                    "description": "Description of param2",
                    "default": 10
                }
            },
            "required": ["param1"]
        }
    },
    {
        "name": "another_tool",
        "description": "Another tool description",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Input data"
                }
            },
            "required": ["data"]
        }
    }
]


async def handle_my_tool(arguments: dict[str, Any]) -> str:
    """Implementation of my_tool."""
    param1 = arguments["param1"]
    param2 = arguments.get("param2", 10)
    # Do something
    return f"Result for {param1} with {param2}"


async def handle_another_tool(arguments: dict[str, Any]) -> str:
    """Implementation of another_tool."""
    import json
    data = arguments["data"]
    # Process data
    result = {"processed": True, "input": data}
    return json.dumps(result)


HANDLERS = {
    "my_tool": handle_my_tool,
    "another_tool": handle_another_tool,
}
```

### Step 3: Implement Server

```python
# core/mcp/my_server/server.py
"""MCP server implementation."""

import asyncio
import json
import sys

from core.mcp.my_server.tools import TOOLS, HANDLERS


async def handle_request(request: dict) -> dict:
    """Handle incoming MCP request."""
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "my_server", "version": "1.0.0"}
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS}
        }

    elif method == "tools/call":
        tool_name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})

        if tool_name in HANDLERS:
            try:
                result = await HANDLERS[tool_name](arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": result}]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": str(e)}],
                        "isError": True
                    }
                }

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}
        }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "Method not found"}
    }


async def run_server():
    """Run the MCP server over stdio."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            request = json.loads(line.decode())
            response = await handle_request(request)
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            }
            writer.write((json.dumps(error_response) + "\n").encode())
            await writer.drain()
```

### Step 4: Create Entry Point

```python
# core/mcp/my_server/__main__.py
"""Entry point for my_server MCP server."""

import asyncio
from core.mcp.my_server.server import run_server

if __name__ == "__main__":
    asyncio.run(run_server())
```

### Step 5: Configure Server

```yaml
# config/mcp_servers.yaml
servers:
  my_server:
    enabled: true
    command:
      - .venv/bin/python
      - core/mcp/my_server/__main__.py
    description: "My custom MCP server"
    auto_restart: true
    max_restarts: 3
    timeout: 30.0
```

## Testing New Servers

### Unit Tests

```python
# tests/unit/test_my_server.py
import pytest
from core.mcp.my_server.tools import handle_my_tool, handle_another_tool


@pytest.mark.asyncio
async def test_my_tool():
    """Test my_tool handler."""
    result = await handle_my_tool({"param1": "test", "param2": 5})
    assert "test" in result
    assert "5" in result


@pytest.mark.asyncio
async def test_another_tool():
    """Test another_tool handler."""
    import json
    result = await handle_another_tool({"data": {"key": "value"}})
    parsed = json.loads(result)
    assert parsed["processed"] is True
```

### Integration Tests

```python
# tests/integration/test_my_server_integration.py
import pytest
from core.mcp import get_registry


@pytest.fixture
def registry():
    """Get MCP registry."""
    return get_registry()


def test_server_registered(registry):
    """Test server is registered."""
    assert registry.is_registered("my_new_server")


def test_server_tools(registry):
    """Test server tools are discoverable."""
    tools = registry.list_tools("my_new_server")
    assert len(tools) > 0
    tool_names = [t.name for t in tools]
    assert "my_tool" in tool_names


def test_tool_call(registry):
    """Test tool execution."""
    result = registry.call_tool(
        "my_new_server",
        "my_tool",
        {"param1": "test"}
    )
    assert result.content
    assert result.content[0].text
```

## HTTP Transport Configuration

For remote MCP servers using HTTP/SSE:

```yaml
# config/mcp_servers.yaml
servers:
  remote_server:
    enabled: true
    transport: http
    url: https://api.example.com/mcp
    headers:
      X-Custom-Header: value
    credential_service: example_service
    auth_type: bearer
    timeout: 60.0
```

**Auth Types:**
- `none`: No authentication
- `bearer`: Bearer token in Authorization header
- `api_key`: API key in header
- `basic`: Basic auth (username:password)

## Server Registration Checklist

When adding a new MCP server, ensure:

- [ ] Configuration added to `config/mcp_servers.yaml`
- [ ] Environment variables documented in `.env.example`
- [ ] Typed Python wrapper created (recommended)
- [ ] Wrapper exported from `core/mcp/servers/__init__.py`
- [ ] Description added to `SERVER_DESCRIPTIONS` in `adapter.py`
- [ ] Documentation created in `docs/mcp/servers/`
- [ ] Unit tests written for tool handlers
- [ ] Integration tests written for server communication

## Related Documentation

- [Agent Integration](/docs/mcp/integration/agent-integration.md) - Using MCP with agents
- [Debugging Guide](/docs/mcp/integration/debugging.md) - Troubleshooting MCP issues
- [Server Documentation](/docs/mcp/servers/) - Individual server references
