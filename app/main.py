import base64
import hashlib
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app import agents, sandbox, store
from app.errors import PublicError
from app.llm import configured, vision_configured
from app.pdf import ARXIV_ID
from app.pipeline import RUNS, Progress, debug, initial_status, read_json, write_json
from app.security import RequestBodyLimit, own_run_directory, validate_deployment

STATIC = Path(__file__).resolve().parents[1] / "static"
MAX_UPLOAD_BYTES = int(os.getenv("PAPER_MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_WORKERS = int(os.getenv("PAPER_MAX_WORKERS", "2"))
MAX_PENDING_RUNS = int(os.getenv("PAPER_MAX_PENDING_RUNS", "10"))
MAX_TUTOR_REQUESTS = int(os.getenv("PAPER_MAX_TUTOR_REQUESTS", "2"))
TUTOR_SLOTS = threading.BoundedSemaphore(max(1, MAX_TUTOR_REQUESTS))
AUTH_SLOTS = threading.BoundedSemaphore(2)
RETENTION_DAYS = float(os.getenv("PAPER_RUN_RETENTION_DAYS", "7" if os.getenv("PAPER_ENV") == "production" else "0"))
WORKERS = {}
QUEUE = []  # run folders waiting for a free worker, oldest first
WORKER_LOCK = threading.RLock()


def stop_worker(run_id, message=None):
    """Stop a run's process group; an unfinished run is marked stopped."""
    process = WORKERS.pop(run_id, None)
    if process and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
    directory = RUNS / run_id
    if directory.is_dir() and not read_json(directory, "status.json")["done"]:
        Progress(directory).fail(*([message] if message else []))


def waiting_status(place):
    status = initial_status()
    ahead = "1 paper is" if place == 1 else f"{place} papers are"
    status.update(headline="Waiting for your turn", subline=f"{ahead} being built before yours. Yours starts automatically.", queued=place)
    return status


def dispatch():
    """Retire finished workers, start queued runs while fewer than MAX_WORKERS build, and show the rest their place."""
    with WORKER_LOCK:
        for run_id in [run_id for run_id, process in WORKERS.items() if process.poll() is not None]:
            stop_worker(run_id)  # a run its worker left unfinished is marked stopped
        while QUEUE and len(WORKERS) < MAX_WORKERS:
            run_dir = QUEUE.pop(0)
            write_json(run_dir, "status.json", initial_status())
            try:
                start_worker(run_dir)
            except OSError as error:
                debug(run_dir, f"Worker launch failed: {error!r}")
                Progress(run_dir).fail("This server could not start the build. Please try again later.")
        for place, run_dir in enumerate(QUEUE, 1):
            write_json(run_dir, "status.json", waiting_status(place))


def prune_runs(now=None):
    """Delete finished runs older than PAPER_RUN_RETENTION_DAYS (0 keeps every run). Running or queued runs stay."""
    if not RETENTION_DAYS:
        return []
    cutoff = (now or datetime.now()) - timedelta(days=RETENTION_DAYS)
    removed = []
    with WORKER_LOCK:
        busy = set(WORKERS) | {run_dir.name for run_dir in QUEUE}
        for run_dir in RUNS.iterdir() if RUNS.is_dir() else []:
            started = created_at(run_dir.name)
            if run_dir.name in busy or started is None or datetime.fromisoformat(started) >= cutoff:
                continue
            if (run_dir / "status.json").is_file() and not read_json(run_dir, "status.json")["done"]:
                continue
            shutil.rmtree(run_dir)
            removed.append(run_dir.name)
    return removed


def recover_runs():
    """A single production owner can safely mark builds left unfinished by a prior process."""
    for directory in RUNS.iterdir():
        if not directory.is_dir() or directory.is_symlink() or not (directory / "status.json").is_file():
            continue
        if not read_json(directory, "status.json")["done"]:
            Progress(directory).fail("This build was interrupted by a server restart. Retry to continue from its saved progress.")


def keep_dispatching(stop):
    ticks = 0
    while not stop.wait(2):
        dispatch()
        ticks += 1
        if ticks % 1800 == 0:  # about hourly
            prune_runs()


@asynccontextmanager
async def lifespan(app):
    validate_deployment(ACCESS_TOKEN, RATE_LIMIT, MAX_WORKERS, MAX_UPLOAD_BYTES, RETENTION_DAYS)
    if MAX_PENDING_RUNS < 1:
        raise RuntimeError("PAPER_MAX_PENDING_RUNS must be positive.")
    if MAX_TUTOR_REQUESTS < 1:
        raise RuntimeError("PAPER_MAX_TUTOR_REQUESTS must be positive.")
    with own_run_directory(RUNS):
        if os.getenv("PAPER_ENV") == "production":
            recover_runs()
        prune_runs()
        stop = threading.Event()
        dispatcher = threading.Thread(target=keep_dispatching, args=(stop,), daemon=True)
        app.state.dispatcher = dispatcher
        dispatcher.start()
        try:
            yield
        finally:
            stop.set()
            dispatcher.join(timeout=5)
            with WORKER_LOCK:
                QUEUE.clear()
                for run_id in list(WORKERS):
                    stop_worker(run_id)


app = FastAPI(title="Paper-to-World", lifespan=lifespan)
app.add_middleware(RequestBodyLimit, upload_limit=lambda: MAX_UPLOAD_BYTES)


def inline_script_hashes():
    """CSP hashes of the inline scripts (import maps) in the app's pages."""
    scripts = {m for page in STATIC.rglob("*.html") for m in re.findall(r"<script[^>]*>(.+?)</script>", page.read_text(), re.S)}
    return " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()}'" for script in sorted(scripts))


# Prepared lessons evaluate authored challenges. Live lessons remove unsafe-eval; generated code
# and challenge expressions execute only inside the opaque sandbox frame.
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-eval' " + inline_script_hashes() + "; "
    "style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: blob:; connect-src 'self'; "
    "frame-ancestors 'none'; worker-src 'self' blob:; media-src 'self' blob:; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
)


