# GitHub MCP Server

| Property | Value |
|----------|-------|
| **Package** | `@modelcontextprotocol/server-github` |
| **Category** | Developer |
| **Transport** | STDIO |
| **Default** | Disabled (requires credentials) |
| **Wrapper** | `core/mcp/servers/github.py` |

## Overview

The GitHub MCP Server provides comprehensive GitHub API integration for repositories, issues, and pull requests. It enables agents to perform complete GitHub workflows without leaving context.

### Key Features

- **Repository Management**: Create, fork, list, and inspect repositories
- **Issue Tracking**: Full CRUD operations on issues with comments
- **Pull Requests**: Create, merge, and manage PRs
- **Code Search**: Search code, issues, and repositories across GitHub
- **File Operations**: Read and push files directly to repositories

### When to Use

- Code review automation
- Issue triage and management
- PR creation and merging
- Code search across repositories
- Automated repository management

## Setup Instructions

### Step 1: Create GitHub Personal Access Token

1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Give it a descriptive name (e.g., "Dryade MCP Access")
4. Select the required scopes:
   - `repo` - Full repository access (required)
   - `read:org` - Read organization data (required for org repos)
   - `workflow` - GitHub Actions access (optional)
5. Click **"Generate token"**
6. Copy the token (starts with `ghp_`)

> **Note**: Fine-grained tokens are also supported. Ensure you grant access to the specific repositories you need.

### Step 2: Configure Environment

Add the token to your environment:

```bash
# Add to .env file
GITHUB_TOKEN=ghp_your_token_here
```

Or export directly:

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

### Step 3: Enable Server

Edit `config/mcp_servers.yaml`:

```yaml
github:
  enabled: true
```

## Configuration

Full configuration in `config/mcp_servers.yaml`:

```yaml
github:
  enabled: false  # Set to true after configuring GITHUB_TOKEN
  command:
    - npx
    - -y
    - '@modelcontextprotocol/server-github'
  env:
    GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_TOKEN}
  description: GitHub integration for repositories, issues, pull requests
  auto_restart: true
  max_restarts: 3
  timeout: 60.0
```

## Tool Reference

### Repository Operations

#### list_repos

List repositories for an owner.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | GitHub username or organization name |

**Returns**: Array of repository objects

```python
repos = await gh.list_repos("microsoft")
for repo in repos:
    print(f"{repo.full_name}: {repo.description}")
```

#### get_repo

Get detailed information about a specific repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |

**Returns**: Repository object with full details

```python
repo = await gh.get_repo("microsoft", "vscode")
print(f"Default branch: {repo.default_branch}")
print(f"Private: {repo.private}")
```

#### create_repo

Create a new repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Repository name |
| `description` | string | No | Repository description |
| `private` | boolean | No | Whether repository is private (default: false) |

**Returns**: Created repository object

```python
repo = await gh.create_repo(
    name="my-project",
    description="My awesome project",
    private=True
)
print(f"Created: {repo.url}")
```

#### fork_repo

Fork an existing repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Original repository owner |
| `repo` | string | Yes | Original repository name |

**Returns**: Forked repository object

```python
fork = await gh.fork_repo("facebook", "react")
print(f"Forked to: {fork.full_name}")
```

### Issue Operations

#### list_issues

List issues in a repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `state` | string | No | Filter by state: "open", "closed", "all" (default: "open") |

**Returns**: Array of issue objects

```python
issues = await gh.list_issues("owner", "repo", state="open")
for issue in issues:
    print(f"#{issue.number}: {issue.title} [{issue.state}]")
```

#### create_issue

Create a new issue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `title` | string | Yes | Issue title |
| `body` | string | No | Issue body/description |

**Returns**: Created issue object

```python
issue = await gh.create_issue(
    owner="owner",
    repo="repo",
    title="Bug: Login fails on mobile",
    body="## Steps to reproduce\n1. Open app on mobile\n2. Try to log in\n\n## Expected\nLogin succeeds"
)
print(f"Created issue #{issue.number}: {issue.url}")
```

#### update_issue

Update an existing issue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `issue_number` | integer | Yes | Issue number |
| `title` | string | No | New title |
| `body` | string | No | New body |
| `state` | string | No | New state: "open" or "closed" |
| `labels` | array | No | New labels |

**Returns**: Updated issue object

```python
issue = await gh.update_issue(
    owner="owner",
    repo="repo",
    number=123,
    state="closed",
    labels=["resolved", "v1.2.0"]
)
```

#### add_issue_comment

Add a comment to an issue.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `issue_number` | integer | Yes | Issue number |
| `body` | string | Yes | Comment body |

**Returns**: Result message

```python
await gh.add_issue_comment(
    owner="owner",
    repo="repo",
    number=123,
    body="Fixed in commit abc123. Will be released in v1.2.0."
)
```

### Pull Request Operations

#### list_pull_requests

List pull requests in a repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `state` | string | No | Filter by state: "open", "closed", "all" (default: "open") |

**Returns**: Array of PR objects

```python
prs = await gh.list_prs("owner", "repo", state="open")
for pr in prs:
    print(f"PR #{pr.number}: {pr.title} ({pr.head_ref} -> {pr.base_ref})")
```

#### create_pull_request

Create a new pull request.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `title` | string | Yes | PR title |
| `head` | string | Yes | Head branch name (source) |
| `base` | string | Yes | Base branch name (target) |
| `body` | string | No | PR description |

**Returns**: Created PR object

