"""Build worlds for several papers with the configured models and report how well it went.

    .venv/bin/python scripts/evaluate.py 1706.03762 2006.11239 path/to/paper.pdf
    .venv/bin/python scripts/evaluate.py --runs runs/20261030-*      # summarize runs that already exist

Each paper is built one after another, saved like an upload (open /learn/<run_id> to look at it), and summarized:
ready or where it stopped, repairs per stage, figures read, evidence verified, equations matched to the printed
page, shapes from the paper vs illustrative, render problems, the Critic's remaining major issues, model calls,
tokens and time. The summary is printed and saved as evaluation-<time>.json.
"""

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import llm
from app.evaluation import report, summarize
from app.pipeline import RUNS, initial_status, run_pipeline, write_json


def build(paper):
    run = RUNS / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    path = Path(paper)
    if path.is_file():
        (run / "paper.pdf").write_bytes(path.read_bytes())
        write_json(run, "source.json", {})
    else:
        write_json(run, "source.json", {"arxiv_id": paper})
    write_json(run, "status.json", initial_status())
    llm.USAGE.clear()
    print(f"Building {paper} in {run.name} ...", flush=True)
    run_pipeline(run)
    return run


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--runs":
        runs = [Path(p) for p in sys.argv[2:]]
    else:
        if not llm.configured():
            sys.exit("Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL (and VISION_MODEL) in .env first.")
        runs = [build(paper) for paper in sys.argv[1:]]
    summaries = [summarize(run) for run in runs]
    result = {"summary": report(summaries), "runs": summaries}
    out = ROOT / f"evaluation-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"Saved {out}")
