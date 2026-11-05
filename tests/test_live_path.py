"""Live path: a text PDF with real-world defects through ETL, model replies, and the served 2D/3D world."""

import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from paper_fixture import ANALYSIS, HEADER, INTERNAL_WORDS, TITLE, ScriptedLLM, blank_pdf, no_browser, paper_pdf, plan, scripted_model

from app import agents, llm, main, pipeline, sandbox
from app.errors import PublicError
from app.pdf import clean_page, paper_chunks, read_pdf, strip_running_lines


def scripted_run(tmp, scripted):
    """Build the fixture paper in tmp with scripted model replies; return the run folder."""
    run = Path(tmp)
    (run / "paper.pdf").write_bytes(paper_pdf())
    pipeline.write_json(run, "status.json", pipeline.initial_status())
    with scripted_model(scripted), no_browser():
        pipeline.run_pipeline(run)
    return run


def replies(scripted, agent):
    return [user for name, user in scripted.calls if name == agent]


ROOT = Path(__file__).resolve().parents[1]


class ExtractTests(unittest.TestCase):
    def test_clean_page_repairs_measured_text_defects(self):
        # Strings as pypdf returns them from arXiv 2006.11239 and 1706.03762.
        self.assertEqual(clean_page("Efﬁcient training"), "Efficient training")
        self.assertEqual(clean_page("ﬂow ﬀ ﬃ ﬄ"), "flow ff ffi ffl")
        self.assertEqual(clean_page("x\x00y"), "xy")
        self.assertEqual(clean_page("the mem-\nbrane voltage"), "the membrane\nvoltage")
        self.assertEqual(clean_page("N = 6 identical\nlayers"), "N = 6 identical\nlayers")
        self.assertEqual(clean_page("pre-\nTraining"), "pre-\nTraining")
        self.assertEqual(clean_page("a   b \t c  \n\n\n\nd"), "a b c\n\nd")
        self.assertEqual(clean_page("∑ t>1 DKL(q(xt−1|xt))"), "∑ t>1 DKL(q(xt−1|xt))")

    def test_running_headers_and_page_numbers_are_removed(self):
        pages = [f"{HEADER}\nBody {i} text\n{i}" for i in range(1, 6)]
        self.assertEqual(strip_running_lines(pages), [f"Body {i} text" for i in range(1, 6)])
        short = ["Title\nIntro", "Methods\nResult"]
        self.assertEqual(strip_running_lines(short), short)

    def test_read_pdf_returns_clean_pages_from_a_real_text_pdf(self):
        pages = read_pdf(paper_pdf())
        self.assertEqual(len(pages), 5)
        text = "\n".join(pages)
        self.assertNotIn(HEADER, text)
        for defect in ["ﬁ", "\x00", "mem-\n"]:
            self.assertNotIn(defect, text)
        self.assertIn("integrate-and-fire neuron", text)
        self.assertIn("The membrane\ntime constant", text)
        self.assertTrue(pages[0].startswith(TITLE))

    def test_unreadable_files_raise_public_messages(self):
        cases = [(b"<html>not a pdf</html>", "couldn"), (b"%PDF-1.7\ngarbage", "couldn"), (paper_pdf(encrypt="secret"), "password"), (blank_pdf(), "scanned")]
        for data, words in cases:
            with self.subTest(words=words), self.assertRaises(PublicError) as caught:
                read_pdf(data)
            self.assertIn(words, str(caught.exception))
            self.assertIsNone(INTERNAL_WORDS.search(str(caught.exception)))

    def test_model_text_drops_references_keeps_appendix_and_splits_long_papers_at_pages(self):
        pages = read_pdf(paper_pdf())
        [text] = paper_chunks(pages, 100_000)
        self.assertNotIn("Lapicque", text)
        self.assertIn("firing-rate formula", text)
        self.assertIn("[page 5]", text)
        budget = len(paper_chunks(pages[:2], 100_000)[0]) + 5
        parts = paper_chunks(pages, budget)
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].startswith("[part 1 of 2: pages 1-2]\n[page 1]"))
        self.assertTrue(parts[1].startswith("[part 2 of 2: pages 3-5]\n[page 3]"))
        self.assertIn("firing-rate formula", parts[1])
        self.assertTrue(paper_chunks(["x" * 500], 100)[0].startswith("[page 1]\nxxx"))

    def test_references_early_in_a_long_appendix_paper_are_dropped(self):
        # arXiv 2006.11239: References on page 9 of 25, followed by "A Extended derivations".
        pages = [
            "Intro",
            "Method\nReferences\n[1] Alain et al. GSNs.",
            "[2] Bengio. 2013.",
            "A Extended derivations\nL = E[...]",
            "B Experimental details",
            "More",
        ]
        [text] = paper_chunks(pages, 100_000)
        self.assertNotIn("Alain", text)
        self.assertNotIn("[page 3]", text)
        self.assertIn("Extended derivations", text)
        self.assertIn("References", paper_chunks(["References\n1. Overview", "Body"], 100_000)[0])


