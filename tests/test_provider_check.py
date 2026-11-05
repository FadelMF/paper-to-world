"""Provider diagnostics never send requests unless explicitly enabled."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import check_provider


class ProviderCheckTests(unittest.TestCase):
    def run_check(self, args, reply=None, error=None):
        output = io.StringIO()
        with (
            patch('sys.argv', ['check_provider.py', *args]),
            patch.object(check_provider.llm, 'configured', return_value=True),
            patch.object(check_provider.llm, 'vision_configured', return_value=False),
            patch.object(check_provider.sandbox, 'problem', return_value=None),
            patch.object(check_provider.llm, 'chat_json', return_value=reply, side_effect=error) as send,
            contextlib.redirect_stdout(output),
        ):
            code = check_provider.main()
        return code, json.loads(output.getvalue()), send

    def test_local_probe_does_not_contact_provider(self):
        code, report, send = self.run_check([])
        self.assertEqual(code, 0)
        self.assertEqual(report['text_request'], 'not_tested')
        send.assert_not_called()

    def test_live_probe_uses_adapter_and_redacts_errors(self):
        code, report, send = self.run_check(['--live'], reply={'connection_test': 'ok'})
        self.assertEqual(code, 0)
        self.assertEqual(report['text_request'], 'passed')
        send.assert_called_once()
        code, report, _ = self.run_check(['--live'], error=RuntimeError('secret credential'))
        self.assertEqual(code, 1)
        self.assertNotIn('secret credential', json.dumps(report))
        self.assertIn('RuntimeError', report['text_request'])
