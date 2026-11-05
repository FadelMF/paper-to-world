"""Create a private offline backup. Stop the production service first; restore only trusted backups."""

import argparse
import fcntl
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import RUNS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='New backup directory outside the runs directory')
    args = parser.parse_args()
    target = args.destination.resolve()
    if target.exists() or target.is_relative_to(RUNS.resolve()):
        parser.error('Use a new destination outside the runs directory.')
    os.umask(0o077)
    target.parent.mkdir(parents=True, exist_ok=True)
    with (RUNS / '.server.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Stop the server before backing up.')
        with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
            staging = Path(tmp) / 'snapshot'
            shutil.copytree(RUNS, staging, ignore=shutil.ignore_patterns('.server.lock', '.state.sqlite3*'), symlinks=True)
            source = RUNS / '.state.sqlite3'
            if source.exists():
                with sqlite3.connect(source) as src, sqlite3.connect(staging / source.name) as dst:
                    src.backup(dst)
            staging.rename(target)
    print(f'Backup saved to {target}. Keep it private; it contains documents, session hashes and ownership records.')


if __name__ == '__main__':
    main()
