---
title: Configuration Reference
sidebar_position: 2
description: Complete reference for all Dryade environment variables
---

# Configuration Reference

Dryade is configured via environment variables, all prefixed with `DRYADE_`. Set them in your `.env` file or pass them directly to Docker.

## Core Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_ENV` | `development` \| `staging` \| `production` | `development` | Application environment. Production enables stricter validation. |
| `DRYADE_DEBUG` | boolean | `false` | Enable debug mode with verbose logging. |
| `DRYADE_LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` | Logging verbosity level. |
| `DRYADE_LOG_FORMAT` | `json` \| `pretty` | `pretty` | Log output format. Use `json` for production log aggregation. |
| `DRYADE_HOST` | string | `0.0.0.0` | Backend server bind address. |
| `DRYADE_PORT` | integer | `8080` | Backend server port. |
| `DRYADE_WORKERS` | integer | `4` | Number of uvicorn workers. |

## LLM Provider

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_LLM_MODE` | `ollama` \| `vllm` \| `openai` \| `anthropic` \| `litellm` | `vllm` | LLM provider type. |
| `DRYADE_LLM_MODEL` | string | `local-llm` | Model name to use. |
| `DRYADE_LLM_BASE_URL` | string | `http://127.0.0.1:8000/v1` | Base URL for LLM API endpoint. **Required.** |
| `DRYADE_LLM_API_KEY` | string | *(none)* | API key for cloud providers (OpenAI, Anthropic). |
| `DRYADE_LLM_TIMEOUT` | integer | `120` | Timeout in seconds for chat/agent requests. |
| `DRYADE_LLM_PLANNER_TIMEOUT` | integer | `300` | Timeout in seconds for plan generation. |
| `DRYADE_LLM_TEMPERATURE` | float | `0.7` | Default sampling temperature. |
| `DRYADE_LLM_MAX_TOKENS` | integer | `4096` | Maximum tokens per response. |
| `DRYADE_LLM_CONFIG_SOURCE` | `env` \| `database` \| `auto` | `auto` | Where to read LLM config from. `auto` tries database first, falls back to env. |

## Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_DATABASE_URL` | string | `postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade` | Database connection URL. Supports PostgreSQL and SQLite. |
| `DRYADE_DATABASE_SSL_MODE` | string | `prefer` | PostgreSQL SSL mode. Use `require` in production. |
| `DRYADE_REDIS_URL` | string | *(none)* | Redis URL for caching and rate limiting (optional). |
| `DRYADE_REDIS_ENABLED` | boolean | `true` | Enable Redis integration. |
| `DRYADE_QDRANT_URL` | string | *(none)* | Qdrant vector database URL for knowledge search (optional). |

## Authentication & Security

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_AUTH_ENABLED` | boolean | `true` | Enable user authentication. |
| `DRYADE_JWT_SECRET` | string | *(none)* | **Required.** Secret key for JWT tokens. Generate with `openssl rand -hex 32`. |
| `DRYADE_JWT_ALGORITHM` | string | `HS256` | JWT signing algorithm. |
| `DRYADE_JWT_EXPIRY_HOURS` | integer | `24` | Token expiration time in hours. |
| `DRYADE_ENCRYPTION_KEY` | string | *(none)* | Encryption key for stored credentials. Generate with `openssl rand -hex 32`. |
| `DRYADE_CORS_ORIGINS` | string | `http://localhost:3000,http://localhost:3001` | Comma-separated list of allowed CORS origins. |

## Rate Limiting

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_RATE_LIMIT_ENABLED` | boolean | `true` | Enable API rate limiting. |
| `DRYADE_RATE_LIMIT_DEFAULT_RPM` | integer | `300` | Default requests per minute. |

## Knowledge / RAG

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_KNOWLEDGE_CHUNK_SIZE` | integer | `1000` | Document chunk size for RAG indexing. |
| `DRYADE_KNOWLEDGE_CHUNK_OVERLAP` | integer | `200` | Overlap between chunks. |
| `DRYADE_KNOWLEDGE_TOP_K` | integer | `5` | Number of chunks to retrieve per query. |

