"""Adversarial API requests and publication failures found during the production audit."""

import asyncio
import copy
import io
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from app import main, pdf, pipeline, sandbox, worker
from app.demo import SAMPLE, DemoProvider
from app.errors import PublicError
from app.quality import require_validation
from app.security import RequestBodyLimit, own_run_directory, validate_deployment


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(main, 'RUNS', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.run_dir = self.root / 'paper'
        self.run_dir.mkdir()
        pipeline.write_json(self.run_dir, 'source.json', {})
        pipeline.write_json(self.run_dir, 'status.json', pipeline.initial_status())
        self.client = TestClient(main.app)

    def test_internal_files_and_symlink_escapes_are_not_served(self):
        for name in ('debug.log', 'source.json', 'usage.json', 'injected.html'):
            (self.run_dir / name).write_text('private')
            self.assertEqual(self.client.get(f'/api/runs/paper/files/{name}').status_code, 404)
        (self.root / 'secret').write_text('private')
        (self.run_dir / 'world.js').symlink_to(self.root / 'secret')
        self.assertEqual(self.client.get('/api/runs/paper/files/world.js').status_code, 404)
        (self.run_dir / 'world.js').unlink()
        (self.run_dir / 'world.js').write_text('export const x=1;')
        reply = self.client.get('/api/runs/paper/files/world.js')
        self.assertEqual(reply.status_code, 200)
        self.assertIn('javascript', reply.headers['content-type'])
        self.assertEqual(reply.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(reply.headers['cache-control'], 'no-store')

    def test_tutor_bounds_and_not_ready_state_do_not_call_provider(self):
        with patch.object(main.agents, 'ask') as ask:
            for question in ('', '   ', 'x' * 2001):
                self.assertEqual(self.client.post('/api/runs/paper/ask', json={'question': question}).status_code, 422)
            self.assertEqual(self.client.post('/api/runs/paper/ask', json={'question': 'Why?'}).status_code, 409)
        ask.assert_not_called()

    def test_full_queue_rejects_before_creating_run_or_launching_worker(self):
        before = set(self.root.iterdir())
        with (
            patch.object(main, 'MAX_PENDING_RUNS', 1),
            patch.object(main, 'QUEUE', [self.run_dir]),
            patch.object(main, 'WORKERS', {}),
            patch.object(main, 'configured', return_value=True),
            patch.object(main, 'launch_run') as launch,
        ):
            response = self.client.post('/api/runs', data={'arxiv_id': '1706.03762'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['retry-after'], '30')
        self.assertEqual(set(self.root.iterdir()), before)
        launch.assert_not_called()

    def test_tutor_capacity_is_released_after_provider_failure(self):
        status = pipeline.initial_status()
        status.update(done=True, error=None)
        pipeline.write_json(self.run_dir, 'status.json', status)
        for name in ('pages', 'analysis', 'plan', 'validation'):
            pipeline.write_json(self.run_dir, f'{name}.json', {})
        slots = threading.BoundedSemaphore(1)
        with patch.object(main, 'TUTOR_SLOTS', slots), patch.object(main.agents, 'ask', side_effect=RuntimeError('provider offline')) as ask:
            slots.acquire()
            response = self.client.post('/api/runs/paper/ask', json={'question': 'Why?'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers['retry-after'], '10')
            ask.assert_not_called()
            slots.release()
            self.assertEqual(self.client.post('/api/runs/paper/ask', json={'question': 'Why?'}).status_code, 503)
            self.assertTrue(slots.acquire(blocking=False))
            slots.release()

    def test_upload_read_is_bounded_even_with_misleading_length(self):
        with patch.object(main, 'MAX_UPLOAD_BYTES', 32), patch.object(main, 'launch_run') as launch:
            reply = self.client.post('/api/runs', files={'file': ('paper.pdf', b'%PDF-' + b'x' * 64)})
        self.assertEqual(reply.status_code, 413)
        launch.assert_not_called()

    def test_cross_site_posts_are_rejected_and_bearer_overrides_stale_cookie(self):
        reply = self.client.post('/api/runs', data={'arxiv_id': '1706.03762'}, headers={'Origin': 'https://other.example'})
        self.assertEqual(reply.status_code, 403)
        with patch.object(main, 'ACCESS_TOKEN', 'new-secret'):
            self.client.cookies.set('paper_token', 'old-secret')
            reply = self.client.get('/api/config', headers={'Authorization': 'bearer new-secret'})
            self.assertEqual(reply.status_code, 200)

    def test_streamed_body_limit_without_content_length(self):
        sent = []

        async def downstream(scope, receive, send):
            try:
                while (await receive()).get('more_body'):
                    pass
            except HTTPException as error:
                sent.append(error.status_code)

        messages = iter([{'type': 'http.request', 'body': b'x' * 40000, 'more_body': True}] * 2)

        async def receive():
            return next(messages)

        scope = {'type': 'http', 'path': '/api/runs/paper/ask', 'method': 'POST', 'headers': []}
        asyncio.run(RequestBodyLimit(downstream, lambda: 32)(scope, receive, Mock()))
        self.assertEqual(sent, [413])

    def test_arxiv_id_and_download_size_are_bounded(self):
        with patch.object(pdf.urllib.request, 'urlopen') as open_url:
            with self.assertRaises(PublicError):
                pdf.download_arxiv('../private?x=1')
            open_url.assert_not_called()
        with (
            patch.dict(os.environ, {'PAPER_MAX_UPLOAD_MB': '1'}),
            patch.object(pdf.urllib.request, 'urlopen', return_value=io.BytesIO(b'x' * (1024 * 1024 + 1))),
        ):
            with self.assertRaisesRegex(PublicError, 'exceeds'):
                pdf.download_arxiv('1706.03762')

    def test_production_rejects_unsafe_configuration(self):
        with patch.dict(os.environ, {'PAPER_ENV': 'production'}), patch.object(sandbox, 'backend', return_value='landlock'):
            with self.assertRaisesRegex(RuntimeError, 'ACCESS_TOKEN'):
                validate_deployment('short', 20, 2, 50, 0)
            with self.assertRaisesRegex(RuntimeError, 'RATE_LIMIT'):
                validate_deployment('x' * 32, 0, 2, 50, 0)
            with patch.object(sandbox, 'backend', return_value='guard'), self.assertRaisesRegex(RuntimeError, 'kernel confinement'):
                validate_deployment('x' * 32, 20, 2, 50, 0)
            validate_deployment('x' * 32, 20, 2, 50, 0)

    def test_generation_prerequisites_work_during_async_upload(self):
        sandbox.runtime_problem.cache_clear()
        with patch.object(main, 'configured', return_value=True), patch.object(main, 'launch_run'):
            response = self.client.post('/api/runs', data={'arxiv_id': '1706.03762'})
        self.assertEqual(response.status_code, 200, response.text)

    def test_restart_recovers_interrupted_runs_and_excludes_second_owner(self):
        main.recover_runs()
        status = pipeline.read_json(self.run_dir, 'status.json')
        self.assertTrue(status['done'])
        self.assertIn('restart', status['error'])
        with patch.dict(os.environ, {'PAPER_ENV': 'production'}), own_run_directory(self.root):
            with self.assertRaisesRegex(RuntimeError, 'Another server'), own_run_directory(self.root):
                self.fail('A second owner must not start')

    def test_worker_binds_lifetime_to_expected_server_parent(self):
        with patch.object(worker.os, 'getppid', return_value=123), patch.object(worker.threading, 'Thread') as thread:
            worker.watch_parent(123)
            thread.return_value.start.assert_called_once()
            with self.assertRaises(SystemExit):
                worker.watch_parent(456)
            monitor = thread.call_args.kwargs['target']
            with (
                patch.object(worker.threading, 'Event') as event,
                patch.object(worker.os, 'getppid', return_value=456),
                patch.object(worker.os, 'kill') as kill,
            ):
                event.return_value.wait.return_value = False
                monitor()
                kill.assert_called_once_with(worker.os.getpid(), worker.signal.SIGTERM)

    def test_cancel_interrupt_always_kills_model_process_group(self):
        process = Mock()
        process.communicate.side_effect = SystemExit(143)
        with patch.object(sandbox.subprocess, 'Popen', return_value=process), patch.object(sandbox, 'kill_group') as kill, self.assertRaises(SystemExit):
            sandbox.run(['unused'], self.run_dir, 5, setup=lambda: None)
        kill.assert_called_once_with(process)


class PublicationTests(unittest.TestCase):
    def test_failed_missing_or_nonfinite_required_results_block_publication(self):
        plan = {'validation_targets': [{'id': 'sum', 'metric': 'sum', 'expected': 1}]}
        validation = {'results': [{'id': 'sum', 'status': 'pass'}, {'id': 'paper_experiment', 'status': 'not_measured'}]}
        require_validation(plan, validation, {'metrics': {'sum': 1}})
        for status in ('fail', 'partial', 'not_measured'):
            bad = copy.deepcopy(validation)
            bad['results'][0]['status'] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                require_validation(plan, bad, {'metrics': {'sum': 1}})
        for value in (None, float('nan'), float('inf'), True, [], 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_validation(plan, validation, {'metrics': {'sum': value}})
        with self.assertRaises(ValueError):
            require_validation(plan, {'results': []}, {'metrics': {'sum': 1}})
        plan['validation_targets'][0]['expected'] = '1'
        with self.assertRaises(ValueError):
            require_validation(plan, validation, {'metrics': {'sum': 2}})
        for expected in ('nan', 'inf', float('nan')):
            plan['validation_targets'][0]['expected'] = expected
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                require_validation(plan, validation, {'metrics': {'sum': 1}})

    def test_rejected_reference_is_not_reused_on_retry(self):
        class RejectedProvider(DemoProvider):
            def validate(self, analysis, plan, output):
                return {'results': [{'id': 'v0', 'status': 'fail'}]}

        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / 'paper.pdf').write_bytes((SAMPLE / 'paper.pdf').read_bytes())
            pipeline.write_json(run, 'status.json', pipeline.initial_status())
            pipeline.run_pipeline(run, provider=RejectedProvider())
            status = pipeline.read_json(run, 'status.json')
            self.assertTrue(status['done'])
            self.assertIn('numerical', status['error'])
            self.assertFalse((run / 'checkpoints/reference.json').exists())
            self.assertFalse((run / 'checkpoints/validation.json').exists())
            self.assertFalse((run / 'world.js').exists())

    def test_unresolved_major_visual_defects_are_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            pipeline.write_json(run, 'status.json', pipeline.initial_status())
            progress = pipeline.Progress(run)
            provider = SimpleNamespace(critique=lambda *args: {'issues': [{'severity': 'major', 'problem': 'Decoder missing'}]})
            with self.assertRaisesRegex(PublicError, 'visual review'):
                pipeline.review(
                    run,
                    progress,
                    provider,
                    {'objects': []},
                    {'entities': [], 'figures': []},
                    [],
                    'world',
                    {'lessons': []},
                    lambda *args: ('world', {'lessons': []}),
                )
