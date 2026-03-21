#!/usr/bin/env bash
export DRYADE_ALLOWED_ORIGINS="http://127.0.0.1:9005,http://localhost:9005" \
       LITELLM_BASE_URL=${LITELLM_BASE_URL:-http://127.0.0.1:4000}
python -m uvicorn core.api.main:app --reload --port 8080
