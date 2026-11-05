"""Shared helpers for the browser test scripts: start and stop servers, collect page errors."""

import contextlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wait_for(url, seconds=30):
    """Return once the URL answers at all (an HTTP error status counts as started)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"{url} did not start")


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@contextlib.contextmanager
def serving(command, url, env, log):
    """Run a server command until the block ends; wait until it answers at url first."""
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
    try:
        wait_for(url)
        yield process
    finally:
        stop(process)


def app_server(port, env, log):
    """Serve app.main:app on 127.0.0.1:port with the given environment."""
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    return serving(command, f"http://127.0.0.1:{port}/api/config", env, log)


def page_errors(page, console=False):
    """Collect uncaught page errors (and console errors, if asked) into the returned list."""
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    if console:
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    return errors


def themed_page(browser, width, height, theme):
    """Open a page in a new context of the given size, with the app's light or dark theme already chosen."""
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_init_script(f"localStorage.setItem('ptw-theme', {json.dumps(json.dumps(theme))})")
    return context.new_page()


def start_prepared_example(page, base, key):
    """Exercise the prepared build endpoint without adding generation controls to the demo UI."""
    sample = ROOT / 'static' / {'2d': 'demo', '3d': 'demo3d', 'attention2d': 'attention2d', 'attention3d': 'attention3d'}[key]
    response = page.request.post(
        base + '/api/runs',
        multipart={
            'demo': 'true',
            'example_id': key,
            'file': {'name': 'example.pdf', 'mimeType': 'application/pdf', 'buffer': (sample / 'paper.pdf').read_bytes()},
        },
    )
    if not response.ok:
        raise RuntimeError(response.text())
    page.goto(base + '/build/' + response.json()['id'])
