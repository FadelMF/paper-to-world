# CODEMAP

Map of Paper-to-World for whoever works on it next: where each part lives and the layout rules it follows.

## Folder and file map

```text
pyproject.toml               Package metadata, dependencies, ruff (lint, format) and pyright settings
app/                         FastAPI backend (Python); app/__init__.py reads .env before any module reads settings
  main.py                    Routes: / (Home), /demo, /demo/3d, /demo/attention/2d, /demo/attention/3d (lesson shell), /learn/{run}, /build/{run},
                             /api/config, /api/runs (create, list, status, cancel, retry, files, ask), /assets (static/).
                             Worker queue (PAPER_MAX_WORKERS / PAPER_MAX_PENDING_RUNS), bounded tutor concurrency,
                             resume-from-checkpoint retries, run retention,
                             optional entry gate, private guest sessions, persisted rate/budget limits and CSP-isolated generated worlds
  pipeline.py                [Transcriber] → Analyst → [Proofreader] → figures → [Viewer] → Observer → Planner → Modeler →
                             Validator → Porter → Designer → Writer → Builder + render check → [Critic]  ([ ] = vision);
                             until_valid() repair loop, checkpoint() per stage; writes status.json and artifacts
  agents.py                  Agent prompts and calls; repairable agents take (previous, error); Tutor retrieval (BM25)
  visual.py                  Evidence normalization (quote and figure-element checks), scene validation, figure anchors
  parity.py                  model.py run() vs model.js in Node: parity cases, reference states, mismatch report
  sandbox.py                 Runs model-written code under Landlock (or the explicit PAPER_SANDBOX=guard); availability
  confine.py                 Landlock (files, TCP ports) and seccomp (sockets, io_uring) for child processes, no root
  figures.py                 Renders figure pages (pypdfium2); cuts out captioned figures and drawings no caption claims
  render_check.py            Opens a candidate world.js in confined headless Chromium: plays, measures, photographs lessons
  lesson_contract.py         Pydantic contract for lessons.json (validate_lessons) and world.js checks (validate_world)
  evaluation.py              Per-run quality summary read from artifacts (scripts/evaluate.py)
  demo.py                    DemoProvider: replays a prepared example's stored stage answers through the real pipeline
  worker.py                  One OS process per run; uses DemoProvider for example walkthroughs
  store.py                   SQLite session/password hashes, optional accounts, run ownership, persistent admission history and provider reservations
  llm.py                     OpenAI-compatible client (text: LLM_*, images: VISION_*); tolerant JSON and code-block reading
  pdf.py                     PDF reading and cleaning, figure captions and mentions, references removal, page-bounded parts
  errors.py                  PublicError: a failure whose message the learner sees; NoTextLayer for scans
static/
  index.html                 Home page markup (example picker: 2d, 3d, attention2d, attention3d)
  home/home.js, home/style.css   Home behaviour and layout: tabs, example picker, live preview, upload, availability
  account/                   Optional username/password registration, sign-in and sign-out
  worlds/                    "Your worlds" page (/worlds): saved-runs list
  build/                     Progress page: vertical stepper and independently scrolling discoveries
  ui/app.css, ui/app.js      Shared tokens (light/dark), header, buttons, icons, theme toggle, localStorage helpers
  lesson/index.html          Lesson shell markup (used by /demo*, /learn/{run})
  lesson/isolated-world.js   Parent-side simulation proxy; no generated code is evaluated here
  lesson/frame.html, frame.js, frame.css   Opaque sandbox frame, restricted HTTP CSP and MessageChannel simulation controls
  lesson/shell.js            Lesson shell: loads lessons.json, world.js, scene.json, evidence.json; left panel, dock, tutor,
                             shape sources, paper-figure dialog; the `demos` table maps example routes to their folders
  lesson/style.css           Lesson layout (context bar, reading column, world panel, dock, menu, tutor, figure dialog)
  lesson/world.css           Everything drawn inside #world by a world module: tags, leaders, top row, plot, tools
  lesson/neuron-parts.js     Seven-part neuron teaching inventory shared by the two neuron examples
  lesson/specimen.js         Assemble/Explode/Anatomy controls and inspector of the two neuron examples
  vendor/                    three.js 0.170.0 (+ OrbitControls, RoomEnvironment), KaTeX 0.19.1, Inter; unmodified, with
                             their licenses; the pages' import maps and stylesheets point here, so nothing loads from a CDN
  demo/, demo3d/, attention2d/, attention3d/    Prepared examples. Each holds every stage's answer as a file: analysis.json, evidence.json,
                             plan.json, model.py, validation.json, model.js, scene.json, lessons.json, world.js, plus
                             paper.pdf and tutor.json (stored tutor answers). demo3d's model files link to demo/.
                             used for the vision steps)
scripts/                     check.sh (every check), check_provider.py (local prerequisites / opt-in live text+image probe),
                             live_run.py (one paper in the foreground), evaluate.py (several
                             papers, quality summary), build_demo_notes.py (regenerates the neuron examples' PDFs)
tests/                       unittest suites (test_*.py), Playwright browser scripts (browser_*.py) and their runner
                             (run_browser_tests.py), harness.py (shared browser-script helpers),
                             paper_fixture.py (fixture PDF, ScriptedLLM), fake_llm_server.py
                             (OpenAI-compatible fake, optional fixture folder), vendor/axe.min.js (accessibility audit)
docs/                        Visual workflow, builder contract, upload/progress, Explode behaviour, STATUS.md
runs/                        Saved runs, one folder each (not versioned)
```

