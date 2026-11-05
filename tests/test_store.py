"""Ownership and reservations survive independent clients and SQLite connections."""

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import llm, main, pipeline, store
from app.errors import PublicError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'PAPER_RUNS_DIR': self.tmp.name, 'PAPER_PRIVATE_SESSIONS': '1'})
        env.start()
        self.addCleanup(env.stop)
        root = patch.object(main, 'RUNS', self.root)
        root.start()
        self.addCleanup(root.stop)

    def test_session_ownership_on_every_run_route(self):
        first, other = TestClient(main.app), TestClient(main.app)
        first.get('/api/config')
        owner, _ = store.session(first.cookies.get('paper_session'), self.root)
        folder = self.root / 'private'
        folder.mkdir()
        pipeline.write_json(folder, 'status.json', pipeline.initial_status())
        pipeline.write_json(folder, 'source.json', {})
        (folder / 'paper.pdf').write_bytes(b'%PDF-private')
        store.assign('private', owner, self.root)
        self.assertEqual(first.get('/api/runs/private').status_code, 200)
        self.assertEqual(other.get('/api/runs').json(), [])
        for path in ('/api/runs/private', '/api/runs/private/files/paper.pdf', '/api/runs/private/lesson/specimen.js', '/learn/private', '/build/private'):
            self.assertEqual(other.get(path).status_code, 404, path)
        for action in ('cancel', 'retry', 'ask'):
            self.assertEqual(other.post('/api/runs/private/' + action, json={'question': 'Why?'}).status_code, 404)
        restored = TestClient(main.app)
        restored.cookies.set('paper_session', first.cookies.get('paper_session') or '')
        self.assertEqual(restored.get('/api/runs/private').status_code, 200)
        self.assertEqual(first.get('/api/runs', headers={'Origin': 'null'}).status_code, 403)

    def test_request_limit_survives_connections_and_subject_changes(self):
        self.assertTrue(store.allow_request(['ip:a', 'user:a'], 2))
        self.assertTrue(store.allow_request(['ip:a', 'user:b'], 2))
        self.assertFalse(store.allow_request(['ip:a', 'user:c'], 2))

    def test_budget_is_atomic_persistent_and_cannot_be_disabled(self):
        with patch.dict(os.environ, {'PAPER_DAILY_GLOBAL_TOKENS': '100', 'PAPER_DAILY_USER_TOKENS': '100'}):

            def attempt(_):
                try:
                    store.reserve(30)
                    return True
                except PublicError:
                    return False

            with ThreadPoolExecutor(max_workers=5) as executor:
                self.assertEqual(sum(executor.map(attempt, range(10))), 3)
            with self.assertRaises(PublicError):
                store.reserve(30)
        with patch.dict(os.environ, {'PAPER_DAILY_GLOBAL_TOKENS': '0'}), self.assertRaises(PublicError):
            store.reserve(1)

    def test_key_only_selects_meta_responses(self):
        with patch.dict(os.environ, {'LLM_API_KEY': 'fake'}, clear=True):
            self.assertTrue(llm.configured())
            self.assertEqual(llm.text_settings(), ('https://api.meta.ai/v1', 'fake', 'muse-wonder-1.0'))
            self.assertEqual(llm.protocol(), 'responses')

    def test_exhausted_budget_never_opens_provider_connection(self):
        with patch.dict(os.environ, {'PAPER_DAILY_GLOBAL_TOKENS': '1'}), patch.object(llm, 'OpenAI') as client:
            with self.assertRaises(PublicError):
                llm.complete(('http://test', 'fake', 'fake'), 'system', 'hello')
            client.assert_not_called()

    def test_production_cookie_flags_and_optional_entry_gate(self):
        with patch.dict(os.environ, {'PAPER_ENV': 'production'}), patch.object(main, 'RATE_LIMIT', 20), patch.object(main, 'ACCESS_TOKEN', ''):
            with TestClient(main.app, base_url='https://paper.example') as client:
                response = client.get('/api/config')
                cookie = response.headers['set-cookie'].lower()
                self.assertIn('httponly', cookie)
                self.assertIn('secure', cookie)
                self.assertIn('samesite=strict', cookie)
                self.assertEqual(client.get('/healthz').status_code, 200)

    def test_offline_backup_keeps_ownership_and_refuses_live_owner(self):
        import fcntl
        import subprocess
        import sys

        destination = self.root.parent / (self.root.name + '-backup')
        self.addCleanup(lambda: __import__('shutil').rmtree(destination, ignore_errors=True))
        store.assign('example', 'owner', self.root)
        command = [sys.executable, 'scripts/backup.py', str(destination)]
        with (self.root / '.server.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(store.owner_for('example', destination), 'owner')
        self.assertFalse((destination / '.server.lock').exists())

    def test_storage_admission_rejects_before_starting(self):
        with patch.dict(os.environ, {'PAPER_MAX_STORAGE_MB': '0'}), patch.object(main, 'launch_run') as launch:
            with self.assertRaises(main.HTTPException) as failure:
                main.start_run(b'%PDF-test')
            self.assertEqual(failure.exception.status_code, 507)
            launch.assert_not_called()

    def test_account_registration_login_logout_and_guest_world_ownership(self):
        first = TestClient(main.app)
        first.get('/api/config')
        guest_token = first.cookies.get('paper_session')
        owner, _ = store.session(guest_token, self.root)
        folder = self.root / 'mine'
        folder.mkdir()
        pipeline.write_json(folder, 'status.json', pipeline.initial_status())
        pipeline.write_json(folder, 'source.json', {})
        store.assign('mine', owner, self.root)
        credentials = {'username': 'researcher', 'password': 'long-test-password-42'}
        self.assertEqual(first.post('/api/account/register', json=credentials).status_code, 200)
        self.assertNotEqual(first.cookies.get('paper_session'), guest_token)
        self.assertEqual(first.get('/api/account').json()['username'], 'researcher')
        other = TestClient(main.app)
        self.assertEqual(other.get('/api/runs/mine').status_code, 404)
        self.assertEqual(other.post('/api/account/login', json={**credentials, 'password': 'wrong-password-42'}).status_code, 401)
        self.assertEqual(other.post('/api/account/login', json=credentials).status_code, 200)
        self.assertEqual(other.get('/api/runs/mine').status_code, 200)
        old = other.cookies.get('paper_session')
        self.assertEqual(other.post('/api/logout').status_code, 200)
        other.cookies.set('paper_session', old or '')
        self.assertEqual(other.get('/api/runs/mine').status_code, 404)
        with store.database(self.root) as db:
            row = db.execute('SELECT salt,digest FROM accounts').fetchone()
            self.assertNotIn(credentials['password'], repr(row))

    def test_login_attempts_share_persistent_ip_limit(self):
        with patch.object(main, 'RATE_LIMIT', 2):
            for number in range(3):
                client = TestClient(main.app)
                response = client.post('/api/account/login', json={'username': 'unknown', 'password': 'a-wrong-password'})
                self.assertEqual(response.status_code, 429 if number == 2 else 401)

    def test_password_hash_concurrency_is_bounded_and_released(self):
        import threading

        slots = threading.BoundedSemaphore(1)
        client = TestClient(main.app)
        credentials = {'username': 'unknown', 'password': 'a-wrong-password'}
        with patch.object(main, 'AUTH_SLOTS', slots):
            slots.acquire()
            with patch.object(store, 'sign_in') as login:
                self.assertEqual(client.post('/api/account/login', json=credentials).status_code, 503)
                login.assert_not_called()
            slots.release()
            self.assertEqual(client.post('/api/account/login', json=credentials).status_code, 401)
            self.assertTrue(slots.acquire(blocking=False))
            slots.release()
