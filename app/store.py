"""SQLite ownership, persistent admission limits, and conservative provider-call budgets."""

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.errors import PublicError

OWNER = ContextVar('owner', default='local')
BUDGET_RUN = ContextVar('budget_run', default='tutor')


def private_sessions():
    return os.getenv('PAPER_ENV') == 'production' or os.getenv('PAPER_PRIVATE_SESSIONS') == '1'


@contextmanager
def database(root=None):
    root = Path(root or os.getenv('PAPER_RUNS_DIR', 'runs'))
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / '.state.sqlite3', timeout=15)
    try:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS owners (run TEXT PRIMARY KEY, owner TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, owner TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (subject TEXT NOT NULL, stamp REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS request_subject ON requests(subject, stamp);
            CREATE TABLE IF NOT EXISTS spending (day TEXT NOT NULL, owner TEXT NOT NULL, run TEXT NOT NULL, tokens INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS spending_day ON spending(day);
        ''')
        with connection:
            yield connection
    finally:
        connection.close()


def session(token, root=None):
    now = time.time()
    digest = hashlib.sha256((token or '').encode()).hexdigest()
    with database(root) as db:
        found = db.execute('SELECT owner FROM sessions WHERE digest=? AND expires>?', (digest, now)).fetchone()
        if found:
            return found[0], None
        token, owner = secrets.token_urlsafe(32), secrets.token_hex(16)
        db.execute('DELETE FROM sessions WHERE expires<?', (now,))
        if db.execute('SELECT count(*) FROM sessions').fetchone()[0] >= 50000:
            raise PublicError('This server cannot accept another session right now. Please try again later.')
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (hashlib.sha256(token.encode()).hexdigest(), owner, now + 30 * 86400))
        return owner, token


def assign(run, owner=None, root=None):
    with database(root) as db:
        db.execute('INSERT INTO owners VALUES (?, ?)', (run, owner or OWNER.get()))


def owns(run, root=None):
    if not private_sessions():
        return True
    with database(root) as db:
        return db.execute('SELECT 1 FROM owners WHERE run=? AND owner=?', (run, OWNER.get())).fetchone() is not None


def owner_for(run, root=None):
    with database(root) as db:
        result = db.execute('SELECT owner FROM owners WHERE run=?', (run,)).fetchone()
        return result[0] if result else 'local'


def allow_request(subjects, limit, root=None):
    now = time.time()
    with database(root) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM requests WHERE stamp<?', (now - 3600,))
        if any(db.execute('SELECT count(*) FROM requests WHERE subject=?', (s,)).fetchone()[0] >= limit for s in subjects):
            return False
        db.executemany('INSERT INTO requests VALUES (?, ?)', [(s, now) for s in subjects])
    return True


def reserve(tokens):
    """Reserve before transmission; never refund uncertain or failed requests, including after restart."""
    if not isinstance(tokens, int) or tokens <= 0:
        raise PublicError('Provider token reservations must be positive integers.')
    day = time.strftime('%Y-%m-%d', time.gmtime())
    owner, run = OWNER.get(), BUDGET_RUN.get()
    user_cap = int(os.getenv('PAPER_DAILY_USER_TOKENS', '5000000'))
    global_cap = int(os.getenv('PAPER_DAILY_GLOBAL_TOKENS', '20000000'))
    run_cap = int(os.getenv('PAPER_RUN_TOKEN_LIMIT', '3000000'))
    call_cap = int(os.getenv('PAPER_RUN_CALL_LIMIT', '100'))
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        total = db.execute('SELECT coalesce(sum(tokens),0) FROM spending WHERE day=?', (day,)).fetchone()[0]
        user = db.execute('SELECT coalesce(sum(tokens),0) FROM spending WHERE day=? AND owner=?', (day, owner)).fetchone()[0]
        used, calls = db.execute('SELECT coalesce(sum(tokens),0), count(*) FROM spending WHERE owner=? AND run=?', (owner, run)).fetchone()
        if min(user_cap, global_cap, run_cap, call_cap) <= 0:
            raise PublicError('Provider budgets must be positive. Ask the server operator to check configuration.')
        if total + tokens > global_cap or user + tokens > user_cap or (run != 'tutor' and (used + tokens > run_cap or calls >= call_cap)):
            raise PublicError('This server has reached its AI usage budget. Try again after the daily reset or ask the operator to raise the limit.')
        db.execute('INSERT INTO spending VALUES (?, ?, ?, ?)', (day, owner, run, tokens))


def register(username, password, root=None):
    salt = secrets.token_bytes(16)
    digest = 'scrypt-131072-8-1$' + hashlib.scrypt(password.encode(), salt=salt, n=131072, r=8, p=1, maxmem=256 * 1024 * 1024).hex()
    with database(root) as db:
        try:
            db.execute('INSERT INTO accounts VALUES (?, ?, ?, ?)', (username, OWNER.get(), salt.hex(), digest))
        except sqlite3.IntegrityError as error:
            raise PublicError('That username or workspace already has an account.') from error


def sign_in(username, password, root=None):
    with database(root) as db:
        found = db.execute('SELECT owner, salt, digest FROM accounts WHERE username=?', (username,)).fetchone()
    salt = bytes.fromhex(found[1]) if found else bytes(16)
    digest = 'scrypt-131072-8-1$' + hashlib.scrypt(password.encode(), salt=salt, n=131072, r=8, p=1, maxmem=256 * 1024 * 1024).hex()
    if not secrets.compare_digest(digest, found[2] if found else '0' * len(digest)):
        raise PublicError('Username or password is incorrect.')
    owner = found[0]
    token = secrets.token_urlsafe(32)
    with database(root) as db:
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (hashlib.sha256(token.encode()).hexdigest(), owner, time.time() + 30 * 86400))
    return token


def revoke(token, root=None):
    with database(root) as db:
        db.execute('DELETE FROM sessions WHERE digest=?', (hashlib.sha256((token or '').encode()).hexdigest(),))


def account_name(root=None):
    with database(root) as db:
        row = db.execute('SELECT username FROM accounts WHERE owner=?', (OWNER.get(),)).fetchone()
        return row[0] if row else None
