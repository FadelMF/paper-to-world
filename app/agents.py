"""The agents of Paper-to-World, in pipeline order.

Transcriber -> turns the page images of a scanned PDF into text (vision)
Analyst   -> reads the paper, extracts concepts, equations, mechanisms, claims, parameters
Proofreader -> checks each extracted equation against an image of its page and corrects the LaTeX (vision)
Viewer    -> looks at each figure (vision): where it is on the page, its elements, layout and axes
Observer  -> reads the paper and the figure readings for how things look: parts, shapes, sizes, layout
Planner   -> picks exactly one of 2D or 3D and writes the simulation spec + validation targets
Modeler   -> writes a Python reference model (numpy/scipy) with run(params, steps) and metrics
Validator -> compares measured metrics with the paper's claims
Porter    -> ports the reference into a pure model.js, checked number-for-number against Python
Designer  -> maps visual needs to scene objects, each drawn from paper evidence or a labelled hypothesis
Writer    -> writes lessons.json over the scene objects
Builder   -> draws the scene in world.js, animated by model.js
Critic    -> looks at screenshots of the world beside the paper's figures (vision) and lists what to fix
Tutor     -> answers learner questions grounded in the paper pages

Agents that can be sent back take `previous` (their last answer) and `error` (why it failed a check).
"""

import json
import math
import re

from app import llm
from app.llm import chat, chat_json, extract_block
from app.teaching import validate_coverage
from app.visual import PRIMITIVES, page_number, squash


def dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)


def revise(user, previous, error, fence):
    """The original request, plus the failed answer and the reason when this is a repair."""
    if error is None:
        return user
    shown = previous if isinstance(previous, str) else dump(previous)
    return (
        user
        + "\n\nYour previous answer failed this check:\n"
        + error
        + (f"\n\nPrevious answer:\n```{fence}\n{shown}\n```" if previous is not None else "")
        + "\n\nFix every problem and return the complete corrected answer."
    )


# ---------------------------------------------------------------- Analyst

ANALYST = """You are the Analyst agent of Paper-to-World, a platform that turns scientific papers into interactive simulations.

Read the whole paper before choosing a simulation. Inventory its architecture/components, mechanisms, data flow, experimental setup, findings and limitations. A runnable submodel is only one part of teaching the paper. Never reduce an architecture paper to a single equation.

Rules:
- Use only what is in the paper. Never invent results or numbers.
- Write equations in LaTeX. PDF text extraction garbles math, so reconstruct equations from context; set "reconstructed": true when you had to.
- Give the page number for every item (the text has [page N] markers).
- A long paper comes in parts ("[part i of n: pages a-b]"); extract what this part contains. Parts are merged afterwards.
- For each parameter, "source" is "paper" when the value is stated in the paper, otherwise "assumed".

JSON shape:
{
  "title": "...",
  "authors": "...",
  "domain": "e.g. computational neuroscience, deep learning",
  "one_line_summary": "...",
  "learning_topics": [{"id":"architecture", "title":"System architecture", "page":3, "required":true}],
  "concepts": [{"name": "...", "explanation": "plain-language, 2-3 sentences", "page": 1}],
  "equations": [{"id": "eq1", "latex": "...", "meaning": "...", "reconstructed": false, "page": 1,
                 "variables": [{"symbol": "...", "meaning": "...", "units": "..."}]}],
  "mechanisms": [{"name": "...", "steps": ["..."], "page": 1}],
  "claims": [{"id": "c1", "statement": "...", "value": "number with units, or null if qualitative", "page": 1}],
  "parameters": [{"symbol": "...", "name": "...", "default": 0, "min": 0, "max": 0, "units": "...", "source": "paper"}]
}"""


def validate_analysis(analysis):
    """Keep only usable items, so later stages and the progress screen can rely on the shape."""
    result = dict(analysis)
    result["title"] = str(analysis.get("title") or "").strip()
    result["authors"] = str(analysis.get("authors") or "").strip()
    result["concepts"] = [dict(c) for c in analysis.get("concepts") or [] if isinstance(c, dict) and str(c.get("name") or "").strip()]
    result["equations"] = [dict(e) for e in analysis.get("equations") or [] if isinstance(e, dict) and str(e.get("latex") or "").strip()]
    for key in ("claims", "mechanisms", "parameters"):
        result[key] = [dict(item) for item in analysis.get(key) or [] if isinstance(item, dict)]
    for item in result["concepts"] + result["equations"] + result["claims"] + result["mechanisms"]:
        item["page"] = page_number(item.get("page"))
    if not result["concepts"] and not result["equations"]:
        raise ValueError("The analysis found no concepts or equations to build from")
    return result


def analyze(paper_text):
    result = chat_json(ANALYST, paper_text)
    if not result.get("learning_topics"):
        raise ValueError("The Analyst must inventory learning_topics across the paper before simulation planning.")
    return result


