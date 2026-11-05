"""A text PDF with the defects measured on real arXiv papers, plus a scripted model endpoint.

Measured on arXiv 2006.11239 with pypdf: 86 ligature glyphs, 13 NUL characters, line-break
hyphenation, and a References section holding ~45% of the extracted text. Every page here also
carries a running header and a page-number footer.
"""

import io
import json
import re
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
HEADER = "Journal of Teaching Neuroscience 12 (2026) 1-5"
TITLE = "Leaky integration sets the firing rhythm of a single neuron"
FI = b"\256"  # StandardEncoding /fi ligature glyph

PAGES = [
    [
        TITLE.encode(),
        b"A. Researcher and B. Scientist",
        b"",
        b"Abstract. We show that a leaky integrate-and-" + FI + b"re neuron converts",
        b"a constant input current into a regular spike train whose rate rises with the",
        b"input. The mem-",
        b"brane time constant sets how quickly the voltage responds.",
    ],
    [
        b"1 Model",
        b"The membrane voltage obeys tau dV/dt = -(V - Vrest) + R I with Vrest = -65 mV,",
        b"R = 10 Mohm and tau = 20 ms. When V reaches the threshold of -50 mV the neuron",
        FI + b"res a spike, V is reset to -65 mV and held for a 2 ms refractory period.\000",
        b"We integrate with forward Euler at dt = 0.1 ms.",
    ],
    [
        b"2 Results",
        b"Over one second the neuron " + FI + b"res 33 spikes at 2 nA and 63 spikes at 3 nA.",
        b"Below the rheobase of 1.5 nA there are no spikes, the signature of leaky integra-",
        b"tion with a hard threshold.",
    ],
    [
        b"References",
        b"[1] L. Lapicque. Recherches quantitatives sur l excitation electrique. 1907.",
        b"[2] W. Gerstner and W. Kistler. Spiking Neuron Models. Cambridge, 2002.",
        b"[3] N. Brunel and M. van Rossum. Lapicque 1907 paper revisited. 2007.",
    ],
    [b"A Appendix: firing-rate formula", b"For R I > 15 mV the continuous model predicts f = 1000 / (tau ln(RI/(RI-15)) + 2) Hz."],
]


# Page 2 carries a vector drawing (as most arXiv diagrams are) with in-figure labels, and its caption below it.
FIGURE_BOX = (0.26, 0.24, 0.93, 0.42)  # where the drawing sits on page 2: x0, y0, x1, y1 from the top left
CAPTION_LINES = [b"Figure 1: A neuron drawn as a round soma with branching dendrites on the left", b"and a long axon to the right."]
FIGURES = {
    2: b"""1.5 w
306 555 m 328.09 555 346 537.09 346 515 c 346 492.91 328.09 475 306 475 c 283.91 475 266 492.91 266 515 c 266 537.09 283.91 555 306 555 c S
266 515 m 200 560 l S 200 560 m 170 590 l S 270 500 m 190 470 l S
346 515 m 540 515 l S 540 515 m 560 535 l S 540 515 m 560 495 l S
BT /F1 9 Tf 292 512 Td (soma) Tj ET
BT /F1 9 Tf 430 522 Td (axon) Tj ET
BT /F1 10 Tf 14 TL 48 440 Td ("""
    + CAPTION_LINES[0]
    + b""") Tj T* ("""
    + CAPTION_LINES[1]
    + b""") Tj ET"""
}


def paper_pdf(pages=PAGES, header=True, encrypt=None, figures=FIGURES):
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/StandardEncoding"),
            }
        )
    )
    for number, lines in enumerate(pages, 1):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        body = ([HEADER.encode(), b""] if header else []) + lines + ([b"", str(number).encode()] if header else [])
        commands = [b"BT /F1 10 Tf 14 TL 48 748 Td"]
        commands += [b"(" + line.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b") Tj T*" for line in body]
        commands.append(b"ET")
        if number in figures:
            commands.append(figures[number])
        stream = DecodedStreamObject()
        stream.set_data(b"\n".join(commands))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypt:
        writer.encrypt(encrypt)
    data = io.BytesIO()
    writer.write(data)
    return data.getvalue()


def blank_pdf(count=2):
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=612, height=792)
    data = io.BytesIO()
    writer.write(data)
    return data.getvalue()


ANALYSIS = {
    "title": TITLE,
    "authors": "A. Researcher, B. Scientist",
    "domain": "computational neuroscience",
    "learning_topics": [
        {"id": "integration", "title": "Leaky integration", "page": 2, "required": True},
        {"id": "threshold", "title": "Threshold and reset", "page": 2, "required": True},
    ],
    "one_line_summary": "Input current sets the firing rate of a leaky neuron.",
    "concepts": [
        {"name": "Leaky integration", "explanation": "Voltage decays toward rest.", "page": 1},
        {"name": "Firing threshold", "explanation": "Crossing -50 mV fires a spike.", "page": 2},
    ],
    "equations": [
        {
            "id": "eq1",
            "latex": r"\tau\frac{dV}{dt}=-(V-V_{rest})+RI",
            "meaning": "membrane voltage dynamics",
            "reconstructed": True,
            "page": "2",
            "variables": [],
        },
        {"id": "eq2", "latex": "", "meaning": "garbled", "page": 2},
    ],
    "mechanisms": [],
    "claims": [
        {"id": "c1", "statement": "33 spikes at 2 nA over one second", "value": "33", "page": 3},
        {"id": "c2", "statement": "63 spikes at 3 nA over one second", "value": "63", "page": 3},
    ],
    "parameters": [],
}


