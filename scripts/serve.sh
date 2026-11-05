#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
export PAPER_ENV=production
# A shared in-memory worker queue requires exactly one server process.
exec uv run --locked --no-dev uvicorn app.main:app \
  --host 127.0.0.1 --port "${PORT:-8000}" --workers 1 \
  --no-server-header --no-access-log --limit-concurrency 64 --backlog 128
