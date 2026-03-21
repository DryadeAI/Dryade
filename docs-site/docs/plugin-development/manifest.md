---
title: Plugin Manifest
sidebar_position: 2
---

# Plugin Manifest

Every Dryade plugin requires a `dryade.json` manifest file in its root directory. This file declares the plugin's metadata, capabilities, tier requirements, and UI configuration.

## Required Fields

At minimum, your manifest must include:

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "A brief description of what your plugin does",
  "author": "Your Name",
  "manifest_version": "1.0",
  "has_ui": false,
  "plugin_dependencies": [],
  "core_version_constraint": ">=1.0.0",
  "required_tier": "starter"
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique plugin identifier. Must match the directory name. |
| `version` | string | Semantic version (e.g., `"1.0.0"`) |
| `description` | string | Short description of the plugin's purpose |
| `author` | string | Plugin author or organization name |
| `manifest_version` | string | Manifest schema version (currently `"1.0"`) |
| `has_ui` | boolean | Whether the plugin includes a frontend bundle |
| `plugin_dependencies` | array | List of other plugin names this plugin depends on |
| `core_version_constraint` | string | Semver range for compatible Dryade core versions |
| `required_tier` | string | Minimum license tier needed to use this plugin |

## Optional Fields

```json
{
  "display_name": "My Plugin",
  "api_paths": ["/api/my_plugin"],
  "routes_prefix": "/api/plugins/my_plugin",
  "dependencies": [],
  "tools": [],
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": { "type": "string" },
      "refresh_interval": { "type": "integer", "default": 60 }
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `display_name` | string | Human-readable name shown in the UI |
| `api_paths` | array | API route paths the plugin registers |
| `routes_prefix` | string | Route prefix for auto-mounted routes |
| `dependencies` | array | External package dependencies |
| `tools` | array | Tools the plugin provides to agents |
| `config_schema` | object | JSON Schema for the plugin's settings form |

## Tier Requirements

The `required_tier` field determines which license tier is needed to use the plugin:

| Tier | Who Can Use It |
|------|----------------|
| `starter` | All licensed users (Starter, Team, and Enterprise) |
| `team` | Team and Enterprise license holders |
| `enterprise` | Enterprise license holders only |

Choose the tier based on the plugin's target audience and feature complexity.

## Configuration Schema

The `config_schema` field defines a JSON Schema that powers an auto-generated settings form in the Dryade UI. Users can configure your plugin without editing files.

```json
{
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "description": "API key for the external service"
      },
      "units": {
        "type": "string",
        "enum": ["metric", "imperial"],
        "default": "metric"
      },
      "locations": {
        "type": "array",
        "items": { "type": "string" },
        "description": "List of locations to monitor"
      }
    },
    "required": ["api_key"]
  }
}
```

## UI Configuration

When `has_ui` is `true`, include a `ui` section to configure the plugin's frontend:

```json
{
  "has_ui": true,
  "ui": {
    "entry": "ui/dist/bundle.js",
    "max_bundle_size_kb": 500,
    "permissions": ["read_config", "write_config", "api_proxy"],
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

### UI Fields

| Field | Type | Description |
|-------|------|-------------|
| `entry` | string | Path to the compiled UI bundle |
| `max_bundle_size_kb` | integer | Maximum allowed bundle size in KB |
| `permissions` | array | Permissions the UI needs (`read_config`, `write_config`, `api_proxy`) |
| `routes` | array | Pages the plugin adds (path + title) |
| `sidebar_item` | object | Sidebar entry (icon, label, parent section) |

### Sidebar Parents

| Parent | Description |
|--------|-------------|
| `monitoring` | Monitoring and analytics section |
| `plugins` | General plugins section |
| `tools` | Developer tools section |
| `settings` | Settings area |

### Available Icons

Use [Lucide](https://lucide.dev/icons/) icon names: `settings`, `file`, `folder`, `cloud`, `database`, `chart`, `users`, `shield`, `dollar-sign`, `activity`, and many more.

## Complete Example

A full manifest for a weather dashboard plugin with UI:

```json
{
  "name": "weather_dashboard",
  "display_name": "Weather Dashboard",
  "version": "1.2.0",
  "description": "Display weather forecasts and alerts in your dashboard",
  "author": "Weather Team",
  "manifest_version": "1.0",
  "has_ui": true,
  "plugin_dependencies": [],
  "core_version_constraint": ">=1.0.0",
  "required_tier": "starter",
  "api_paths": ["/api/weather"],
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "description": "OpenWeatherMap API key"
      },
      "units": {
        "type": "string",
        "enum": ["metric", "imperial"],
        "default": "metric"
      },
      "locations": {
        "type": "array",
        "items": { "type": "string" }
      }
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

## Validation

Before publishing, validate your manifest:

```bash
# Check manifest structure
dryade validate-plugin plugins/my_plugin

# Verbose output for debugging
dryade validate-plugin plugins/my_plugin --verbose
```

Common validation errors:

| Error | Cause | Fix |
|-------|-------|-----|
| Missing required field | A required field is absent | Add the field to `dryade.json` |
| Invalid version format | Version is not valid semver | Use format `"1.0.0"` |
| UI bundle missing | `has_ui: true` but no bundle file | Run `npm run build` in `ui/` |
| Bundle size exceeds limit | Bundle larger than `max_bundle_size_kb` | Optimize the bundle or increase the limit |
