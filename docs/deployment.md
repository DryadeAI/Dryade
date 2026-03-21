---
title: Deployment Guide
sidebar_position: 3
description: Deploy Dryade with Docker Compose or manually for production use
---

# Deployment Guide

This guide covers deploying Dryade in different environments, from local development to production.

## Docker Compose (Recommended)

Docker Compose is the fastest way to deploy Dryade with all required services.

### Prerequisites

- Docker 24+ and Docker Compose v2+
- 4 GB RAM minimum (8 GB recommended)
- 2 CPU cores minimum

### Basic Setup

```bash
git clone https://github.com/DryadeAI/Dryade.git
cd Dryade

# Configure environment
cp .env.example .env
# Edit .env -- set DRYADE_JWT_SECRET at minimum

# Start all services
docker compose up -d
```

This starts:
- **dryade-backend** -- FastAPI backend on port 8080
- **dryade-frontend** -- React frontend on port 3000
- **postgres** -- PostgreSQL database on port 5432

### GPU Profile (vLLM)

To run a local LLM with GPU acceleration:

```bash
docker compose --profile gpu up -d
```

This additionally starts a vLLM inference server. Requires:
- NVIDIA GPU with Compute Capability >= 7.0 (Volta or newer)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

### Verifying the Deployment

```bash
# Check all services are running
docker compose ps

# Check backend health
curl http://localhost:8080/health

# Check detailed health (database, LLM connectivity)
curl http://localhost:8080/health/detailed

# View logs
docker compose logs -f dryade-backend
```

## Manual Setup

For environments where Docker is not available or not preferred.

### Prerequisites

- Python 3.12+
- Node.js 20+ and npm
- PostgreSQL 15+ (or SQLite for development)

### Backend

```bash
cd dryade-core

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run database migrations
alembic upgrade head

# Start the server
uvicorn core.api.main:app --host 0.0.0.0 --port 8080 --workers 4
```

### Frontend

```bash
cd dryade-workbench

# Install dependencies
npm install

# Configure API URL
echo "VITE_API_URL=http://localhost:8080" > .env

# Build for production
npm run build

# Serve with any static file server (e.g., nginx, caddy, serve)
npx serve dist -p 3000
```

## Production Considerations

### Database

Use PostgreSQL in production. SQLite is suitable only for development and testing.

```env
DRYADE_DATABASE_URL=postgresql+psycopg://dryade:strong_password@db-host:5432/dryade
DRYADE_DATABASE_SSL_MODE=require
```

**Backup strategy:** Set up automated daily backups of your PostgreSQL database. Use `pg_dump` for logical backups or PostgreSQL's built-in continuous archiving for point-in-time recovery.

### Reverse Proxy & TLS

Place Dryade behind a reverse proxy for TLS termination. Example with [Caddy](https://caddyserver.com/):

```
your-domain.com {
    handle /api/* {
        reverse_proxy dryade-backend:8080
    }
    handle /ws/* {
        reverse_proxy dryade-backend:8080
    }
    handle {
        reverse_proxy dryade-frontend:3000
    }
}
```

Example with nginx:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /api/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        proxy_pass http://localhost:3000;
    }
}
```

### Security Checklist

- [ ] Set a strong `DRYADE_JWT_SECRET` (use `openssl rand -hex 32`)
- [ ] Set a strong `DRYADE_ENCRYPTION_KEY` for credential storage
- [ ] Set `DRYADE_ENV=production` to enable production validation
- [ ] Set `DRYADE_DATABASE_SSL_MODE=require` for encrypted database connections
- [ ] Configure `DRYADE_CORS_ORIGINS` to your domain only
- [ ] Enable TLS via reverse proxy
- [ ] Set up database backups
- [ ] Review rate limiting settings

### Resource Recommendations

| Deployment | CPU | RAM | Storage | GPU |
|------------|-----|-----|---------|-----|
| Development | 2 cores | 4 GB | 10 GB | None |
| Small team (cloud LLM) | 4 cores | 8 GB | 50 GB | None |
| Self-hosted LLM (8B) | 4 cores | 16 GB | 50 GB | 16 GB VRAM |
| Self-hosted LLM (70B) | 8 cores | 32 GB | 100 GB | 48+ GB VRAM |

### Environment-Specific Settings

```env
# Production .env additions
DRYADE_ENV=production
DRYADE_LOG_FORMAT=json
DRYADE_LOG_LEVEL=WARNING
DRYADE_DEBUG=false
DRYADE_RATE_LIMIT_ENABLED=true
```

## Updating

To update Dryade to the latest version:

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker compose down
docker compose build
docker compose up -d

# Check health
curl http://localhost:8080/health
```

For manual installations, also run `alembic upgrade head` after pulling updates to apply any database migrations.
