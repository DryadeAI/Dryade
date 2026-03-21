---
title: Testing Plugins
sidebar_position: 4
---

# Testing Plugins

This guide covers how to set up a test environment, write unit and integration tests, and verify your plugin works correctly before publishing.

## Local Development Setup

Install your plugin in development mode:

```bash
cd plugins/my_plugin
pip install -e .
```

Or if using `uv`:

```bash
cd plugins/my_plugin
uv pip install -e .
```

Ensure Dryade core is running locally so your plugin can register and serve routes.

## Test Fixtures

Create `tests/conftest.py` with shared fixtures:

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
    """Create a test client with plugin routes mounted."""
    from plugins.my_plugin import routes
    mock_app.include_router(routes.router, prefix="/api/my_plugin")
    return TestClient(mock_app)
```

## Unit Tests

Test the plugin class lifecycle in `tests/test_plugin.py`:

```python
"""Unit tests for plugin lifecycle."""
import pytest
from plugins.my_plugin.plugin import MyPlugin


class TestMyPlugin:
    """Tests for MyPlugin class."""

    @pytest.fixture
    def plugin(self):
        """Create a fresh plugin instance."""
        return MyPlugin()

    @pytest.mark.asyncio
    async def test_on_load(self, plugin, mock_app, mock_context):
        """Test that plugin loads and initializes."""
        await plugin.on_load(mock_app, mock_context)
        assert plugin._initialized is True

    @pytest.mark.asyncio
    async def test_on_unload(self, plugin, mock_app, mock_context):
        """Test that plugin unloads cleanly."""
        await plugin.on_load(mock_app, mock_context)
        await plugin.on_unload()
        assert plugin._initialized is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, plugin, mock_app, mock_context):
        """Test health check when plugin is loaded."""
        await plugin.on_load(mock_app, mock_context)
        health = await plugin.health_check()
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, plugin):
        """Test health check before loading."""
        health = await plugin.health_check()
        assert health["status"] == "not_initialized"
```

## Testing Routes with TestClient

Use FastAPI's `TestClient` to test your API endpoints:

```python
"""Integration tests for plugin API routes."""


def test_get_status(test_client):
    """Test the status endpoint."""
    response = test_client.get("/api/my_plugin/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_item(test_client):
    """Test item creation."""
    response = test_client.post(
        "/api/my_plugin/items",
        json={"name": "Test Item", "value": 42},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Item"
    assert data["value"] == 42


def test_create_item_validation(test_client):
    """Test that invalid input returns 422."""
    response = test_client.post(
        "/api/my_plugin/items",
        json={"name": "", "value": -1},
    )
    assert response.status_code == 422


def test_delete_item(test_client):
    """Test item deletion."""
    response = test_client.delete("/api/my_plugin/items/1")
    assert response.status_code == 200
    assert response.json()["deleted"] is True
```

## Testing Plugin Configuration

If your plugin reads configuration from the context:

```python
@pytest.mark.asyncio
async def test_config_loading(mock_app):
    """Test that plugin reads config from context."""
    plugin = MyPlugin()
    context = {
        "config": {
            "api_key": "test-key-123",
            "refresh_interval": 30,
        },
    }
    await plugin.on_load(mock_app, context)
    assert plugin.api_key == "test-key-123"
    assert plugin.refresh_interval == 30
```

## Testing UI Components

For plugins with a frontend, test React components with your preferred testing library:

```bash
cd plugins/my_plugin/ui
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Add to `vite.config.ts`:

```typescript
export default defineConfig({
  // ... existing config
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
```

Example component test:

```typescript
// src/__tests__/App.test.tsx
import { render, screen } from '@testing-library/react';
import { App } from '../App';

// Mock the DryadeBridge
window.DryadeBridge = {
  pluginName: 'test_plugin',
  permissions: ['read_config'],
  currentTheme: 'dark',
  postMessage: vi.fn(),
  apiRequest: vi.fn(),
  ready: vi.fn(),
};

describe('App', () => {
  it('renders the plugin title', () => {
    render(<App />);
    expect(screen.getByText('My Plugin')).toBeInTheDocument();
  });
});
```

Run frontend tests:

```bash
cd plugins/my_plugin/ui
npx vitest run
```

## Running Tests

```bash
# Run all plugin tests
pytest plugins/my_plugin/tests -v

# Run with coverage report
pytest plugins/my_plugin/tests \
  --cov=plugins.my_plugin \
  --cov-report=term-missing

# Run a specific test
pytest plugins/my_plugin/tests/test_plugin.py::TestMyPlugin::test_on_load -v
```

## Integration Testing with Core

To test your plugin running inside a full Dryade instance:

1. Start Dryade with your plugin directory included
2. Use the plugin CLI to push a development allowlist:

```bash
dryade-pm push --plugins-dir plugins/
```

3. Verify your plugin loaded:

```bash
curl http://localhost:8000/api/plugins
```

4. Test your plugin's endpoints against the running server:

```bash
curl http://localhost:8000/api/my_plugin/status
```

## Testing Checklist

Before publishing, verify:

- [ ] All lifecycle hooks work (`on_load`, `on_unload`, `health_check`)
- [ ] API routes return correct status codes and response shapes
- [ ] Input validation rejects invalid data (422 responses)
- [ ] Error cases are handled gracefully (no 500 errors)
- [ ] Configuration is read correctly from context
- [ ] UI renders without errors (if applicable)
- [ ] Plugin loads in a running Dryade instance
