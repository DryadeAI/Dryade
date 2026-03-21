---
title: Installation
sidebar_position: 2
---

# Installation

Set up Dryade on your machine or server. Choose the method that best fits your workflow.

## Prerequisites

Before installing Dryade, make sure you have the following:

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.11 or higher | 3.12+ recommended |
| **Node.js** | 20 or higher | Required for the frontend and MCP servers |
| **Docker** | 24+ (optional) | Recommended for the simplest setup |
| **Git** | Any recent version | For cloning the repository |

You will also need at least one LLM provider API key (OpenAI, Anthropic, or a local model endpoint). You can configure this during the [onboarding wizard](/getting-started/onboarding-guide) after installation.

## Docker Installation (Recommended)

Docker is the fastest way to get Dryade running. It handles all dependencies and database setup automatically.

**1. Clone the repository**

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade
```

**2. Configure environment variables**

```bash
cp .env.example .env
```

Open `.env` in your editor and set the required variables:

```bash
# Authentication (required)
DRYADE_AUTH_ENABLED=true
DRYADE_JWT_SECRET=your-secure-random-string-here

# LLM Provider (configure at least one)
OPENAI_API_KEY=sk-...         # For OpenAI models
ANTHROPIC_API_KEY=sk-ant-...  # For Anthropic models
```

:::tip
You can skip the API key configuration here and set it through the onboarding wizard instead. The wizard will guide you through provider selection and key validation.
:::

**3. Start Dryade**

```bash
docker-compose up -d
```

This starts the following services:

| Service | URL | Description |
|---------|-----|-------------|
| **API Server** | `http://localhost:8000` | Backend API |
| **Workbench** | `http://localhost:3000` | Frontend UI |
| **PostgreSQL** | `localhost:5432` | Database (internal) |

**4. Verify the installation**

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "healthy", "version": "1.0.0"}
```

Open your browser to **http://localhost:3000** to access the Dryade Workbench.

## Manual Installation

For development or custom deployments, you can install Dryade directly on your system.

**1. Clone the repository**

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade
```

**2. Set up the Python backend**

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**3. Set up the frontend**

```bash
cd dryade-workbench
npm install
npm run build
cd ..
```

**4. Configure environment**

```bash
cp .env.example .env
```

Edit `.env` to set your configuration (see [Environment Variables](#environment-variables) below).

**5. Initialize the database**

```bash
alembic upgrade head
```

This creates the SQLite database by default. For PostgreSQL, set `DATABASE_URL` in your `.env` file before running migrations.

**6. Start the backend**

```bash
uvicorn core.api.main:app --host 0.0.0.0 --port 8000
```

**7. Start the frontend** (in a separate terminal)

```bash
cd dryade-workbench
npm run dev
```

The Workbench will be available at **http://localhost:3000**.

## Environment Variables

These are the key environment variables you can configure in `.env`:

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DRYADE_JWT_SECRET` | Secret key for JWT token signing | A long random string (32+ characters) |
| `DRYADE_AUTH_ENABLED` | Enable authentication | `true` |

### LLM Providers

Configure at least one provider. You can also configure these through the [Settings](/using-dryade/settings) page after installation.

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `GOOGLE_API_KEY` | Google AI API key | `AIza...` |
| `VLLM_BASE_URL` | Local vLLM endpoint | `http://localhost:8080/v1` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://dryade:dryade@postgres:5432/dryade` | Database connection string (PostgreSQL required) |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |

## Using a Local LLM

Dryade supports local models through vLLM or any OpenAI-compatible endpoint. This is ideal for privacy-sensitive deployments or GPU-equipped machines.

**1. Start vLLM with your model:**

```bash
vllm serve your-model-name --host 0.0.0.0 --port 8080
```

**2. Configure Dryade to use it:**

```bash
VLLM_BASE_URL=http://localhost:8080/v1
```

You can configure local models alongside cloud providers and switch between them in the Workbench.

## First Launch

After installation, open the Workbench at **http://localhost:3000**. On your first visit:

1. **Create an account** -- Register with your email and a password
2. **Complete the onboarding wizard** -- The wizard guides you through LLM provider setup, connection testing, and optional configuration
3. **Start using Dryade** -- You are ready to chat, create agents, and build workflows

For a detailed walkthrough of the onboarding process, see the [Onboarding Guide](/getting-started/onboarding-guide).

## Updating Dryade

To update to the latest version:

**Docker:**

```bash
git pull
docker-compose pull
docker-compose up -d
```

**Manual:**

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

Then restart the backend and frontend.

## Troubleshooting

### "Connection refused" error

Make sure the backend is running:

```bash
# Docker
docker ps

# Manual
ps aux | grep uvicorn
```

### Database errors

If you encounter migration issues, you can reset and reinitialize:

```bash
alembic upgrade head
```

For SQLite, you can start fresh by removing the database file and re-running migrations.

### Port already in use

Change the port in your start command:

```bash
uvicorn core.api.main:app --host 0.0.0.0 --port 8001
```

For more troubleshooting help, see the [Troubleshooting](/reference/troubleshooting) page.

## Next Steps

- [Quick Start](/getting-started/quick-start) -- Get from zero to your first conversation in 5 minutes
- [Onboarding Guide](/getting-started/onboarding-guide) -- Detailed walkthrough of first-time setup
- [Settings](/using-dryade/settings) -- Configure providers, keys, and preferences
