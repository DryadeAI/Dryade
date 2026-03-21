# Agent Quickstart

Create an AI agent with tool calling capabilities in Dryade.

## What You'll Learn

- How Dryade's agent system works
- How to create an agent with a specific persona and tools
- How tool routing connects agents to capabilities
- How to test an agent via the UI and API

## Prerequisites

- Docker and Docker Compose installed
- An LLM API key (OpenAI or Anthropic recommended for reliable tool calling)

## Steps

### 1. Configure your environment

```bash
cp .env.example .env
```

Edit `.env` and set your API key. Tool calling works best with:
- **OpenAI** (`gpt-4o` or newer)
- **Anthropic** (`claude-sonnet-4-20250514` or newer)

### 2. Review the agent configuration

This example includes `agent-config.json` -- a sample agent definition for a "Research Assistant" that can search the web:

```json
{
  "name": "Research Assistant",
  "description": "An agent that helps research topics using web search",
  "system_prompt": "You are a research assistant. Use your tools to find accurate, up-to-date information.",
  "mode": "orchestrate",
  "tools": ["web_search"]
}
```

Key fields:
- **name** -- Display name in the UI
- **description** -- What the agent does
- **system_prompt** -- Instructions that shape the agent's behavior
- **mode** -- `chat` (conversational), `planner` (structured reasoning), or `orchestrate` (autonomous multi-step)
- **tools** -- Which built-in tools the agent can use

### 3. Start the services

```bash
docker compose up -d
```

### 4. Create the agent

**Option A -- Via the UI:**

1. Open [http://localhost:3000](http://localhost:3000)
2. Navigate to **Agents** in the sidebar
3. Click **Create Agent**
4. Fill in the fields from `agent-config.json`
5. Save the agent

**Option B -- Via the API:**

```bash
curl -X POST http://localhost:8080/api/agents \
  -H "Content-Type: application/json" \
  -d @agent-config.json
```

### 5. Test the agent

1. Open the agent from the sidebar
2. Ask a research question: "What are the latest developments in quantum computing?"
3. Watch the agent use its tools to search and synthesize information

### Expected Result

The agent should:
- Receive your question
- Decide to use the web search tool
- Execute the search and process results
- Return a synthesized answer with sources

In `orchestrate` mode, you'll see the agent's reasoning steps as it works through the problem.

## How Tool Routing Works

Dryade uses a HierarchicalToolRouter that matches user requests to available tools:

1. **Semantic matching** -- Understands natural language intent
2. **Regex matching** -- Pattern-based tool selection for precise routing
3. **Tool capping** -- Limits concurrent tool calls based on model capability

The router automatically selects the right tool from all connected sources (built-in tools, MCP servers, plugins).

## Troubleshooting

**Agent not using tools:**
- Verify your LLM supports tool calling (GPT-4o, Claude Sonnet/Opus)
- Some local models have limited tool calling support

**"No tools available" error:**
- Check that the tools listed in agent config are valid
- View available tools at `http://localhost:8080/api/tools`

## What's Next

- Try the [MCP Server Quickstart](../quickstart-mcp/) to give agents access to external tools
- Read about [Agent Modes](https://dryade.ai/docs/using-dryade/agents) in the documentation
- Learn about [Workflow Builder](https://dryade.ai/docs/using-dryade/workflows) for multi-agent pipelines
- Join [Discord](https://discord.gg/bvCPwqmu) for help

## Cleanup

```bash
docker compose down        # Stop services
docker compose down -v     # Stop and remove data volumes
```

---

*Licensed under [DSUL](../../LICENSE)*
