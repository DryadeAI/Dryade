#!/bin/bash
set -e

# ==============================================================================
# Production Startup Script
# ==============================================================================

# 1. Production Environment Setup
#    Enforce production mode.
export DRYADE_ENV=production

export DRYADE_TIER_INSTANT_ENABLED=true
export DRYADE_TIER_SIMPLE_ENABLED=true
# 2. Plugin Discovery
#    Tell Dryade where to find user/custom plugins (separate from plugins/ where
#    entry-point-registered plugins live). Only signed-allowlist plugins load.
export DRYADE_ENABLE_DIRECTORY_PLUGINS=true
export DRYADE_USER_PLUGINS_DIR=plugins

# 3. JWT Secret
#    Auto-generate a secure JWT secret if not already set.
if [ -z "$DRYADE_JWT_SECRET" ]; then
  export DRYADE_JWT_SECRET=$(openssl rand -hex 32)
  echo "[auto] Generated DRYADE_JWT_SECRET ($(echo $DRYADE_JWT_SECRET | cut -c1-8)...)"
fi

# 4. Database Setup
#    Auto-detect the local Docker PostgreSQL container, or use DRYADE_DATABASE_URL if set.
#    Enforce SSL for remote connections; disable for local Docker.
if [ -z "$DRYADE_DATABASE_URL" ]; then
  # Try to read credentials from the deploy-postgres container
  PG_CONTAINER=$(docker ps --filter name=postgres --format '{{.Names}}' 2>/dev/null | head -1)
  if [ -n "$PG_CONTAINER" ]; then
    PG_USER=$(docker inspect "$PG_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^POSTGRES_USER=' | cut -d= -f2)
    PG_PASS=$(docker inspect "$PG_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^POSTGRES_PASSWORD=' | cut -d= -f2)
    PG_DB=$(docker inspect "$PG_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^POSTGRES_DB=' | cut -d= -f2)
    PG_PORT=$(docker inspect "$PG_CONTAINER" --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' 2>/dev/null || echo "5432")
    export DRYADE_DATABASE_URL="postgresql+psycopg://${PG_USER}:${PG_PASS}@localhost:${PG_PORT}/${PG_DB}"
    export DRYADE_DATABASE_SSL_MODE="${DRYADE_DATABASE_SSL_MODE:-disable}"
    echo "[auto] Using local Docker PostgreSQL: ${PG_DB}@localhost:${PG_PORT}"
  else
    echo "[FATAL] DRYADE_DATABASE_URL is not set and no Docker PostgreSQL container found."
    echo "  Example: export DRYADE_DATABASE_URL=postgresql+psycopg://dryade:password@localhost:5432/dryade"
    exit 1
  fi
else
  # External DB — enforce SSL by default
  export DRYADE_DATABASE_SSL_MODE="${DRYADE_DATABASE_SSL_MODE:-require}"
fi

# 5. External Services Configuration
#    Configure URLs for optional services (Redis, Qdrant, Neo4j)
#    These must be set for health page to show actual status instead of "not configured"
export DRYADE_REDIS_URL="${DRYADE_REDIS_URL:-redis://localhost:6379}"
export DRYADE_QDRANT_URL="${DRYADE_QDRANT_URL:-http://localhost:6333}"
# Neo4j is optional - uncomment and set password if using graph features
# export NEO4J_URI=bolt://localhost:7687
# export NEO4J_USER=neo4j
# export NEO4J_PASSWORD=your_neo4j_password

# Add project root and dryade-core submodule to PYTHONPATH so services can find modules
export PYTHONPATH=$PYTHONPATH:.:dryade-core

echo "----------------------------------------------------------------"
echo "Starting Dryade in PRODUCTION mode"
echo "----------------------------------------------------------------"

# Step 1: Start Dryade Core API
echo "[1/2] Starting Dryade Core API..."
python -m uvicorn core.api.main:app --host 0.0.0.0 --port 8080 &
CORE_PID=$!

# Step 2: Wait for core to be ready
# For plugin support, see https://dryade.ai/docs/plugins

echo "----------------------------------------------------------------"
echo "Dryade is running"
echo "  Core API:      http://0.0.0.0:8080"
echo ""
echo "----------------------------------------------------------------"

# Wait for core process
wait $CORE_PID
