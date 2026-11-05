"""Paper-grounded visual workflow: figure captions, visual evidence, scene design, JS port parity, lessons and world."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from paper_fixture import FIGURE_BOX, HEADER, INTERNAL_WORDS, PRINTED_EQ1, READING, TITLE, ScriptedLLM, blank_pdf, no_browser, paper_pdf, plan, scripted_model

from app import agents, llm, main, pipeline
from app.evaluation import report as evaluation_report
from app.evaluation import summarize
from app.figures import render_figures
from app.lesson_contract import validate_lessons, validate_world
from app.parity import check_port, parity_cases, reference_states
from app.pdf import figure_captions, figure_mentions, read_pdf, select_figures
from app.render_check import check_render
from app.visual import figure_anchors, normalize_critique, normalize_evidence, normalize_reading, validate_scene

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "static" / "demo"
DEMO3D = ROOT / "static" / "demo3d"
STATE = {"V": -65.0, "time": 0.0, "spikes": 0, "refractory": 0.0, "rate": 0.0, "I": 0.0, "tau": 20.0}


def load(folder, name):
    return json.loads((folder / name).read_text())


class FigureCaptionTests(unittest.TestCase):
    def test_captions_are_found_with_pages_and_in_text_mentions_ignored(self):
        pages = [
            "Intro. As shown in Figure 1, the cell is round.\nFigure 1: A neuron with a round soma\nand a long axon.\n\nBody text.",
            "Fig. 2. Voltage over time.\nMethods follow.",
            "Figure 1 shows the same cell again.\nFIGURE 3 | Branching dendrites.",
        ]
        self.assertEqual(
            figure_captions(pages),
            [
                {"id": "fig1", "page": 1, "caption": "Figure 1: A neuron with a round soma and a long axon."},
                {"id": "fig2", "page": 2, "caption": "Fig. 2. Voltage over time. Methods follow."},
                {"id": "fig3", "page": 3, "caption": "FIGURE 3 | Branching dendrites."},
            ],
        )

    def test_caption_variants_get_distinct_ids(self):
        pages = [
            "Fig 3: No period.\n\nFigure 2: Main.\n\nExtended Data Fig. 2 | Extra.\n\nFigure S1. Supplement.",
            "Main text cites Figure 2. Extended Data Fig. 2 shows more.",
        ]
        self.assertEqual([c["id"] for c in figure_captions(pages)], ["fig3", "fig2", "figED2", "figS1"])
        self.assertEqual(figure_mentions(pages, "fig2"), ["Main text cites Figure 2."])
        self.assertEqual(figure_mentions(pages, "figED2"), ["Extended Data Fig. 2 shows more."])

    def test_the_most_cited_figures_are_kept_in_paper_order(self):
        captions = [{"id": f"fig{i}", "page": 1, "caption": f"Figure {i}: x"} for i in (1, 2, 3)]
        pages = ["See Figure 3. Again Figure 3. And Figure 1. Not figure two."]
        self.assertEqual([c["id"] for c in select_figures(pages, captions, 2)], ["fig1", "fig3"])
        self.assertEqual(select_figures(pages, captions, 5), captions)

    def test_drawings_without_a_numbered_caption_are_figures_too(self):
        from paper_fixture import FIGURES

        data = paper_pdf(figures={2: FIGURES[2].split(b"BT /F1 10 Tf 14 TL")[0]})
        [figure] = render_figures(data, figure_captions(read_pdf(data)))
        self.assertEqual((figure["id"], figure["caption"]), ("figP2a", ""))
        for got, want in zip(figure["box"], FIGURE_BOX, strict=False):
            self.assertAlmostEqual(got, want, delta=0.04)
        self.assertEqual(figure_mentions(["See figure P2a."], "figP2a"), [])

    def test_equations_tables_and_rules_are_not_figures(self):
        rules = b"0.5 w 100 600 m 500 600 l S 100 560 m 500 560 l S 100 520 m 500 520 l S 300 500 m 300 620 l S 120 580 m 160 580 l S"
        data = paper_pdf(figures={2: rules})
        self.assertEqual(render_figures(data, figure_captions(read_pdf(data))), [])

    def test_fixture_pdf_caption_survives_extraction(self):
        captions = figure_captions(read_pdf(paper_pdf()))
        self.assertEqual([c["id"] for c in captions], ["fig1"])
        self.assertIn("round soma", captions[0]["caption"])


class FigureTests(unittest.TestCase):
    def test_vector_figure_is_cut_out_above_its_caption(self):
        data = paper_pdf()
        [figure] = render_figures(data, figure_captions(read_pdf(data)))
        for got, want in zip(figure["box"], FIGURE_BOX, strict=False):
            self.assertAlmostEqual(got, want, delta=0.04)
        self.assertEqual(figure["page_image"].size, (1224, 1584))

    def test_a_drawing_running_past_its_caption_is_cut_at_the_caption(self):
        # A box from y=400 to y=600 pt with the caption's top at about 450 pt: most of it is above the caption.
        drawing = b"1 w 60 400 m 300 400 l 300 600 l 60 600 l h S BT /F1 10 Tf 48 440 Td (Figure 1: A tall box.) Tj ET"
        data = paper_pdf(figures={2: drawing})
        [figure] = render_figures(data, figure_captions(read_pdf(data)))
        self.assertAlmostEqual(figure["box"][1], 1 - 600 / 792, delta=0.02)
        self.assertLess(figure["box"][3], 0.48)  # cut near the caption top (0.435 + margin); uncut it would reach 0.51

    def test_a_drawing_in_the_next_column_is_left_out(self):
        # Left column: a figure above its caption. Right column, at the same height: another drawing.
        drawing = (
            b"1 w 60 480 m 280 480 l 280 600 l 60 600 l h S "
            b"1 w 330 480 m 560 480 l 560 600 l 330 600 l h S "
            b"BT /F1 10 Tf 60 460 Td (Figure 1: The left figure.) Tj ET"
        )
        data = paper_pdf(figures={2: drawing})
        [figure] = render_figures(data, figure_captions(read_pdf(data)))
        self.assertLess(figure["box"][2], 300 / 612)

    def test_figure_without_drawings_falls_back_to_its_page(self):
        data = paper_pdf(figures={2: b"BT /F1 10 Tf 48 440 Td (Figure 1: Only words here.) Tj ET"})
        [figure] = render_figures(data, figure_captions(read_pdf(data)))
        self.assertEqual(figure["box"], [0.0, 0.0, 1.0, 1.0])

    def test_mentions_skip_captions_and_abbreviations_do_not_split_sentences(self):
        pages = ["As Figure 1 shows, the soma is round. Other text.\nFigure 1: The caption.", "See Fig. 1 for layout. Figure 12 differs."]
        self.assertEqual(figure_mentions(pages, "fig1"), ["As Figure 1 shows, the soma is round.", "See Fig. 1 for layout."])

    def test_readings_keep_only_a_usable_box_and_named_elements(self):
        self.assertEqual(normalize_reading(READING)["box"], READING["box"])
        for box in [[0.5, 0.5, 0.4, 0.9], [0, 0, 0.05, 0.05], [0, 0, 2, 1], "top", None]:
            self.assertIsNone(normalize_reading({**READING, "box": box})["box"])
        self.assertEqual(len(normalize_reading({"elements": [{"name": "a"}, {"label": "x"}, "junk"]})["elements"]), 1)

    def test_element_boxes_anchor_paper_objects_inside_their_figure(self):
        reading = normalize_reading({**READING, "elements": READING["elements"] + [{"name": "nucleus", "box": [2, 0, 3, 1]}]})
        self.assertIsNone(reading["elements"][-1]["box"])
        evidence = {
            "figures": [{"id": "fig1", "box": READING["box"], "reading": reading}],
            "entities": [
                {"id": "soma", "name": "Soma", "figure": "fig1", "element": "soma"},
                {"id": "axon", "name": "Axon", "figure": "fig1"},
                {"id": "leak", "name": "Leak"},
            ],
        }
        scene = {
            "objects": [
                {"id": "membrane", "basis": "paper", "evidence": "soma"},
                {"id": "axon", "basis": "paper", "evidence": "axon"},
                {"id": "leak", "basis": "paper", "evidence": "leak"},
                {"id": "rate", "basis": "hypothesis", "evidence": None},
            ]
        }
        anchors = figure_anchors(scene, evidence)
        self.assertEqual(sorted(anchors), ["axon", "membrane"])
        self.assertLess(anchors["membrane"][1], anchors["axon"][1])
        self.assertTrue(all(0 <= v <= 1 for _, x, y in anchors.values() for v in (x, y)))

    def test_critique_severity_defaults_to_major(self):
        critique = normalize_critique({"issues": [{"problem": "Wrong shape"}, {"problem": "Small", "severity": "MINOR"}, {"fix": "no problem"}]})
        self.assertEqual([i["severity"] for i in critique["issues"]], ["major", "minor"])
        self.assertEqual(len(critique["major"]), 1)


class EvidenceTests(unittest.TestCase):
    def test_entities_are_verified_by_quote_or_by_what_a_read_figure_shows(self):
        pages = read_pdf((DEMO / "paper.pdf").read_bytes())
        evidence = load(DEMO, "evidence.json")
        evidence["entities"] += [
            {"id": "dendrites", "name": "Dendrites", "page": 1, "quote": "Dendrites are drawn as a dense forest."},
            {"id": "soma", "name": "Cell body", "page": 2, "quote": None, "figure": "fig1", "element": "soma"},
            {"id": "nucleus", "name": "Nucleus", "page": 2, "figure": "fig1", "element": "nucleus"},
            {"name": "no id"},
        ]
        figures = [{"id": "fig1", "page": 2, "caption": "Figure 1: x", "image": "figure-1.png", "box": READING["box"], "reading": normalize_reading(READING)}]
        result = normalize_evidence(evidence, pages, figures)
        verified = {e["id"]: e["verified_by"] for e in result["entities"]}
        self.assertTrue(all(verified[k] == "text" for k in ["membrane", "input", "axon", "leak", "threshold", "spike"]))
        self.assertEqual((verified["dendrites"], verified["soma"], verified["nucleus"]), (None, "figure", None))
        self.assertEqual(result["figures"], figures)
        unread = normalize_evidence(evidence, pages, [{**figures[0], "reading": None}])
        self.assertIsNone(next(e for e in unread["entities"] if e["id"] == "soma")["verified_by"])
        self.assertEqual(normalize_evidence({}, pages, []), {"subject": "", "figures": [], "entities": []})


class SceneTests(unittest.TestCase):
    def check(self, scene, folder=DEMO, modality="2d"):
        pages = read_pdf((folder / "paper.pdf").read_bytes())
        return validate_scene(scene, modality, normalize_evidence(load(folder, "evidence.json"), pages, []), STATE)

    def test_authored_scenes_are_valid(self):
        self.assertEqual(len(self.check(load(DEMO, "scene.json"))["objects"]), 7)
        self.assertEqual(len(self.check(load(DEMO3D, "scene.json"), DEMO3D, "3d")["objects"]), 8)

    def test_every_problem_is_reported_at_once(self):
        scene = load(DEMO, "scene.json")
        objects = scene["objects"]
        objects[1]["id"] = "input"  # duplicate
        objects[2]["parent"] = "ghost"  # unknown parent
        objects[3]["evidence"] = "made_up"  # paper basis without evidence
        objects[6]["rationale"] = ""  # hypothesis without ideation
        objects[4]["primitive"] = "sphere"  # 3D primitive in a 2D scene
        objects[5]["position"] = [1, 2, 3]  # wrong dimension
        objects[0]["bindings"] = [{"state": "voltage_mv", "property": "fill"}]  # not in the JS model state
        scene["visual_needs"][0]["objects"] = ["nowhere"]
        with self.assertRaises(ValueError) as caught:
            self.check(scene)
        message = str(caught.exception)
        for words in ["duplicate", "ghost", "made_up", "rationale", "sphere", "position", "voltage_mv", "nowhere"]:
            self.assertIn(words, message)

    def test_shapes_must_lean_on_the_paper_when_it_describes_them(self):
        scene = load(DEMO, "scene.json")
        for item in scene["objects"]:
            item.update(basis="hypothesis", evidence=None, rationale="Imagined.")
        with self.assertRaisesRegex(ValueError, "from the paper"):
            self.check(scene)

    def test_scene_needs_a_live_binding_and_enough_objects(self):
        scene = load(DEMO, "scene.json")
        for item in scene["objects"]:
            item["bindings"] = []
        with self.assertRaisesRegex(ValueError, "binding"):
            self.check(scene)
        scene = load(DEMO, "scene.json")
        scene["objects"] = scene["objects"][:2]
        with self.assertRaisesRegex(ValueError, "at least 3"):
            self.check(scene)


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        shutil.copy(DEMO / "model.py", self.folder / "model.py")
        self.cases = parity_cases(plan("2d"))

    def tearDown(self):
        self.tmp.cleanup()

    def port(self, text):
        (self.folder / "model.js").write_text(text)
        return check_port(self.folder, self.cases, reference_states(self.folder, self.cases))

    def test_cases_cover_defaults_and_control_edges(self):
        self.assertEqual(self.cases[:3], [[{"I": 0.0, "tau": 20.0}, 1], [{"I": 0.0, "tau": 20.0}, 20], [{"I": 0.0, "tau": 20.0}, 1000]])
        self.assertIn([{"I": 5.0, "tau": 20.0}, 1000], self.cases)
        self.assertIn([{"I": 0.0, "tau": 5.0}, 1000], self.cases)

    def test_reference_states_come_from_the_python_run_function(self):
        states = reference_states(self.folder, self.cases)
        self.assertEqual(len(states), len(self.cases))
        self.assertGreater(states[self.cases.index([{"I": 5.0, "tau": 20.0}, 1000])]["spikes"], 0)
        (self.folder / "model.py").write_text('print("no run function")')
        with self.assertRaisesRegex(ValueError, "run"):
            reference_states(self.folder, self.cases)

    def test_demo_port_matches(self):
        self.assertEqual(self.port((DEMO / "model.js").read_text()), len(self.cases))

    def test_mismatches_are_reported_per_case(self):
        source = (DEMO / "model.js").read_text()
        with self.assertRaises(ValueError) as caught:
            self.port(source.replace("s.spikes++", "s.spikes += 2"))
        self.assertIn("spikes", str(caught.exception))
        self.assertIn("'I': 5.0", str(caught.exception))
        stepped = source.replace("for (let i = 0; i < steps; i++) advanceModel(s);", "for (let i = 0; i < steps; i++) advanceModel(s); s.V = 0;")
        with self.assertRaisesRegex(ValueError, "advanceModel"):
            self.port(stepped)
        with self.assertRaisesRegex(ValueError, "missing"):
            self.port(source.replace("rate: 0,", "").replace("s.rate = s.spikes / (s.time / 1000);", ""))

    def test_port_must_be_pure(self):
        source = (DEMO / "model.js").read_text()
        for bad, words in [
            ("import * as THREE from 'three';\n" + source, "import"),
            (source + "\ndocument.title = 1;", "document"),
            (source.replace("export function run", "function run"), "run"),
            ('throw new Error("boom")', "boom"),
        ]:
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, words):
                self.port(bad)


class BuildContractTests(unittest.TestCase):
    def test_lessons_only_use_scene_objects_and_model_parameters(self):
        lessons = load(DEMO, "lessons.json")
        ids = [o["id"] for o in load(DEMO, "scene.json")["objects"]]
        self.assertEqual(len(validate_lessons(lessons, ids, ["I", "tau"])), 4)
        with self.assertRaisesRegex(ValueError, "membrane"):
            validate_lessons(lessons, [i for i in ids if i != "membrane"], ["I", "tau"])
        with self.assertRaisesRegex(ValueError, "tau"):
            validate_lessons(lessons, ids, ["I"])

    def test_world_imports_the_checked_model_and_draws_every_object(self):
        for folder, modality in [(DEMO, "2d"), (DEMO3D, "3d")]:
            ids = [o["id"] for o in load(folder, "scene.json")["objects"]]
            world = (folder / "world.js").read_text()
            validate_world(world, modality, ids)
            with self.subTest(modality=modality):
                with self.assertRaisesRegex(ValueError, "model.js"):
                    validate_world(world.replace("from './model.js'", "from './sim.js'"), modality, ids)
                with self.assertRaisesRegex(ValueError, "flagellum"):
                    validate_world(world, modality, [*ids, "flagellum"])
                with self.assertRaisesRegex(ValueError, "dimensionality"):
                    validate_world(world, "3d" if modality == "2d" else "2d", ids)
                with self.assertRaisesRegex(ValueError, "setAssembly"):
                    validate_world(world.replace("export function setAssembly(", "function setAssembly("), modality, ids)
                for extra in [
                    "import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';",
                    "import confetti from 'https://cdn.example.com/confetti.js';",
                ]:
                    with self.assertRaisesRegex(ValueError, "available addons"):
                        validate_world(extra + "\n" + world, modality, ids)
                for call in ["new WebSocket('wss://x')", "new RTCPeerConnection()", "navigator.sendBeacon('/x', '')", "fetch('/api/runs')"]:
                    with self.assertRaisesRegex(ValueError, "network"):
                        validate_world(world + "\n" + call + ";", modality, ids)

    def test_pages_that_run_worlds_load_only_from_this_server(self):
        with TestClient(main.app) as client:
            policy = client.get("/demo").headers["content-security-policy"]
            self.assertNotIn("content-security-policy", client.get("/api/config").headers)
        self.assertIn("default-src 'self'", policy)
        self.assertIn("connect-src 'self';", policy)
        self.assertNotIn("https://", policy)  # three.js, KaTeX and Inter are served from static/vendor
        self.assertIn("object-src 'none'", policy)
        self.assertNotIn("'unsafe-inline' https://cdn", policy.split("style-src")[0])  # scripts run only from files and hashed import maps


# A small DOM world: fast to open, and each defect below is one text replacement away.
TINY_WORLD = """export const dimensionality = 2;
import { createModel, advanceModel } from './model.js';
const ids = ['membrane', 'axon', 'leak'];
// Boxes as shares of the world's width and height, so the drawing fits a desktop and a phone panel.
const layout = {membrane: [0.1, 0.2, 0.15, 0.25], axon: [0.32, 0.3, 0.6, 0.05], leak: [0.12, 0.6, 0.05, 0.15]};
let el, state = createModel(), running = false, assemblyTarget = 0;
const boxes = () => Object.fromEntries(ids.map(id => { const [x, y, w, h] = layout[id];
  return [id, {x: x * el.clientWidth, y: y * el.clientHeight, width: w * el.clientWidth, height: h * el.clientHeight}]; }));