class LongPaperTests(unittest.TestCase):
    def test_part_extractions_merge_without_duplicates_and_with_fresh_ids(self):
        first = {"title": "T", "concepts": [{"name": "Leak"}], "equations": [{"id": "eq1", "latex": "a=b"}], "claims": [{"id": "c1", "statement": "X rises"}]}
        second = {
            "title": "",
            "authors": "A",
            "concepts": [{"name": "leak"}, {"name": "Spike"}],
            "equations": [{"id": "eq1", "latex": "a = b"}, {"id": "eq1", "latex": "c=d"}],
            "claims": [{"id": "c1", "statement": "Y falls"}],
        }
        merged = agents.merge_analyses([first, second])
        self.assertEqual((merged["title"], merged["authors"]), ("T", "A"))
        self.assertEqual([c["name"] for c in merged["concepts"]], ["Leak", "Spike"])
        self.assertEqual([(e["id"], e["latex"]) for e in merged["equations"]], [("eq1", "a=b"), ("eq2", "c=d")])
        self.assertEqual([c["id"] for c in merged["claims"]], ["c1", "c2"])
        self.assertIs(agents.merge_analyses([first]), first)
        evidence = agents.merge_evidence([{"subject": "S", "entities": [{"id": "soma"}]}, {"entities": [{"id": "soma", "x": 1}, {"id": "axon"}]}])
        self.assertEqual(evidence, {"subject": "S", "entities": [{"id": "soma"}, {"id": "axon"}]})

    def test_a_long_paper_is_read_in_parts_by_every_reading_agent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pipeline, "MAX_CHARS", 700):
            scripted = ScriptedLLM("2d")
            run = scripted_run(tmp, scripted)
            self.assertIsNone(pipeline.read_json(run, "status.json")["error"], (run / "debug.log").read_text())
            analyst = [user for name, user in scripted.calls if name == "Analyst"]
            self.assertGreaterEqual(len(replies(scripted, "Observer")), 2)
            self.assertTrue(any("[part 2 of" in user for user in analyst))
            self.assertTrue(any("firing-rate formula" in user for user in analyst))


class ResumeTests(unittest.TestCase):
    def test_retry_resumes_after_the_last_finished_stage(self):
        broken = "```js\n" + (ROOT / "static" / "demo" / "world.js").read_text().replace("export function step(", "function step(") + "\n```"
        first = ScriptedLLM("2d", Builder=[broken] * (pipeline.FIX_ATTEMPTS + 1))
        second = ScriptedLLM("2d")
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(main, "RUNS", Path(tmp)),
            patch.object(main, "configured", return_value=True),
            patch.object(main, "launch_run", side_effect=pipeline.run_pipeline),
            no_browser(),
            TestClient(main.app) as client,
        ):
            with scripted_model(first):
                failed = client.post("/api/runs", files={"file": ("paper.pdf", paper_pdf(), "application/pdf")}).json()["id"]
            self.assertIsNotNone(client.get(f"/api/runs/{failed}").json()["status"]["error"])
            with scripted_model(second):
                resumed = client.post(f"/api/runs/{failed}/retry").json()["id"]
            status = client.get(f"/api/runs/{resumed}").json()["status"]
            self.assertIsNone(status["error"], (Path(tmp) / resumed / "debug.log").read_text())
            self.assertEqual([name for name, _ in second.calls], ["Builder", "Builder"])
            self.assertIn("Resumed lessons from an earlier attempt", (Path(tmp) / resumed / "debug.log").read_text())
            for name in ["analysis.json", "evidence.json", "scene.json", "model.js", "model.py", "figure-1.png", "world.js"]:
                self.assertTrue((Path(tmp) / resumed / name).is_file(), name)
            fresh = ScriptedLLM("2d")
            with scripted_model(fresh):
                client.post(f"/api/runs/{failed}/retry?fresh=true")
            self.assertEqual(fresh.calls[0][0], "Analyst")


