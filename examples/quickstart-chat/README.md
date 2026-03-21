# Chat Quickstart

Get Dryade running and chat with an LLM in under 5 minutes.

## What You'll Learn

- How to start Dryade with Docker Compose
- How to configure an LLM provider (OpenAI, Anthropic, or Ollama)
- How to use the chat interface for conversations

## Prerequisites

- Docker and Docker Compose installed
- An LLM API key **or** Ollama running locally (free)

## Steps

### 1. Configure your environment

```bash
cp .env.example .env
```

Edit `.env` and set your LLM provider. Choose one:

**Option A -- OpenAI:**
```env
OPENAI_API_KEY=sk-your-key-here
```

**Option B -- Anthropic:**
```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Option C -- Ollama (free, local):**
```env
OLLAMA_HOST=http://host.docker.internal:11434
```

Make sure Ollama is running on your host machine (`ollama serve`). No API key needed.

### 2. Start the services

```bash
docker compose up -d
```

This starts three containers:
- **PostgreSQL** -- database for conversations and settings
- **Dryade backend** -- the API server
- **Dryade frontend** -- the web interface

Wait about 30 seconds for everything to initialize.

### 3. Open the UI

Navigate to [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Start chatting

1. You'll see the Dryade chat interface
2. If using OpenAI or Anthropic, your models are auto-detected from the API key
3. If using Ollama, go to **Settings > LLM Providers** and add your Ollama endpoint
4. Type a message and press Enter -- you're chatting with your LLM

### Expected Result

You should see a responsive chat interface where you can:
- Send messages and receive streamed responses
- Switch between different LLM models
- Create multiple conversations
- View conversation history

## Troubleshooting

**"Connection refused" error:**
- Make sure Docker is running: `docker compose ps`
- Wait for health checks to pass: `docker compose logs dryade`

**Ollama not connecting:**
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- On Linux, use `http://172.17.0.1:11434` instead of `host.docker.internal`

**No models showing:**
- Check your API key is correct in `.env`
- Restart the backend: `docker compose restart dryade`

## What's Next

- Try the [Agent Quickstart](../quickstart-agent/) to create agents with tool calling
- Try the [MCP Server Quickstart](../quickstart-mcp/) to connect external tools
- Read the [Configuration Guide](https://dryade.ai/docs/getting-started/quick-start) for all options
- Join [Discord](https://discord.gg/bvCPwqmu) for help

## Cleanup

```bash
docker compose down        # Stop services
docker compose down -v     # Stop and remove data volumes
```

---

*Licensed under [DSUL](../../LICENSE)*
