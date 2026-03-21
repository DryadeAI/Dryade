---
title: Plugin UI
sidebar_position: 3
---

# Plugin UI

Plugin frontends run inside **sandboxed iframes**, isolated from the main Dryade application. This guide covers how to build a React UI for your plugin, communicate with the host application, and handle theming.

## How Plugin UIs Work

When a user navigates to your plugin's page, Dryade loads your compiled JavaScript bundle inside a sandboxed iframe. The iframe has restricted permissions:

- No access to the parent window's DOM
- No direct network requests (use the API proxy instead)
- No access to the main application's localStorage
- No form submissions or popups

Communication between your plugin and Dryade happens through the **DryadeBridge** -- a `postMessage`-based API injected into the iframe.

## Setting Up the UI

Initialize a React project in the `ui/` directory of your plugin:

```bash
cd plugins/my_plugin
mkdir ui && cd ui
npm init -y
npm install react react-dom
npm install -D typescript vite @vitejs/plugin-react @types/react @types/react-dom
```

### Vite Configuration

Create `vite.config.ts`:

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
  },
});
```

The `iife` format produces a single self-contained bundle that runs inside the iframe.

### Entry Point

Create `src/index.tsx`:

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

// Signal to the host that the plugin UI is ready
declare global {
  interface Window {
    DryadeBridge?: { ready: () => void };
  }
}
window.DryadeBridge?.ready();
```

## DryadeBridge API

The DryadeBridge is the communication layer between your plugin and the host application. It is injected into the iframe's `window` object.

### Available Methods

| Method | Description |
|--------|-------------|
| `DryadeBridge.ready()` | Signal that the plugin UI has finished loading |
| `DryadeBridge.postMessage(type, data)` | Send a message to the host application |
| `DryadeBridge.apiRequest(requestId, method, path, body?)` | Make an API request through the host proxy |

### Available Properties

| Property | Type | Description |
|----------|------|-------------|
| `DryadeBridge.pluginName` | string | The plugin's name |
| `DryadeBridge.permissions` | string[] | Granted permissions |
| `DryadeBridge.currentTheme` | `'light'` or `'dark'` | Current UI theme |

### Making API Requests

Use the bridge to make API requests through the host. This avoids CORS issues and ensures proper authentication:

```typescript
// src/bridge/api.ts

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

// Handle responses from the host
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

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
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
```

### Using the API Client

```typescript
// Plugin-specific API client
export const api = {
  getStatus: () => apiRequest<{ status: string }>('GET', '/my_plugin/status'),
  getItems: () => apiRequest<Item[]>('GET', '/my_plugin/items'),
  createItem: (data: CreateItemRequest) =>
    apiRequest<Item>('POST', '/my_plugin/items', data),
};
```

## Settings UI

If your plugin defines a `config_schema` in the manifest, Dryade automatically generates a settings form. Users can configure your plugin from the UI without any additional frontend code.

For custom settings interfaces, use the DryadeBridge to read and write configuration:

```typescript
// Read current config
const config = await apiRequest<PluginConfig>('GET', '/my_plugin/config');

// Save updated config
await apiRequest('PUT', '/my_plugin/config', { api_key: 'new-key' });
```

## Example: Simple Plugin UI

A complete `App.tsx` for a plugin with a list view:

```typescript
import { useState, useEffect } from 'react';
import { apiRequest } from './bridge/api';

interface Item {
  id: number;
  name: string;
  value: number;
}

export function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    setLoading(true);
    try {
      const data = await apiRequest<Item[]>('GET', '/my_plugin/items');
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin h-8 w-8 border-2 border-primary
          border-t-transparent rounded-full" />
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
    <div className="p-6 max-w-7xl mx-auto text-foreground bg-background
      min-h-screen">
      <h1 className="text-2xl font-bold mb-6">My Plugin</h1>
      {items.length === 0 ? (
        <p className="text-muted-foreground py-12 text-center">
          No items yet.
        </p>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <div key={item.id}
              className="p-4 bg-card rounded-lg border border-border">
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

## Theming

Plugins inherit the host application's theme. Use CSS variables for consistent styling that adapts to light and dark modes:

```css
/* Available CSS variables from the host theme */
--background          /* Page background */
--foreground          /* Primary text color */
--card                /* Card background */
--card-foreground     /* Card text */
--primary             /* Primary accent color */
--muted               /* Muted background */
--muted-foreground    /* Secondary text */
--border              /* Border color */
--destructive         /* Error/danger color */
--success             /* Success color */
```

Use these in your components via Tailwind utility classes or CSS:

```css
.my-card {
  background: hsl(var(--card));
  color: hsl(var(--card-foreground));
  border: 1px solid hsl(var(--border));
}
```

## Building the UI

Compile your plugin's frontend:

```bash
cd plugins/my_plugin/ui
npm run build
```

This generates `ui/dist/bundle.js`, which Dryade loads into the sandboxed iframe. Remember to rebuild after any source changes.
