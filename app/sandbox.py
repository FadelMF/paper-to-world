"""Run model-written code (model.py, model.js) isolated from the server.

PAPER_SANDBOX chooses how:
- "landlock" (the default, "auto"): kernel confinement without root (app/confine.py). Landlock lets the process
  read only the system and the language runtimes and write only the run’s .scratch folder, with no TCP; seccomp refuses
  network sockets and io_uring. Neither can be lifted by the code. Needs Linux 6.7+ with Landlock (x86_64).
- "guard": for a trusted development machine without Landlock, chosen explicitly. Python runs under an audit
  hook that refuses network, subprocesses, native code and files outside the run folder; Node runs with
  --permission, and model.js in an empty vm context with no process, fetch, require or imports.

The guard and the vm context also run inside Landlock, as a second layer. Every run gets a timeout, a memory
cap, its own process group (killed afterwards) and none of the server's environment (no API key).
"""

import contextlib
import os
import resource
import shutil
import signal
import subprocess
import sys
import sysconfig
from functools import lru_cache
from pathlib import Path

from app import confine

MEMORY_BYTES = 2 * 1024**3
BACKEND = os.getenv("PAPER_SANDBOX", "auto")

GUARD = r"""
import os, sys, sysconfig
WORK = os.path.realpath(os.getcwd())
SCRATCH = os.path.join(WORK, ".scratch")
LIBRARIES = {sys.prefix, sys.base_prefix, sys.exec_prefix, *sysconfig.get_paths().values()}
READABLE = tuple(os.path.realpath(p) for p in LIBRARIES if p) + (WORK,)
BLOCKED = ("socket.", "subprocess.", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
           "os.kill", "os.killpg", "ctypes.", "pty.", "webbrowser.", "urllib.Request", "http.client.", "ftplib.",
           "smtplib.", "telnetlib.", "imaplib.", "poplib.", "nntplib.", "sys.addaudithook")
WRITES = ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.link", "os.symlink",
          "os.truncate", "os.utime", "shutil.rmtree", "shutil.move", "shutil.copyfile", "os.chdir", "os.chroot")
LISTS = ("os.listdir", "os.scandir", "glob.glob", "os.walk")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

def inside(path, roots):
    if isinstance(path, int):
        return True
    path = os.path.realpath(os.fsdecode(path))
    return any(path == root or path.startswith(root + os.sep) for root in roots)

# The scientific libraries load native code through ctypes as they import, so they are imported before the guard.
for name in ("numpy", "scipy", "scipy.integrate", "scipy.optimize", "scipy.signal", "scipy.sparse", "scipy.linalg",
             "scipy.stats", "scipy.special", "scipy.interpolate", "scipy.fft", "scipy.ndimage", "scipy.spatial"):
    try:
        __import__(name)
    except ImportError:
        pass

def guard(event, args):
    if event.startswith(BLOCKED) or (event == "import" and args[0] in ("cffi", "_cffi_backend")):
        raise PermissionError(f"sandbox: {event} is not allowed in the reference model")
    if event == "open":
        path, mode, flags = args
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and flags & WRITE_FLAGS)
        if not inside(path, (SCRATCH,) if writing else READABLE):
            raise PermissionError(f"sandbox: {'writing' if writing else 'reading'} {path} is not allowed; temporary output belongs in .scratch")
    elif event in WRITES and args and (not inside(args[0], (SCRATCH,)) or
         (event in ("os.rename", "os.link", "os.symlink", "shutil.move", "shutil.copyfile") and len(args)>1 and not inside(args[1], (SCRATCH,)))):
        raise PermissionError(f"sandbox: {event} outside .scratch is not allowed")
    elif event in LISTS and args and args[0] is not None and not inside(args[0], READABLE):
        raise PermissionError(f"sandbox: listing {args[0]} is not allowed")

sys.addaudithook(guard)
if sys.argv[1] == "-c":
    code, sys.argv = sys.argv[2], ["<harness>", *sys.argv[3:]]
    exec(compile(code, "<harness>", "exec"), {"__name__": "__main__"})
else:
    import runpy
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name="__main__")
"""


def python_roots():
    """Folders the reference model may read: the interpreter's and the installed libraries'."""
    paths = {sys.prefix, sys.base_prefix, sys.exec_prefix, *sysconfig.get_paths().values()}
    return sorted(p for p in paths if p and os.path.isdir(p))


