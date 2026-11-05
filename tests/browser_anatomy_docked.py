"""Anatomy belongs to the right simulation panel and never covers the model or lesson text."""

import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
OUT = Path('artifacts/anatomy-docked')
OUT.mkdir(parents=True, exist_ok=True)


def inside(inner, outer):
    return (
        inner['x'] >= outer['x'] - 1
        and inner['y'] >= outer['y'] - 1
        and inner['x'] + inner['width'] <= outer['x'] + outer['width'] + 1
        and inner['y'] + inner['height'] <= outer['y'] + outer['height'] + 1
    )


with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for mode, route in [('2d', '/demo'), ('3d', '/demo/3d')]:
        for width, height in [(1440, 900), (1000, 760), (390, 844)]:
            page = browser.new_page(viewport={'width': width, 'height': height})
            errors = page_errors(page, console=True)
            page.goto(BASE + route)
            expect(page.locator('#workspace')).to_be_visible()
            page.evaluate('document.fonts.ready')
            if mode == '3d':
                page.evaluate("async()=>window.dockedWorld=await import('/assets/demo3d/world.js')")
                page.wait_for_function('dockedWorld.getState().frames>1')
                frames = page.evaluate('dockedWorld.getState().frames')
            before = page.evaluate('scrollY')
            left_scroll = page.locator('#reading').evaluate('el=>el.scrollTop')
            page.get_by_role('button', name='Anatomy', exact=True).click()
            panel = page.locator('.anatomy-inspector')
            expect(panel).to_be_visible()
            if mode == '3d':
                page.wait_for_function('frames=>dockedWorld.getState().frames>frames+1 && !dockedWorld.getState().cameraTransitioning', arg=frames)
            bounds, visual, model = panel.bounding_box(), page.locator('#visual').bounding_box(), page.locator('#world').bounding_box()
            assert inside(bounds, visual), (bounds, visual)
            if width == 1440:
                assert bounds['x'] >= model['x'] + model['width'] - 1
            else:
                assert bounds['y'] >= model['y'] + model['height'] - 1
            assert model['height'] >= 160 and model['width'] >= 200
            for control in panel.locator('.app-select-trigger, .anatomy-actions button, .anatomy-value').all():
                assert inside(control.bounding_box(), bounds)
            assert page.evaluate('scrollY') == before
            assert page.locator('#reading').evaluate('el=>el.scrollTop') == left_scroll
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            if width > 760:
                assert bounds['y'] + bounds['height'] <= page.locator('#controlbar').bounding_box()['y']
            expect(page.locator('.neuron-explanation')).to_be_hidden()
            clock = page.locator('#clock-status').inner_text()
            panel.get_by_role('region', name='Component description').focus()
            page.keyboard.press(' ')
            assert page.locator('#clock-status').inner_text() == clock
            assert page.evaluate('scrollY') == before
            panel.get_by_role('button', name='Focus component').click()
            panel.get_by_role('button', name='Reset view', exact=True).click()
            expect(panel).to_be_visible()
            if mode == '3d':
                panel.get_by_role('button', name='Focus component').click()
                page.wait_for_function('!dockedWorld.getState().cameraTransitioning')
                focused_target = page.evaluate('dockedWorld.getState().target')
            page.screenshot(path=str(OUT / f'verified-{mode}-{width}.png'))
            panel.get_by_role('button', name='Close', exact=True).click()
            expect(page.locator('.neuron-explanation')).to_be_visible()
            if mode == '3d':
                page.wait_for_timeout(100)
                assert page.evaluate('dockedWorld.getState().target') == focused_target
            assert page.evaluate('scrollY') == before
            assert not errors, errors
            page.close()
    # The same shared inspector is also used by the home preview.
    for width in (1440, 390):
        page = browser.new_page(viewport={'width': width, 'height': 900})
        page.goto(BASE)
        page.get_by_role('button', name='Anatomy', exact=True).click()
        assert inside(page.locator('.anatomy-inspector').bounding_box(), page.locator('#visual').bounding_box())
        page.close()
    browser.close()
print(
    'PASS: 2D/3D Anatomy docks beside or below the model inside the right panel; all controls fit, focus/reset stay open, and Close restores the state panel.'
)
