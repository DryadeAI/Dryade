# Agent Frameworks in Dryade

Dryade supports multiple AI agent frameworks through a unified adapter pattern. Instead of locking you into one framework, Dryade lets you connect any supported framework and the orchestrator routes tools and manages execution across all of them.

This means you can use CrewAI for multi-agent crews, LangChain for chain-based workflows, Google ADK for Google ecosystem integration, and MCP servers for standardized tool access -- all in the same deployment, managed by a single orchestrator.

---

## Supported Frameworks

| Framework | Adapter | Status | Use Case |
|-----------|---------|--------|----------|
| **CrewAI** | `CrewAIAdapter` | Supported | Multi-agent crews with role-based agents |
| **Google ADK** | `ADKAdapter` | Supported | Google AI ecosystem integration |
| **LangChain** | `LangChainAdapter` | Supported | Chain-based workflows with extensive tool library |
| **A2A** (Agent-to-Agent) | `A2AAdapter` | Supported | Inter-agent communication protocol |
| **MCP** (Model Context Protocol) | `MCPAgentAdapter` | Supported | Standardized tool server integration |

All adapters conform to the same interface, so the orchestrator treats them uniformly regardless of the underlying framework.

---

## How Agents Work in Dryade

The DryadeOrchestrator operates in three modes: **chat** for conversational interaction, **planner** for structured task decomposition, and **orchestrate** for full multi-step execution. In orchestrate mode, the orchestrator breaks complex requests into steps and routes each to the best available tool across all connected servers and frameworks.

Tool discovery and routing is handled by the HierarchicalToolRouter, which performs semantic and regex matching to find the right tool regardless of which framework or MCP server provides it. For per-server resolution, the MCP adapter uses three-tier matching: exact name match, substring containment, and verb-based inference. This means tools are found by what they do, not where they live.

Tools from different frameworks can be composed in a single workflow. A CrewAI agent can trigger a tool hosted on an MCP server, which produces output consumed by a LangChain chain -- all within the same orchestration run. The adapter pattern abstracts framework differences so the orchestrator focuses on capability, not implementation.

---

## Quick Examples

### CrewAI -- Multi-Agent Crew

```python
# Define a crew with specialized agents
crew_config = {
    "agents": [
        {"role": "researcher", "tools": ["web_search", "summarize"]},
        {"role": "writer", "tools": ["draft", "edit"]}
    ],
    "task": "Research and write a report on AI orchestration trends"
}
```

### MCP -- Tool Server Connection

```json
{
    "mcp_servers": [
        {
            "name": "filesystem",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]
        },
        {
            "name": "github",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": "ghp_..."}
        }
    ]
}
```

### Google ADK -- Google Ecosystem

```python
# Connect Google ADK agents with Google-native tools
adk_config = {
    "framework": "adk",
    "tools": ["google_search", "google_docs", "vertex_ai"],
    "model": "gemini-2.0-flash"
}
```

### LangChain -- Chain Workflows

```python
# LangChain tools are auto-discovered and routed
langchain_config = {
    "framework": "langchain",
    "tools": ["serpapi", "calculator", "python_repl"],
    "chain_type": "sequential"
}
```

### A2A -- Agent-to-Agent Communication

```python
# A2A enables inter-agent message passing
a2a_config = {
    "framework": "a2a",
    "agents": ["analysis-agent", "reporting-agent"],
    "protocol": "request-response"
}
```

---

## LLM Provider Support

Dryade works with any LLM provider through a unified interface:

| Provider | Configuration | Local/Cloud |
|----------|--------------|-------------|
| **OpenAI** | API key | Cloud |
| **Anthropic** | API key | Cloud |
| **Google** (Gemini) | API key | Cloud |
| **vLLM** | Base URL | Local |
| **Ollama** | Base URL | Local |
| **Any OpenAI-compatible API** | Base URL + API key | Either |

Local model inference with vLLM supports GPU acceleration and runs entirely on your hardware -- no data leaves your infrastructure.

---

## Learn More

- **Full agent documentation:** [dryade.ai/docs/agents](https://dryade.ai/docs/agents)
- **MCP integration guide:** [dryade.ai/docs/mcp](https://dryade.ai/docs/mcp)
- **Self-hosting guide:** [SELF_HOSTING.md](SELF_HOSTING.md)
- **Contributing adapters:** [CONTRIBUTING.md](CONTRIBUTING.md)
