"""Run the existing scientific stages and publish learner-facing progress."""

import json
import os
import time
import traceback
from pathlib import Path

from app import agents, llm, sandbox
from app.errors import NoTextLayer, PublicError
from app.figures import crop, page_count, page_images, png, render_figures, save_figure
from app.lesson_contract import validate_lessons, validate_world
from app.parity import check_port, parity_cases, reference_states
from app.pdf import NO_TEXT, clean_page, download_arxiv, figure_captions, figure_mentions, paper_chunks, read_pdf, select_figures, strip_running_lines
from app.quality import require_validation
from app.render_check import check_render
from app.teaching import validate_coverage
from app.visual import figure_anchors, normalize_critique, normalize_evidence, normalize_reading, validate_scene

RUNS = Path(os.getenv("PAPER_RUNS_DIR", "runs"))
MAX_CHARS = int(os.getenv("PAPER_MAX_CHARS", "120000"))  # per part; a longer paper is read in several parts
FIX_ATTEMPTS = 2
CRITIC_ROUNDS = 2
# Vision calls per paper. Every figure is still cut out and shown; these only bound what the vision model reads.
MAX_READ_FIGURES = int(os.getenv("PAPER_MAX_READ_FIGURES", "12"))
MAX_SCANNED_PAGES = int(os.getenv("PAPER_MAX_SCANNED_PAGES", "0"))  # 0: transcribe every page of a scan
MODEL_TIMEOUT = 120
ERROR_CHARS = 4000
LABELS = ["Reading the paper", "Finding the core ideas", "Designing your world", "Building & checking", "Ready"]
PUBLIC_ERROR = "We couldn't finish building this world. Try again, or try a different paper."


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def public_text(value, fallback=""):
    text = str(value or "").strip()
    return text or fallback


def read_json(run_dir, name):
    return json.loads((run_dir / name).read_text())