function place() { for (const [id, box] of Object.entries(boxes())) { const tag = el.querySelector(`[data-object="${id}"]`); if (tag) Object.assign(tag.style, {left: box.x + 'px', top: box.y - 26 + 'px'}); } }
export function init(container) {
  el = container;
  for (const id of ids) { const tag = document.createElement('button'); tag.dataset.object = id; tag.textContent = id;
    Object.assign(tag.style, {position: 'absolute', font: '11px sans-serif', padding: '2px 4px'}); container.append(tag); }
  place(); new ResizeObserver(place).observe(container);
  setInterval(() => { if (running) for (let i = 0; i < 10; i++) advanceModel(state); }, 50);
}
export function setParams(params) { Object.assign(state, params); }
export function setLesson(scene) { state = createModel(scene.params); }
export function highlight() {}
export function getState() { return {...state, assembly: assemblyTarget, assemblyTarget}; }
export function play() { running = true; }
export function pause() { running = false; }
export function step() { advanceModel(state); }
export function onObjectClick() {}
export function setAssembly(amount) { if (Number.isFinite(amount)) assemblyTarget = Math.min(1, Math.max(0, amount)); }
export function objectBounds() { return boxes(); }
"""
TINY_SCENE = {
    "modality": "2d",
    "objects": [
        {"id": "membrane", "position": [-100, 50], "size": [120, 120]},
        {"id": "axon", "position": [150, 30], "size": [300, 20]},
        {"id": "leak", "position": [-90, -80], "size": [40, 60]},
    ],
}
TINY_LESSONS = [
    {
        "id": f"l{i}",
        "scene_state": {"visible": ["membrane", "axon", "leak"], "camera": [0, 0, 6], "params": {"I": 2.0, "tau": 20.0}},
        "controls": [{"symbol": "I", "min": 0, "max": 5, "default": 2}],
        "challenge": {"check_js": "state.V > -60"},
    }
    for i in (1, 2)
]


class RenderCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        shutil.copy(DEMO / "model.js", self.folder / "model.js")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_sound_world_passes_with_a_screenshot_per_lesson(self):
        report = check_render(self.folder, TINY_WORLD, TINY_LESSONS, TINY_SCENE)
        self.assertEqual([item["screenshot"] for item in report["lessons"]], ["render/lesson-1.png", "render/lesson-2.png"])
        self.assertIn(report["isolation"], ("chromium sandbox", "landlock and seccomp"))
        self.assertTrue((self.folder / "render" / "lesson-1.png").read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(json.loads((self.folder / "render" / "report.json").read_text())["problems"], [])
        self.assertFalse((self.folder / "world.js").exists())

    def test_every_drawing_problem_is_reported_at_once(self):
        broken = (
            TINY_WORLD.replace("for (const id of ids) {", "for (const id of ids.filter(id => id !== 'leak')) {")  # no tag for leak
            .replace("axon: [0.32,", "axon: [3.2,")  # drawn off-screen
            .replace("leak: [0.12, 0.6,", "leak: [0.12, 0.05,")  # above the membrane
            .replace("if (running) for", "if (false) for")  # time stands still
            .replace("export function setParams(params) { Object.assign(state, params); }", "export function setParams(params) {}")
            .replace("container.append(tag); }", "container.append(tag); }\n  fetch('https://example.com/data.json').catch(() => {});")
            .replace("membrane: [0.1, 0.2,", "membrane: [-0.08, 0.2,")
        )  # its tag hangs off the left edge
        lessons = [dict(TINY_LESSONS[0], challenge={"check_js": "state.missing.value > 1"})]
        with self.assertRaises(ValueError) as caught:
            check_render(self.folder, broken, lessons, TINY_SCENE)
        report = str(caught.exception)
        for words in [
            'data-object="leak"',
            "axon is drawn outside",
            "puts membrane above leak",
            "phone, lesson 1",
            "time does not advance",
            "setParams({I: 5})",
            "check_js throws",
            "example.com",
            "tag for membrane is cut off",
        ]:
            self.assertIn(words, report)

    def test_paper_objects_keep_the_order_of_their_figure(self):
        anchors = {"membrane": ("fig1", 0.2, 0.5), "axon": ("fig1", 0.8, 0.5)}
        check_render(self.folder, TINY_WORLD, TINY_LESSONS[:1], TINY_SCENE, anchors)
        with self.assertRaisesRegex(ValueError, "paper's fig1 puts axon left of membrane"):
            check_render(self.folder, TINY_WORLD, TINY_LESSONS[:1], TINY_SCENE, {"membrane": ("fig1", 0.8, 0.5), "axon": ("fig1", 0.2, 0.5)})
        check_render(self.folder, TINY_WORLD, TINY_LESSONS[:1], TINY_SCENE, {"membrane": ("fig1", 0.8, 0.5), "axon": ("fig2", 0.2, 0.5)})

    def test_a_drawing_that_only_fits_a_desktop_fails_on_a_phone(self):
        fixed = TINY_WORLD.replace(
            "return [id, {x: x * el.clientWidth, y: y * el.clientHeight, width: w * el.clientWidth, height: h * el.clientHeight}];",
            "return [id, {x: x * 900, y: y * 600, width: w * 900, height: h * 600}];",
        )
        with self.assertRaises(ValueError) as caught:
            check_render(self.folder, fixed, TINY_LESSONS[:1], TINY_SCENE)
        report = str(caught.exception)
        self.assertIn("phone, lesson 1 (l1): axon is drawn outside the world", report)
        self.assertNotIn("\nlesson 1 (l1): axon", report)
        self.assertTrue((self.folder / "render" / "lesson-1-phone.png").is_file())

    def test_a_world_that_cannot_start_is_reported(self):
        with self.assertRaisesRegex(ValueError, "failed to load or init"):
            check_render(
                self.folder,
                TINY_WORLD.replace("export function init(container) {", 'export function init(container) { throw new Error("no canvas");'),
                TINY_LESSONS,
                TINY_SCENE,
            )


class AgentRequestTests(unittest.TestCase):
    def test_designer_sees_paper_evidence_ideation_rules_and_model_state(self):
        evidence = load(DEMO, "evidence.json")
        with patch.object(llm, "chat", return_value=json.dumps(load(DEMO, "scene.json"))) as chat:
            agents.design_scene({"concepts": [{"name": "Leak"}]}, evidence, plan("3d"), STATE)
        system, user = chat.call_args.args
        self.assertIn("hypothesis", system)
        self.assertIn("sphere", system)
        self.assertNotIn("ellipse", system)
        self.assertIn("Membrane: The boundary", user)
        self.assertIn('"refractory"', user)

    def test_builder_gets_scene_lessons_and_model_source_for_one_renderer(self):
        for mode, present, absent in [("2d", "2D Canvas", "MeshPhysicalMaterial"), ("3d", "MeshPhysicalMaterial", "2D Canvas")]:
            with patch.object(agents, "chat", return_value="```js\nexport const x = 1;\n```") as chat:
                world = agents.build_world(plan(mode), load(DEMO, "scene.json"), load(DEMO, "lessons.json"), "export function run() {}", STATE)
            system, user = chat.call_args.args
            self.assertEqual(world, "export const x = 1;\n")
            self.assertIn(present, system)
            self.assertNotIn(absent, system)
            self.assertIn("export function run() {}", user)
            self.assertIn('"membrane"', user)

    def test_viewer_sees_the_page_and_the_guessed_crop(self):
        with patch.object(llm, "chat_vision", return_value=json.dumps(READING)) as vision:
            agents.read_figure({"id": "fig1", "page": 2, "caption": "Figure 1: A neuron"}, b"page", b"crop", ["As Figure 1 shows."])
        system, user, images = vision.call_args.args
        self.assertEqual(images, [b"page", b"crop"])
        self.assertIn("As Figure 1 shows.", user)
        self.assertIn("Do not add parts from your own knowledge", system)

    def test_critic_gets_labelled_screenshots_then_figures(self):
        figure = {"id": "fig1", "page": 2, "caption": "Figure 1: A neuron"}
        with patch.object(llm, "chat_vision", return_value='{"issues": []}') as vision:
            agents.critique(load(DEMO, "scene.json"), {"entities": []}, load(DEMO, "lessons.json"), [(f"l{i}", b"shot") for i in range(8)], [(figure, b"fig")])
        _, user, images = vision.call_args.args
        self.assertEqual(images, [b"shot"] * agents.CRITIC_SCREENSHOTS + [b"fig"])
        self.assertIn("Image 7: paper figure fig1 (page 2)", user)

    def test_repairs_carry_the_previous_answer_and_the_failure(self):
        with patch.object(agents, "chat", return_value="```js\nfixed\n```") as chat:
            agents.port_model(plan("2d"), "python code", "old js", "spikes differ")
        user = chat.call_args.args[1]
        self.assertIn("old js", user)
        self.assertIn("spikes differ", user)
        self.assertIn("python code", user)


class WorkflowTests(unittest.TestCase):
    """Real PDF → every stage → served world, with the drawing opened in Chromium. 3D runs with a vision model, 2D without."""

    def run_paper(self, tmp, modality, vision):
        scripted = ScriptedLLM(modality)
        self.shown = []  # every activity line the progress screen showed
        original = pipeline.write_json

        def record(directory, name, data):
            if name == "status.json":
                self.shown += [a["text"] for a in data["activity"] if a["text"] not in self.shown]
            original(directory, name, data)

        with (
            patch.object(pipeline, "write_json", side_effect=record),
            patch.object(main, "RUNS", Path(tmp)),
            patch.object(main, "configured", return_value=True),
            patch.object(main, "launch_run", side_effect=pipeline.run_pipeline),
            scripted_model(scripted, vision),
            TestClient(main.app) as client,
        ):
            run_id = client.post("/api/runs", files={"file": ("paper.pdf", paper_pdf(), "application/pdf")}).json()["id"]
            yield scripted, client, run_id, Path(tmp) / run_id

    def check_common(self, scripted, client, run_id, run, modality):
        status = client.get(f"/api/runs/{run_id}").json()["status"]
        self.assertIsNone(status["error"], (run / "debug.log").read_text())
        calls = dict(scripted.calls)
        self.assertIn("Figure 1: A neuron drawn as a round soma", calls["Observer"])
        self.assertIn("round soma", calls["Planner"])
        self.assertIn('"refractory"', calls["Designer"])
        self.assertIn("Leaky integration", calls["Designer"])
        self.assertIn("export function advanceModel", calls["Builder"])
        self.assertIn('"rate"', calls["Builder"])
        repairs = [user for name, user in scripted.calls if name in ("Porter", "Designer")][1::2]
        self.assertIn("spikes", repairs[0])
        self.assertIn("voltage_mv", repairs[1])

        self.assertEqual(pipeline.read_json(run, "parity.json")["cases"], len(parity_cases(plan(modality))))
        scene = pipeline.read_json(run, "scene.json")
        self.assertEqual(scene["modality"], modality)
        self.assertEqual(
            status["discovered"]["parts"],
            {"paper": sum(o["basis"] == "paper" for o in scene["objects"]), "illustrative": sum(o["basis"] == "hypothesis" for o in scene["objects"])},
        )
        self.assertEqual(status["discovered"]["figures"], 1)
        model_js = client.get(f"/api/runs/{run_id}/files/model.js")
        self.assertIn("javascript", model_js.headers["content-type"])
        self.assertIn("export function run", model_js.text)
        world = client.get(f"/api/runs/{run_id}/files/world.js").text
        self.assertIn("from './model.js'", world)
        self.assertIn(f"export const dimensionality = {modality[0]};", world)
        figure = client.get(f"/api/runs/{run_id}/files/figure-1.png")
        self.assertEqual(figure.headers["content-type"], "image/png")
        report = json.loads((run / "render" / "report.json").read_text())
        self.assertEqual((report["problems"], len(report["lessons"])), ([], 4))
        activity = " ".join(self.shown)
        self.assertIsNone(INTERNAL_WORDS.search(activity), activity)
        self.assertIn(
            "Drew 7 parts and checked every lesson in a browser" if modality == "2d" else "Drew 8 parts and checked every lesson in a browser", self.shown
        )

        paper_text = scripted.calls[0][1]
        for leaked in [HEADER, "Lapicque", "ﬁ", "\x00"]:
            self.assertNotIn(leaked, paper_text)
        self.assertIn("integrate-and-fire", paper_text)
        self.assertEqual(status["discovered"]["title"], TITLE)
        self.assertEqual(status["discovered"]["modality"], modality)
        self.assertEqual(status["discovered"]["checks"], {"passed": 2, "total": 2})
        self.assertEqual(client.get(f"/learn/{run_id}").status_code, 200)
        self.assertEqual(len(client.get(f"/api/runs/{run_id}/files/lessons.json").json()), 4)
        self.assertTrue(client.get(f"/api/runs/{run_id}/files/paper.pdf").content.startswith(b"%PDF"))
        self.assertEqual(len(client.get(f"/api/runs/{run_id}/files/pages.json").json()), 5)
        listed = next(r for r in client.get("/api/runs").json() if r["id"] == run_id)
        self.assertTrue(listed["ready"])
        self.assertEqual(listed["modality"], modality)
        return status

    def test_3d_with_a_vision_model_reads_figures_and_answers_the_critic(self):
        with tempfile.TemporaryDirectory() as tmp:
            for scripted, client, run_id, run in self.run_paper(tmp, "3d", vision=True):
                self.check_common(scripted, client, run_id, run, "3d")
                self.assertEqual(
                    [name for name, _ in scripted.calls],
                    [
                        "Analyst",
                        "Analyst",
                        "Proofreader",
                        "Viewer",
                        "Observer",
                        "Planner",
                        "Modeler",
                        "Validator",
                        "Porter",
                        "Porter",
                        "Designer",
                        "Designer",
                        "Writer",
                        "Builder",
                        "Builder",
                        "Critic",
                        "Builder",
                        "Critic",
                    ],
                )
                images = dict((agent, len(sent)) for agent, sent in scripted.images)
                self.assertEqual(images, {"Proofreader": 1, "Viewer": 2, "Critic": 5})  # Critic: 4 lesson screenshots + figure 1, cited through the axon
                equation = pipeline.read_json(run, "analysis.json")["equations"][0]
                self.assertEqual((equation["latex"], equation["checked"]), (PRINTED_EQ1, "page"))
                self.assertIn(json.dumps(PRINTED_EQ1), dict(scripted.calls)["Writer"])
                self.assertIn("Checked 1 equation against the printed page", self.shown)
                self.assertIn("The axon is shorter than in Figure 1.", [user for name, user in scripted.calls if name == "Builder"][-1])
                self.assertNotIn("Tags could be lighter", [user for name, user in scripted.calls if name == "Builder"][-1])
                evidence = pipeline.read_json(run, "evidence.json")
                self.assertEqual(
                    {e["id"]: e["verified_by"] for e in evidence["entities"]},
                    {"membrane": "text", "axon": "text", "input": "text", "threshold": "text", "spike": None, "dendrites": "figure"},
                )
                self.assertEqual(evidence["figures"][0]["box"], READING["box"])
                observer = dict(scripted.calls)["Observer"]
                self.assertIn('"elements"', observer)
                self.assertIn("forks at its end", observer)
                critique = pipeline.read_json(run, "critique.json")
                self.assertEqual((critique["round"], critique["major"]), (2, []))
                self.assertIn("Compared your world with the paper and 1 of its figures", self.shown)
                summary = summarize(run)
                self.assertTrue(summary["ready"])
                self.assertEqual(summary["repairs"], {"Reference model": 0, "Browser model": 1, "Scene": 1, "Lessons": 0, "World": 1})
                self.assertEqual(
                    (summary["figures"], summary["entities"], summary["equations"]),
                    ({"found": 1, "read": 1}, {"total": 6, "verified": 5}, {"total": 1, "matched_page": 1}),
                )
                self.assertEqual((summary["render_problems"], summary["critic_major_left"], summary["modality"]), (0, 0, "3d"))
                self.assertTrue((run / "usage.json").is_file())
                totals = evaluation_report([summary, {**summary, "ready": False, "seconds": 1}])
                self.assertEqual((totals["runs"], totals["ready"], totals["repairs"]["World"]), (2, 1, 2))
                self.assertIn("Noted 6 parts the paper describes, looking closely at its 1 figure", self.shown)

    def test_2d_without_a_vision_model_uses_captions_and_layout_guesses(self):
        with tempfile.TemporaryDirectory() as tmp:
            for scripted, client, run_id, run in self.run_paper(tmp, "2d", vision=False):
                self.check_common(scripted, client, run_id, run, "2d")
                self.assertEqual(
                    [name for name, _ in scripted.calls],
                    [
                        "Analyst",
                        "Analyst",
                        "Observer",
                        "Planner",
                        "Modeler",
                        "Validator",
                        "Porter",
                        "Porter",
                        "Designer",
                        "Designer",
                        "Writer",
                        "Builder",
                        "Builder",
                    ],
                )
                self.assertEqual(scripted.images, [])
                evidence = pipeline.read_json(run, "evidence.json")
                self.assertIsNone(evidence["figures"][0]["reading"])
                for got, want in zip(evidence["figures"][0]["box"], FIGURE_BOX, strict=False):
                    self.assertAlmostEqual(got, want, delta=0.04)
                self.assertIsNone(next(e for e in evidence["entities"] if e["id"] == "dendrites")["verified_by"])
                self.assertFalse((run / "critique.json").exists())
                self.assertIn("Noted 6 parts the paper describes and 1 figure caption", self.shown)

    def test_a_scanned_paper_is_transcribed_by_the_vision_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "paper.pdf").write_bytes(blank_pdf(5))
            pipeline.write_json(run, "status.json", pipeline.initial_status())
            scripted = ScriptedLLM("2d")
            with scripted_model(scripted, vision=True), no_browser():
                pipeline.run_pipeline(run)
            self.assertIsNone(pipeline.read_json(run, "status.json")["error"], (run / "debug.log").read_text())
            self.assertEqual([name for name, _ in scripted.calls][:5], ["Transcriber"] * 5)
            pages = pipeline.read_json(run, "pages.json")
            self.assertIn("Leaky integration sets the firing rhythm", pages[0])
            self.assertIn("the threshold of -50 mV", pages[1])
            self.assertIn("integrate-and-fire", scripted.calls[5][1])
            with scripted_model(ScriptedLLM("2d"), vision=False):
                shutil.rmtree(run / "checkpoints")  # a fresh attempt, not a resumed one
                pipeline.write_json(run, "status.json", pipeline.initial_status())
                pipeline.run_pipeline(run)
            self.assertIn("scanned", pipeline.read_json(run, "status.json")["error"])

    def test_a_port_that_never_matches_stops_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "paper.pdf").write_bytes(paper_pdf())
            pipeline.write_json(run, "status.json", pipeline.initial_status())
            scripted = ScriptedLLM("2d")
            scripted.port_fixes = False
            with scripted_model(scripted):
                pipeline.run_pipeline(run)
            status = pipeline.read_json(run, "status.json")
            self.assertEqual(status["error"], pipeline.PUBLIC_ERROR)
            self.assertEqual([name for name, _ in scripted.calls].count("Porter"), pipeline.FIX_ATTEMPTS + 1)
            self.assertNotIn("Designer", [name for name, _ in scripted.calls])
            self.assertIn("spikes", (run / "debug.log").read_text())


if __name__ == "__main__":
    unittest.main()
