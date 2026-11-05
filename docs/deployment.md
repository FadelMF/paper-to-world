# Running and deploying Paper-to-World

## Local start: one API key

From the project directory, create `.env` from `.env.example` if it does not exist, then set `LLM_API_KEY`. The code defaults to `https://api.meta.ai/v1`, `muse-wonder-1.0`, and the Responses protocol. `MODEL_API_KEY` is also accepted as a fallback. Existing nonempty endpoint/model/protocol settings override those defaults.

```bash
cp -n .env.example .env
# Edit LLM_API_KEY in .env. Do not put the key in a shell command.
scripts/start.sh
```

The startup script installs the locked Python dependencies and Playwright Chromium, then starts a single production server on `127.0.0.1:8000`. Python/uv, Node 22.13+ and Linux 6.7+ x86_64 are host prerequisites. No provider call is made during startup. Visit the home page, upload a paper, and the live pipeline starts. Missing keys, quotas, provider failures or rejected generated artifacts produce an error instead of substituting a demo result.

Use an SSH tunnel to this port for a private test. Restart after changing `.env`. `scripts/check_provider.py --live` is an optional billable probe, not a startup requirement. `VISION_MODEL` is optional and must name a model the provider actually supports for images; text-only configuration does not silently claim visual review. Model access, provider behavior and generated quality remain subject to the real-key test.

## Browser sessions and private runs

Production automatically issues a random, HttpOnly, SameSite=Strict session cookie. Under HTTPS it is Secure. Run ownership is checked on list, status, artifacts, libraries, learn/build pages, cancel, retry and tutor routes. Cookies contain random credentials, and only their hashes are stored. A session lasts 30 days; runs default to seven-day retention. Guest workspaces need no signup. From Your worlds → Manage your account, users can optionally register a username/password to keep the current workspace across devices. Passwords use salted scrypt hashes (N=2^17, r=8, p=1); login rotates the session credential and logout revokes it. Clearing guest cookies starts a different workspace. Registered users can sign in again, but there is no email/password-reset service; keep credentials in a password manager. Signing in does not merge an unrelated guest workspace. Existing unowned runs are not publicly claimed. Prepared examples stay public. An optional `PAPER_ACCESS_TOKEN` adds an entry gate without merging session ownership.

The database (`runs/.state.sqlite3`) stores ownership, session hashes, rate history and provider reservations. Back it up with the run artifacts. Never expose `runs/` through the web server.

## Isolation and limits

Generated model/world JavaScript and challenge expressions execute in a browser iframe with an opaque origin (`sandbox="allow-scripts"`). Its HTTP CSP independently enforces the sandbox, blocks connections, nested frames, workers, forms and external resources, and permits only bundled assets and blob modules. The parent sends simulation inputs over a private MessageChannel; the frame cannot request arbitrary fetches or tutor actions. The parent document has no `unsafe-eval` on live lesson routes. Prepared authored examples remain ordinary application code.

Build admission and tutor concurrency are bounded. New builds are rejected above the configurable storage admission ceiling (2 GB by default) or when disk headroom is too small; running builds can still grow, so monitor disk capacity. New session admission is capped at 50,000 unexpired sessions. Per-IP and per-session hourly limits survive restart. Provider calls reserve conservative input-byte/output-token/image allowances before transmission, with daily UTC session/global caps and per-build caps. Automatic SDK retries are disabled so every actual call has one reservation. Failed calls keep their reservation. These are conservative usage limits, **not a quoted dollar budget or a guarantee of the provider's billing semantics**. Configure the provider account's spending ceiling as well. Never set a zero budget to mean unlimited.

Reference-model code can write only inside its run’s `.scratch` folder; status, checkpoints and world artifacts are read-only to it. Workers have CPU, wall-time and address-space limits for document processing. Generated Python/Node still use kernel confinement. Chromium needs a large virtual address space; its resident-memory ceiling comes from the service cgroup below. Running the development command alone does not install that cgroup.

## Public host setup

The repository includes `deploy/paper-to-world.service` and `deploy/nginx.conf`. These are deployment templates, not an already-installed public deployment. A domain, TLS certificate, service account and host configuration are necessarily specific to your server.

1. Install the app under `/opt/paper-to-world`, with a dedicated `paper-world` system user and group. Use the host Python 3.12+ for the virtual environment (`uv venv --python /usr/bin/python3 --no-managed-python`), then `uv sync --locked --no-dev`. Install compatible Node on the system PATH.
2. Install Chromium and its system libraries with `PLAYWRIGHT_BROWSERS_PATH=/opt/paper-to-world/browsers uv run --no-dev python -m playwright install --with-deps chromium`. The service cannot read a browser installed in another user's home directory.
3. Keep source and `.venv` read-only to the service account. Create `runs/` owned by `paper-world` with mode 0700; `.env` should be readable only by root/service account (0640 or stricter).
4. Install the systemd unit. It sets a 2,500 MB resident-memory cap for the whole service tree, CPU quota, task/file limits, read-only system directories and process-tree cleanup. Adjust capacity deliberately for the host. It keeps the backend bound to loopback.
5. Replace the example domain and certificate paths in the nginx configuration. Test with `nginx -t`; enable HTTPS and the HTTP redirect. nginx overwrites forwarded addresses; only the loopback proxy is trusted by Uvicorn. Keep port 8000 closed to external traffic.
6. Enable the service and verify `/healthz` and a real-paper build from the HTTPS origin. Verify a second browser cannot access the first browser's run.

Monitor systemd/journald for exits and worker failures, `/healthz` for process health, and failed build statuses. Access logs are disabled to avoid logging optional entry tokens. Operator-only `runs/<id>/debug.log` and `usage.json` contain diagnostics; do not publish them. A health response does not prove provider connectivity.

## Backup and recovery

Stop the production service, then run:

```bash
uv run --locked python scripts/backup.py /private/backups/paper-world-2026-11-04
```

The destination must be new and outside `runs/`. The backup command refuses an active production owner, copies artifacts and uses SQLite's backup API for state. Protect backups as private documents. Restart the service after the snapshot. Retain backups according to the same document-retention policy.

To restore, stop the service, preserve the current `runs/` separately, copy the trusted snapshot into a new `runs/`, restore service-account ownership and mode 0700, and restart. Startup marks interrupted work stopped and retryable. Keep `.env` separately in the deployment's secret store; backups intentionally do not include it. Test restoration before relying on backups.

## Verification and release boundary

`uv.lock`, `scripts/check.sh`, and `.github/workflows/check.yml` define reproducible local/CI checks. The project now has its own local Git repository; it has not been pushed to a remote. The workflow runs after pushing to a GitHub repository. Choose code-distribution licensing with the owner before publishing source; operating the web app does not require releasing its source.

The supported server remains one Uvicorn process with SQLite and a local worker queue. This is a bounded single-host deployment, not a distributed service; email verification and password recovery are not included. Browser sandboxing does not make generated scientific claims correct, nor prevent a faulty world from hanging its own view. Real-provider validation, DNS/TLS activation, host capacity testing and off-host backup execution must happen in the actual deployment environment.

Password work factors follow the [OWASP password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt); concurrent password operations are capped at two, separately from tutor requests.