def write_json(run_dir, name, data):
    tmp = run_dir / (name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(run_dir / name)


def initial_status():
    return {
        "step": 1,
        "steps": [{"label": label, "state": "active" if i == 0 else "pending"} for i, label in enumerate(LABELS)],
        "headline": "Reading your paper",
        "subline": "Getting to know the paper you brought.",
        "activity": [],
        "waiting_hints": [],
        "discovered": {
            "title": "",
            "authors": "",
            "concepts": [],
            "equations": [],
            "modality": None,
            "modality_reason": "",
            "checks": None,
            "parts": None,
            "figures": 0,
        },
        "done": False,
        "error": None,
    }


def debug(run_dir, message):
    with (run_dir / "debug.log").open("a") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


class Progress:
    def __init__(self, run_dir, demo=False):
        self.run_dir = run_dir
        self.status = read_json(run_dir, "status.json")
        self.demo = demo

    def save(self):
        write_json(self.run_dir, "status.json", self.status)

    def stage(self, step, headline, subline):
        self.status.update(step=step, headline=headline, subline=subline, activity=[])
        for i, item in enumerate(self.status["steps"], 1):
            item["state"] = "done" if i < step else "active" if i == step else "pending"
        debug(self.run_dir, f"Started step {step}")
        self.save()

    def add(self, key, text, done=True):
        if not text:
            return
        self.status["activity"] = [item for item in self.status["activity"] if item["key"] != key]
        self.status["activity"].insert(0, {"key": key, "text": text, "done": done})
        self.status["activity"] = self.status["activity"][:5]
        self.save()

    def complete(self):
        for item in self.status["activity"]:
            item["done"] = True

    def hold_demo(self):
        # Only the explicitly labelled sample walkthrough is slowed for viewing.
        if self.demo:
            time.sleep(2.4)

    def analysis(self, analysis):
        d = self.status["discovered"]
        d["title"] = public_text(analysis.get("title"))
        d["authors"] = public_text(analysis.get("authors"))
        d["concepts"] = [name for c in analysis.get("concepts", []) if (name := public_text(c.get("name")))]
        d["equations"] = [
            {"latex": e["latex"], "meaning": public_text(e.get("meaning"))} for e in analysis.get("equations", []) if public_text(e.get("latex"))
        ][:2]
        self.complete()
        if d["title"]:
            self.status["headline"] = f"Finding the core ideas in “{d['title']}”"
            self.add("read", f"Reading “{d['title']}”")
        self.add("concepts", f"Found {len(analysis.get('concepts', []))} key ideas")
        equations = analysis.get("equations", [])
        if equations:
            meaning = public_text(equations[0].get("meaning"))
            self.add("equations", f"Spotted {len(equations)} equations" + (f", starting with {meaning}" if meaning else ""))
        self.add("claims", f"Noted {len(analysis.get('claims', []))} results the paper reports")
        self.status["waiting_hints"] = [f"Looking closely at {name}" for name in d["concepts"]]
        self.save()

    def evidence(self, evidence):
        parts, figures = len(evidence["entities"]), len(evidence["figures"])
        read = sum(bool(f.get("reading")) for f in evidence["figures"])
        self.status["discovered"]["figures"] = figures
        looked = f"its {plural(figures, 'figure')}" if read == figures else f"{read} of its {plural(figures, 'figure')}"
        self.add(
            "figures",
            f"Noted {plural(parts, 'part')} the paper describes"
            + (f", looking closely at {looked}" if read else f" and {plural(figures, 'figure caption')}" if figures else ""),
        )

    def plan(self, plan):
        d = self.status["discovered"]
        d["modality"] = plan["modality"]
        d["modality_reason"] = public_text(plan.get("rationale"))
        self.complete()
        text = f"This paper works best in {plan['modality'].upper()}"
        self.add("plan", text + (f": {d['modality_reason']}" if d["modality_reason"] else ""))
        controls = plan.get("controls", [])
        if controls:
            first = public_text(controls[0].get("label"))
            self.add("controls", f"Preparing {len(controls)} things you can change" + (f", like {first}" if first else ""))
        self.save()

    def checks(self, validation):
        results = validation["results"]
        passed = sum(r["status"] == "pass" for r in results)
        self.status["discovered"]["checks"] = {"passed": passed, "total": len(results)}
        self.complete()
        self.add("compare", f"Comparing with the paper: {passed} of {len(results)} results match")

    def scene(self, scene):
        paper = sum(o["basis"] == "paper" for o in scene["objects"])
        illustrative = len(scene["objects"]) - paper
        self.status["discovered"]["parts"] = {"paper": paper, "illustrative": illustrative}
        self.add("scene", f"Sketching {len(scene['objects'])} parts: {paper} drawn from the paper, {illustrative} illustrative")

    def ready(self, title):
        self.stage(5, f"Your world for “{title}” is ready" if title else "Your world is ready", "Start exploring, one idea at a time.")
        self.status["done"] = True
        self.status["waiting_hints"] = []
        for item in self.status["steps"]:
            item["state"] = "done"
        self.add("ready", self.status["headline"])

    def fail(self, message=PUBLIC_ERROR):
        self.status.update(done=True, error=message, headline="Building stopped", subline=message, waiting_hints=[])
        self.status["steps"][self.status["step"] - 1]["state"] = "error"
        self.save()


def run_model(run_dir):
    return sandbox.python(run_dir, ["model.py"], MODEL_TIMEOUT)


def parse_model_output(stdout):
    """The reference model's result: the last stdout line, a JSON object with a metrics object."""
    lines = stdout.strip().splitlines()
    try:
        result = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict) or not isinstance(result.get("metrics"), dict):
        raise ValueError('The last line printed must be one JSON object such as {"metrics": {...}, "notes": "..."}')
    return result


def checkpoint(run_dir, name, make):
    """A stage's result: saved in checkpoints/<name>.json, so a retried run resumes after its last finished stage."""
    path = run_dir / "checkpoints" / f"{name}.json"
    if path.exists():
        debug(run_dir, f"Resumed {name} from an earlier attempt")
        return json.loads(path.read_text())
    value = make()
    path.parent.mkdir(exist_ok=True)
    write_json(path.parent, path.name, value)
    return value


def until_valid(run_dir, name, make, check, on_retry=None, previous=None, error=None):
    """Ask make(previous, error) for an answer until check accepts it; each failure goes back with its reason.
    A starting `previous` and `error` turn the first call into a repair."""
    for attempt in range(FIX_ATTEMPTS + 1):
        if error is not None and on_retry:
            on_retry()
        try:
            # An unreadable reply and a failed check are both sent back for repair.
            previous = make(previous, error)
            return check(previous)
        except ValueError as failure:
            error = str(failure)[-ERROR_CHARS:]
            debug(run_dir, f"{name} check {attempt + 1} failed: {error}")
    raise RuntimeError(f"{name} failed its checks after {FIX_ATTEMPTS} repairs")


