#!/usr/bin/env bash
# Content Pipeline Startup Script
# Brings up Postiz + n8n stack with auto-generated secrets.
#
# Usage:
#   scripts/content-pipeline-up.sh          # Start the stack
#   scripts/content-pipeline-up.sh --down   # Stop the stack

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_DIR="$REPO_ROOT/docker/content-pipeline"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
ENV_FILE="$COMPOSE_DIR/.env"
ENV_EXAMPLE="$COMPOSE_DIR/.env.example"

# Handle --down flag
if [[ "${1:-}" == "--down" ]]; then
    echo "Stopping content pipeline..."
    docker compose -f "$COMPOSE_FILE" down
    echo "Content pipeline stopped."
    exit 0
fi

# Step 1: Create .env from .env.example if it doesn't exist
if [[ ! -f "$ENV_FILE" ]]; then
    echo "No .env file found. Creating from .env.example..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "Created $ENV_FILE -- review and customize as needed."
fi

# Step 2: Generate random secrets for any "changeme" placeholders
generate_secret() {
    openssl rand -hex 32
}

replace_changeme() {
    local key="$1"
    local current
    current=$(grep "^${key}=" "$ENV_FILE" | cut -d'=' -f2-)
    if [[ "$current" == "changeme" || "$current" == "changeme-generate-random" ]]; then
        local new_secret
        new_secret=$(generate_secret)
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^${key}=.*|${key}=${new_secret}|" "$ENV_FILE"
        else
            sed -i "s|^${key}=.*|${key}=${new_secret}|" "$ENV_FILE"
        fi
        echo "  Generated random secret for $key"
    fi
}

echo "Checking secrets..."
replace_changeme "POSTGRES_PASSWORD"
replace_changeme "JWT_SECRET"
replace_changeme "BACKEND_INTERNAL_SECRET"
replace_changeme "N8N_ENCRYPTION_KEY"
replace_changeme "N8N_BASIC_AUTH_PASSWORD"

# Step 3: Bring stack up
echo ""
echo "Starting content pipeline..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Step 4: Wait for health checks
echo ""
echo "Waiting for services to become healthy..."
MAX_WAIT=180
INTERVAL=5
ELAPSED=0

check_health() {
    local service="$1"
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null || echo "missing")
    echo "$status"
}

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    postiz_health=$(check_health "content-postiz")
    n8n_health=$(check_health "content-n8n")
    redis_health=$(check_health "content-redis")
    db_health=$(check_health "content-postiz-db")

    echo "  [${ELAPSED}s] postiz-db=$db_health redis=$redis_health postiz=$postiz_health n8n=$n8n_health"

    if [[ "$postiz_health" == "healthy" && "$n8n_health" == "healthy" ]]; then
        break
    fi

    # Check for container crashes
    for svc in content-postiz content-n8n content-postiz-db content-redis; do
        state=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
        if [[ "$state" == "exited" || "$state" == "dead" ]]; then
            echo "ERROR: $svc has exited. Check logs with: docker logs $svc"
            exit 1
        fi
    done

    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ $ELAPSED -ge $MAX_WAIT ]]; then
    echo ""
    echo "WARNING: Timeout waiting for services. Some may still be starting."
    echo "Check status: docker compose -f $COMPOSE_FILE ps"
    echo "Check logs:   docker compose -f $COMPOSE_FILE logs -f"
    exit 1
fi

# Step 5: Print access URLs
POSTIZ_PORT=$(grep "^POSTIZ_PORT=" "$ENV_FILE" | cut -d'=' -f2- || echo "4200")
N8N_PORT=$(grep "^N8N_PORT=" "$ENV_FILE" | cut -d'=' -f2- || echo "5678")

echo ""
echo "============================================="
echo "  Content Pipeline is running!"
echo "============================================="
echo ""
echo "  Postiz (social scheduler): http://localhost:${POSTIZ_PORT}"
echo "  n8n (workflow automation):  http://localhost:${N8N_PORT}"
echo ""
echo "  Stop:    scripts/content-pipeline-up.sh --down"
echo "  Logs:    docker compose -f docker/content-pipeline/docker-compose.yml logs -f"
echo "  Config:  docker/content-pipeline/.env"
echo ""
echo "  Next steps:"
echo "    1. Open Postiz and create your account"
echo "    2. Connect LinkedIn, X/Twitter via Postiz OAuth"
echo "    3. Open n8n and configure your first workflow"
echo ""
