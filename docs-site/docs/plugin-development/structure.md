---
title: Plugin Structure
sidebar_position: 1
---

# Plugin Structure

This guide covers the anatomy of a Dryade plugin: directory layout, entry points, lifecycle hooks, and how to build your first plugin from scratch.

## Overview

A Dryade plugin is a Python package that extends the platform with new capabilities -- custom API endpoints, UI pages, tool integrations, and more. Plugins are discovered at startup and loaded if they are included in the plugin catalog for your license tier.

**Plugins can:**

- Add new API endpoints to the backend
- Provide custom UI pages in the sidebar
- Integrate with external services and tools
- Add agent capabilities and skills
- Process and transform data

## Directory Layout

Every plugin follows this structure:

```
my_plugin/
  dryade.json          # Manifest -- metadata and configuration (required)
  __init__.py          # Python package marker (required)
  plugin.py            # Entry point with plugin class (required)
  routes.py            # FastAPI routes (optional)
  schemas.py           # Pydantic models (optional)
  config.py            # Configuration management (optional)
  tests/               # Test directory (recommended)
    __init__.py
    test_plugin.py
    conftest.py
  ui/                  # Frontend bundle (if has_ui: true)
    package.json
    vite.config.ts
    src/
      App.tsx
      index.tsx
    dist/
      bundle.js
```

### File Summary

| File | Purpose | Required |
|------|---------|----------|
| `dryade.json` | Plugin metadata, tier, and capabilities | Yes |
| `__init__.py` | Makes directory a Python package | Yes |
| `plugin.py` | Main plugin class with lifecycle hooks | Yes |
| `routes.py` | FastAPI router with API endpoints | No |
| `schemas.py` | Pydantic models for request/response validation | No |
| `config.py` | Plugin-specific configuration | No |
| `tests/` | Plugin tests (pytest) | Recommended |
| `ui/` | React frontend application | No |

## Plugin Entry Point

The `plugin.py` file contains your plugin class. It must export a module-level `plugin` variable:

```python
"""Plugin entry point."""
from typing import Any
from fastapi import FastAPI


class MyPlugin:
    """My plugin implementation."""

    name = "my_plugin"
    version = "1.0.0"
    description = "A brief description of what this plugin does"

    def __init__(self):
        self._initialized = False

    async def on_load(self, app: FastAPI, context: dict[str, Any]) -> None:
        """Called when the plugin is loaded.

        Args:
            app: The FastAPI application instance.
            context: Plugin context with config, database session factory, etc.
        """
        # Register routes
        from . import routes
        app.include_router(
            routes.router,
            prefix="/api/my_plugin",
            tags=["my_plugin"],
        )
        self._initialized = True

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded. Clean up resources."""
        self._initialized = False

    async def health_check(self) -> dict[str, Any]:
        """Return plugin health status."""
        return {
            "status": "healthy" if self._initialized else "not_initialized",
            "version": self.version,
        }


# Module-level instance -- required for discovery
plugin = MyPlugin()
```

## Lifecycle Hooks

Dryade calls these methods at specific points in the plugin lifecycle:

| Hook | When Called | Purpose |
|------|------------|---------|
| `on_load(app, context)` | Plugin startup | Initialize resources, register routes |
| `on_unload()` | Plugin shutdown | Close connections, save state |
| `health_check()` | Health endpoint called | Report plugin status |

The `context` dictionary passed to `on_load` provides access to shared services:

```python
async def on_load(self, app: FastAPI, context: dict[str, Any]) -> None:
    config = context.get("config", {})
    event_bus = context.get("event_bus")
```

## Adding API Routes

Create `routes.py` with a FastAPI router:

```python
"""Plugin API routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class ItemCreate(BaseModel):
    """Request schema for creating an item."""
    name: str = Field(..., min_length=1, max_length=100)
    value: int = Field(..., ge=0)


class ItemResponse(BaseModel):
    """Response schema."""
    id: int
    name: str
    value: int


@router.get("/status")
async def get_status():
    """Get plugin status."""
    return {"status": "ok", "version": "1.0.0"}


@router.post("/items", response_model=ItemResponse)
async def create_item(item: ItemCreate):
    """Create a new item."""
    return {"id": 1, "name": item.name, "value": item.value}
```

Register the router in your `on_load` method:

```python
from . import routes
app.include_router(routes.router, prefix="/api/my_plugin", tags=["my_plugin"])
```

## Settings Schema

Plugins can define a configuration schema in the manifest. This schema drives an auto-generated settings form in the Dryade UI:

```json
{
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": { "type": "string", "description": "External API key" },
      "refresh_interval": { "type": "integer", "default": 60 }
    },
    "required": ["api_key"]
  }
}
```

Access settings in your plugin:

```python
async def on_load(self, app: FastAPI, context: dict[str, Any]) -> None:
    config = context.get("config", {})
    api_key = config.get("api_key", "")
    refresh = config.get("refresh_interval", 60)
```

## Example: Minimal Hello World Plugin

A complete working plugin with one route:

**`dryade.json`:**

```json
{
  "name": "hello_world",
  "version": "1.0.0",
  "description": "A simple greeting plugin",
  "author": "Your Name",
  "manifest_version": "1.0",
  "has_ui": false,
  "plugin_dependencies": [],
  "core_version_constraint": ">=1.0.0",
  "api_paths": ["/api/hello"],
  "required_tier": "starter"
}
```

**`__init__.py`:**

```python
from .plugin import plugin
```

**`plugin.py`:**

```python
"""Hello World plugin."""
from fastapi import FastAPI, APIRouter

router = APIRouter()


@router.get("/greet/{name}")
async def greet(name: str):
    """Return a greeting."""
    return {"message": f"Hello, {name}!"}


class HelloWorldPlugin:
    name = "hello_world"
    version = "1.0.0"
    description = "A simple greeting plugin"

    async def on_load(self, app: FastAPI, context: dict) -> None:
        app.include_router(router, prefix="/api/hello", tags=["hello"])

    async def on_unload(self) -> None:
        pass

    async def health_check(self) -> dict:
        return {"status": "healthy"}


plugin = HelloWorldPlugin()
```

After loading, the endpoint is available at `GET /api/hello/greet/World`.

## Next Steps

- [Plugin Manifest](/plugin-development/manifest) -- Learn the full manifest format
- [Plugin UI](/plugin-development/ui-sandbox) -- Add a frontend to your plugin
- [Testing Plugins](/plugin-development/testing) -- Write and run plugin tests
- [Publishing Plugins](/plugin-development/publishing) -- Share your plugin