## MCP (Model Context Protocol)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_MCP_CONFIG_PATH` | string | `config/mcp_servers.yaml` | Path to MCP server configuration file. |
| `DRYADE_MCP_SERVERS` | JSON string | `{}` | Inline MCP server configuration as JSON. |
| `DRYADE_MCP_TOOL_EMBEDDING_MODEL` | string | `all-MiniLM-L6-v2` | Sentence-transformer model for MCP tool routing. |

## Uploads & Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_UPLOAD_MAX_SIZE_MB` | float | `10.0` | Maximum upload file size in MB. |
| `DRYADE_UPLOAD_ALLOWED_TYPES` | string | `*` | Comma-separated allowed file types (or `*` for all). |
| `DRYADE_S3_BUCKET` | string | *(none)* | S3 bucket for file storage (optional). |
| `DRYADE_S3_REGION` | string | `us-east-1` | S3 region. |
| `DRYADE_S3_ENDPOINT` | string | *(none)* | Custom S3 endpoint for S3-compatible storage. |

## Observability

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_OTEL_ENABLED` | boolean | `false` | Enable OpenTelemetry tracing. |
| `DRYADE_OTEL_ENDPOINT` | string | *(none)* | OpenTelemetry collector endpoint. |
| `DRYADE_OTEL_SERVICE_NAME` | string | `dryade-api` | Service name for traces. |
| `DRYADE_COST_TRACKING_ENABLED` | boolean | `true` | Enable LLM cost tracking. |
| `DRYADE_COST_BUDGET_DAILY` | float | *(none)* | Daily cost budget limit (optional). |

## Concurrency & Performance

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DRYADE_MAX_CONCURRENT_LLM` | integer | `8` | Maximum concurrent LLM requests. |
| `DRYADE_MAX_QUEUE_SIZE` | integer | `20` | Request queue size. |
| `DRYADE_QUEUE_TIMEOUT_S` | float | `30.0` | Queue wait timeout in seconds. |
| `DRYADE_SEMANTIC_CACHE_ENABLED` | boolean | `true` | Enable semantic response caching. |
| `DRYADE_SEMANTIC_CACHE_TTL` | integer | `3600` | Cache TTL in seconds. |

## Example Configurations

### Minimal (PostgreSQL + Ollama)

```env
DRYADE_DATABASE_URL=postgresql+psycopg://dryade:dryade@localhost:5432/dryade
DRYADE_LLM_BASE_URL=http://localhost:11434/v1
DRYADE_LLM_MODEL=llama3.2
DRYADE_JWT_SECRET=your-secret-here-generate-with-openssl-rand-hex-32
```

### Production (PostgreSQL + vLLM)

```env
DRYADE_ENV=production
DRYADE_DATABASE_URL=postgresql+psycopg://dryade:strong_password@db:5432/dryade
DRYADE_DATABASE_SSL_MODE=require
DRYADE_LLM_MODE=vllm
DRYADE_LLM_BASE_URL=http://vllm:8000/v1
DRYADE_LLM_MODEL=local-llm
DRYADE_JWT_SECRET=<generate-with-openssl-rand-hex-32>
DRYADE_ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>
DRYADE_CORS_ORIGINS=https://your-domain.com
DRYADE_LOG_FORMAT=json
```

### Cloud Provider (PostgreSQL + OpenAI)

```env
DRYADE_ENV=production
DRYADE_DATABASE_URL=postgresql+psycopg://user:pass@db-host:5432/dryade
DRYADE_LLM_MODE=openai
DRYADE_LLM_BASE_URL=https://api.openai.com/v1
DRYADE_LLM_API_KEY=sk-your-openai-key
DRYADE_LLM_MODEL=gpt-4o
DRYADE_JWT_SECRET=<generate-with-openssl-rand-hex-32>
DRYADE_ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>
DRYADE_CORS_ORIGINS=https://your-domain.com
```
