# Dryade Deployment Stack

This folder bundles a full docker-compose stack that boots the Dryade backend, Next.js frontend, LiteLLM proxy, and vLLM serving layer with a single compose command.

## Prerequisites

- Docker Engine 24+ with Compose V2 (`docker compose` CLI)
- NVIDIA Container Toolkit when running any GPU-backed vLLM profile
- Enough free disk (≥40 GB) for model weights and caches (adjust for your `VLLM_MODEL`)

## Layout

```
deploy/
├── backend/
│   ├── Dockerfile          # FastAPI/ADK backend container
│   ├── entrypoint.sh       # Prepares persistent data and launches uvicorn
│   └── requirements.txt    # Python dependencies for the backend
├── frontend/
│   └── Dockerfile          # Next.js production build + runtime
├── docker-compose.yml      # Orchestrates backend, frontend, LiteLLM, vLLM variants
├── .env.example            # Sample environment overrides (copy to .env)
└── README.md               # This file
```

The compose file also mounts project directories for persistent state:

- `../artifacts` → backend artifact store
- `../uploads` → user-uploaded files (exposed at `/files`)
- `../workflows` → workflow templates consumed by the backend
- `backend-data` named volume → SQLite session DB (`adk_sessions.db`)
- `huggingface-cache` named volume → shared HF model cache for vLLM

## Quick start

Copy the sample env file and select the hardware profile that matches your host GPU:

```bash
cd deploy
cp .env.example .env    # edit COMPOSE_PROFILES, PUBLIC_HOST, and ports as needed
# Replace x86 with arm64 when targeting ARM64 hosts
docker compose --profile ${COMPOSE_PROFILES:-x86} build
docker compose --profile ${COMPOSE_PROFILES:-x86} up -d
```

Set `PUBLIC_HOST` to the hostname or IP that external users will type in the browser. The frontend uses it to generate API URLs, and the backend uses it to populate the default CORS allow list. For multi-domain setups, override `NEXT_PUBLIC_FASTAPI_URL` / `DRYADE_ALLOWED_ORIGINS` explicitly in `.env`.

To auto-detect the host IP, use the helper script (first argument = profile, remaining arguments are passed to `docker compose`):

```bash
./deploy/up.sh x86 up -d --build
```

You can still override the value explicitly when needed: `PUBLIC_HOST=my.domain ./deploy/up.sh x86 up -d`.

Profile summary:

| Profile | vLLM service | Notes |
| --- | --- | --- |
| `x86` | `vllm-x86` | Default; expects discrete NVIDIA GPU on x86/amd64 (`gpus: all`). |
| `arm64` | `vllm-arm64` | ARM64 hosts with NVIDIA GPU; uses `runtime: nvidia`. |

The stack exposes the following host ports (reachable from other machines once network rules allow it):

- Frontend UI: <http://0.0.0.0:${FRONTEND_PORT:-3000}>
- Backend API: <http://0.0.0.0:${BACKEND_PORT:-8080}>
- LiteLLM proxy: <http://0.0.0.0:${LITELLM_PORT:-4000}>
- vLLM OpenAI API: <http://0.0.0.0:${VLLM_PORT:-8000}>

All services include health checks so the frontend waits for the backend and LiteLLM only reports healthy once the selected vLLM profile is ready.

## Configuration

Key environment knobs (set in `.env` or exported before `docker compose`):

| Variable | Default | Description |
| --- | --- | --- |
| `PUBLIC_HOST` | `127.0.0.1` | Hostname/IP that browsers hit (set to your public domain/IP). |
| `COMPOSE_PROFILES` | `x86` | Selects which vLLM profile to launch (`x86`, `arm64`). |
| `FRONTEND_PORT` | `3000` | Host port for the Next.js app |
| `BACKEND_PORT` | `8080` | Host port for the FastAPI API |
| `LITELLM_PORT` | `4000` | Host port for LiteLLM |
| `VLLM_PORT` | `8000` | Host port for the vLLM service profile you start |
| `NEXT_PUBLIC_FASTAPI_URL` | Computed from `PUBLIC_HOST` + backend port | Browser-visible API base (override for complex setups). |
| `FASTAPI_INTERNAL_URL` | `http://backend:8080` | Internal API base for server-side Next.js routes. |
| `MCP_BACKEND_URL` | `http://litellm:4000` | Base URL LiteLLM client uses inside the frontend container. |
| `DRYADE_ALLOWED_ORIGINS` | Computed list incl. `PUBLIC_HOST` | Comma-separated origins FastAPI will allow through CORS. |
| `LITELLM_MODEL` | `local-llm` | Default model LiteLLM exposes to clients |
| `VLLM_MODEL` | `unsloth/Qwen3-14B-unsloth-bnb-4bit` | HuggingFace model ID to serve |
| `VLLM_SERVED_NAME` | `local-llm` | Name exposed by vLLM/LiteLLM |
| `VLLM_DTYPE` | `auto` | Precision override for vLLM (profile may override defaults) |
| `VLLM_GPU_MEM_UTIL` | `0.60` | GPU memory utilization target |
| `AUTH_SECRET` | `change-me` | Token signing secret for backend auth |
| `NO_EGRESS` | `true` | Disable outbound calls from the backend’s LiteLLM client |

The defaults wire `FASTAPI_INTERNAL_URL` to the Docker network hostname (`backend`) so server-rendered routes work, while `NEXT_PUBLIC_FASTAPI_URL` points to `http://${PUBLIC_HOST}:${BACKEND_PORT}` for the browser. Adjust `PUBLIC_HOST` (or override the specific variables) whenever you front the stack with a public hostname or load balancer.

### Architecture specifics

- **x86 (default):** uses the upstream `vllm/vllm-openai` image with Compose GPU device requests (`gpus: all`).
- **arm64:** uses the `vllm/vllm-openai` arm64 build with `runtime: nvidia`.

Switch profiles with `docker compose --profile <name> …`; the backend, frontend, and LiteLLM containers are shared across profiles and automatically join whichever profile you select.

## Operational notes

- The backend entrypoint keeps the ADK SQLite database in the `backend-data` volume and symlinks it to `/app/adk_sessions.db` so session history survives restarts.
- LiteLLM loads its routing table from `deploy/litellm.yaml`; update that file to change model aliases or backends.
- vLLM shares a HuggingFace cache volume so models download once and persist across container updates.
- Tail logs with `docker compose --profile <name> logs -f backend`, `frontend`, `litellm`, or the chosen vLLM service (`vllm-x86`, `vllm-arm64`).
- Shutdown with `docker compose --profile <name> down` (add `-v` to purge named volumes, which also clears model caches and session history).

## Observability Stack (Optional)

Enable the observability profile to run Prometheus, Grafana, and Jaeger alongside your main stack:

```bash
docker compose --profile x86 --profile observability up -d
```

This adds:

| Service | Port | Description |
| --- | --- | --- |
| Prometheus | 9090 | Metrics collection and storage |
| Grafana | 3001 | Dashboards and visualization |
| Jaeger | 16686 | Distributed tracing UI |

### Configuration

Prometheus scrapes metrics from:
- Backend API (`backend:8080/metrics`)
- LiteLLM (`litellm:4000/metrics`)

Grafana is pre-configured with:
- Prometheus datasource
- Jaeger datasource for trace visualization

To send traces from the backend, set these environment variables:

```bash
DRYADE_OTEL_ENABLED=true
DRYADE_OTEL_ENDPOINT=http://jaeger:4317
```

### Accessing dashboards

- Grafana: http://localhost:3001 (admin/admin by default)
- Prometheus: http://localhost:9090
- Jaeger UI: http://localhost:16686
