"""The fixed learner shell's Builder contract."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Symbol(Record):
    symbol: str
    meaning: str
    links_to: str


class Equation(Record):
    latex: str
    symbols: list[Symbol] = Field(min_length=1)


class Term(Record):
    term: str
    definition: str
    links_to: str


class Prediction(Record):
    question: str
    options: list[str] = Field(min_length=2, max_length=3)
    answer_index: int = Field(ge=0)
    why: str
    page: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_answer(self):
        if self.answer_index >= len(self.options):
            raise ValueError("Prediction answer_index is outside its options")
        return self


class Control(Record):
    symbol: str
    label: str
    min: float
    max: float
    step: float = Field(gt=0)
    default: float
    units: str

    @model_validator(mode="after")
    def valid_range(self):
        if not self.min <= self.default <= self.max or self.min >= self.max:
            raise ValueError("Control requires min < max and default within range")
        return self


class Challenge(Record):
    text: str
    check_js: str


class Source(Record):
    title: str
    page: int = Field(ge=1)
    # paper: stated in the paper; background: general teaching material; simulation: a result of our own reference run.
    kind: Literal["paper", "background", "simulation"]


class SceneState(Record):
    visible: list[str] = Field(min_length=1)
    camera: list[float] = Field(min_length=3, max_length=3)
    params: dict[str, float]


class Learning(Record):
    objective: str = Field(min_length=10)
    action: str = Field(min_length=10)
    observe: str = Field(min_length=10)
    mechanism: str = Field(min_length=10)
    focus: list[str] = Field(min_length=1)
    test_params: dict[str, float]
    outcome_js: str = Field(min_length=5)


class Lesson(Record):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    title: str
    intro: list[str] = Field(min_length=2, max_length=3)
    intro_links: list[str] = Field(min_length=2, max_length=3)
    equation: Equation
    terms: list[Term] = Field(min_length=1)
    predict: Prediction
    controls: list[Control]
    challenge: Challenge
    figure_caption: str
    scene_state: SceneState
    source: Source
    learning: Learning | None = None

    @model_validator(mode="after")
    def valid_links(self):
        if len(self.intro_links) != len(self.intro):
            raise ValueError("Each intro sentence needs an intro_links object ID")
        links = self.intro_links + [x.links_to for x in self.equation.symbols] + [x.links_to for x in self.terms]
        if not set(links) <= set(self.scene_state.visible):
            raise ValueError("Every text link must name a visible scene object")
        for control in self.controls:
            if self.scene_state.params.get(control.symbol) != control.default:
                raise ValueError("Control default must match the lesson parameter preset")
        return self


# three.js addons served from static/vendor/three/addons; the import map points "three/addons/" there.
ADDONS = ("three/addons/controls/OrbitControls.js", "three/addons/environments/RoomEnvironment.js")
EXPORTS = ("init", "setParams", "setLesson", "highlight", "getState", "play", "pause", "step", "onObjectClick", "setAssembly", "objectBounds")


def validate_lessons(lessons, object_ids, parameters):
    """Lessons may show only scene objects and set only parameters the checked model accepts."""
    if not isinstance(lessons, list) or not 3 <= len(lessons) <= 6:
        raise ValueError("Write 3 to 6 lessons")
    parsed = [Lesson.model_validate(item) for item in lessons]
    if len({item.id for item in parsed}) != len(parsed):
        raise ValueError("Lesson IDs must be unique")
    problems = []
    for lesson in parsed:
        unknown = [i for i in lesson.scene_state.visible if i not in object_ids]
        if unknown:
            problems.append(f"{lesson.id}: visible {unknown} are not scene objects ({', '.join(object_ids)})")
        if lesson.learning:
            outputs = set(re.findall(r"state\.(\w+)", lesson.learning.outcome_js)) - set(parameters) - {"time", "phase", "assembly", "assemblyTarget"}
            if not outputs:
                problems.append(f"{lesson.id}: outcome must check a computed result, not just a parameter or clock")
        if lesson.learning and not set(lesson.learning.focus) <= set(object_ids):
            problems.append(f"{lesson.id}: learning focus names unknown objects")
        foreign = [
            p
            for p in [*lesson.scene_state.params, *(c.symbol for c in lesson.controls), *(lesson.learning.test_params if lesson.learning else {})]
            if p not in parameters
        ]
        if foreign:
            problems.append(f"{lesson.id}: {sorted(set(foreign))} are not model parameters ({', '.join(parameters)})")
    if problems:
        raise ValueError("; ".join(problems))
    return [item.model_dump() for item in parsed]


def validate_world(world_js, modality, object_ids):
    """The world draws every scene object with one renderer and animates the checked model.js."""
    problems = []
    if not re.search(rf"export\s+const\s+dimensionality\s*=\s*{modality[0]}\s*;", world_js):
        problems.append(f"Declare export const dimensionality = {modality[0]};")
    if modality == "2d" and re.search(r"from\s+[\"\']three", world_js):
        problems.append("A 2D world cannot import three.js")
    unavailable = sorted(set(re.findall(r"[\"\'](three/addons/[^\"\']+|https?://[^\"\']+\.m?js)[\"\']", world_js)) - set(ADDONS))
    if unavailable:
        problems.append(f"Import only three, ./model.js and the available addons ({', '.join(ADDONS)}); not {unavailable}")
    if not re.search(r"from\s+[\"\']\./model\.js[\"\']", world_js):
        problems.append("Import the checked simulation from './model.js' instead of writing a new one")
    for name in EXPORTS:
        if not re.search(rf"export\s+(?:async\s+)?(?:function|const|let)\s+{name}\b", world_js):
            problems.append(f"Missing named export {name}")
    missing = [i for i in object_ids if not re.search(rf"[\"\'`]{i}[\"\'`]", world_js)]
    if missing:
        problems.append(f"Draw every scene object by its id; missing {missing}")
    network = re.search(r"\bfetch\s*\(|\b(?:WebSocket|RTCPeerConnection|EventSource|XMLHttpRequest|sendBeacon|importScripts|WebTransport)\b", world_js)
    if "<script" in world_js.lower() or network:
        problems.append("world.js is an ES module with no HTML or network calls" + (f" (found {network.group()})" if network else ""))
    if problems:
        raise ValueError("; ".join(problems))
    return world_js
