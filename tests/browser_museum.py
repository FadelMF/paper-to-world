"""Exercise the detailed 3D anatomy independently of the scientific clock."""

import importlib.util
import os
import sys
from pathlib import Path

from harness import page_errors
from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

ART = Path(__file__).resolve().parents[1] / "artifacts"
with sync_playwright() as p:
    for mode, route, module in [("3d", "/demo/3d", "demo3d")]:
        if len(sys.argv) > 1 and sys.argv[1] != mode:
            continue
        flags = ["--no-sandbox", "--disable-gpu"] if mode == "2d" else ["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        browser = p.chromium.launch(channel="chromium", args=flags)
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        errors = page_errors(page)
        page.goto(APP_URL + route, wait_until="networkidle")
        page.evaluate(f"async()=>window.museumWorld=await import('/assets/{module}/world.js')")
        state = lambda: page.evaluate(f"async()=>(await import('/assets/{module}/world.js')).getState()")
        page.evaluate(f"async()=>(await import('/assets/{module}/world.js')).pause()")
        before = state()["time"]
        spec = importlib.util.spec_from_file_location("reference", ART.parent / "static" / module / "model.py")
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        cases = [(0, 20, 1000), (1, 20, 1000), (2, 20, 1000), (3, 20, 1000), (5, 5, 1000), (2.7, 50, 700), (1.5, 20, 2000)]
        measured = page.evaluate("(cases)=>cases.map(args=>window.museumWorld.measure(...args))", cases)
        for args, actual in zip(cases, measured, strict=False):
            for key, value in reference.simulate(*args).items():
                assert abs(actual[key] - value) < 1e-9
        assembled = state()["assemblyPositions"]
        page.get_by_role("button", name="Explode", exact=True).click()
        page.wait_for_function("()=>window.museumWorld.getState().assembly>.98", timeout=20000)
        assert state()["time"] == before
        assert state()["assemblyPositions"] != assembled
        page.screenshot(path=str(ART / f"museum-{mode}-exploded.png"), timeout=15000)
        page.get_by_role("button", name="Assemble", exact=True).click()
        page.wait_for_function("()=>window.museumWorld.getState().assembly===0", timeout=20000)
        assert state()["time"] == before
        assert state()["assemblyPositions"] == assembled, (assembled, state()["assemblyPositions"], state()["assembly"])
        page.evaluate(f"async()=>{{const m=await import('/assets/{module}/world.js');m.setAssembly(.5);}}")
        page.wait_for_function("()=>window.museumWorld.getState().assembly>0")
        page.get_by_role("button", name="Assemble", exact=True).click()
        page.wait_for_function("()=>window.museumWorld.getState().assembly===0")
        assert state()["assemblyPositions"] == assembled and state()["time"] == before
        page.screenshot(path=str(ART / f"museum-{mode}-assembled.png"), timeout=15000)
        print(mode, "assembly checked", flush=True)
        page.get_by_role("button", name="Anatomy", exact=True).click()
        select = page.locator(".anatomy-inspector select")

        def pick(part):
            options = select.locator("option").evaluate_all("els=>els.map(el=>el.value)")
            page.locator(".anatomy-inspector .app-select-trigger").click()
            page.locator("#" + select.get_attribute("id") + "-options [role=option]").nth(options.index(part)).click()

        inventory = select.locator("option").evaluate_all("(options)=>options.map(o=>o.value)")
        assert len(inventory) == 18 and set(inventory) == set(state()["anatomyInventory"])
        for part in inventory:
            pick(part)
            assert state()["anatomySelected"] == part
            assert page.locator(".anatomy-description").inner_text()
            if mode == "3d" and part in ["smoothER", "lysosomes", "cytoskeleton", "terminals"]:
                page.get_by_role("button", name="Focus component", exact=True).click()
                page.wait_for_function(
                    "()=>{const s=window.museumWorld.getState();return !s.cameraTransitioning&&Math.hypot(...s.camera.map((v,i)=>v-s.target[i]))<3.2}"
                )
                if part == "terminals":
                    assert state()["target"][0] > 5
        pick("nucleus")
        page.get_by_role("button", name="Focus component", exact=True).click()
        assert page.locator(".anatomy-inspector").is_visible()
        if mode == "3d":
            page.wait_for_function(
                "()=>{const s=window.museumWorld.getState();return !s.cameraTransitioning&&Math.hypot(...s.camera.map((v,i)=>v-s.target[i]))<2.05}"
            )
        else:
            assert state()["zoom"] == 2.8
        page.screenshot(path=str(ART / f"museum-{mode}-nucleus.png"), timeout=15000)
        canvas = page.locator("#world>canvas")
        rect = canvas.bounding_box()
        canvas.click(position={"x": rect["width"] / 2, "y": rect["height"] / 2})
        assert page.locator(".anatomy-inspector").is_visible()
        assert select.input_value() == "nucleus"
        page.get_by_role("button", name="Close", exact=True).click()
        print(mode, "18 structures and detail focus checked", flush=True)
        page.get_by_role("button", name="Anatomy", exact=True).click()
        page.get_by_role("button", name="Reset view", exact=True).click()
        page.get_by_role("button", name="Close", exact=True).click()
        for width in [390, 768]:
            page.set_viewport_size({"width": width, "height": 844})
            page.get_by_role("button", name="Explode", exact=True).click()
            page.wait_for_timeout(1200)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            for dark in [True, False]:
                page.locator("[data-theme-toggle]").click()
                assert page.locator("html").get_attribute("data-theme") == ("dark" if dark else "light")
                page.get_by_role("button", name="Anatomy", exact=True).click()
                pick("mitochondria")
                rect = page.locator(".anatomy-inspector").bounding_box()
                assert rect["x"] >= 0 and rect["x"] + rect["width"] <= width
                assert rect["y"] >= 0 and rect["y"] + rect["height"] <= 844
                page.get_by_role("button", name="Close", exact=True).click()
                page.screenshot(path=str(ART / f"museum-{mode}-{width}-{dark}.png"), timeout=15000)
            print(mode, width, "both themes checked", flush=True)
        page.emulate_media(reduced_motion="reduce")
        page.reload(wait_until="networkidle")
        page.evaluate(f"async()=>window.museumWorld=await import('/assets/{module}/world.js')")
        page.get_by_role("button", name="Explode", exact=True).click()
        page.wait_for_function("()=>window.museumWorld.getState().assembly===1")
        assert not errors, errors
        print(mode, "assembly, paused clock, reduced motion and rendering PASS", flush=True)
        browser.close()
