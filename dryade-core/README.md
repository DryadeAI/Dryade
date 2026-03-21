# dryade-core

Multi-agent orchestration platform — core backend and reference agent implementations.

## Overview

`dryade-core` provides:

- **Core API** — FastAPI backend with agent orchestration, plugin system, auth, and observability
- **Reference Agents** — Five production-ready agent implementations demonstrating different framework integrations:
  - `devops_engineer` — MCP-native agent
  - `code_reviewer` — CrewAI-based agent
  - `database_analyst` — LangChain/LangGraph-based agent
  - `research_assistant` — LangChain with browser automation
  - `project_manager` — MCP-native agent

## Installation

```bash
pip install dryade-core
```

Or with optional dependencies:

```bash
pip install "dryade-core[otel]"    # OpenTelemetry support
pip install "dryade-core[mcp]"     # MCP protocol support
```

## Requirements

- Python 3.10–3.13
- PostgreSQL 14+
- Redis 7+
- Qdrant 1.7+ (for knowledge/RAG features)

## License

Licensed under the Dryade Source Use License (DSUL). See [LICENSE](LICENSE) for details.

Enterprise features are available under a commercial license. See [https://dryade.ai/pricing](https://dryade.ai/pricing).