def merge_analyses(parts):
    """One extraction from the extractions of a long paper's parts: lists joined without duplicates,
    equations and claims numbered again (eq1.., c1..) so ids stay unique."""
    if len(parts) == 1:
        return parts[0]
    merged: dict = {key: next((p.get(key) for p in parts if p.get(key)), "") for key in ("title", "authors", "domain", "one_line_summary")}
    for key, identity in (
        ("learning_topics", "id"),
        ("concepts", "name"),
        ("equations", "latex"),
        ("mechanisms", "name"),
        ("claims", "statement"),
        ("parameters", "symbol"),
    ):
        seen, items = set(), []
        for item in (i for p in parts for i in p.get(key) or [] if isinstance(i, dict)):
            mark = squash(item.get(identity) or "")
            if mark and mark not in seen:
                seen.add(mark)
                items.append(dict(item))
        merged[key] = items
    for prefix, key in (("eq", "equations"), ("c", "claims")):
        for number, item in enumerate(merged[key], 1):
            item["id"] = f"{prefix}{number}"
    return merged


def merge_evidence(parts):
    """One evidence answer from a long paper's parts: the first entity with each id is kept."""
    if len(parts) == 1:
        return parts[0]
    seen, entities = set(), []
    for entity in (e for p in parts for e in p.get("entities") or [] if isinstance(e, dict)):
        if entity.get("id") not in seen:
            seen.add(entity.get("id"))
            entities.append(entity)
    return {"subject": next((p.get("subject") for p in parts if p.get("subject")), ""), "entities": entities}


# ---------------------------------------------------------------- Transcriber

TRANSCRIBER = """You are the Transcriber agent of Paper-to-World. The paper is a scan with no text layer; you read one page image.

Transcribe all text on the page in reading order (columns left to right). Keep paragraph breaks as blank lines. Write equations in LaTeX between $...$. Keep each figure or table caption on its own line, starting exactly as printed (e.g. "Figure 2: ..."). Skip running headers and page numbers. Do not summarize, translate or add anything.

Reply with the page text only."""


def transcribe(number, page_png):
    return llm.chat_vision(TRANSCRIBER, f"Page {number}.", [page_png])


# ---------------------------------------------------------------- Proofreader

PROOFREADER = """You are the Proofreader agent of Paper-to-World. Text extraction garbles printed math, so equations were reconstructed from context. You see the page each one is cited on.

For each equation, find it on the page image. If it is there, give the LaTeX exactly as printed (same symbols, sub- and superscripts, order). If it is not on this page, say so; do not invent one.

JSON shape:
{"equations": [{"id": "eq1", "found": true, "latex": "as printed, or null when not found", "note": "what you corrected, if anything"}]}"""


def proofread(page_number, page_png, equations):
    user = f"Page {page_number}. Equations cited on this page:\n" + dump([{k: e.get(k) for k in ("id", "latex", "meaning")} for e in equations])
    return chat_json(PROOFREADER, user, images=[page_png])


# ---------------------------------------------------------------- Viewer


def vision_available():
    return llm.vision_configured()


VIEWER = """You are the Viewer agent of Paper-to-World. You look at one figure of a scientific paper so that a later agent can draw the paper's subject the way the paper draws it.

You get two images: the whole page, then a first guess at the figure's area (it may be off). You also get the caption and sentences that mention the figure.

Report only what is visible. Do not add parts from your own knowledge of the subject. Copy printed labels exactly.

JSON shape:
{
  "box": [x0, y0, x1, y1],   // the figure on the PAGE image as fractions 0-1 from the top left; tight around the drawing, without the caption
  "kind": "diagram|plot|photo|table|mixed",
  "depicts": "one or two sentences",
  "layout": "the overall arrangement and flow, e.g. inputs on the left feed a round body in the middle, output to the right",
  "elements": [{"name": "...", "appearance": "shape, color, line style, relative size", "position": "where in the figure",
                "box": [x0, y0, x1, y1],   // the element on the PAGE image, same coordinates as "box" above
                "count": 1, "label": "text printed on or next to it, or null", "connections": ["what it touches or points to"]}],
  "axes": [{"axis": "x", "label": "...", "units": "...", "range": [0, 1]}]   // plots only; [] otherwise
}"""


def read_figure(figure, page_png, crop_png, mentions):
    user = (
        f"Figure {figure['id']} on page {figure['page']}.\nCaption: {figure['caption'] or '(none: a drawing found on the page without a numbered caption)'}"
        + "\n\nSentences that mention it:\n"
        + dump(mentions)
        + "\n\nImage 1: the whole page. Image 2: the first guess at the figure area."
    )
    return chat_json(VIEWER, user, images=[page_png, crop_png])


