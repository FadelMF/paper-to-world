"""One cancellable OS process per document."""

import os
import signal
import sys
import threading
from pathlib import Path

from app import store
from app.pipeline import read_json, run_pipeline


def terminate(signum, frame):
    raise SystemExit(128 + signum)


def watch_parent(expected_pid):
    """Stop after server exit without depending on the lifetime of its spawning thread."""
    if os.getppid() != expected_pid:
        raise SystemExit(143)

    def monitor():
        tick = threading.Event()
        while not tick.wait(1):
            if os.getppid() != expected_pid:
                os.kill(os.getpid(), signal.SIGTERM)
                return

    threading.Thread(target=monitor, daemon=True).start()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    if len(sys.argv) > 2:
        watch_parent(int(sys.argv[2]))
    directory = Path(sys.argv[1])
    store.OWNER.set(store.owner_for(directory.name, directory.parent))
    store.BUDGET_RUN.set(directory.name)
    import resource

    memory = int(os.getenv("PAPER_WORKER_MEMORY_MB", "3072")) * 1024 * 1024
    cpu = int(os.getenv("PAPER_WORKER_CPU_SECONDS", "600"))
    resource.setrlimit(resource.RLIMIT_AS, (memory, resource.getrlimit(resource.RLIMIT_AS)[1]))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    signal.signal(signal.SIGALRM, terminate)
    signal.alarm(int(os.getenv("PAPER_WORKER_WALL_SECONDS", "3600")))
    source = read_json(directory, "source.json")
    demo = source.get("demo", False)
    if demo:
        from app.demo import DemoProvider

        run_pipeline(directory, provider=DemoProvider(source.get("example", "2d")), demo=True)
    else:
        run_pipeline(directory)
