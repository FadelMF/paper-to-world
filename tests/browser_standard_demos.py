"""Demo consistency, complete component data, unclipped normal views and anatomy actions."""

import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
OUT = Path('artifacts/standard-demos')
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1000, 'height': 760})
    errors = page_errors(page, console=True)
    page.goto(BASE)
    assert page.locator('#example-upload,.sample-details').count() == 0
    assert 'Vaswani' not in page.locator('body').inner_text()
    assert 'Watch this paper become a world' not in page.locator('body').inner_text()
    for dimension in ['2d', '3d']:
        page.goto(BASE + '/demo/attention/' + dimension)
        page.locator('#workspace').wait_for(state='visible')
        expect(page.locator('#paper-label')).to_have_text('Transformer · ' + dimension.upper())
        inspect = page.locator('[data-info="selected-vector"]')
        inspect.locator('summary').first.click()
        cells = inspect.locator('table tbody td')
        expect(cells).to_have_count(12)
        assert all(text.strip() for text in cells.all_text_contents())
        page.evaluate("async dim=>window.demoWorld=await import('/assets/attention'+dim+'/world.js')", dimension)
        expected = page.evaluate('demoWorld.getState().encoder.flat().map(v=>v.toFixed(3))')
        assert cells.all_text_contents() == expected
        assert page.locator('.transformer-detail').evaluate('(el)=>el.clientHeight>0 && getComputedStyle(el).overflowY==="auto"')
        detail_box = page.locator('.transformer-detail').bounding_box()
        world_box = page.locator('#world').bounding_box()
        assert detail_box['y'] + detail_box['height'] <= world_box['y'] + world_box['height'] + 1
        page.locator('[data-object="source_embed"]').click()
        expect(page.locator('[data-info="selected-vector"] table tbody td')).to_have_count(12)
        page.locator('[data-object="encoder_attention"]').click()
        page.locator('[data-info="qkv"] summary').click()
        expect(page.locator('[data-info="qkv"] table')).to_have_count(3)
        for index in range(6):
            page.locator('#lesson-path button').nth(index).click()
            for summary in page.locator('.transformer-detail > details > summary').all():
                summary.click()
            detail = page.locator('.transformer-detail')
            detail.evaluate('el=>el.scrollTop=el.scrollHeight')
            assert detail.evaluate('(el)=>el.clientHeight>0 && getComputedStyle(el).overflowY==="auto"')
            assert page.evaluate('scrollY') == 0
        page.locator('#visual').screenshot(path=str(OUT / f'transformer-{dimension}-normal.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.locator('#visual').screenshot(path=str(OUT / f'transformer-{dimension}-phone.png'))
        page.set_viewport_size({'width': 1000, 'height': 760})
    for dimension, route in [('2d', '/demo'), ('3d', '/demo/3d')]:
        page.goto(BASE + route)
        page.locator('#workspace').wait_for(state='visible')
        expect(page.locator('#paper-label')).to_have_text('Neuron · ' + dimension.upper())
        for width in [1000, 390]:
            page.set_viewport_size({'width': width, 'height': 844})
            page.locator('.specimen-controls button', has_text='Anatomy').click()
            panel = page.locator('.anatomy-inspector')
            expect(panel).to_be_visible()
            assert panel.evaluate('(el)=>el.clientHeight>=el.scrollHeight-1')
            assert 'Illustration and sources' not in panel.inner_text()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            for button in panel.locator('.anatomy-actions button').all():
                rect = button.bounding_box()
                assert rect['height'] >= 40 and rect['x'] >= 0 and rect['x'] + rect['width'] <= width
            panel.screenshot(path=str(OUT / f'neuron-{dimension}-{width}-inspector.png'))
            panel.get_by_role('button', name='Focus component').click()
            expect(panel).to_be_visible()
            panel.get_by_role('button', name='Reset view', exact=True).click()
            expect(panel).to_be_visible()
            panel.get_by_role('button', name='Close', exact=True).click()
            expect(panel).to_be_hidden()
        page.set_viewport_size({'width': 1000, 'height': 760})
    assert not errors, errors
    browser.close()
print(
    'PASS: consistent demo entry, full encoder/embedding/QKV data, six unclipped information views, normal/phone neuron inspector controls; no browser errors.'
)
