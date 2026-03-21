# Context7 MCP Server

| Property | Value |
|----------|-------|
| **Package** | `@anthropic/mcp-server-context7` |
| **Category** | Developer |
| **Transport** | HTTP/SSE |
| **Default** | Disabled |
| **Wrapper** | `core/mcp/servers/context7.py` |

## Overview

The Context7 MCP Server provides library documentation lookup, enabling agents to access up-to-date API references for programming libraries. This helps avoid stale knowledge by retrieving current documentation directly.

### Key Features

- **Library Resolution**: Match library names to Context7 documentation sources
- **Documentation Retrieval**: Get relevant docs for specific topics
- **Version-Aware**: Access documentation for specific library versions
- **Token-Limited**: Control response size for LLM context windows

### When to Use

- Getting current API syntax and examples
- Learning unfamiliar library features
- Avoiding outdated documentation in training data
- Looking up function signatures and parameters
- Understanding library best practices

## Configuration

Configuration in `config/mcp_servers.yaml`:

```yaml
context7:
  enabled: false  # Set to true to enable
  command:
    - npx
    - -y
    - '@anthropic/mcp-server-context7'
  description: Library documentation lookup for up-to-date API references
  auto_restart: true
  max_restarts: 3
  timeout: 30.0
```

### No Credentials Required

Context7 provides a free tier that works without authentication. For higher rate limits, an optional API key can be configured.

### Optional API Key Configuration

For production use with higher rate limits:

```python
from core.mcp.servers.context7 import Context7Server

config = Context7Server.get_config(
    api_key="your_context7_api_key"  # Optional
)
```

## Tool Reference

Context7 provides two tools that work together in a two-step lookup pattern.

### resolve-library-id

Match a common library name to a Context7 compatible library ID.

**Always call this first** before `get-library-docs`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `libraryName` | string | Yes | Common library name (e.g., "react", "fastapi", "lodash") |

**Returns**: LibraryInfo object with Context7 compatible ID

```python
lib = await ctx7.resolve_library("react")
print(f"Library ID: {lib.library_id}")  # e.g., "/react/18.2.0"
print(f"Name: {lib.name}")
print(f"Version: {lib.version}")
```

### get-library-docs

Retrieve documentation for a specific topic.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context7CompatibleLibraryID` | string | Yes | Library ID from resolve-library-id |
| `topic` | string | Yes | Documentation topic to search |
| `tokens` | integer | No | Maximum tokens to return (default: 5000) |

**Returns**: Array of documentation chunks

```python
docs = await ctx7.get_library_docs(
    library_id="/react/18.2.0",
    topic="useEffect cleanup function",
    tokens=2000
)

for chunk in docs:
    print(f"Source: {chunk.source}")
    print(f"Content: {chunk.content[:200]}...")
```

## Two-Step Lookup Pattern

Context7 uses a two-step pattern for accurate documentation retrieval:

### Step 1: Resolve Library

Convert common library name to Context7 ID:

```python
from core.mcp.servers import Context7Server

ctx7 = Context7Server(registry)

# Resolve the library first
lib = await ctx7.resolve_library("react")
if not lib:
    print("Library not found")
    return
```

### Step 2: Get Documentation

Use the resolved ID to fetch docs:

```python
# Then get documentation for a specific topic
docs = await ctx7.get_library_docs(
    library_id=lib.library_id,
    topic="useState hook",
    tokens=3000
)

for chunk in docs:
    print(chunk.content)
```

### Convenience Method

The wrapper provides a combined method:

```python
# Single call that does both steps
docs = await ctx7.query_docs(
    library_name="fastapi",
    query="dependency injection",
    tokens=5000
)
```

## Python Wrapper Usage

The `Context7Server` wrapper provides a typed Python interface:

```python
from core.mcp import get_registry
from core.mcp.servers import Context7Server

# Get registry and create server wrapper
registry = get_registry()
ctx7 = Context7Server(registry)