# ---------------------------------------------------------------- Observer

OBSERVER = """You are the Observer agent of Paper-to-World.

Read the paper, its figure captions and the readings of its figures for everything that says how the subject LOOKS, so a later agent can draw it from the paper rather than from imagination.

Collect entities: each physical part, signal, quantity or process the learner should see. Describe its appearance (shape, structure, count, arrangement), dimensions or scale with units when stated, and its spatial relations to other entities.

Rules:
- Ground each entity in the paper. "quote" is a short verbatim phrase from the paper text that supports it (copy it exactly; it is checked against the text), or null. When a figure shows it, set "figure" to the figure id and "element" to the element's name as given in that figure's reading (it is checked against the reading).
- Prefer what the figures show for shape and layout; prefer the text for numbers and units.
- Never invent sizes or numbers. Use null for unknown dimensions.
- Use lowercase snake_case ids. Give page numbers (the text has [page N] markers).
- Abstract subjects (algorithms, fields, networks) still have visible constituents: list those, e.g. layers, tokens, vectors, axes.

JSON shape:
{
  "subject": "one sentence: what system is depicted and its overall form",
  "entities": [{"id": "soma", "name": "...", "kind": "structure|signal|quantity|process",
                "appearance": "...", "dimensions": "value with units, or null", "relations": ["..."],
                "page": 2, "quote": "... or null", "figure": "fig1 or null", "element": "element name or null"}]
}"""


def observe(paper_text, figures):
    shown = [{k: f.get(k) for k in ("id", "page", "caption", "reading")} for f in figures]
    return chat_json(OBSERVER, paper_text + "\n\nFigures (caption, and a reading of the image when available):\n" + dump(shown))


# ---------------------------------------------------------------- Planner

PLANNER = """You are the Planner agent of Paper-to-World.

Given the Analyst's extraction, design ONE interactive simulation that lets a learner experience the paper's core mechanism.

You also get the Observer's visual evidence: what the paper says the subject looks like. Use it to decide whether spatial form matters.

Choose the representation by reasoning about the knowledge itself, not the field name:
- "2d": dynamics of a few variables over time, curves, phase planes, heatmaps, matrices, 2D fields.
- "3d": the idea lives in space — geometry, 3D structures, trajectories or landscapes in 3 dimensions, embeddings.
- Choose exactly ONE modality and ONE view for the entire document. Never produce hybrid, both renderers, alternate versions, or a dimension switch. Prefer 2D when spatial depth is not essential; use 3D only when it materially helps explain the core idea.

Scope the COMPUTATION to run in the browser, but cover the WHOLE PAPER in the teaching sequence. Map every learning_topic to a lesson: simulated, explained with source evidence, or explicitly excluded with a reason (only optional topics may be excluded). Do not drop encoder/decoder architecture to teach attention alone. Explain experiments/training/results without pretending to reproduce costly training. One renderer can contain a coherent architecture overview and progressive detail views.
Controls must create an observable difference across a useful range. Use binary choices for true on/off settings, not artificial wide sliders. For continuous controls give units, a source-backed or explicitly illustrative range, and a meaningful baseline. Never widen a physical or safety bound just for visual drama.
Every guided step must state the causal chain: input -> transformation -> observable output, the learner's action and what changes on screen. A clock advancing on a static calculation is not a simulation. For feed-forward computation, animate actual computational stages and label this as a forward-pass walkthrough.

Validation targets must be measurable by running the model, and tied to claims from the paper.

JSON shape:
{
  "modality": "2d" | "3d",
  "rationale": "one short learner-facing sentence about what this view makes visible; no internal implementation terminology",
  "core_model": "which equations/mechanism are simulated",
  "coverage": [{"topic":"architecture", "mode":"simulated", "lessons":["architecture"], "reason":""}],
  "simplifications": ["..."],
  "state_variables": [{"name": "...", "meaning": "...", "initial": 0}],
  "update_rule": "pseudo-code of one simulation step (name the integrator, e.g. RK4, and dt)",
  "controls": [{"symbol": "...", "label": "...", "min": 0, "max": 0, "step": 0, "default": 0}],
  "views": [{"type": "2d" | "3d", "shows": "..."}],
  "guided_steps": [{"title": "...", "do": "what the learner changes", "notice": "what they should observe and why it matters"}],
  "validation_targets": [{"id": "v1", "claim_id": "c1", "metric": "snake_case_name", "how_to_measure": "...",
                          "expected": "...", "tolerance": "..."}]
}"""


def validate_plan(plan, analysis=None):
    if plan.get("modality") not in ("2d", "3d"):
        raise ValueError("Choose exactly one modality: 2d or 3d")
    views = plan.get("views", [])
    if len(views) != 1 or views[0].get("type") != plan["modality"]:
        raise ValueError("The plan must contain one view matching its modality")
    if analysis is not None:
        validate_coverage(analysis, plan)
    return plan


