---
title: Troubleshooting
sidebar_position: 4
---

# Troubleshooting

Common issues and their solutions when running Dryade. For each issue: symptom, cause, and fix.

## Quick Diagnostics

Before diving into specific issues, run the health check:

```bash
./scripts/health-check.sh
```

This checks database connectivity, API server status, and LLM provider reachability.

---

## LLM Provider Connection Issues

### Symptom

Chat messages fail with "Provider error" or "Authentication failed". The agent does not respond.

### Cause

The LLM API key is missing, invalid, or the provider endpoint is unreachable.

### Fix

1. **Verify your API key:**

```bash
# Check your .env file
grep -E "OPENAI_API_KEY|ANTHROPIC_API_KEY" .env
```

2. **Test the key directly:**

```bash
# OpenAI
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_KEY"

# Anthropic
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: YOUR_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}'
```

3. **Check for rate limiting:** If you see 429 errors in the logs, you have hit the provider's rate limit. Wait and retry, or configure a fallback provider in Settings.

4. **For local models (vLLM):** Ensure the vLLM server is running and the endpoint URL in Settings matches:

```bash
curl http://localhost:8000/v1/models
```

---

## WebSocket Connection Drops

### Symptom

Real-time chat updates stop mid-response. The UI shows a disconnection indicator or responses appear incomplete.

### Cause

A reverse proxy (Nginx, Caddy) is closing the WebSocket connection due to an idle timeout.

### Fix

**Nginx:** Add WebSocket upgrade headers and increase the timeout:

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

**Caddy:** WebSocket support is automatic. Ensure you are not setting a short `read_timeout` in your Caddyfile.

**Without a proxy:** If connecting directly to the Dryade API server, check that your client implements reconnection logic. See the [WebSocket Streaming](/developer-guide/websocket) guide for a reconnection strategy.

---

## Plugin Not Loading

### Symptom

A plugin does not appear in the sidebar or its API endpoints return 404.

### Cause

The plugin may not be in the active catalog for your license tier, or it has a manifest issue.

### Fix

1. **Check the plugin list:**

```bash
curl http://localhost:8000/api/plugins
```

2. **Validate the manifest:**

```bash
dryade validate-plugin plugins/my_plugin --verbose
```

3. **For custom plugins**, push a development allowlist to enable them:

```bash
dryade-pm push --plugins-dir plugins/
```

4. **Check logs** for loading errors:

```bash
docker logs dryade-api 2>&1 | grep -i plugin
```

Common manifest issues:
- Missing required fields in `dryade.json`
- `has_ui: true` but no compiled `ui/dist/bundle.js`
- Plugin requires a higher tier than your license provides

---

## Docker Memory Issues

### Symptom

Containers crash with `Killed` or `OOMKilled` status. The system becomes unresponsive.

### Cause

Docker memory limits are too low for the workload, especially when running local LLM models alongside Dryade.

### Fix

1. **Check container memory usage:**

```bash
docker stats --no-stream
```

2. **Increase memory limits** in `docker-compose.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 4G
```

3. **For local LLM models:** Allocate at least 8GB of RAM for the model server. If running both the model and Dryade on the same machine, ensure you have at least 16GB total available.

4. **Reduce enabled MCP servers** if memory is constrained. Each MCP server process consumes additional memory.

---

## Database Migration Errors

### Symptom

Startup fails with "no such table" or "relation does not exist". The API returns 500 errors.

### Cause

Database migrations have not been applied, or the database schema is out of date.

### Fix

1. **Run pending migrations:**

```bash
alembic upgrade head
```

2. **Check migration status:**

```bash
alembic current
alembic history --verbose | head -20
```

3. **For SQLite "database is locked" errors:**

```bash
# Stop all Dryade processes
pkill -f uvicorn

# Remove WAL lock files
rm -f data/dryade.db-shm data/dryade.db-wal

# Restart
```

4. **For PostgreSQL connection errors:** Verify the `DATABASE_URL` in `.env` is correct and the PostgreSQL server is running.

---

## Frontend Not Loading

### Symptom

Blank page when opening the Dryade UI in the browser.

### Fix

1. **Check the frontend container is running:**

```bash
docker logs dryade-frontend
```

2. **Verify the API URL** in the frontend configuration matches the backend:

```bash
# In docker-compose, check VITE_API_URL
grep VITE_API_URL docker-compose.yml
```

3. **Clear browser cache** -- stale assets can cause blank pages after an update.

4. **Check browser console** (F12 > Console) for JavaScript errors.

---

## Startup: Address Already in Use

### Symptom

The API server fails to start with `Address already in use` error.

### Fix

```bash
# Find what is using the port
lsof -i :8000

# Stop the conflicting process
kill <PID>

# Or start Dryade on a different port
uvicorn core.api.main:app --port 8001
```

---

## Getting More Help

### Collect Debug Information

Before filing a bug report, gather:

```bash
# System info
uname -a
python3 --version
node --version
docker --version

# Dryade version
grep version pyproject.toml | head -1

# Health check
./scripts/health-check.sh

# Recent logs
docker logs --tail 100 dryade-api
```

### Where to Ask

- **GitHub Issues**: [github.com/DryadeAI/Dryade/issues](https://github.com/DryadeAI/Dryade/issues) -- for bugs with reproduction steps
- **GitHub Discussions**: [github.com/DryadeAI/Dryade/discussions](https://github.com/DryadeAI/Dryade/discussions) -- for questions and general help

### Filing a Bug Report

Include:
- Dryade version
- Operating system and architecture
- Steps to reproduce the issue
- Expected vs actual behavior
- Relevant log output
- Screenshots (if it is a UI issue)
