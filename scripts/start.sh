#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
node tools/postgres.mjs start
uv run python -m scripts.use_postgres
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --loop app.services.loops:postgres_loop &
backend_pid=$!
npm --prefix frontend run dev &
frontend_pid=$!
trap 'kill "$backend_pid" "$frontend_pid"; node tools/postgres.mjs stop' EXIT INT TERM
wait
