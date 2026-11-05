# Visual workflow: from paper to a drawn and reviewed 2D/3D world

A world is not drawn from a summary. Each stage reads the previous stages' structured output, and a check sits between stages. Reference execution, browser-port, scene, lesson and world checks return failures to their generating agent with its previous answer and the exact problem, at most twice (`FIX_ATTEMPTS`). Other contract/publication failures stop the run; details go to `debug.log`.

Two models can be configured. The text model (`LLM_*`) runs every agent that reads and writes text and code. The vision model (`VISION_MODEL`, with `VISION_BASE_URL` and `VISION_API_KEY` defaulting to the `LLM_*` values) runs the four agents that look at images: Transcriber, Proofreader, Viewer and Critic. Without a vision model those four are skipped and the rest still runs (see "Without a vision model").

| # | Stage | Reads | Writes | Check before the next stage |
|---|---|---|---|---|
| 0 | ETL (no model) | `paper.pdf` | `pages.json` | Text cleaned; references dropped; split into parts of `PAPER_MAX_CHARS` at page boundaries |
| 0a | Transcriber (vision; scans only) | page images | `pages.json` | At least one page with text, else the scan is refused |
| 1 | Analyst | paper text, in parts when long | `analysis.json` | Parts merged without duplicates; at least one concept or equation (`validate_analysis`) |
| 1a | Proofreader (vision) | each cited page image + its equations | `analysis.json` | Printed LaTeX replaces the reconstruction; `checked`: `page` or `not_found` |
| 2 | Figures (no model) | `paper.pdf` + captions | `figure-<id>.png` | Every captioned figure, plus drawings no caption claims; each cut from its rendered page |
| 2a | Viewer (vision) | page image + first cut + caption + mentions | readings in `evidence.json` | Up to `PAPER_MAX_READ_FIGURES`, most mentioned first. A usable box replaces the first cut; elements must be named; element boxes are kept when usable |
| 3 | Observer | paper text + figures with readings | `evidence.json` | Quotes searched in the text; figure elements searched in the readings (`visual.normalize_evidence`) |
| 4 | Planner | analysis + evidence | `plan.json` | One modality, one matching view (`validate_plan`) |
| 5 | Modeler | analysis + plan | `model.py`, `model_output.txt` | Runs isolated; last line `{"metrics": ...}`; `run(params, steps)` returns a state dict for every parity case |
| 6 | Validator | claims + targets + output | `validation.json` | Statuses normalized |
| 7 | Porter | plan + `model.py` | `model.js`, `parity.json` | Pure module; in Node, `run()` and a manual `createModel` + `advanceModel` loop both match Python (`parity.check_port`) |
| 8 | Designer | analysis + evidence + plan + model state | `scene.json` | `visual.validate_scene` (below) |
| 9 | Writer | analysis + plan + validation + scene + state | `lessons.json` | `validate_lessons`: lesson contract, scene IDs only, model parameters only |
| 10 | Builder | plan + scene + lessons + `model.js` + state | `world.js`, `render/` | `validate_world`, then the render check (below) |
| 11 | Critic (vision) | lesson screenshots + cited figures + scene + evidence | `critique.json` | Major issues go back to the Builder (up to `CRITIC_ROUNDS` = 2); each redraw passes the render check again |

## Reading the paper's figures

`pdf.figure_captions` finds captions in the text: "Figure 1:", "Fig. 2.", "Fig 3", "FIGURE 4 |", "Figure S1." and "Extended Data Fig. 2 |" (ids `fig1`, `figS1`, `figED2`). Drawings that no caption claims become figures too (ids `figP3a`: page 3, first one) when they cover at least 4% of the page and look like a picture: a raster image or form, or at least three shapes with both width and height. Equations, tables and algorithm boxes are mostly thin rules and bars, so they are left out. With a vision model, the `PAPER_MAX_READ_FIGURES` figures the text mentions most are read; the rest are still cut out and shown.

`figures.render_figures` renders each figure's page with pypdfium2 at 144 dpi. Rendering whole pages captures vector drawings, which most arXiv diagrams are. The first cut is a layout guess. Starting at the caption, it gathers the drawing objects stacked above it (paths, images, shadings, forms):

