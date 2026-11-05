"""Prepared examples, replayed through the real pipeline for the labelled upload walkthrough.

Each example folder holds every stage's answer as a file (analysis, plan, evidence, model, validation,
model.js, scene, lessons, world), so the walkthrough calls no model.
"""

import json
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[1] / "static" / "demo"


SAMPLES = {"2d": SAMPLE, "3d": SAMPLE.parent / "demo3d", "attention2d": SAMPLE.parent / "attention2d", "attention3d": SAMPLE.parent / "attention3d"}


class DemoProvider:
    # The authored worlds are opened in a browser by the test suite, so the walkthrough doesn't reopen them.
    prepared = True

    def __init__(self, example="2d"):
        self.sample = SAMPLES[example]

    def read(self, name):
        return (self.sample / name).read_text()

    def answer(self, name, error=None):
        if error is not None:
            raise RuntimeError(f"The prepared example's {name} needs repair: {error}")
        return self.read(name)

    def vision_available(self):
        return False  # The walkthrough calls no model.

    def analyze(self, paper_text):
        return json.loads(self.read("analysis.json"))

    def observe(self, paper_text, figures):
        return json.loads(self.read("evidence.json"))

    def plan(self, analysis, evidence):
        return json.loads(self.read("plan.json"))

    def build_model(self, analysis, plan, previous=None, error=None):
        return self.answer("model.py", error)

    def validate(self, analysis, plan, output):
        return json.loads(self.read("validation.json"))

    def port_model(self, plan, model_code, previous=None, error=None):
        return self.answer("model.js", error)

    def design_scene(self, analysis, evidence, plan, state, previous=None, error=None):
        return json.loads(self.answer("scene.json", error))

    def write_lessons(self, analysis, plan, validation, scene, state, previous=None, error=None):
        return json.loads(self.answer("lessons.json", error))

    def build_world(self, plan, scene, lessons, model_js, state, previous=None, error=None):
        return self.answer("world.js", error)
