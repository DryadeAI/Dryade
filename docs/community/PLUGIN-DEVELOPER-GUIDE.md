# Dryade Plugin Developer Guide

This comprehensive guide covers everything you need to know to build plugins for Dryade Community Edition.

## Table of Contents

1. [Introduction](#1-introduction)
2. [Getting Started](#2-getting-started)
3. [Plugin Structure](#3-plugin-structure)
4. [Manifest (dryade.json)](#4-manifest-dryadejson)
5. [Backend Development](#5-backend-development)
6. [Frontend Development (UI Plugins)](#6-frontend-development-ui-plugins)
7. [Testing](#7-testing)
8. [Validation](#8-validation)
9. [Distribution](#9-distribution)
10. [Best Practices](#10-best-practices)
11. [Troubleshooting](#11-troubleshooting)
12. [Examples](#12-examples)

---

## 1. Introduction

### What are Dryade Plugins?

Dryade plugins extend the platform's capabilities by adding new features, integrations, and workflows. Plugins can:

- Add new API endpoints to the backend
- Provide custom UI pages accessible from the sidebar
- Integrate with external services and tools
- Add new agent capabilities and skills
- Process and transform data

### When to Create a Plugin vs Use Existing Features

**Create a plugin when you need to:**
- Add a new page or significant UI component
- Create custom API endpoints for new functionality
- Integrate with an external service that doesn't have MCP support
- Bundle multiple related features together

**Use existing features instead when:**
- You only need to call existing APIs (use the workflow builder)
- You need simple data processing (use a skill or prompt template)
- You want to add a tool for agents (create an MCP server)

### Plugin vs Agent vs Skill Comparison

| Component | Purpose | Has UI | Persistent State | Example |
|-----------|---------|--------|------------------|---------|
| **Plugin** | Extend platform functionality | Optional | Yes (database) | Cost tracker, KPI monitor |
| **Agent** | Autonomous task execution | No | Per-session | Code reviewer, data analyst |
| **Skill** | Reusable prompt template | No | No | create-plugin, audit-code |
| **MCP Server** | Tool provider for agents | No | External | GitHub API, filesystem |

---

## 2. Getting Started

### Prerequisites

Before creating a plugin, ensure you have:

- Python 3.10 or higher
- Node.js 18+ (for UI plugins)
- A running Dryade instance
- Basic knowledge of FastAPI (backend) and React (frontend)

### Create Using Scaffold (Recommended)

The fastest way to create a new plugin:

```bash
# Create a plugin with CLI
dryade create-plugin my-plugin

# Or with options
dryade create-plugin my-plugin --with-ui --author "Your Name"
```

This creates a complete plugin skeleton with:
- Proper directory structure
- Pre-configured dryade.json manifest
- Backend plugin.py with lifecycle hooks
- UI scaffold (if --with-ui specified)
- Test files

### Create Manually

If you prefer to create plugins manually:

```bash
mkdir -p plugins/my_plugin
touch plugins/my_plugin/__init__.py
touch plugins/my_plugin/plugin.py
touch plugins/my_plugin/dryade.json
```

### Template Repository

For a complete reference implementation, clone the plugin template:

```bash
git clone https://github.com/dryade/plugin-template.git plugins/my_plugin
cd plugins/my_plugin
./setup.sh
```

---

## 3. Plugin Structure

Every plugin follows this directory structure:

```
plugins/my_plugin/
+-- dryade.json          # Manifest (required)
+-- __init__.py          # Python package marker (required)
+-- plugin.py            # Entry point with PluginProtocol (required)
+-- routes.py            # FastAPI routes (optional)
+-- schemas.py           # Pydantic models (optional)
+-- config.py            # Configuration management (optional)
+-- tests/               # Test directory (recommended)
|   +-- __init__.py
|   +-- test_plugin.py
|   +-- conftest.py
+-- ui/                  # Frontend (if has_ui: true)
    +-- package.json
    +-- vite.config.ts
    +-- src/
    |   +-- App.tsx
    |   +-- index.tsx
    |   +-- bridge/
    |       +-- DryadeBridge.ts
    +-- dist/
        +-- bundle.js
```

### File Descriptions

| File | Purpose | Required |
|------|---------|----------|
| `dryade.json` | Plugin metadata and configuration | Yes |
| `__init__.py` | Makes directory a Python package | Yes |
| `plugin.py` | Main plugin class with lifecycle hooks | Yes |
| `routes.py` | FastAPI router with API endpoints | No |
| `schemas.py` | Pydantic models for request/response validation | No |
| `config.py` | Plugin-specific configuration | No |
| `ui/` | React frontend application | No |

---

## 4. Manifest (dryade.json)

The manifest file declares plugin metadata, capabilities, and UI configuration.

### Required Fields

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "A brief description of what your plugin does",
  "author": "Your Name",
  "manifest_version": "1.0",
  "has_ui": false,
  "plugin_dependencies": [],
  "core_version_constraint": ">=2.0.0,<3.0.0"
}
```

### Optional Fields

```json
{
  "api_paths": ["/api/my_plugin"],
  "slots": ["sidebar", "dashboard-widget"],
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {"type": "string"},
      "refresh_interval": {"type": "integer", "default": 60}
    }
  }
}
```

### UI Configuration (when has_ui: true)

```json
{
  "has_ui": true,
  "ui": {
    "entry": "ui/dist/bundle.js",
    "max_bundle_size_kb": 500,
    "permissions": ["read_config", "api_proxy"],
    "routes": [
      {
        "path": "/workspace/plugins/my_plugin",
        "title": "My Plugin"
      }
    ],
    "sidebar_item": {
      "icon": "settings",
      "label": "My Plugin",
      "parent": "plugins"
    }
  }
}
```

### Complete Example

```json
{
  "name": "weather_dashboard",
  "version": "1.2.0",
  "description": "Display weather forecasts and alerts in your dashboard",
  "author": "Weather Team",
  "manifest_version": "1.0",
  "has_ui": true,
  "plugin_dependencies": [],
  "core_version_constraint": ">=2.0.0,<3.0.0",
  "api_paths": ["/api/weather"],
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {"type": "string", "description": "OpenWeatherMap API key"},
      "units": {"type": "string", "enum": ["metric", "imperial"], "default": "metric"},
      "locations": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["api_key"]
  },
  "ui": {
    "entry": "ui/dist/bundle.js",
    "max_bundle_size_kb": 300,
    "permissions": ["read_config", "write_config", "api_proxy"],
    "routes": [
      {
        "path": "/workspace/plugins/weather",
        "title": "Weather Dashboard"
      }
    ],
    "sidebar_item": {
      "icon": "cloud",
      "label": "Weather",
      "parent": "monitoring"
    }
  }
}
```

### Sidebar Parents

| Parent | Description |
|--------|-------------|
| `monitoring` | Monitoring & analytics section |
| `plugins` | General plugins section |
| `tools` | Developer tools section |
| `settings` | Settings area |

### Available Icons

Use Lucide icon names: `settings`, `file`, `folder`, `cloud`, `database`, `chart`, `users`, `shield`, `dollar-sign`, `activity`, etc.

---

## 5. Backend Development

### Plugin Entry Point (plugin.py)

Implement the `PluginProtocol` interface:

```python
"""Plugin entry point."""
from typing import Any
from fastapi import FastAPI


class MyPlugin:
    """My plugin implementation."""

    def __init__(self):
        self._initialized = False
        self._app = None

    async def on_load(self, app: FastAPI, context: dict[str, Any]) -> None:
        """Called when plugin is loaded.

        Args:
            app: The FastAPI application instance
            context: Plugin context with config, database session factory, etc.
        """
        self._app = app

        # Register routes
        from . import routes
        app.include_router(routes.router, prefix="/api/my_plugin", tags=["my_plugin"])

        self._initialized = True

    async def on_unload(self) -> None:
        """Called when plugin is unloaded. Clean up resources."""
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        """Return plugin health status."""
        return {
            "status": "healthy" if self._initialized else "not_initialized",
            "version": "1.0.0"
        }


# Plugin instance - required for discovery
plugin = MyPlugin()
```

### Lifecycle Hooks

| Hook | When Called | Purpose |
|------|-------------|---------|
| `on_load` | Plugin startup | Initialize resources, register routes |
| `on_unload` | Plugin shutdown | Clean up connections, save state |
| `health_check` | Health endpoint called | Report plugin status |

### Adding API Routes (routes.py)

```python
"""Plugin API routes."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from core.database import get_db

router = APIRouter()


class ItemCreate(BaseModel):
    """Request schema for creating an item."""
    name: str = Field(..., min_length=1, max_length=100)
    value: int = Field(..., ge=0)


class ItemResponse(BaseModel):
    """Response schema for item."""
    id: int
    name: str
    value: int


@router.get("/status")
async def get_status():
    """Get plugin status."""
    return {"status": "ok", "version": "1.0.0"}


@router.get("/items", response_model=list[ItemResponse])
async def list_items(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all items with pagination."""
    # Your implementation here
    return []


@router.post("/items", response_model=ItemResponse)
async def create_item(
    item: ItemCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Create a new item."""
    # Your implementation here
    # Use background_tasks for async processing
    return {"id": 1, "name": item.name, "value": item.value}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an item by ID."""
    # Your implementation here
    return {"deleted": True}
```

### Database Access

Plugins can use the shared database session:

```python
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MyPluginModel(Base):
    """Plugin database model."""
    __tablename__ = "my_plugin_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    value = Column(Integer, default=0)


async def get_items(db: AsyncSession):
    """Retrieve items from database."""
    result = await db.execute(select(MyPluginModel))
    return result.scalars().all()
```

### Accessing Other Services

Plugins can access core services through the context:

```python
async def on_load(self, app: FastAPI, context: dict[str, Any]) -> None:
    # Access configuration
    config = context.get("config", {})

    # Access the event bus for publishing events
    event_bus = context.get("event_bus")
    if event_bus:
        await event_bus.publish("my_plugin.loaded", {"version": "1.0.0"})
```

---

## 6. Frontend Development (UI Plugins)

### Setting Up the UI

Initialize a React project in the `ui/` directory:

```bash
cd plugins/my_plugin
mkdir ui && cd ui
npm init -y
npm install react react-dom
npm install -D typescript vite @vitejs/plugin-react @types/react @types/react-dom
```

### Vite Configuration (vite.config.ts)

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    lib: {
      entry: 'src/index.tsx',
      name: 'PluginUI',
      fileName: () => 'bundle.js',
      formats: ['iife'],
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {},
      },
    },
  },
});
```

### Entry Point (src/index.tsx)

```typescript
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
}

// Signal ready to host
declare global {
  interface Window {
    DryadeBridge?: { ready: () => void };
  }
}
window.DryadeBridge?.ready();
```

### DryadeBridge API (src/bridge/DryadeBridge.ts)

The DryadeBridge provides communication between your plugin and the host application:

```typescript
declare global {
  interface Window {
    DryadeBridge?: {
      pluginName: string;
      permissions: string[];
      currentTheme: 'light' | 'dark';
      postMessage: (type: string, data: unknown) => void;
      apiRequest: (requestId: string, method: string, path: string, body?: unknown) => void;
      ready: () => void;
    };
    onDryadeBridgeMessage?: (type: string, data: unknown) => void;
  }
}

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
};

const pendingRequests = new Map<string, PendingRequest>();
const REQUEST_TIMEOUT = 30000;

function generateRequestId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

// Handle responses from host
window.onDryadeBridgeMessage = (type: string, data: unknown) => {
  if (type === 'api_response') {
    const { requestId, success, data: responseData, error } = data as {
      requestId: string;
      success: boolean;
      data?: unknown;
      error?: string;
    };
    const pending = pendingRequests.get(requestId);
    if (pending) {
      clearTimeout(pending.timeout);
      pendingRequests.delete(requestId);
      if (success) {
        pending.resolve(responseData);
      } else {
        pending.reject(new Error(error || 'Request failed'));
      }
    }
  }
};

export async function apiRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    const requestId = generateRequestId();
    const timeout = setTimeout(() => {
      pendingRequests.delete(requestId);
      reject(new Error('Request timeout'));
    }, REQUEST_TIMEOUT);

    pendingRequests.set(requestId, {
      resolve: resolve as (value: unknown) => void,
      reject,
      timeout,
    });

    window.DryadeBridge?.apiRequest(requestId, method, path, body);
  });
}

// Plugin-specific API client
export const api = {
  getStatus: () => apiRequest<{status: string}>('GET', '/my_plugin/status'),
  getItems: () => apiRequest<Item[]>('GET', '/my_plugin/items'),
  createItem: (data: CreateItemRequest) => apiRequest<Item>('POST', '/my_plugin/items', data),
};
```

### Main Component (src/App.tsx)

```typescript
import { useState, useEffect } from 'react';
import { api } from './bridge/DryadeBridge';

interface Item {
  id: number;
  name: string;
  value: number;
}

export function App() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getItems();
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-destructive/10 text-destructive p-4 rounded-lg">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto text-foreground bg-background min-h-screen">
      <h1 className="text-2xl font-bold mb-6">My Plugin</h1>

      {items.length === 0 ? (
        <div className="text-center text-muted-foreground py-12">
          No items yet. Create your first item to get started.
        </div>
      ) : (
        <div className="space-y-4">
          {items.map(item => (
            <div key={item.id} className="p-4 bg-card rounded-lg border border-border">
              <h3 className="font-medium">{item.name}</h3>
              <p className="text-muted-foreground">Value: {item.value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

### Building the UI

```bash
cd ui
npm run build
```

This generates `ui/dist/bundle.js` which is loaded by the host application.

### Theming and Styling

Plugins inherit the host application's theme. Use CSS variables for consistent styling:

```css
/* Available CSS variables */
--background        /* Page background */
--foreground        /* Primary text */
--card              /* Card backgrounds */
--card-foreground   /* Card text */
--primary           /* Primary accent color */
--muted             /* Muted backgrounds */
--muted-foreground  /* Muted text */
--border            /* Border color */
--destructive       /* Error/danger color */
--success           /* Success color */
```

### Security Considerations

Plugins run in sandboxed iframes with these restrictions:
- No access to parent window DOM
- No direct network requests (use api_proxy)
- No localStorage access to main app
- No form submissions
- No popups

---

## 7. Testing

### Test Fixtures for Dryade Context

Create `tests/conftest.py`:

```python
"""Test fixtures for plugin testing."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_app():
    """Create a mock FastAPI application."""
    return FastAPI()


@pytest.fixture
def mock_context():
    """Create a mock plugin context."""
    return {
        "config": {},
        "event_bus": AsyncMock(),
        "db_session_factory": MagicMock(),
    }


@pytest.fixture
def test_client(mock_app):
    """Create a test client for the app."""
    from plugins.my_plugin import routes
    mock_app.include_router(routes.router, prefix="/api/my_plugin")
    return TestClient(mock_app)
```

### Unit Testing Plugins

Create `tests/test_plugin.py`:

```python
"""Unit tests for plugin."""
import pytest
from plugins.my_plugin.plugin import MyPlugin


class TestMyPlugin:
    """Tests for MyPlugin class."""

    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return MyPlugin()

    @pytest.mark.asyncio
    async def test_on_load(self, plugin, mock_app, mock_context):
        """Test plugin loads successfully."""
        await plugin.on_load(mock_app, mock_context)
        assert plugin._initialized is True

    @pytest.mark.asyncio
    async def test_on_unload(self, plugin, mock_app, mock_context):
        """Test plugin unloads successfully."""
        await plugin.on_load(mock_app, mock_context)
        await plugin.on_unload()
        assert plugin._initialized is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, plugin, mock_app, mock_context):
        """Test health check when initialized."""
        await plugin.on_load(mock_app, mock_context)
        health = await plugin.health_check()
        assert health["status"] == "healthy"
```

### Integration Testing

Test API routes with the test client:

```python
"""Integration tests for plugin routes."""

def test_get_status(test_client):
    """Test status endpoint."""
    response = test_client.get("/api/my_plugin/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_item(test_client):
    """Test item creation."""
    response = test_client.post(
        "/api/my_plugin/items",
        json={"name": "Test Item", "value": 42}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Test Item"
```

### Running Tests

```bash
# Run all plugin tests
pytest plugins/my_plugin/tests -v

# Run with coverage
pytest plugins/my_plugin/tests --cov=plugins.my_plugin --cov-report=term-missing
```

---

## 8. Validation

### Using dryade validate-plugin

Before deploying, validate your plugin:

```bash
# Validate manifest and structure
dryade validate-plugin plugins/my_plugin

# Verbose output
dryade validate-plugin plugins/my_plugin --verbose
```

### Common Validation Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Missing required field: name` | dryade.json incomplete | Add all required fields |
| `Invalid version format` | Version not semver | Use format like "1.0.0" |
| `Plugin entry not found` | Missing plugin.py | Create plugin.py with plugin instance |
| `UI bundle missing` | has_ui true but no bundle | Run `npm run build` in ui/ |
| `Bundle size exceeds limit` | Bundle too large | Optimize bundle, increase limit |

### Pre-commit Checks

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: validate-plugin
        name: Validate Dryade Plugin
        entry: dryade validate-plugin
        language: system
        files: ^plugins/.*/dryade\.json$
        pass_filenames: false
        args: [plugins/my_plugin]
```

---

## 9. Distribution

### Publishing to Community (Future Marketplace)

In the future, Dryade will support a plugin marketplace. For now, share plugins via GitHub.

### Sharing via GitHub

1. Create a public repository for your plugin
2. Include a README with installation instructions
3. Tag releases with semantic versioning

```bash
# Create release
git tag v1.0.0
git push origin v1.0.0
```

### Installation from GitHub

Users can install plugins from GitHub:

```bash
# Clone into plugins directory
git clone https://github.com/username/my-dryade-plugin.git plugins/my_plugin

# Restart Dryade to load the plugin
dryade restart
```

### Version Management

Follow semantic versioning (semver):

- MAJOR: Breaking changes (incompatible API changes)
- MINOR: New features (backwards compatible)
- PATCH: Bug fixes (backwards compatible)

---

## 10. Best Practices

### Error Handling

```python
from fastapi import HTTPException
from core.logging import get_logger

logger = get_logger(__name__)


@router.post("/items")
async def create_item(item: ItemCreate):
    try:
        result = await process_item(item)
        return result
    except ValidationError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except ExternalServiceError as e:
        logger.error(f"External service error: {e}")
        raise HTTPException(status_code=502, detail="External service unavailable")
    except Exception as e:
        logger.exception(f"Unexpected error creating item: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Logging

Use structured logging:

```python
from core.logging import get_logger

logger = get_logger(__name__)

# Use appropriate log levels
logger.debug("Detailed debug info", extra={"item_id": 123})
logger.info("Operation completed", extra={"count": 42})
logger.warning("Unusual condition", extra={"threshold": 100})
logger.error("Operation failed", extra={"error_code": "E001"})
```

### Configuration Management

Use environment variables and config files:

```python
"""Plugin configuration."""
from pydantic_settings import BaseSettings


class PluginSettings(BaseSettings):
    """Plugin settings from environment."""

    api_key: str = ""
    refresh_interval: int = 60
    max_items: int = 1000

    class Config:
        env_prefix = "MY_PLUGIN_"


settings = PluginSettings()
```

### Performance Considerations

- Use background tasks for long-running operations
- Implement caching for frequently accessed data
- Use pagination for large data sets
- Optimize database queries with indexes

```python
from fastapi import BackgroundTasks


@router.post("/process")
async def start_processing(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
):
    """Start async processing."""
    job_id = generate_job_id()
    background_tasks.add_task(process_in_background, job_id, request)
    return {"job_id": job_id, "status": "processing"}
```

---

## 11. Troubleshooting

### Plugin Not Loading

**Symptoms:** Plugin doesn't appear in the UI or API endpoints return 404.

**Checks:**
1. Verify `dryade.json` exists and is valid JSON
2. Check `plugin.py` has a `plugin` instance exported
3. Review Dryade logs for loading errors
4. Ensure Python dependencies are installed

```bash
# Check plugin is discovered
dryade plugins list

# View loading logs
tail -f logs/dryade.log | grep my_plugin
```

### API Routes Not Registering

**Symptoms:** Routes defined in routes.py return 404.

**Checks:**
1. Verify routes are imported in `on_load`
2. Check prefix matches expected path
3. Ensure router is included with `app.include_router()`

```python
# Correct way to register routes
async def on_load(self, app: FastAPI, context: dict) -> None:
    from . import routes
    app.include_router(routes.router, prefix="/api/my_plugin", tags=["my_plugin"])
```

### UI Not Appearing

**Symptoms:** Sidebar item missing or page shows blank/error.

**Checks:**
1. Verify `has_ui: true` in manifest
2. Check `ui/dist/bundle.js` exists
3. Ensure bundle size is within limit
4. Check browser console for JavaScript errors

```bash
# Rebuild UI
cd plugins/my_plugin/ui
npm run build
ls -la dist/bundle.js
```

### Common Errors and Solutions

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError` | Install missing dependency: `pip install package` |
| `CORS error in UI` | Use DryadeBridge for API calls, not fetch() |
| `Database connection error` | Check database URL in configuration |
| `Permission denied` | Verify plugin has required permissions in manifest |
| `Timeout on API call` | Increase REQUEST_TIMEOUT or optimize endpoint |

---

## 12. Examples

### Simple Plugin (No UI)

A minimal plugin that adds an API endpoint:

```python
# plugins/hello_world/plugin.py
"""Hello World plugin - minimal example."""
from fastapi import FastAPI, APIRouter

router = APIRouter()


@router.get("/greet/{name}")
async def greet(name: str):
    """Return a greeting."""
    return {"message": f"Hello, {name}!"}


class HelloWorldPlugin:
    """Simple greeting plugin."""

    async def on_load(self, app: FastAPI, context: dict) -> None:
        app.include_router(router, prefix="/api/hello", tags=["hello"])

    async def on_unload(self) -> None:
        pass

    async def health_check(self) -> dict:
        return {"status": "healthy"}


plugin = HelloWorldPlugin()
```

```json
// plugins/hello_world/dryade.json
{
  "name": "hello_world",
  "version": "1.0.0",
  "description": "A simple greeting plugin",
  "author": "Dryade Community",
  "manifest_version": "1.0",
  "has_ui": false,
  "plugin_dependencies": [],
  "core_version_constraint": ">=2.0.0,<3.0.0",
  "api_paths": ["/api/hello"]
}
```

### Plugin with API Routes

See the `document_processor` plugin in the community repository for a complete example with:
- Multiple API endpoints
- File upload handling
- Background processing
- Database storage

### Full Plugin with UI

See the `skill_editor` plugin for a complete example with:
- React frontend with multiple pages
- DryadeBridge API integration
- Real-time updates
- Theme-aware styling

### Community Plugin Repositories

- [dryade/plugin-template](https://github.com/dryade/plugin-template) - Official template
- [dryade/plugin-examples](https://github.com/dryade/plugin-examples) - Example plugins

---

## Next Steps

1. **Create your first plugin** using `dryade create-plugin`
2. **Explore existing plugins** in the `plugins/` directory
3. **Join the community** on [Discord](https://discord.gg/bvCPwqmu) or [GitHub Discussions](https://github.com/DryadeAI/Dryade/discussions)
4. **Share your plugins** by publishing to GitHub

---

*Last updated: 2026-02-05*
*Dryade Community Edition*
