#!/usr/bin/env bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
echo "[WORKER] Starting RQ worker (Redis: ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}) ..."
python3 -m app.worker
