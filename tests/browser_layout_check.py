"""Layout, label, mode and number checks for Home, Your worlds and the Lesson view in real Chromium.

Every page is opened and then hard-reloaded (cache bypassed, like Ctrl+Shift+R). Needs the app on APP_URL (default 127.0.0.1:8000)
and supports an empty saved-world list. Screenshots go to artifacts/. Exits non-zero if any check fails.
"""

import json
import os
import sys
from pathlib import Path

from harness import themed_page
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "artifacts"
SHOTS.mkdir(exist_ok=True)
URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")
EXAMPLES = {
    "2d": {"path": "/demo", "base": "/assets/demo/", "hint": "2D schematic · Click a part to inspect"},
    "3d": {"path": "/demo/3d", "base": "/assets/demo3d/", "hint": "3D · Drag to rotate · Click to inspect"},
}
PARTS_2D = ("dendrites", "soma", "leak", "threshold", "myelin", "axon", "terminals")
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


# Records canvas text so the 2D plot's own label can be read back.
CANVAS_TEXT = """window.__canvasText=[];const original=CanvasRenderingContext2D.prototype.fillText;
CanvasRenderingContext2D.prototype.fillText=function(text,...rest){window.__canvasText.push(String(text));if(window.__canvasText.length>400)window.__canvasText.shift();return original.call(this,text,...rest);};"""

FACTS = """()=>{
 const rect=el=>el?el.getBoundingClientRect().toJSON():null;
 const shown=el=>!el.hidden&&el.offsetParent&&getComputedStyle(el).opacity>0.5;
 // Every element whose content overflows and that the user can scroll.
 const scrollers=[document.documentElement,...document.querySelectorAll('body *')].filter(el=>{
   if(el===document.documentElement)return el.scrollHeight>innerHeight;
   return /(auto|scroll)/.test(getComputedStyle(el).overflowY)&&el.scrollHeight>el.clientHeight+1;})
  .map(el=>el===document.documentElement?'page':el.id?'#'+el.id:'.'+el.className.split(' ')[0]);
 const canvas=document.querySelector('#world>canvas');
 return {scrollHeight:document.documentElement.scrollHeight,innerHeight,scrollers,
  logo:rect(document.querySelector('.brand')),theme:rect(document.querySelector('[data-theme-toggle]')),
  h1:rect(document.querySelector('.welcome h1')),subtitle:rect(document.querySelector('.welcome>p')),card:rect(document.querySelector('.start-panel')),
  side:rect(document.querySelector('.home-side')),lesson:rect(document.getElementById('lesson-content')),panel:rect(document.getElementById('visual')),
  world:rect(document.getElementById('world')),canvas:rect(canvas),canvasPixels:canvas?canvas.width*canvas.height:0,
  plot:rect(document.querySelector('#world .voltage-inset:not([hidden])')),plotArea:rect(document.querySelector('#world .plot-area:not([hidden])')),
  segmented:rect(document.querySelector('.specimen-controls')),
  segmentedFont:document.querySelector('.specimen-controls button')?getComputedStyle(document.querySelector('.specimen-controls button')).fontSize:null,
  hint:rect(document.querySelector('.scene-hint')),hintText:document.querySelector('.scene-hint')?.textContent,
  inspector:document.querySelector('.anatomy-inspector:not([hidden])')?rect(document.querySelector('.anatomy-inspector')):null,
  selected:document.querySelector('[data-example][aria-checked=true]')?.dataset.example||null,
  badge:document.getElementById('world-dimension')?.textContent,
  renderer:document.querySelector('[data-renderer]')?'three-webgl':'canvas-2d',
  labels:[...document.querySelectorAll('#world .object-tag')].filter(shown).map(t=>({id:t.dataset.part||t.dataset.object||t.textContent,caption:t.classList.contains('part-label'),text:t.textContent,rect:t.getBoundingClientRect().toJSON()})),
  resources:performance.getEntriesByType('resource').map(r=>new URL(r.name).pathname)};}"""


def overlaps(a, b):
    return min(a["right"], b["right"]) - max(a["left"], b["left"]) > 0.5 and min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]) > 0.5


def hard_open(page, path):
    page.goto(URL + path, wait_until="networkidle")
    page.context.new_cdp_session(page).send("Page.reload", {"ignoreCache": True})
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        "()=>document.querySelector('#world canvas')&&document.getElementById('world-dimension').textContent.includes('D world')", timeout=30000
    )
    page.wait_for_timeout(2000)


