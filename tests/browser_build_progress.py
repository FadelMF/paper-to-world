"""Exercise real sample upload workers, polling, cancellation, retry and handoff locally."""

import itertools
import json
import os
import re
import tempfile
import time
from pathlib import Path

from harness import app_server, page_errors, start_prepared_example
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8765"
FORBIDDEN = re.compile(
    r"\b(agent|Analyst|Planner|Modeler|Validator|Builder|Tutor|LLM|AI model|prompt|token|JSON|pipeline|parse|decompose|deconstruct|reconstruct|compose|extract|reasoning|retry|crash|exception|stack trace)\b",
    re.I,
)

with tempfile.TemporaryDirectory(prefix="paper-progress-") as tmp:
    env = {**os.environ, "PAPER_RUNS_DIR": tmp}
    with (ARTIFACTS / "build-test-server.log").open("w") as log:
        with app_server(8765, env, log):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                errors = page_errors(page)
                polls = []
                page.on("request", lambda req: polls.append(time.monotonic()) if re.search(r"/api/runs/[^/]+$", req.url) and req.method == "GET" else None)
                page.goto(BASE + "/demo/upload")
                start_prepared_example(page, BASE, "2d")
                page.wait_for_url("**/build/*")
                run = page.url.split("/")[-1]
                expect(page.locator("#enter")).to_be_disabled()
                expect(page.locator("#sample-note")).to_be_visible()
                seen = set()
                ready_at = None
                deadline = time.monotonic() + 20
                while "/build/" in page.url and time.monotonic() < deadline:
                    snapshot = page.evaluate(
                        '({text:document.body.innerText,states:[...document.querySelectorAll("#steps>li")].map(el=>el.dataset.state),disabled:document.querySelector("#enter")?.disabled})'
                    )
                    state = snapshot["states"]
                    if len(state) != 5:
                        break
                    text = snapshot["text"]
                    assert not FORBIDDEN.search(text), text
                    active = state.index("active") + 1 if "active" in state else 5
                    seen.add(active)
                    if active == 3 and 3 not in getattr(page, "_captured", set()):
                        page.wait_for_timeout(500)
                        page.screenshot(path=str(ARTIFACTS / "upload-progress-desktop.png"), full_page=True)
                        page._captured = {3}
                    if active == 4:
                        expect(page.locator("#modality")).to_have_text("2D")
                        expect(page.locator("#checks")).to_have_text("4 of 4 results match the paper")
                        assert page.locator("#equations .katex").count() == 2
                        assert page.locator("#concepts .chip").count() == 4
                        assert page.locator("#activity li").count() <= 5
                    if active == 5:
                        assert snapshot["disabled"] is False
                        if ready_at is None:
                            ready_at = time.monotonic()
                        break
                    page.wait_for_timeout(180)
                page.wait_for_url("**/learn/*", timeout=5000)
                assert ready_at is not None and 1.6 < time.monotonic() - ready_at < 4.0
                expect(page.locator("#workspace")).to_be_visible()
                assert seen == {1, 2, 3, 4, 5}, seen
                assert page.locator("#demo-switch").count() == 0
                assert not any("three" in script for script in page.evaluate('performance.getEntriesByType("resource").map(r=>r.name)'))
                status = page.request.get(BASE + "/api/runs/" + run).json()
                assert status["status"]["done"] and status["status"]["error"] is None
                assert status["plan"]["modality"] == "2d"
                assert sum(1.3 < b - a < 1.7 for a, b in itertools.pairwise(polls)) >= 4, polls

                # Submit a prepared PDF to the replay endpoint, then cancel the real worker.
                page.goto(BASE + "/demo/upload")
                start_prepared_example(page, BASE, "2d")
                page.wait_for_url("**/build/*")
                canceled = page.url.split("/")[-1]
                page.locator("#cancel").click()
                page.wait_for_url(BASE + "/")
                canceled_status = page.request.get(BASE + "/api/runs/" + canceled).json()["status"]
                assert canceled_status["done"] and "canceled" in canceled_status["error"]
                before = (Path(tmp) / canceled / "status.json").read_text()
                page.wait_for_timeout(2700)
                assert before == (Path(tmp) / canceled / "status.json").read_text()

                # Resume the stopped screen and create a new run from the same PDF.
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(BASE + "/build/" + canceled)
                expect(page.locator("#retry")).to_be_visible()
                expect(page.locator("#enter")).to_be_hidden()
                expect(page.locator('#steps li[data-state="error"]')).to_have_count(1)
                page.screenshot(path=str(ARTIFACTS / "upload-progress-stopped.png"), full_page=True)
                page.locator("#retry").click()
                page.wait_for_url(lambda url: "/build/" in url and canceled not in url)
                retried = page.url.split("/")[-1]
                assert (Path(tmp) / retried / "paper.pdf").read_bytes() == (Path(tmp) / canceled / "paper.pdf").read_bytes()
                page.wait_for_function("document.querySelectorAll('#steps>li')[3].dataset.state==='active'", timeout=16000)
                expect(page.locator("#mobile-step")).to_have_text("Building & checking")
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.wait_for_timeout(500)
                page.screenshot(path=str(ARTIFACTS / "upload-progress-mobile.png"), full_page=True)
                page.wait_for_function("!document.getElementById('enter').disabled", timeout=7000)
                page.locator("#enter").click()
                page.wait_for_url("**/learn/*")
                expect(page.locator("#workspace")).to_be_visible()

                # The 3D example is independent, with no output dimension switch.
                page.goto(BASE + "/demo/3d")
                expect(page.locator("#workspace")).to_be_visible(timeout=20000)
                assert page.locator("#demo-switch").count() == 0

                # Stable status fixture checks smaller widths and reduced-motion styling.
                fixture = "responsive-fixture"
                folder = Path(tmp) / fixture
                folder.mkdir()
                pending = json.loads(json.dumps(status["status"]))
                pending.update(done=False, step=4, headline="Building and checking your world")
                pending["steps"][3]["state"] = "active"
                pending["steps"][4]["state"] = "pending"
                pending["waiting_hints"] = ["Looking closely at Resting potential", "Looking closely at Membrane leak"]
                (folder / "status.json").write_text(json.dumps(pending))
                (folder / "source.json").write_text('{"demo":true}')
                page.emulate_media(reduced_motion="reduce")
                page.goto(BASE + "/build/" + fixture)
                expect(page.locator("#modality")).to_have_text("2D")
                for width in [320, 375, 580, 768, 1440]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
                assert page.locator("#steps li[data-state=active] .circle").evaluate("el=>getComputedStyle(el,'::after').animationName") == "none"
                hint = page.locator("#waiting").inner_text()
                page.wait_for_timeout(4200)
                assert page.locator("#waiting").inner_text() != hint
                page.set_viewport_size({"width": 1440, "height": 1100})
                page.screenshot(path=str(ARTIFACTS / "upload-progress-checking.png"), full_page=True)
                assert not errors, errors
                browser.close()
                print(
                    json.dumps(
                        {
                            "real_upload": "pass",
                            "stages": sorted(seen),
                            "paper_details": "pass",
                            "single_renderer": "pass",
                            "automatic_and_manual_handoff": "pass",
                            "cancel_worker": "pass",
                            "same_pdf_retry": "pass",
                            "responsive": "320–1440px",
                            "reduced_motion": "pass",
                            "waiting_hints": "pass",
                            "errors": errors,
                        }
                    )
                )
