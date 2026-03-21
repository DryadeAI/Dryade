# Memory MCP Server

| Field | Value |
|-------|-------|
| **Package** | `@modelcontextprotocol/server-memory` |
| **Category** | Core |
| **Default** | Enabled |
| **Transport** | STDIO |

## Overview

The Memory MCP Server provides a knowledge graph for persistent agent memory. It enables agents to store, retrieve, and query information as entities with relationships and observations.

**Key Features:**
- Entity-based knowledge storage with types and observations
- Directed relationships between entities
- Graph-based queries and search
- Persistent memory across agent sessions

**When to Use:**
- Storing context that agents need to remember across sessions
- Building knowledge bases about users, projects, or systems
- Tracking relationships between concepts
- Accumulating observations over time

## Configuration

```yaml
memory:
  enabled: true
  command:
    - npx
    - -y
    - '@modelcontextprotocol/server-memory'
  description: Knowledge graph operations for persistent agent memory
  auto_restart: true
  max_restarts: 3
```

**Configuration Notes:**
- No additional configuration required
- Memory persists in the server's internal storage
- Restart clears memory (consider external persistence for production)

## Environment Variables

None required. The memory server stores data in-memory.

## Knowledge Graph Concepts

### Entity

An entity is a node in the knowledge graph representing a named concept.

```python
{
    "name": "ProjectDryade",       # Unique identifier
    "entityType": "project",       # Category/type
    "observations": [              # List of facts
        "Python project",
        "Uses LLM agents",
        "Started in 2024"
    ]
}
```

### Relation

A relation is a directed edge between two entities.

```python
{
    "from": "Alice",               # Source entity name
    "to": "ProjectDryade",         # Target entity name
    "relationType": "works_on"     # Relationship type (active voice)
}
```

### Observation

An observation is a text fact attached to an entity. Observations are strings that describe attributes, events, or properties of the entity.

## Tool Reference

### create_entities

Create multiple new entities in the knowledge graph.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entities` | object[] | Yes | List of entity objects with `name`, `entityType`, and `observations` |

**Entity Object:**
| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique name for the entity |
| `entityType` | string | Type/category of the entity |
| `observations` | string[] | List of facts about the entity |

**Returns:** Confirmation message from server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer, Entity

registry = get_registry()
memory = MemoryServer(registry)

# Using Entity class
memory.create_entities([
    Entity("Alice", "person", ["Software engineer", "Works on Dryade"]),
    Entity("Bob", "person", ["Designer", "Remote worker"])
])

# Using dict format
memory.create_entities([
    {"name": "ProjectDryade", "entityType": "project", "observations": ["Python project"]}
])
```

---

### create_relations

Create directed relationships between entities.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relations` | object[] | Yes | List of relation objects with `from`, `to`, and `relationType` |

**Relation Object:**
| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Source entity name |
| `to` | string | Target entity name |
| `relationType` | string | Type of relationship (use active voice) |

**Returns:** Confirmation message from server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer, Relation

registry = get_registry()
memory = MemoryServer(registry)

# Using Relation class
memory.create_relations([
    Relation("Alice", "ProjectDryade", "works_on"),
    Relation("Bob", "Alice", "collaborates_with")
])

# Using dict format
memory.create_relations([
    {"from": "ProjectDryade", "to": "Python", "relationType": "uses"}
])
```

---

### add_observations

Add new observations (facts) to existing entities.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `observations` | object[] | Yes | List of objects with `entityName` and `contents` |

**Observation Object:**
| Field | Type | Description |
|-------|------|-------------|
| `entityName` | string | Name of the entity to update |
| `contents` | string[] | List of new observations to add |

**Returns:** Confirmation message from server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Add observations to existing entities
memory.add_observations([
    {"entityName": "Alice", "contents": ["Joined team in 2024", "Expert in LLMs"]},
    {"entityName": "ProjectDryade", "contents": ["Version 0.2 in development"]}
])
```

---

### delete_entities

Delete entities and their associated relations from the graph.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `entityNames` | string[] | Yes | Names of entities to delete |

**Returns:** Confirmation message from server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Delete entities (also removes their relations)
memory.delete_entities(["OldProject", "FormerEmployee"])
```

---

### delete_observations

Delete specific observations from entities.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `deletions` | object[] | Yes | List of objects with `entityName` and `observations` to delete |

**Deletion Object:**
| Field | Type | Description |
|-------|------|-------------|
| `entityName` | string | Name of the entity |
| `observations` | string[] | Exact observation strings to remove |

**Returns:** Confirmation message from server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Remove outdated observations
memory.delete_observations([
    {"entityName": "Alice", "observations": ["Outdated fact", "Wrong information"]}
])
```

---

### delete_relations

Delete specific relations between entities.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `relations` | object[] | Yes | List of relation objects to delete |

**Returns:** Confirmation message from server.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer, Relation

registry = get_registry()
memory = MemoryServer(registry)

# Delete specific relations
memory.delete_relations([
    Relation("Alice", "OldProject", "worked_on"),
    {"from": "Bob", "to": "Alice", "relationType": "managed"}
])
```

---

### read_graph

Read the entire knowledge graph with all entities and relations.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | No parameters |

**Returns:** Dict with `entities` and `relations` arrays.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Read the entire graph
graph = memory.read_graph()
print(f"Entities: {len(graph['entities'])}")
print(f"Relations: {len(graph['relations'])}")

