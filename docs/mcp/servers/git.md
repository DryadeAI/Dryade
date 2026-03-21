# Git MCP Server

| Field | Value |
|-------|-------|
| **Package** | `mcp-server-git` (via uvx) |
| **Category** | Core |
| **Default** | Enabled |
| **Transport** | STDIO |

## Overview

The Git MCP Server provides repository operations including status, diff, commit, and branch management. It enables agents to interact with Git repositories through a Python-based MCP server.

**Key Features:**
- Full Git status and diff capabilities
- Commit and staging operations
- Branch creation and checkout
- Commit history exploration

**When to Use:**
- Checking repository status before/after changes
- Staging and committing code changes
- Creating and switching branches
- Reviewing commit history and diffs

## Configuration

```yaml
git:
  enabled: true
  command:
    - uvx
    - mcp-server-git
    - --repository
    - .
  description: Git repository operations (status, diff, commit, branch)
  auto_restart: true
  max_restarts: 3
```

**Configuration Notes:**
- Uses `uvx` to run the Python-based mcp-server-git package
- The `--repository .` argument sets the default repository path
- Repository paths can be overridden per-call via `repo_path` parameter

## Environment Variables

None required. The git server uses local git configuration.

## Tool Reference

### git_status

Show the working tree status including branch info and file changes.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |

**Returns:** Git status output including branch info and file status.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Get repository status
status = git.status("$HOME/project")
print(status)
```

---

### git_diff_unstaged

Show unstaged changes in the working directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |

**Returns:** Diff output for unstaged changes.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# See what's changed but not staged
diff = git.diff_unstaged("$HOME/project")
print(diff)
```

---

### git_diff_staged

Show staged changes (changes in the index ready for commit).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |

**Returns:** Diff output for staged changes.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# See what's staged for commit
staged = git.diff_staged("$HOME/project")
print(staged)
```

---

### git_diff

Show diff between current state and a specific branch or commit.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `target` | string | Yes | Branch name, commit hash, or ref to diff against |

**Returns:** Diff output comparing current state to target.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Compare to main branch
diff = git.diff("$HOME/project", "main")

# Compare to specific commit
diff = git.diff("$HOME/project", "abc1234")

# Compare to HEAD~3
diff = git.diff("$HOME/project", "HEAD~3")
```

---

### git_commit

Record changes to the repository with a commit message.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `message` | string | Yes | Commit message |

**Returns:** Commit result message with hash.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Commit staged changes
result = git.commit("$HOME/project", "feat: add new feature")
print(result)  # Contains commit hash
```

---

### git_add

Add file contents to the staging area.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `files` | string[] | Yes | List of file paths (relative to repo) to stage |

**Returns:** Add result message.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Stage specific files
git.add("$HOME/project", ["src/main.py", "README.md"])

# Stage all Python files (list them first)
git.add("$HOME/project", ["*.py"])  # Depends on shell expansion
```

---

### git_reset

Unstage all staged changes (soft reset).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |

**Returns:** Reset result message.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Unstage all changes
result = git.reset("$HOME/project")
print(result)
```

---

### git_log

Show the commit history.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `max_count` | int | No | Maximum number of commits to show (default: 10) |

**Returns:** Commit log with hash, author, date, and message for each commit.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Get last 10 commits (default)
log = git.log("$HOME/project")
print(log)

# Get last 50 commits
log = git.log("$HOME/project", max_count=50)
```

---

### git_create_branch

Create a new branch, optionally from a specific base branch.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `branch_name` | string | Yes | Name for the new branch |
| `base_branch` | string | No | Optional base branch to create from (default: current HEAD) |

**Returns:** Branch creation result message.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Create branch from current HEAD
git.create_branch("$HOME/project", "feature/new-feature")

