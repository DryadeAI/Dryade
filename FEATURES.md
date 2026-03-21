# Dryade Features

Dryade is a source-available AI orchestration platform. The core platform is free to use under the [Dryade Source Use License (DSUL)](LICENSE), with extended features available via the [Dryade marketplace](https://dryade.ai/marketplace).

> **Source-Available Model**: All source code is visible and auditable. The Community platform is fully functional for development and evaluation. Extended plugins add advanced capabilities for teams and organizations.

## Platform Capabilities

### Core Platform (Community)

Everything you need to get started with AI orchestration:

| Category | Feature | Description |
|----------|---------|-------------|
| **Orchestration** | Multi-Agent Router | Unified adapter pattern for multi-agent workflows |
| | ReAct Orchestrator | 3 modes: Chat, Planner, Orchestrate |
| | CrewAI Adapter | Multi-agent crew orchestration |
| | LangChain Adapter | LangChain tool and chain execution |
| | ADK Adapter | Google Agent Development Kit integration |
| | A2A Protocol | Agent-to-Agent inter-agent communication |
| **Workflow** | Visual Workflow Builder | ReactFlow drag-and-drop pipeline editor |
| | Flow Editor | Code-level workflow editing |
| | MCP Integration | Model Context Protocol server connectivity |
| | Plan Templates | Reusable workflow templates |
| | Workflow Execution | End-to-end automated execution |
| **Developer Experience** | Checkpoint/Resume | Save and resume agent execution state |
| | Conversation Management | Full conversation history and management |
| | Debugger | Inspect agent reasoning and tool calls |
| | Replay | Replay past conversations and executions |
| | Message Hygiene | Automatic message cleaning and formatting |
| | Clarification Workflow | Agent-driven clarification requests |
| **Local AI** | vLLM Integration | High-throughput local inference server |
| | Ollama Integration | Easy local model deployment |
| | Any OpenAI-Compatible API | Works with any provider following the OpenAI spec |
| **Infrastructure** | REST API | Full REST API with OpenAPI documentation |
| | WebSocket Streaming | Real-time streaming with guaranteed delivery |
| | Database Persistence | SQLite (dev) or PostgreSQL (production) |
| | Standalone Auth (JWT) | Built-in authentication and authorization |
| | Plugin System | Extensible architecture via plugins |

### Extended Features (via Marketplace)

Access additional features and agents via the Dryade marketplace. Extended plugins cover:

| Category | Examples |
|----------|----------|
| **Performance** | Semantic caching, cost tracking and analytics |
| **Security** | Input/output safety validation, sandbox execution, file safety (malware detection), SSO integration |
| **Reliability** | Self-healing with circuit breakers, error escalation, automatic retry |
| **AI Customization** | Model fine-tuning, synthetic data generation, advanced tool-call routing |
| **Business Workflows** | Document processing, Excel analysis, advanced RAG, customer support, DevOps/SRE, HR recruiting, marketing, project management, real estate, healthcare, finance, legal review |
| **Enterprise** | Compliance auditing, enterprise search, KPI monitoring, air-gapped deployment |
| **Support** | Email support, priority support, custom SLA |

See [dryade.ai/pricing](https://dryade.ai/pricing) for full details on available plans.

### Build Your Own

Create your own plugins and sell them on the Dryade marketplace. See the [Plugin Development Guide](docs/plugins.md) for getting started.

## Getting Started

1. **Community users**: Clone the repository and follow the [Quick Start](README.md#quick-start)
2. **Extended features**: Visit [dryade.ai/pricing](https://dryade.ai/pricing) to explore available plans
3. **Enterprise**: Contact [enterprise@dryade.ai](mailto:enterprise@dryade.ai) for custom deployment discussions

## More Information

- [README](README.md) -- Quick start and overview
- [LICENSE](LICENSE) -- Dryade Source Use License (DSUL)
- [LICENSE_EE.md](LICENSE_EE.md) -- Enterprise feature license
- [CONTRIBUTING.md](CONTRIBUTING.md) -- Contribution guidelines
- [CLA.md](CLA.md) -- Contributor License Agreement