def plan(analysis, evidence):
    return chat_json(PLANNER, "Analyst extraction:\n" + dump(analysis) + "\n\nVisual evidence:\n" + dump(evidence))


# ---------------------------------------------------------------- Modeler

MODELER = """You are the Modeler agent of Paper-to-World.

Write a Python 3 reference implementation of the planned model. It is the scientific source of truth that the browser simulation will later be ported from.

Rules:
- Use only numpy and scipy. No plotting, no file I/O, no network.
- Must finish in under 60 seconds.
- Use the parameter defaults from the plan.
- Define run(params, steps): start from the initial state with the given parameters (a dict keyed by the plan's control symbols; missing keys use defaults), advance exactly `steps` timesteps, and return a flat dict of the state: every state variable, elapsed time, and the parameters. Values are numbers or short lists of numbers. The browser port is checked against run() number for number.
- Compute every validation target metric by calling the same stepping code.
- Put the metric printing under `if __name__ == "__main__":`. It prints exactly one JSON object as the last stdout line:
  {"metrics": {"<metric name from validation_targets>": <number or short list>}, "notes": "..."}
- Keep the code simple and commented with references to equation ids.

Return the code in one ```python block."""


def build_model(analysis, plan, previous=None, error=None):
    user = "Analyst extraction:\n" + dump(analysis) + "\n\nPlan:\n" + dump(plan)
    return extract_block(chat(MODELER, revise(user, previous, error, "python")), "python")


# ---------------------------------------------------------------- Validator

VALIDATOR = """You are the Validator agent of Paper-to-World.

Compare what the reference model actually computed against what the paper claims.

Status per target:
- "pass": measured value matches the expectation within tolerance
- "partial": right direction or shape, wrong magnitude
- "fail": contradicts the paper
- "not_measured": the metric is missing from the output

Be strict and honest. Learners will see this report.

JSON shape:
{
  "results": [{"id": "v1", "claim": "...", "expected": "...", "measured": "...", "status": "pass", "note": "..."}],
  "summary": "2-3 sentences: how faithful is the simulation to the paper, and its main limits"
}"""


STATUSES = ("pass", "partial", "fail", "not_measured")


def normalize_validation(validation):
    results = [dict(r) for r in validation.get("results") or [] if isinstance(r, dict)]
    for r in results:
        status = str(r.get("status") or "").strip().lower()
        r["status"] = status if status in STATUSES else "not_measured"
    return {"results": results, "summary": str(validation.get("summary") or "")}


def validate(analysis, plan, model_output):
    return chat_json(
        VALIDATOR,
        "Claims:\n" + dump(analysis["claims"]) + "\n\nValidation targets:\n" + dump(plan["validation_targets"]) + "\n\nModel output:\n" + model_output,
    )


# ---------------------------------------------------------------- Porter

PORTER = """You are the Porter agent of Paper-to-World.

Port the Python reference model to one pure JavaScript ES module, model.js. A world renderer will import it and animate it; it is checked number for number against the Python run(params, steps) at several parameter values and step counts.

Export exactly:
- `export const DT` — the reference timestep.
- `export function createModel(params)` — the initial state object with the parameters merged in (missing keys use the reference defaults).
- `export function advanceModel(state)` — advance the state by exactly one reference timestep, in place, and return it.
- `export function run(params, steps)` — createModel, then advanceModel `steps` times; return the state.

Rules:
- The state object has the same keys as the Python run() result, with the same meaning and units.
- Same equations, integrator, constants, order of operations, reset and refractory rules. No approximations, no smoothing, no randomness unless the reference seeds it identically.
- Pure computation: no import, no DOM, no timers, no network. Plain numbers and arrays.

Return the module in one ```javascript block."""


def port_model(plan, model_code, previous=None, error=None):
    user = (
        "Plan:\n"
        + dump({k: plan.get(k) for k in ("core_model", "state_variables", "update_rule", "controls")})
        + "\n\nPython reference model:\n```python\n"
        + model_code
        + "\n```"
    )
    return extract_block(chat(PORTER, revise(user, previous, error, "javascript")), "javascript")


# ---------------------------------------------------------------- Designer

