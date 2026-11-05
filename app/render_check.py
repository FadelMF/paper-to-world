"""Open a generated world in headless Chromium and check what it actually draws.

The world is served from the run folder exactly as the lesson shell loads it: the candidate world.js and the
run's model.js, '../lesson/*.js' from the shared library, three.js through the same import map (static/vendor). Every lesson is
applied, played, measured and photographed. Problems are returned all at once so the Builder can fix them in
one repair; screenshots go to <run>/render/ for the Critic and for review.

The browser runs model-written code, so it is isolated in layers: a separate process with no server
environment, confined by Landlock and seccomp where available (it can read only the system, the browser, the
Python runtime and this app's app/ and static/ folders, write only the run's render/ folder, and open no
network socket); Chromium's own sandbox when the system supports it; a Content-Security-Policy that lets the
page load only from itself; WebRTC kept off UDP; and every request to another host aborted.
"""

import base64
import hashlib
import json
import os
import resource
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from app import confine, sandbox

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
RENDER_TIMEOUT = 600
PlaywrightError = Exception  # replaced by Playwright's error class inside the confined process
ORIGIN = "http://world.check"
ALLOWED_HOSTS = {"world.check"}
VIEWPORT = (960, 680)
PHONE_VIEWPORT = (390, 760)
PHONE_PANEL = (358, 340)  # the lesson shell's world panel on a phone: full width, about 40% of the screen
SETTLE_MS = 900  # lesson transitions take 400-600 ms
PLAY_MS = 500  # long enough for a playing model to advance
ASSEMBLY_MS = 1100  # explode animations take up to 900 ms
LOAD_TIMEOUT_MS = 30000
TAG_INSIDE = 0.9  # share of a tag that must be inside the world
MIN_VISIBLE = 0.5  # share of an object's box that must be inside the world
LABEL_OVERLAP = 0.3  # share of the smaller label that may be covered
FIGURE_APART = 0.15  # elements this far apart in a paper figure (share of its size) must keep their order
# WebGL uses SwiftShader (no GPU on servers);
# 2D canvas and compositing stay in software, which is several times faster than emulating a GPU for them.
LAUNCH_ARGS = [
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--disable-accelerated-2d-canvas",
    "--disable-gpu-compositing",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
]
TYPES = {".js": "text/javascript", ".json": "application/json", ".css": "text/css", ".html": "text/html"}

IMPORT_MAP = '{"imports":{"three":"/assets/vendor/three/three.module.js","three/addons/":"/assets/vendor/three/addons/"}}'
CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-eval' 'sha256-{hash}'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
    "img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
).replace("{hash}", base64.b64encode(hashlib.sha256(IMPORT_MAP.encode()).digest()).decode())

HARNESS = (
    """<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="/assets/ui/app.css"><link rel="stylesheet" href="/assets/lesson/style.css"><link rel="stylesheet" href="/assets/lesson/world.css">
<script type="importmap">"""
    + IMPORT_MAP
    + """</script>
<style>body{margin:0;padding:16px}#visual{width:900px;height:620px;display:flex;flex-direction:column}#world{flex:1;position:relative}</style>
</head><body><section id="visual" class="world-panel"><div id="world"></div></section></body></html>"""
)

# Runs in the page: overlap and placement facts for one lesson.
MEASURE = """(visible) => {
  const host = document.getElementById('world').getBoundingClientRect();
  const bounds = window.world.objectBounds();
  const tags = [...document.querySelectorAll('#world [data-object]')].filter(el => {
    const style = getComputedStyle(el), r = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) > 0.05 && r.width > 0 && r.height > 0;
  }).map(el => { const r = el.getBoundingClientRect(); return {id: el.dataset.object, x: r.left - host.left, y: r.top - host.top, width: r.width, height: r.height,
    focusable: el.tabIndex >= 0}; });
  return {width: host.width, height: host.height, bounds, tags};
}"""


def overlap(a, b):
    width = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    height = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    return max(0, width) * max(0, height)