def check_model(run_dir, code, cases):
    """Run the reference; return its code, printed output and run() states for the parity cases."""
    (run_dir / "model.py").write_text(code)
    returncode, out, err = run_model(run_dir)
    debug(run_dir, f"Reference execution: returncode={returncode}\nstdout={out}\nstderr={err}")
    if returncode != 0:
        raise ValueError(err or f"The script exited with code {returncode}")
    try:
        parse_model_output(out)
    except ValueError as error:
        raise ValueError(f"The script ran but its output is unusable. {error}\nstdout ended with:\n{out[-1000:]}") from error
    return code, out, reference_states(run_dir, cases)


def read_pages(run_dir, provider, progress):
    """The paper's pages as text: from arXiv or the upload; a scan is transcribed when a vision model is available."""
    source = read_json(run_dir, "source.json") if (run_dir / "source.json").exists() else {}
    if not (run_dir / "paper.pdf").exists() and source.get("arxiv_id"):
        progress.add("open", "Opening your paper from arXiv", done=False)
        (run_dir / "paper.pdf").write_bytes(download_arxiv(source["arxiv_id"]))
    if not (run_dir / "paper.pdf").exists():
        return read_json(run_dir, "pages.json")
    data = (run_dir / "paper.pdf").read_bytes()
    try:
        return read_pdf(data)
    except NoTextLayer:
        if not provider.vision_available():
            raise
        return transcribe_scan(run_dir, provider, progress, data)


def transcribe_scan(run_dir, provider, progress, data):
    """Text for a scanned PDF, one page image at a time."""
    total = page_count(data)
    numbers = range(1, (min(total, MAX_SCANNED_PAGES) if MAX_SCANNED_PAGES else total) + 1)
    if len(numbers) < total:
        debug(run_dir, f"Scanned PDF has {total} pages; transcribing the first {len(numbers)} (PAPER_MAX_SCANNED_PAGES)")
    progress.add("open", f"Reading {plural(len(numbers), 'scanned page')}", done=False)
    images = page_images(data, numbers)
    pages = [clean_page(provider.transcribe(n, images[n])) for n in numbers]
    if not any(len(page) > 20 for page in pages):
        raise PublicError(NO_TEXT)
    return strip_running_lines(pages)


def proofread_equations(run_dir, provider, analysis):
    """Check each cited equation against an image of its page; keep the printed LaTeX when found (checked: page)."""
    equations = [e for e in analysis["equations"] if e.get("page")]  # one call per cited page
    pages = sorted({e["page"] for e in equations})
    images = page_images((run_dir / "paper.pdf").read_bytes(), pages)
    for page in images:
        cited = [e for e in equations if e["page"] == page]
        try:
            reply = provider.proofread(page, images[page], cited)
        except ValueError as error:
            debug(run_dir, f"Proofreading page {page} unusable: {error}")
            continue
        answers = {str(item.get("id")): item for item in reply.get("equations") or [] if isinstance(item, dict)}
        for equation in cited:
            answer = answers.get(str(equation.get("id")))
            if answer is None:
                continue
            printed = str(answer.get("latex") or "").strip()
            if answer.get("found") and printed:
                equation.update(latex=printed, checked="page")
            else:
                equation["checked"] = "not_found"
    return sum(e.get("checked") == "page" for e in equations)


def prepare_figures(run_dir, provider, pages):
    """Every figure (captioned, and drawings no caption claims) cut out of its rendered page as figure-<id>.png.
    With a vision model, the MAX_READ_FIGURES the text mentions most are read."""
    captions = figure_captions(pages)
    if not (run_dir / "paper.pdf").exists():
        return [{**caption, "image": None, "box": None, "reading": None} for caption in captions]
    found = render_figures((run_dir / "paper.pdf").read_bytes(), captions)
    to_read = {f["id"] for f in select_figures(pages, found, MAX_READ_FIGURES)} if provider.vision_available() else set()
    figures = []
    for figure in found:
        reading = None
        if figure["id"] in to_read:
            meta = {k: figure[k] for k in ("id", "page", "caption")}
            try:
                reading = normalize_reading(
                    provider.read_figure(meta, png(figure["page_image"]), png(crop(figure["page_image"], figure["box"])), figure_mentions(pages, figure["id"]))
                )
            except ValueError as error:
                debug(run_dir, f"Figure {figure['id']} reading unusable, layout guess kept: {error}")
        box = reading["box"] if reading and reading["box"] else figure["box"]
        figures.append(
            {
                "id": figure["id"],
                "page": figure["page"],
                "caption": figure["caption"],
                "box": box,
                "image": save_figure(run_dir, figure, box),
                "reading": reading,
            }
        )
    return figures