def label_checks(name, facts):
    labels = facts["labels"]
    pairs = [(a["id"], b["id"]) for i, a in enumerate(labels) for b in labels[i + 1 :] if overlaps(a["rect"], b["rect"])]
    check(f"labels do not overlap · {name}", not pairs, f"{len(labels)} labels" + (f", overlapping {pairs}" if pairs else ""))
    world = facts["world"]
    inside = all(
        t["rect"]["left"] >= world["left"] - 1
        and t["rect"]["right"] <= world["right"] + 1
        and t["rect"]["top"] >= world["top"] - 1
        and t["rect"]["bottom"] <= world["bottom"] + 1
        for t in labels
    )
    check(f"labels inside the panel · {name}", inside)
    if facts["inspector"]:
        covered = [t["id"] for t in labels if overlaps(t["rect"], facts["inspector"])]
        check(f"no label under the inspector · {name}", not covered, str(covered))
    if facts["plotArea"]:
        on_plot = [t["id"] for t in labels if overlaps(t["rect"], facts["plotArea"])]
        check(f"2D labels keep off the plot · {name}", not on_plot, str(on_plot))
    if facts["plot"]:
        on_plot = [t["id"] for t in labels if overlaps(t["rect"], facts["plot"])]
        check(f"3D plot below the scene, no label on it · {name}", facts["canvas"]["bottom"] <= facts["plot"]["top"] + 0.5 and not on_plot)


def page_checks(name, facts, kind, key):
    allowed = {".home-side"} if kind == "home" else {"#reading", "#visual", ".transformer-detail"}
    check(
        f"one intended scroll container · {name}",
        facts["scrollHeight"] <= facts["innerHeight"] and set(facts["scrollers"]) <= allowed,
        f"scrollHeight {facts['scrollHeight']} / {facts['innerHeight']}, scrollable {facts['scrollers']}",
    )
    logo = facts["logo"]["left"]
    edges = [facts["h1"]["left"], facts["card"]["left"]] if kind == "home" else [facts["lesson"]["left"]]
    check(
        f"left edges = logo, right edge = theme button · {name}",
        all(abs(e - logo) <= 2 for e in edges) and abs(facts["panel"]["right"] - facts["theme"]["right"]) <= 2,
    )
    check(
        f"world drawn on first load, no tab switch · {name}",
        facts["canvasPixels"] > 0 and facts["canvas"]["width"] > 200 and facts["canvas"]["height"] > 200 and len(facts["labels"]) >= 3,
        f"canvas {facts['canvas']['width']:.0f}×{facts['canvas']['height']:.0f}, {len(facts['labels'])} labels",
    )
    if kind == "home":
        check(
            f"two columns, example selected, subtitle under title · {name}",
            facts["panel"]["left"] > facts["side"]["right"] and facts["selected"] == key and facts["subtitle"]["top"] >= facts["h1"]["bottom"] - 1,
        )
    check(f"hint text · {name}", facts["hintText"] == EXAMPLES[key]["hint"], facts["hintText"])
    seg, hint = facts["segmented"], facts["hint"]
    check(
        f"segmented control 28px in the hint row, not over the hint · {name}",
        seg is not None
        and 26 <= seg["height"] <= 30
        and facts["segmentedFont"] in ("12px", "13px")
        and abs(seg["top"] - hint["top"]) <= 2
        and not overlaps(seg, hint),
    )
    label_checks(name, facts)


