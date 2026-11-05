"""Live path with nothing patched: a learner uploads a real text PDF on the homepage, the server's worker
process cleans it and calls an OpenAI-compatible endpoint over HTTP, and the browser opens the 2D or 3D world.

The endpoint is tests/fake_llm_server.py, which returns realistic raw replies (prose, ```js fences, one
invalid JSON reply, one contract-breaking world) so the retry and repair paths run. The 3D world renders
with actual WebGL (SwiftShader).
"""

import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests")]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE, MODEL_PORT = "http://127.0.0.1:8766", 8767

from harness import app_server, page_errors, serving
from paper_fixture import HEADER, TITLE, paper_pdf

with tempfile.TemporaryDirectory(prefix="paper-live-") as tmp:
    pdf = Path(tmp) / "leaky-neuron.pdf"
    pdf.write_bytes(paper_pdf())
    runs = Path(tmp) / "runs"
    runs.mkdir()
    env = {
        **os.environ,
        "PAPER_RUNS_DIR": str(runs),
        "LLM_BASE_URL": f"http://127.0.0.1:{MODEL_PORT}/v1",
        "LLM_API_KEY": "fake",
        "LLM_MODEL": "scripted",
        "LLM_API": "responses",
        "VISION_API": "responses",
        "VISION_MODEL": "scripted-vision",
        "PAPER_DAILY_GLOBAL_TOKENS": "100000000",
        "PAPER_DAILY_USER_TOKENS": "100000000",
        "PAPER_RUN_TOKEN_LIMIT": "50000000",
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
        for modality in ("2d", "3d"):
            with (ARTIFACTS / f"live-path-{modality}-server.log").open("w") as log:
                model_server = serving(
                    [sys.executable, str(ROOT / "tests" / "fake_llm_server.py"), str(MODEL_PORT), modality], f"http://127.0.0.1:{MODEL_PORT}/", env, log
                )
                with model_server, app_server(8766, env, log):
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.set_default_timeout(20000)
                    errors = page_errors(page, console=True)

                    page.goto(BASE + "/")
                    page.locator("#paper-tab").click()
                    expect(page.locator("#build-paper")).to_be_enabled()
                    page.locator("#pdf").set_input_files(str(pdf))
                    page.locator("#build-paper").click()
                    page.wait_for_url("**/build/*")
                    run = page.url.rsplit("/", 1)[-1]
                    expect(page.get_by_text(TITLE).first).to_be_visible(timeout=30000)
                    page.wait_for_url(f"**/learn/{run}", timeout=300000)

                    status = json.loads(urllib.request.urlopen(f"{BASE}/api/runs/{run}").read())
                    assert status["status"]["error"] is None, (runs / run / "debug.log").read_text()[-3000:]
                    assert status["status"]["discovered"]["modality"] == modality
                    assert status["status"]["discovered"]["checks"] == {"passed": 2, "total": 2}
                    pages = json.loads(urllib.request.urlopen(f"{BASE}/api/runs/{run}/files/pages.json").read())
                    assert len(pages) == 5 and not any(HEADER in text or "ﬁ" in text for text in pages)
                    debug = (runs / run / "debug.log").read_text()
                    for repaired in ["Browser model check 1 failed", "Scene check 1 failed", "World check 1 failed", "Reference execution: returncode=0"]:
                        assert repaired in debug, repaired
                    critique = json.loads((runs / run / "critique.json").read_text())
                    assert critique["round"] == 2 and critique["major"] == [], critique
                    evidence = json.loads(urllib.request.urlopen(f"{BASE}/api/runs/{run}/files/evidence.json").read())
                    assert evidence["figures"][0]["reading"]["elements"], "the figure was read over HTTP with images"
                    scene = json.loads(urllib.request.urlopen(f"{BASE}/api/runs/{run}/files/scene.json").read())
                    assert scene["modality"] == modality and any(o["basis"] == "hypothesis" for o in scene["objects"])

                    expect(page.locator("#loading")).to_be_hidden(timeout=45000)
                    expect(page.locator("#workspace")).to_be_visible()
                    expect(page.locator("#world-dimension")).to_have_text(f"{modality[0]}D world")
                    expect(page.locator("#shape-sources")).to_contain_text("Shapes from the paper")
                    expect(page.locator("#shape-sources")).to_contain_text("p.")
                    page.locator('#shape-sources [data-figure="fig1"]').click()
                    expect(page.locator("#figure-viewer")).to_be_visible()
                    page.wait_for_function("document.getElementById('figure-image').naturalWidth > 100")
                    expect(page.locator("#figure-caption")).to_contain_text("round soma")
                    page.screenshot(timeout=60000, animations='disabled', path=str(ARTIFACTS / f"live-path-{modality}-figure.png"))
                    page.locator("#figure-close").click()
                    expect(page.locator("#figure-viewer")).to_be_hidden()
                    page.frame_locator('.isolated-world').locator('canvas').first.wait_for(timeout=45000)
                    inner = next(f for f in page.frames if f != page.main_frame)
                    state = lambda: inner.evaluate("async()=>(await import('/assets/lesson/frame.js')).getState()")
                    if modality == "3d":
                        assert "WebGL" in state()["webglVersion"] and state()["frames"] > 0
                    else:
                        assert inner.locator("#world canvas").count() > 0
                    page.locator("#next").click()
                    # Drive the generated lesson's own control to its declared maximum.
                    top = page.locator("#control-I").get_attribute("max")
                    page.locator("#control-I").fill(top)
                    inner.wait_for_function("async value=>(await import('/assets/lesson/frame.js')).getState().I===value", arg=float(top))
                    started = state()["time"]
                    page.wait_for_timeout(600)
                    assert state()["time"] > started, "the generated world advances while playing"
                    assert page.locator("#source-link").get_attribute("href").endswith(f"{run}/files/paper.pdf")
                    page.screenshot(timeout=60000, animations='disabled', path=str(ARTIFACTS / f"live-path-{modality}.png"))

                    page.set_viewport_size({"width": 390, "height": 844})
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                    expect(page.locator("#loading")).to_be_hidden(timeout=45000)
                    expect(page.locator("#workspace")).to_be_visible()
                    page.screenshot(timeout=60000, animations='disabled', path=str(ARTIFACTS / f"live-path-{modality}-390.png"))

                    page.goto(BASE + "/worlds", wait_until="domcontentloaded", timeout=60000)
                    expect(page.get_by_text(TITLE).first).to_be_visible()
                    assert not errors, errors
                    page.close()
        browser.close()

print(
    "PASS: homepage upload of a PDF with a vector figure -> worker -> HTTP text and vision model endpoints (figure reading, render check, critic) -> working 2D and 3D worlds with the paper figure to compare; no browser errors."
)
