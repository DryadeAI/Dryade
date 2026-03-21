# Troubleshooting Guide

Common issues and their solutions for Dryade Community Edition.

## Quick Diagnostics

Run the health check first:
```bash
./scripts/health-check.sh
```

## Installation Issues

### Python version error

**Problem**: `Python 3.10+ required`

**Solution**:
```bash
# Check your Python version
python3 --version

# Install Python 3.10+ (Ubuntu/Debian)
sudo apt update
sudo apt install python3.10 python3.10-venv

# Use pyenv (recommended)
pyenv install 3.10.13
pyenv local 3.10.13
```

### pip install fails

**Problem**: `error: externally-managed-environment`

**Solution**: Use a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### npm/Node.js not found

**Problem**: MCP servers require Node.js

**Solution**:
```bash
# Install Node.js (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install nodejs

# Or use nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 18
```

## Startup Issues

### API server won't start

**Problem**: `Address already in use`

**Solution**:
```bash
# Find what's using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
uvicorn core.api.main:app --port 8001
```

### Database errors on startup

**Problem**: `no such table: users`

**Solution**: Run migrations
```bash
alembic upgrade head
```

**Problem**: `database is locked`

**Solution**: SQLite lock issue
```bash
# Stop all Dryade processes
pkill -f uvicorn

# Remove lock file if exists
rm -f data/dryade.db-shm data/dryade.db-wal

# Restart
```

### LLM API key errors

**Problem**: `Invalid API key` or `Authentication failed`

**Solution**:
```bash
# Check your .env
grep LLM_API_KEY .env

# Verify the key works
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_KEY"
```

## Runtime Issues

### Agent not responding

**Problem**: Chat messages timeout or fail

**Checklist**:
1. Check LLM API key is valid
2. Check LLM provider is reachable
3. Check for rate limiting (429 errors)
4. Check logs: `docker logs dryade-api`

### MCP server not connecting

**Problem**: Tools not available for agents

**Solution**:
```bash
# Check if server is enabled
grep -A5 "filesystem:" config/mcp_servers.community.yaml

# Check server status
curl http://localhost:8000/api/mcp/servers

# Restart MCP servers
curl -X POST http://localhost:8000/api/mcp/restart
```

### Plugin not loading

**Problem**: Plugin doesn't appear in UI

**Checklist**:
1. Validate plugin: `dryade validate-plugin plugins/my-plugin`
2. Check dryade.json exists and is valid JSON
3. Check plugin.py has no syntax errors
4. Check logs for import errors

### Slow responses

**Problem**: Chat or workflow execution is slow

**Possible causes**:
1. **LLM latency**: Check provider status page
2. **Database**: Consider PostgreSQL for production
3. **Memory**: Check `free -h`, increase RAM
4. **MCP servers**: Reduce enabled servers

## Docker Issues

### Container won't start

**Problem**: `docker-compose up` fails

**Solution**:
```bash
# Check Docker is running
docker info

# Check compose file syntax
docker-compose -f docker-compose.community.yml config

# Pull latest images
docker-compose pull

# Start with logs
docker-compose up --build
```

### Can't connect to container

**Problem**: `Connection refused` to localhost:8000

**Solution**:
```bash
# Check container is running
docker ps

# Check container logs
docker logs dryade-api

# Check port mapping
docker port dryade-api
```

### Disk space issues

**Problem**: `no space left on device`

**Solution**:
```bash
# Clean Docker
docker system prune -a

# Clean old images
docker image prune -a
```

## Frontend Issues

### UI not loading

**Problem**: Blank page at localhost:3000

**Solution**:
```bash
# Check frontend is running
docker logs dryade-frontend

# Check API URL
# In docker-compose, ensure VITE_API_URL points to API
```

### WebSocket disconnects

**Problem**: Real-time updates stop working

**Checklist**:
1. Check for proxy issues (nginx config)
2. Check WebSocket endpoint is accessible
3. Check browser console for errors

## Getting More Help

### Collect Debug Info

```bash
# System info
uname -a
python3 --version
node --version

# Dryade version
cat pyproject.toml | grep version

# Health check output
./scripts/health-check.sh

# Recent logs
docker logs --tail 100 dryade-api
```

### Where to Ask

1. **GitHub Discussions**: Best for general questions
2. **GitHub Issues**: For bugs with reproduction steps
3. **Discord**: Real-time help (coming soon)

### Filing a Bug Report

Include:
- Dryade version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs
- Screenshots if UI issue
