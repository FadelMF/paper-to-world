"""Optional account signup/login/logout and mobile layout, without a model or email service."""

import os
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]
from harness import app_server
from run_browser_tests import free_port

with tempfile.TemporaryDirectory() as tmp:
    port = free_port()
    base = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'PAPER_RUNS_DIR': tmp, 'PAPER_PRIVATE_SESSIONS': '1', 'PAPER_ACCESS_TOKEN': '', 'PAPER_ENV': 'development'}
    with (Path(tmp) / 'server.log').open('w') as log, app_server(port, env, log), sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={'width': 390, 'height': 844})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base + '/worlds')
        page.get_by_role('link', name='Manage your account').click()
        expect(page.locator('#account-form')).to_be_visible()
        page.get_by_label('Username', exact=True).fill('researcher')
        page.get_by_label('Password', exact=True).fill('testing-account-password')
        page.get_by_role('button', name='Create account', exact=True).click()
        expect(page.locator('#account-status')).to_have_text('Signed in as researcher.')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        other = browser.new_context()
        another = other.new_page()
        another.goto(base + '/account')
        another.get_by_label('Username', exact=True).fill('researcher')
        another.get_by_label('Password', exact=True).fill('testing-account-password')
        another.get_by_role('button', name='Sign in', exact=True).click()
        expect(another.locator('#account-status')).to_have_text('Signed in as researcher.')
        another.get_by_role('button', name='Sign out', exact=True).click()
        expect(another.locator('#account-form')).to_be_visible()
        assert not errors, errors
        browser.close()
print('PASS: optional signup, cross-browser login and logout work; the account page fits a phone.')
