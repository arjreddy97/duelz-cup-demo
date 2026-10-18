"""Both modes end to end with the scripted fake model (no API calls), plus the web API."""
import asyncio
import json

import pytest

from app import config, main, modes
from devtools.fake_model import FakeModel


def run_mode(fn, model):
    events = []
    summary = asyncio.run(fn(events.append, model))
    return summary, events


def turns_of(events, nid=None):
    return [e for e in events if e["kind"] == "turn" and (nid is None or e["id"] == nid)]


def test_single_agent_one_growing_conversation():
    summary, events = run_mode(modes.single_agent, FakeModel(latency=0))
    assert summary["green"] and (summary["passed"], summary["total"]) == (43, 43)
    turns = turns_of(events)
    assert {t["id"] for t in turns} == {"agent"}
    assert len(turns) == summary["calls"] > 10
    assert [t["turn"] for t in turns] == list(range(1, len(turns) + 1))
    prompts = [t["prompt_tokens"] for t in turns]
    assert prompts == sorted(prompts) and prompts[-1] > prompts[0]
    assert all(t["max_turns"] == config.SINGLE_MAX_TURNS for t in turns)
    usage = [e for e in events if e["kind"] == "usage"]
    assert usage and usage[-1]["calls"] == summary["calls"]
    assert summary["cost_usd"] > 0 and summary["max_prompt_tokens"] == prompts[-1]


def test_split_runs_short_parallel_branches():
    summary, events = run_mode(modes.split_verify, FakeModel(latency=0))
    assert summary["green"] and summary["passed"] == 43
    branches = {e["id"] for e in events if e["kind"] == "node" and e["id"].startswith("g")}
    assert branches == {f"g{i}" for i in range(1, 7)}
    for b in branches:
        n = len(turns_of(events, b))
        assert 1 < n <= config.SPLIT_MAX_TURNS
    final = [e for e in events if e["kind"] == "node" and e["id"] == "verify"][-1]
    assert final["state"] == "green"
    assert not any(e["id"] in ("r1", "final") for e in events if e["kind"] == "node")


def test_split_prompts_stay_smaller_than_single():
    single, _ = run_mode(modes.single_agent, FakeModel(latency=0))
    split, _ = run_mode(modes.split_verify, FakeModel(latency=0))
    assert split["max_prompt_tokens"] * 3 < single["max_prompt_tokens"]
    assert split["cost_usd"] < single["cost_usd"]


def test_split_retries_a_still_red_group_once():
    summary, events = run_mode(modes.split_verify, FakeModel(latency=0, fail_once=["invoicer/paging.py"]))
    nodes = {e["id"]: e for e in events if e["kind"] == "node"}  # last state per id
    assert nodes["verify"]["state"] == "red"
    assert nodes["r1"]["state"] == "green" and "invoicer/paging.py" in nodes["r1"]["label"]
    assert nodes["final"]["state"] == "green"
    assert summary["green"]
    assert all(t["max_turns"] == config.SPLIT_RETRY_TURNS for t in turns_of(events, "r1"))


def test_turn_cap_leaves_single_agent_red(monkeypatch):
    monkeypatch.setattr(config, "SINGLE_MAX_TURNS", 5)
    summary, events = run_mode(modes.single_agent, FakeModel(latency=0))
    assert not summary["green"] and summary["calls"] == 5 and summary["stop"] == "turn cap"


@pytest.mark.parametrize("fn", [modes.single_agent, modes.split_verify])
def test_budget_cap_stops_each_mode(monkeypatch, fn):
    monkeypatch.setattr(config, "MODE_MAX_USD", 0.005)
    summary, _ = run_mode(fn, FakeModel(latency=0))
    assert summary["stop"] == "budget cap" and not summary["green"]
    # A mode may overshoot by at most one call per parallel loop (~$0.01 each here).
    assert summary["cost_usd"] < 0.005 + 6 * 0.01


def test_workspaces_are_cleaned_up(monkeypatch):
    made = []
    real_new, real_clone = modes.sandbox.new_workspace, modes.sandbox.clone_workspace
    monkeypatch.setattr(modes.sandbox, "new_workspace", lambda p: made.append(real_new(p)) or made[-1])
    monkeypatch.setattr(modes.sandbox, "clone_workspace", lambda s: made.append(real_clone(s)) or made[-1])
    run_mode(modes.split_verify, FakeModel(latency=0, fail_once=["invoicer/money.py"]))
    run_mode(modes.single_agent, FakeModel(latency=0))
    assert len(made) > 7 and not any(p.parent.exists() for p in made)


# ---------------------------------------------------------------- web API
@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config, "FAKE_MODEL", True)
    monkeypatch.setenv("DEMO_FAKE_LATENCY", "0")
    monkeypatch.setattr(main, "limiter", main.Limiter())
    return TestClient(main.app)


def test_api_streams_both_modes_and_rate_limits(client):
    cfg = client.get("/api/config").json()
    assert cfg["fake_model"] and cfg["live"] and cfg["single_max_turns"] == config.SINGLE_MAX_TURNS
    events = []
    with client.stream("POST", "/api/run") as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert events[0] == {"kind": "start", "model": "scripted fake model"}
    assert events[-1] == {"kind": "end"}
    done = {e["mode"]: e for e in events if e["kind"] == "done"}
    assert done["single"]["green"] and done["split"]["green"]
    assert not [e for e in events if e["kind"] == "error"]
    assert {e["mode"] for e in events if e["kind"] == "turn"} == {"single", "split"}
    again = client.post("/api/run")
    assert again.status_code == 429 and "per minute" in again.json()["error"]


def test_api_refuses_without_key_or_fake(client, monkeypatch):
    monkeypatch.setattr(config, "FAKE_MODEL", False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/api/run")
    assert r.status_code == 429 and "not configured" in r.json()["error"]
    assert client.get("/api/config").json()["live"] is False
