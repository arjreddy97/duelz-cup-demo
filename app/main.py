"""FastAPI app: static results page, live demo page, and the streaming run API."""
import asyncio
import json
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .modes import single_agent, split_verify

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Duelz for Gemini", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    # Pages and assets change with each deploy; make browsers revalidate instead of showing old copies.
    response = await call_next(request)
    if request.url.path != "/api/run":
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------------- rate limits
class Limiter:
    """In-memory limits (deploy with max-instances=1 so they are global)."""

    def __init__(self):
        self.last_by_visitor = {}
        self.recent = deque()  # start times of runs in the last 24h
        self.active = 0

    def check(self, visitor):
        now = time.time()
        while self.recent and now - self.recent[0] > 86400:
            self.recent.popleft()
        if not config.LIVE_ENABLED:
            return "Live runs are switched off right now."
        if not config.api_key() and not config.FAKE_MODEL:
            return "Live runs are not configured on this server (no GEMINI_API_KEY)."
        last = self.last_by_visitor.get(visitor)
        if last and now - last < config.PER_VISITOR_SECONDS:
            return f"One live run per minute. Try again in {int(config.PER_VISITOR_SECONDS - (now - last)) + 1}s."
        if self.active >= config.MAX_CONCURRENT_RUNS:
            return "Other visitors are running the demo. Try again in a few seconds."
        if sum(1 for t in self.recent if now - t < 3600) >= config.MAX_RUNS_PER_HOUR:
            return "The demo hit its hourly cap. Please come back later."
        if len(self.recent) >= config.MAX_RUNS_PER_DAY:
            return "The demo hit its daily cap. Please come back tomorrow."
        return None

    def start(self, visitor):
        now = time.time()
        self.last_by_visitor[visitor] = now
        self.recent.append(now)
        self.active += 1
        if len(self.last_by_visitor) > 10000:
            cutoff = now - config.PER_VISITOR_SECONDS
            self.last_by_visitor = {k: v for k, v in self.last_by_visitor.items() if v > cutoff}

    def finish(self):
        self.active = max(0, self.active - 1)


limiter = Limiter()


def visitor_id(request: Request):
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- pages
@app.get("/")
def results_page():
    return FileResponse(STATIC / "index.html")


@app.get("/demo")
def demo_page():
    return FileResponse(STATIC / "demo.html")


@app.get("/replay")
def replay_page():
    return FileResponse(STATIC / "replay.html")


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/api/config")
def public_config():
    return {"model": config.MODEL, "thinking": config.THINKING_LEVEL,
            "prices_per_million": {"input": config.PRICE_INPUT, "output": config.PRICE_OUTPUT,
                                   "cached": config.PRICE_CACHED},
            "single_max_turns": config.SINGLE_MAX_TURNS, "split_max_turns": config.SPLIT_MAX_TURNS,
            "split_retry_turns": config.SPLIT_RETRY_TURNS, "mode_max_usd": config.MODE_MAX_USD,
            "tool_output_chars": config.TOOL_OUTPUT_CHARS, "fake_model": config.FAKE_MODEL,
            "live": bool(config.LIVE_ENABLED and (config.api_key() or config.FAKE_MODEL))}


@app.post("/api/run")
async def run(request: Request):
    who = visitor_id(request)
    refusal = limiter.check(who)
    if refusal:
        return JSONResponse({"error": refusal}, status_code=429)
    limiter.start(who)
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event):
        queue.put_nowait(event)

    async def guarded(fn, mode):
        try:
            return await fn(emit)
        except Exception as exc:  # keep the stream alive; report the error
            emit({"mode": mode, "kind": "error", "message": f"{type(exc).__name__}: {str(exc)[:300]}"})
            return None

    async def driver():
        try:
            await asyncio.gather(guarded(single_agent, "single"), guarded(split_verify, "split"))
        finally:
            limiter.finish()
            queue.put_nowait({"kind": "end"})

    task = asyncio.create_task(driver())

    async def stream():
        model = "scripted fake model" if config.FAKE_MODEL else config.MODEL
        yield f"data: {json.dumps({'kind': 'start', 'model': model})}\n\n"
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("kind") == "end":
                break
        await task

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
