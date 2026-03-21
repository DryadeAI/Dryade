# Self-Hosting Dryade

Everything you need to run Dryade on your own infrastructure.

Dryade is designed for self-hosting. Your models, your data, your rules. This guide covers every deployment path from Docker quickstart to manual installation, with operational guidance for production use.

> For full documentation, visit [dryade.ai/docs](https://dryade.ai/docs).

---

## System Requirements

| Resource | Minimum | Recommended | With Local Models (vLLM) |
|----------|---------|-------------|--------------------------|
| **OS** | Ubuntu 22.04+, Debian 12+, macOS 13+ | Ubuntu 24.04 LTS | Same |
| **CPU** | 2 cores | 4+ cores | 8+ cores |
| **RAM** | 4 GB | 8 GB | 16 GB+ |
| **Disk** | 10 GB | 20 GB | 50 GB+ (model storage) |
| **GPU** | Not required | Not required | NVIDIA with CUDA 12+ |
| **Network** | Outbound HTTPS | Outbound HTTPS | Not required for local-only |

**Windows users:** Run Dryade inside WSL2 with an Ubuntu distribution. Native Windows is not supported.

---

## Prerequisites

- **Python 3.12+** -- required for the backend
- **Node.js 20+** -- required for building the frontend
- **PostgreSQL 15+** -- the production database (required, not optional)
- **Docker** and **Docker Compose** -- if using the Docker path
- **uv** (recommended) or **pip** -- if using the manual path

> PostgreSQL is required for all deployment paths. The Docker quickstart includes a PostgreSQL container automatically.

---

## Docker Compose Quickstart

The fastest way to get Dryade running. No Python environment needed.

### 1. Clone and configure

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade
cp .env.example .env
```

Edit `.env` to configure your LLM provider. The default uses Ollama (no API key needed).

### 2. Start services

```bash
docker compose -f deploy/docker-compose.quickstart.yml up -d
```

This starts three services:

| Service | Port | Description |
|---------|------|-------------|
| **Ollama** | 11434 | Local LLM server (pulls models on demand) |
| **dryade-api** | 8080 | FastAPI backend |
| **dryade-frontend** | 3000 | Workbench UI |

### 3. Pull a model (Ollama)

```bash
docker compose -f deploy/docker-compose.quickstart.yml exec ollama ollama pull llama3.2:3b
```

### 4. Verify

```bash
# Check all services are healthy
docker compose -f deploy/docker-compose.quickstart.yml ps

# Test the API
curl http://localhost:8080/api/health

# Open the UI
open http://localhost:3000
```

### Using a cloud LLM provider

To use OpenAI, Anthropic, or Google instead of Ollama, set these in your `.env`:

```env
DRYADE_LLM_MODE=openai
DRYADE_LLM_MODEL=gpt-4o
DRYADE_LLM_BASE_URL=https://api.openai.com/v1
DRYADE_LLM_API_KEY=sk-your-key-here
```

Then stop the Ollama service:

```bash
docker compose -f deploy/docker-compose.quickstart.yml stop ollama
```

### GPU acceleration (optional)

Uncomment the GPU section in `deploy/docker-compose.quickstart.yml` to enable NVIDIA GPU passthrough for Ollama. Requires `nvidia-container-toolkit` on your host.

---

## Manual Installation (uv)

For production deployments or when you want full control over the stack.

### 1. Set up PostgreSQL

```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt install postgresql postgresql-contrib

# Create database and user
sudo -u postgres createuser dryade
sudo -u postgres createdb dryade -O dryade
sudo -u postgres psql -c "ALTER USER dryade PASSWORD 'your-secure-password';"
```

### 2. Clone and configure

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade
cp .env.example .env
```

Edit `.env` with your database connection and LLM provider:

```env
DRYADE_DATABASE_URL=postgresql+psycopg://dryade:your-secure-password@localhost:5432/dryade
DRYADE_LLM_BASE_URL=https://api.openai.com/v1
DRYADE_LLM_MODEL=gpt-4o
DRYADE_LLM_API_KEY=sk-your-key
DRYADE_JWT_SECRET=CHANGE_ME_GENERATE_WITH_openssl_rand_hex_32
```

### 3. Install backend

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv sync

# Start the backend
PYTHONPATH=.:dryade-core uvicorn core.api.main:app --host 0.0.0.0 --port 8080
```

### 4. Build and serve frontend

```bash
cd dryade-workbench
npm install
npm run build
npm run preview
```

The frontend runs on port 4173 by default in preview mode (or use `npm run dev` for port 5173 in development). Set `VITE_API_BASE_URL` in your `.env` to point to your backend.

### 5. Verify

```bash
curl http://localhost:8080/api/health
# Open http://localhost:3000 in your browser
```

---

## One-Click Deploy

Deploy Dryade to a cloud platform with a single click.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/dryade)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/DryadeAI/Dryade)

[![Deploy on Fly.io](https://fly.io/docs/images/launch-button.svg)](https://fly.io/launch?source=https://github.com/DryadeAI/Dryade)

> Deploy buttons require a platform account. Configuration is pre-set for quickstart. Each platform has its own pricing -- refer to their documentation for free tier limits.

---

## Reverse Proxy

For production deployments behind a reverse proxy.

### Traefik (recommended)

Dryade ships with Traefik configuration in `deploy/traefik-tls.yaml`. See `deploy/` for the full setup including TLS termination.

### Nginx

Minimal Nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name dryade.example.com;

    ssl_certificate /etc/ssl/certs/dryade.pem;
    ssl_certificate_key /etc/ssl/private/dryade-key.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

> WebSocket support (`/ws` endpoint) is required for real-time streaming responses.

---

## Backup and Restore

### What to back up

| Item | Location | Method |
|------|----------|--------|
| **Database** | PostgreSQL | `pg_dump` |
| **Environment** | `.env` | File copy |
| **Uploaded files** | `uploads/` or Docker volume | File copy / volume backup |

### PostgreSQL backup

```bash
# Backup
pg_dump -U dryade -h localhost dryade > dryade_backup_$(date +%Y%m%d).sql

# Restore
psql -U dryade -h localhost dryade < dryade_backup_20260309.sql
```

### Docker volume backup

```bash
# Backup data volume
docker run --rm -v dryade-quickstart-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/dryade-data.tar.gz /data

# Backup uploads volume
docker run --rm -v dryade-quickstart-uploads:/data -v $(pwd):/backup \
  alpine tar czf /backup/dryade-uploads.tar.gz /data
```

> See `deploy/` for additional deployment configuration.

---

## Upgrading

### Docker deployment

```bash
# Pull latest images
docker compose -f deploy/docker-compose.quickstart.yml pull

# Restart with new images
docker compose -f deploy/docker-compose.quickstart.yml up -d

# Check logs for migration output
docker compose -f deploy/docker-compose.quickstart.yml logs dryade-api
```

### Manual deployment

```bash
# Pull latest code
git pull origin main

# Update dependencies
source .venv/bin/activate
uv sync

# Run database migrations
python -m alembic upgrade head

# Rebuild frontend
cd dryade-workbench
npm install
npm run build
cd ..

# Restart services
```

> Always check [CHANGELOG.md](CHANGELOG.md) before upgrading for breaking changes.

---

## Troubleshooting FAQ

### Port 8080 already in use

Another service is using port 8080. Either stop it or change the Dryade port:

```bash
# Find what's using the port
lsof -i :8080

# Change Dryade's port in .env
DRYADE_PORT=8081
```

### PostgreSQL connection refused

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Verify connection string in .env
# Format: postgresql://user:password@host:5432/dbname

# Check pg_hba.conf allows local connections
sudo cat /etc/postgresql/15/main/pg_hba.conf
```

### Frontend not loading (blank page)

The frontend must be built before serving:

```bash
cd dryade-workbench
npm run build
npm run preview
```

If using Docker, check that the frontend container started successfully:

```bash
docker compose -f deploy/docker-compose.quickstart.yml logs dryade-frontend
```

### vLLM / GPU not detected

```bash
# Verify NVIDIA drivers
nvidia-smi

# Check nvidia-container-toolkit is installed (for Docker)
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# For vLLM, ensure CUDA 12+ is available
python -c "import torch; print(torch.cuda.is_available())"
```

### Permission errors on Docker volumes

```bash
# Fix volume ownership
sudo chown -R 1000:1000 /var/lib/docker/volumes/dryade-quickstart-data/
```

Or run the container with your user ID:

```bash
# Add to docker-compose.yml under the service
user: "${UID}:${GID}"
```

### Database migration errors

```bash
# Check current migration state
python -m alembic current

# If stuck, check for pending migrations
python -m alembic heads

# Force to a specific revision (use with caution)
python -m alembic stamp head
```

---

## Further Reading

- [Full documentation](https://dryade.ai/docs)
- [Configuration reference](docs/configuration.md) -- all environment variables and options
- [Contributing](CONTRIBUTING.md) -- development setup and contribution guidelines
- [Security policy](SECURITY.md) -- vulnerability reporting and security practices
- [Deploy directory](deploy/) -- Docker Compose profiles, observability, and TLS configuration
