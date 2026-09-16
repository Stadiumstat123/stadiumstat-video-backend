#!/bin/sh
set -eu
if [ "$(id -u)" = "0" ]; then
  mkdir -p "${DATA_DIR:-/data}"
  chown stadium:stadium "${DATA_DIR:-/data}"
  exec runuser -u stadium -- sh /app/start.sh
fi
python -m service.worker &
worker_pid=$!
uvicorn service.api:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 &
api_pid=$!
trap 'kill "$worker_pid" "$api_pid" 2>/dev/null || true' INT TERM EXIT
while kill -0 "$worker_pid" 2>/dev/null && kill -0 "$api_pid" 2>/dev/null; do
  sleep 2
done
exit 1