ACCESS_TOKEN = os.getenv("PAPER_ACCESS_TOKEN", "")
RATE_LIMIT = int(os.getenv("PAPER_RATE_LIMIT_PER_HOUR", "20" if os.getenv("PAPER_ENV") == "production" else "0"))
LIMITED = {("POST", "/api/runs"), ("POST", "ask"), ("POST", "retry"), ("POST", "/api/account/register"), ("POST", "/api/account/login")}


def limited(request):
    path = request.url.path
    return (request.method, path) in LIMITED or (request.method, path.rsplit("/", 1)[-1]) in LIMITED


@app.middleware("http")
async def access(request, call_next):
    """With PAPER_ACCESS_TOKEN set, every request needs the token: once as ?token=… (kept in a cookie) or as a
    Bearer header. With PAPER_RATE_LIMIT_PER_HOUR set, each client may start that many runs, retries and tutor
    questions per hour."""
    if request.url.path.startswith("/assets/") or request.url.path == "/healthz":
        return await call_next(request)
    origin = request.headers.get("origin")
    if origin == "null":
        return JSONResponse({"detail": "Sandboxed documents cannot access application endpoints."}, status_code=403)
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
    if ACCESS_TOKEN:
        scheme, _, credential = request.headers.get("authorization", "").partition(" ")
        bearer = credential if scheme.lower() == "bearer" else ""
        offered = request.query_params.get("token") or bearer or request.cookies.get("paper_token")
        if not secrets.compare_digest((offered or "").encode(), ACCESS_TOKEN.encode()):
            return PlainTextResponse("This server needs an access token. Open the link you were given, which ends in ?token=…", status_code=401)
        if request.query_params.get("token"):
            response = RedirectResponse(request.url.remove_query_params("token"), status_code=303)
            response.set_cookie("paper_token", ACCESS_TOKEN, httponly=True, samesite="strict", secure=request.url.scheme == "https")
            return response
    try:
        owner, new_cookie = store.session(request.cookies.get("paper_session"), RUNS) if store.private_sessions() else ("local", None)
    except PublicError as error:
        return JSONResponse({"detail": str(error)}, status_code=503)
    context = store.OWNER.set(owner)
    try:
        limit = RATE_LIMIT or (20 if request.url.path.startswith("/api/account/") else 0)
        if limit and limited(request):
            client = request.client.host if request.client else "unknown"
            if not store.allow_request(["owner:" + owner, "ip:" + client], limit, RUNS):
                return JSONResponse({"detail": "You've reached this server's hourly limit. Please try again later."}, status_code=429)
        response = await call_next(request)
        if new_cookie and "paper_session=" not in response.headers.get("set-cookie", ""):
            response.set_cookie("paper_session", new_cookie, max_age=30 * 86400, httponly=True, samesite="strict", secure=request.url.scheme == "https")
        return response
    finally:
        store.OWNER.reset(context)