def plan(modality):
    return {
        "modality": modality,
        "rationale": "Voltage changes over time, so its rhythm is easiest to see this way.",
        "core_model": "leaky integration with threshold and reset",
        "simplifications": [],
        "state_variables": [{"name": "V", "meaning": "membrane voltage", "initial": -65}],
        "update_rule": "forward Euler, dt = 0.1 ms",
        "controls": [
            {"symbol": "I", "label": "Input current", "min": 0, "max": 5, "step": 0.1, "default": 0},
            {"symbol": "tau", "label": "Membrane time constant", "min": 5, "max": 50, "step": 1, "default": 20},
        ],
        "views": [{"type": modality, "shows": "neuron and voltage trace"}],
        "coverage": [
            {"topic": "integration", "mode": "simulated", "lessons": ["integrate"]},
            {"topic": "threshold", "mode": "simulated", "lessons": ["threshold"]},
        ],
        "guided_steps": [],
        "validation_targets": [
            {"id": "v1", "claim_id": "c1", "metric": "spikes_2nA", "how_to_measure": "count", "expected": "33", "tolerance": "0"},
            {"id": "v2", "claim_id": "c2", "metric": "spikes_3nA", "how_to_measure": "count", "expected": "63", "tolerance": "0"},
        ],
    }


EVIDENCE = {
    "subject": "A single neuron: dendrites, a round soma and a long axon.",
    "figures": [{"id": "fig1", "page": 2, "caption": "Figure 1", "depicts": "a round soma, dendrites on the left, axon to the right"}],
    "entities": [
        {
            "id": "membrane",
            "name": "Membrane",
            "kind": "structure",
            "appearance": "the boundary of a round soma",
            "page": 2,
            "quote": "The membrane voltage obeys",
            "figure": "fig1",
            "element": "soma",
        },
        {
            "id": "axon",
            "name": "Axon",
            "kind": "structure",
            "appearance": "a long axon to the right",
            "page": 2,
            "quote": "a long axon to the right",
            "figure": "fig1",
        },
        {"id": "input", "name": "Input current", "kind": "signal", "appearance": "a constant drive", "page": 1, "quote": "a constant input current"},
        {
            "id": "threshold",
            "name": "Threshold",
            "kind": "quantity",
            "appearance": "a -50 mV level",
            "page": 2,
            "quote": "When V reaches the threshold of -50 mV",
        },
        {"id": "spike", "name": "Spike", "kind": "signal", "appearance": "a flash", "page": 3, "quote": "spikes glow like lightning"},
        {
            "id": "dendrites",
            "name": "Dendrites",
            "kind": "structure",
            "appearance": "three branching lines on the left",
            "page": 2,
            "quote": None,
            "figure": "fig1",
            "element": "dendrite",
        },
    ],
}
READING = {
    "box": [0.25, 0.23, 0.94, 0.42],
    "kind": "diagram",
    "depicts": "A neuron: a circle with branches on the left and a long line to the right.",
    "layout": "branches on the left feed a circle in the middle; a line leaves to the right and forks at its end",
    "elements": [
        {
            "name": "soma",
            "appearance": "circle",
            "position": "middle",
            "box": [0.43, 0.29, 0.57, 0.40],
            "count": 1,
            "label": "soma",
            "connections": ["dendrites", "axon"],
        },
        {
            "name": "dendrites",
            "appearance": "straight branching lines",
            "position": "left",
            "box": [0.27, 0.25, 0.44, 0.41],
            "count": 3,
            "label": None,
            "connections": ["soma"],
        },
        {
            "name": "axon",
            "appearance": "long horizontal line forking at the end",
            "position": "right",
            "box": [0.56, 0.32, 0.92, 0.37],
            "count": 1,
            "label": "axon",
            "connections": ["soma"],
        },
    ],
    "axes": [],
}
PRINTED_EQ1 = r"\tau \frac{dV}{dt} = -(V - V_{\mathrm{rest}}) + R I"
CRITIQUE = {
    "issues": [
        {"lesson": "rest", "object": "axon", "severity": "major", "problem": "The axon is shorter than in Figure 1.", "fix": "Lengthen the axon path."},
        {"lesson": None, "object": None, "severity": "minor", "problem": "Tags could be lighter.", "fix": "Use the muted color."},
    ],
    "summary": "Close to the figure.",
}
GROUNDED = {"membrane", "axon", "input", "threshold", "fig1"}


