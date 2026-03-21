# Filesystem MCP Server

| Field | Value |
|-------|-------|
| **Package** | `@modelcontextprotocol/server-filesystem` |
| **Category** | Core |
| **Default** | Enabled |
| **Transport** | STDIO |

## Overview

The Filesystem MCP Server provides secure file operations with directory access control. It enables agents to read, write, edit, and manage files within explicitly allowed directories.

**Key Features:**
- Configurable allowed directories restrict access scope
- Support for text and binary file operations
- Batch operations for reading multiple files
- Directory tree exploration and search capabilities

**When to Use:**
- Reading configuration files or source code
- Writing output files or logs
- Searching for files by pattern
- Exploring directory structures

## Configuration

```yaml
filesystem:
  enabled: true
  command:
    - npx
    - -y
    - '@modelcontextprotocol/server-filesystem'
    - $HOME
    - $HOME/Desktop
    - /tmp
  description: Secure file operations with directory access control
  auto_restart: true
  max_restarts: 3
```

**Configuration Notes:**
- The last arguments in the command array are the allowed directories
- The server cannot access paths outside these allowed directories
- Add additional directories by appending them to the command array
- All paths must be absolute

## Environment Variables

None required. The filesystem server does not need credentials.

## Tool Reference

### read_file (DEPRECATED)

Read file contents. **Deprecated:** Use `read_text_file` instead.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the file to read |

**Returns:** File contents as a string.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Deprecated - use read_text_file instead
content = fs.read_file("/tmp/example.txt")
```

---

### read_text_file

Read file contents as text with encoding support.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the file to read |
| `encoding` | string | No | Character encoding (default: "utf-8") |

**Returns:** File contents as a string.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Read with default UTF-8 encoding
content = fs.read_text_file("/tmp/example.txt")

# Read with specific encoding
content = fs.read_text_file("/tmp/latin1_file.txt", encoding="latin-1")
```

---

### read_media_file

Read image or audio files as binary data. Returns base64-encoded content.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the media file |

**Returns:** File contents as bytes (base64 decoded).

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Read image file
image_bytes = fs.read_media_file("/tmp/image.png")

# Save to new location
with open("/tmp/copy.png", "wb") as f:
    f.write(image_bytes)
```

---

### read_multiple_files

Read multiple files simultaneously for batch operations.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `paths` | string[] | Yes | List of absolute paths to files |

**Returns:** Dict mapping file paths to their contents.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Read multiple config files
contents = fs.read_multiple_files([
    "/tmp/config.yaml",
    "/tmp/settings.json",
    "/tmp/README.md"
])

for path, content in contents.items():
    print(f"{path}: {len(content)} bytes")
```

---

### write_file

Create or overwrite a file with the specified content.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the file to write |
| `content` | string | Yes | Content to write to the file |

**Returns:** None (void operation).

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Write a new file
fs.write_file("/tmp/output.txt", "Hello, World!")

# Overwrite existing file
fs.write_file("/tmp/config.json", '{"key": "value"}')
```

---

### edit_file

Make line-based text edits using search and replace.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the file to edit |
| `edits` | object[] | Yes | List of edits with `oldText` and `newText` keys |

**Returns:** Result message from the server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Single replacement
fs.edit_file("/tmp/example.txt", [
    {"oldText": "old content", "newText": "new content"}
])

# Multiple replacements
fs.edit_file("/tmp/config.py", [
    {"oldText": "DEBUG = True", "newText": "DEBUG = False"},
    {"oldText": "PORT = 8000", "newText": "PORT = 8080"}
])
```

---

### create_directory

Create a directory, including nested directories.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the directory to create |

**Returns:** None (void operation).

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Create single directory
fs.create_directory("/tmp/new_dir")

# Create nested directories
fs.create_directory("/tmp/project/src/components")
```

---

### list_directory

List directory contents with [FILE]/[DIR] prefixes.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the directory |

**Returns:** List of entries like `"[FILE] name.txt"` or `"[DIR] subdir"`.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# List directory
entries = fs.list_directory("/tmp")
for entry in entries:
    print(entry)  # "[FILE] example.txt" or "[DIR] subdir"

# Filter files only
files = [e for e in entries if e.startswith("[FILE]")]
```

---

### list_directory_with_sizes

List directory contents with file sizes included.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the directory |

**Returns:** Formatted string with entries and their sizes.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Get directory listing with sizes
listing = fs.list_directory_with_sizes("/tmp")
print(listing)
```

---

### directory_tree

Get a recursive JSON tree view of a directory structure.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the directory |

**Returns:** Dict representing the directory tree structure.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer
import json

registry = get_registry()
fs = FilesystemServer(registry)

# Get directory tree
tree = fs.directory_tree("/tmp/project")
print(json.dumps(tree, indent=2))
```