def cited_figures(run_dir, scene, evidence):
    """(figure, PNG) for each figure a paper-based scene object relies on, directly or through an entity."""
    cited = {o["evidence"] for o in scene["objects"] if o["basis"] == "paper"}
    cited |= {e.get("figure") for e in evidence["entities"] if e["id"] in cited}
    return [(f, (run_dir / f["image"]).read_bytes()) for f in evidence["figures"] if f["id"] in cited and f.get("image")]


def check_browser_model(run_dir, model_js, cases, states):
    (run_dir / "model.js").write_text(model_js)
    check_port(run_dir, cases, states)
    return model_js


def review(run_dir, progress, provider, scene, evidence, lessons, world_js, render, draw):
    """Let the Critic compare screenshots with the paper's figures; major issues go back to the Builder.
    A redraw that fails its checks is dropped and the last checked world is kept."""
    figures = cited_figures(run_dir, scene, evidence)
    progress.add("review", "Comparing your world with the paper", done=False)
    for round in range(1, CRITIC_ROUNDS + 1):
        shots = [(item["id"], (run_dir / item["screenshot"]).read_bytes()) for item in render["lessons"]]
        critique = normalize_critique(provider.critique(scene, evidence, lessons, shots, figures))
        write_json(run_dir, "critique.json", {"round": round, **critique})
        if not critique["major"]:
            break
        if round == CRITIC_ROUNDS:
            raise PublicError("The visual review found issues that still need correction. Try building this paper again.")
        feedback = "A reviewer compared screenshots of your world with the paper's figures and found:\n" + "\n".join(
            f"- [{i.get('lesson') or 'all lessons'} / {i.get('object') or 'scene'}] {i['problem']} Fix: {i.get('fix') or ''}" for i in critique["major"]
        )
        try:
            world_js, render = draw(world_js, feedback)
        except RuntimeError as error:
            debug(run_dir, f"Kept the previous world: {error}")
            raise PublicError("The visual corrections did not pass their checks. Try building this paper again.") from error
    progress.add("review", "Compared your world with the paper" + (f" and {len(figures)} of its figures" if figures else ""))
    return world_js, render


