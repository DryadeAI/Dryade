---
title: Getting Started
sidebar_position: 1
description: Get Dryade running in under 5 minutes with Docker Compose
---

# Getting Started

Get Dryade running locally in three steps. You will need [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade
```

### 2. Configure your environment

```bash
cp .env.example .env
```

Open `.env` and set your JWT secret (required):

```bash
# Generate a secure JWT secret
export DRYADE_JWT_SECRET=$(openssl rand -hex 32)
# Add it to .env
echo "DRYADE_JWT_SECRET=$DRYADE_JWT_SECRET" >> .env
```

### 3. Start Dryade

```bash
docker compose up -d
```

This starts the backend (FastAPI), frontend (React), and PostgreSQL database.

Once running, open [http://localhost:3000](http://localhost:3000) in your browser.

## First Steps

1. **Register an account** -- Click "Register" and create your admin account (the first user becomes admin automatically).

2. **Configure an LLM provider** -- Go to **Settings > Models** and configure at least one provider:

   | Provider | Setup | Best For |
   |----------|-------|----------|
   | **Ollama** | Install [Ollama](https://ollama.ai), run `ollama pull llama3.2` | Free, local, getting started |
   | **vLLM** | Requires NVIDIA GPU. See [Edge Hardware Guide](edge-hardware.md) | Performance, large models |
   | **OpenAI** | Add your API key in Settings | Cloud, no GPU needed |
   | **Anthropic** | Add your API key in Settings | Cloud, no GPU needed |
   | **Any OpenAI-compatible API** | Set the base URL and API key | Custom providers |

3. **Send your first message** -- Navigate to **Chat**, select your model, and start a conversation.

4. **Try an agent** -- Go to **Agents**, pick one of the built-in agents, and let Dryade orchestrate a multi-step task for you.

## Using Ollama (Recommended for Getting Started)

If you do not have a GPU or cloud API key, [Ollama](https://ollama.ai) is the fastest way to get started:

```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.2

# Ollama runs on http://localhost:11434 by default
```

In your `.env`, set:

```env
DRYADE_LLM_MODE=ollama
DRYADE_LLM_BASE_URL=http://host.docker.internal:11434/v1
DRYADE_LLM_MODEL=llama3.2
```

> **Note:** Use `host.docker.internal` instead of `localhost` so the Docker container can reach Ollama running on your host machine.

## What's Next

- [Configuration Reference](configuration.md) -- All environment variables and their defaults
- [Deployment Guide](deployment.md) -- Production deployment with PostgreSQL, TLS, and reverse proxy
- [Architecture Overview](architecture.md) -- How Dryade works under the hood
- [Edge Hardware Guide](edge-hardware.md) -- Run large models on NVIDIA Jetson or DGX Spark
