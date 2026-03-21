# MCP Agent Integration Guide

This guide covers how to use MCP tools with agents in the Dryade system.

## Overview

MCP (Model Context Protocol) servers appear as agents in the agent registry through the MCPAgentAdapter. This enables:

- MCP servers discovered alongside native agents
- Tools available in OpenAI function format via `get_tools()`
- Seamless integration with CrewAI, LangChain, and other frameworks
- Lazy-start pattern: servers auto-start on first tool call

## Architecture

```
Agent Request
     │
     ▼
MCPAgentAdapter.execute()
     │
     ▼
MCPRegistry.call_tool()
     │
     ▼
StdioTransport / HttpSseTransport
     │
     ▼
MCP Server Process
```

## Discovering MCP Agents

### Via Python

```python
from core.adapters import get_agent_registry

registry = get_agent_registry()

# List all MCP agents
agents = [a for a in registry.list_agents() if a.framework == "mcp"]
for agent in agents:
    print(f"{agent.name}: {agent.description}")
    print(f"  Tools: {len(agent.capabilities)}")
```

### Via API

```bash
# List all agents
curl http://localhost:8000/api/agents

# Filter by framework
curl http://localhost:8000/api/agents?framework=mcp
```

### Via CLI

```bash
dryade agents list --framework mcp
```

## Using MCP Tools Directly

The most direct way to use MCP tools is through the MCPRegistry.

### Basic Tool Call

```python
from core.mcp import get_registry

registry = get_registry()

# Call tool directly
result = registry.call_tool(
    server_name="filesystem",
    tool_name="read_text_file",
    arguments={"path": "/tmp/test.txt"}
)

# Result is MCPToolCallResult
for item in result.content:
    if item.type == "text":
        print(item.text)
```

### Listing Available Tools

```python
from core.mcp import get_registry

registry = get_registry()

# List all tools from a specific server
tools = registry.list_tools("filesystem")
for tool in tools:
    print(f"{tool.name}: {tool.description}")
    print(f"  Schema: {tool.inputSchema.model_dump()}")
```

### Tool Search

```python
from core.mcp import get_registry

registry = get_registry()

# Search tools by natural language
results = registry.search_tools(
    query="read a file",
    mode="hybrid",
    top_k=3
)

for r in results:
    print(f"{r['server']}/{r['name']}: {r['score']:.2f}")
```

## Using Typed Wrappers

Typed wrappers provide IDE autocompletion and type hints for MCP tools.

### FilesystemServer

```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Read file - returns str
content = fs.read_text_file("/tmp/test.txt")

# List directory - returns list[str]
entries = fs.list_directory("/tmp")
for entry in entries:
    print(entry)  # "[FILE] example.txt" or "[DIR] subdir"

# Edit file with search/replace
fs.edit_file("/tmp/example.txt", [
    {"oldText": "foo", "newText": "bar"}
])
```

### GitServer

```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Get git status
status = git.status("/path/to/repo")

# View diff
diff = git.diff_unstaged("/path/to/repo")

# Commit changes
git.commit("/path/to/repo", "feat: add new feature")
```

### MemoryServer

```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Create entities in knowledge graph
memory.create_entities([{
    "name": "Project X",
    "entityType": "project",
    "observations": ["Started in 2024", "Python-based"]
}])

# Create relationships
memory.create_relations([{
    "from": "Project X",
    "to": "Python",
    "relationType": "uses"
}])

# Search nodes
results = memory.search_nodes("Python")
```

### Available Wrappers

| Wrapper | Server | Description |
|---------|--------|-------------|
| `FilesystemServer` | filesystem | File operations with access control |
| `GitServer` | git | Git repository operations |
| `MemoryServer` | memory | Knowledge graph operations |
| `GitHubServer` | github | GitHub API operations |
| `PlaywrightServer` | playwright | Browser automation |
| `Context7Server` | context7 | Library documentation lookup |
| `LinearServer` | linear | Linear issue tracking |
| `DBHubServer` | dbhub | Database operations |
| `GrafanaServer` | grafana | Observability dashboards |
| `PDFReaderServer` | pdf-reader | PDF extraction |
| `DocumentOpsServer` | document-ops | Office document operations |

