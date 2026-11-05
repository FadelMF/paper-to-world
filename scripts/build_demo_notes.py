"""Build the authored source PDF; no external research claims are implied."""

import argparse
import json
import sys
import textwrap
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.lesson_contract import validate_lessons

parser = argparse.ArgumentParser()
parser.add_argument("--demo", choices=["demo", "demo3d"], default="demo")
options = parser.parse_args()
DEMO = ROOT / "static" / options.demo
lessons = json.loads((DEMO / "lessons.json").read_text())
validate_lessons(lessons, [o["id"] for o in json.loads((DEMO / "scene.json").read_text())["objects"]], ["I", "tau"])
writer = PdfWriter()
font = DictionaryObject(
    {NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}
)
font_ref = writer._add_object(font)
extras = [
    "Parameters throughout these notes: rest/reset = -65 mV; resistance = 10 Mohm; default tau = 20 ms. A resting neuron starts at V = -65 mV. I is applied current in nA. These are illustrative model choices, not empirical measurements.",
    "Differential equation: tau * dV/dt = -(V - Vrest) + R*I. Numerical method: forward Euler, dt = 0.1 ms. At each step, V += (-(V+65)+10*I)/tau * 0.1. Equilibrium: Vrest + R*I. There is no stochastic input.",
    "After the Euler voltage update, if V >= -50 mV: increment spike count; set V = -65 mV; set refractory timer = 2 ms. While that timer is positive, decrement it by dt (clamped at zero) and hold V = -65 mV. A +20 mV graphical marker records an event, not an action-potential waveform.",
    "Reference targets measured over 1000 ms at tau=20 ms: I=0 nA -> 0 spikes; I=1 nA -> 0 spikes; I=2 nA -> 33 spikes; I=3 nA -> 63 spikes. Approximate continuous-model rate for I>1.5 nA: f=1000/(tau*ln(R*I/(R*I-15))+2) Hz. Finite observation time and discrete Euler updates cause small differences from this formula. Passing numerical agreement is not validation against a published paper or biological data.",
]
if options.demo == "demo3d":
    extras[0] += (
        " The 3D anatomy is schematic. Dendrites are drawn as branching inputs, the soma as the cell body, and six myelin sheaths around the axon. Geometry and myelin do not affect this single-compartment model."
    )
    extras[1] += (
        " One voltage represents the whole neuron. This is not a spatial cable model. Branches and membrane pores illustrate the lesson, not individually simulated compartments or ion channels."
    )
    extras[2] += (
        " Each spike triggers a 60 ms illustrative transit animation along the 3D axon. This duration is a visualization choice, not a computed or measured conduction speed."
    )
    extras[3] += " The 3D presentation uses exactly the same discrete update rule as the Python and 2D references."


def ascii_text(text):
    return (
        text.replace("−", "-")
        .replace("τ", "tau")
        .replace("Ω", "ohm")
        .replace("→", "->")
        .replace("≤", "<=")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .encode("ascii", "replace")
        .decode()
    )


for index, lesson in enumerate(lessons):
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
    lines = [
        "PAPER-TO-WORLD / AUTHORED DEMONSTRATION NOTES",
        "",
        lesson["source"]["title"],
        f"Page {index + 1}: {lesson['title']}",
        "",
        "Background teaching material. Not a published research paper.",
        "",
    ]
    paragraphs = lesson["intro"] + [extras[index], lesson["predict"]["why"]]
    paragraphs += [f"{term['term']}: {term['definition']}" for term in lesson["terms"]]
    for paragraph in paragraphs:
        lines.extend(textwrap.wrap(ascii_text(paragraph), width=83))
        lines.append("")
    leading = min(15, 680 / len(lines))
    commands = [f"BT /F1 10 Tf {leading:.2f} TL 48 748 Td"]
    for line in lines:
        escaped = ascii_text(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({escaped}) Tj T*")
    commands.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
writer.add_metadata({"/Title": lessons[0]["source"]["title"], "/Author": "Paper-to-World demo"})
writer.write(DEMO / "paper.pdf")
print("Built four-page demo source; lesson contract valid.")
