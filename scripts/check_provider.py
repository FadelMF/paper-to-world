"""Check local configuration; --live sends small, billable text and optional image requests."""

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from app import llm, sandbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Make billable requests using the configured application adapter.')
    args = parser.parse_args()
    report = {
        'text_configured': bool(llm.configured()),
        'vision_configured': bool(llm.vision_configured()),
        'runtime_problem': sandbox.problem(),
        'text_request': 'not_tested',
        'image_request': 'not_tested',
    }
    failed = not report['text_configured'] or bool(report['runtime_problem'])
    if args.live and report['text_configured']:
        try:
            reply = llm.chat_json('Follow the requested JSON format.', 'Return {"connection_test": "ok"}.')
            if reply.get('connection_test') != 'ok':
                raise ValueError('Unexpected test response')
            report['text_request'] = 'passed'
        except Exception as error:
            # Provider exception messages can contain URLs, echoed prompts, or credentials.
            report['text_request'] = f'failed ({type(error).__name__})'
            failed = True
        if report['vision_configured']:
            image = io.BytesIO()
            Image.new('RGB', (64, 64), (255, 0, 0)).save(image, format='PNG')
            try:
                reply = llm.chat_json('Identify the image color.', 'Return {"color": "<English lowercase color>"}.', images=[image.getvalue()])
                if reply.get('color') != 'red':
                    raise ValueError('Image test did not identify red')
                report['image_request'] = 'passed'
            except Exception as error:
                report['image_request'] = f'failed ({type(error).__name__})'
                failed = True
    print(json.dumps(report, indent=2))
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
