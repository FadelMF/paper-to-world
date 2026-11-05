"""Model-written code runs isolated: no network, no files outside the run folder, no subprocesses, no native code."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import confine, render_check, sandbox
from app.parity import NODE

ATTACKS = """import json, os, socket, numpy, scipy.integrate
results = {}
def attempt(name, action):
    try:
        action()
        results[name] = "allowed"
    except Exception as error:
        results[name] = type(error).__name__
attempt("network", lambda: socket.create_connection(("1.1.1.1", 80), timeout=2))
attempt("dns", lambda: socket.getaddrinfo("example.com", 80))
attempt("read_outside", lambda: open(OUTSIDE).read())
attempt("list_outside", lambda: os.listdir(os.path.dirname(OUTSIDE)))
attempt("write_outside", lambda: open(OUTSIDE + ".new", "w").write("x"))
attempt("delete_outside", lambda: os.remove(OUTSIDE))
attempt("subprocess", lambda: __import__("subprocess").run(["id"]))
attempt("shell", lambda: os.system("id"))
attempt("native_code", lambda: __import__("ctypes").CDLL(None))
attempt("environment", lambda: os.environ["LLM_API_KEY"])
attempt("write_scratch", lambda: open(".scratch/notes.txt", "w").write("x"))
attempt("overwrite_status", lambda: open("status.json", "w").write("fake ready"))
attempt("overwrite_world", lambda: open("world.js", "w").write("fake world"))
attempt("science", lambda: scipy.integrate.solve_ivp(lambda t, y: -y, (0, 1), [1.0]))
print(json.dumps({"metrics": results}))
"""


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outside = Path(self.tmp.name) / "secret.txt"
        self.outside.write_text("server secret")
        self.folder = Path(self.tmp.name) / "run"
        self.folder.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reference_model_cannot_reach_outside_its_run_folder(self):
        (self.folder / "model.py").write_text(f"OUTSIDE = {str(self.outside)!r}\n" + ATTACKS)
        with patch.dict(os.environ, {"LLM_API_KEY": "secret"}):
            code, out, err = sandbox.python(self.folder, ["model.py"], 60)
        self.assertEqual(code, 0, err)
        results = json.loads(out.strip().splitlines()[-1])["metrics"]
        allowed = {name for name, result in results.items() if result == "allowed"}
        self.assertEqual(allowed, {"write_scratch", "science"}, results)
        self.assertEqual(self.outside.read_text(), "server secret")
        self.assertFalse(Path(str(self.outside) + ".new").exists())

    def test_browser_model_gets_no_host_objects(self):
        for source, words in [
            ("export const run = () => process.exit(3);", "process is not defined"),
            ("const f = globalThis['fe' + 'tch']; export const run = () => f('http://example.com');", "f is not a function"),
            (
                "export const DT = 1; export function createModel(){ return {}; } export function advanceModel(s){ return s; }"
                " export function run(){ return eval('require')('fs'); }",
                "ReferenceError",
            ),
            ("import fs from 'node:fs'; export const run = 1;", "must not import anything"),
        ]:
            with self.subTest(words=words):
                (self.folder / "model.js").write_text(
                    source + "\nexport function createModel(){ return {}; } export function advanceModel(s){ return s; }"
                    if "createModel" not in source
                    else source
                )
                code, _out, err = sandbox.node(self.folder, NODE, [json.dumps([[{}, 1]])], 30)
                self.assertNotEqual(code, 0)
                self.assertIn(words, err)

    def test_node_cannot_read_outside_its_run_folder(self):
        code, _out, err = sandbox.node(self.folder, f"import {{ readFileSync }} from 'node:fs'; readFileSync({json.dumps(str(self.outside))});", [], 30)
        self.assertNotEqual(code, 0)
        self.assertIn("ERR_ACCESS_DENIED", err)

    @unittest.skipUnless(confine.available(), "Landlock with TCP rules is not available here")
    def test_kernel_confinement_holds_without_the_interpreter_guard(self):
        (self.folder / "model.py").write_text(f"OUTSIDE = {str(self.outside)!r}\n" + ATTACKS)
        with patch.object(sandbox, "BACKEND", "landlock"):
            _code, out, _err = sandbox.run([sys.executable, "-I", "model.py"], self.folder, 60)  # no audit hook: only the kernel
        results = json.loads(out.strip().splitlines()[-1])["metrics"]
        for escape in ["network", "dns", "read_outside", "list_outside", "write_outside", "delete_outside", "overwrite_status", "overwrite_world"]:
            self.assertNotEqual(results[escape], "allowed", escape)
        self.assertEqual(self.outside.read_text(), "server secret")

    @unittest.skipUnless(confine.available(), "Landlock with TCP rules is not available here")
    def test_the_browser_process_cannot_read_the_project_or_open_a_socket(self):
        (self.folder / "render").mkdir()
        probe = f"""
