import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from . import __version__
from .models import AnalysisRequest

STATIC = Path(__file__).parent / "static"
MAX_BODY = 1_500_000
SLOTS = threading.BoundedSemaphore(2)
app = FastAPI(title="CodeScope", version=__version__, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and urlsplit(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail": "Запросы с другого сайта запрещены"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    import shutil
    return {"version": __version__, "mode": "local-static-analysis",
            "tools": {name: bool(shutil.which(name) or (Path(sys.executable).parent / (name + (".exe" if os.name == "nt" else ""))).is_file()) for name in ["ruff", "bandit", "pyright", "g++", "cppcheck", "javac", "dotnet"]}}


def analyze_isolated(payload: AnalysisRequest):
    if not SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Две проверки уже выполняются. Повторите чуть позже.")
    process = None
    try:
        process = subprocess.Popen([sys.executable, "-m", "codescope.worker"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=(os.name == "posix"))
        try:
            stdout, stderr = process.communicate(payload.model_dump_json().encode(), timeout=85)
        except subprocess.TimeoutExpired:
            raise HTTPException(504, "Проверка превысила общий лимит 85 секунд")
        if process.returncode != 0:
            raise HTTPException(503, "Анализатор не смог завершить проверку. Проверьте установку инструментов или уменьшите файл.")
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            raise HTTPException(503, "Анализатор вернул повреждённый отчёт")
    finally:
        if process is not None:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.wait()
        SLOTS.release()


@app.post("/api/analyze")
async def analyze_code(request: Request):
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "Ожидается application/json")
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > MAX_BODY:
            raise HTTPException(413, "Запрос слишком большой")
    try:
        payload = AnalysisRequest.model_validate_json(chunks)
    except ValidationError as exc:
        messages = [entry["msg"] for entry in exc.errors(include_input=False, include_context=False)]
        raise HTTPException(422, "; ".join(messages))
    return await run_in_threadpool(analyze_isolated, payload)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
