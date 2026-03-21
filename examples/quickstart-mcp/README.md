# MCP Server Quickstart

Connect external tools to Dryade via the Model Context Protocol (MCP).

## What You'll Learn

- What MCP servers are and how they extend Dryade
- How to configure and connect an MCP server
- How Dryade discovers and routes to MCP tools
- How to test MCP tool calling in a conversation

## Prerequisites

- Docker and Docker Compose installed
- An LLM API key (OpenAI or Anthropic recommended)

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io) is an open standard for connecting AI models to external tools and data sources. MCP servers expose capabilities (tools, resources, prompts) that Dryade can discover and use automatically.

In this example, we connect a **filesystem MCP server** that lets your AI assistant read and navigate files in a workspace directory.

## Steps

### 1. Configure your environment

```bash
cp .env.example .env
```

Edit `.env` with your API key.

### 2. Review the MCP configuration

The `mcp-config.yaml` file defines which MCP servers Dryade should connect to:

```yaml
servers:
  filesystem:
    enabled: true
    command:
      - npx
      - --silent
      - -y
      - "@modelcontextprotocol/server-filesystem"
      - /workspace
    description: "Secure file operations with directory access control"
    timeout: 120.0
    auto_restart: true
    max_restarts: 3
```

Key fields:
- **command** -- How to start the MCP server process
- **description** -- Human-readable description shown in the UI
- **timeout** -- Max seconds to wait for server startup
- **auto_restart** -- Automatically restart if the server crashes

### 3. Start the services

```bash
docker compose up -d
```

The compose file mounts:
- `mcp-config.yaml` into the Dryade container
- A `workspace/` directory that the filesystem MCP server can access

### 4. Create test files

Create some files in the workspace for the MCP server to access:

```bash
mkdir -p workspace
echo "Hello from the MCP quickstart!" > workspace/hello.txt
echo "Project: Dryade MCP Example" > workspace/project-info.txt
```

Then restart to pick up the new files:

```bash
docker compose restart dryade
```

### 5. Test MCP tools

1. Open [http://localhost:3000](http://localhost:3000)
2. Start a new conversation
3. Ask: "List the files in the /workspace directory"
4. The AI will use the filesystem MCP tools to read the directory
5. Ask: "Read the contents of hello.txt"
6. The AI will use the `read_file` tool to show the file contents

### Expected Result

Dryade should:
- Discover the filesystem MCP server on startup
- Register its tools (read_file, list_directory, etc.)
- Route your natural language requests to the appropriate MCP tools
- Return file contents and directory listings

You can verify MCP server status via the API:

```bash
curl http://localhost:8080/api/mcp/servers
```

## How MCP Routing Works

When you send a message, Dryade's HierarchicalToolRouter:

1. Analyzes your request for tool-calling intent
2. Searches all connected MCP servers for matching tools
3. Uses semantic matching (understanding intent) and regex matching (pattern-based)
4. Calls the matched tool on the appropriate MCP server
5. Returns the result to the LLM for final response generation

Multiple MCP servers can be connected simultaneously. Dryade handles discovery, routing, and error recovery automatically.

## Adding More MCP Servers

Edit `mcp-config.yaml` to add more servers. Popular MCP servers include:

| Server | Package | Description |
|--------|---------|-------------|
| Filesystem | `@modelcontextprotocol/server-filesystem` | File read/write operations |
| Git | `mcp-server-git` | Git repository operations |
| Memory | `@modelcontextprotocol/server-memory` | Persistent key-value memory |
| Brave Search | `@anthropic/mcp-server-brave-search` | Web search via Brave |
| Puppeteer | `@anthropic/mcp-server-puppeteer` | Browser automation |

See the [MCP Server Directory](https://modelcontextprotocol.io/servers) for the full list.

## Troubleshooting

**"MCP server failed to start":**
- Check that Node.js/npx is available inside the container
- View server logs: `docker compose logs dryade | grep -i mcp`

**Tools not discovered:**
- Verify `mcp-config.yaml` is mounted correctly: `docker compose exec dryade cat /app/config/mcp_servers.yaml`
- Restart the backend: `docker compose restart dryade`

**"Permission denied" on file operations:**
- The filesystem server only has access to directories listed in its command args
- Add more directories by modifying the command in `mcp-config.yaml`

## What's Next

- Read about [MCP in Dryade](https://dryade.ai/docs/using-dryade/mcp) for advanced configuration
- Try the [Agent Quickstart](../quickstart-agent/) to combine agents with MCP tools
- Browse the [MCP Server Directory](https://modelcontextprotocol.io/servers) for more integrations
- Join [Discord](https://discord.gg/bvCPwqmu) for help

## Cleanup

```bash
docker compose down        # Stop services
docker compose down -v     # Stop and remove data volumes
rm -rf workspace           # Remove test files
```

---

*Licensed under [DSUL](../../LICENSE)*
