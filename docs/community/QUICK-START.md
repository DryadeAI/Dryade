# Quick Start Guide

Get Dryade running in under 5 minutes.

## Prerequisites

- Python 3.10 or higher
- An LLM API key (OpenAI, Anthropic, or compatible)

## Option 1: One-Line Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/dryade/dryade/main/scripts/install.sh | bash
```

The installer will:
1. Check system requirements
2. Ask for your LLM API key
3. Set up the database
4. Start Dryade

After installation, Dryade will be running at http://localhost:8000

## Option 2: Docker Install

```bash
# Clone the repository
git clone https://github.com/dryade/dryade.git
cd dryade

# Configure
cp .env.example .env
nano .env  # Add your LLM_API_KEY

# Start
docker-compose -f docker-compose.community.yml up -d
```

This starts:
- **API Server**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **PostgreSQL**: localhost:5432 (internal)

## Option 3: Manual Install

For development or custom setups:

```bash
# Clone
git clone https://github.com/dryade/dryade.git
cd dryade

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Add your LLM_API_KEY

# Initialize database
alembic upgrade head

# Start
uvicorn core.api.main:app --host 0.0.0.0 --port 8000
```

## Verify Installation

```bash
# Check health
curl http://localhost:8000/health

# Or use the health check script
./scripts/health-check.sh
```

Expected output:
```json
{"status": "healthy", "version": "1.0.0"}
```

## Access the UI

Open your browser to:
- **API Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:3000 (if running with Docker)

## Your First Agent Chat

1. Open the Dryade UI at http://localhost:3000
2. Click "New Chat"
3. Type a message and send
4. The agent will respond using your configured LLM

## Your First Workflow

1. Go to "Workflows" in the sidebar
2. Click "Create Workflow"
3. Add nodes by dragging from the palette
4. Connect nodes by dragging from output to input
5. Click "Run" to execute

## Enable MCP Servers

MCP servers provide tools for agents. Enable them in your config:

```bash
nano config/mcp_servers.community.yaml
```

Set `enabled: true` for servers you want. For servers requiring credentials (GitHub, Linear), add your API keys to `.env`.

### Available MCP Servers

| Server | Purpose | Credentials Required |
|--------|---------|---------------------|
| `filesystem` | File operations | No |
| `git` | Git operations | No |
| `memory` | Memory storage | No |
| `playwright` | Browser automation | No |
| `pdf-reader` | PDF parsing | No |
| `github` | GitHub API | Yes (GITHUB_TOKEN) |
| `linear` | Linear integration | Yes (LINEAR_API_KEY) |

## Environment Variables

Key environment variables in `.env`:

```bash
# Required
LLM_API_KEY=your-api-key-here

# Optional (defaults shown)
LLM_PROVIDER=openai           # openai, anthropic, ollama
LLM_MODEL=gpt-4               # Model to use
DATABASE_URL=postgresql+psycopg://dryade:dryade@localhost:5432/dryade
LOG_LEVEL=INFO
```

## Next Steps

- [Plugin Developer Guide](./PLUGIN-DEVELOPER-GUIDE.md) - Build custom plugins
- [API Reference](./API-REFERENCE.md) - Explore the REST API
- [MCP Servers](./MCP-SERVERS.md) - Available tool integrations
- [Architecture](./ARCHITECTURE.md) - Understand the system design

## Troubleshooting

### "Connection refused" error

Ensure Dryade is running:
```bash
docker ps  # For Docker
# or
ps aux | grep uvicorn  # For manual install
```

### "LLM API key invalid" error

Check your `.env` file has the correct key:
```bash
grep LLM_API_KEY .env
```

### Database errors

Reset and reinitialize:
```bash
rm data/dryade.db
alembic upgrade head
```

### Port already in use

Change the port:
```bash
uvicorn core.api.main:app --host 0.0.0.0 --port 8001
```

For more issues, see [Troubleshooting](./TROUBLESHOOTING.md).

---

*Last updated: 2026-02-05*
*Dryade Community Edition*