DESIGNER = """You are the Designer agent of Paper-to-World.

Design the scene a learner will explore: which objects to draw, what shape each has, where it sits, and which live model values drive it. A Builder will draw exactly this scene.

Work in three moves:
1. Visual needs: from the concepts, mechanisms and plan, list what the learner must SEE to understand each idea (e.g. "see the voltage approach the threshold").
2. Paper first: for each need, use the Observer's evidence: shapes, counts, sizes, arrangement and figure layouts the paper states. When a figure reading gives element boxes, keep that figure's arrangement: what is left of, right of, above or below what. Objects drawn this way have "basis": "paper" and "evidence" naming a verified entity id or a figure id.
3. Ideation: where the paper is silent, propose a clear, honest depiction yourself. These objects have "basis": "hypothesis", "evidence": null and a "rationale" explaining why this form helps understanding and how it stays faithful to the paper. Never present a hypothesis as the paper's own geometry.

Rules:
- Bind live values: each binding maps one key of the model state (given below) to a visible property (fill, size, glow, arrow length, particle speed, label, position...). Describe the mapping in "map". Bind every state variable a lesson will talk about.
- Use only these primitives: {primitives}. Positions have {axes} numbers{units}. "size" gives the extent per axis.
- "parent" groups a part under another object (or null). "explode" is the offset used when the learner pulls the parts apart.
- 3-12 objects. Lowercase snake_case ids. Labels are short learner-facing names.

JSON shape:
{{
  "visual_needs": [{{"need": "...", "concept": "...", "objects": ["id"]}}],
  "objects": [{{"id": "soma", "label": "Soma", "role": "structure|signal|plot|annotation", "primitive": "...",
                "position": [...], "size": [...], "parent": null, "description": "how it looks, in detail",
                "basis": "paper|hypothesis", "evidence": "entity or figure id, or null", "rationale": "...",
                "bindings": [{{"state": "V", "property": "fill", "map": "-65 mV muted to -50 mV accent"}}],
                "explode": [...]}}],
  "camera": [x, y, z]
}}"""

SCENE_AXES = {"2d": (2, " in canvas units centered on the origin, y up"), "3d": (3, " in world units, the subject about 10 units across")}


def design_scene(analysis, evidence, plan, state, previous=None, error=None):
    axes, units = SCENE_AXES[plan["modality"]]
    system = DESIGNER.format(primitives=", ".join(PRIMITIVES[plan["modality"]]), axes=axes, units=units)
    user = (
        "Selected modality: "
        + plan["modality"]
        + "\n\nConcepts and mechanisms:\n"
        + dump({k: analysis.get(k) for k in ("title", "concepts", "mechanisms", "equations")})
        + "\n\nVisual evidence from the paper (verified = its quote was found in the paper text):\n"
        + dump(evidence)
        + "\n\nPlan:\n"
        + dump({k: plan.get(k) for k in ("core_model", "views", "controls", "guided_steps")})
        + "\n\nModel state keys with example values (model.js state after one step):\n"
        + dump(state)
    )
    return chat_json(system, revise(user, previous, error, "json"))


# ---------------------------------------------------------------- Writer

WRITER = """You are the Writer agent of Paper-to-World.
Write the lessons for an interactive world built from a paper. A fixed hand-written shell shows them beside the world: narration, equation, terms, prediction, sliders and a challenge. Return one ```json block containing an array of 3-6 lessons.

Lesson object (all fields required, no extra fields):
{
 "id":"rest", "title":"...",
 "learning":{"objective":"What the learner will understand", "action":"One specific input to change", "observe":"Which named visual quantity changes", "mechanism":"Why the input causes that output", "focus":["membrane"], "test_params":{"I":2}, "outcome_js":"state.spikes > 0"},
 "intro":["Plain-language sentence.","Another sentence."],
 "intro_links":["object_id","another_object_id"],
 "equation":{"latex":"...","symbols":[{"symbol":"V","meaning":"membrane potential, mV","links_to":"membrane"}]},
 "terms":[{"term":"Membrane","definition":"...","links_to":"membrane"}],
 "predict":{"question":"...","options":["...","..."],"answer_index":0,"why":"...","page":1},
 "controls":[{"symbol":"I","label":"Input current","min":0,"max":5,"step":0.1,"default":0,"units":"nA"}],
 "challenge":{"text":"...","check_js":"state.some_numeric_value > 2"},
 "figure_caption":"What the learner sees.",
 "scene_state":{"visible":["membrane","object_id","another_object_id"],"camera":[0,0,6],"params":{"I":0}},
 "source":{"title":"Exact source paper title","page":1,"kind":"paper"}
}

Lesson design:
- Object ids are the scene's object ids only. Control symbols and scene_state.params keys are model parameters only.
- Intro contains 2-3 sentences; intro_links is parallel and names the scene object highlighted during each sentence's narration.
- Lesson 1 explains the whole system and its input/output path. Subsequent lessons focus on distinct stages while preserving an overview. Feed-forward models need computational stages, not a fictitious resting state. Every next lesson adds exactly ONE mechanism or equation. The last lesson reproduces a Validator passing target. If only partial/failed/not_measured results exist, explicitly say this, never invent a passing result.
- Source page covers every factual claim in the lesson; predict.page cites the explanation. Use extra lessons to separate different source pages. source.kind is "paper" when the paper states the lesson's claims, "background" for general background (never present it as a paper finding), and "simulation" when the lesson's result comes from our own reference run.
- When a lesson names a part whose shape is a scene hypothesis, say it is drawn for illustration.
- All links_to and intro_links IDs must appear in scene_state.visible. Match controls' defaults to scene_state.params.
- Every lesson needs learning.objective/action/observe/mechanism/focus/test_params/outcome_js. outcome_js must check a computed consequence, not just echo a slider value. Its test_params must reach that outcome; use a bounded measurement window for dynamical models. Explained results must identify which source figure/table is being inspected.
- check_js is a PURE boolean JS EXPRESSION over `state`, the model state (keys given below) plus anything the world adds, without DOM access, side effects, external variables, or a return statement. Challenges must be achievable within the control ranges. No fake validation values.
"""


