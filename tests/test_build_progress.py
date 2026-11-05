import copy
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from paper_fixture import INTERNAL_WORDS, no_browser

from app import agents, main, pipeline
from app.demo import SAMPLE, DemoProvider


@contextmanager
def offline_client():
    """A test client on an empty runs folder, with no model configured and no worker started."""
    with (
        tempfile.TemporaryDirectory() as tmp,
        patch.object(main, "RUNS", Path(tmp)),
        patch.object(main, "configured", return_value=False),
        patch.object(main, "launch_run"),
        TestClient(main.app) as client,
    ):
        yield client


class BuildProgressTests(unittest.TestCase):
    def setUp(self):
        browser = no_browser()
        browser.start()
        self.addCleanup(browser.stop)

    def test_one_modality_and_one_view(self):
        for mode in ("2d", "3d"):
            self.assertEqual(agents.validate_plan({"modality": mode, "views": [{"type": mode}]})["modality"], mode)
        for plan in [
            {"modality": "hybrid", "views": [{"type": "2d"}, {"type": "3d"}]},
            {"modality": "2d", "views": [{"type": "3d"}]},
            {"modality": "3d", "views": [{"type": "3d"}, {"type": "3d"}]},
            {"modality": "2d", "views": []},
        ]:
            with self.assertRaises(ValueError):
                agents.validate_plan(plan)

    def test_real_sample_stages_and_derived_details(self):
        snapshots = []
        original = pipeline.write_json

        def capture(directory, name, data):
            if name == "status.json":
                snapshots.append(copy.deepcopy(data))
            original(directory, name, data)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "paper.pdf").write_bytes((SAMPLE / "paper.pdf").read_bytes())
            original(directory, "status.json", pipeline.initial_status())
            with patch.object(pipeline, "write_json", side_effect=capture), patch.object(agents, "chat", side_effect=AssertionError("No narration calls")):
                pipeline.run_pipeline(directory, provider=DemoProvider())
            status = pipeline.read_json(directory, "status.json")
            self.assertIsNone(status["error"])
            self.assertTrue(status["done"])
            self.assertEqual(sorted({s["step"] for s in snapshots}), [1, 2, 3, 4, 5])
            self.assertTrue(all(s["state"] == "done" for s in status["steps"]))
            self.assertEqual(status["discovered"]["checks"], {"passed": 4, "total": 4})
            self.assertEqual(status["discovered"]["modality"], "2d")
            self.assertEqual(status["discovered"]["parts"], {"paper": 6, "illustrative": 1})
            for name in ["evidence.json", "scene.json", "model.js", "parity.json"]:
                self.assertTrue((directory / name).is_file(), name)
            self.assertEqual(len(status["discovered"]["concepts"]), 4)
            self.assertEqual(len(status["discovered"]["equations"]), 2)
            self.assertTrue(any("Opened 4 pages" in str(s["activity"]) for s in snapshots))
            for s in snapshots:
                self.assertNotIn("log", s)
                self.assertNotIn("agent", s)
                self.assertLessEqual(len(s["activity"]), 5)
                keys = [a["key"] for a in s["activity"]]
                self.assertEqual(len(keys), len(set(keys)))
                allowed = {
                    1: {"open"},
                    2: {"read", "concepts", "equations", "claims", "figures", "proofread"},
                    3: {"plan", "controls"},
                    4: {"model", "compare", "port", "scene", "lessons", "world", "review"},
                    5: {"ready"},
                }
                self.assertLessEqual(set(keys), allowed[s["step"]])
                visible = " ".join([s["headline"], s["subline"], *[a["text"] for a in s["activity"]], *s["waiting_hints"]])
                self.assertIsNone(INTERNAL_WORDS.search(visible), visible)
                if s["step"] < 3:
                    self.assertIsNone(s["discovered"]["modality"])
                if s["step"] < 4:
                    self.assertIsNone(s["discovered"]["checks"])
            self.assertIn("Reference execution", (directory / "debug.log").read_text())
            self.assertFalse((directory / "status.json.tmp").exists())
            for key, placeholder, result in [
                ("compare", "Comparing the results with the paper", "Comparing with the paper: 4 of 4 results match"),
                ("lessons", "Shaping your lessons", "Shaping 4 lessons for you"),
                ("port", "Making the simulation run in your browser", "Your browser simulation matches the reference in all 7 checks"),
                ("scene", "Sketching the parts you’ll explore", "Sketching 7 parts: 6 drawn from the paper, 1 illustrative"),
            ]:
                messages = [a for s in snapshots for a in s["activity"] if a["key"] == key]
                self.assertTrue(any(a["text"] == placeholder and not a["done"] for a in messages))
                self.assertTrue(any(a["text"] == result and a["done"] for a in messages))
                for s in snapshots:
                    texts = [a["text"] for a in s["activity"]]
                    if result in texts:
                        self.assertNotIn(placeholder, texts)

    def test_errors_are_private_and_stay_on_current_step(self):
        for stage, method in [
            (2, "analyze"),
            (2, "observe"),
            (3, "plan"),
            (4, "build_model"),
            (4, "validate"),
            (4, "port_model"),
            (4, "design_scene"),
            (4, "write_lessons"),
            (4, "build_world"),
        ]:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "paper.pdf").write_bytes((SAMPLE / "paper.pdf").read_bytes())
                pipeline.write_json(directory, "status.json", pipeline.initial_status())
                provider = DemoProvider()
                with patch.object(provider, method, side_effect=RuntimeError("SECRET prompt stack trace")):
                    pipeline.run_pipeline(directory, provider)
                s = pipeline.read_json(directory, "status.json")
                self.assertEqual(s["step"], stage)
                self.assertEqual(s["steps"][stage - 1]["state"], "error")
                self.assertEqual(s["error"], pipeline.PUBLIC_ERROR)
                self.assertNotIn("SECRET", json.dumps(s))
                self.assertIn("SECRET", (directory / "debug.log").read_text())

    def test_repair_reports_plain_message_and_stops_after_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "paper.pdf").write_bytes((SAMPLE / "paper.pdf").read_bytes())
            pipeline.write_json(directory, "status.json", pipeline.initial_status())
            provider = DemoProvider()
            with (
                patch.object(pipeline, "run_model", return_value=(1, "", "technical error")),
                patch.object(provider, "build_model", return_value="broken") as model,
                patch.object(provider, "port_model") as port,
            ):
                pipeline.run_pipeline(directory, provider)
            status = pipeline.read_json(directory, "status.json")
            self.assertEqual(model.call_count, pipeline.FIX_ATTEMPTS + 1)
            port.assert_not_called()
            self.assertEqual(model.call_args.args[-1], "technical error")
            self.assertIn("Fine-tuning the simulation", [a["text"] for a in status["activity"]])
            self.assertIsNotNone(status["error"])

    def test_scientific_source_terms_are_not_filtered_as_internal_jargon(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            pipeline.write_json(directory, "status.json", pipeline.initial_status())
            progress = pipeline.Progress(directory)
            progress.analysis(
                {"title": "Agent reasoning", "authors": "A. Planner", "concepts": [{"name": "tokens"}, {"name": "Voltage"}], "equations": [], "claims": []}
            )
            self.assertEqual(progress.status["discovered"]["title"], "Agent reasoning")
            self.assertEqual(progress.status["discovered"]["concepts"], ["tokens", "Voltage"])

    def test_upload_arxiv_error_retry_and_cancel_contract(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(main, "RUNS", Path(tmp)),
            patch.object(main, "configured", return_value=True),
            patch.object(main, "launch_run"),
        ):
            with TestClient(main.app) as client:
                response = client.post("/api/runs", files={"file": ("example.pdf", (SAMPLE / "paper.pdf").read_bytes(), "application/pdf")})
                run = response.json()["id"]
                directory = Path(tmp) / run
                self.assertEqual(client.get(f"/build/{run}").status_code, 200)
                self.assertEqual(client.get(f"/api/runs/{run}").json()["status"]["step"], 1)
                self.assertFalse((directory / "pages.json").exists())
                pipeline.Progress(directory).fail()
                retry = client.post(f"/api/runs/{run}/retry")
                self.assertEqual(retry.status_code, 200)
                new = retry.json()["id"]
                self.assertNotEqual(run, new)
                self.assertEqual((Path(tmp) / new / "paper.pdf").read_bytes(), (directory / "paper.pdf").read_bytes())
                self.assertEqual(client.post(f"/api/runs/{new}/retry").status_code, 409)
                canceled = client.post(f"/api/runs/{new}/cancel").json()["status"]
                self.assertIn("canceled", canceled["error"])
                self.assertTrue(canceled["done"])
                arxiv = client.post("/api/runs", data={"arxiv_id": "1706.03762"})
                arxiv_dir = Path(tmp) / arxiv.json()["id"]
                self.assertFalse((arxiv_dir / "paper.pdf").exists())
                with patch.object(pipeline, "download_arxiv", return_value=(SAMPLE / "paper.pdf").read_bytes()) as download:
                    pipeline.run_pipeline(arxiv_dir, provider=DemoProvider())
                download.assert_called_once_with("1706.03762")
                self.assertTrue(client.get(f"/api/runs/{arxiv.json()['id']}").json()["status"]["done"])
                self.assertEqual(client.post("/api/runs", data={"arxiv_id": "../../bad"}).status_code, 422)

    def test_worker_exit_reloads_final_status_before_marking_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main, "RUNS", Path(tmp)):
            directory = Path(tmp) / "finished"
            directory.mkdir()
            pipeline.write_json(directory, "status.json", pipeline.initial_status())
            pipeline.write_json(directory, "source.json", {})

            def finish_during_poll():
                pipeline.Progress(directory).ready("Example paper")
                return 0

            worker = Mock()
            worker.poll.side_effect = finish_during_poll
            with patch.dict(main.WORKERS, {"finished": worker}, clear=True):
                response = main.get_run("finished")
            self.assertTrue(response["status"]["done"])
            self.assertIsNone(response["status"]["error"])

    def test_runs_wait_in_line_for_a_free_worker(self):
        started = []

        class Worker:
            def __init__(self):
                self.code = None

            def poll(self):
                return self.code

        def start(run_dir):
            started.append(run_dir.name)
            main.WORKERS[run_dir.name] = Worker()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(main, "RUNS", Path(tmp)),
            patch.object(main, "MAX_WORKERS", 1),
            patch.object(main, "start_worker", side_effect=start),
            patch.dict(main.WORKERS, {}, clear=True),
            patch.object(main, "QUEUE", []),
        ):
            runs = [Path(tmp) / name for name in ("a", "b", "c")]
            for run in runs:
                run.mkdir()
                pipeline.write_json(run, "source.json", {})
                pipeline.write_json(run, "status.json", pipeline.initial_status())
                main.launch_run(run)
            self.assertEqual(started, ["a"])
            waiting = [pipeline.read_json(run, "status.json") for run in runs[1:]]
            self.assertEqual([(s["headline"], s["queued"]) for s in waiting], [("Waiting for your turn", 1), ("Waiting for your turn", 2)])
            self.assertIsNone(INTERNAL_WORDS.search(waiting[1]["subline"]))
            main.cancel_run("c")
            self.assertIn("canceled", pipeline.read_json(runs[2], "status.json")["error"])
            pipeline.Progress(runs[0]).ready("A")
            main.WORKERS["a"].code = 0
            main.get_run("b")
            self.assertEqual(started, ["a", "b"])
            self.assertNotIn("queued", pipeline.read_json(runs[1], "status.json"))
            self.assertEqual(main.QUEUE, [])

    def test_an_access_token_guards_every_page_when_set(self):
        with patch.object(main, "ACCESS_TOKEN", "s3cret"), TestClient(main.app) as client:
            self.assertEqual(client.get("/").status_code, 401)
            self.assertEqual(client.get("/api/runs").status_code, 401)
            self.assertEqual(client.get("/api/runs", headers={"Authorization": "Bearer s3cret"}).status_code, 200)
            entry = client.get("/demo?token=s3cret", follow_redirects=False)
            self.assertEqual((entry.status_code, entry.headers["location"]), (303, "http://testserver/demo"))
            self.assertEqual(client.get("/demo").status_code, 200)  # the cookie now carries the token
            self.assertEqual(client.get("/?token=wrong", follow_redirects=False).status_code, 401)

    def test_starting_runs_is_rate_limited_per_client(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main, "RUNS", Path(tmp)), patch.object(main, "RATE_LIMIT", 2), TestClient(main.app) as client:
            codes = [client.post("/api/runs", data={"arxiv_id": "1706.03762"}).status_code for _ in range(3)]
            self.assertEqual(codes[2], 429)
            self.assertNotEqual(codes[0], 429)
            self.assertEqual(client.get("/api/runs").status_code, 200)  # reading is not limited

    def test_old_finished_runs_are_pruned_and_busy_ones_kept(self):
        from datetime import datetime

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(main, "RUNS", Path(tmp)),
            patch.object(main, "QUEUE", []),
            patch.dict(main.WORKERS, {}, clear=True),
        ):
            for name, done in [("20260101-000000-old", True), ("20260101-000000-unfinished", False), ("20261029-000000-recent", True)]:
                run = Path(tmp) / name
                run.mkdir()
                status = pipeline.initial_status()
                status["done"] = done
                pipeline.write_json(run, "status.json", status)
            with patch.object(main, "RETENTION_DAYS", 0):
                self.assertEqual(main.prune_runs(datetime(2026, 10, 30)), [])
            with patch.object(main, "RETENTION_DAYS", 30):
                self.assertEqual(main.prune_runs(datetime(2026, 10, 30)), ["20260101-000000-old"])
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["20260101-000000-unfinished", "20261029-000000-recent"])

    def test_demo_accepts_only_sample_and_needs_no_provider(self):
        with offline_client() as client:
            good = client.post("/api/runs", data={"demo": "true"}, files={"file": ("sample.pdf", (SAMPLE / "paper.pdf").read_bytes(), "application/pdf")})
            self.assertEqual(good.status_code, 200)
            bad = client.post("/api/runs", data={"demo": "true"}, files={"file": ("other.pdf", b"%PDF-other", "application/pdf")})
            self.assertEqual(bad.status_code, 422)
            self.assertEqual(client.post("/api/runs", data={"arxiv_id": "1706.03762"}).status_code, 503)


