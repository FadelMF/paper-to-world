"""Exercise the real three.js/WebGL demo; no renderer mocks."""

import importlib.util
import json
import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location("lif_reference", ROOT / "static/demo3d/model.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
scenarios = [(0, 20, 1000), (1, 20, 1000), (2, 20, 1000), (3, 20, 1000), (5, 5, 1000), (2.7, 50, 700), (1.5, 20, 2000)]
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chromium", headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.set_default_timeout(20000)
    errors = page_errors(page, console=True)
    page.goto(APP_URL + "/demo/3d", wait_until="networkidle")
    expect(page.locator("#workspace")).to_be_visible()
    state = lambda: page.evaluate("async()=> (await import('/assets/demo3d/world.js')).getState()")
    s = state()
    assert s["dimensionality"] == 3 and "WebGL 2.0" in s["webglVersion"]
    assert s["meshCount"] > 40 and s["drawCalls"] > 30 and s["frames"] > 0
    actuals = page.evaluate("async cases=>{const m=await import('/assets/demo3d/world.js');return cases.map(s=>m.measure(...s));}", scenarios)
    for args, actual in zip(scenarios, actuals, strict=False):
        for key, expected in reference.simulate(*args).items():
            assert abs(actual[key] - expected) < 1e-9, (args, key, actual[key], expected)
    print("WebGL geometry and seven numerical parity cases: PASS", flush=True)
    expect(page.locator("#reveal-trigger")).to_be_disabled()
    page.locator('[data-option="0"]').click()
    page.locator("#reveal-trigger").click()
    expect(page.locator(".why-result")).to_have_text("You called it.")
    page.locator('.term[data-link="myelin"]').hover()
    expect(page.locator('[data-object="myelin"]')).to_have_class("object-tag selected")
    page.locator('[data-object="input"]').click()
    expect(page.locator('.term[data-link="input"]')).to_have_class("term linked-term is-linked")
    # Select the actual soma surface using the same perspective camera, not its tag. The point lies on the outer shell
    # (the cutaway opening faces the camera, so the soma's centre would hit the nucleus instead).
    point = page.evaluate(
        """async()=>{const THREE=await import('three');const m=await import('/assets/demo3d/world.js');const s=m.getState();const r=document.querySelector('[data-renderer]').getBoundingClientRect();const c=new THREE.PerspectiveCamera(38,r.width/r.height,.1,150);c.position.fromArray(s.camera);c.lookAt(new THREE.Vector3(...s.target));c.updateMatrixWorld();const v=new THREE.Vector3(-.49,.35,.37).project(c);return{x:r.x+(v.x*.5+.5)*r.width,y:r.y+(-v.y*.5+.5)*r.height}}"""
    )
    page.mouse.click(point["x"], point["y"])
    expect(page.locator('.term[data-link="membrane"]')).to_have_class("term linked-term is-linked")
    before = state()["camera"]
    page.get_by_role("button", name="Rotate right", exact=True).click()
    assert sum(abs(a - b) for a, b in zip(before, state()["camera"], strict=False)) > 0.5
    page.locator("#play-toggle").click()
    frozen = state()["time"]
    page.wait_for_timeout(250)
    assert state()["time"] == frozen
    page.locator("#menu-toggle").click()
    page.locator("#step").click()
    assert abs(state()["time"] - frozen - 0.1) < 1e-8
    page.keyboard.press("Escape")
    page.locator("#next").click()
    page.locator("#next").click()
    page.locator("#control-I").fill("2")
    assert state()["I"] == 2
    page.locator("#play-toggle").click()
    expect(page.locator("#challenge")).to_have_class("challenge achieved", timeout=90000)
    page.locator("#control-I").fill("3")
    for _ in range(300):
        if state()["spikes"] >= 3 and state()["pulsePositions"]:
            break
        page.wait_for_timeout(100)
    assert state()["spikes"] >= 3 and len(state()["pulsePositions"]) > 0
    a = state()["pulsePositions"]
    page.wait_for_timeout(500)
    assert state()["pulsePositions"] != a
    page.locator("#play-toggle").click()
    frozen = state()
    page.wait_for_timeout(250)
    assert state()["pulsePositions"] == frozen["pulsePositions"]
    page.evaluate("document.getElementById('reading').scrollTo({top:0,behavior:'instant'})")
    page.screenshot(path=str(ART / "neuron3d-desktop.png"))
    page.locator("[data-theme-toggle]").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.wait_for_timeout(200)
    page.screenshot(path=str(ART / "neuron3d-dark.png"))
    page.locator("[data-theme-toggle]").click()
    page.locator("#explore-toggle").click()
    expect(page.locator("#reading")).to_be_hidden()
    c1 = state()["camera"]
    box = page.locator("[data-renderer]").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.4, box["y"] + box["height"] * 0.5)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.55, steps=8)
    page.mouse.up()
    c2 = state()["camera"]
    assert sum(abs(a - b) for a, b in zip(c1, c2, strict=False)) > 1
    before = state()["camera"]
    page.get_by_role("button", name="Zoom in", exact=True).click()
    assert state()["camera"] != before
    target = state()["target"]
    page.mouse.move(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.5)
    page.mouse.down(button="right")
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.6, steps=5)
    page.mouse.up(button="right")
    assert state()["target"] != target
    page.get_by_role("button", name="Reset 3D view", exact=True).click()
    page.keyboard.press("Escape")
    page.locator("#ask-open").click()
    page.locator("#question").fill("Is this a spatial cable model?")
    page.locator("#ask-form button").click()
    expect(page.locator("#messages")).to_contain_text("one membrane voltage")
    page.keyboard.press("Escape")
    page.locator("#next").click()
    expect(page.locator("#lesson-title")).to_have_text("Follow the signal down the axon.")
    for width in [375, 768, 900, 1440]:
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(400)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#explore-toggle").click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(ART / "neuron3d-mobile.png"))
    # Labels must remain within the visible 3D container on mobile.
    bounds = page.locator("#world").bounding_box()
    for tag in page.locator(".object-tag:visible").all():
        rect = tag.bounding_box()
        assert rect["x"] >= bounds["x"] - 1 and rect["x"] + rect["width"] <= bounds["x"] + bounds["width"] + 1
        assert rect["y"] >= bounds["y"] - 1 and rect["y"] + rect["height"] <= bounds["y"] + bounds["height"] + 1
    page.locator("#explore-toggle").click()
    assert page.locator("#demo-switch").count() == 0
    page.goto(APP_URL + "/demo")
    expect(page.locator("#lesson-title")).to_have_text("A neuron, at rest.")
    assert page.locator("#demo-switch").count() == 0
    page.goto(APP_URL + "/demo/3d")
    expect(page.locator("[data-renderer]")).to_be_visible(timeout=20000)
    assert not errors, errors
    print(
        json.dumps(
            {
                "renderer": s["webglVersion"],
                "mesh_count": s["meshCount"],
                "numerical_parity_cases": len(scenarios),
                "prediction": "pass",
                "links_and_raycast": "pass",
                "pulse_animation": "pass",
                "clock_and_step": "pass",
                "orbit_zoom_pan": "pass",
                "dark_mode": "pass",
                "mobile_labels": "pass",
                "independent_examples": "pass",
                "errors": errors,
            }
        )
    )
    browser.close()