def run_pipeline(run_dir, provider=None, demo=False):
    provider = provider or agents
    progress = Progress(run_dir, demo)
    try:
        pages = checkpoint(run_dir, "pages", lambda: read_pages(run_dir, provider, progress))
        write_json(run_dir, "pages.json", pages)
        progress.complete()
        progress.add("open", f"Opened {len(pages)} pages")
        progress.hold_demo()

        progress.stage(2, "Finding the core ideas in your paper", "Finding the ideas you’ll be able to explore.")
        progress.add("read", "Reading your paper", done=False)
        chunks = paper_chunks(pages, MAX_CHARS)
        if len(chunks) > 1:
            progress.add("read", f"Reading your paper in {len(chunks)} parts", done=False)

        def analyze():
            analysis = agents.validate_analysis(agents.merge_analyses([provider.analyze(chunk) for chunk in chunks]))
            if provider.vision_available() and (run_dir / "paper.pdf").exists():
                proofread_equations(run_dir, provider, analysis)
            return analysis

        analysis = checkpoint(run_dir, "analysis", analyze)
        write_json(run_dir, "analysis.json", analysis)
        progress.analysis(analysis)
        checked = sum(e.get("checked") == "page" for e in analysis["equations"])
        if checked:
            progress.add("proofread", f"Checked {plural(checked, 'equation')} against the printed page")
        progress.add("figures", "Looking at how the paper draws it", done=False)

        def observe():
            figures = prepare_figures(run_dir, provider, pages)
            return normalize_evidence(agents.merge_evidence([provider.observe(chunk, figures) for chunk in chunks]), pages, figures)

        evidence = checkpoint(run_dir, "evidence", observe)
        write_json(run_dir, "evidence.json", evidence)
        progress.evidence(evidence)
        progress.hold_demo()

        progress.stage(3, "Designing your world", "Choosing a clear way to see the ideas in action.")
        concepts = progress.status["discovered"]["concepts"]
        progress.add("plan", f"Planning how to show {concepts[0]}" if concepts else "Planning how to show the paper’s main idea", done=False)
        plan = checkpoint(run_dir, "plan", lambda: agents.validate_plan(provider.plan(analysis, evidence), analysis))
        write_json(run_dir, "plan.json", plan)
        progress.plan(plan)
        progress.hold_demo()

        progress.stage(4, "Building and checking your world", "Making the ideas interactive and checking them against the paper.")
        core = public_text(plan.get("core_model"), "the paper’s central mechanism")
        progress.add("model", f"Recreating {core} so it really runs", done=False)
        cases = parity_cases(plan)

        def build_reference():
            code, out, states = until_valid(
                run_dir,
                "Reference model",
                lambda previous, error: provider.build_model(analysis, plan, previous, error),
                lambda code: check_model(run_dir, code, cases),
                on_retry=lambda: progress.add("model", "Fine-tuning the simulation", done=False),
            )
            return {"code": code, "output": out, "states": states}

        reference = checkpoint(run_dir, "reference", build_reference)
        code, out, states = reference["code"], reference["output"], reference["states"]
        (run_dir / "model.py").write_text(code)
        (run_dir / "model_output.txt").write_text(out)
        progress.complete()
        progress.add("compare", "Comparing the results with the paper", done=False)
        validation = checkpoint(run_dir, "validation", lambda: agents.normalize_validation(provider.validate(analysis, plan, out)))
        write_json(run_dir, "validation.json", validation)
        try:
            require_validation(plan, validation, parse_model_output(out))
        except ValueError as error:
            # A retry must regenerate the rejected model and every artifact derived from it.
            for name in ("reference", "validation", "port", "scene", "lessons"):
                (run_dir / "checkpoints" / f"{name}.json").unlink(missing_ok=True)
            debug(run_dir, f"Publication blocked by numerical validation: {error}")
            raise PublicError("The simulation did not pass its required numerical checks. Try building this paper again.") from error
        progress.checks(validation)

        progress.add("port", "Making the simulation run in your browser", done=False)
        model_js = checkpoint(
            run_dir,
            "port",
            lambda: until_valid(
                run_dir,
                "Browser model",
                lambda previous, error: provider.port_model(plan, code, previous, error),
                lambda model_js: check_browser_model(run_dir, model_js, cases, states),
            ),
        )
        (run_dir / "model.js").write_text(model_js)
        write_json(run_dir, "parity.json", {"cases": len(cases), "params_and_steps": cases, "reference": states})
        progress.add("port", f"Your browser simulation matches the reference in all {len(cases)} checks")

        state = states[0]
        progress.add("scene", "Sketching the parts you’ll explore", done=False)
        scene = checkpoint(
            run_dir,
            "scene",
            lambda: until_valid(
                run_dir,
                "Scene",
                lambda previous, error: provider.design_scene(analysis, evidence, plan, state, previous, error),
                lambda scene: validate_scene(scene, plan["modality"], evidence, state),
            ),
        )
        write_json(run_dir, "scene.json", scene)
        progress.scene(scene)

        object_ids = [o["id"] for o in scene["objects"]]
        progress.add("lessons", "Shaping your lessons", done=False)
        lessons = checkpoint(
            run_dir,
            "lessons",
            lambda: until_valid(
                run_dir,
                "Lessons",
                lambda previous, error: provider.write_lessons(analysis, plan, validation, scene, state, previous, error),
                lambda lessons: validate_lessons(lessons, object_ids, list(cases[0][0])),
            ),
        )
        write_json(run_dir, "coverage.json", validate_coverage(analysis, plan, lessons))
        progress.add("lessons", f"Shaping {len(lessons)} lessons for you")

        progress.add("world", "Drawing your world", done=False)
        anchors = figure_anchors(scene, evidence)

        def check_world(world_js):
            validate_world(world_js, plan["modality"], object_ids)
            if getattr(provider, "prepared", False):
                return world_js, {"lessons": []}
            return world_js, check_render(run_dir, world_js, lessons, scene, anchors)

        def draw(previous=None, error=None):
            return until_valid(
                run_dir,
                "World",
                lambda previous, error: provider.build_world(plan, scene, lessons, model_js, state, previous, error),
                check_world,
                previous=previous,
                error=error,
            )

        world_js, render = draw()
        progress.complete()
        progress.add("world", f"Drew {len(object_ids)} parts" + ("" if getattr(provider, "prepared", False) else " and checked every lesson in a browser"))
        if provider.vision_available():
            world_js, render = review(run_dir, progress, provider, scene, evidence, lessons, world_js, render, draw)
        write_json(run_dir, "lessons.json", lessons)
        (run_dir / "world.js").write_text(world_js)
        progress.hold_demo()
        progress.ready(progress.status["discovered"]["title"])
    except PublicError as error:
        debug(run_dir, traceback.format_exc())
        progress.fail(str(error))
    except Exception:
        debug(run_dir, traceback.format_exc())
        progress.fail()
    finally:
        write_json(run_dir, "usage.json", llm.USAGE)
