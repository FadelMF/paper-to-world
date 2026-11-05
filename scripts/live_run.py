"""Build one world from a real paper with the configured model, in the foreground.

    .venv/bin/python scripts/live_run.py path/to/paper.pdf
    .venv/bin/python scripts/live_run.py 1706.03762

The run is saved like an uploaded one, so `uvicorn app.main:app` serves it at /learn/<run_id>.
Diagnostics are in runs/<run_id>/debug.log.
"""

import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import store
from app.llm import configured
from app.pipeline import RUNS, initial_status, read_json, run_pipeline, write_json

if len(sys.argv) != 2:
    sys.exit(__doc__)
if not configured():
    sys.exit("Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in .env first.")
paper = Path(sys.argv[1])
run = RUNS / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
run.mkdir(parents=True)
if paper.is_file():
    (run / "paper.pdf").write_bytes(paper.read_bytes())
    write_json(run, "source.json", {})
else:
    write_json(run, "source.json", {"arxiv_id": sys.argv[1]})
write_json(run, "status.json", initial_status())


def build():
    store.BUDGET_RUN.set(run.name)
    run_pipeline(run)


worker = threading.Thread(target=build, daemon=True)
started, seen = time.monotonic(), None
worker.start()
while worker.is_alive() or seen is None:
    status = read_json(run, "status.json")
    line = f"[{status['step']}/5] {status['headline']}" + (f" - {status['activity'][0]['text']}" if status["activity"] else "")
    if line != seen:
        print(f"{time.monotonic() - started:6.0f}s {line}", flush=True)
        seen = line
    worker.join(timeout=1)

status = read_json(run, "status.json")
if status["error"]:
    print(f"Stopped: {status['error']}\nDetails: {run / 'debug.log'}")
    sys.exit(1)
checks = status["discovered"]["checks"] or {"passed": 0, "total": 0}
print(f"Ready: {status['discovered']['modality']} world, {checks['passed']}/{checks['total']} checks match the paper.")
print(f"Open http://localhost:8000/learn/{run.name}")