# Example: Look up React hooks documentation
lib = await ctx7.resolve_library("react")
if lib:
    docs = await ctx7.get_library_docs(
        lib.library_id,
        "useCallback vs useMemo",
        tokens=4000
    )
    for chunk in docs:
        print(f"## {chunk.source}\n{chunk.content}\n")
```

### Data Types

```python
@dataclass
class LibraryInfo:
    library_id: str        # Context7 compatible ID
    name: str              # Library name
    version: str           # Version string
    description: str | None

@dataclass
class DocChunk:
    content: str           # Documentation text
    source: str            # Source URL or reference
    relevance: float       # Relevance score (0-1)
```

## Supported Libraries

Context7 supports documentation for many popular libraries including:

### JavaScript/TypeScript
- React, Vue, Angular, Svelte
- Next.js, Nuxt, Remix
- Express, Fastify, Hono
- Lodash, Ramda, date-fns

### Python
- FastAPI, Flask, Django
- SQLAlchemy, Pydantic
- Pandas, NumPy, PyTorch
- Requests, httpx, aiohttp

### Go
- Gin, Echo, Fiber
- GORM, sqlx
- Cobra, Viper

### Rust
- Tokio, Axum, Actix
- Serde, Diesel
- Clap, Tracing

> **Note**: Library availability may vary. Use `resolve-library-id` to check if a library is supported.

## Common Use Cases

### Learning New APIs

```python
# Get started with a new library
docs = await ctx7.query_docs("fastapi", "getting started quickstart")
```

### Looking Up Specific Functions

```python
# Find function signature and usage
docs = await ctx7.query_docs("lodash", "debounce function parameters")
```

### Understanding Patterns

```python
# Learn best practices
docs = await ctx7.query_docs("react", "error boundary implementation")
```

### Checking Migration Guides

```python
# Version migration help
docs = await ctx7.query_docs("vue", "vue 2 to vue 3 migration guide")
```

## Error Handling

```python
# Handle library not found
lib = await ctx7.resolve_library("obscure-library")
if lib is None:
    print("Library not available in Context7")
    # Fallback to other documentation sources

# Handle empty results
docs = await ctx7.get_library_docs(lib.library_id, "very specific topic")
if not docs:
    # Try broader search
    docs = await ctx7.get_library_docs(lib.library_id, "general topic")
```

## Token Management

Control response size for LLM context windows:

```python
# Small context - quick answers
docs = await ctx7.get_library_docs(lib_id, topic, tokens=1000)

# Medium context - detailed explanations
docs = await ctx7.get_library_docs(lib_id, topic, tokens=5000)

# Large context - comprehensive coverage
docs = await ctx7.get_library_docs(lib_id, topic, tokens=10000)
```

**Recommendations:**

| Use Case | Token Limit |
|----------|-------------|
| Function signature lookup | 1000-2000 |
| API reference | 3000-5000 |
| Tutorial/guide content | 5000-8000 |
| Comprehensive overview | 8000-15000 |

## Troubleshooting

### Common Errors

#### "Library not found"

**Cause**: Library name doesn't match Context7's index.

**Solution**:
1. Try alternative names (e.g., "reactjs" vs "react")
2. Check for typos
3. Verify library is popular enough to be indexed

#### "Empty results"

**Cause**: Topic too specific or library docs limited.

**Solution**:
1. Broaden the search topic
2. Try different keywords
3. Use more general terms

#### "Rate limited"

**Cause**: Too many requests without API key.

**Solution**:
1. Add delay between requests
2. Configure API key for higher limits
3. Cache frequently accessed docs

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("core.mcp.servers.context7").setLevel(logging.DEBUG)
```

## Performance Tips

1. **Cache resolve results** - Library IDs don't change frequently
2. **Request only needed tokens** - Smaller responses are faster
3. **Batch related queries** - Group lookups for same library
4. **Use specific topics** - Better results than broad queries

## Comparison with Static Documentation

| Feature | Context7 | Static Docs |
|---------|----------|-------------|
| Freshness | Always current | May be stale |
| Availability | Requires network | Works offline |
| Coverage | Popular libraries | Any docs |
| Format | Optimized for LLMs | Varies |

## Related Documentation

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
