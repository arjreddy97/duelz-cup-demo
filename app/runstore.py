"""Live-run results in Firestore (collection "live_runs").

One document per finished live run: a server timestamp, the model name, and per
mode the outcome and meter totals. Nothing about the visitor (no IP, no id).

Writes happen on a daemon thread with a short timeout and never raise, so a
slow or missing Firestore can't break or delay a run. Firestore is used only on
Cloud Run (K_SERVICE is set) or when DEMO_FIRESTORE=1, never with the fake
model, and DEMO_FIRESTORE=0 switches it off. Local dev needs no credentials.
"""
import logging
import os
import statistics
import threading
import time

from . import config

log = logging.getLogger("duelz.runstore")

COLLECTION = "live_runs"
TIMEOUT_SECONDS = 5.0
CACHE_SECONDS = 20.0
MODE_FIELDS = ("green", "passed", "total", "cost_usd", "wall_seconds", "input_tokens",
               "output_tokens", "cached_tokens", "calls", "max_prompt_tokens", "stop")

_client = None
_client_failed_at = 0.0
_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}


def enabled():
    flag = os.environ.get("DEMO_FIRESTORE")
    if config.FAKE_MODEL or flag == "0":
        return False
    return flag == "1" or bool(os.environ.get("K_SERVICE"))


def _get_client():
    """A Firestore client, or None if unavailable (retried at most once a minute)."""
    global _client, _client_failed_at
    if not enabled():
        return None
    with _lock:
        if _client is not None:
            return _client
        if time.time() - _client_failed_at < 60:
            return None
        try:
            from google.cloud import firestore  # lazy: tests and local dev never import it
            _client = firestore.Client(project=os.environ.get("DEMO_FIRESTORE_PROJECT") or None)
        except Exception as exc:
            _client_failed_at = time.time()
            log.warning("Firestore unavailable: %s", type(exc).__name__)
            return None
        return _client


# ---------------------------------------------------------------- record building (pure)
def mode_record(summary):
    """The stored fields for one mode, from its `done` summary (None/{} = errored)."""
    if not summary or summary.get("kind") == "error" or "passed" not in summary:
        return {"error": True}
    rec = {k: summary.get(k) for k in MODE_FIELDS}
    rec["stop"] = rec["stop"] or ""
    rec["turns"] = rec.pop("calls")
    return rec


def build_record(model, single, split):
    return {"model": model, "single": mode_record(single), "split": mode_record(split)}


# ---------------------------------------------------------------- aggregation/formatting (pure)
def cost_ratio(run):
    """split cost / single cost, or None if either mode errored or cost nothing."""
    a, b = run.get("single") or {}, run.get("split") or {}
    ca, cb = a.get("cost_usd"), b.get("cost_usd")
    if a.get("error") or b.get("error") or not ca or not cb or ca <= 0 or cb <= 0:
        return None
    return cb / ca


def ratio_label(r, less="less", more="more"):
    """0.66 -> '0.66x (34% less)', the way the comparison panel reports split vs single."""
    if r is None:
        return "n/a"
    pct = round(abs(1 - r) * 100)
    tail = "about even" if pct < 3 else f"{pct}% {less if r < 1 else more}"
    return f"{r:.2f}x ({tail})"


def both_green(run):
    return bool((run.get("single") or {}).get("green") and (run.get("split") or {}).get("green"))


def aggregate(runs):
    ratios = [r for r in (cost_ratio(x) for x in runs) if r is not None]
    median = statistics.median(ratios) if ratios else None
    return {"count": len(runs),
            "compared": len(ratios),
            "median_cost_ratio": round(median, 3) if median is not None else None,
            "median_cost_label": ratio_label(median),
            "split_cheaper": sum(1 for r in ratios if r < 1),
            "both_green": sum(1 for x in runs if both_green(x))}


def public_row(run):
    r = cost_ratio(run)
    return {"created": run.get("created"), "model": run.get("model"),
            "single": run.get("single") or {"error": True}, "split": run.get("split") or {"error": True},
            "cost_ratio": round(r, 3) if r is not None else None, "cost_label": ratio_label(r),
            "both_green": both_green(run)}


def summarize(runs, recent=10):
    """API payload: newest-first runs in, last `recent` rows + aggregates over all given."""
    return {"runs": [public_row(x) for x in runs[:recent]], "aggregate": aggregate(runs)}


# ---------------------------------------------------------------- I/O
def _write(record):
    client = _get_client()
    if client is None:
        return
    try:
        from google.cloud import firestore
        doc = dict(record, created=firestore.SERVER_TIMESTAMP)
        client.collection(COLLECTION).document().set(doc, timeout=TIMEOUT_SECONDS)
        _cache["at"] = 0.0  # next /api/runs shows the new run
    except Exception as exc:
        log.warning("live_runs write failed: %s: %s", type(exc).__name__, str(exc)[:200])


def save_run_async(record):
    """Fire-and-forget write; returns immediately and never raises."""
    if not enabled():
        return
    try:
        threading.Thread(target=_write, args=(record,), daemon=True).start()
    except Exception as exc:
        log.warning("live_runs write not started: %s", type(exc).__name__)


def _fetch(limit):
    client = _get_client()
    if client is None:
        return []
    from google.cloud import firestore
    q = (client.collection(COLLECTION).order_by("created", direction=firestore.Query.DESCENDING)
         .limit(limit))
    out = []
    for snap in q.stream(timeout=TIMEOUT_SECONDS):
        d = snap.to_dict() or {}
        created = d.get("created")
        d["created"] = created.timestamp() if hasattr(created, "timestamp") else None
        out.append(d)
    return out


def recent_summary(limit=50, recent=10):
    """Cached ~20 s. Empty when Firestore is off or failing."""
    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    try:
        runs = _fetch(limit)
    except Exception as exc:
        log.warning("live_runs read failed: %s: %s", type(exc).__name__, str(exc)[:200])
        runs = []
    data = dict(summarize(runs, recent), stored=enabled())
    _cache.update(at=now, data=data)
    return data