def modes(page, name, tag, captions_expected):
    """2D Explode and Anatomy: parts move, the clock keeps running, captions and popover appear, nothing overlaps."""
    state = lambda: page.evaluate("()=>window.__world.getState()")
    page.evaluate("async()=>{window.__world=await import('/assets/demo/world.js');}")
    before = state()
    page.locator(".specimen-controls button", has_text="Explode").click()
    page.wait_for_function("()=>window.__world.getState().assembly===1", timeout=10000)
    page.wait_for_function("before=>window.__world.getState().time>before", arg=before["time"], timeout=10000)
    after = state()
    check(
        f"2D Explode animates parts apart, clock keeps running · {name}",
        after["assembly"] == 1 and after["assemblyPositions"] != before["assemblyPositions"] and after["time"] > before["time"],
        f"assembly {after['assembly']}, time {before['time']:.0f}→{after['time']:.0f} ms",
    )
    facts = page.evaluate(FACTS)
    values_live = sum(any(ch.isdigit() for ch in t["text"]) for t in facts["labels"]) >= 2
    check(f"2D Explode keeps one-line labels with live values · {name}", values_live and all(t["rect"]["height"] < 30 for t in facts["labels"]))
    label_checks(f"{name} explode", facts)
    page.screenshot(path=SHOTS / f"{tag}-explode.png")
    page.locator(".specimen-controls button", has_text="Anatomy").click()
    page.wait_for_timeout(900)
    facts = page.evaluate(FACTS)
    captions = [t for t in facts["labels"] if t["caption"] and t["id"] in PARTS_2D]
    picker = page.locator(".anatomy-inspector .app-select-trigger")
    picker.click()
    page.get_by_role("option", name="Membrane leak", exact=True).click()
    page.wait_for_timeout(200)
    description = page.locator(".anatomy-description").inner_text()
    actions = page.locator(".anatomy-actions button").count()
    check(
        f"2D Anatomy: captions, panel with picker, description, actions · {name}",
        facts["inspector"] is not None
        and len(captions) == captions_expected
        and "leak" in description.lower()
        and actions == 3
        and state()["anatomySelected"] == "leak",
        f'{len(captions)} captions, "{description[:40]}…", {actions} actions',
    )
    label_checks(f"{name} anatomy", page.evaluate(FACTS))
    page.screenshot(path=SHOTS / f"{tag}-anatomy.png")
    page.locator(".anatomy-actions button", has_text="Close").click()
    page.locator(".specimen-controls button", has_text="Assemble").click()
    for _ in range(50):  # wait for the reassembly animation itself, not a fixed delay
        if state()["assembly"] == 0:
            break
        page.wait_for_timeout(100)
    page.wait_for_timeout(100)
    check(f"2D Assemble restores the schematic exactly · {name}", state()["assemblyPositions"] == before["assemblyPositions"])


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chromium", headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
    errors = []
    for width, height in [(1440, 900), (1920, 1080)]:
        for theme in ["light", "dark"]:
            page = themed_page(browser, width, height, theme)
            context = page.context
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            tag = f"{width}x{height}-{theme}"
            runs = page.request.get(URL + "/api/runs").json()
            for key, example in EXAMPLES.items():
                hard_open(page, f"/?example={key}")
                page.screenshot(path=SHOTS / f"home-{key}-{tag}.png")
                home = page.evaluate(FACTS)
                page_checks(f"Home {key} {tag}", home, "home", key)
                if key == "2d":
                    modes(page, f"Home {tag}", f"home-2d-{tag}", 7)
                hard_open(page, example["path"])
                page.locator("#lesson-path button").nth(0).click()
                page.wait_for_timeout(2500)
                page.screenshot(path=SHOTS / f"lesson1-{key}-{tag}.png")
                lesson1 = page.evaluate(FACTS)
                page_checks(f"Lesson 1 {key} {tag}", lesson1, "lesson", key)
                same = (
                    example["base"] + "world.js" in home["resources"]
                    and sorted(t["id"] for t in home["labels"]) == sorted(t["id"] for t in lesson1["labels"])
                    and home["badge"] == lesson1["badge"]
                )
                check(f"Home preview = Lesson 1 drawing · {key} {tag}", same)
                check(f'prepared example omits redundant source banner · {key} {tag}', page.locator(".intro .citation:visible").count() == 0)
                page.locator("#lesson-path button").nth(3).click()
                page.wait_for_timeout(3000)
                page.screenshot(path=SHOTS / f"lesson4-{key}-{tag}.png")
                page_checks(f"Lesson 4 {key} {tag}", page.evaluate(FACTS), "lesson", key)
                if key == "2d":
                    modes(page, f"Lesson 4 {tag}", f"lesson4-2d-{tag}", 7)
            # Your worlds has its own page and lists the saved runs.
            page.goto(URL + "/worlds", wait_until="networkidle")
            page.wait_for_function("()=>document.querySelectorAll('#runs .run-item').length||document.querySelector('#runs .empty-worlds span')")
            # Every saved run is listed, or the empty state is shown when there is none.
            listed = page.locator("#runs .run-item").count() == len(runs) if runs else page.locator("#runs .empty-worlds").count() == 1
            check(
                f"Your worlds page lists the {len(runs)} saved runs · {tag}",
                listed and page.locator(".header-nav a[aria-current=page]").inner_text() == "Your worlds",
            )
            page.screenshot(path=SHOTS / f"worlds-{tag}.png")
            context.close()

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(CANVAS_TEXT)
    page = context.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Reload while scrolled: Home still renders both columns and the preview.
    hard_open(page, "/?example=2d")
    page.locator("#paper-tab").click()
    page.evaluate("document.querySelector('.home-side').scrollTop=400;window.scrollTo(0,400)")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2500)
    facts = page.evaluate(FACTS)
    check(
        "reload while scrolled: preview and two columns render",
        facts["canvasPixels"] > 0 and facts["panel"]["left"] > facts["side"]["right"] and facts["scrollHeight"] <= facts["innerHeight"],
    )
    # Every page, style and script must be revalidated, so a refresh never mixes old and new files.
    headers = {}

    def record(response):
        if response.url.startswith(URL):
            headers[response.url[len(URL) :]] = response.headers.get("cache-control")

    page.on("response", record)
    page.reload(wait_until="networkidle")
    stale = {path: value for path, value in headers.items() if value != ("no-store" if path.startswith("/api/") else "no-cache")}
    check(
        "public assets revalidate and API responses are not stored",
        bool(headers) and not stale,
        f"{len(headers)} responses" + (f", missing on {stale}" if stale else ""),
    )
    # Home restores the last opened example.
    hard_open(page, "/demo/3d")
    hard_open(page, "/")
    facts = page.evaluate(FACTS)
    check("Home selects the last opened example (3D)", facts["selected"] == "3d" and facts["renderer"] == "three-webgl")
    # The left column scrolls by itself when it overflows; the page and the preview do not move.
    page.set_viewport_size({"width": 1440, "height": 640})
    hard_open(page, "/?example=2d")
    page.locator("#paper-tab").click()
    side = page.locator(".home-side").bounding_box()
    page.mouse.move(side["x"] + side["width"] / 2, side["y"] + side["height"] / 2)
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(500)
    moved = page.evaluate("()=>{const s=document.querySelector('.home-side');return {side:s.scrollTop,page:scrollY,overflow:s.scrollHeight>s.clientHeight}}")
    panel = page.locator("#visual").bounding_box()
    page.mouse.move(panel["x"] + 40, panel["y"] + panel["height"] - 30)
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(300)
    after = page.evaluate("()=>({side:document.querySelector('.home-side').scrollTop,page:scrollY})")
    check(
        "Home left column scrolls under the cursor; page and preview stay",
        moved["overflow"] and moved["side"] > 0 and moved["page"] == 0 and after == {"side": moved["side"], "page": 0},
        json.dumps(moved),
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    hard_open(page, "/demo")
    box = page.locator("#reading").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(500)
    check("Lesson left column scrolls while the world stays fixed", page.evaluate("()=>document.getElementById('reading').scrollTop>0&&scrollY===0"))

    # Each example opens its own lessons and renderer; at one moment text, tags and plot agree on spikes.
    titles = {}
    for key, example in EXAMPLES.items():
        hard_open(page, example["path"])
        facts = page.evaluate(FACTS)
        titles[key] = [b.get_attribute("title") for b in page.locator("#lesson-path button").all()]
        dimension = page.evaluate(f"async()=>(await import('{example['base']}world.js')).dimensionality")
        check(
            f"{key} loads its own lessons/module, badge matches renderer",
            example["base"] + "lessons.json" in facts["resources"]
            and facts["badge"] == f"{dimension}D world"
            and facts["renderer"] == ("three-webgl" if key == "3d" else "canvas-2d"),
        )
        page.locator("#lesson-path button").nth(3).click()
        page.wait_for_timeout(500)
        for current, expected in [(2, 33), (3, 63)]:
            page.evaluate(
                f"async()=>{{window.__world=await import('{example['base']}world.js');window.__world.setParams({{I:{current}}});window.__world.play();}}"
            )
            page.wait_for_function("()=>window.__world.getState().firstSecondDone", timeout=240000, polling=500)
            page.evaluate("()=>window.__world.pause()")
            page.wait_for_timeout(400)
            state = page.evaluate("()=>window.__world.getState()")
            tags = {t["id"]: t["text"] for t in page.evaluate(FACTS)["labels"]}
            plot = (
                page.locator("#world .voltage-inset b").inner_text()
                if key == "3d"
                else next((t for t in reversed(page.evaluate("window.__canvasText")) if "Membrane potential" in t), "")
            )
            ok = (
                state["spikesFirstSecond"] == expected
                and f"{expected} spikes · 0–1000 ms" in tags.get("spike", "")
                and f"{expected} Hz · 0–1000 ms" in tags.get("rate", "")
                and f"{expected} spikes · 0–1000 ms" in plot
                and page.locator('.neuron-metrics [data-field="spikes"]').inner_text() == str(expected)
            )
            check(f"{key} at {current} nA: text = tags = plot", ok, f"{state['spikesFirstSecond']} / {tags.get('spike')} / {tags.get('rate')} / {plot}")
        source = page.request.get(URL + example['base'] + 'lessons.json').json()[3]['source']
        check(f'{key} lesson 4 records simulation provenance', source['kind'] == 'simulation')
    check("the two examples have different lesson sets", not set(titles["2d"]) & set(titles["3d"]))
    context.close()
    check("no page errors", not errors, str(errors[:3]))
    browser.close()

print(f"\n{len(failures)} failing check(s)" + (": " + ", ".join(failures) if failures else ""))
sys.exit(1 if failures else 0)
