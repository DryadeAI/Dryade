# MCP Servers Guide

Model Context Protocol (MCP) servers provide tools that agents can use. This guide covers the MCP servers included in Dryade Community Edition.

## Overview

MCP servers run as separate processes and communicate with Dryade via stdio transport. Each server provides specialized tools for agents.

Dryade Community Edition includes **9 MCP servers** covering file operations, version control, browser automation, and document processing.

## Configuration

MCP servers are configured in `config/mcp_servers.community.yaml`:

```yaml
servers:
  filesystem:
    enabled: true  # Set to true to enable
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    description: "File operations"
    auto_restart: true
    max_restarts: 3
```

### Configuration Options

| Option | Description |
|--------|-------------|
| `enabled` | Whether to start this server |
| `command` | Command to run the server |
| `env` | Environment variables |
| `description` | Human-readable description |
| `auto_restart` | Restart on crash |
| `max_restarts` | Maximum restart attempts |
| `timeout` | Request timeout in seconds |

## Core MCP Servers

These servers require no credentials and are enabled by default.

### Filesystem

**Purpose**: Secure file operations with directory access control

**Tools provided**:
- `read_file`: Read file contents
- `write_file`: Write to file
- `list_directory`: List directory contents
- `create_directory`: Create directory
- `move_file`: Move or rename file
- `delete_file`: Delete file

**Configuration**:
```yaml
filesystem:
  enabled: true
  command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

The last argument is the allowed directory. Change to restrict access:
```yaml
command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]
```

### Git

**Purpose**: Git repository operations

**Tools provided**:
- `git_status`: Show working tree status
- `git_diff`: Show changes
- `git_log`: Show commit history
- `git_commit`: Create a commit
- `git_branch`: List/create branches
- `git_checkout`: Switch branches

**Configuration**:
```yaml
git:
  enabled: true
  command: ["uvx", "mcp-server-git", "--repository", "."]
```

Change the `--repository` argument to work with different repos.

### Memory

**Purpose**: Persistent knowledge graph for agent memory

**Tools provided**:
- `create_entities`: Create knowledge entities
- `create_relations`: Create relationships
- `search_nodes`: Search the graph
- `read_graph`: Read entire graph

**Configuration**:
```yaml
memory:
  enabled: true
  command: ["npx", "-y", "@modelcontextprotocol/server-memory"]
```

## Developer Productivity MCP Servers

These servers enhance developer workflows. Some require credentials you provide.

### Playwright

**Purpose**: Browser automation for testing and screenshots

**Tools provided**:
- `navigate`: Go to URL
- `screenshot`: Take screenshot
- `click`: Click element
- `fill`: Fill form field
- `evaluate`: Run JavaScript

**Configuration**:
```yaml
playwright:
  enabled: true
  command: ["npx", "-y", "@playwright/mcp@latest"]
```

**Note**: First run may take longer as Playwright downloads browser binaries.

### GitHub

**Purpose**: GitHub API integration

**Setup**:
1. Create a GitHub Personal Access Token
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `repo`, `read:org`
   - Copy the token

2. Add to `.env`:
   ```
   GITHUB_TOKEN=ghp_your_token_here
   ```

3. Enable in config:
   ```yaml
   github:
     enabled: true
   ```

**Tools provided**:
- `search_repositories`: Search repos
- `create_issue`: Create issue
- `list_pull_requests`: List PRs
- `get_file_contents`: Read file from repo
- `create_pull_request`: Create PR
- `list_commits`: Get commit history

### Context7

**Purpose**: Library documentation lookup for up-to-date API references

**Setup**:
```yaml
context7:
  enabled: true
```

No credentials required.

**Tools provided**:
- `resolve_library_id`: Find library documentation
- `get_library_docs`: Get documentation for a library

### Linear

**Purpose**: Issue tracking with Linear

**Setup**:
1. Get API key from https://linear.app/settings/api
2. Add to `.env`:
   ```
   LINEAR_API_KEY=lin_api_your_key
   ```
3. Enable in config:
   ```yaml
   linear:
     enabled: true
   ```

**Tools provided**:
- `create_issue`: Create Linear issue
- `search_issues`: Search issues
- `update_issue`: Update issue status
- `get_issue`: Get issue details

## Document Processing MCP Servers

These servers handle document operations.

### PDF Reader

**Purpose**: PDF extraction (text, tables, images, structure)

**Setup**:
```yaml
pdf-reader:
  enabled: true
```

No credentials required.

**Tools provided**:
- `read_pdf`: Extract text from PDF
- `extract_tables`: Extract tables from PDF
- `get_pdf_info`: Get PDF metadata

### Document Operations (Excel)

**Purpose**: Excel file operations

**Setup**:
```yaml
document-ops:
  enabled: true
```

No credentials required.

**Tools provided**:
- `read_excel`: Read Excel file
- `write_excel`: Write to Excel file
- `create_sheet`: Create new sheet
- `list_sheets`: List sheets in workbook

## Managing MCP Servers

### Check Status

```bash
curl http://localhost:8000/api/mcp/servers
```

Response:
```json
[
  {"name": "filesystem", "status": "running"},
  {"name": "git", "status": "running"},
  {"name": "github", "status": "stopped"}
]
```

### Restart Servers

```bash
# Restart all
curl -X POST http://localhost:8000/api/mcp/restart

# Restart specific server
curl -X POST http://localhost:8000/api/mcp/servers/filesystem/restart
```

### View Server Logs

```bash
# With Docker
docker logs dryade-api | grep "MCP"

# Without Docker
tail -f logs/api.log | grep "MCP"
```

## Troubleshooting

### Server won't start

**Check**: Is the command available?
```bash
npx -y @modelcontextprotocol/server-filesystem --help
```

**Check**: Is Node.js installed?
```bash
node --version  # Need 18+
```

### Server times out

**Solution**: Increase timeout
```yaml
playwright:
  timeout: 120.0  # seconds
```

### Authentication errors

**Check**: Environment variables are set
```bash
echo $GITHUB_TOKEN
```

**Check**: .env file is loaded
```bash
grep GITHUB_TOKEN .env
```

## Adding Custom MCP Servers

You can add any MCP-compatible server:

```yaml
servers:
  my_custom_server:
    enabled: true
    command: ["python", "my_mcp_server.py"]
    description: "My custom tools"
    auto_restart: true
```

The server must implement the MCP protocol over stdio.

## Enterprise MCP Servers

The following servers are available in Dryade Enterprise:

- **DBHub**: Database operations (Postgres, MySQL, SQLite, and more)
- **Grafana**: Metrics and dashboard integration

These servers enable advanced data operations and monitoring capabilities.

Learn more: https://dryade.ai/enterprise