def write_lessons(analysis, plan, validation, scene, state, previous=None, error=None):
    user = (
        "Analyst extraction:\n"
        + dump(analysis)
        + "\n\nPlan:\n"
        + dump({k: plan.get(k) for k in ("controls", "guided_steps", "validation_targets", "coverage", "simplifications")})
        + "\n\nValidation report:\n"
        + dump(validation)
        + "\n\nScene objects:\n"
        + dump([{k: o.get(k) for k in ("id", "label", "basis", "description")} for o in scene["objects"]])
        + "\n\nScene camera: "
        + dump(scene["camera"])
        + "\n\nModel state keys with example values:\n"
        + dump(state)
    )
    return json.loads(extract_block(chat(WRITER, revise(user, previous, error, "json")), "json"))


# ---------------------------------------------------------------- Builder

BUILDER = """You are the Builder agent of Paper-to-World.
Draw the designed scene as one living world module, world.js. Return ONE ```javascript block containing a complete ES module.
Generate only the selected modality, with exactly one renderer. Never generate both 2D and 3D, an alternate renderer, a dimension toggle, or a fallback. Export `const dimensionality = 2` for 2D or `const dimensionality = 3` for 3D.
Never output HTML, a shell, CSS files, or sim.html. A fixed hand-written shell owns lessons, sliders, narration, navigation, prediction/reveal, and the tutor.

The simulation is already written and checked against the Python reference: `import { DT, createModel, advanceModel } from './model.js';`. Animate it by calling advanceModel; never re-implement, approximate or alter the model. Exactly one advanceModel call is one timestep.

Scene:
- Create every scene object with its id as a string literal, its primitive, position, size, parent and explode offset. Follow each object's description closely; it was designed from the paper's evidence.
- Apply every binding each frame: read the bound state key and drive the property as its map describes.
- Keep the scene's arrangement on screen. Paper-based objects must keep the left/right and above/below order their elements have in the paper's figure; the render check measures this with objectBounds() (in every 2D lesson, and in the first 3D lesson).
- Objects with "basis": "hypothesis" are illustrative: their tag or inspector says "illustrative". Objects with "basis": "paper" may cite the page of their evidence.

world.js named exports (export each function directly):
init(container), setParams(obj), setLesson(scene_state), highlight(objectId), getState(), play(), pause(), step(), onObjectClick(callback), setAssembly(amount), objectBounds().
- The world is opened in a headless browser before it is published: every lesson is applied, played, measured and photographed, and the screenshots are compared with the paper's figures. Problems found there come back to you.
- objectBounds() returns {objectId: {x, y, width, height}} in CSS pixels relative to the container, for every scene object, matching where it is drawn now (after camera, explode and transitions). A signal with no geometry at the moment uses its anchor.
- init sets up the renderer and ResizeObserver, but does not advance time until play().
- setParams updates model parameters instantly; setLesson applies visible objects, camera and preset, resets the model with createModel, but preserves play/pause. Transition camera/objects smoothly over 400-600ms; no hard scene cuts. Respect prefers-reduced-motion.
- getState returns the model state (all its keys) plus params, `time` (elapsed model time, increasing while playing), assembly and assemblyTarget. Lesson challenges evaluate against it. No values invented just to pass a challenge.
- step advances exactly ONE timestep while paused. play/pause control time; rendering may continue while paused.
- highlight(id) accents an object; highlight(null) clears it. onObjectClick(cb) registers cb(objectId), invoked on object click and keyboard activation. Every meaningful object is clickable AND keyboard accessible with a live-value tag near it: one focusable element per scene object carrying data-object="<object id>", visible whenever the object is.
- Read --paper, --ink, --accent, --muted, --line CSS variables from container for light/dark. Listen on container for CustomEvent('themechange', {detail:{dark:boolean}}) and CustomEvent('explorechange', {detail:{enabled:boolean}}). No controls outside container.
- In explore mode implement pointer pan and wheel/pinch zoom for 2D; OrbitControls for 3D. Provide accessible pan/zoom controls inside container. Leaving explore restores normal framing. Don't consume scroll gestures when exploration is off.
- Libraries: only three (`import * as THREE from 'three'`) and the addons 'three/addons/controls/OrbitControls.js' and 'three/addons/environments/RoomEnvironment.js', served locally through the import map. Nothing loads from the network. KaTeX and fonts belong to the shell.
- Labels are compact one-line tags (name and live value) with a thin leader line to their anchor; they must not overlap each other or cover the model. Counts and rates always state their measurement window, and every count shown comes from that same measurement.
- Preserve the shared shell theme and blue selection accent.
- No fetch, external data, network calls or backend calls from the world. No framework, no build, no fallback renderer or compatibility code. Keep straightforward and readable.
"""


