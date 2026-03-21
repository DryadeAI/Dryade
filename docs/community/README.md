# Dryade Community Edition

Welcome to Dryade Community Edition - the source-available multi-agent orchestration platform.

## What is Dryade?

Dryade enables you to build, orchestrate, and deploy AI agent workflows. Connect multiple AI agents with tools via MCP (Model Context Protocol), create visual workflows, and integrate with your existing systems.

**Key Features:**
- Multi-framework agent support (CrewAI, LangChain, ADK, MCP, A2A)
- Visual workflow builder with React Flow
- MCP server integration for tool connectivity
- Plugin architecture for extensibility
- Real-time streaming and WebSocket support
- Knowledge base / RAG integration

## Quick Links

| Documentation | Description |
|---------------|-------------|
| [Quick Start](./QUICK-START.md) | Get running in 5 minutes |
| [Plugin Developer Guide](./PLUGIN-DEVELOPER-GUIDE.md) | Build custom plugins |
| [Architecture](./ARCHITECTURE.md) | System design overview |
| [API Reference](./API-REFERENCE.md) | REST API documentation |
| [MCP Servers](./MCP-SERVERS.md) | Available MCP integrations |
| [Troubleshooting](./TROUBLESHOOTING.md) | Common issues and solutions |

## Installation

### Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/dryade/dryade/main/scripts/install.sh | bash
```

### Docker

```bash
git clone https://github.com/dryade/dryade.git
cd dryade
cp .env.example .env
# Edit .env with your LLM API key
docker-compose -f docker-compose.community.yml up -d
```

### Manual Installation

See [Quick Start](./QUICK-START.md) for detailed instructions.

## Requirements

- Python 3.10+
- Node.js 18+ (for MCP servers)
- 4GB RAM minimum
- LLM API key (OpenAI, Anthropic, or compatible)

## Community Plugins

Dryade Community includes 15 plugins out of the box:

| Plugin | Description |
|--------|-------------|
| `document_processor` | Process and analyze documents |
| `flow_editor` | Visual workflow editing |
| `mcp` | MCP server integration |
| `skill_editor` | Custom skill management |
| `vllm` | vLLM model integration |
| `excel_analyst` | Excel/spreadsheet analysis |
| `kpi_monitor` | KPI dashboards |
| `replay` | Conversation replay |
| `checkpoint` | Workflow checkpoints |
| `message_hygiene` | Message cleaning |
| `conversation` | Conversation branching |
| `reactflow` | ReactFlow utilities |
| `debugger` | Workflow debugging |
| `project_manager` | Project/issue tracking |
| `clarify` | Clarification protocol |

## Support

- **GitHub Discussions**: [Ask questions, share ideas](https://github.com/dryade/dryade/discussions)
- **Issues**: [Report bugs](https://github.com/dryade/dryade/issues)
- **Discord**: [Real-time chat](https://discord.gg/bvCPwqmu)

## Enterprise Edition

Need advanced features? Dryade Enterprise includes:

- Additional plugins (audio processing, self-healing, compliance)
- SSO authentication (Zitadel, OIDC)
- Plugin Manager with signing and verification
- Priority support
- Custom development

Learn more: [https://dryade.ai/enterprise](https://dryade.ai/enterprise)

## Contributing

We welcome contributions! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

Dryade Community Edition is released under the [Sustainable Use License](../../LICENSE).

---

*Built with care by the Dryade team*
