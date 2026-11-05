"""Real walkthroughs, seven-part picking, label geometry, and shared 2D/3D anatomy."""

import json
import os
import tempfile
from pathlib import Path

from harness import app_server, page_errors, themed_page
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "artifacts"
BASE = "http://127.0.0.1:8766"
results = []


def check(name, condition, detail=None):
    results.append({"check": name, "pass": bool(condition), "detail": detail})
    print(("PASS " if condition else "FAIL ") + name, flush=True)


def overlap(a, b):
    return (
        min(a["x"] + a["width"], b["x"] + b["width"]) > max(a["x"], b["x"]) + 0.5
        and min(a["y"] + a["height"], b["y"] + b["height"]) > max(a["y"], b["y"]) + 0.5
    )


def geometry(page, name):
    facts = page.evaluate("""async()=>{
      const world=document.querySelector('#world').getBoundingClientRect();
      const module=await import('/assets/demo/world.js');
      return {width:world.width,height:world.height,parts:module.getState().partBounds,
        labels:[...document.querySelectorAll('.part-label:not([hidden])')].map(el=>{
          const r=el.getBoundingClientRect();return {id:el.dataset.part,x:r.x-world.x,y:r.y-world.y,width:r.width,height:r.height,text:el.textContent};})};
    }""")
    check(name + " seven labels", len(facts["labels"]) == 7)
    collisions = [(a["id"], b["id"]) for i, a in enumerate(facts["labels"]) for b in facts["labels"][i + 1 :] if overlap(a, b)]
    check(name + " labels do not overlap", not collisions, collisions)
    collisions = [(a["id"], b["id"]) for a in facts["labels"] for b in facts["parts"] if overlap(a, b)]
    check(name + " labels clear all shape bounds", not collisions, collisions)
    check(
        name + " labels stay inside world",
        all(
            a["x"] >= 0 and a["y"] >= 40 and a["x"] + a["width"] <= facts["width"] + 1 and a["y"] + a["height"] <= facts["height"] + 1 for a in facts["labels"]
        ),
        facts,
    )
    return facts