class ScriptedLLM:
    """Stands in for llm.chat with the raw text shapes real chat models return.

    Replies include prose around the payload and ```js fences instead of ```javascript. The first
    Analyst reply is not valid JSON, the first browser port miscounts spikes, the first scene binds
    an unknown state key and the first world misses an export, so every repair path runs.
    Vision agents (Transcriber, Proofreader, Viewer, Critic) get images; the first Critic reply asks for one major fix.
    Set port_fixes = False to keep the port wrong. Keyword arguments give replies an agent uses first,
    e.g. ScriptedLLM('2d', Modeler=['```py\nprint(1)\n```']). Records every (agent, user message) pair.
    """

    def __init__(self, modality, **replies):
        self.modality = modality
        self.calls = []
        self.port_fixes = True
        self.replies = replies
        self.images = []
        self.folder = ROOT / "static" / ("demo" if modality == "2d" else "demo3d")

    def read(self, name):
        return (self.folder / name).read_text()

    def scene(self, first):
        scene = json.loads(self.read("scene.json"))
        for item in scene["objects"]:
            if item["basis"] == "paper" and item["evidence"] not in GROUNDED:
                item.update(basis="hypothesis", evidence=None, rationale="The paper does not describe this part; drawn for illustration.")
        if first:
            scene["objects"][0]["bindings"] = [{"state": "voltage_mv", "property": "fill"}]
        return scene

    def __call__(self, system, user, images=None):
        agent = system.split(" agent", 1)[0].rsplit(" ", 1)[-1]
        self.calls.append((agent, user))
        if images is not None:
            self.images.append((agent, images))
        first = sum(name == agent for name, _ in self.calls) == 1
        if self.replies.get(agent):
            return self.replies[agent].pop(0)
        if agent == "Analyst":
            if first:
                return "Here is the extraction:\n```json\n{'title': 'single quotes are not JSON'}\n```"
            return "Sure! Below is the analysis.\n```json\n" + json.dumps(ANALYSIS) + "\n```\nLet me know if you need {more}."
        if agent == "Transcriber":
            number = int(user.split()[1].rstrip("."))
            lines = (PAGES[number - 1] + ([b"", *CAPTION_LINES] if number in FIGURES else [])) if number <= len(PAGES) else []
            return "\n".join(line.replace(FI, b"fi").decode("latin-1") for line in lines)  # a reader sees the ligature as fi
        if agent == "Proofreader":
            return json.dumps({"equations": [{"id": "eq1", "found": True, "latex": PRINTED_EQ1, "note": "subscript is roman"}]})
        if agent == "Viewer":
            return json.dumps(READING)
        if agent == "Critic":
            return json.dumps(CRITIQUE if first else {"issues": [CRITIQUE["issues"][1]], "summary": "Matches the figure."})
        if agent == "Observer":
            return json.dumps(EVIDENCE)
        if agent == "Planner":
            return json.dumps(plan(self.modality))
        if agent == "Modeler":
            return "The reference model:\n\n```py\n" + self.read("model.py") + "\n```"
        if agent == "Validator":
            return json.dumps(
                {
                    "results": [
                        {"id": "v1", "claim": "c1", "expected": "33", "measured": "33", "status": "PASS"},
                        {"id": "v2", "claim": "c2", "expected": "63", "measured": "63", "status": "pass"},
                    ],
                    "summary": "Spike counts match the paper.",
                }
            )
        if agent == "Porter":
            port = self.read("model.js")
            return "```js\n" + (port.replace("s.spikes++", "s.spikes += 2") if first or not self.port_fixes else port) + "\n```"
        if agent == "Designer":
            return "Scene:\n" + json.dumps(self.scene(first))
        if agent == "Writer":
            return "Lessons:\n```JSON\n" + self.read("lessons.json") + "\n```"
        if agent == "Builder":
            world = self.read("world.js")
            return "World module:\n```js\n" + (world.replace("export function step(", "function step(") if first else world) + "\n```"
        raise AssertionError(f"Unexpected agent {agent}")


def scripted_model(scripted, vision=False):
    """Route every model call (text and, when `vision`, image) to `scripted`. Use as a context manager."""
    from app import agents, llm

    stack = ExitStack()
    stack.enter_context(patch.object(llm, "chat", side_effect=scripted))
    stack.enter_context(patch.object(agents, "chat", side_effect=scripted))
    stack.enter_context(patch.object(llm, "chat_vision", side_effect=scripted))
    stack.enter_context(patch.object(llm, "vision_configured", return_value=vision))
    return stack


def no_browser():
    """Skip opening the world in Chromium, for tests about other stages (WorkflowTests and RenderCheckTests open it)."""
    return patch("app.pipeline.check_render", side_effect=lambda *args: {"lessons": []})


# Operational copy is checked separately from scientific source text.
INTERNAL_WORDS = re.compile(
    r"\b(?:agents?|Analyst|Planner|Modeler|Validator|Builder|Tutor|LLM|AI model|prompts?|tokens?|JSON|pipeline|parse|decompose|deconstruct|reconstruct|compose|extract|reasoning|retry|crash|exception|stack trace)\b",
    re.I,
)