@app.middleware("http")
async def revalidate(request, call_next):
    # Browsers must revalidate every page, style and script, so a refresh never mixes old and new files.
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store" if ACCESS_TOKEN or request.url.path.startswith("/api/") else "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/assets/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Content-Security-Policy"] = CSP.replace(" 'unsafe-eval'", "") if request.url.path.startswith("/learn/") else CSP
    if request.url.path == "/assets/lesson/frame.html":
        origin = str(request.base_url).rstrip("/")
        del response.headers["X-Frame-Options"]
        response.headers["Content-Security-Policy"] = (
            f"sandbox allow-scripts; default-src 'none'; script-src {origin}/assets/ blob: 'unsafe-eval' {inline_script_hashes()}; "
            f"style-src {origin}/assets/ 'unsafe-inline'; font-src {origin}/assets/ data:; img-src data: blob:; "
            "connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        )
    return response


def launch_run(run_dir):
    with WORKER_LOCK:
        QUEUE.append(run_dir)
    dispatch()


def start_worker(run_dir):
    with (run_dir / "debug.log").open("a") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "app.worker", str(run_dir.resolve()), str(os.getpid())], stdout=log, stderr=log, start_new_session=True
        )
    with WORKER_LOCK:
        WORKERS[run_dir.name] = process


def start_run(data=None, source=None, resume_from=None):
    # Admission and enqueue share the dispatcher lock, including concurrent retries.
    with WORKER_LOCK:
        if len(WORKERS) + len(QUEUE) >= MAX_PENDING_RUNS:
            raise HTTPException(503, "This server's build queue is full. Please try again later.", headers={"Retry-After": "30"})
        limit = int(os.getenv("PAPER_MAX_STORAGE_MB", "2048")) * 1024 * 1024
        used = 0
        for path in RUNS.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    used += path.stat().st_size
            except FileNotFoundError:
                continue  # A finished worker can remove temporary render files during admission.
        if limit <= 0 or used + len(data or b"") >= limit or shutil.disk_usage(RUNS).free < 2 * MAX_UPLOAD_BYTES:
            raise HTTPException(507, "This server needs more storage before another paper can be built.")
        return create_admitted_run(data, source, resume_from)


def create_admitted_run(data=None, source=None, resume_from=None):
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    directory = RUNS / run_id
    directory.mkdir()
    store.assign(run_id, root=RUNS)
    if data is not None:
        (directory / "paper.pdf").write_bytes(data)
    if resume_from and (resume_from / "checkpoints").is_dir():
        # The finished stages of an earlier attempt, and the figures their evidence points to.
        shutil.copytree(resume_from / "checkpoints", directory / "checkpoints")
        for figure in resume_from.glob("figure-*.png"):
            shutil.copyfile(figure, directory / figure.name)
    write_json(directory, "source.json", source or {})
    write_json(directory, "status.json", initial_status())
    launch_run(directory)
    return {"id": run_id}


