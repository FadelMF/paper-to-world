"""Audit the exact vendored npm versions without adding an npm runtime to the app."""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
versions = json.loads((ROOT / 'static/vendor/versions.json').read_text())
with tempfile.TemporaryDirectory(prefix='paper-vendor-audit-') as tmp:
    path = Path(tmp)
    (path / 'package.json').write_text(
        json.dumps(
            {'name': 'paper-to-world-vendor-audit', 'version': '1.0.0', 'private': True, 'dependencies': {name: versions[name] for name in ('three', 'katex')}}
        )
    )
    subprocess.run(['npm', 'install', '--package-lock-only', '--ignore-scripts', '--no-fund'], cwd=path, check=True)
    subprocess.run(['npm', 'audit', '--omit=dev'], cwd=path, check=True)
