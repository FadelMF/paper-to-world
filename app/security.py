"""Bound request bodies before multipart parsing can spool arbitrary amounts to disk."""

import os
from contextlib import contextmanager

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, upload_limit):
        self.app = app
        self.upload_limit = upload_limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        # Multipart boundaries and form fields get 1 MB beyond the PDF limit.
        limit = self.upload_limit() + 1024 * 1024 if scope['path'] == '/api/runs' else 64 * 1024
        if scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        length = headers.get(b'content-length')
        try:
            declared = int(length) if length else 0
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        if declared < 0:
            return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, send)
        if declared > limit:
            return await JSONResponse({'detail': 'Request body is too large.'}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > limit:
                    raise HTTPException(status_code=413, detail='Request body is too large.')
            return message

        return await self.app(scope, bounded_receive, send)


def validate_deployment(token, rate_limit, max_workers, upload_limit, retention_days):
    if max_workers < 1 or upload_limit < 1 or rate_limit < 0 or retention_days < 0:
        raise RuntimeError('Worker/upload limits must be positive; rate and retention limits must be nonnegative.')
    if os.getenv('PAPER_ENV', 'development') != 'production':
        return
    from app import sandbox

    if token and len(token) < 32:
        raise RuntimeError('When configured, PAPER_ACCESS_TOKEN must have at least 32 characters.')
    if rate_limit < 1:
        raise RuntimeError('Production requires a positive PAPER_RATE_LIMIT_PER_HOUR.')
    if sandbox.backend() != 'landlock':
        raise RuntimeError('Production requires kernel confinement; PAPER_SANDBOX=guard is development only.')


@contextmanager
def own_run_directory(directory):
    """The in-memory queue must have a single owner for a production runs directory."""
    if os.getenv('PAPER_ENV', 'development') != 'production':
        yield
        return
    import fcntl

    with (directory / '.server.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another server owns this runs directory. Use one Uvicorn worker.') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