def run_directory(run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise HTTPException(404, "Run not found")
    directory = RUNS / run_id
    if not directory.is_dir() or directory.is_symlink() or not store.owns(run_id, RUNS):
        raise HTTPException(404, "Run not found")
    return directory


RUNS.mkdir(parents=True, exist_ok=True, mode=0o700)
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/worlds")
def worlds():
    return FileResponse(STATIC / "worlds" / "index.html")


@app.get("/demo")
@app.get("/demo/3d")
@app.get("/demo/attention/2d")
@app.get("/demo/attention/3d")
def demo():
    return FileResponse(STATIC / "lesson" / "index.html")


@app.get("/learn/{run_id}")
def learn(run_id: str):
    run_directory(run_id)
    return FileResponse(STATIC / "lesson" / "index.html")


@app.get("/build/{run_id}")
def building(run_id: str):
    run_directory(run_id)
    return FileResponse(STATIC / "build" / "index.html")


@app.get("/demo/upload")
def upload_demo():
    return RedirectResponse("/?mode=examples&journey=1", status_code=307)


def generation_problem():
    """Why papers cannot be built on this server, in words for the learner, or None when they can."""
    if not configured():
        return "Live building is not connected on this server yet. The prepared examples are ready to explore."
    return sandbox.problem()


@app.get("/api/config")
def app_config():
    problem = generation_problem()
    return {
        "generation_available": problem is None,
        "problem": problem,
        "readiness_scope": "local_prerequisites",
        "vision_configured": bool(vision_configured()),
    }


@app.post("/api/runs")
async def create_run(
    file: Annotated[UploadFile | None, File()] = None,
    arxiv_id: Annotated[str, Form()] = "",
    demo: Annotated[bool, Form()] = False,
    example_id: Annotated[str, Form()] = "",
):

    if not file and not arxiv_id.strip():
        raise HTTPException(422, "Upload a PDF or enter an arXiv ID.")
    if file and arxiv_id.strip():
        raise HTTPException(422, "Choose one paper: a PDF or an arXiv ID.")
    data = await file.read(MAX_UPLOAD_BYTES + 1) if file else None
    if data is not None:
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"This PDF is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Try the arXiv ID instead.")
        if not data.lstrip()[:5] == b"%PDF-":
            raise HTTPException(422, "This file isn't a PDF. Upload the paper as a PDF or enter its arXiv ID.")
    example = None
    if demo:
        from app.demo import SAMPLES

        if example_id:
            if example_id not in SAMPLES or data != (SAMPLES[example_id] / "paper.pdf").read_bytes():
                raise HTTPException(422, "Choose the matching example PDF and example ID.")
            example = example_id
        else:
            example = next((mode for mode, folder in SAMPLES.items() if data == (folder / "paper.pdf").read_bytes()), None)
        if example is None:
            raise HTTPException(422, "This walkthrough uses the example PDF. For your own paper, use the main upload page.")
    elif problem := generation_problem():
        raise HTTPException(503, problem)
    if arxiv_id.strip() and not ARXIV_ID.fullmatch(arxiv_id.strip()):
        raise HTTPException(422, "Enter an arXiv ID such as 1706.03762.")
    return start_run(data, {"arxiv_id": arxiv_id.strip(), "demo": demo, "example": example})


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    directory = run_directory(run_id)
    with WORKER_LOCK:
        if directory in QUEUE:
            QUEUE.remove(directory)
        if not read_json(directory, "status.json")["done"]:
            debug(directory, "Canceled by user; stopped worker and reference process group")
        stop_worker(run_id, "You canceled this world. You can try again whenever you're ready.")
    dispatch()
    return {"status": read_json(directory, "status.json")}


@app.post("/api/runs/{run_id}/retry")
def retry_run(run_id: str, fresh: bool = False):
    """A new run for the same paper. It resumes after the last stage that finished, unless `fresh`."""
    directory = run_directory(run_id)
    status = read_json(directory, "status.json")
    if not status["done"] or not status["error"]:
        raise HTTPException(409, "This paper is still being prepared or is already ready.")
    source = read_json(directory, "source.json")
    if not source.get("demo") and (problem := generation_problem()):
        raise HTTPException(503, problem)
    pdf = directory / "paper.pdf"
    return start_run(pdf.read_bytes() if pdf.exists() else None, source, None if fresh else directory)


def created_at(run_id):
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").isoformat()
    except ValueError:
        return None


@app.get("/api/runs")
def list_runs():
    runs = []
    for run_dir in sorted(RUNS.iterdir(), reverse=True):
        if run_dir.is_symlink() or not store.owns(run_dir.name, RUNS) or not (run_dir / "status.json").is_file():
            continue
        status = read_json(run_dir, "status.json")
        source = read_json(run_dir, "source.json") if (run_dir / "source.json").is_file() else {}
        runs.append(
            {
                "id": run_dir.name,
                "title": status["discovered"]["title"] or "Your paper",
                "created": created_at(run_dir.name),
                "example": bool(source.get("demo")),
                "stopped": bool(status["error"]),
                "modality": status["discovered"]["modality"],
                "ready": status["done"] and not status["error"] and (run_dir / "lessons.json").exists() and (run_dir / "world.js").exists(),
            }
        )
    return runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run_dir = run_directory(run_id)
    dispatch()
    status = read_json(run_dir, "status.json")
    source = read_json(run_dir, "source.json")
    result = {"status": status, "demo": source.get("demo", False), "example": source.get("example")}
    for name in ["analysis", "plan", "validation"]:
        if (run_dir / f"{name}.json").exists():
            result[name] = read_json(run_dir, f"{name}.json")
    result["has_world"] = (run_dir / "lessons.json").exists() and (run_dir / "world.js").exists()
    return result


