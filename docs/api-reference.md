---
title: API Reference
sidebar_position: 7
description: Dryade REST API endpoints and interactive documentation
---

# API Reference

Dryade exposes a RESTful API built with FastAPI. All endpoints are available under the `/api/` prefix.

## Interactive Documentation

After starting Dryade, access the interactive API docs at:

- **Swagger UI:** [http://localhost:8080/api/docs](http://localhost:8080/api/docs)
- **ReDoc:** [http://localhost:8080/api/redoc](http://localhost:8080/api/redoc)

These are auto-generated from the FastAPI OpenAPI schema and include request/response examples, parameter descriptions, and a "Try it out" feature.

## Authentication

Most endpoints require authentication via a JWT bearer token.

### Register

```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "your-password", "display_name": "User"}'
```

### Login

```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "your-password"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### Using the Token

Include the token in the `Authorization` header for authenticated requests:

```bash
curl http://localhost:8080/api/users/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

## Endpoint Groups

### Health (`/health`)

System health and diagnostics.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Basic health check |
| GET | `/health/detailed` | Detailed health with component status |
| GET | `/health/metrics` | System metrics |
| GET | `/live` | Kubernetes liveness probe |
| GET | `/ready` | Kubernetes readiness probe |

```bash
# Quick health check
curl http://localhost:8080/health

# Detailed health (database, LLM, etc.)
curl http://localhost:8080/health/detailed
```

### Authentication (`/api/auth`)

User registration, login, and session management.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register a new user |
| POST | `/api/auth/login` | Login and get JWT token |
| POST | `/api/auth/logout` | Invalidate current token |
| POST | `/api/auth/refresh` | Refresh an expiring token |
| POST | `/api/auth/setup` | Initial admin setup (first user) |

### Chat (`/api/chat`)

Conversation management and message streaming.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message (non-streaming) |
| POST | `/api/chat/stream` | Send a message (streaming via SSE) |
| GET | `/api/chat/conversations` | List all conversations |
| POST | `/api/chat/conversations` | Create a new conversation |
| GET | `/api/chat/conversations/{id}` | Get conversation details |
| DELETE | `/api/chat/conversations/{id}` | Delete a conversation |
| GET | `/api/chat/history/{id}` | Get conversation message history |
| GET | `/api/chat/modes` | List available orchestration modes |

```bash
# Send a chat message
curl -X POST http://localhost:8080/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "conversation_id": "conv-123"}'
```

### Agents (`/api/agents`)

Agent management and invocation.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents` | List available agents |
| GET | `/api/agents/{name}` | Get agent details |
| POST | `/api/agents/{name}/invoke` | Invoke an agent |
| GET | `/api/agents/{name}/tools` | List agent tools |
| GET | `/api/agents/{name}/describe` | Get agent description |

```bash
# List available agents
curl http://localhost:8080/api/agents \
  -H "Authorization: Bearer $TOKEN"

# Invoke an agent
curl -X POST http://localhost:8080/api/agents/researcher/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Research the latest trends in edge AI"}'
```

### Knowledge (`/api/knowledge`)

Knowledge base management for RAG.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/knowledge` | List knowledge sources |
| POST | `/api/knowledge/upload` | Upload a document |
| POST | `/api/knowledge/query` | Query the knowledge base |
| GET | `/api/knowledge/{id}` | Get source details |
| GET | `/api/knowledge/{id}/chunks` | Get source chunks |
| DELETE | `/api/knowledge/{id}` | Delete a knowledge source |

```bash
# Upload a document
curl -X POST http://localhost:8080/api/knowledge/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf"

# Query knowledge base
curl -X POST http://localhost:8080/api/knowledge/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the deployment requirements?"}'
```

### Workflows (`/api/flows`)

Multi-agent workflow execution.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/flows` | List available workflows |
| GET | `/api/flows/{name}` | Get workflow details |
| POST | `/api/flows/{name}/execute` | Execute a workflow |
| POST | `/api/flows/{name}/execute/stream` | Execute with streaming |
| GET | `/api/flows/{name}/graph` | Get workflow graph structure |
| GET | `/api/flows/executions/{id}` | Get execution status |

### Models & Providers (`/api/models`, `/api/providers`)

LLM provider management and configuration.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/models/config` | Get current model configuration |
| PATCH | `/api/models/config` | Update model configuration |
| GET | `/api/providers` | List configured providers |
| POST | `/api/providers/{id}/test` | Test provider connectivity |
| GET | `/api/providers/{id}/models` | Discover available models |
| POST | `/api/models/keys` | Store provider API key |

### Projects (`/api/projects`)

Organize conversations into projects.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create a project |
| GET | `/api/projects/{id}` | Get project details |
| PATCH | `/api/projects/{id}` | Update a project |
| DELETE | `/api/projects/{id}` | Delete a project |
| GET | `/api/projects/{id}/conversations` | List project conversations |

### Users (`/api/users`)

User management (admin only for listing/searching).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/users/me` | Get current user profile |
| PATCH | `/api/users/me` | Update current user profile |
| GET | `/api/users` | List all users (admin) |
| GET | `/api/users/search` | Search users (admin) |

## WebSocket API

Dryade uses WebSocket for real-time streaming of LLM responses.

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8080/ws/chat?token=YOUR_JWT_TOKEN');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.content); // Streamed response chunks
};
```

### Message Format

```json
{
  "type": "chat",
  "message": "What is Dryade?",
  "conversation_id": "conv-123",
  "mode": "orchestrate"
}
```

### Response Events

| Event Type | Description |
|------------|-------------|
| `token` | Streamed text token |
| `tool_call` | Tool invocation notification |
| `tool_result` | Tool execution result |
| `done` | Stream complete |
| `error` | Error occurred |

## Rate Limiting

API requests are rate-limited per user. Default limits:

| Tier | Requests per minute |
|------|-------------------|
| Default | 300 |
| Pro | 600 |
| Admin | 1000 |

Rate limit headers are included in every response:

```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 298
X-RateLimit-Reset: 1234567890
```

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Description of the error"
}
```

Common HTTP status codes:

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (missing or invalid token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Resource not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
