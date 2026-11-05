"""Run every browser test script as one suite, against an app server this runner starts.

    .venv/bin/python tests/run_browser_tests.py               # all scripts
    .venv/bin/python tests/run_browser_tests.py living museum # only browser_living.py and browser_museum.py

The server gets a free port and a temporary runs folder, so saved runs stay untouched. Scripts that start their
own servers (live path, build progress, unified, progress/explode) are run as they are. Each script prints its
result line; the runner prints a summary and exits non-zero if any script fails.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness import app_server

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "tests").glob("browser_*.py"))
TIMEOUT = 1200


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main(names):
    scripts = [s for s in SCRIPTS if not names or s.stem.removeprefix("browser_") in names]
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    results = []
    logs = ROOT / "artifacts" / "browser-logs"
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as runs:
        env = {
            **os.environ,
            "PAPER_RUNS_DIR": runs,
            "APP_URL": url,
            "PAPER_ENV": "development",
            "PAPER_PRIVATE_SESSIONS": "0",
            "PAPER_ACCESS_TOKEN": "",
            "PAPER_RATE_LIMIT_PER_HOUR": "0",
        }
        with app_server(port, env, subprocess.DEVNULL):
            for script in scripts:
                started = time.monotonic()
                try:
                    done = subprocess.run([sys.executable, str(script)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT)
                    code, output = done.returncode, (done.stdout + done.stderr).strip()
                except subprocess.TimeoutExpired:
                    code, output = None, f"timed out after {TIMEOUT} s"
                (logs / (script.stem + ".log")).write_text(output + "\n")
                last = output.splitlines()[-1] if output else ""
                results.append((script.stem, code == 0, round(time.monotonic() - started)))
                print(f"{'PASS' if code == 0 else 'FAIL'} {script.stem} ({results[-1][2]} s): {last[:160]}", flush=True)
                if code != 0:
                    print("\n".join(output.splitlines()[-20:]), flush=True)
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} browser scripts passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:])))