```python
pr = await gh.create_pr(
    owner="owner",
    repo="repo",
    title="feat: Add user authentication",
    head="feature/auth",
    base="main",
    body="## Summary\nAdds JWT-based authentication.\n\n## Test Plan\n- [ ] Unit tests pass\n- [ ] Integration tests pass"
)
print(f"Created PR #{pr.number}: {pr.url}")
```

#### merge_pull_request

Merge a pull request.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `pull_number` | integer | Yes | PR number |
| `commit_message` | string | No | Custom merge commit message |

**Returns**: Result message

```python
result = await gh.merge_pr(
    owner="owner",
    repo="repo",
    number=456,
    commit_message="Merge feature/auth: Add user authentication"
)
```

### Search Operations

#### search_code

Search code across GitHub.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | GitHub search query |

**Returns**: Array of search results

```python
# Find all uses of a specific function
results = await gh.search_code("useEffect repo:facebook/react")
for r in results:
    print(f"{r['repository']['full_name']}: {r['path']}")
```

#### search_issues

Search issues and pull requests.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | GitHub search query |

**Returns**: Array of search results

```python
# Find open bugs assigned to me
results = await gh.search_issues("is:issue is:open assignee:@me label:bug")
```

#### search_repos

Search repositories.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | GitHub search query |

**Returns**: Array of search results

```python
# Find popular Python ML repos
results = await gh.search_repos("machine learning language:python stars:>1000")
```

### File Operations

#### get_file_contents

Read file contents from a repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `path` | string | Yes | File path in repository |
| `branch` | string | No | Branch name (default: default branch) |

**Returns**: File contents as string

```python
content = await gh.get_file_contents(
    owner="microsoft",
    repo="vscode",
    path="package.json",
    branch="main"
)
```

#### push_files

Push files to a repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | Yes | Repository owner |
| `repo` | string | Yes | Repository name |
| `branch` | string | Yes | Target branch |
| `files` | array | Yes | Array of `{path, content}` objects |
| `message` | string | Yes | Commit message |

**Returns**: Result message

```python
result = await gh.push_files(
    owner="owner",
    repo="repo",
    branch="main",
    files=[
        {"path": "README.md", "content": "# My Project\n\nUpdated readme."},
        {"path": "docs/CHANGELOG.md", "content": "# Changelog\n\n## v1.0.0\n- Initial release"}
    ],
    message="docs: Update README and add changelog"
)
```

## Python Wrapper Usage

The `GitHubServer` wrapper provides a typed Python interface:

```python
from core.mcp import get_registry
from core.mcp.servers import GitHubServer

# Get registry and create server wrapper
registry = get_registry()
gh = GitHubServer(registry)

# List open issues
issues = await gh.list_issues("owner", "repo", state="open")

# Create a pull request
pr = await gh.create_pr(
    owner="owner",
    repo="repo",
    title="Fix authentication bug",
    head="fix/auth-bug",
    base="main",
    body="This PR fixes the authentication timeout issue."
)

# Merge the PR after review
await gh.merge_pr("owner", "repo", pr.number)
```

### Data Types

The wrapper provides typed dataclasses:

```python
@dataclass
class GitHubRepo:
    full_name: str
    description: str | None
    default_branch: str
    private: bool
    url: str

@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str | None
    state: str
    labels: list[str]
    url: str

@dataclass
class GitHubPR:
    number: int
    title: str
    body: str | None
    state: str
    head_ref: str
    base_ref: str
    url: str
```

## Security Considerations

### Token Scope Principle of Least Privilege

Only grant the scopes your workflows actually need:

| Scope | Use Case |
|-------|----------|
| `repo` | Full repo access (issues, PRs, code) |
| `public_repo` | Public repositories only |
| `read:org` | Read organization membership |
| `workflow` | Trigger and manage GitHub Actions |

### Best Practices

1. **Never commit tokens to git** - Use environment variables or secret management
2. **Use fine-grained tokens** when possible - Limit access to specific repositories
3. **Rotate tokens regularly** - Set expiration dates on tokens
4. **Audit token usage** - Review token activity in GitHub settings
5. **Use separate tokens** for different environments (dev, staging, prod)

### Environment Variable Security

```bash
# Good: Use .env file (gitignored)
echo "GITHUB_TOKEN=ghp_xxx" >> .env
echo ".env" >> .gitignore

# Good: Use secret management
export GITHUB_TOKEN=$(vault read -field=token secret/github)

# Bad: Hardcoded in code or config
# NEVER do this
```

## Troubleshooting

### Common Errors

#### "Bad credentials"

**Cause**: GITHUB_TOKEN is invalid or not set.

**Solution**:
1. Verify token is set: `echo $GITHUB_TOKEN`
2. Check token hasn't expired in GitHub settings
3. Regenerate token if necessary

#### "Not Found" (404)

**Cause**: Repository doesn't exist or token lacks access.

**Solution**:
1. Verify repository exists and is spelled correctly
2. Check token has `repo` scope for private repos
3. For org repos, ensure `read:org` scope is granted

#### "Rate limit exceeded"

**Cause**: Too many API requests.

**Solution**:
1. Authenticated requests get 5,000/hour (vs 60 unauthenticated)
2. Implement caching for repeated queries
3. Use conditional requests with ETags

#### "Merge conflict"

**Cause**: PR cannot be automatically merged.

**Solution**:
1. Resolve conflicts locally
2. Push resolution to head branch
3. Retry merge

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger("core.mcp.servers.github").setLevel(logging.DEBUG)
```

## Related Documentation

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
- [GitHub API Documentation](https://docs.github.com/en/rest)
