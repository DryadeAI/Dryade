---
title: WebSocket Streaming
sidebar_position: 2
---

# WebSocket Streaming

Dryade provides real-time streaming via WebSocket connections. This is how the chat interface receives live responses, tool execution results, and agent thinking steps as they happen.

## Connecting

Open a WebSocket connection to the chat endpoint:

```
ws://localhost:8000/api/chat/ws
```

In production with TLS:

```
wss://your-domain.com/api/chat/ws
```

**Authentication:** Include your JWT token as a query parameter or in the connection headers:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/chat/ws?token=YOUR_JWT_TOKEN');
```

## Message Format

All messages are JSON objects with a `type` field that indicates the event kind.

### Sending Messages

Send a chat message to the agent:

```json
{
  "type": "message",
  "content": "What files are in the project?",
  "conversation_id": "conv-123"
}
```

### Receiving Events

The server sends a stream of events as the agent processes your request.

**Example stream for a single message:**

```
{ "type": "thinking",    "content": "I need to list the project files..." }
{ "type": "tool_call",   "name": "filesystem_list", "arguments": {"path": "."} }
{ "type": "tool_result", "name": "filesystem_list", "result": "src/ docs/ ..." }
{ "type": "message",     "content": "Here are the files in your project..." }
{ "type": "done" }
```

## Event Types

| Type | Direction | Description |
|------|-----------|-------------|
| `message` | Both | Chat message content (user sends, agent responds) |
| `thinking` | Server | Agent reasoning steps (visible when thinking mode is enabled) |
| `tool_call` | Server | Agent is invoking a tool (includes tool name and arguments) |
| `tool_result` | Server | Result from a tool execution |
| `error` | Server | An error occurred during processing |
| `done` | Server | Agent has finished processing the current request |

### Event Payloads

**message:**

```json
{
  "type": "message",
  "content": "The project contains 3 directories...",
  "conversation_id": "conv-123"
}
```

**thinking:**

```json
{
  "type": "thinking",
  "content": "Let me analyze the directory structure to give a helpful overview."
}
```

**tool_call:**

```json
{
  "type": "tool_call",
  "name": "filesystem_list",
  "arguments": { "path": ".", "recursive": false },
  "call_id": "call-456"
}
```

**tool_result:**

```json
{
  "type": "tool_result",
  "name": "filesystem_list",
  "result": "src/\ndocs/\ntests/",
  "call_id": "call-456"
}
```

**error:**

```json
{
  "type": "error",
  "message": "Tool execution failed: connection timeout",
  "code": "TOOL_ERROR"
}
```

## SSE Alternative

For environments where WebSocket connections are difficult (corporate proxies, serverless functions), Dryade also supports Server-Sent Events (SSE):

```bash
curl -N http://localhost:8000/api/chat/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hello!",
    "conversation_id": "conv-123"
  }'
```

**SSE response stream:**

```
data: {"type": "thinking", "content": "Processing the greeting..."}

data: {"type": "message", "content": "Hello! How can I help you today?"}

data: {"type": "done"}
```

**JavaScript SSE client:**

```javascript
async function streamChat(message, conversationId, onEvent) {
  const response = await fetch('http://localhost:8000/api/chat/stream', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      content: message,
      conversation_id: conversationId,
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6));
        onEvent(event);
      }
    }
  }
}
```

## JavaScript WebSocket Client

A complete WebSocket client example:

```javascript
class DryadeChat {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl.replace(/^http/, 'ws');
    this.token = token;
    this.ws = null;
    this.handlers = {};
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(
        `${this.baseUrl}/api/chat/ws?token=${this.token}`
      );

      this.ws.onopen = () => resolve();
      this.ws.onerror = (err) => reject(err);

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const handler = this.handlers[data.type];
        if (handler) handler(data);
      };

      this.ws.onclose = () => {
        // Attempt reconnection after a delay
        setTimeout(() => this.connect(), 3000);
      };
    });
  }

  on(eventType, handler) {
    this.handlers[eventType] = handler;
    return this;
  }

  send(content, conversationId) {
    this.ws.send(JSON.stringify({
      type: 'message',
      content,
      conversation_id: conversationId,
    }));
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Usage
const chat = new DryadeChat('http://localhost:8000', 'YOUR_TOKEN');

chat
  .on('message', (e) => console.log('Agent:', e.content))
  .on('thinking', (e) => console.log('Thinking:', e.content))
  .on('tool_call', (e) => console.log('Calling tool:', e.name))
  .on('error', (e) => console.error('Error:', e.message))
  .on('done', () => console.log('--- Response complete ---'));

await chat.connect();
chat.send('What tools do you have available?', 'conv-123');
```

## Reconnection Strategy

WebSocket connections can drop due to network issues, server restarts, or proxy timeouts. Recommended reconnection approach:

1. **Detect disconnection** via the `onclose` event
2. **Wait before reconnecting** -- use exponential backoff (1s, 2s, 4s, 8s, max 30s)
3. **Re-authenticate** on reconnect -- send a fresh token
4. **Resume context** -- include the `conversation_id` to continue where you left off

```javascript
function connectWithBackoff(url, token, maxRetries = 10) {
  let retries = 0;

  function attempt() {
    const ws = new WebSocket(`${url}?token=${token}`);

    ws.onopen = () => {
      retries = 0; // Reset on successful connection
    };

    ws.onclose = () => {
      if (retries < maxRetries) {
        const delay = Math.min(1000 * Math.pow(2, retries), 30000);
        retries++;
        setTimeout(attempt, delay);
      }
    };

    return ws;
  }

  return attempt();
}
```

## Proxy Configuration

If running behind a reverse proxy (Nginx, Caddy), ensure WebSocket upgrade headers are forwarded:

**Nginx example:**

```nginx
location /api/chat/ws {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}
```

The `proxy_read_timeout` value prevents Nginx from closing idle WebSocket connections prematurely.