import socket
def attempt(action):
    try:
        action(); return 'allowed'
    except OSError as error:
        return error.__class__.__name__ + str(error.errno)
print(attempt(lambda: open({str(render_check.ROOT / ".env.example")!r}).read()))
print(attempt(lambda: open({str(render_check.ROOT / "app" / "render_check.py")!r}).read()))
print(attempt(lambda: socket.create_connection(('127.0.0.1', 80), timeout=2)))
print(attempt(lambda: socket.create_connection(('127.0.0.1', 443), timeout=2)))
print(attempt(lambda: open({str(self.folder / "render" / "shot.png")!r}, 'w').write('x')))
print(attempt(lambda: open({str(self.folder / "world.js")!r}, 'w').write('x')))
"""
        rules = render_check.browser_rules(self.folder.resolve())
        result = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=60, preexec_fn=lambda: confine.confine(rules))
        env_file, app_code, port_80, port_443, render_write, run_write = result.stdout.split()
        self.assertTrue(env_file.startswith("PermissionError"), result.stdout)
        self.assertEqual((app_code, render_write), ("allowed", "allowed"))
        self.assertEqual(port_80, "PermissionError1")  # seccomp refuses to create the socket at all
        self.assertEqual(port_443, "PermissionError1")  # no network at all: libraries are served locally
        self.assertTrue(run_write.startswith("PermissionError"))

    def test_the_server_says_when_it_cannot_isolate_model_code(self):
        from fastapi.testclient import TestClient

        from app import main

        with (
            patch.object(main, "configured", return_value=True),
            patch.object(confine, "available", return_value=False),
            patch.object(sandbox, "BACKEND", "auto"),
            TestClient(main.app) as client,
        ):
            config = client.get("/api/config").json()
            refused = client.post("/api/runs", data={"arxiv_id": "1706.03762"})
        self.assertFalse(config["generation_available"])
        self.assertIn("Landlock", config["problem"])
        self.assertEqual(refused.status_code, 503)
        self.assertIn("Landlock", refused.json()["detail"])

    def test_kernel_isolation_is_required_unless_the_guard_is_chosen(self):
        with patch.object(confine, "available", return_value=False):
            for setting in ("auto", "landlock"):
                with self.subTest(setting=setting), patch.object(sandbox, "BACKEND", setting), self.assertRaisesRegex(RuntimeError, "PAPER_SANDBOX=guard"):
                    sandbox.backend()
            with patch.object(sandbox, "BACKEND", "guard"):
                self.assertEqual(sandbox.backend(), "guard")
                self.assertEqual(sandbox.python(self.folder, ["-c", "print(1)"], 30)[1].strip(), "1")
        with patch.object(sandbox, "BACKEND", "docker"), self.assertRaisesRegex(RuntimeError, "auto, landlock or guard"):
            sandbox.backend()


if __name__ == "__main__":
    unittest.main()
