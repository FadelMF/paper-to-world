"""Neuron lessons explain a causal mechanism and reproduce actual first-second counts."""

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
    for key, route in [('demo', '/demo'), ('demo3d', '/demo/3d')]:
        lessons = json.loads((ROOT / 'static' / key / 'lessons.json').read_text())
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = page_errors(page, console=True)
        page.goto(BASE + route)
        expect(page.locator('#workspace')).to_be_visible()
        for index, lesson in enumerate(lessons):
            page.locator('#lesson-path button').nth(index).click()
            expect(page.locator('.neuron-metrics')).to_be_visible()
            expect(page.locator('.lesson-instructions')).to_contain_text(lesson['learning']['observe'])
            for symbol, value in lesson['learning']['test_params'].items():
                page.locator('#control-' + symbol).fill(str(value))
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
            page.evaluate("document.activeElement?.blur(); document.getElementById('reading').scrollTop=0; window.scrollTo(0,0)")
            page.screenshot(path=str(SHOTS / f'{key}-{index + 1}.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        page.wait_for_timeout(800)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.locator('#visual').screenshot(path=str(SHOTS / f'{key}-phone.png'))
        assert not errors, errors
        page.close()
        print(f'PASS {key}: four causal lessons, resting/equilibrium/threshold outcomes and 33/63 first-second spike counts.', flush=True)
    browser.close()
