"""Unified entry and shared design, using real sample workers and both renderers."""

import json
import os
import tempfile
from pathlib import Path

from harness import app_server, page_errors, start_prepared_example
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8766"
with tempfile.TemporaryDirectory(prefix="unified-worlds-") as tmp:
    with (ART / "unified-test-server.log").open("w") as log:
        with app_server(8766, {**os.environ, "PAPER_RUNS_DIR": tmp}, log):
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chromium", headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = page_errors(page)
                page.add_init_script(
                    "window.speechCalls=[];window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};Object.defineProperty(window,'speechSynthesis',{value:{cancel(){},speak(u){window.speechCalls.push(u.text);u.onstart?.();setTimeout(()=>u.onend?.(),50);}}});"
                )

                def shot(name):
                    page.evaluate("document.fonts.ready")
                    page.wait_for_timeout(550)
                    page.screenshot(path=str(ART / name), full_page=True)

                def theme():
                    values = page.evaluate(
                        "(()=>{const s=getComputedStyle(document.documentElement);return ['--paper','--accent','--font'].map(x=>s.getPropertyValue(x).trim())})()"
                    )
                    assert values[0] == "#ffffff" and values[1] == "#0866ff", values
                    assert page.locator(".app-header").count() == 1

                page.goto(BASE)
                expect(page.locator("#examples-panel")).to_be_visible()
                theme()
                expect(page.locator("#preview-play")).to_be_enabled(timeout=20000)
                page.locator("#preview-I").fill("0.8")
                expect(page.locator(".preview-slider output")).to_have_text("0.8 nA")
                shot("unified-home-desktop.png")
                page.locator('[data-example="3d"]').click()
                expect(page.locator('[data-renderer="three-webgl"]')).to_be_visible(timeout=20000)
                expect(page.locator("#open-example")).to_have_attribute("href", "/demo/3d")
                assert page.locator("#world>canvas").count() == 1
                page.locator("#preview-I").fill("0.6")
                expect(page.locator(".preview-slider output")).to_have_text("0.6 nA")
                page.locator("#open-example").click()
                page.wait_for_url("**/demo/3d")
                expect(page.locator("#workspace")).to_be_visible(timeout=20000)
                theme()
                expect(page.locator("#world-dimension")).to_have_text("3D world")
                assert page.locator("#demo-switch").count() == 0
                page.locator("#lesson-path button").nth(2).click()
                page.locator("#control-I").fill("3")
                page.wait_for_timeout(700)
                page.locator('[data-option="1"]').click()
                page.locator("#reveal-trigger").click()
                expect(page.locator("#why-answer")).to_be_visible()
                page.locator("#play-toggle").click()
                world = "/assets/demo3d/world.js"
                before = page.evaluate(f"async()=> (await import('{world}')).getState().time")
                page.wait_for_timeout(200)
                assert page.evaluate(f"async()=> (await import('{world}')).getState().time") == before
                page.locator("#menu-toggle").click()
                page.locator("#step").click()
                assert abs(page.evaluate(f"async()=> (await import('{world}')).getState().time") - before - 0.1) < 1e-7
                page.locator("#menu-toggle").click()
                page.locator('[data-link="membrane"]').first.hover()
                expect(page.locator('[data-object="membrane"]')).to_have_class("object-tag selected")
                page.locator("#narrate").click()
                page.wait_for_function("speechCalls.length >= 2", timeout=10000)
                page.locator("#reading").evaluate('(el)=>el.scrollTo({top:0,behavior:"instant"})')
                shot("unified-3d-desktop.png")
                page.locator("#explore-toggle").click()
                assert page.locator("#world").bounding_box()["width"] > 1100
                expect(page.locator("#explore-label")).to_have_text("Exit focus")
                page.locator('[aria-label="Zoom in"]').click()
                page.keyboard.press("Escape")
                expect(page.locator("#explore-label")).to_have_text("Focus view")
                page.locator("#ask-open").click()
                page.locator("#question").fill("What does the membrane do?")
                page.locator("#ask-form button").click()
                expect(page.locator(".message").last).to_contain_text("Demo response")
                page.locator("#ask-close").click()
                page.locator("[data-theme-toggle]").click()
                assert page.evaluate("document.documentElement.dataset.theme") == "dark"
                page.locator('.header-nav a[href="/"]').click()
                expect(page.locator("#resume")).to_be_visible()
                assert page.evaluate("document.documentElement.dataset.theme") == "dark"
                page.locator("[data-theme-toggle]").click()
                theme()
                page.locator('[data-example="2d"]').click()
                page.locator("#open-example").click()
                expect(page.locator("#workspace")).to_be_visible()
                theme()
                page.locator("#lesson-path button").nth(1).click()
                page.locator("#control-I").fill("1.2")
                expect(page.locator('[data-object="input"] .tag-value')).to_have_text("1.2 nA")
                page.locator("#reading").evaluate('(el)=>el.scrollTo({top:0,behavior:"instant"})')
                shot("unified-2d-desktop.png")
                page.locator(".brand").click()
                page.locator("#paper-tab").click()
                expect(page.locator("#paper-panel")).to_be_visible()
                expect(page.locator("#build-paper")).to_be_disabled()
                expect(page.locator("#availability")).to_contain_text("not connected")
                page.locator("#pdf").set_input_files(str(ROOT / "static/demo/paper.pdf"))
                expect(page.locator("#file-title")).to_have_text("paper.pdf")
                page.locator("#remove-file").click()
                expect(page.locator("#file-title")).to_have_text("Drop your paper here")
                page.locator("#arxiv-tab").click()
                page.locator("#arxiv").fill("https://arxiv.org/abs/1706.03762")
                shot("unified-live-desktop.png")
                # Exercise the live input transport without making a paid provider call.
                captured = []
                page.route("**/api/config", lambda route: route.fulfill(json={"generation_available": True}))
                page.reload()
                page.locator("#arxiv-tab").click()
                page.locator("#arxiv").fill("https://arxiv.org/abs/1706.03762")

                def live_submit(route):
                    if route.request.method == "POST":
                        captured.append(route.request.post_data)
                        route.fulfill(status=503, json={"detail": "This test did not call a provider."})
                    else:
                        route.continue_()

                page.route("**/api/runs", live_submit)
                page.locator("#build-paper").click()
                expect(page.locator("#status")).to_have_text("This test did not call a provider.")
                assert "1706.03762" in captured[0] and "https://arxiv.org" not in captured[0]
                page.unroute("**/api/runs")
                page.unroute("**/api/config")
                # Both prepared examples enter the same real progress route and each builds one world.
                for mode in ["2d", "3d"]:
                    page.goto(BASE)
                    page.locator(f'[data-example="{mode}"]').click()
                    start_prepared_example(page, BASE, mode)
                    page.wait_for_url("**/build/*")
                    theme()
                    run_id = page.url.split("/")[-1]
                    page.wait_for_function("document.querySelector('#modality').textContent.length>0", timeout=15000)
                    expect(page.locator("#modality")).to_have_text(mode.upper())
                    if mode == "2d":
                        shot("unified-progress-desktop.png")
                    page.wait_for_url("**/learn/*", timeout=20000)
                    expect(page.locator("#workspace")).to_be_visible(timeout=20000)
                    expect(page.locator("#world-dimension")).to_have_text(mode[0] + "D world")
                    theme()
                    data = page.request.get(BASE + "/api/runs/" + run_id).json()
                    assert data["plan"]["modality"] == mode and len(data["plan"]["views"]) == 1
                    page.locator('.header-nav a[href="/worlds"]').click()
                    expect(page.locator("#runs .run-item")).not_to_have_count(0)
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(BASE)
                expect(page.locator("#preview-play")).to_be_enabled(timeout=20000)
                shot("unified-home-mobile.png")
                for mode in ["2d", "3d"]:
                    page.locator(f'[data-example="{mode}"]').click()
                    expect(page.locator(f'[data-example="{mode}"]')).to_have_attribute("aria-checked", "true")
                    page.locator("#open-example").click()
                    expect(page.locator("#workspace")).to_be_visible(timeout=20000)
                    page.locator("#lesson-path button").nth(0).click()
                    theme()
                    assert page.locator("#visual").bounding_box()["y"] < page.locator("#reading").bounding_box()["y"]
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                    page.locator("#control-I").fill("0.5")
                    expect(page.locator('[data-object="input"] .tag-value')).to_have_text("0.5 nA")
                    page.locator("#reading").evaluate('(el)=>el.scrollTo({top:0,behavior:"instant"})')
                    shot(f"unified-{mode}-mobile.png")
                    page.locator("#explore-toggle").click()
                    assert page.locator("#world").bounding_box()["height"] > 400
                    page.locator("#explore-toggle").click()
                    page.locator(".brand").click()
                for width in [320, 375, 768, 1024, 1440]:
                    page.set_viewport_size({"width": width, "height": 1000})
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
                page.emulate_media(reduced_motion="reduce")
                assert page.locator(".example-option").first.evaluate("el=>getComputedStyle(el).transitionDuration") == "0s"
                assert not errors, errors
                browser.close()
                print(
                    json.dumps(
                        {
                            "entry_and_previews": "pass",
                            "both_sample_journeys": "pass",
                            "single_world_per_document": "pass",
                            "source_and_questions": "pass",
                            "lesson_controls": "pass",
                            "shared_theme": "pass",
                            "live_input_and_availability": "pass",
                            "mobile": "pass",
                            "errors": errors,
                        }
                    )
                )
