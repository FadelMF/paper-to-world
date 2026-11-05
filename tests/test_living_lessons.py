import copy
import json
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_fixture import ScriptedLLM, no_browser, paper_pdf, scripted_model

from app import agents, pipeline
from app.lesson_contract import validate_lessons

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "static" / "demo"
IDS = [o["id"] for o in json.loads((DEMO / "scene.json").read_text())["objects"]]


class LivingLessonTests(unittest.TestCase):
    def setUp(self):
        self.lessons = json.loads((DEMO / "lessons.json").read_text())
        self.world = (DEMO / "world.js").read_text()

    def test_contract_rejects_unusable_lessons(self):
        validate_lessons(self.lessons, IDS, ["I", "tau"])
        for mutate in [
            lambda x: x[0]["predict"].update(answer_index=9),
            lambda x: x[0]["equation"]["symbols"][0].update(links_to="missing"),
            lambda x: x[0]["controls"][0].update(default=100),
            lambda x: x[0].update(intro=["Only one sentence."]),
            lambda x: x[0]["source"].update(kind="other"),
        ]:
            broken = copy.deepcopy(self.lessons)
            mutate(broken)
            with self.assertRaises(ValueError):
                validate_lessons(broken, IDS, ["I", "tau"])
        with self.assertRaises(ValueError):
            validate_lessons(self.lessons[:2], IDS, ["I", "tau"])

    def test_python_javascript_numerical_parity(self):
        simulate = runpy.run_path(str(DEMO / "model.py"))["simulate"]
        scenarios = [(0, 20, 1000), (1, 20, 1000), (2, 20, 1000), (3, 20, 1000), (5, 5, 1000), (2.7, 50, 700), (1.5, 20, 2000)]
        program = f"const m=await import('{(DEMO / 'model.js').as_uri()}');console.log(JSON.stringify({json.dumps(scenarios)}.map(s=>m.measure(...s))))"
        actuals = json.loads(subprocess.run(["node", "--input-type=module", "-e", program], capture_output=True, text=True, check=True).stdout)
        for scenario, actual in zip(scenarios, actuals, strict=False):
            for key, expected in simulate(*scenario).items():
                self.assertAlmostEqual(actual[key], expected, places=9, msg=f"{scenario} {key}")

    def test_source_has_real_cited_pages(self):
        from pypdf import PdfReader

        pages = PdfReader(DEMO / "paper.pdf").pages
        self.assertEqual(len(pages), 4)
        for lesson in self.lessons:
            self.assertIn(lesson["title"], pages[lesson["source"]["page"] - 1].extract_text())
        self.assertIn("63 spikes", pages[3].extract_text())

    def test_upload_to_new_lesson_routes_and_tutor(self):
        from fastapi.testclient import TestClient

        from app import main

        scripted = ScriptedLLM("2d")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(main, "RUNS", Path(directory)),
            patch.object(main, "configured", return_value=True),
            patch.object(main, "launch_run", side_effect=pipeline.run_pipeline),
            scripted_model(scripted),
            no_browser(),
            patch.object(agents, "ask", return_value="A grounded answer [p.2].") as tutor,
        ):
            with TestClient(main.app) as client:
                response = client.post("/api/runs", files={"file": ("paper.pdf", paper_pdf(), "application/pdf")})
                self.assertEqual(response.status_code, 200)
                run_id = response.json()["id"]
                status = client.get(f"/api/runs/{run_id}").json()
                self.assertTrue(status["has_world"])
                self.assertTrue(status["status"]["done"])
                self.assertTrue(client.get("/api/runs").json()[0]["ready"])
                self.assertEqual(client.get(f"/learn/{run_id}").content, client.get("/demo").content)
                library = client.get(f"/api/runs/{run_id}/lesson/specimen.js")
                self.assertEqual(library.status_code, 200)
                self.assertIn("export function specimenControls", library.text)
                self.assertEqual(client.get(f"/api/runs/{run_id}/files/lessons.json").json(), validate_lessons(self.lessons, IDS, ["I", "tau"]))
                self.assertEqual(client.get(f"/api/runs/{run_id}/sim").status_code, 404)
                answer = client.post(f"/api/runs/{run_id}/ask", json={"question": "Why?"})
                self.assertEqual(answer.json()["answer"], "A grounded answer [p.2].")
                self.assertEqual(tutor.call_args.args[-1], "Why?")


if __name__ == "__main__":
    unittest.main()
