# Dryade Examples

Quickstart projects to get you running with Dryade in minutes. Each example is self-contained with its own Docker Compose file and step-by-step instructions.

## Available Examples

| Example | Difficulty | Time | What You'll Learn |
|---------|-----------|------|-------------------|
| [Chat Quickstart](quickstart-chat/) | Beginner | 5 min | Connect an LLM and start chatting |
| [Agent Quickstart](quickstart-agent/) | Intermediate | 10 min | Create an agent with tool calling |
| [MCP Server Quickstart](quickstart-mcp/) | Intermediate | 10 min | Connect external tools via MCP |

## Prerequisites

- **Docker** and **Docker Compose** installed ([Get Docker](https://docs.docker.com/get-docker/))
- An LLM provider -- choose one:
  - **OpenAI API key** ([Get one](https://platform.openai.com/api-keys))
  - **Anthropic API key** ([Get one](https://console.anthropic.com/))
  - **Ollama** running locally ([Install Ollama](https://ollama.ai/)) -- free, no API key needed
  - **vLLM** with a local GPU -- see [Edge Hardware Guide](https://dryade.ai/docs/edge-hardware)

## Quick Start

Pick any example and follow its README:

```bash
cd quickstart-chat    # or quickstart-agent, quickstart-mcp
cp .env.example .env
# Edit .env with your API key (or use Ollama for free local inference)
docker compose up -d
```

Open [http://localhost:3000](http://localhost:3000) and you're ready.

## Project Structure

Each example contains:

```
quickstart-*/
  README.md            # Step-by-step guide
  docker-compose.yml   # Services configuration
  .env.example         # Environment template
  *.json / *.yaml      # Example-specific configs (where applicable)
```

## Next Steps

- Read the full [Documentation](https://dryade.ai/docs)
- Join [Discord](https://discord.gg/bvCPwqmu) for help and discussion
- See the [Contributing Guide](../CONTRIBUTING.md) to add your own examples
- Browse the main [README](../README.md) for a platform overview

---

*Licensed under [DSUL](../LICENSE)*