class TutorTests(unittest.TestCase):
    def test_pages_are_ranked_by_rare_question_words(self):
        pages = ["the neuron and the neuron again", "refractory period after a spike", "the the the the neuron", "unrelated text about methods"]
        self.assertEqual(agents.top_pages(pages, "What is the refractory period?", k=1), [1])
        self.assertEqual(agents.top_pages(pages, "neuron", k=2), [0, 2])

    def test_the_tutor_also_knows_what_the_figures_show(self):
        evidence = {"figures": [{"id": "fig1", "page": 2, "caption": "Figure 1: A neuron", "reading": {"depicts": "a round soma"}}]}
        with patch.object(agents, "chat", return_value="answer") as chat:
            agents.ask(["page one"], ANALYSIS, plan("2d"), {}, "What does figure 1 show?", evidence)
        self.assertIn("a round soma", chat.call_args.args[1])
        self.assertIn("[Figure 2, p.5]", chat.call_args.args[0])


class ModelReplyTests(unittest.TestCase):
    def test_parse_json_accepts_fenced_and_wrapped_objects(self):
        self.assertEqual(llm.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(llm.parse_json('Sure:\n{"a": {"b": 2}}\nLet me know {more}.'), {"a": {"b": 2}})
        self.assertEqual(llm.parse_json('{"a": "}"}'), {"a": "}"})
        for bad in ["no object here", "{'a': 1}", "[1, 2]"]:
            with self.assertRaises(ValueError):
                llm.parse_json(bad)

    def test_chat_json_retries_once_with_the_parse_error(self):
        with patch.object(llm, "chat", side_effect=["{oops", '{"ok": true}']) as chat:
            self.assertEqual(llm.chat_json("system", "user"), {"ok": True})
        self.assertEqual(chat.call_count, 2)
        self.assertIn("not valid JSON", chat.call_args.args[1])
        with patch.object(llm, "chat", side_effect=["{oops", "still no"]), self.assertRaises(ValueError):
            llm.chat_json("system", "user")

    def test_extract_block_accepts_common_fence_names(self):
        self.assertEqual(llm.extract_block("```js\nexport const a = 1;\n```", "javascript"), "export const a = 1;\n")
        self.assertEqual(llm.extract_block("```JavaScript\nx\n```", "javascript"), "x\n")
        self.assertEqual(llm.extract_block("```py\nprint(1)\n```", "python"), "print(1)\n")
        self.assertEqual(llm.extract_block("```JSON\n[]\n```", "json"), "[]\n")
        with self.assertRaises(ValueError):
            llm.extract_block("no code", "python")

    def test_chat_rejects_empty_and_cut_off_replies(self):
        def client(content, reason):
            choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=reason)
            create = lambda **_kwargs: SimpleNamespace(choices=[choice])
            return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        env = {"LLM_BASE_URL": "http://x", "LLM_API_KEY": "k", "LLM_MODEL": "m", "LLM_API": "chat_completions"}
        with patch.dict(os.environ, env):
            with patch.object(llm, "OpenAI", return_value=nullcontext(client("hello", "stop"))):
                self.assertEqual(llm.chat("s", "u"), "hello")
            with patch.object(llm, "OpenAI", return_value=nullcontext(client(None, "stop"))), self.assertRaises(RuntimeError):
                llm.chat("s", "u")
            with patch.object(llm, "OpenAI", return_value=nullcontext(client('{"half', "length"))), self.assertRaisesRegex(RuntimeError, "LLM_MAX_TOKENS"):
                llm.chat("s", "u")


