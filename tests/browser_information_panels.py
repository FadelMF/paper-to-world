"""Structured information and in-page dropdowns: actual values, keyboard and mobile bounds."""

import os
from pathlib import Path

from harness import page_errors
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
SHOTS = Path('artifacts/information-layout')
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = page_errors(page, console=True)
    page.goto(BASE + '/demo/attention/2d')
    trigger = page.locator('#control-source-trigger')
    trigger.click()
    expect(page.locator('#control-source-options')).to_be_visible()
    page.wait_for_timeout(300)
    page.screenshot(path=str(SHOTS / 'dropdown-desktop.png'))
    page.locator('#control-source-options [role=option]').nth(1).click()
    expect(trigger).to_contain_text('I like cats')
    page.evaluate("async()=>window.checked=await import('/assets/attention2d/world.js')")
    assert page.evaluate('checked.getState().source') == 1
    trigger.focus()
    page.keyboard.press('Enter')
    page.keyboard.press('Home')
    page.keyboard.press('Enter')
    expect(trigger).to_contain_text('I see cats')
    trigger.click()
    page.keyboard.press('Escape')
    expect(trigger).to_have_attribute('aria-expanded', 'false')
    page.locator('[data-info="model-setup"] summary').click()
    page.locator('#control-input_gain').fill('150')
    assert page.locator('[data-info="model-setup"]').get_attribute('open') is not None
    page.locator('.transformer-detail').screenshot(path=str(SHOTS / 'overview-expanded.png'))
    for index in range(6):
        page.locator('#lesson-path button').nth(index).click()
        expect(page.locator('.info-metrics')).to_be_visible()
        expect(page.locator('.info-disclosure').first).to_be_visible()
        page.locator('.transformer-detail').screenshot(path=str(SHOTS / f'lesson-{index + 1}.png'))
    page.locator('#lesson-path button').first.click()
    page.set_viewport_size({'width': 390, 'height': 844})
    trigger.click()
    expect(page.locator('#control-source-options')).to_be_visible()
    page.screenshot(path=str(SHOTS / 'dropdown-phone.png'))
    rect = page.locator('#control-source-options').bounding_box()
    assert rect['x'] >= 0 and rect['x'] + rect['width'] <= 390
    page.keyboard.press('Escape')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.goto(BASE + '/demo')
    page.locator('#workspace').wait_for(state='visible')
    page.locator('.specimen-controls button', has_text='Anatomy').click()
    anatomy = page.locator('.anatomy-inspector .app-select-trigger')
    anatomy.click()
    expect(page.locator('.app-select-options:not([hidden])')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('.anatomy-inspector')).to_be_visible()
    anatomy.click()
    page.keyboard.press('End')
    page.keyboard.press('Enter')
    expect(anatomy).to_contain_text('Terminals')
    page.screenshot(path=str(SHOTS / 'anatomy-phone.png'))
    assert not errors, errors
    browser.close()
print('PASS: six structured panels, custom dropdown mouse/keyboard/Escape, model updates, persistent disclosures, mobile bounds and anatomy picker.')
