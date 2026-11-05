"""Retest authored teaching examples through the full pipeline, including real browser outcomes.

    .venv/bin/python scripts/check_teaching_examples.py 2d 3d attention2d attention3d

Stage answers are local. This tests workflow and computations, not a live model provider.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.demo import SAMPLES, DemoProvider
from app.pipeline import initial_status, run_pipeline, write_json


class CheckedProvider(DemoProvider):
    prepared = False


def main(keys):
    for key in keys:
        if key not in SAMPLES:
            raise SystemExit(f'Unknown example {key}')
        sample = SAMPLES[key]
        run = ROOT / 'artifacts' / ('teaching-pipeline-' + key)
        if run.exists():
            shutil.rmtree(run)
        run.mkdir(parents=True)
        shutil.copy(sample / 'paper.pdf', run / 'paper.pdf')
        write_json(run, 'source.json', {})
        write_json(run, 'status.json', initial_status())
        run_pipeline(run, provider=CheckedProvider(key))
        status = json.loads((run / 'status.json').read_text())
        if status['error']:
            print((run / 'debug.log').read_text(), flush=True)
            raise SystemExit(f'{key} failed: {status["error"]}')
        coverage = json.loads((run / 'coverage.json').read_text())
        print(f'PASS {key}: {len(coverage["topics"])} topics mapped; model, parity, teaching outcomes and desktop/phone renders passed.', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:] or list(SAMPLES))