def figure_order_problems(name, anchors, visible, bounds):
    """Paper-based objects keep the left/right and above/below order their elements have in the paper's figure."""
    problems = []
    placed = [oid for oid in visible if oid in anchors and isinstance(bounds.get(oid), dict)]
    center = lambda box, axis: box["x"] + box["width"] / 2 if axis == "x" else box["y"] + box["height"] / 2
    for i, a in enumerate(placed):
        for b in placed[i + 1 :]:
            (fa, xa, ya), (fb, xb, yb) = anchors[a], anchors[b]
            if fa != fb:
                continue
            for axis, (pa, pb), word in (("x", (xa, xb), "left of"), ("y", (ya, yb), "above")):
                if abs(pa - pb) > FIGURE_APART and (pa < pb) != (center(bounds[a], axis) < center(bounds[b], axis)):
                    first, second = (a, b) if pa < pb else (b, a)
                    problems.append(f"{name}: the paper's {fa} puts {first} {word} {second}, but the world draws it the other way")
    return problems


def layout_problems(name, scene, visible, facts):
    """Every visible object is drawn inside the world with a focusable tag; tags don't pile up; 2D order follows the scene."""
    problems = []
    objects = {o["id"]: o for o in scene["objects"]}
    tags = {t["id"]: t for t in facts["tags"]}
    world = {"x": 0, "y": 0, "width": facts["width"], "height": facts["height"]}
    for oid in visible:
        box = facts["bounds"].get(oid)
        if not isinstance(box, dict) or not all(isinstance(box.get(k), (int, float)) for k in ("x", "y", "width", "height")):
            problems.append(f"{name}: objectBounds() has no box for visible object {oid}")
        elif box["width"] < 1 or box["height"] < 1:
            problems.append(f"{name}: {oid} is drawn {box['width']:.0f}×{box['height']:.0f} px, too small to see")
        elif overlap(box, {"x": 0, "y": 0, "width": facts["width"], "height": facts["height"]}) < MIN_VISIBLE * box["width"] * box["height"]:
            seen = overlap(box, {"x": 0, "y": 0, "width": facts["width"], "height": facts["height"]}) / (box["width"] * box["height"])
            problems.append(f"{name}: {oid} is drawn outside the world at ({box['x']:.0f}, {box['y']:.0f}); {seen:.0%} of it is visible")
        if oid not in tags:
            problems.append(f'{name}: visible object {oid} has no visible tag element with data-object="{oid}"')
        elif not tags[oid]["focusable"]:
            problems.append(f"{name}: the tag for {oid} cannot be reached with the keyboard")
        elif overlap(tags[oid], world) < TAG_INSIDE * tags[oid]["width"] * tags[oid]["height"]:
            problems.append(f"{name}: the tag for {oid} is cut off at the edge of the world")
    shown = [t for t in facts["tags"] if t["id"] in visible]
    for i, a in enumerate(shown):
        for b in shown[i + 1 :]:
            if overlap(a, b) > LABEL_OVERLAP * min(a["width"] * a["height"], b["width"] * b["height"]):
                problems.append(f"{name}: the {a['id']} and {b['id']} tags overlap")
    if scene["modality"] == "2d":
        drawn = [oid for oid in visible if oid in objects and isinstance(facts["bounds"].get(oid), dict)]
        for i, a in enumerate(drawn):
            for b in drawn[i + 1 :]:
                pa, pb, sa, sb = objects[a]["position"], objects[b]["position"], objects[a].get("size") or [0, 0], objects[b].get("size") or [0, 0]
                ba, bb = facts["bounds"][a], facts["bounds"][b]
                for axis, screen, sign, word in ((0, "x", 1, "left of"), (1, "y", -1, "above")):
                    if abs(pa[axis] - pb[axis]) <= (sa[axis] + sb[axis]) / 2:
                        continue  # They overlap along this axis in the design, so either order is fine.
                    designed = (pa[axis] < pb[axis]) == (sign > 0)
                    drawn_first = ba[screen] + ba["width" if screen == "x" else "height"] / 2 < bb[screen] + bb["width" if screen == "x" else "height"] / 2
                    if designed != drawn_first:
                        first, second = (a, b) if designed else (b, a)
                        problems.append(f"{name}: the scene puts {first} {word} {second}, but the world draws it the other way")
    return problems