## Home page

- Header: `<header data-app-header>` is filled by `static/ui/app.js` (brand, Start / Your worlds nav, context text, theme button). It uses the shared page padding `--page-pad`.
- `main.home` is a two-column grid filling `100dvh − header`:
  - left column `.home-side` (scrolls on its own only when it overflows): hero (`h1` + one line), resume link, the start card (tabs *Explore examples / Use your paper*, example picker radios, *Open this example*). *Your worlds* lives on `/worlds`.
  - right column `.world-panel` (fixed, fills its column): the example's **lesson 1 world**, drawn by that example's own `world.js`, plus lesson 1's figure caption and lesson 1's controls.
- `home.js` imports `<example>/world.js` directly into `#world` and applies `lessons[0].scene_state`. Examples are listed in its `examples` table (title, route, folder, optional note). Selection: `?example=`, else the example of the last opened lesson, else 2D. Choosing another example reloads Home with `?example=<key>`, so the previous world module and its animation loop are discarded completely.
- The availability line under *Use your paper* shows `/api/config`'s `problem` when papers cannot be built (no model, no Node.js, no kernel isolation).
- Every response carries `Cache-Control: no-cache` (`app/main.py` middleware), so a refresh never mixes old and new HTML/CSS/JS.

## Lesson view

- `lesson/index.html` + `shell.js`. Header, then `.lesson-context` (paper title, demo note), then `#workspace` (grid: `#reading` left, `#visual` world panel right), then the fixed `.lesson-dock` (lesson list, previous/next, play/pause, listen, focus view).
- `#reading`: lesson path buttons, lesson text, KaTeX equation, terms, prediction + reveal, sliders, challenge, source note, tutor button. Scrolls on its own.
- `#visual` (`.world-panel`): heading row (dimension badge, "Explore the idea", running status), `#world`, figure caption.
- Under the caption, `#shape-sources` lists the visible objects drawn from the paper (with page, from `scene.json` + `evidence.json`), the illustrative ones (rationale on hover), and buttons for the paper figures they cite, which open `#figure-viewer` (figure image, caption, link to its PDF page). Hidden when a run has no `scene.json`.
- `shell.js` loads `lessons.json` and `world.js` from the example's folder (`/assets/demo/`, `/assets/demo3d/`, `/assets/attention2d/, attention3d/`) or `/api/runs/{id}/files/`. An example's paper attribution is shown beside the paper title, also on walkthrough runs. It calls `world.setLesson(lesson.scene_state)` on every lesson change and `world.setParams` on slider input.

## Renderers

