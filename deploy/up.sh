#!/usr/bin/env bash
# Helper to detect the host IP and launch docker compose with the right PUBLIC_HOST.
# Usage: ./deploy/up.sh [profile] [compose args...]
# Example: ./deploy/up.sh thor up -d --build

set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

PROFILE="${1:-x86}"
shift || true

if [ $# -eq 0 ]; then
  set -- up -d
fi

# Detect host IP (best-effort). Allow override via env PUBLIC_HOST.
if [ -n "${PUBLIC_HOST:-}" ]; then
  HOST_IP="$PUBLIC_HOST"
else
  if command -v ip >/dev/null 2>&1; then
    HOST_IP=$(ip route get 1.1.1.1 2>/dev/null | awk 'NR==1 {print $7; exit}')
  fi
  if [ -z "${HOST_IP:-}" ]; then
    HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi
  HOST_IP=${HOST_IP:-127.0.0.1}
fi

export PUBLIC_HOST="$HOST_IP"
echo "[deploy/up.sh] Using PUBLIC_HOST=$PUBLIC_HOST" >&2

docker compose -f "$COMPOSE_FILE" --profile "$PROFILE" "$@"