def serve(run_dir, world_js):
    def handle(route):
        url = urlparse(route.request.url)
        if url.hostname != "world.check":
            route.continue_() if url.hostname in ALLOWED_HOSTS else route.abort()
            return
        if url.path in ("/index.html", "/run/world.js"):
            route.fulfill(
                body=HARNESS if url.path == "/index.html" else world_js, content_type=TYPES[Path(url.path).suffix], headers={"Content-Security-Policy": CSP}
            )
            return
        roots = {"/run/": run_dir, "/lesson/": STATIC / "lesson", "/assets/": STATIC}
        for prefix, root in roots.items():
            if url.path.startswith(prefix):
                file = (root / url.path[len(prefix) :]).resolve()
                if file.is_relative_to(root.resolve()) and file.is_file():
                    route.fulfill(body=file.read_bytes(), content_type=TYPES.get(file.suffix, "application/octet-stream"))
                    return
        route.fulfill(status=404, body="not found")

    return handle


def browser_rules(run_dir):
    """What the confined browser process may touch: read the system, the browser and Python, and this app's code
    and static files (not the project folder, which holds .env); write only the run's render/ folder."""
    readable = [
        *sandbox.SYSTEM,
        "/etc",
        "/run/systemd/resolve",
        "/proc",
        "/sys",
        "/usr/share",
        browsers_path(),
        *sandbox.python_roots(),
        str(ROOT / "app"),
        str(STATIC),
    ]
    return (
        [(path, confine.READ) for path in readable]
        + [(str(ROOT), confine.LIST)]
        + [(str(run_dir / "render"), confine.WRITE), (str(run_dir / "model.js"), confine.READ), ("/dev/null", confine.WRITE), ("/dev/shm", confine.WRITE)]
    )


def browsers_path():
    return os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / ".cache" / "ms-playwright")


def check_render(run_dir, world_js, lessons, scene, anchors=None):
    """Open the candidate world (not yet saved) beside the run's model.js. Raise ValueError listing every
    problem; return a report with one screenshot per lesson. `anchors` (visual.figure_anchors) hold paper-based
    objects to their figure's order: in every 2D lesson, and in the first 3D lesson (later ones may turn the camera)."""
    run_dir = Path(run_dir).resolve()
    shots = run_dir / "render"
    shutil.rmtree(shots, ignore_errors=True)
    (shots / "tmp").mkdir(parents=True)
    confined = confine.available()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(shots / "tmp"),
        "TMPDIR": str(shots / "tmp"),
        "PLAYWRIGHT_BROWSERS_PATH": browsers_path(),
        "PAPER_CONFINED": "1" if confined else "",
    }
    rules = browser_rules(run_dir)

    def setup():  # Chromium needs large virtual address space; the service cgroup bounds resident memory.
        hard = resource.getrlimit(resource.RLIMIT_AS)[1]
        resource.setrlimit(resource.RLIMIT_AS, (hard, hard))
        if confined:
            confine.confine(rules)

    request = json.dumps({"run_dir": str(run_dir), "world_js": world_js, "lessons": lessons, "scene": scene, "anchors": anchors or {}})
    starter = f"import sys; sys.path.insert(0, {str(ROOT)!r}); from app.render_check import main; main()"
    code, out, err = sandbox.run([sys.executable, "-I", "-c", starter], run_dir, RENDER_TIMEOUT, env=env, setup=setup, stdin=request)
    shutil.rmtree(shots / "tmp", ignore_errors=True)
    lines = out.strip().splitlines()
    if code is None or not lines:
        raise RuntimeError(f"The render check did not finish: {err[-1500:]}")
    result = json.loads(lines[-1])
    if result.get("error"):
        raise RuntimeError(result["error"])
    if result["problems"]:
        raise ValueError(f"{len(result['problems'])} problems when the world was opened in a browser:\n" + "\n".join(result["problems"][:20]))
    return result["report"]