class StageContractTests(unittest.TestCase):
    def test_analysis_is_normalized_and_must_contain_something_to_build(self):
        analysis = agents.validate_analysis(json.loads(json.dumps(ANALYSIS)))
        self.assertEqual([e["id"] for e in analysis["equations"]], ["eq1"])
        self.assertEqual(analysis["equations"][0]["page"], 2)
        sparse = agents.validate_analysis({"concepts": [{"name": "Idea"}, {"explanation": "nameless"}]})
        self.assertEqual(sparse["title"], "")
        self.assertEqual([c["name"] for c in sparse["concepts"]], ["Idea"])
        for key in ["equations", "claims", "mechanisms", "parameters"]:
            self.assertEqual(sparse[key], [])
        with self.assertRaises(ValueError):
            agents.validate_analysis({"title": "Empty", "concepts": [], "equations": []})

    def test_model_output_must_end_with_metrics_json(self):
        self.assertEqual(pipeline.parse_model_output('step 1\n{"metrics": {"spikes": 3}, "notes": ""}\n')["metrics"], {"spikes": 3})
        for bad in ["", "reference output", '{"notes": "no metrics"}']:
            with self.assertRaises(ValueError):
                pipeline.parse_model_output(bad)

    def test_unreadable_model_output_is_repaired_like_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripted = ScriptedLLM("2d", Modeler=['```python\nprint("done")\n```'])
            run = scripted_run(tmp, scripted)
            self.assertIsNone(pipeline.read_json(run, "status.json")["error"], (run / "debug.log").read_text())
            self.assertIn("metrics", replies(scripted, "Modeler")[1])
            self.assertIn('print("done")', replies(scripted, "Modeler")[1])
            self.assertIn("def run(", (run / "model.py").read_text())

    def test_validation_statuses_are_normalized(self):
        result = agents.normalize_validation({"results": [{"id": "v1", "status": "PASS"}, {"id": "v2", "status": "matches"}, {"id": "v3"}]})
        self.assertEqual([r["status"] for r in result["results"]], ["pass", "not_measured", "not_measured"])
        self.assertEqual(result["summary"], "")
        self.assertEqual(agents.normalize_validation({})["results"], [])

    def test_world_contract_failures_get_bounded_repairs(self):
        broken = "```js\n" + (ROOT / "static" / "demo" / "world.js").read_text().replace("export function step(", "function step(") + "\n```"
        for builder, expect_ready in [([], True), ([broken] * (pipeline.FIX_ATTEMPTS + 1), False)]:
            with self.subTest(expect_ready=expect_ready), tempfile.TemporaryDirectory() as tmp:
                scripted = ScriptedLLM("2d", Builder=builder)
                run = scripted_run(tmp, scripted)
                status = pipeline.read_json(run, "status.json")
                self.assertEqual(status["done"] and not status["error"], expect_ready)
                self.assertEqual(len(replies(scripted, "Builder")), 2 if expect_ready else pipeline.FIX_ATTEMPTS + 1)
                self.assertIn("Missing named export step", replies(scripted, "Builder")[-1])
                self.assertEqual((run / "world.js").exists(), expect_ready)

    def test_public_errors_reach_the_learner_and_others_stay_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "paper.pdf").write_bytes(blank_pdf())
            pipeline.write_json(run, "status.json", pipeline.initial_status())
            pipeline.run_pipeline(run)
            status = pipeline.read_json(run, "status.json")
            self.assertIn("scanned", status["error"])
            self.assertEqual(status["step"], 1)


class UploadTests(unittest.TestCase):
    def test_upload_rejects_non_pdf_and_oversized_files_before_starting(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(main, "RUNS", Path(tmp)),
            patch.object(main, "configured", return_value=True),
            patch.object(main, "launch_run") as launch,
            patch.object(main, "MAX_UPLOAD_BYTES", 1000),
        ):
            with TestClient(main.app) as client:
                html = client.post("/api/runs", files={"file": ("paper.pdf", b"<html></html>", "application/pdf")})
                self.assertEqual(html.status_code, 422)
                big = client.post("/api/runs", files={"file": ("paper.pdf", b"%PDF-1.7\n" + b"0" * 2000, "application/pdf")})
                self.assertEqual(big.status_code, 413)
                launch.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()