with tempfile.TemporaryDirectory(prefix="ptw-seven-parts-") as tmp:
    SHOTS.mkdir(exist_ok=True)
    with (SHOTS / "verification-server.log").open("w") as log:
        with app_server(8766, {**os.environ, "PAPER_RUNS_DIR": tmp}, log):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                parity = []
                for width, height in [(1440, 900), (1920, 1080)]:
                    for theme in ["light", "dark"]:
                        name = f"{width}x{height}-{theme}"
                        page = themed_page(browser, width, height, theme)
                        context = page.context
                        errors = page_errors(page)
                        page.goto(BASE)
                        response = page.request.post(
                            BASE + "/api/runs",
                            multipart={
                                "demo": "true",
                                "file": {"name": "paper.pdf", "mimeType": "application/pdf", "buffer": (ROOT / "static/demo/paper.pdf").read_bytes()},
                            },
                        )
                        assert response.ok, response.text()
                        run = response.json()["id"]
                        page.goto(BASE + "/build/" + run)
                        seen = set()
                        states = []
                        layout = []
                        duplicates = []
                        captured = False
                        while "/build/" in page.url:
                            facts = page.evaluate("""()=>{
                              const steps=[...document.querySelectorAll('#steps>li')];if(!steps.length)return null;
                              const rect=el=>el.getBoundingClientRect().toJSON();
                              return {states:steps.map(el=>el.dataset.state),step:steps.findIndex(el=>el.dataset.state==='active')+1,
                                activity:[...document.querySelectorAll('#activity>li')].map(el=>({key:el.dataset.key,text:el.textContent})),
                                detailParent:document.querySelector('.card-body').parentElement.dataset.state,
                                left:rect(document.querySelector('.build-card')),right:rect(document.querySelector('#discovered')),logo:rect(document.querySelector('.brand')),
                                height:innerHeight,scroll:document.documentElement.scrollHeight,body:document.body.scrollHeight,
                                circles:steps.map(el=>rect(el.querySelector('.circle')))};
                            }""")
                            if not facts:
                                break
                            seen.add(facts["step"] or 5)
                            states.append(facts)
                            layout.append(
                                facts["scroll"] <= height
                                and facts["body"] <= height
                                and abs(facts["left"]["x"] - facts["logo"]["x"]) < 1
                                and facts["left"]["right"] < facts["right"]["x"]
                                and all(abs(c["x"] - facts["circles"][0]["x"]) < 1 for c in facts["circles"])
                            )
                            keys = [item["key"] for item in facts["activity"]]
                            texts = " ".join(item["text"] for item in facts["activity"])
                            duplicates.append(
                                len(keys) != len(set(keys))
                                or ("Shaping your lessons" in texts and "Shaping 4 lessons" in texts)
                                or ("Comparing the results with the paper" in texts and "Comparing with the paper:" in texts)
                            )
                            if facts["step"] == 4 and not captured:
                                page.screenshot(path=str(SHOTS / f"progress-{name}.png"), animations="disabled")
                                captured = True
                            if facts["step"]:
                                check_active = facts["detailParent"] == "active"
                                if not check_active:
                                    layout[-1] = False
                            if len(states) > 120:
                                raise AssertionError("Walkthrough did not finish")
                            if all(state == "done" for state in facts["states"]):
                                break
                            page.wait_for_timeout(200)
                        page.wait_for_url("**/learn/*", timeout=7000)
                        page.wait_for_selector(".specimen-controls", timeout=15000)
                        check(name + " full real walkthrough", seen == {1, 2, 3, 4, 5}, sorted(seen))
                        check(
                            name + " progress no page scroll, aligned vertical stepper and two columns",
                            all(layout),
                            [s for s, ok in zip(states, layout, strict=False) if not ok],
                        )
                        check(name + " no duplicate feed keys or actions throughout walkthrough", not any(duplicates))
                        check(name + " rebuilt example loads shared modules", page.locator(".specimen-controls").count() == 1)

                        page.goto(BASE + "/demo")
                        page.wait_for_selector(".specimen-controls")
                        page.evaluate("document.fonts.ready")
                        page.evaluate("async()=>{window.world=await import('/assets/demo/world.js');world.setParams({I:2,tau:20});}")
                        before = page.evaluate("world.getState()")
                        animation = page.evaluate("""async()=>{
                          await new Promise(requestAnimationFrame);
                          const start=performance.now(),samples=[];
                          [...document.querySelectorAll('.specimen-controls button')].find(b=>b.textContent==='Explode').click();
                          await new Promise(resolve=>{function tick(now){const s=world.getState();samples.push({at:now-start,assembly:s.assembly});if(now-start>550)resolve();else requestAnimationFrame(tick)}requestAnimationFrame(tick)});
                          return samples;
                        }""")
                        after = page.evaluate("world.getState()")
                        complete = next((s["at"] for s in animation if s["assembly"] == 1), 10000)
                        check(
                            name + " smooth 400ms explosion with running simulation",
                            any(0 < s["assembly"] < 1 for s in animation)
                            and 300 < complete < 550
                            and after["assembly"] == 1
                            and after["time"] > before["time"],
                            animation,
                        )
                        facts = geometry(page, name + " lesson 1")
                        page.screenshot(path=str(SHOTS / f"explode-2d-{name}.png"))
                        parts = page.evaluate("world.teachingParts")
                        for part in parts:
                            page.locator(f'.part-label[data-part="{part["id"]}"]').click()
                            expect(page.locator(".anatomy-inspector")).to_be_visible()
                            expect(page.locator(".anatomy-inspector select")).to_have_value(part["id"])
                            check(
                                name + " label inspection " + part["id"],
                                page.locator(".anatomy-description").inner_text() == part["description"]
                                and bool(page.locator(".anatomy-value").inner_text())
                                and page.locator(f'.term[data-link="{part["link"]}"].is-linked').count() == 1
                                and page.locator(".anatomy-actions button").count() == 3,
                            )
                            if part["id"] == "soma":
                                first = page.locator(".anatomy-value").inner_text()
                                page.wait_for_timeout(140)
                                check(name + " inspector voltage remains live", first != page.locator(".anatomy-value").inner_text())
                                page.screenshot(path=str(SHOTS / f"inspector-2d-{name}.png"))
                            page.get_by_role("button", name="Close", exact=True).click()
                            bounds = page.evaluate("world.getState().partBounds")
                            shape = next(b for b in bounds if b["id"] == part["id"])
                            world = page.locator("#world").bounding_box()
                            page.mouse.click(world["x"] + shape["x"] + shape["width"] / 2, world["y"] + shape["y"] + shape["height"] / 2)
                            expect(page.locator(".anatomy-inspector")).to_be_visible()
                            expect(page.locator(".anatomy-inspector select")).to_have_value(part["id"])
                            check(name + " shape inspection " + part["id"], page.locator(f'.term[data-link="{part["link"]}"].is-linked').count() == 1)
                            page.get_by_role("button", name="Close", exact=True).click()
                        page.get_by_role("button", name="Assemble", exact=True).click()
                        page.wait_for_timeout(500)
                        assembled = page.evaluate("world.getState()")
                        check(
                            name + " reassembly restores exact positions and clock keeps running",
                            assembled["assemblyPositions"] == before["assemblyPositions"] and assembled["time"] > after["time"],
                        )
                        page.get_by_role("button", name="Explode", exact=True).click()
                        page.wait_for_timeout(500)
                        page.locator("#lesson-path button").nth(3).click()
                        page.wait_for_timeout(600)
                        geometry(page, name + " lesson 4")
                        page.screenshot(path=str(SHOTS / f"explode-2d-lesson4-{name}.png"))
                        check(name + " unchanged scientific reference", page.evaluate("world.measure(2).spikes===33&&world.measure(3).spikes===63"))
                        page.evaluate("world.pause();world.setParams({I:2,tau:20})")
                        labels2d = page.locator(".part-label .tag-name").all_text_contents()
                        values2d = page.locator(".part-label .tag-value").all_text_contents()
                        parity.append((width, height, theme, parts, labels2d, values2d))
                        check(name + " no browser errors", not errors, errors)
                        context.close()
                # Stable fixture isolates DOM replacement and overflow from worker timing.
                folder = Path(tmp) / "layout-fixture"
                folder.mkdir()
                data = json.loads((Path(tmp) / run / "status.json").read_text())
                data.update(
                    step=4,
                    done=False,
                    error=None,
                    headline="Building and checking your world",
                    subline="Checking the results against the paper.",
                    waiting_hints=["Looking closely at Membrane leak"],
                )
                for i, step in enumerate(data["steps"]):
                    step["state"] = "done" if i < 3 else "active" if i == 3 else "pending"
                data["activity"] = [
                    {"key": "compare", "text": "Comparing the results with the paper", "done": False},
                    {"key": "lessons", "text": "Shaping your lessons", "done": False},
                ]
                (folder / "status.json").write_text(json.dumps(data))
                (folder / "source.json").write_text('{"demo":true}')
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(BASE + "/build/layout-fixture")
                page.wait_for_selector('#activity [data-key="compare"]')
                page.evaluate("window.compareItem=document.querySelector('#activity [data-key=compare]')")
                data["activity"][0].update(text="Comparing with the paper: 4 of 4 results match", done=True)
                data["activity"][1].update(text="Shaping 4 lessons for you", done=True)
                (folder / "status.json").write_text(json.dumps(data))
                expect(page.locator('#activity [data-key="compare"]')).to_contain_text("4 of 4")
                check(
                    "specific activity updates replace generic DOM nodes",
                    page.evaluate("compareItem===document.querySelector('#activity [data-key=compare]')") and page.locator("#activity li").count() == 2,
                )
                for width in [390, 899, 900]:
                    page.set_viewport_size({"width": width, "height": 900})
                    layout = page.evaluate(
                        """()=>{const a=document.querySelector('.build-card').getBoundingClientRect(),b=document.querySelector('#discovered').getBoundingClientRect();return {stacked:b.top>=a.bottom,side:b.left>=a.right,scroll:document.documentElement.scrollHeight,width:document.documentElement.scrollWidth}}"""
                    )
                    check(
                        f"progress responsive at {width}px",
                        layout["scroll"] <= 900 and layout["width"] <= width and (layout["stacked"] if width < 900 else layout["side"]),
                        layout,
                    )
                    page.screenshot(path=str(SHOTS / f"progress-responsive-{width}.png"))
                page.set_viewport_size({"width": 1440, "height": 900})
                data["discovered"]["concepts"] = [f"Paper concept {i}" for i in range(120)]
                (folder / "status.json").write_text(json.dumps(data))
                page.wait_for_function("document.querySelectorAll('#concepts .chip').length>100")
                overflow = page.evaluate(
                    "()=>{const d=document.querySelector('#discovered');return {page:document.documentElement.scrollHeight,viewport:innerHeight,content:d.scrollHeight,column:d.clientHeight,overflow:getComputedStyle(d).overflowY}}"
                )
                check(
                    "discovery overflow stays inside its column",
                    overflow["page"] <= overflow["viewport"] and overflow["content"] > overflow["column"] and overflow["overflow"] == "auto",
                    overflow,
                )
                page.emulate_media(reduced_motion="reduce")
                page.reload()
                page.wait_for_selector("#steps>li[data-state=active]")
                check(
                    "reduced motion disables progress pulse",
                    page.locator("#steps>li[data-state=active] .circle").evaluate("el=>getComputedStyle(el,'::after').animationName==='none'"),
                )
                page.close()
                browser.close()
                # Software WebGL teardown can stall a shared browser's compositor.
                # Run the 3D parity phase after timing the 2D transitions.
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
                for width, height, theme, parts, labels2d, values2d in parity:
                    name = f"{width}x{height}-{theme}"
                    page = themed_page(browser, width, height, theme)
                    context = page.context
                    errors = page_errors(page)
                    page.goto(BASE + "/demo/3d")
                    page.wait_for_selector(".specimen-controls", timeout=30000)
                    page.evaluate(
                        "async()=>{window.world=await import('/assets/demo3d/world.js');world.pause();world.setParams({I:2,tau:20});world.setAssembly(1)}"
                    )
                    page.wait_for_function("world.getState().assembly===1")
                    page.wait_for_timeout(300)
                    labels3d = {
                        el["id"]: el
                        for el in page.locator("[data-part]").evaluate_all(
                            "els=>els.filter(e=>!e.hidden).map(e=>({id:e.dataset.part,name:e.querySelector('.tag-name').textContent,value:e.querySelector('.tag-value').textContent}))"
                        )
                    }
                    check(
                        name + " seven shared IDs, label text and values in 3D",
                        len(labels3d) == 7
                        and all(labels3d[part["id"]]["name"] == labels2d[i] and labels3d[part["id"]]["value"] == values2d[i] for i, part in enumerate(parts)),
                        labels3d,
                    )
                    page.screenshot(path=str(SHOTS / f"explode-3d-{name}.png"))
                    check(name + " no 3D browser errors", not errors, errors)
                    context.close()
                browser.close()
        (SHOTS / "progress-explode-checks.json").write_text(json.dumps(results, indent=2))

assert all(r["pass"] for r in results), [r for r in results if not r["pass"]]
print(f"{len(results)} checks passed")
