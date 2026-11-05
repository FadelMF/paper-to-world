"""Run with system Python + Playwright against the local app."""

import json
import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chromium", headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    errors = page_errors(page)
    page.goto(APP_URL + "/demo", wait_until="networkidle")
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#lesson-title")).to_have_text("A neuron, at rest.")
    # One shared page container: the reading column starts at the logo, the world panel ends at the theme button.
    assert abs(page.locator("#reading").bounding_box()["x"] - page.locator(".brand").bounding_box()["x"]) <= 2
    visual = page.locator("#visual").bounding_box()
    theme = page.locator("[data-theme-toggle]").bounding_box()
    assert abs(visual["x"] + visual["width"] - theme["x"] - theme["width"]) <= 2
    page.wait_for_timeout(700)
    # Click the soma (its membrane) where the world itself reports it, not at coordinates from an earlier drawing.
    canvas_box = page.locator("#world canvas").bounding_box()
    membrane = page.evaluate("async()=>(await import('/assets/demo/world.js')).getState().partBounds.find(b=>b.id==='soma')")
    page.mouse.click(canvas_box["x"] + membrane["x"] + membrane["width"] * 0.2, canvas_box["y"] + membrane["y"] + membrane["height"] / 2)
    expect(page.locator('.term[data-link="membrane"]')).to_have_class("term linked-term is-linked")
    page.locator('[data-object="axon"]').click()
    expect(page.locator('.term[data-link="axon"]')).to_have_class("term linked-term is-linked")
    expect(page.locator("#reveal-trigger")).to_be_disabled()
    expect(page.locator("#why-answer")).to_be_hidden()
    page.locator('[data-option="1"]').click()
    page.locator("#reveal-trigger").click()
    expect(page.locator(".why-result")).to_have_text("Here’s what happens.")
    page.locator('[data-option="0"]').click()
    expect(page.locator("#why-answer")).to_be_hidden()
    page.locator("#reveal-trigger").click()
    expect(page.locator(".why-result")).to_have_text("You called it.")
    page.locator('.term[data-link="membrane"]').hover()
    expect(page.locator('[data-object="membrane"]')).to_have_class("object-tag selected")
    page.locator('[data-object="input"]').click()
    expect(page.locator('.term[data-link="input"]')).to_have_class("term linked-term is-linked")
    page.locator("#play-toggle").click()
    before = page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().time")
    page.wait_for_timeout(150)
    after = page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().time")
    assert before == after
    page.locator("#menu-toggle").click()
    page.locator("#step").click()
    stepped = page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().time")
    assert abs(stepped - before - 0.1) < 1e-8
    page.keyboard.press("Escape")
    page.locator("#next").click()
    expect(page.locator("#lesson-title")).to_have_text("An input becomes a voltage.")
    page.locator("#control-I").fill("1")
    page.locator("#control-tau").fill("5")
    assert page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().I") == 1
    expect(page.locator("#value-I")).to_have_text("1 nA")
    page.locator("#play-toggle").click()
    expect(page.locator("#challenge")).to_have_class("challenge achieved", timeout=10000)
    page.locator("#next").click()
    page.locator("#control-I").fill("2")
    expect(page.locator("#challenge")).to_have_class("challenge achieved", timeout=30000)
    # Check that a tagged object and its actual canvas body are both pickable.
    page.locator('[data-object="threshold"]').click()
    expect(page.locator('.term[data-link="threshold"]')).to_have_class("term linked-term is-linked")
    page.locator("[data-theme-toggle]").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.evaluate("document.getElementById('reading').scrollTop=0")
    page.wait_for_timeout(500)
    page.screenshot(path=str(ARTIFACTS / "lesson-dark.png"))
    page.locator("[data-theme-toggle]").click()
    page.locator("#explore-toggle").click()
    expect(page.locator("#reading")).to_be_hidden()
    expect(page.locator(".world-tools")).to_be_visible()
    assert (
        page.locator("#visual").bounding_box()["width"] == page.locator("#workspace").bounding_box()["width"] - 2 * page.locator(".brand").bounding_box()["x"]
    )
    page.get_by_role("button", name="Zoom in", exact=True).click()
    assert page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().zoom") > 1
    page.get_by_role("button", name="Pan right", exact=True).click()
    assert page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().panX") == 30
    canvas = page.locator("#world canvas").bounding_box()
    page.mouse.move(canvas["x"] + canvas["width"] * 0.6, canvas["y"] + canvas["height"] * 0.5)
    page.mouse.down()
    page.mouse.move(canvas["x"] + canvas["width"] * 0.6 + 50, canvas["y"] + canvas["height"] * 0.5 + 20, steps=5)
    page.mouse.up()
    assert page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().panX") > 30
    page.locator(".world-tools").get_by_role("button", name="Reset view", exact=True).click()
    assert page.evaluate("async()=> (await import('/assets/demo/world.js')).getState().zoom") == 1
    page.keyboard.press("Escape")
    expect(page.locator("#reading")).to_be_visible()
    # Verify narration dispatch/highlight sequencing without claiming audible OS output.
    page.evaluate("""()=>{window.__utterances=[];speechSynthesis.speak=u=>{window.__utterances.push(u);u.onstart();};speechSynthesis.cancel=()=>{};}""")
    page.locator("#narrate").click()
    expect(page.locator("#narrate")).to_have_attribute("aria-pressed", "true")
    expect(page.locator('[data-object="threshold"]')).to_have_class("object-tag selected")
    page.evaluate("window.__utterances[0].onend()")
    expect(page.locator('[data-object="spike"]')).to_have_class("object-tag selected")
    page.locator("#narrate").click()
    expect(page.locator("#narrate")).to_have_attribute("aria-pressed", "false")
    page.locator("#ask-open").click()
    expect(page.locator("#tutor")).to_be_visible()
    expect(page.locator("#question")).to_be_focused()
    page.locator("#question").fill("Why does it fire?")
    page.locator("#ask-form button").click()
    expect(page.locator("#messages")).to_contain_text("p.3, demo teaching notes")
    page.keyboard.press("Escape")
    expect(page.locator("#tutor")).to_be_hidden()
    page.locator("#next").click()
    expect(page.locator("#next")).to_be_disabled()
    page.locator("#control-I").fill("3")
    expect(page.locator("#challenge")).to_have_class("challenge achieved", timeout=20000)
    page.locator("#previous").click()
    expect(page.locator("#lesson-title")).to_have_text("A threshold changes everything.")
    page.locator("#menu-toggle").click()
    page.locator("#restart").click()
    expect(page.locator("#challenge")).not_to_have_class("challenge achieved")
    page.evaluate("document.getElementById('reading').scrollTop=0")
    page.wait_for_timeout(600)
    page.screenshot(path=str(ARTIFACTS / "lesson-desktop.png"))
    for width in [375, 768, 899, 900, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(150)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f"overflow at {width}"
        columns = page.evaluate(
            "(()=>{const style=getComputedStyle(document.getElementById('workspace'));return style.display==='flex'?1:style.gridTemplateColumns.split(' ').length})()"
        )
        assert columns == (1 if width <= 760 else 2), (width, columns)
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(ARTIFACTS / "lesson-mobile.png"), full_page=True)
    page.locator("#explore-toggle").click()
    page.screenshot(path=str(ARTIFACTS / "explore-mobile.png"))
    page.locator("#explore-toggle").click()
    page.goto(APP_URL + "/", wait_until="networkidle")
    expect(page.locator("#examples-panel")).to_be_visible()
    page.locator("#open-example").click()
    expect(page.locator("#workspace")).to_be_visible()
    assert not errors, errors
    print(
        json.dumps(
            {
                "prediction_gate": "pass",
                "bidirectional_links": "pass",
                "pause_step": "pass",
                "sliders": "pass",
                "challenges": "pass",
                "explore_pan_zoom": "pass",
                "narration_dispatch_and_sync": "pass (speech API stub)",
                "tutor_drawer": "pass",
                "themes": "pass",
                "responsive": [375, 768, 899, 900, 1440],
                "page_errors": errors,
            }
        )
    )
    browser.close()