RENDERER_RULES = {
    "2d": "- 2D Canvas: Draw a clear, flat schematic with ink lines and theme colors (no 3D shading), plus a live plot of the key variable. Scale for devicePixelRatio. Use theme variables for text and background, readable Inter labels and leader lines. No plotting library.\n- For anatomical subjects provide Assemble / Explode / Anatomy; for computational subjects use the lesson-relevant architecture/detail inspection controls instead. Never force anatomy controls onto a non-anatomical paper. Assemble is the schematic. Explode slides the constituent parts apart along the main axis over about 400ms; each part keeps its one-line label and live value. Anatomy keeps the same flat style, adds a short caption per part and opens an Inspect-a-structure popover (part picker, description, reference links). The simulation keeps running in every mode.\n- Export setAssembly(amount): clamp a finite amount to 0–1 (0 assembled, 1 exploded) and animate toward it; reversible, no positional drift, reduced-motion support. Expose assembly and assemblyTarget in getState(). Invalid input leaves the target unchanged. Never alter scientific parameters or time.",
    "3d": "- For a selected 3D view, use a perspective camera, meaningful separation along depth, orbit and reset controls, and readable labels that do not cover the geometry. Avoid a frontal, nearly coplanar copy of the 2D diagram.\n- Choose geometry from the subject: spatial anatomy can be an exhibit; abstract computation needs a labeled connected dataflow with readable intermediate values. Avoid floating unlabelled blocks. The lesson objective and observable transformation take priority over decorative materials. For anatomical subjects include the relevant internal structures, membranes, organelles and fine branching, with cutaways so they remain visible. Label schematic scale and distinguish illustrative anatomy from simulated variables.\n- Export setAssembly(amount): clamp a finite amount to 0–1 and animate toward it (0 assembled, 1 exploded) over 600–900ms between saved home transforms and separated inspection transforms, with reversible interruption, no positional drift and reduced-motion support. Synchronize a compact Assemble/Explode segmented control inside the container. Expose assembly and assemblyTarget in getState(). Invalid input leaves the target unchanged. Never alter scientific parameters or time.\n- 3D: import * as THREE from 'three'; use OrbitControls from 'three/addons/controls/OrbitControls.js'. The shell supplies three@0.170.0. Use detailed smooth geometry, MeshPhysicalMaterial or MeshStandardMaterial with differentiated roughness/metalness, environment lighting using RoomEnvironment and PMREMGenerator, ACES tone mapping, soft shadows, and a restrained museum palette. Use cutaways for internal anatomy. Preserve theme-aware contrast and blue selection. Raycast object IDs and anchor labels to transformed geometry. Animate explode/assemble from stored transforms, independently of simulation play/pause. Smooth camera interpolation between lessons.",
}


def build_world(plan, scene, lessons, model_js, state, previous=None, error=None):
    system = BUILDER + "\nSelected renderer: " + plan["modality"] + "\n" + RENDERER_RULES[plan["modality"]]
    user = (
        "Complete lessons: teach each objective with a distinct visible focus and observable change:\n"
        + dump(lessons)
        + "\n\nCoverage and limitations:\n"
        + dump({k: plan.get(k) for k in ("coverage", "simplifications")})
        + "\n\nScene design:\n"
        + dump(scene)
        + "\n\nLesson scene states (passed to setLesson):\n"
        + dump([{"id": lesson["id"], "scene_state": lesson["scene_state"], "controls": lesson["controls"]} for lesson in lessons])
        + "\n\nmodel.js (import it, do not change it):\n```javascript\n"
        + model_js
        + "\n```"
        + "\n\nModel state keys with example values:\n"
        + dump(state)
    )
    return extract_block(chat(system, revise(user, previous, error, "javascript")), "javascript")


# ---------------------------------------------------------------- Critic