# Create branch from main
git.create_branch("$HOME/project", "fix/bug-123", base_branch="main")
```

---

### git_checkout

Switch to a different branch.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `branch_name` | string | Yes | Name of the branch to switch to |

**Returns:** Checkout result message.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Switch to main branch
git.checkout("$HOME/project", "main")

# Switch to feature branch
git.checkout("$HOME/project", "feature/new-feature")
```

---

### git_show

Show the contents of a specific commit.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |
| `revision` | string | Yes | Commit hash, branch, or ref to show |

**Returns:** Commit details including diff.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# Show latest commit
details = git.show("$HOME/project", "HEAD")
print(details)

# Show specific commit
details = git.show("$HOME/project", "abc1234")
```

---

### git_branch

List all Git branches in the repository.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_path` | string | Yes | Absolute path to the git repository |

**Returns:** List of branch names.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

registry = get_registry()
git = GitServer(registry)

# List all branches
branches = git.branches("$HOME/project")
for branch in branches:
    print(branch)
```

## Python Wrapper Usage

The `GitServer` wrapper provides a typed Python interface for all git operations.

```python
from core.mcp import get_registry
from core.mcp.servers import GitServer

# Get the MCP registry and create wrapper
registry = get_registry()
git = GitServer(registry)

repo = "$HOME/project"

# Check status
status = git.status(repo)
print(status)

# Stage changes
git.add(repo, ["src/main.py", "tests/test_main.py"])

# Check what's staged
staged = git.diff_staged(repo)
print(staged)

# Commit
result = git.commit(repo, "feat: implement new feature")
print(result)

# View commit history
log = git.log(repo, max_count=5)
print(log)
```

## Common Patterns

### Status Check Workflow

```python
# Check repository state before making changes
status = git.status(repo)
print("Current status:")
print(status)

# Check for uncommitted changes
unstaged = git.diff_unstaged(repo)
staged = git.diff_staged(repo)

if unstaged or staged:
    print("Warning: Repository has uncommitted changes")
```

### Complete Commit Workflow

```python
# 1. Check status
status = git.status(repo)

# 2. Stage specific files
git.add(repo, ["src/feature.py", "tests/test_feature.py"])

# 3. Review staged changes
staged_diff = git.diff_staged(repo)
print("Changes to be committed:")
print(staged_diff)

# 4. Commit
result = git.commit(repo, "feat: add new feature with tests")
print(f"Committed: {result}")
```

### Branch Management

```python
# List existing branches
branches = git.branches(repo)
print("Available branches:", branches)

# Create feature branch
git.create_branch(repo, "feature/my-feature", base_branch="main")

# Switch to feature branch
git.checkout(repo, "feature/my-feature")

# Do work, then switch back
git.checkout(repo, "main")
```

### Reviewing History

```python
# Get recent commits
log = git.log(repo, max_count=10)
print(log)

# Compare current branch to main
diff = git.diff(repo, "main")
print("Changes from main:")
print(diff)

# Show specific commit details
details = git.show(repo, "HEAD~1")
print("Previous commit:")
print(details)
```

## Troubleshooting

### "Not a git repository" Error

**Cause:** The specified path is not a valid git repository.

**Solution:**
1. Verify the path contains a `.git` directory
2. Use absolute paths, not relative
3. Ensure the repository was properly initialized

### "Nothing to commit" Error

**Cause:** No changes were staged before attempting to commit.

**Solution:**
1. Stage files using `git.add()` before committing
2. Check `git.diff_unstaged()` to see available changes
3. Verify files were modified within the repository

### "Branch already exists" Error

**Cause:** Attempting to create a branch with a name that already exists.

**Solution:**
1. Check existing branches with `git.branches()`
2. Use a different branch name
3. Delete the existing branch first if needed

### "Uncommitted changes" on Checkout

**Cause:** Cannot switch branches with uncommitted changes that would be overwritten.

**Solution:**
1. Commit current changes first
2. Stash changes (not available via MCP, use direct git)
3. Discard changes with `git.reset()` (loses changes)

## See Also

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
- [Filesystem Server](./filesystem.md)
- [Memory Server](./memory.md)
