# Linear MCP Server

| Property | Value |
|----------|-------|
| **Package** | `@tacticlaunch/mcp-linear` |
| **Category** | Developer |
| **Transport** | STDIO |
| **Default** | Disabled (requires credentials) |
| **Wrapper** | `core/mcp/servers/linear.py` |

## Overview

The Linear MCP Server provides issue tracking and project management integration with Linear. It enables agents to manage issues, projects, and teams directly from automated workflows.

### Key Features

- **Issue Management**: Create, update, list, and search issues
- **Project Tracking**: List and manage projects
- **Team Support**: Access team information and structure
- **Comments**: Add comments to issues for collaboration
- **Priority & State**: Control issue workflow states

### When to Use

- Sprint planning and task management
- Bug tracking and issue triage
- Automated issue creation from code analysis
- Release management workflows
- Developer productivity automation

## Setup Instructions

### Step 1: Get Linear API Key

1. Go to [https://linear.app/settings/api](https://linear.app/settings/api)
2. Under **"Personal API Keys"**, click **"Create key"**
3. Give it a descriptive name (e.g., "Dryade MCP Integration")
4. Copy the key (starts with `lin_api_`)

> **Security Note**: API keys provide full access to your Linear workspace. Treat them as sensitive credentials.

### Step 2: Configure Environment

Add the token to your environment:

```bash
# Add to .env file
LINEAR_API_KEY=lin_api_your_key_here
```

Or export directly:

```bash
export LINEAR_API_KEY=lin_api_your_key_here
```

### Step 3: Enable Server

Edit `config/mcp_servers.yaml`:

```yaml
linear:
  enabled: true
```

## Configuration

Full configuration in `config/mcp_servers.yaml`:

```yaml
linear:
  enabled: false  # Set to true after configuring LINEAR_API_KEY
  command:
    - npx
    - -y
    - '@anthropic/mcp-server-linear'
  env:
    LINEAR_API_KEY: ${LINEAR_API_KEY}
  description: Issue tracking and project management with Linear
  auto_restart: true
  max_restarts: 3
  timeout: 30.0
```

## Linear Concepts

Before using the tools, understand Linear's hierarchy:

### Organizational Structure

```
Workspace
├── Team 1 (key: "ENG")
│   ├── Issues (ENG-1, ENG-2, ...)
│   ├── Projects
│   └── Cycles
├── Team 2 (key: "DES")
│   ├── Issues (DES-1, DES-2, ...)
│   └── Projects
└── Team 3 (key: "OPS")
    └── ...
```

### Issue States

Linear issues flow through workflow states:

| State | Description |
|-------|-------------|
| Backlog | Not yet planned |
| Todo | Planned for work |
| In Progress | Currently being worked on |
| In Review | Ready for review |
| Done | Completed |
| Canceled | No longer needed |

### Priority Levels

| Value | Level | Description |
|-------|-------|-------------|
| 0 | No priority | Not prioritized |
| 1 | Urgent | Critical, immediate attention |
| 2 | High | Important, address soon |
| 3 | Medium | Normal priority |
| 4 | Low | Can wait |

## Tool Reference

### Team Operations

#### linear_list_teams

List all teams in the workspace.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | Lists all accessible teams |

**Returns**: Array of team objects

```python
teams = await linear.list_teams()
for team in teams:
    print(f"{team.name} ({team.key}): {team.id}")
```

### Issue Operations

#### linear_list_issues

List issues, optionally filtered by team and state.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `teamId` | string | No | Filter by team ID |
| `state` | string | No | Filter by state name |

**Returns**: Array of issue objects

```python
# List all open issues
issues = await linear.list_issues()

# List issues for specific team
issues = await linear.list_issues(team_id="team-uuid")

# List issues in specific state
issues = await linear.list_issues(state="In Progress")
```

#### linear_create_issue

Create a new issue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `teamId` | string | Yes | Team ID to create issue in |
| `title` | string | Yes | Issue title |
| `description` | string | No | Issue description (markdown) |
| `priority` | integer | No | Priority level (0-4, default: 0) |

**Returns**: Created issue object

```python
issue = await linear.create_issue(
    team_id="team-uuid",
    title="Fix authentication timeout",
    description="""
## Problem
Users are experiencing authentication timeouts after 5 minutes of inactivity.

## Expected Behavior
Session should persist for at least 30 minutes.

## Steps to Reproduce
1. Log in to the application
2. Wait 5 minutes without activity
3. Try to perform any action
    """,
    priority=2  # High priority
)
print(f"Created: {issue.identifier} - {issue.url}")
```

#### linear_update_issue

Update an existing issue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `issueId` | string | Yes | Issue ID to update |
| `title` | string | No | New title |
| `description` | string | No | New description |
| `state` | string | No | New state name |
| `priority` | integer | No | New priority (0-4) |

**Returns**: Updated issue object

```python
# Update issue status
issue = await linear.update_issue(
    issue_id="issue-uuid",
    state="In Progress"
)

# Update priority
issue = await linear.update_issue(
    issue_id="issue-uuid",
    priority=1  # Urgent
)

# Update multiple fields
issue = await linear.update_issue(
    issue_id="issue-uuid",
    title="[URGENT] Fix authentication timeout",
    priority=1,
    description="Updated description..."
)
```

#### linear_search_issues

Search issues by query.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query string |

**Returns**: Array of matching issues

```python
# Search by keyword
issues = await linear.search_issues("authentication")

# Search with specific terms
issues = await linear.search_issues("bug timeout")
```

### Comment Operations

#### linear_create_comment

Add a comment to an issue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `issueId` | string | Yes | Issue ID to comment on |
| `body` | string | Yes | Comment body (markdown) |

**Returns**: void

```python
await linear.add_comment(
    issue_id="issue-uuid",
    body="Fixed in commit abc123. Deploying to staging for verification."
)
```

### Project Operations

#### linear_list_projects

List projects, optionally filtered by team.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `teamId` | string | No | Filter by team ID |

**Returns**: Array of project objects

```python
# List all projects
projects = await linear.list_projects()

# List projects for specific team
projects = await linear.list_projects(team_id="team-uuid")

for project in projects:
    print(f"{project.name}: {project.state}")
```

## Python Wrapper Usage

The `LinearServer` wrapper provides a typed Python interface:

```python
from core.mcp import get_registry
from core.mcp.servers import LinearServer

# Get registry and create server wrapper
registry = get_registry()
linear = LinearServer(registry)

# Complete workflow example
# 1. Get teams to find team ID
teams = await linear.list_teams()
eng_team = next(t for t in teams if t.key == "ENG")

# 2. Create an issue
issue = await linear.create_issue(
    team_id=eng_team.id,
    title="Implement user authentication",
    description="Add JWT-based authentication to the API.",
    priority=2
)
print(f"Created: {issue.identifier}")

# 3. Update status as work progresses
await linear.update_issue(issue.id, state="In Progress")

# 4. Add progress comment
await linear.add_comment(issue.id, "Started implementation, ETA 2 days")

# 5. Mark as done
await linear.update_issue(issue.id, state="Done")
```

### Data Types

```python
@dataclass
class LinearTeam:
    id: str
    name: str
    key: str  # e.g., "ENG", "DES"

@dataclass
class LinearIssue:
    id: str
    identifier: str  # e.g., "ENG-123"
    title: str
    description: str | None
    state: str
    priority: int
    url: str

@dataclass
class LinearProject:
    id: str
    name: str
    description: str | None
    state: str
```

## Common Workflows

### Sprint Planning

```python
# List backlog issues
backlog = await linear.list_issues(team_id=team.id, state="Backlog")

# Prioritize and move to sprint
for issue in backlog[:5]:  # Take top 5
    await linear.update_issue(issue.id, state="Todo")
```

### Bug Tracking

```python
# Create bug from automated detection
bug = await linear.create_issue(
    team_id=eng_team.id,
    title=f"[Auto-detected] {error_type}",
    description=f"""
## Error Details
{error_message}

## Stack Trace
```
{stack_trace}
```

## Affected Users
{affected_count}
    """,
    priority=1 if is_critical else 3
)
```

### Release Management

```python
# Find all issues for release
release_issues = await linear.search_issues("v2.0.0")

# Update release notes
for issue in release_issues:
    await linear.add_comment(
        issue.id,
        f"Included in release v2.0.0 (deployed {today})"
    )
```

### Code Review Integration

```python
# Link issue to PR
await linear.add_comment(
    issue_id=issue.id,
    body=f"PR opened: {pr_url}\n\nReady for review."
)

# Update status
await linear.update_issue(issue.id, state="In Review")
```

## Security Considerations

### API Key Security

1. **Never commit API keys** - Use environment variables
2. **Limit key scope** - Linear keys have full access, be careful
3. **Rotate regularly** - Regenerate keys periodically
4. **Audit access** - Review Linear settings for active keys

### Environment Setup

```bash
# Good: Use .env file (gitignored)
echo "LINEAR_API_KEY=lin_api_xxx" >> .env
echo ".env" >> .gitignore

# Good: Use secret management
export LINEAR_API_KEY=$(vault read -field=token secret/linear)
```

## Troubleshooting

### Common Errors

#### "Unauthorized"

**Cause**: LINEAR_API_KEY is invalid or not set.

**Solution**:
1. Verify key is set: `echo $LINEAR_API_KEY`
2. Check key in Linear settings
3. Regenerate key if needed

#### "Team not found"

**Cause**: Team ID is incorrect or you don't have access.

**Solution**:
1. List teams first: `await linear.list_teams()`
2. Use team ID (UUID), not key
3. Verify workspace access

#### "Invalid priority"

**Cause**: Priority value outside 0-4 range.

**Solution**:
Use integer values: 0 (none), 1 (urgent), 2 (high), 3 (medium), 4 (low)

#### "State not found"

**Cause**: State name doesn't match team's workflow.

**Solution**:
1. Check team's workflow states in Linear settings
2. Use exact state names (case-sensitive)

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("core.mcp.servers.linear").setLevel(logging.DEBUG)
```

## Performance Tips

1. **Cache team IDs** - Teams don't change frequently
2. **Batch operations** - Group related updates
3. **Use search** - More efficient than listing all issues
4. **Limit results** - Filter by team and state when possible

## Related Documentation

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
- [Linear API Documentation](https://developers.linear.app/docs)