@app.get("/api/runs/{run_id}/files/{name}")
def get_file(run_id: str, name: str):
    directory = run_directory(run_id)
    public = {"paper.pdf", "world.js", "model.js"} | {
        f"{item}.json" for item in ("analysis", "evidence", "plan", "validation", "scene", "lessons", "pages", "coverage", "parity")
    }
    if name not in public and not re.fullmatch(r"figure-[A-Za-z0-9_-]+\.png", name):
        raise HTTPException(404, "Artifact not found")
    file = directory / name
    if not file.is_file() or not file.resolve().is_relative_to(directory.resolve()):
        raise HTTPException(404, "Artifact not found")
    return FileResponse(file, media_type="text/javascript" if file.suffix == ".js" else None)


@app.get("/api/runs/{run_id}/lesson/{name}")
def lesson_library(run_id: str, name: str):
    # A saved example world imports '../lesson/<library>.js' relative to its files/ URL.
    run_directory(run_id)
    file = STATIC / "lesson" / Path(name).name
    if file.suffix != ".js" or not file.is_file():
        raise HTTPException(404, "Library not found")
    return FileResponse(file, media_type="text/javascript")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a question")
        return value


@app.post("/api/runs/{run_id}/ask")
def ask(run_id: str, q: Question):
    run_dir = run_directory(run_id)
    source = read_json(run_dir, "source.json")
    if source.get("demo"):
        from app.demo import SAMPLES

        replies = read_json(SAMPLES[source.get("example", "2d")], "tutor.json")
        answer = next((item["text"] for item in replies["answers"] if any(word in q.question.lower() for word in item["keywords"])), replies["other"])
        return {"answer": "Demo response · " + answer}
    status = read_json(run_dir, "status.json")
    if not status["done"] or status["error"] or not all((run_dir / name).is_file() for name in ("pages.json", "analysis.json", "plan.json", "validation.json")):
        raise HTTPException(409, "This paper is not ready for questions yet.")
    if not TUTOR_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "The tutor is busy. Please try again shortly.", headers={"Retry-After": "10"})
    try:
        answer = agents.ask(
            read_json(run_dir, "pages.json"),
            read_json(run_dir, "analysis.json"),
            read_json(run_dir, "plan.json"),
            read_json(run_dir, "validation.json"),
            q.question,
            evidence=read_json(run_dir, "evidence.json") if (run_dir / "evidence.json").exists() else None,
        )
    except PublicError as error:
        raise HTTPException(429, str(error)) from None
    except Exception as error:
        debug(run_dir, f"Tutor reply failed: {error!r}")
        raise HTTPException(503, "The tutor couldn't answer just now. Please ask again in a moment.") from None
    finally:
        TUTOR_SLOTS.release()
    return {"answer": answer}


@app.get("/healthz")
def health():
    dispatcher = getattr(app.state, "dispatcher", None)
    healthy = dispatcher is None or dispatcher.is_alive()
    return JSONResponse({"status": "ok" if healthy else "unavailable"}, status_code=200 if healthy else 503)


@app.get("/account")
def account_page():
    return FileResponse(STATIC / "account" / "index.html")


class Credentials(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,40}$")
    password: str = Field(min_length=12, max_length=128)


@app.get("/api/account")
def account_status():
    return {"available": store.private_sessions(), "username": store.account_name(RUNS) if store.private_sessions() else None}


@app.post("/api/account/{action}")
def account_action(action: str, credentials: Credentials, request: Request):
    if not store.private_sessions():
        raise HTTPException(409, "Accounts are unavailable on this server.")
    if action not in ("register", "login"):
        raise HTTPException(404, "Not found")
    username = credentials.username.lower()
    if not AUTH_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "Sign-in is busy. Please try again shortly.", headers={"Retry-After": "2"})
    try:
        if action == "register":
            store.register(username, credentials.password, RUNS)
        token = store.sign_in(username, credentials.password, RUNS)
    except PublicError as error:
        raise HTTPException(409 if action == "register" else 401, str(error)) from None
    finally:
        AUTH_SLOTS.release()
    store.revoke(request.cookies.get("paper_session"), RUNS)
    response = JSONResponse({"username": username})
    response.set_cookie("paper_session", token, max_age=30 * 86400, httponly=True, samesite="strict", secure=request.url.scheme == "https")
    return response


@app.post("/api/logout")
def logout(request: Request):
    store.revoke(request.cookies.get("paper_session"), RUNS)
    response = JSONResponse({"signed_out": True})
    response.delete_cookie("paper_session")
    return response
