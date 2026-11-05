"""Verify full Transformer coverage, distinct lesson inspections and computed teaching outcomes."""

import json
import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
SHOTS = ROOT / 'artifacts' / 'workflow-audit' / 'after'
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    for dimension in ['2d', '3d']:
        key = 'attention' + dimension
        lessons = json.loads((ROOT / 'static' / key / 'lessons.json').read_text())
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = page_errors(page, console=True)
        page.goto(BASE + '/?example=' + key)
        expect(page.locator('#world-dimension')).to_have_text(dimension.upper() + ' world')
        page.locator('#open-example').click()
        page.wait_for_url('**/demo/attention/' + dimension)
        expect(page.locator('#workspace')).to_be_visible()
        views = []
        for index, lesson in enumerate(lessons):
            page.locator('#lesson-path button').nth(index).click()
            expect(page.locator('.transformer-node')).to_have_count(12)
            expect(page.locator('[data-object="encoder_output"]')).to_be_visible()
            expect(page.locator('[data-object="cross_attention"]')).to_be_visible()
            expect(page.locator('.lesson-instructions')).to_contain_text(lesson['learning']['observe'])
            for symbol, value in lesson['learning']['test_params'].items():
                control = page.locator('#control-' + symbol)
                if control.evaluate('(el)=>el.tagName') == 'SELECT':
                    page.locator('#control-' + symbol + '-trigger').click()
                    page.locator('#control-' + symbol + '-options [role=option]').nth(int(value)).click()
                else:
                    control.fill(str(value))
            page.evaluate("async key => {window.teachingWorld=await import('/assets/'+key+'/world.js');}", key)
            page.wait_for_function(
                "expression => Boolean(new Function('state',`return (${expression})`)(teachingWorld.getState()))",
                arg=lesson['learning']['outcome_js'],
                polling=100,
                timeout=30000,
            )
            assert page.evaluate(
                "expression => Boolean(new Function('state',`return (${expression})`)(teachingWorld.getState()))", lesson['learning']['outcome_js']
            )

            expect(page.locator('#challenge')).to_have_class('challenge achieved')
            views.append(page.locator('.transformer-detail').get_attribute('data-view'))
            page.wait_for_timeout(200)
            page.evaluate("document.getElementById('reading').scrollTop=0; window.scrollTo(0,0)")
            page.screenshot(path=str(SHOTS / f'{key}-{index + 1}.png'))
        assert len(set(views)) == 6, views
        if dimension == '3d':
            before = page.evaluate('teachingWorld.getState().view.camera')
            canvas = page.locator('.spatial-graph canvas')
            box = canvas.bounding_box()
            page.mouse.move(box['x'] + box['width'] * 0.6, box['y'] + box['height'] * 0.4)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] * 0.8, box['y'] + box['height'] * 0.5, steps=12)
            page.mouse.up()
            assert page.evaluate('teachingWorld.getState().view.camera') != before
            page.locator('[data-spacing]').fill('100')
            assert page.evaluate('teachingWorld.getState().assemblyTarget') == 1
            page.locator('[data-reset]').click()
            page.locator('[data-spacing]').fill('35')
        page.locator('#lesson-path button').first.click()
        for theme in ['light', 'dark']:
            page.evaluate("async theme => {const ui=await import('/assets/ui/app.js');ui.setTheme(theme==='dark');}", theme)
            for width, height in [(390, 844), (1440, 1000)]:
                page.set_viewport_size({'width': width, 'height': height})
                page.wait_for_timeout(500)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.locator('#visual').screenshot(path=str(SHOTS / f'{key}-{theme}-{width}.png'))
        assert not errors, errors
        page.close()
        print(f'PASS {key}: encoder/decoder, six distinct inspections, all computed outcomes, phone layout and camera controls.', flush=True)
    browser.close()