def main():
    """The confined process: read the request on stdin, open the world, print one JSON line."""
    request = json.loads(sys.stdin.read())
    try:
        report, problems = open_world(
            Path(request["run_dir"]), request["world_js"], request["lessons"], request["scene"], {k: tuple(v) for k, v in request["anchors"].items()}
        )
        print(json.dumps({"report": report, "problems": problems}))
    except ValueError as error:
        print(json.dumps({"report": {}, "problems": [str(error)]}))
    except RuntimeError as error:
        print(json.dumps({"error": str(error)}))


def launch(playwright):
    """Chromium with its own sandbox when the system supports one; without it only inside Landlock confinement."""
    try:
        return playwright.chromium.launch(args=LAUNCH_ARGS, chromium_sandbox=True), "chromium sandbox"
    except PlaywrightError as error:
        if os.environ.get("PAPER_CONFINED") != "1" and os.environ.get("PAPER_ALLOW_UNSANDBOXED_BROWSER") != "1":
            raise RuntimeError(
                "Chromium cannot use its sandbox here and Landlock is not available to confine it. "
                "Enable user namespaces or Landlock, or set PAPER_ALLOW_UNSANDBOXED_BROWSER=1 on a trusted machine."
            ) from error
        return playwright.chromium.launch(args=LAUNCH_ARGS), "landlock and seccomp" if os.environ.get("PAPER_CONFINED") == "1" else "none"