CRITIC = """You are the Critic agent of Paper-to-World. You compare an interactive world, as a learner sees it, with the paper it was built from.

You get screenshots of the world (one per lesson) and, after them, the paper's figures that the scene claims to follow. You also get the scene design: each object, whether its shape comes from the paper (with the evidence it cites) or is an illustrative hypothesis.

Check:
- Every object with basis "paper" looks and sits the way the paper's figure or text describes it (shape, count, arrangement, connections, labels).
- Hypothesis objects do not contradict the paper.
- The learner can tell the parts apart: legible tags, no overlaps, nothing important cut off or hidden, sensible contrast.
- Each screenshot shows its lesson objective, named input, transformation and observable output. Repeating a generic scene for different lessons without an inspectable change is a major issue. Check the learning.action/observe/mechanism contract against the picture; look for missing architecture components and unexplained state changes. Do not mistake a running timer or a decorative object for an implemented mechanism.

Severity: "major" for anything that misrepresents the paper or blocks understanding; "minor" for polish. Be concrete: name the object and lesson, say what is wrong and how to fix it in the drawing code. Do not ask for changes to the science or the lessons' text.

JSON shape:
{
  "issues": [{"lesson": "lesson id or null", "object": "object id or null", "severity": "major|minor", "problem": "...", "fix": "..."}],
  "summary": "one or two sentences"
}"""
CRITIC_SCREENSHOTS = 6
CRITIC_FIGURES = 4


def critique(scene, evidence, lessons, screenshots, figures):
    """`screenshots`: (lesson id, PNG) pairs. `figures`: (figure record, PNG) pairs."""
    screenshots, figures = screenshots[:CRITIC_SCREENSHOTS], figures[:CRITIC_FIGURES]
    legend = [f"Image {i}: screenshot of lesson {lesson_id}" for i, (lesson_id, _) in enumerate(screenshots, 1)]
    legend += [f"Image {i}: paper figure {f['id']} (page {f['page']}): {f['caption']}" for i, (f, _) in enumerate(figures, len(screenshots) + 1)]
    user = (
        "\n".join(legend)
        + "\n\nScene design:\n"
        + dump(scene)
        + "\n\nPaper evidence:\n"
        + dump(evidence["entities"])
        + "\n\nLessons:\n"
        + dump(
            [
                {
                    "id": lesson["id"],
                    "title": lesson["title"],
                    "figure_caption": lesson["figure_caption"],
                    "visible": lesson["scene_state"]["visible"],
                    "learning": lesson.get("learning"),
                }
                for lesson in lessons
            ]
        )
    )
    return chat_json(CRITIC, user, images=[png for _, png in screenshots] + [png for _, png in figures])


# ---------------------------------------------------------------- Tutor

TUTOR = """You are the Tutor agent of Paper-to-World. A learner is exploring an interactive simulation built from a scientific paper.

Rules:
- Ground answers in the paper pages given. Cite pages like [p.3], and figures like [Figure 2, p.5] when you use what a figure shows.
- If the paper does not say it, say so, then you may add general background clearly labelled "Background (not from the paper)".
- When useful, tell the learner which slider to move in the simulation and what to watch.
- Mention the validation report if the learner asks how trustworthy the simulation is.
- Short, clear, visual-learner friendly. Use LaTeX between $...$ for math."""


def words(text):
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def top_pages(pages, question, k=4):
    """The k pages that best answer the question, by BM25 (rare question words count most), in page order."""
    documents = [words(p) for p in pages]
    average = sum(map(len, documents)) / max(1, len(documents)) or 1
    terms = set(words(question))
    rarity = {t: math.log(1 + (len(documents) - (n := sum(t in d for d in documents)) + 0.5) / (n + 0.5)) for t in terms}

    def score(document):
        counts = {t: document.count(t) for t in terms}
        return sum(rarity[t] * c * 2.2 / (c + 1.2 * (0.25 + 0.75 * len(document) / average)) for t, c in counts.items() if c)

    scores = [score(d) for d in documents]
    return sorted(sorted(range(len(pages)), key=lambda i: -scores[i])[:k])


def ask(pages, analysis, plan, validation, question, evidence=None):
    picked = top_pages(pages, question)
    excerpts = "\n\n".join(f"[page {i + 1}]\n{pages[i]}" for i in picked)
    figures = [{k: f.get(k) for k in ("id", "page", "caption", "reading")} for f in (evidence or {}).get("figures", []) if f.get("reading") or f.get("caption")]
    context = (
        "Paper summary:\n"
        + dump({k: analysis[k] for k in ["title", "one_line_summary", "concepts", "equations"]})
        + "\n\nSimulation controls:\n"
        + dump(plan["controls"])
        + "\n\nValidation report:\n"
        + dump(validation)
        + ("\n\nThe paper's figures (what each shows):\n" + dump(figures) if figures else "")
        + "\n\nRelevant paper pages:\n"
        + excerpts
    )
    return chat(TUTOR, context + "\n\nLearner question: " + question)
