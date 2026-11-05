"""Inspectors and disclosures must not scroll the document or close themselves."""

import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
OUT = Path('artifacts/scroll-stability')
OUT.mkdir(parents=True, exist_ok=True)


def assert_scroll(page, before):
    page.wait_for_timeout(250)
    assert abs(page.evaluate('scrollY') - before) < 2, (before, page.evaluate('scrollY'))


with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for dim, route in [('2d', '/demo'), ('3d', '/demo/3d')]:
        for width in [1000, 390]:
            page = browser.new_page(viewport={'width': width, 'height': 844})
            errors = page_errors(page, console=True)
            page.goto(BASE + route)
            page.locator('#workspace').wait_for(state='visible')
            anatomy = page.get_by_role('button', name='Anatomy', exact=True)
            anatomy.scroll_into_view_if_needed()
            before = page.evaluate('scrollY')
            anatomy.click()
            panel = page.locator('.anatomy-inspector')
            expect(panel).to_be_visible()
            assert_scroll(page, before)
            page.wait_for_timeout(1600)
            expect(panel).to_be_visible()
            assert_scroll(page, before)
            picker = panel.locator('.app-select-trigger')
            picker.click()
            page.keyboard.press('End')
            page.keyboard.press('Enter')
            expect(panel).to_be_visible()
            assert_scroll(page, before)
            for label in ['Focus component', 'Reset view']:
                panel.get_by_role('button', name=label, exact=True).click()
                expect(panel).to_be_visible()
                assert_scroll(page, before)
            panel.screenshot(path=str(OUT / f'{dim}-{width}.png'))
            panel.get_by_role('button', name='Close', exact=True).click()
            expect(panel).to_be_hidden()
            assert_scroll(page, before)
            anatomy.click()
            page.keyboard.press('Escape')
            expect(panel).to_be_hidden()
            assert_scroll(page, before)
            navigation = page.locator('#lesson-path button').first
            navigation.evaluate("el=>el.scrollIntoView({block:'end'})")
            bounds = navigation.bounding_box()
            dock = page.locator('#controlbar').bounding_box()
            assert bounds['y'] + bounds['height'] <= dock['y'], (bounds, dock)
            navigation.click()
            assert not errors, errors
            page.close()
    for dim in ['2d', '3d']:
        page = browser.new_page(viewport={'width': 1000, 'height': 844})
        page.goto(BASE + '/demo/attention/' + dim)
        summary = page.locator('[data-info="selected-vector"] > summary')
        summary.scroll_into_view_if_needed()
        before = page.evaluate('scrollY')
        summary.click()
        expect(page.locator('[data-info="selected-vector"] table')).to_be_visible()
        assert_scroll(page, before)
        page.wait_for_timeout(800)
        assert_scroll(page, before)
        page.close()
    browser.close()
print('PASS: Anatomy open/select/focus/reset/close/Escape stays stable in 2D/3D at desktop/phone sizes; Transformer disclosures do not force scroll.')