def open_world(run_dir, world_js, lessons, scene, anchors):
    """Runs in the confined process. Returns (report, problems)."""
    from playwright.sync_api import Error, sync_playwright

    global PlaywrightError
    PlaywrightError = Error
    shots = run_dir / "render"
    problems, shown = [], []
    with sync_playwright() as playwright:
        browser, isolation = launch(playwright)
        try:
            page = browser.new_page(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]})
            page.set_default_timeout(LOAD_TIMEOUT_MS)
            errors, blocked = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("requestfailed", lambda request: blocked.append(request.url) if urlparse(request.url).hostname not in ALLOWED_HOSTS else None)
            page.route("**/*", serve(run_dir, world_js))
            page.goto(ORIGIN + "/index.html")
            try:
                page.evaluate("async () => { window.world = await import('/run/world.js'); await window.world.init(document.getElementById('world')); }")
            except PlaywrightError as error:
                raise ValueError(f"world.js failed to load or init: {error.message.splitlines()[0]}") from error
            for index, lesson in enumerate(lessons, 1):
                name = f"lesson {index} ({lesson['id']})"
                page.evaluate("(scene) => { world.setLesson(scene); world.setParams(scene.params); world.play(); }", lesson["scene_state"])
                page.wait_for_timeout(SETTLE_MS)
                before = page.evaluate("() => world.getState()")
                page.wait_for_timeout(PLAY_MS)
                after = page.evaluate("() => world.getState()")
                if not isinstance(after.get("time"), (int, float)) or not after["time"] > before.get("time", after["time"]):
                    problems.append(f"{name}: getState().time does not advance while playing")
                page.evaluate("() => world.pause()")  # Measure a still frame; software rendering of a running world is slow.
                facts = page.evaluate(MEASURE, lesson["scene_state"]["visible"])
                problems += layout_problems(name, scene, lesson["scene_state"]["visible"], facts)
                if scene["modality"] == "2d" or index == 1:
                    problems += figure_order_problems(name, anchors, lesson["scene_state"]["visible"], facts["bounds"])
                shot = shots / f"lesson-{index}.png"
                page.locator("#visual").screenshot(path=str(shot))
                shown.append({"id": lesson["id"], "screenshot": str(shot.relative_to(run_dir)), "bounds": facts["bounds"]})
                for control in lesson["controls"]:
                    value = page.evaluate(
                        "([symbol, value]) => { world.setParams({[symbol]: value}); return world.getState()[symbol]; }", [control["symbol"], control["max"]]
                    )
                    if value != control["max"]:
                        problems.append(f"{name}: setParams({{{control['symbol']}: {control['max']}}}) left getState().{control['symbol']} = {value!r}")
                    page.evaluate("([symbol, value]) => world.setParams({[symbol]: value})", [control["symbol"], control["default"]])
                learning = lesson.get("learning")
                if learning:
                    page.evaluate("s => {world.setLesson(s); world.pause();}", lesson["scene_state"])
                    page.evaluate("p => world.setParams(p)", learning["test_params"])
                    page.evaluate("() => world.play()")
                    try:
                        page.wait_for_function(
                            "expression => Boolean(new Function('state', `return (${expression})`)(world.getState()))",
                            arg=learning["outcome_js"],
                            polling=100,
                            timeout=20000,
                        )
                    except PlaywrightError:
                        facts = page.evaluate("() => {const s=world.getState(); return {time:s.time, spikes:s.spikes, count:s.spikesFirstSecond};}")
                        problems.append(f"{name}: the proposed teaching interaction did not produce its computed outcome: {facts}")
                    finally:
                        page.evaluate("() => world.pause()")
                outcome = page.evaluate(
                    """(expression) => { try { return {ok: true, value: typeof Boolean(new Function('state', `"use strict"; return (${expression});`)(world.getState()))}; }
                                           catch (error) { return {ok: false, error: String(error)}; } }""",
                    lesson["challenge"]["check_js"],
                )
                if not outcome["ok"]:
                    problems.append(f"{name}: challenge check_js throws on getState(): {outcome['error']}")
            paused = page.evaluate("() => world.getState().time")
            page.evaluate("() => world.step()")
            if not page.evaluate("() => world.getState().time") > paused:
                problems.append("step() while paused does not advance time")
            page.evaluate("() => world.setAssembly(1)")
            page.wait_for_timeout(ASSEMBLY_MS)
            if page.evaluate("() => world.getState().assemblyTarget") != 1:
                problems.append("setAssembly(1) does not set getState().assemblyTarget to 1")
            page.evaluate(
                "() => { world.setAssembly(0); document.getElementById('world').dispatchEvent(new CustomEvent('themechange', {detail: {dark: true}})); }"
            )
            page.wait_for_timeout(PLAY_MS)
            # The same lessons in a phone-sized world panel: everything still visible, tagged and apart.
            page.set_viewport_size({"width": PHONE_VIEWPORT[0], "height": PHONE_VIEWPORT[1]})
            page.evaluate("([w, h]) => Object.assign(document.getElementById('visual').style, {width: w + 'px', height: h + 'px'})", list(PHONE_PANEL))
            page.evaluate(
                "() => { const v=document.getElementById('visual'), w=document.getElementById('world'), host=w.closest('.specimen-shell')||w; const extras=[...v.children].filter(e=>e!==host).reduce((s,e)=>s+e.getBoundingClientRect().height+12,0); v.style.height=Math.max(v.clientHeight,(parseFloat(getComputedStyle(w).minHeight)||0)+extras)+ 'px'; }"
            )
            for index, lesson in enumerate(lessons, 1):
                name = f"phone, lesson {index} ({lesson['id']})"
                page.evaluate("(scene) => { world.setLesson(scene); world.setParams(scene.params); }", lesson["scene_state"])
                page.wait_for_timeout(SETTLE_MS)
                facts = page.evaluate(MEASURE, lesson["scene_state"]["visible"])
                problems += layout_problems(name, scene, lesson["scene_state"]["visible"], facts)
                page.locator("#visual").screenshot(path=str(shots / f"lesson-{index}-phone.png"))
                shown[index - 1]["phone_screenshot"] = f"render/lesson-{index}-phone.png"
            problems += [f"browser error: {message}" for message in dict.fromkeys(errors)]
            problems += [f"world.js requested {url}; worlds make no network requests" for url in dict.fromkeys(blocked)]
        except PlaywrightError as error:
            problems.append(f"the world stopped responding: {error.message.splitlines()[0]}")
        finally:
            browser.close()
    report = {"lessons": shown, "isolation": isolation}
    (run_dir / "render" / "report.json").write_text(json.dumps({**report, "problems": problems}, indent=2))
    return report, problems