## Using MCPAgentAdapter

The MCPAgentAdapter wraps MCP servers as UniversalAgent instances.

### Creating an Adapter

```python
from core.mcp.adapter import create_mcp_agent

# Create adapter for a server
agent = create_mcp_agent("filesystem")

# Get agent card (AgentCard)
card = agent.get_card()
print(f"Name: {card.name}")           # "mcp-filesystem"
print(f"Framework: {card.framework}")  # AgentFramework.MCP
print(f"Capabilities: {len(card.capabilities)}")
```

### Getting Tools in OpenAI Format

```python
from core.mcp.adapter import create_mcp_agent

agent = create_mcp_agent("filesystem")

# Get tools in OpenAI function format
tools = agent.get_tools()
# [{"type": "function", "function": {"name": "read_file", ...}}, ...]

# Use with OpenAI-compatible LLM
for tool in tools:
    print(f"Tool: {tool['function']['name']}")
    print(f"Description: {tool['function']['description']}")
```

### Executing Tasks

```python
from core.mcp.adapter import create_mcp_agent

agent = create_mcp_agent("filesystem")

# Execute with explicit tool
result = await agent.execute(
    task="read file",
    context={
        "tool": "read_text_file",
        "arguments": {"path": "/tmp/test.txt"}
    }
)
print(result.result)

# Execute with task description (auto-matches tool)
result = await agent.execute(
    task="list the contents of /tmp directory"
)
print(result.result)
```

## Integration with CrewAI

MCP tools can be used with CrewAI agents.

### Basic Integration

```python
from crewai import Agent, Task, Crew
from core.mcp.adapter import create_mcp_agent

# Create MCP agent adapter
mcp_agent = create_mcp_agent("filesystem")

# Get tools in CrewAI-compatible format
mcp_tools = mcp_agent.get_tools()

# Create CrewAI agent with MCP tools
crew_agent = Agent(
    role="File Analyst",
    goal="Analyze file contents",
    tools=mcp_tools
)

task = Task(
    description="Read and summarize /tmp/report.txt",
    agent=crew_agent
)

crew = Crew(agents=[crew_agent], tasks=[task])
result = crew.kickoff()
```

### Multiple MCP Servers

```python
from crewai import Agent, Task, Crew
from core.mcp.adapter import create_mcp_agent

# Combine tools from multiple servers
fs_tools = create_mcp_agent("filesystem").get_tools()
git_tools = create_mcp_agent("git").get_tools()

all_tools = fs_tools + git_tools

# Create agent with combined toolset
dev_agent = Agent(
    role="Developer",
    goal="Manage files and git repositories",
    tools=all_tools
)
```

## Integration with LangChain

Create LangChain tools from MCP tools.

### Using StructuredTool

```python
from langchain.tools import StructuredTool
from core.mcp import get_registry

registry = get_registry()

# Create LangChain tool from MCP tool
def read_file(path: str) -> str:
    """Read a file from the filesystem."""
    result = registry.call_tool("filesystem", "read_text_file", {"path": path})
    return result.content[0].text if result.content else ""

tool = StructuredTool.from_function(
    func=read_file,
    name="read_file",
    description="Read a file from the filesystem"
)

# Use with LangChain agent
from langchain.agents import AgentExecutor, create_openai_tools_agent

agent = create_openai_tools_agent(llm, [tool], prompt)
executor = AgentExecutor(agent=agent, tools=[tool])
```

### Creating Multiple Tools

```python
from langchain.tools import StructuredTool
from core.mcp import get_registry

registry = get_registry()

def create_langchain_tool(server: str, tool_name: str, description: str):
    """Factory to create LangChain tool from MCP tool."""
    def tool_func(**kwargs):
        result = registry.call_tool(server, tool_name, kwargs)
        return result.content[0].text if result.content else ""

    return StructuredTool.from_function(
        func=tool_func,
        name=tool_name,
        description=description
    )

# Create tools from MCP
tools = [
    create_langchain_tool("filesystem", "read_text_file", "Read a file"),
    create_langchain_tool("filesystem", "write_file", "Write a file"),
    create_langchain_tool("git", "git_status", "Get git status"),
]
```

