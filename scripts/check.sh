#!/usr/bin/env bash
# Every check the project has, in order of speed. Stops at the first failure.
#   scripts/check.sh            lint, format, types, unit and integration tests
#   scripts/check.sh --browser  the same, then every browser script against a server it starts
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

uv lock --check
uv run --locked ruff check
uv run --locked ruff format --check app scripts tests
uv run --locked pyright
$PY - <<'PYJS'
import subprocess
from pathlib import Path
files = [p for p in Path("static").rglob("*.js") if "vendor" not in p.parts]
for path in files:
    subprocess.run(["node", "--check", str(path)], check=True)
print(f"JavaScript syntax: {len(files)} modules passed")
PYJS
$PY - <<'PYTEST'
import os
import subprocess
import sys
import tempfile
with tempfile.TemporaryDirectory(prefix="paper-tests-") as directory:
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                   env={**os.environ, "PAPER_RUNS_DIR": directory, "PAPER_ENV": "development",
                        "PAPER_PRIVATE_SESSIONS": "0", "PAPER_RATE_LIMIT_PER_HOUR": "0", "PAPER_ACCESS_TOKEN": ""}, check=True)
PYTEST
if [[ "${1:-}" == "--browser" ]]; then
  $PY tests/run_browser_tests.py
fi
