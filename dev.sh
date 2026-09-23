#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [[ ! -x backend/.venv/bin/uvicorn || ! -d frontend/node_modules ]]; then
  echo "Сначала установите зависимости по README.md" >&2
  exit 1
fi

backend/.venv/bin/uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000 &
api_pid=$!
cleanup() {
  kill "$api_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd frontend
npm run dev -- --host 127.0.0.1 --strictPort
