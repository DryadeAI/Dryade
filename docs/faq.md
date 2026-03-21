---
title: FAQ
sidebar_position: 9
description: Frequently asked questions about Dryade
---

# Frequently Asked Questions

## General

### What is Dryade?

Dryade is a self-hosted AI orchestration platform. It connects to any LLM (local or cloud), routes tool calls through MCP (Model Context Protocol) servers, and manages multi-step agent workflows -- all while keeping your data on your own infrastructure.

### What LLM providers does Dryade support?

Dryade works with any provider that exposes an OpenAI-compatible API:

- **Ollama** -- Free, local, easy to set up (recommended for getting started)
- **vLLM** -- High-performance local inference with GPU acceleration
- **OpenAI** -- GPT-4o, GPT-4, etc. via API key
- **Anthropic** -- Claude models (via OpenAI-compatible proxy)
- **LiteLLM** -- Unified proxy for 100+ providers
- **Any OpenAI-compatible endpoint** -- Just set the base URL

### Is Dryade free?

The core platform is free for development and personal use. Production deployments and premium features (plugins, integrations) require a license. See the [LICENSE](https://github.com/DryadeAI/Dryade/blob/main/LICENSE) file for full terms.

### Can I self-host Dryade?

Yes -- self-hosting is the primary use case. Dryade is designed to run entirely on your infrastructure, from a laptop to a data center. See the [Deployment Guide](deployment.md) to get started.

## Hardware & Requirements

### What hardware do I need to run Dryade?

**Minimum (cloud LLM providers):**
- 2 CPU cores
- 4 GB RAM
- 10 GB storage

**Recommended (local LLM with GPU):**
- 4 CPU cores
- 16 GB RAM
- NVIDIA GPU with 16+ GB VRAM (for 8B parameter models)
- 50 GB storage

**For large models (70B+):**
- NVIDIA GPU with 48+ GB VRAM, or
- NVIDIA DGX Spark with 128 GB unified memory

See the [Edge Hardware Guide](edge-hardware.md) for detailed hardware recommendations.

### Can I run Dryade without a GPU?

Yes. Use a cloud LLM provider (OpenAI, Anthropic, etc.) or Ollama with small CPU-compatible models. GPU is only needed for local high-performance inference with vLLM.

### Does Dryade run on ARM / Apple Silicon / Jetson?

The Dryade backend runs on any platform with Python 3.12+ and Docker. For GPU-accelerated local LLMs on ARM:
- **NVIDIA Jetson** -- Fully supported with vLLM. See [Edge Hardware Guide](edge-hardware.md).
- **Apple Silicon** -- Use Ollama for local models (Metal acceleration). vLLM does not support Apple GPUs.
- **ARM Linux** -- Backend works natively. Use Ollama or a cloud provider for LLM.

## Data & Privacy

### Is my data sent to any third party?

Only if you configure a cloud LLM provider (e.g., OpenAI, Anthropic). Your prompts and responses go through their API. When using local models (Ollama, vLLM), all data stays on your hardware -- nothing leaves your network.

### Where is data stored?

All data is stored in your PostgreSQL (or SQLite) database:
- Conversations and messages
- Agent configurations
- Knowledge base documents and embeddings
- User accounts and settings

Files are stored on the local filesystem or in S3-compatible storage if configured.

### Can I delete all my data?

Yes. For SQLite, delete the database file. For PostgreSQL, drop the database. All uploaded files are stored in the configured upload directory and can be deleted directly.

## Plugins

### How do I add plugins?

Plugins are available through the [Dryade Marketplace](https://dryade.ai). Choose a subscription plan that includes the plugins you need, and follow the installation instructions.

### Can I create and sell my own plugins?

Yes. Dryade has an open plugin architecture. Create a plugin with a manifest, Python backend, and optional UI -- then submit it to the marketplace. See the [Plugin Guide](plugins.md) for development details and the [Developer Agreement](https://dryade.ai/legal/developer-agreement) for publishing terms.

### What is the difference between community and paid tiers?

- **Community (free):** Full core platform -- chat, agents, workflows, knowledge base, MCP integration, project management
- **Starter / Team / Enterprise:** Additional plugins and integrations available via the marketplace

The core platform is fully functional without plugins. Plugins add specialized features on top (analytics, compliance, integrations, etc.).

## Configuration

### How do I change the LLM provider?

Update these environment variables in your `.env` file:

```env
DRYADE_LLM_MODE=ollama       # or: vllm, openai, anthropic, litellm
DRYADE_LLM_BASE_URL=http://localhost:11434/v1
DRYADE_LLM_MODEL=llama3.2
DRYADE_LLM_API_KEY=           # Only needed for cloud providers
```

You can also configure providers in the UI at **Settings > Models** without restarting.

### How do I connect MCP servers?

Create or edit `config/mcp_servers.yaml`:

```yaml
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
```

Restart Dryade to discover the new tools. See the [Architecture Overview](architecture.md#mcp-integration) for details.

### How do I enable GPU support in Docker?

Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html), then use the GPU profile:

```bash
docker compose --profile gpu up -d
```

See the [Edge Hardware Guide](edge-hardware.md) for detailed GPU setup instructions.

## Troubleshooting

### The frontend shows a blank page

Check that `VITE_API_URL` in the frontend environment matches the backend URL. Verify the backend is accessible at `http://localhost:8080/health`. See the [Troubleshooting Guide](troubleshooting.md#frontend-shows-blank-page) for more solutions.

### Docker Compose fails to start

Check Docker version (24+ required), port conflicts on 3000/8080/5432, and that `DRYADE_JWT_SECRET` is set in `.env`. See the [Troubleshooting Guide](troubleshooting.md#docker-compose-fails-to-start) for step-by-step diagnosis.

### Where can I get help?

- **GitHub Issues:** [github.com/DryadeAI/Dryade/issues](https://github.com/DryadeAI/Dryade/issues) for bug reports
- **GitHub Discussions:** [github.com/DryadeAI/Dryade/discussions](https://github.com/DryadeAI/Dryade/discussions) for questions and ideas
- **Discord:** Join our community for real-time help and discussion
