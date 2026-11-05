"""Numerical parity between the Python reference (model.py) and its browser port (model.js).

Both expose run(params, steps): the model state after `steps` timesteps from the initial state.
model.js also exports createModel(params) and advanceModel(state), which the world animates with;
stepping them by hand must give the same state as run().
"""

import json
import math
import re

from app import sandbox

STEPS = (1, 20, 1000)
EDGE_CONTROLS = 4
TIMEOUT = 60
RTOL, ATOL = 1e-3, 1e-6
MAX_REPORTED = 12
IMPURE = re.compile(
    r"^\s*import\b|\bimport\s*\(|\brequire\s*\(|\b(?:document|window|localStorage|process|globalThis)\s*\.|\bfetch\s*\(|\bXMLHttpRequest\b", re.M
)

PYTHON = """import json, runpy, sys
run = runpy.run_path("model.py", run_name="reference")["run"]
states = [run(dict(params), steps) for params, steps in json.loads(sys.argv[1])]
if not all(isinstance(state, dict) for state in states):
    raise TypeError("run(params, steps) must return a dict of state values")
print(json.dumps(states, default=lambda value: value.tolist() if hasattr(value, "tolist") else str(value)))
"""

# model.js is evaluated as a module inside an empty vm context: no process, fetch, require, timers or imports.
NODE = """import vm from 'node:vm';
import { readFileSync } from 'node:fs';
const module = new vm.SourceTextModule(readFileSync('model.js', 'utf8'), { context: vm.createContext({}), identifier: 'model.js' });
await module.link(() => { throw new Error('model.js must not import anything'); });
await module.evaluate({ timeout: 20000 });
const m = module.namespace;
for (const name of ['run', 'createModel', 'advanceModel'])
  if (typeof m[name] !== 'function') { console.error(`model.js must export function ${name}`); process.exit(1); }
console.log(JSON.stringify(JSON.parse(process.argv[1]).map(([params, steps]) => {
  const stepped = m.createModel({ ...params });
  for (let i = 0; i < steps; i++) m.advanceModel(stepped);
  return { run: m.run({ ...params }, steps), stepped };
})));
"""


def parity_cases(plan):
    """Default parameters at several step counts, then each control at its min and max for the longest count."""
    controls = [c for c in plan.get("controls") or [] if all(isinstance(c.get(k), (int, float)) for k in ("min", "max", "default"))]
    base = {c["symbol"]: float(c["default"]) for c in controls}
    cases = [[base, steps] for steps in STEPS]
    for control in controls[:EDGE_CONTROLS]:
        for edge in ("min", "max"):
            cases.append([{**base, control["symbol"]: float(control[edge])}, STEPS[-1]])
    return cases


def reference_states(run_dir, cases):
    code, out, err = sandbox.python(run_dir, ["-c", PYTHON, json.dumps(cases)], TIMEOUT)
    if code != 0:
        raise ValueError("model.py must define run(params, steps) returning the model state as a dict. Calling it failed:\n" + err[-2000:])
    return json.loads(out.strip().splitlines()[-1])


def close(expected, actual):
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(expected) == bool(actual)
    if isinstance(expected, (int, float)):
        if not math.isfinite(expected):
            return actual is None or actual == expected or (isinstance(actual, float) and math.isnan(actual) and math.isnan(expected))
        return isinstance(actual, (int, float)) and abs(actual - expected) <= ATOL + RTOL * abs(expected)
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(map(close, expected, actual))
    return True  # Text and other values are descriptive, not numerical state.


def check_port(run_dir, cases, expected):
    """Raise ValueError listing the differences; return the number of matching cases."""
    impure = IMPURE.search((run_dir / "model.js").read_text())
    if impure:
        raise ValueError(f"model.js must be pure computation with no import, DOM, storage or network (found {impure.group().strip()!r})")
    code, out, err = sandbox.node(run_dir, NODE, [json.dumps(cases)], TIMEOUT)
    if code != 0:
        raise ValueError("model.js failed in Node:\n" + err[-2000:])
    problems = []
    for (params, steps), want, got in zip(cases, expected, json.loads(out.strip().splitlines()[-1]), strict=True):
        where = f"{params} after {steps} steps"
        for key, value in want.items():
            if key not in got["run"]:
                problems.append(f"{where}: run() result is missing {key}")
                continue
            if not close(value, got["run"][key]):
                problems.append(f"{where}: {key} is {value!r} in model.py but {got['run'][key]!r} in model.js")
            if not close(got["run"][key], got["stepped"].get(key)):
                problems.append(f"{where}: createModel + advanceModel gives {key}={got['stepped'].get(key)!r} but run() gives {got['run'][key]!r}")
    if problems:
        raise ValueError(f"{len(problems)} differences from the Python reference:\n" + "\n".join(problems[:MAX_REPORTED]))
    return len(cases)
