"""Live-run storage: record building, aggregation, formatting, and the API without Firestore."""
from app import config, runstore


def done(cost, wall=10.0, green=True, stop=""):
    return {"mode": "x", "kind": "done", "green": green, "passed": 43 if green else 30, "total": 43,
            "stop": stop, "budget_usd": 0.25, "wall_seconds": wall, "calls": 7, "input_tokens": 1000,
            "cached_tokens": 200, "output_tokens": 50, "model_seconds": 3.0, "max_prompt_tokens": 900,
            "cost_usd": cost}


def test_record_keeps_only_run_fields():
    rec = runstore.build_record("gemini-3.8-flash", done(0.10), None)
    assert rec["model"] == "gemini-3.8-flash"
    assert rec["split"] == {"error": True}
    s = rec["single"]
    assert set(s) == {"green", "passed", "total", "cost_usd", "wall_seconds", "input_tokens", "output_tokens",
                      "cached_tokens", "turns", "max_prompt_tokens", "stop"}
    assert s["turns"] == 7 and s["stop"] == "" and s["cost_usd"] == 0.10


def test_ratio_label_matches_comparison_panel():
    assert runstore.ratio_label(0.66) == "0.66x (34% less)"
    assert runstore.ratio_label(1.25) == "1.25x (25% more)"
    assert runstore.ratio_label(0.99) == "0.99x (about even)"
    assert runstore.ratio_label(None) == "n/a"


def test_aggregate_and_summary():
    runs = [runstore.build_record("m", done(0.10), done(0.05)),            # 0.5x, both green
            runstore.build_record("m", done(0.10), done(0.20, green=False)),  # 2.0x
            runstore.build_record("m", done(0.10), done(0.08)),            # 0.8x, both green
            runstore.build_record("m", None, done(0.08))]                  # single errored
    agg = runstore.aggregate(runs)
    assert agg["count"] == 4 and agg["compared"] == 3
    assert agg["median_cost_ratio"] == 0.8 and agg["median_cost_label"] == "0.80x (20% less)"
    assert agg["split_cheaper"] == 2 and agg["both_green"] == 2

    out = runstore.summarize(runs, recent=2)
    assert len(out["runs"]) == 2
    assert out["runs"][0]["cost_label"] == "0.50x (50% less)" and out["runs"][0]["both_green"]
    assert out["runs"][1]["both_green"] is False
    assert runstore.aggregate([])["median_cost_label"] == "n/a"


def test_disabled_with_fake_model_and_locally(monkeypatch):
    monkeypatch.setattr(config, "FAKE_MODEL", True)
    monkeypatch.setenv("DEMO_FIRESTORE", "1")
    assert not runstore.enabled()
    monkeypatch.setattr(config, "FAKE_MODEL", False)
    monkeypatch.delenv("DEMO_FIRESTORE")
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert not runstore.enabled()
    runstore.save_run_async({"model": "m"})  # no-op, no error


def test_api_runs_empty_without_firestore(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("DEMO_FIRESTORE", raising=False)
    monkeypatch.setitem(runstore._cache, "data", None)
    r = TestClient(main.app).get("/api/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["runs"] == [] and body["aggregate"]["count"] == 0 and body["stored"] is False


def test_failed_read_keeps_last_good_and_never_says_empty(monkeypatch):
    monkeypatch.setenv("DEMO_FIRESTORE", "1")
    monkeypatch.setattr(config, "FAKE_MODEL", False)
    monkeypatch.setattr(runstore, "_cache", {"at": 0.0, "data": None})
    good = [runstore.build_record("m", done(0.10), done(0.05))]
    calls = []

    def fetch(limit):
        calls.append(limit)
        if len(calls) == 1:
            raise TimeoutError("cold instance")
        if len(calls) == 2:
            return good
        raise TimeoutError("again")

    monkeypatch.setattr(runstore, "_fetch", fetch)
    first = runstore.recent_summary()
    assert first["ok"] is False and first["runs"] == []        # page shows "loading", not "no runs"
    assert runstore._cache["data"] is None                      # the failure is not cached
    second = runstore.recent_summary()
    assert second["ok"] is True and len(second["runs"]) == 1
    monkeypatch.setitem(runstore._cache, "at", 0.0)             # cache expired
    assert runstore.recent_summary() is second                  # failed refresh: last good read


def test_busy_read_gives_up_after_the_wait(monkeypatch):
    monkeypatch.setattr(runstore, "BUSY_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(runstore, "_cache", {"at": 0.0, "data": None})
    monkeypatch.setattr(runstore, "_fetch", lambda limit: (_ for _ in ()).throw(AssertionError("no second read")))
    assert runstore._reading.acquire(blocking=False)
    try:
        assert runstore.recent_summary()["ok"] is False
    finally:
        runstore._reading.release()


def test_no_client_while_enabled_is_a_failure(monkeypatch):
    monkeypatch.setenv("DEMO_FIRESTORE", "1")
    monkeypatch.setattr(config, "FAKE_MODEL", False)
    monkeypatch.setattr(runstore, "_cache", {"at": 0.0, "data": None})
    monkeypatch.setattr(runstore, "_get_client", lambda: None)
    out = runstore.recent_summary()
    assert out["ok"] is False and out["stored"] is True


def test_query_makes_one_attempt(monkeypatch):
    seen = {}

    class Query:
        def order_by(self, *a, **k):
            return self

        def limit(self, n):
            return self

        def stream(self, **kw):
            seen.update(kw)
            return iter(())

    class Client:
        def collection(self, name):
            return Query()

    monkeypatch.setattr(runstore, "_get_client", lambda: Client())
    import sys, types
    fake = types.SimpleNamespace(Query=types.SimpleNamespace(DESCENDING="DESC"))
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", fake)
    assert runstore._fetch(5) == []
    assert seen["timeout"] == runstore.TIMEOUT_SECONDS
    assert seen["retry"]._predicate(TimeoutError()) is False


def test_busy_read_waits_for_the_read_in_flight(monkeypatch):
    import threading
    import time as _time
    monkeypatch.setattr(runstore, "_cache", {"at": 0.0, "data": None})
    monkeypatch.setattr(runstore, "_fetch", lambda limit: (_ for _ in ()).throw(AssertionError("no second read")))
    good = dict(runstore.summarize([runstore.build_record("m", done(0.10), done(0.05))]), stored=True, ok=True)
    assert runstore._reading.acquire(blocking=False)

    def finish_first_read():
        _time.sleep(0.2)
        runstore._cache.update(at=_time.time(), data=good)
        runstore._reading.release()

    threading.Thread(target=finish_first_read).start()
    assert runstore.recent_summary() is good  # waited, then served the other read's result
