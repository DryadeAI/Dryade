---
title: Plugins
sidebar_position: 6
description: Extend Dryade with plugins from the marketplace or build your own
---

# Plugins

Plugins extend Dryade with additional features, integrations, and capabilities. They can add new API endpoints, UI pages, background tasks, and more.

## Discovering Plugins

Browse available plugins on the [Dryade Marketplace](https://dryade.ai). Plugins are organized by category:

- **Productivity** -- Project management, document processing, templates
- **Analytics** -- Cost tracking, KPI monitoring, usage metrics
- **Integration** -- External service connectors, CRM tools
- **AI Enhancement** -- Model selection, semantic caching, conversation tools
- **Security & Compliance** -- Audit logging, compliance checks

## Installing Plugins

1. Visit the [Dryade Marketplace](https://dryade.ai) and choose a plan that includes the plugins you need
2. Follow the installation instructions for your subscription tier
3. Restart Dryade to load the new plugins
4. Verify installation at **Settings > Plugins** in the Dryade UI

## Creating Your Own Plugins

Dryade has an open plugin architecture. You can create plugins to add custom functionality and even publish them on the marketplace.

### Plugin Structure

A minimal plugin looks like this:

```
my-plugin/
  dryade.json          # Plugin manifest
  __init__.py          # Plugin entry point
  routes.py            # API routes (optional)
  ui/                  # Frontend UI (optional)
    dist/
      index.html
      bundle.js
```

### Plugin Manifest (dryade.json)

Every plugin needs a manifest file that describes it:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "A custom plugin that does amazing things",
  "author": "Your Name",
  "entry_point": "__init__",
  "required_tier": "starter",
  "capabilities": {
    "has_routes": true,
    "has_ui": true,
    "has_settings": true
  },
  "settings_schema": {
    "type": "object",
    "properties": {
      "api_url": {
        "type": "string",
        "title": "API URL",
        "description": "External API endpoint"
      }
    }
  }
}
```

**Manifest fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique plugin identifier (lowercase, hyphens allowed) |
| `version` | Yes | Semantic version (e.g., `1.0.0`) |
| `description` | Yes | Short description of what the plugin does |
| `author` | Yes | Plugin author name |
| `entry_point` | Yes | Python module containing the plugin class |
| `required_tier` | Yes | Minimum subscription tier (`starter`, `team`, `enterprise`) |
| `capabilities` | No | Declares what the plugin provides (routes, UI, settings) |
| `settings_schema` | No | JSON Schema for plugin settings (rendered in the UI) |

### Plugin Entry Point

The `__init__.py` file must export a plugin instance:

```python
from core.plugins import DryadePlugin

class MyPlugin(DryadePlugin):
    """My custom plugin."""

    name = "my-plugin"
    version = "1.0.0"

    def on_load(self):
        """Called when the plugin is loaded."""
        self.logger.info("My plugin loaded!")

    def get_routes(self):
        """Return FastAPI routes for this plugin."""
        from .routes import router
        return router

# Required: export the plugin instance
plugin = MyPlugin()
```

### Adding API Routes

Create a `routes.py` file with FastAPI routes:

```python
from fastapi import APIRouter

router = APIRouter(tags=["my-plugin"])

@router.get("/my-plugin/data")
async def get_data():
    return {"message": "Hello from my plugin!"}
```

Plugin routes are automatically mounted under `/api/plugins/`.

### Adding a UI

Plugins can include a frontend UI that renders inside Dryade's workbench:

1. Create your UI in `ui/src/` using any framework (React, Svelte, vanilla JS)
2. Build it to `ui/dist/` with an `index.html` entry point
3. Set `has_ui: true` in your manifest
4. The UI renders in a sandboxed iframe within the Dryade workbench

### Plugin Settings

Plugins can define a settings schema in their manifest. The schema is rendered as a form in the Dryade UI under **Settings > Plugins > [Your Plugin]**.

Settings are stored per-user and accessible in your plugin code:

```python
class MyPlugin(DryadePlugin):
    def on_load(self):
        # Access plugin settings
        settings = self.get_settings()
        api_url = settings.get("api_url", "https://default-api.example.com")
```

## Publishing to the Marketplace

Want to share your plugin with the Dryade community or sell it on the marketplace?

1. **Develop and test** your plugin locally
2. **Write documentation** -- Include a README with setup instructions, configuration options, and usage examples
3. **Submit for review** -- Visit the [Developer Portal](https://dryade.ai/developers) and submit your plugin for review
4. **Publish** -- Once approved, your plugin appears in the marketplace

Plugins on the marketplace can be offered as free or paid. See the [Developer Agreement](https://dryade.ai/legal/developer-agreement) for terms.

## Plugin Tiers

Plugins are categorized by subscription tier:

| Tier | Description |
|------|-------------|
| **Starter** | Essential productivity plugins for individuals |
| **Team** | Collaboration and analytics plugins for teams |
| **Enterprise** | Advanced compliance, security, and integration plugins |

Community users have access to the full Dryade core platform. Plugins add premium features on top of the core.
