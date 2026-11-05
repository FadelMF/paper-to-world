"""Opt-in checks against real inputs. Skipped unless the inputs are provided.

REAL_PDF_DIR=/path/to/pdfs   every *.pdf there goes through extraction (no model calls)
LIVE_LLM=1 with LLM_* set     the fixture paper goes through every stage with the configured model;
                              with VISION_MODEL set too, its figure is read and the world is reviewed against it
"""

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from paper_fixture import paper_pdf

from app import pipeline
from app.lesson_contract import validate_lessons, validate_world
from app.llm import configured, vision_configured
from app.parity import check_port
from app.pdf import paper_chunks, read_pdf

REAL_PDF_DIR = os.getenv("REAL_PDF_DIR", "")


@unittest.skipUnless(REAL_PDF_DIR, "set REAL_PDF_DIR to a folder of real paper PDFs")
class RealPdfExtractionTests(unittest.TestCase):
    def test_each_real_pdf_yields_clean_model_text(self):
        files = sorted(Path(REAL_PDF_DIR).glob("*.pdf"))
        self.assertTrue(files, f"no PDFs in {REAL_PDF_DIR}")
        for file in files:
            with self.subTest(file=file.name):
                pages = read_pdf(file.read_bytes())
                text = "\n".join(paper_chunks(pages, pipeline.MAX_CHARS))
                self.assertGreater(len(text), 2000)
                self.assertFalse(re.search("[\x00ﬀ-ﬆ]", text))
                cited = len(re.findall(r"^\[\d+\] ", text, re.M))
                self.assertLess(cited, 5, "reference list reached the model text")


@unittest.skipUnless(os.getenv("LIVE_LLM") == "1" and configured(), "set LIVE_LLM=1 and LLM_BASE_URL, LLM_API_KEY, LLM_MODEL")
class LiveProviderTests(unittest.TestCase):
    def test_fixture_paper_builds_a_world_with_the_configured_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "paper.pdf").write_bytes(paper_pdf())
            pipeline.write_json(run, "status.json", pipeline.initial_status())
            pipeline.run_pipeline(run)
            status = pipeline.read_json(run, "status.json")
            self.assertIsNone(status["error"], (run / "debug.log").read_text()[-4000:])
            plan = pipeline.read_json(run, "plan.json")
            scene = pipeline.read_json(run, "scene.json")
            parity = pipeline.read_json(run, "parity.json")
            ids = [o["id"] for o in scene["objects"]]
            validate_lessons(pipeline.read_json(run, "lessons.json"), ids, list(parity["params_and_steps"][0][0]))
            validate_world((run / "world.js").read_text(), plan["modality"], ids)
            self.assertEqual(check_port(run, parity["params_and_steps"], parity["reference"]), parity["cases"])
            self.assertTrue(any(o["basis"] == "paper" for o in scene["objects"]), "no shape was drawn from the paper")
            self.assertIn("metrics", (run / "model_output.txt").read_text())
            self.assertEqual(pipeline.read_json(run, "render/report.json")["problems"], [])
            evidence = pipeline.read_json(run, "evidence.json")
            self.assertTrue((run / evidence["figures"][0]["image"]).is_file())
            if vision_configured():
                self.assertTrue(evidence["figures"][0]["reading"]["elements"], "the vision model did not read figure 1")
                print("\nReview:", json.dumps(pipeline.read_json(run, "critique.json"), indent=2))


if __name__ == "__main__":
    unittest.main()