| Example | Route | Lessons | World module | Renderer |
|---|---|---|---|---|
| How a neuron fires | `/demo` | `static/demo/lessons.json` | `static/demo/world.js` | Canvas 2D, `dimensionality = 2` |
| Inside a neuron | `/demo/3d` | `static/demo3d/lessons.json` | `static/demo3d/world.js` | three.js WebGL, `dimensionality = 3`, uses `lesson/specimen.js` |
| Generated run | `/learn/{id}` | `runs/{id}/lessons.json` | `runs/{id}/world.js` + `model.js` | whatever the Planner chose; checked by `validate_world` and `check_port` |

The same module draws the Home preview and the Lesson world; there is no separate preview renderer. Each `scene_state` (`visible`, `camera`, `params`) is applied by the module's `setLesson`. The 2D module uses `visible` to fade objects and tags and `camera` as a 2D pan/zoom preset; the 3D module uses `visible` for tags/leak/plot and `camera` as the view direction for camera fitting.

Inside `#world`, each neuron module draws a top row (hint and Assemble/Explode/Anatomy controls), the scene, compact labels, a membrane-potential plot, and explore tools. Both neuron examples import the seven teaching parts from `lesson/neuron-parts.js`. In 2D Explode, the seven parts separate into a numbered row over 400 ms; `renderParts()` packs their live labels into lanes outside the shape bounds and draws leaders plus a dashed directional path. Assembled lesson tags still use `placeLabels()`. Anatomy and part/label clicks open the shared live inspector and highlight the lesson term without scrolling the page. The shared specimen shell wraps the model and inspector inside the right panel. A container query docks Anatomy beside the model at 720 px of specimen width, otherwise below it. Summary metrics are restored on Close; Focus and Reset keep inspection open. Resizing the dock preserves an explicitly focused 3D camera target. The 3D inspector also retains detailed organelles. The simulation runs in every mode. Compact 2D panels scroll internally, with their plot below the labels.

In the two neuron examples, spike numbers have one source: the world counts spikes in the first second of the current run (0–1000 ms of simulated time after the last reset, the same window as the Python reference targets). Tags, the plot title, `getState().spikesFirstSecond`, and the lesson text all use that window.

## Shared layout and CSS

- `--page-pad: clamp(20px, 3vw, 48px)` (in `ui/app.css`) is the only horizontal page padding. Header, Home `main`, lesson context bar, lesson workspace and dock all use it, so content left edges line up with the logo and right edges with the theme button. No max-width: both pages use the full viewport width.
- Desktop lessons (above 760 px) and prepared worlds use a fixed-height workspace: the reading scrolls independently, and the right simulation panel retains its viewport position. Long right-hand inspections scroll inside their panel. Home keeps its 900 px breakpoint.
- Below 900 px Home stacks and the page scrolls normally. Lessons keep their 1050/760 px breakpoints; on phones prepared worlds stack above the reading and use document scrolling.
- `.world-panel` (in `ui/app.css`) is the shared card for the right column on both pages: surface background, 1px line border, 14 px radius.

---

## Known limits

- Under software WebGL (headless tests) the 3D simulation runs slower than real time, so reaching 1000 ms takes a few minutes; with a GPU it runs at the normal 0.12× teaching speed.

The Transformer examples live in `static/attention2d/` and `static/attention3d/`. Shared interaction code is in `static/attention-common/`; flat.js draws the connected architecture map and spatial.js draws the encoder/decoder stacks; runtime.js shows six distinct numerical/evidence inspections. `scripts/check_teaching_examples.py attention2d attention3d` validates both through the complete pipeline.

`app/teaching.py` checks paper-topic coverage against the plan and real lesson IDs. New lesson learning contracts carry objective/action/observation/mechanism/test inputs/computed outcome. `render_check.py` executes those interactions. `static/lesson/neuron-explanation.js` explains the actual neuron state beside its diagram.

`static/ui/dropdown.js` enhances selects in the lesson, home preview and anatomy inspector with shared themed listboxes. `app.js` observes added controls; `specimen.js` also initializes its picker directly for standalone render checks. `tests/browser_information_panels.py` checks keyboard/mouse interactions, model updates, disclosures and phone bounds.

`app/security.py` bounds streamed request bodies and checks production deployment settings / single-process ownership. `app/quality.py` blocks publication of failed or missing required numerical results. `uv.lock` pins Python dependencies; `static/vendor/versions.json` records frontend dependency versions.
