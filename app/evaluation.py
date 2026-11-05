"""What a finished run says about the models' work: one summary per run, read from its artifacts."""

import json
import re
from datetime import datetime

STAGES = ("Reference model", "Browser model", "Scene", "Lessons", "World")


def load(run_dir, name, default=None):
    path = run_dir / name
    return json.loads(path.read_text()) if path.is_file() else default


def summarize(run_dir):
    status = load(run_dir, "status.json", {})
    log = (run_dir / "debug.log").read_text() if (run_dir / "debug.log").is_file() else ""
    stamps = [datetime.strptime(m, "%Y-%m-%d %H:%M:%S") for m in re.findall(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ", log, re.M)]
    evidence = load(run_dir, "evidence.json", {"entities": [], "figures": []})
    scene = load(run_dir, "scene.json", {"objects": []})
    analysis = load(run_dir, "analysis.json", {"equations": []})
    critique = load(run_dir, "critique.json")
    render = load(run_dir, "render/report.json", {})
    usage = load(run_dir, "usage.json", [])
    return {
        "run": run_dir.name,
        "title": status.get("discovered", {}).get("title") or "",
        "ready": bool(status.get("done") and not status.get("error")),
        "stopped_at_step": status.get("step") if status.get("error") else None,
        "seconds": int((stamps[-1] - stamps[0]).total_seconds()) if len(stamps) > 1 else None,
        "modality": status.get("discovered", {}).get("modality"),
        "repairs": {stage: len(re.findall(rf"\d \d\d:\d\d:\d\d {re.escape(stage)} check \d+ failed", log)) for stage in STAGES},
        "checks_passed": status.get("discovered", {}).get("checks"),
        "figures": {"found": len(evidence["figures"]), "read": sum(bool(f.get("reading")) for f in evidence["figures"])},
        "entities": {"total": len(evidence["entities"]), "verified": sum(bool(e.get("verified")) for e in evidence["entities"])},
        "equations": {"total": len(analysis["equations"]), "matched_page": sum(e.get("checked") == "page" for e in analysis["equations"])},
        "parts": {
            "paper": sum(o.get("basis") == "paper" for o in scene["objects"]),
            "illustrative": sum(o.get("basis") == "hypothesis" for o in scene["objects"]),
        },
        "render_problems": len(render.get("problems", [])),
        "critic_major_left": len(critique["major"]) if critique else None,
        "model_calls": len(usage),
        "tokens": {"prompt": sum(u["prompt_tokens"] for u in usage), "completion": sum(u["completion_tokens"] for u in usage)},
        "images_sent": sum(u.get("images", 0) for u in usage),
    }


def report(summaries):
    """Totals across runs: how often a world is ready, and where repairs and cost go."""
    ready = [s for s in summaries if s["ready"]]
    return {
        "runs": len(summaries),
        "ready": len(ready),
        "repairs": {stage: sum(s["repairs"][stage] for s in summaries) for stage in STAGES},
        "paper_share_of_parts": round(
            sum(s["parts"]["paper"] for s in ready) / max(1, sum(s["parts"]["paper"] + s["parts"]["illustrative"] for s in ready)), 2
        ),
        "critic_major_left": sum(s["critic_major_left"] or 0 for s in ready),
        "tokens": {k: sum(s["tokens"][k] for s in summaries) for k in ("prompt", "completion")},
        "median_seconds": sorted(s["seconds"] or 0 for s in summaries)[len(summaries) // 2] if summaries else None,
    }