## Using MCPToolWrapper

The MCPToolWrapper provides observability integration for MCP tools.

```python
from core.mcp.tool_wrapper import MCPToolWrapper, extract_mcp_text

# Create a wrapper for a specific tool
wrapper = MCPToolWrapper('git', 'git_status', 'Get git repository status')

# Call the tool (includes tracing and metrics)
result = wrapper.call(repo_path='/path/to/repo')
print(result)

# Mock mode for testing
import os
os.environ["DRYADE_MOCK_MODE"] = "true"
mock_result = wrapper.call(repo_path='/path/to/repo')  # Returns mock data
```

## Error Handling

Handle MCP errors gracefully with try/except.

```python
from core.exceptions import MCPTransportError, MCPTimeoutError, MCPRegistryError
from core.mcp import get_registry

registry = get_registry()

try:
    result = registry.call_tool("filesystem", "read_text_file", {"path": "/missing"})
except MCPTimeoutError:
    print("Tool execution timed out")
except MCPTransportError as e:
    print(f"Communication error: {e}")
except MCPRegistryError as e:
    print(f"Server not registered: {e}")
```

### Error Types

| Error | Cause | Recovery |
|-------|-------|----------|
| `MCPRegistryError` | Server not registered | Check config, enable server |
| `MCPTransportError` | Communication failed | Check server process, restart |
| `MCPTimeoutError` | Operation too slow | Increase timeout, simplify operation |

## Async Operations

All MCP operations have async variants.

```python
import asyncio
from core.mcp import get_registry

registry = get_registry()

async def process_files():
    # Async tool call
    result = await registry.acall_tool(
        "filesystem",
        "read_text_file",
        {"path": "/tmp/test.txt"}
    )
    return result.content[0].text if result.content else ""

# Run async
content = asyncio.run(process_files())
```

## Best Practices

### 1. Use Typed Wrappers When Available

Typed wrappers provide better IDE support and type safety:

```python
# Preferred
from core.mcp.servers import FilesystemServer
fs = FilesystemServer(registry)
content = fs.read_text_file("/tmp/test.txt")

# Instead of
result = registry.call_tool("filesystem", "read_text_file", {"path": "/tmp/test.txt"})
```

### 2. Check Server Status Before Operations

```python
from core.mcp import get_registry

registry = get_registry()

# Check if server is running
if registry.is_running("filesystem"):
    result = registry.call_tool("filesystem", "list_directory", {"path": "/tmp"})
else:
    print("Server not running - will auto-start on call")
```

### 3. Use Search for Dynamic Tool Selection

```python
from core.mcp import get_registry

registry = get_registry()

# Find the right tool for a task
results = registry.search_tools("read pdf content", mode="hybrid", top_k=3)
if results:
    best_match = results[0]
    result = registry.call_tool(
        best_match["server"],
        best_match["name"],
        {"path": "/tmp/document.pdf"}
    )
```

### 4. Cache Registry Reference

```python
from core.mcp import get_registry

# Get once and reuse
_registry = None

def get_mcp():
    global _registry
    if _registry is None:
        _registry = get_registry()
    return _registry

# Use cached reference
registry = get_mcp()
```

### 5. Handle Errors at Boundaries

```python
from core.exceptions import MCPTransportError, MCPTimeoutError

def safe_read_file(path: str) -> str | None:
    """Read file with graceful error handling."""
    try:
        registry = get_registry()
        result = registry.call_tool("filesystem", "read_text_file", {"path": path})
        return result.content[0].text if result.content else None
    except (MCPTransportError, MCPTimeoutError) as e:
        logger.warning(f"Failed to read {path}: {e}")
        return None
```

## Related Documentation

- [Server Documentation](/docs/mcp/servers/) - Individual server references
- [Adding Servers](/docs/mcp/integration/adding-servers.md) - How to add new MCP servers
- [Debugging Guide](/docs/mcp/integration/debugging.md) - Troubleshooting MCP issues
- [MCP Architecture](/docs/mcp/ARCHITECTURE.md) - System design overview
