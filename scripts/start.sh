#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  umask 077
  cp .env.example .env
fi
uv sync --locked --no-dev
uv run --locked --no-dev python -m playwright install chromium
exec scripts/serve.sh