class ProcessGapTests(unittest.TestCase):
    def run_dir(self, tmp):
        run = Path(tmp)
        pipeline.write_json(run, "pages.json", ["Teaching content"])
        pipeline.write_json(run, "status.json", pipeline.initial_status())
        return run

    def test_compound_hyphens_seen_elsewhere_survive_line_breaks(self):
        self.assertEqual(clean_page("a position-\nwise layer", frozenset({"position-wise"})), "a position-wise\nlayer")
        self.assertEqual(clean_page("the mem-\nbrane", frozenset({"position-wise"})), "the membrane")
        pdf = paper_pdf([[b"A leaky integrate-and-fire model.", b"Every integrate-and-", b"fire neuron leaks."]])
        self.assertIn("integrate-and-fire\nneuron", "\n".join(read_pdf(pdf)))

    def test_unparsable_replies_are_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripted = ScriptedLLM("2d", Writer=['```json\n[{"id": broken\n```'], Builder=["Here is the module, no code block."])
            run = scripted_run(tmp, scripted)
            self.assertIsNone(pipeline.read_json(run, "status.json")["error"], (run / "debug.log").read_text())
            self.assertIn("failed this check", replies(scripted, "Writer")[1])
            self.assertIn("no ```javascript block", replies(scripted, "Builder")[1])

    def test_reference_timeout_is_repaired_like_a_crash(self):
        # 5 s leaves the working model room to import scipy in the sandbox on a busy machine.
        with tempfile.TemporaryDirectory() as tmp, patch.object(pipeline, "MODEL_TIMEOUT", 5):
            scripted = ScriptedLLM("2d", Modeler=["```python\nimport time\ntime.sleep(60)\n```"])
            run = scripted_run(tmp, scripted)
            self.assertIn("5 seconds", replies(scripted, "Modeler")[1])
            self.assertIn("metrics", (run / "model_output.txt").read_text())

    def test_tutor_failure_is_a_friendly_503(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main, "RUNS", Path(tmp)):
            run = Path(tmp) / "paper"
            run.mkdir()
            for name, data in [("source.json", {}), ("pages.json", ["p"]), ("analysis.json", ANALYSIS), ("plan.json", plan("2d")), ("validation.json", {})]:
                pipeline.write_json(run, name, data)
            pipeline.write_json(run, "status.json", {**pipeline.initial_status(), "done": True})
            with patch.object(agents, "ask", side_effect=RuntimeError("SECRET provider failure")), TestClient(main.app) as client:
                response = client.post("/api/runs/paper/ask", json={"question": "Why?"})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("SECRET", response.text)
            self.assertIn("SECRET", (run / "debug.log").read_text())

    def test_saved_worlds_list_when_and_whether_an_example(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main, "RUNS", Path(tmp)), TestClient(main.app) as client:
            for run_id, demo in [("20261030-091500-aaaa1111", True), ("20261030-101500-bbbb2222", False)]:
                run = Path(tmp) / run_id
                run.mkdir()
                pipeline.write_json(run, "source.json", {"demo": demo})
                pipeline.write_json(run, "status.json", pipeline.initial_status())
            listed = client.get("/api/runs").json()
            self.assertEqual([(r["created"], r["example"]) for r in listed], [("2026-10-30T10:15:00", False), ("2026-10-30T09:15:00", True)])

    def test_failed_arxiv_download_explains_itself(self):
        import urllib.error
        from email.message import Message

        from app import pdf

        failures = [
            (urllib.error.HTTPError("u", 404, "Not Found", Message(), None), "arXiv ID"),
            (urllib.error.HTTPError("u", 429, "Too Many Requests", Message(), None), "Try again later"),
            (urllib.error.URLError("offline"), "reach arXiv"),
        ]
        for failure, words in failures:
            with self.subTest(words=words), patch.object(pdf.urllib.request, "urlopen", side_effect=failure), self.assertRaises(PublicError) as caught:
                pdf.download_arxiv("9999.99999")
            self.assertIn(words, str(caught.exception))

    def test_reference_model_runs_without_secrets_and_with_a_memory_cap(self):
        probe = (
            "import json, os, resource\n"
            'print(json.dumps({"metrics": {"key": "LLM_API_KEY" in os.environ, "memory": resource.getrlimit(resource.RLIMIT_AS)[0]}}))\n'
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LLM_API_KEY": "secret"}):
            (Path(tmp) / "model.py").write_text(probe)
            code, out, err = pipeline.run_model(Path(tmp))
        self.assertEqual(code, 0, err)
        metrics = pipeline.parse_model_output(out)["metrics"]
        self.assertFalse(metrics["key"])
        self.assertEqual(metrics["memory"], sandbox.MEMORY_BYTES)