- **Joining.** The first drawing must lie within 10% of the page width of the caption's sides and within 5% of the page height above it. After that, a drawing joins only when it is that close vertically and touches the region sideways (within 2%). A neighbouring column stays out.
- **Forms that run on.** A form whose box runs on through the caption's whitespace counts when most of its height is above the caption, and is cut at the caption.
- **Wrapper forms.** Forms that wrap most of the page are opened, and their contents are mapped to page coordinates.
- **Fallback.** If no drawing is found, the whole page is used.

On four arXiv papers (Adam, Transformer, Neural ODE, DDPM), 43 of 44 figures got a figure-sized cut. The exception, DDPM Fig. 6, has no drawing within reach of its caption.

The **Viewer** sees the whole page, the first cut, the caption and the sentences that mention the figure. It returns a tight box (which replaces the first cut), the figure's kind, what it depicts, its layout, its elements (shape, color, position, box on the page, count, printed label, connections) and plot axes. It is told to report only what is visible, not what it knows about the subject.

## What comes from the paper and what is an idea

The **Observer** collects everything the paper says or shows about how things look. Each entity is checked:

- `verified_by: "text"`: its `quote` appears in the extracted text (case and punctuation ignored).
- `verified_by: "figure"`: it cites a figure that was read, and the `element` it names is in that figure's reading.
- `verified_by: null`: neither; it cannot ground a shape.

The **Designer** works in three moves:

1. **Visual needs**: what the learner must see for each concept ("see the voltage approach the threshold"), each answered by named objects.
2. **Paper first**: objects the paper describes get `"basis": "paper"` and `"evidence"` naming a verified entity or a figure.
3. **Ideation**: where the paper is silent, the Designer proposes a depiction with `"basis": "hypothesis"`, no evidence, and a `rationale` saying why the form helps and how it stays faithful.

`validate_scene` rejects, all in one report: duplicate or malformed IDs, primitives outside the selected modality (2D: circle, ellipse, rect, line, polyline, path, arrow, text, plot, particles, group; 3D: sphere, box, cylinder, cone, capsule, torus, tube, plane, lathe, points, plot, group), positions with the wrong number of axes, unknown parents, paper objects without verified evidence, hypotheses without a rationale, bindings to keys the model state does not have, needs naming unknown objects, fewer than 3 objects, no live binding at all, and a scene made only of hypotheses when the paper does describe some shapes. Scene coordinates have y pointing up.

## How the drawing stays tied to the simulation

`model.js` is written and checked **before** the scene is designed. The Designer and Builder get its actual state keys and example values, so each binding (`{"state": "V", "property": "fill", "map": "-65 mV muted to -50 mV accent"}`) refers to a value that really exists. The Builder imports `model.js` instead of re-writing the equations, so what moves on screen is the checked model.

Parity cases (`parity.parity_cases`): default parameters after 1, 20 and 1000 steps, then each of the first four controls at its min and max for 1000 steps. Tolerance: `|a − b| ≤ 1e-6 + 1e-3·|b|`; booleans must agree; non-finite values must agree.

## Looking at the world before a learner does

