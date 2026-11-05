"""Scrolling the reading column must keep every desktop world visible in one viewport."""

import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
OUT = Path('artifacts/fixed-workspace')
OUT.mkdir(parents=True, exist_ok=True)
ROUTES = ['/demo', '/demo/3d', '/demo/attention/2d', '/demo/attention/3d']


def same_box(before, after):
    assert all(abs(before[key] - after[key]) < 1 for key in ('x', 'y', 'width', 'height')), (before, after)


with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for route in ROUTES:
        for width, height in [(1000, 760), (1440, 900)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            errors = page_errors(page, console=True)
            page.goto(BASE + route)
            expect(page.locator('#workspace')).to_be_visible()
            page.evaluate('document.fonts.ready')
            reading, visual, world = (page.locator(selector) for selector in ('#reading', '#visual', '#world'))
            frame, model = visual.bounding_box(), world.bounding_box()
            right_scroll = visual.evaluate('el=>el.scrollTop')
            bounds = reading.bounding_box()
            page.mouse.move(bounds['x'] + 60, bounds['y'] + 80)
            page.mouse.wheel(0, 1200)
            page.wait_for_function("document.getElementById('reading').scrollTop>0")
            assert page.evaluate('scrollY===0 && document.documentElement.scrollHeight<=innerHeight+1')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            same_box(frame, visual.bounding_box())
            same_box(model, world.bounding_box())
            assert visual.evaluate('el=>el.scrollTop') == right_scroll
            assert frame['y'] + frame['height'] <= page.locator('#controlbar').bounding_box()['y'] + 1
            page.locator('#ask-open').scroll_into_view_if_needed()
            expect(page.locator('#ask-open')).to_be_in_viewport()
            same_box(frame, visual.bounding_box())
            if '/attention/' in route:
                inspect = page.locator('[data-info="selected-vector"]')
                inspect.locator('summary').click()
                last_value = inspect.locator('table tbody td').last
                last_value.scroll_into_view_if_needed()
                expect(last_value).to_be_in_viewport()
                detail = page.locator('.transformer-detail').bounding_box()
                assert detail['y'] + detail['height'] <= world.bounding_box()['y'] + world.bounding_box()['height'] + 1
                same_box(frame, visual.bounding_box())
            else:
                page.get_by_role('button', name='Anatomy', exact=True).click()
                expect(page.locator('.anatomy-inspector')).to_be_visible()
                assert page.evaluate('scrollY') == 0
                page.get_by_role('button', name='Close', exact=True).click()
            if width == 1440:
                page.screenshot(path=str(OUT / (route.strip('/').replace('/', '-') + '-reading-scrolled.png')))
            assert not errors, errors
            page.close()
        # Phones retain a stacked view with all information reachable and no sideways overflow.
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.goto(BASE + route)
        expect(page.locator('#workspace')).to_be_visible()
        assert page.locator('#visual').bounding_box()['y'] < page.locator('#reading').bounding_box()['y']
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.locator('#ask-open').scroll_into_view_if_needed()
        expect(page.locator('#ask-open')).to_be_in_viewport()
        page.close()
    browser.close()
print('PASS: all four desktop worlds stay visible while the left column scrolls; long inspections remain reachable; phone layouts stay usable.')
