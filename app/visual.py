"""Contracts for the paper's visual evidence and the scene designed from it."""

import re

PRIMITIVES = {
    "2d": ("circle", "ellipse", "rect", "line", "polyline", "path", "arrow", "text", "plot", "particles", "group"),
    "3d": ("sphere", "box", "cylinder", "cone", "capsule", "torus", "tube", "plane", "lathe", "points", "plot", "group"),
}
OBJECT_ID = re.compile(r"^[a-z][a-z0-9_]*$")
MIN_OBJECTS = 3
MIN_BOX_AREA = 0.01  # a reported figure box smaller than this share of the page is ignored


def squash(text):
    return re.sub(r"\W+", " ", str(text).lower()).strip()


def page_number(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def page_box(box, min_area=0.0):
    """A [x0, y0, x1, y1] box in page fractions (top-left origin), or None when unusable."""
    valid = (
        isinstance(box, list)
        and len(box) == 4
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)
        and 0 <= box[0] < box[2] <= 1
        and 0 <= box[1] < box[3] <= 1
        and (box[2] - box[0]) * (box[3] - box[1]) >= min_area
    )
    return [float(v) for v in box] if valid else None


def normalize_reading(reading):
    """A figure reader's answer: a usable box (or None) and named elements, each with a usable box or None."""
    return {
        "box": page_box(reading.get("box"), MIN_BOX_AREA),
        "kind": str(reading.get("kind") or ""),
        "depicts": str(reading.get("depicts") or ""),
        "layout": str(reading.get("layout") or ""),
        "elements": [{**e, "box": page_box(e.get("box"))} for e in reading.get("elements") or [] if isinstance(e, dict) and str(e.get("name") or "").strip()],
        "axes": [dict(a) for a in reading.get("axes") or [] if isinstance(a, dict)],
    }


def element_in(reading, words):
    """The element of a figure reading whose name or printed label matches `words`, or None."""
    target = squash(words)
    for element in reading["elements"]:
        for name in (squash(element.get(k) or "") for k in ("name", "label")):
            if target and name and (target in name or name in target):
                return element
    return None


def figure_anchors(scene, evidence):
    """Where each paper-based object sits in the figure its evidence cites: {object id: (figure id, x, y)},
    x and y as fractions of the figure's width and height. The render check holds the world to this order."""
    figures = {f["id"]: f for f in evidence["figures"] if f.get("reading") and f.get("box")}
    entities = {e["id"]: e for e in evidence["entities"]}
    anchors = {}
    for obj in scene["objects"]:
        entity = entities.get(obj.get("evidence")) if obj.get("basis") == "paper" else None
        figure = figures.get(entity.get("figure")) if entity else None
        if entity is None or figure is None:
            continue
        element = element_in(figure["reading"], entity.get("element") or entity["name"])
        if element and element["box"]:
            x0, y0, x1, y1 = figure["box"]
            ex0, ey0, ex1, ey1 = element["box"]
            anchors[obj["id"]] = (figure["id"], ((ex0 + ex1) / 2 - x0) / (x1 - x0), ((ey0 + ey1) / 2 - y0) / (y1 - y0))
    return anchors


def normalize_evidence(evidence, pages, figures):
    """Keep usable entities and mark each verified: its quote appears in the paper text ("text"), or the figure
    it cites was read and shows the element it names ("figure"). `figures` are the pipeline's own figure records."""
    paper = squash(" ".join(pages))
    readings = {f["id"]: f["reading"] for f in figures if f.get("reading")}
    entities = []
    for item in evidence.get("entities") or []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        quote = squash(item.get("quote") or "")
        reading = readings.get(item.get("figure"))
        source = "text" if quote and quote in paper else "figure" if reading and element_in(reading, item.get("element") or item["name"]) else None
        entities.append({**item, "id": str(item["id"]), "page": page_number(item.get("page")), "verified": source is not None, "verified_by": source})
    return {"subject": str(evidence.get("subject") or ""), "figures": figures, "entities": entities}


SEVERITIES = ("major", "minor")


def normalize_critique(critique):
    """A Critic's answer: issues with a severity; only major issues send the world back to the Builder."""
    issues = []
    for issue in critique.get("issues") or []:
        if isinstance(issue, dict) and str(issue.get("problem") or "").strip():
            severity = str(issue.get("severity") or "").lower()
            issues.append({**issue, "severity": severity if severity in SEVERITIES else "major"})
    return {"issues": issues, "major": [i for i in issues if i["severity"] == "major"], "summary": str(critique.get("summary") or "")}


def validate_scene(scene, modality, evidence, state):
    """Check the scene against the paper's evidence and the browser model's state; report every problem at once."""
    problems = []
    objects = [o for o in scene.get("objects") or [] if isinstance(o, dict)]
    ids = [str(o.get("id") or "") for o in objects]
    grounded = {e["id"] for e in evidence["entities"] if e["verified"]} | {f["id"] for f in evidence["figures"]}
    if len(objects) < MIN_OBJECTS:
        problems.append(f"Design at least {MIN_OBJECTS} objects")
    for obj, oid in zip(objects, ids, strict=True):
        name = oid or "an object"
        if not OBJECT_ID.match(oid):
            problems.append(f"{name}: id must be lowercase snake_case")
        if ids.count(oid) > 1:
            problems.append(f"{name}: duplicate id")
        if obj.get("primitive") not in PRIMITIVES[modality]:
            problems.append(f"{name}: primitive {obj.get('primitive')!r} is not one of {', '.join(PRIMITIVES[modality])}")
        position = obj.get("position")
        if not (isinstance(position, list) and len(position) == int(modality[0]) and all(isinstance(v, (int, float)) for v in position)):
            problems.append(f"{name}: position needs {modality[0]} numbers")
        if obj.get("parent") is not None and obj.get("parent") not in ids:
            problems.append(f"{name}: parent {obj.get('parent')!r} is not an object")
        if obj.get("basis") == "paper":
            if obj.get("evidence") not in grounded:
                problems.append(f"{name}: basis paper needs evidence naming a verified entity or figure, not {obj.get('evidence')!r}")
        elif obj.get("basis") == "hypothesis":
            if not str(obj.get("rationale") or "").strip():
                problems.append(f"{name}: a hypothesis needs a rationale")
        else:
            problems.append(f"{name}: basis must be paper or hypothesis")
        for binding in obj.get("bindings") or []:
            if not isinstance(binding, dict) or binding.get("state") not in state or not binding.get("property"):
                problems.append(f"{name}: binding {binding!r} must name a property and one of the model state keys {', '.join(state)}")
    if not any(o.get("bindings") for o in objects):
        problems.append("Add at least one binding from a model state key to an object property")
    if grounded and not any(o.get("basis") == "paper" for o in objects):
        problems.append("The paper describes some of these shapes; draw them from the paper instead of only hypotheses")
    needs = [n for n in scene.get("visual_needs") or [] if isinstance(n, dict)]
    if not needs:
        problems.append("List the visual_needs the scene answers")
    for need in needs:
        missing = [i for i in need.get("objects") or [] if i not in ids]
        if missing or not need.get("objects"):
            problems.append(f"visual need {need.get('need')!r} names unknown objects {missing}")
    camera = scene.get("camera")
    if not (isinstance(camera, list) and len(camera) == 3):
        problems.append("camera must be [x, y, z]")
    if problems:
        raise ValueError("; ".join(problems))
    return {"modality": modality, "visual_needs": needs, "objects": objects, "camera": camera}