def limit_memory():
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))


def problem():
    """Why model-written code cannot run here, in words for the learner, or None when it can."""
    node_path = shutil.which("node")
    if not node_path:
        return "Live building is switched off: this server has no Node.js to check the browser simulation."
    if issue := runtime_problem(node_path):
        return issue
    try:
        backend()
    except RuntimeError:
        return "Live building is switched off: this server cannot isolate model-written code (it needs Linux 6.7+ with Landlock)."
    return None


@lru_cache(maxsize=4)
def runtime_problem(node_path):
    try:
        result = subprocess.run([node_path, "--permission", "-e", ""], capture_output=True, timeout=5)
        if result.returncode:
            return "Live building requires Node.js 22.13+ with the permission model enabled."
        probe = "from pathlib import Path; from playwright.sync_api import sync_playwright\nwith sync_playwright() as p: print(int(Path(p.chromium.executable_path).is_file()))"
        result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=10)
        if result.returncode or result.stdout.strip() != "1":
            return "Live building requires Chromium. Install it with: python -m playwright install chromium."
    except (OSError, subprocess.TimeoutExpired):
        return "Live building could not verify this server's Node.js and Chromium installation."
    return None


def backend():
    if BACKEND in ("auto", "landlock"):
        if not confine.available():
            raise RuntimeError(
                "Model-written code needs kernel isolation: Linux 6.7+ with Landlock enabled (x86_64). "
                "On a trusted development machine without it, set PAPER_SANDBOX=guard."
            )
        return "landlock"
    if BACKEND == "guard":
        return "guard"
    raise RuntimeError(f"PAPER_SANDBOX must be auto, landlock or guard, not {BACKEND!r}")


SYSTEM = [
    "/usr",
    "/lib",
    "/lib64",
    "/bin",
    "/etc/ld.so.cache",
    "/etc/localtime",
    "/etc/alternatives",
    "/etc/ssl",
    "/dev/urandom",
    "/sys/devices/system/cpu",
    "/proc/self",
]


def node_root():
    node_path = shutil.which("node")
    return str(Path(node_path).resolve().parents[1]) if node_path else "/usr"


def code_rules(cwd):
    """Landlock rules for model-written code: read the system and runtimes, write only the run’s .scratch folder."""
    return [(path, confine.READ) for path in [*SYSTEM, *python_roots(), node_root(), str(cwd)]] + [
        (str(Path(cwd) / ".scratch"), confine.WRITE),
        ("/dev/null", confine.WRITE),
    ]


def preexec(cwd):
    (Path(cwd) / ".scratch").mkdir(exist_ok=True, mode=0o700)
    rules = code_rules(Path(cwd).resolve()) if backend() == "landlock" else None

    def setup():
        limit_memory()
        if rules:
            confine.confine(rules)

    return setup


def run(command, cwd, timeout, env=None, setup=None, stdin=None):
    """Return (returncode, stdout, stderr); returncode is None after a timeout. The command gets its own process
    group, which is killed when it finishes or times out, so nothing it started outlives it."""
    env = env or {"PATH": os.environ.get("PATH", ""), "HOME": str(cwd), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        preexec_fn=setup or preexec(cwd),
        start_new_session=True,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        try:
            out, err = process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(process)
            out, _ = process.communicate()
            return None, out, f"The script did not finish within {timeout} seconds. Make it faster: fewer steps or a shorter simulated time."
        return process.returncode, out, err
    finally:
        # Canceling a worker must also stop its reference/Node/browser process group.
        kill_group(process)


def kill_group(process):
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


def python(run_dir, args, timeout):
    """Run `python model.py` or `python -c CODE ARGS` in the run folder under the guard."""
    return run([sys.executable, "-I", "-c", GUARD, *args], run_dir, timeout)


def node(run_dir, code, args, timeout):
    """Run an ES module `code` with Node in the run folder: file reads only there, no child processes."""
    folder = str(Path(run_dir).resolve())
    node_path = shutil.which("node")
    if not node_path:
        raise RuntimeError("Node.js is required to check the browser model; install it on the server.")
    return run(
        [node_path, "--permission", f"--allow-fs-read={folder}", "--experimental-vm-modules", "--no-warnings", "--input-type=module", "-e", code, *args],
        run_dir,
        timeout,
    )