# Iterate entities
for entity in graph['entities']:
    print(f"- {entity['name']} ({entity['entityType']})")
```

---

### search_nodes

Search for entities based on a query string.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query (searches names and observations) |

**Returns:** List of matching entity dicts.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Search for entities
results = memory.search_nodes("Python")
for entity in results:
    print(f"Found: {entity['name']}")

# Search by observation content
results = memory.search_nodes("engineer")
```

---

### open_nodes

Retrieve specific entities by their exact names.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `names` | string[] | Yes | List of entity names to retrieve |

**Returns:** List of entity dicts with full details.

**Example:**
```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer

registry = get_registry()
memory = MemoryServer(registry)

# Get specific entities
entities = memory.open_nodes(["Alice", "ProjectDryade"])
for entity in entities:
    print(f"{entity['name']}: {entity['observations']}")
```

## Python Wrapper Usage

The `MemoryServer` wrapper provides a typed Python interface with helper classes.

```python
from core.mcp import get_registry
from core.mcp.servers import MemoryServer, Entity, Relation

# Get the MCP registry and create wrapper
registry = get_registry()
memory = MemoryServer(registry)

# Create entities
memory.create_entities([
    Entity("Alice", "person", ["Software engineer"]),
    Entity("ProjectDryade", "project", ["Python project", "Uses LLM agents"])
])

# Create relations
memory.create_relations([
    Relation("Alice", "ProjectDryade", "works_on")
])

# Add observations
memory.add_observations([
    {"entityName": "Alice", "contents": ["Expert in Python"]}
])

# Read the graph
graph = memory.read_graph()
print(f"Graph has {len(graph['entities'])} entities")

# Search
results = memory.search_nodes("Python")
print(f"Found {len(results)} matching entities")
```

## Common Patterns

### Building User Profiles

```python
# Create user entity
memory.create_entities([
    Entity("user_john", "user", [
        "Name: John Smith",
        "Email: john@example.com",
        "Preference: Dark mode",
        "Language: English"
    ])
])

# Add preferences over time
memory.add_observations([
    {"entityName": "user_john", "contents": [
        "Last active: 2024-01-15",
        "Favorite feature: Workflows"
    ]}
])
```

### Project Knowledge Base

```python
# Create project structure
memory.create_entities([
    Entity("Dryade", "project", ["AI agent platform", "Python-based"]),
    Entity("MCPRegistry", "component", ["Manages MCP servers", "Singleton pattern"]),
    Entity("WorkflowExecutor", "component", ["Executes workflows", "Async"]),
])

# Create relationships
memory.create_relations([
    Relation("Dryade", "MCPRegistry", "contains"),
    Relation("Dryade", "WorkflowExecutor", "contains"),
    Relation("WorkflowExecutor", "MCPRegistry", "depends_on"),
])

# Query relationships
related = memory.search_nodes("component")
```

### Session Context Persistence

```python
# Store conversation context
memory.create_entities([
    Entity(f"session_{session_id}", "conversation", [
        f"Started: {datetime.now().isoformat()}",
        "Topic: Database optimization",
        "User asked about indexing"
    ])
])

# Link to user
memory.create_relations([
    Relation(f"session_{session_id}", "user_john", "belongs_to")
])

# Later: retrieve context
sessions = memory.search_nodes("conversation")
context = memory.open_nodes([f"session_{session_id}"])
```

### Incremental Knowledge Accumulation

```python
# Check if entity exists
results = memory.search_nodes("CompanyAcme")

if not results:
    # Create new entity
    memory.create_entities([
        Entity("CompanyAcme", "organization", ["First contact: 2024-01-01"])
    ])
else:
    # Add to existing
    memory.add_observations([
        {"entityName": "CompanyAcme", "contents": ["Meeting on 2024-01-15"]}
    ])
```

## Use Cases

### Agent Memory

Agents can use the memory server to remember context across conversations:
- User preferences and settings
- Previous interactions and decisions
- Learned patterns and corrections

### Context Persistence

Store and retrieve context for long-running operations:
- Workflow state and progress
- Multi-step task tracking
- Cross-session continuity

### Knowledge Accumulation

Build domain knowledge over time:
- Document insights and summaries
- Project architecture understanding
- Team and organizational structure

## Troubleshooting

### "Entity not found" Error

**Cause:** Attempting to add observations or relations to non-existent entities.

**Solution:**
1. Create the entity first using `create_entities()`
2. Check entity name spelling (case-sensitive)
3. Use `search_nodes()` to verify entity exists

### Graph Growing Too Large

**Cause:** Accumulating too many entities and observations.

**Solution:**
1. Periodically clean up old entities with `delete_entities()`
2. Remove outdated observations with `delete_observations()`
3. Implement rotation policies for session-based entities

### Memory Loss on Restart

**Cause:** The memory server stores data in-memory only.

**Solution:**
1. Export graph before shutdown: `graph = memory.read_graph()`
2. Store JSON to file system
3. Restore on startup by recreating entities
4. Consider external graph database for production

### Duplicate Entities

**Cause:** Creating entities with the same name creates duplicates.

**Solution:**
1. Search before creating: `memory.search_nodes(name)`
2. Use consistent naming conventions
3. Add observations to existing entities instead of recreating

## See Also

- [MCP Overview](../README.md)
- [MCP Architecture](../ARCHITECTURE.md)
- [Tool Inventory](../INVENTORY.md)
- [Filesystem Server](./filesystem.md)
- [Git Server](./git.md)
