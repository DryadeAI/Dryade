---
title: MCP Servers
sidebar_position: 5
---

# MCP Servers

MCP (Model Context Protocol) is an open standard for connecting AI models to external tools. Dryade uses MCP servers to give agents capabilities like file access, Git operations, browser automation, and third-party integrations.

![MCP servers configuration showing server cards with status indicators, toggle switches, and tool counts](/img/screenshots/agents-panel.png)

## How MCP Works in Dryade

Each MCP server is a separate process that provides a set of tools. When you enable an MCP server, its tools become available to agents during conversations. The agent discovers available tools automatically and selects the right one based on your request.

You do not need to tell the agent which server to use -- Dryade routes tool calls to the correct server behind the scenes.

## Available MCP Servers

### Core Servers (No Credentials Required)

These servers work out of the box with no additional setup.

#### Filesystem

Secure file operations with directory access control.

**Tools:** read_file, write_file, list_directory, create_directory, move_file, delete_file

**Configuration:**
```yaml
filesystem:
  enabled: true
  command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

The last argument specifies the allowed directory. Change it to control which files the agent can access.

#### Git

Git repository operations for version control workflows.

**Tools:** git_status, git_diff, git_log, git_commit, git_branch, git_checkout

**Configuration:**
```yaml
git:
  enabled: true
  command: ["uvx", "mcp-server-git", "--repository", "."]
```

Change `--repository` to work with a different repository path.

#### Memory

Persistent knowledge graph for agent memory across conversations.

**Tools:** create_entities, create_relations, search_nodes, read_graph

**Configuration:**
```yaml
memory:
  enabled: true
  command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
```

#### Playwright

Browser automation for web interactions and screenshots.

**Tools:** navigate, screenshot, click, fill, evaluate

**Configuration:**
```yaml
playwright:
  enabled: true
  command: ["npx", "-y", "@playwright/mcp@latest"]
```

First run may take longer as Playwright downloads browser binaries.

#### PDF Reader

Extract text, tables, and metadata from PDF files.

**Tools:** read_pdf, extract_tables, get_pdf_info

**Configuration:**
```yaml
pdf-reader:
  enabled: true
```

#### Document Operations (Excel)

Read and write Excel files.

**Tools:** read_excel, write_excel, create_sheet, list_sheets

**Configuration:**
```yaml
document-ops:
  enabled: true
```

#### Context7

Library documentation lookup for up-to-date API references.

**Tools:** resolve_library_id, get_library_docs

**Configuration:**
```yaml
context7:
  enabled: true
```

### Integration Servers (Credentials Required)

These servers connect to third-party services and require API keys.

#### GitHub

GitHub API integration for repository management.

**Tools:** search_repositories, create_issue, list_pull_requests, get_file_contents, create_pull_request, list_commits

**Setup:**
1. Create a Personal Access Token at [github.com/settings/tokens](https://github.com/settings/tokens) with `repo` and `read:org` scopes
2. Add `GITHUB_TOKEN=ghp_your_token_here` to your `.env` file
3. Enable in config:
```yaml
github:
  enabled: true
```

#### Linear

Issue tracking with Linear.

**Tools:** create_issue, search_issues, update_issue, get_issue

**Setup:**
1. Get an API key from [linear.app/settings/api](https://linear.app/settings/api)
2. Add `LINEAR_API_KEY=lin_api_your_key` to your `.env` file
3. Enable in config:
```yaml
linear:
  enabled: true
```

## Configuring MCP Servers

MCP servers are configured in `config/mcp_servers.community.yaml`. Each server entry supports these options:

| Option | Description | Default |
|--------|-------------|---------|
| `enabled` | Whether to start this server | `false` |
| `command` | Command to run the server | Required |
| `env` | Environment variables to pass | None |
| `description` | Human-readable description | None |
| `auto_restart` | Restart on crash | `true` |
| `max_restarts` | Maximum restart attempts | `3` |
| `timeout` | Request timeout in seconds | `30` |

You can also manage MCP servers from the [Settings](/using-dryade/settings) page in the Dryade UI.

## Managing MCP Servers at Runtime

### Check Server Status

View which servers are running from the Settings page, or via the API:

```bash
curl http://localhost:8000/api/mcp/servers
```

### Restart Servers

If a server stops responding:

```bash
# Restart all servers
curl -X POST http://localhost:8000/api/mcp/restart

# Restart a specific server
curl -X POST http://localhost:8000/api/mcp/servers/filesystem/restart
```

## Adding Custom MCP Servers

You can add any MCP-compatible server to Dryade:

```yaml
servers:
  my_custom_server:
    enabled: true
    command: ["python", "my_mcp_server.py"]
    description: "My custom tools"
    auto_restart: true
```

The server must implement the MCP protocol over stdio transport. See the [MCP specification](https://modelcontextprotocol.io/) for details on building your own server.

## Troubleshooting

### Server will not start

**Check:** Is the command available?
```bash
npx -y @modelcontextprotocol/server-filesystem --help
```

**Check:** Is Node.js 18+ installed?
```bash
node --version
```

### Server times out

Increase the timeout for slow servers:
```yaml
playwright:
  timeout: 120.0
```

### Authentication errors (GitHub, Linear)

Make sure environment variables are set:
```bash
echo $GITHUB_TOKEN
```

And that the `.env` file is loaded by Dryade.

### Tools not appearing in conversations

1. Verify the server is enabled in config
2. Check that the server is running (Settings page or API)
3. Restart the server if needed

## Tips

- **Start with core servers.** Filesystem, Git, and Memory cover most use cases and need no credentials.
- **Restrict filesystem access.** Set the allowed directory to only what the agent needs. Avoid giving access to your entire system.
- **Monitor server health.** Check the Settings page periodically to ensure servers are running.
- **Use auto_restart.** Enable automatic restart so a server crash does not interrupt your work.
