"""Automated accessibility audit (axe-core, WCAG 2.1 A and AA) of every page and every example lesson.

    APP_URL=http://127.0.0.1:8000 python3 tests/browser_accessibility.py

Pages are checked at desktop and phone width; each example lesson is opened in turn. Any violation fails.
axe-core is in tests/vendor (MPL-2.0). The pages' Content-Security-Policy is bypassed only to inject the audit.
An automated audit finds about half of WCAG issues; it does not replace testing with a screen reader.
"""

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("APP_URL", "http://127.0.0.1:8000")
AXE = Path(__file__).resolve().parent / "vendor" / "axe.min.js"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
PAGES = ["/", "/?example=3d", "/?example=attention2d", "/?example=attention3d", "/?mode=paper", "/worlds"]
LESSONS = {"/demo": 4, "/demo/3d": 4, "/demo/attention/2d": 6, "/demo/attention/3d": 6}
AUDIT = (
    "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
    ".map(v => ({rule: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))"
)


SETTLED = """() => Promise.all(document.getAnimations()
  .filter(a => a.effect && a.effect.target && a.effect.target.closest && !a.effect.target.closest('#world') && a.effect.getTiming().iterations !== Infinity)
  .map(a => a.finished))"""


def audit(page, label, found):
    page.evaluate(SETTLED)  # contrast is judged on the settled page, not mid-fade
    page.add_script_tag(path=str(AXE))
    for violation in page.evaluate(AUDIT, TAGS):
        found.append({"where": label, **violation})


found, checked = [], 0
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for width, height in [(1440, 900), (390, 844)]:
        page = browser.new_context(viewport={"width": width, "height": height}, bypass_csp=True).new_page()
        for route in PAGES:
            page.goto(BASE + route)
            page.wait_for_timeout(2500)
            audit(page, f"{route} @{width}", found)
            checked += 1
        for route, count in LESSONS.items():
            page.goto(BASE + route)
            page.wait_for_selector("#workspace:not([hidden])")
            for index in range(1, count + 1):
                page.locator(f'#lesson-path button[aria-label^="Lesson {index}:"]').click()
                page.wait_for_timeout(1200)
                audit(page, f"{route} lesson {index} @{width}", found)
                checked += 1
        page.context.close()
    browser.close()

print(json.dumps({"views_checked": checked, "violations": found}))
sys.exit(1 if found else 0)
