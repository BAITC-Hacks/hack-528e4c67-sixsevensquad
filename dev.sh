#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [[ ! -x backend/.venv/bin/python || ! -d frontend/node_modules ]]; then
  echo "Сначала установите зависимости по README.md" >&2
  exit 1
fi

backend/.venv/bin/python -c 'import uvicorn, fastapi, openai'
# No automatic API reload: editing a file must not interrupt a paid analysis.
backend/.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!
web_pid=""
cleanup() {
  if [[ -n "$web_pid" ]]; then
    kill "$web_pid" 2>/dev/null || true
    wait "$web_pid" 2>/dev/null || true
  fi
  kill "$api_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd frontend
node node_modules/vite/bin/vite.js --host 127.0.0.1 --strictPort &
web_pid=$!
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 1
done
echo "Один из серверов остановился. Проверьте сообщение выше и доступность портов." >&2
exit 1