class UnifiedEntryTests(unittest.TestCase):
    def test_entry_routes_and_honest_availability(self):
        with patch.object(main, "configured", return_value=False), TestClient(main.app) as client:
            self.assertEqual(client.get("/api/config").json()["generation_available"], False)
            self.assertIn("not connected", client.get("/api/config").json()["problem"])
            response = client.get("/demo/upload", follow_redirects=False)
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers["location"], "/?mode=examples&journey=1")
            for path in ["/", "/?example=3d", "/demo", "/demo/3d"]:
                self.assertEqual(client.get(path).status_code, 200, path)
            self.assertEqual(client.get("/preview/2d").status_code, 404)

    def test_each_prepared_pdf_builds_only_its_selected_example(self):
        from app.demo import SAMPLES

        with offline_client() as client:
            for mode, folder in SAMPLES.items():
                response = client.post(
                    "/api/runs",
                    data={"demo": "true", "example_id": mode},
                    files={"file": ("example.pdf", (folder / "paper.pdf").read_bytes(), "application/pdf")},
                )
                self.assertEqual(response.status_code, 200)
                directory = main.RUNS / response.json()["id"]
                self.assertEqual(pipeline.read_json(directory, "source.json")["example"], mode)
                pipeline.run_pipeline(directory, provider=DemoProvider(mode))
                status = pipeline.read_json(directory, "status.json")
                modality = pipeline.read_json(folder, "plan.json")["modality"]
                results = pipeline.read_json(folder, "validation.json")["results"]
                self.assertIsNone(status["error"], (directory / "debug.log").read_text())
                self.assertEqual(status["discovered"]["modality"], modality)
                self.assertEqual(status["discovered"]["checks"], {"passed": sum(r["status"] == "pass" for r in results), "total": len(results)})
                world = (directory / "world.js").read_text()
                self.assertIn(f"export const dimensionality = {modality[0]};", world)
                self.assertEqual(list(directory.glob("world*.js")), [directory / "world.js"])
                answer = client.post(f"/api/runs/{directory.name}/ask", json={"question": "What is this neuron?"}).json()["answer"]
                self.assertTrue(answer.startswith("Demo response"))


if __name__ == "__main__":
    unittest.main()
