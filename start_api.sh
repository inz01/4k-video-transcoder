#!/usr/bin/env bash
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
echo "[API] Starting FastAPI on ${API_HOST:-0.0.0.0}:${API_PORT:-8000} ..."
uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" --reload
