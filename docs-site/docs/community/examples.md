---
title: Examples
description: Quickstart projects and example integrations for Dryade
sidebar_position: 4
---

# Examples

Get hands-on with Dryade through our curated quickstart projects. Each example is self-contained with its own Docker Compose file and step-by-step instructions.

## Available Examples

| Example | Difficulty | Time | What You'll Learn |
|---------|-----------|------|-------------------|
| **Chat Quickstart** | Beginner | 5 min | Connect an LLM and start chatting |
| **Agent Quickstart** | Intermediate | 10 min | Create an agent with tool calling |
| **MCP Server Quickstart** | Intermediate | 10 min | Connect external tools via MCP |

## Getting Started

1. Clone the repository
2. Navigate to the example you want to try
3. Follow the README instructions

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade/examples/quickstart-chat
cp .env.example .env
# Edit .env with your API key
docker compose up -d
```

**[Browse all examples on GitHub](https://github.com/DryadeAI/Dryade/tree/main/examples)**

## Submit Your Own Example

We welcome community-contributed examples. If you've built something interesting with Dryade, consider sharing it:

1. Read the [Contributing Guide](https://github.com/DryadeAI/Dryade/blob/main/CONTRIBUTING.md)
2. Create a self-contained directory under `examples/`
3. Include a README with prerequisites, steps, and expected output
4. Submit a pull request

Join [Discord](https://discord.gg/bvCPwqmu) if you'd like feedback on your example before submitting.