---

### move_file

Move or rename a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source` | string | Yes | Absolute path to the source file |
| `destination` | string | Yes | Absolute path to the destination |

**Returns:** None (void operation).

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Rename a file
fs.move_file("/tmp/old_name.txt", "/tmp/new_name.txt")

# Move to different directory
fs.move_file("/tmp/file.txt", "/tmp/archive/file.txt")
```

---

### search_files

Search for files matching glob patterns.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the directory to search in |
| `pattern` | string | Yes | Glob pattern to match files against |

**Returns:** List of matching file paths.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Find all Python files
py_files = fs.search_files("/tmp/project", "*.py")

# Find files in nested directories
all_configs = fs.search_files("/tmp", "**/config.*")

# Find specific file patterns
logs = fs.search_files("/tmp", "*.log")
```

---

### get_file_info

Get detailed file metadata including size, timestamps, and permissions.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the file |

**Returns:** Dict with file metadata (size, mtime, ctime, etc.).

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Get file metadata
info = fs.get_file_info("/tmp/example.txt")
print(f"Size: {info.get('size')} bytes")
print(f"Modified: {info.get('mtime')}")
```

---

### list_allowed_directories

List the directories that the server is allowed to access.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | No parameters |

**Returns:** List of directory paths that the server can access.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

registry = get_registry()
fs = FilesystemServer(registry)

# Check allowed directories
allowed = fs.list_allowed_directories()
for dir_path in allowed:
    print(f"Allowed: {dir_path}")
```

## Python Wrapper Usage

The `FilesystemServer` wrapper provides a typed Python interface for all filesystem operations.

```python
from core.mcp import get_registry
from core.mcp.servers import FilesystemServer

# Get the MCP registry and create wrapper
registry = get_registry()
fs = FilesystemServer(registry)

# Read file
content = fs.read_text_file("/tmp/example.txt")

# List directory
entries = fs.list_directory("/tmp")
for entry in entries:
    print(entry)  # "[FILE] example.txt" or "[DIR] subdir"

# Edit file with search/replace
fs.edit_file("/tmp/example.txt", [
    {"oldText": "foo", "newText": "bar"}
])

# Write new file
fs.write_file("/tmp/output.txt", "Generated content")

# Search for files
matches = fs.search_files("/tmp/project", "*.py")
```

## Common Patterns

### Reading Configuration Files

```python
import json
import yaml

# Read JSON config
config_json = fs.read_text_file("$HOME/project/config.json")
config = json.loads(config_json)

# Read YAML config
config_yaml = fs.read_text_file("$HOME/project/config.yaml")
config = yaml.safe_load(config_yaml)
```

### Writing Log Files

```python
import datetime

# Append to log file (read, modify, write)
log_path = "/tmp/app.log"
try:
    existing = fs.read_text_file(log_path)
except:
    existing = ""

timestamp = datetime.datetime.now().isoformat()
new_log = f"{existing}{timestamp}: Event occurred\n"
fs.write_file(log_path, new_log)
```

### Batch File Operations

```python
# Read all Python files in a project
py_files = fs.search_files("$HOME/project", "*.py")
contents = fs.read_multiple_files(py_files)

for path, content in contents.items():
    print(f"{path}: {len(content.splitlines())} lines")
```

### Directory Tree Exploration

```python
import json

# Explore project structure
tree = fs.directory_tree("$HOME/project")
print(json.dumps(tree, indent=2))

# List with sizes for disk usage analysis
sizes = fs.list_directory_with_sizes("$HOME/project")
print(sizes)
```

## Troubleshooting

### "Path not allowed" Error

**Cause:** The requested path is outside the allowed directories.

**Solution:**
1. Check configured allowed directories: `fs.list_allowed_directories()`
2. Add the required directory to the command array in `mcp_servers.yaml`
3. Restart the MCP server

### "File not found" Error

**Cause:** The file does not exist at the specified path.

**Solution:**
1. Verify the path is absolute (starts with `/`)
2. Check if the file exists using `list_directory()` on the parent
3. Ensure correct file name and extension

### "Permission denied" Error

**Cause:** The operating system denied access to the file.

**Solution:**
1. Check file system permissions (`ls -la` on the file)
2. Ensure the Dryade process user has read/write access
3. Check if the file is locked by another process

### Server Restart Issues

**Cause:** The filesystem server process crashed.

**Solution:**
1. Check `auto_restart: true` in configuration
2. Review `max_restarts: 3` limit
3. Check Dryade logs for crash details
4. Manually restart via registry: `registry.restart_server("filesystem")`

## See Also

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
- [Git Server](./git.md)
- [Memory Server](./memory.md)