`render_check.check_render` opens the candidate `world.js` (served from memory; nothing is saved until it passes) in headless Chromium, in a separate process confined by Landlock and seccomp (see the README's limits), beside the run's `model.js` and the shared lesson library, exactly as the lesson shell loads it. The browser process cannot open network sockets; three.js comes from `static/vendor` through the same import map as the lesson shell, and any request to another host is blocked and reported. For every lesson it applies the scene state, plays, and checks:

- `getState().time` advances while playing; `step()` advances it while paused; `setAssembly(1)` sets `assemblyTarget`.
- Each visible object has a box from `objectBounds()` that is at least 1 px and inside the world, and a visible, keyboard-focusable tag with `data-object="<id>"`.
- Tags of visible objects do not cover each other (more than 30% of the smaller one).
- In 2D, objects that are apart in the scene keep their left/right and above/below order on screen.
- Paper-based objects whose evidence names an element with a box in a read figure keep that figure's order: if the paper's figure puts the soma left of the axon (by more than 15% of the figure), the world must too. Checked in every 2D lesson and in the first 3D lesson; later 3D lessons may turn the camera.
- Each control's maximum, passed to `setParams`, shows up in `getState()`.
- The lesson's `check_js` evaluates against `getState()` without throwing.
- No page errors or console errors, including after a dark-theme switch.

Then it shrinks the world panel to a phone's (358×340 px in a 390 px wide window) and checks every lesson's visibility, tags and order again. It saves `render/lesson-N.png`, `render/lesson-N-phone.png` and `render/report.json`. An object counts as drawn when at least half of its box is inside the world. 2D canvas and compositing run in software and WebGL in SwiftShader: about 9 s for the 2D example and 23 s for the 3D one on a server without a GPU. Every problem is listed in one report for the Builder. 

The **Critic** then sees up to 6 lesson screenshots and up to 4 of the paper's figures that the scene's paper-based objects cite (directly or through their evidence entity), with the scene and evidence. It lists issues as `major` (misrepresents the paper or blocks understanding) or `minor`. Major issues go back to the Builder as a repair; the new world must pass the render check again, then the Critic looks again. Unresolved major issues after two rounds, or a failed major correction, block publication. The issue report remains in `critique.json` for diagnosis. Minor issues alone do not block publication.

## Scanned papers and printed equations

A PDF with no text layer raises `NoTextLayer`. With a vision model, the **Transcriber** reads each page image (all of them, or the first `PAPER_MAX_SCANNED_PAGES`) into text with LaTeX math and captions on their own lines; the rest of the pipeline treats that text like extracted text. Without one, the scan is refused with a plain message.

The Analyst reconstructs equations from garbled extracted text. The **Proofreader** sees the page each equation is cited on (one call per page) and returns the LaTeX as printed, or says it is not on that page. Corrected equations flow into the lessons.

## When the server cannot build papers

`/api/config` reports `generation_available` and, when it is false, a `problem` the home page shows: no model configured, no Node.js, or no kernel isolation (Landlock). Creating or retrying a run is refused with the same message.

## Without a vision model

Figures are still cut out by the layout guess, saved and shown to the learner. Shapes count as paper evidence only through text quotes and figure ids from captions. Scans are refused. Equations keep the Analyst's reconstruction. The render check still runs; the Critic does not.

## What the learner sees

The progress screen reports, among others: "Noted 6 parts the paper describes, looking closely at its 1 figure", "Checked 3 equations against the printed page", "Your browser simulation matches the reference in all 7 checks", "Sketching 7 parts: 6 drawn from the paper, 1 illustrative", "Drew 7 parts and checked every lesson in a browser" and "Compared your world with the paper and 1 of its figures".

In the lesson, a line under the figure caption lists the visible shapes drawn from the paper (with page), the illustrative ones (rationale on hover), and buttons for the paper's figures they cite. A figure opens in a dialog with its caption and a link to its page in the PDF.

## Artifacts per run

`pages.json`, `analysis.json`, `figure-<id>.png`, `evidence.json`, `plan.json`, `model.py`, `model_output.txt`, `validation.json`, `model.js`, `parity.json`, `scene.json`, `lessons.json`, `world.js`, `render/lesson-N.png`, `render/report.json`, `critique.json` (vision), `status.json`, `debug.log`.

The prepared examples (`static/demo`, `static/demo3d`) ship authored `evidence.json` and `scene.json` and go through the same checks. In the 2D example, the firing-rhythm tag is a hypothesis, because the notes report spike counts but draw no terminals.

## Running safely and recovering

- Model-written Python and JavaScript run confined by Landlock and seccomp, with an in-process second layer (`app/sandbox.py`, `app/confine.py`). The render check's browser runs in its own confined process.
- Successful stages save their results in `checkpoints/`. Retrying starts a new run using those checkpoints; `?fresh=true` starts over. A required numerical validation failure invalidates the rejected reference and its downstream checkpoints, so retry regenerates the model.
- At most `PAPER_MAX_WORKERS` runs build at once; the others wait in line with their place shown.

## Publication boundary

Required planned numerical targets must each have one passing result and a finite measured metric. Numeric expected values are checked with numeric tolerances when available. Extra source-only experiments may remain explicitly unmeasured. Parity and browser checks establish implementation consistency, not scientific correctness. The current deployment limits and verification are in [production-audit.md](production-audit.md).
