"""Opaque world frames cannot use the parent DOM, cookies, storage or application API."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
from harness import app_server
from run_browser_tests import free_port

from app import pipeline, store


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for ident, sample in [('flat', 'demo'), ('spatial', 'demo3d'), ('hostile', 'demo')]:
            folder = root / ident
            shutil.copytree(ROOT / 'static' / sample, folder)
            status = pipeline.initial_status()
            status.update(done=True, error=None)
            pipeline.write_json(folder, 'status.json', status)
            pipeline.write_json(folder, 'source.json', {})
        (root / 'hostile' / 'world.js').write_text('''
export const dimensionality=2;
const result={};
export async function init(el){
 el.textContent='Isolation probe';
 for(const [name,fn] of Object.entries({parent:()=>parent.document.body.dataset.compromised='yes',cookie:()=>document.cookie,storage:()=>localStorage.getItem('secret'),top:()=>top.location.href='/compromised'})){
   try{fn();result[name]='allowed';}catch{result[name]='blocked';}
 }
 try{await fetch('/api/runs',{credentials:'include'});result.api='allowed';}catch{result.api='blocked';}
 window.probe=result;
}
export function getState(){return result;}
export function setParams(){} export function setLesson(){} export function highlight(){}
export function play(){} export function pause(){} export function step(){} export function onObjectClick(){}
''')
        port = free_port()
        base = f'http://127.0.0.1:{port}'
        env = {**os.environ, 'PAPER_RUNS_DIR': tmp, 'PAPER_PRIVATE_SESSIONS': '1', 'PAPER_ACCESS_TOKEN': '', 'PAPER_ENV': 'development'}
        with (root / 'server.log').open('w') as log, app_server(port, env, log), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            page.goto(base)
            token = next(c['value'] for c in context.cookies() if c['name'] == 'paper_session')
            owner, _ = store.session(token, root)
            for ident in ('flat', 'spatial', 'hostile'):
                store.assign(ident, owner, root)
                page.goto(base + '/learn/' + ident)
                page.wait_for_selector('#workspace:not([hidden])', timeout=45000)
                page.wait_for_selector('.isolated-world', timeout=45000)
                page.wait_for_selector('#loading', state='hidden', timeout=45000)
                frame = page.frame_locator('.isolated-world')
                if ident == 'hostile':
                    frame.get_by_text('Isolation probe').wait_for()
                    inner = next(f for f in page.frames if f != page.main_frame)
                    inner.wait_for_function('window.probe?.api')
                    result = inner.evaluate('window.probe')
                    assert set(result.values()) == {'blocked'}, result
                    assert page.evaluate('document.body.dataset.compromised') is None
                    assert page.url.endswith('/hostile')
                else:
                    frame.locator('canvas').first.wait_for(timeout=45000)
                    page.locator('#next').click()
                    page.wait_for_timeout(800)
                    assert not page.locator('#workspace').is_hidden(), page.locator('#loading-message').inner_text()
                assert page.locator('.isolated-world').get_attribute('sandbox') == 'allow-scripts'
            stranger = browser.new_context()
            response = stranger.request.get(base + '/api/runs/hostile')
            assert response.status == 404
            assert stranger.request.get(base + '/api/runs').json() == []
            browser.close()
    print(
        'PASS: real 2D/3D worlds render in opaque frames; hostile DOM, cookie, storage, navigation and API probes are blocked; another session cannot access runs.'
    )


if __name__ == '__main__':
    main()
