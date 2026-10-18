"""The two demo modes. Both run the SAME agent loop (app/agent.py) with the same
tools, prompt wording and model settings; only the harness around it differs.

Events are plain dicts passed to `emit`; the web layer streams them to the page:
  node  {id, parent, state, label, detail}       a box in the live tree
  turn  {id, turn, max_turns, action, arg, prompt_tokens, cached_tokens, output_tokens}
  usage {meter snapshot}                         running totals for the lane
  done  {green, passed, total, wall_seconds, ...meter}
"""
import asyncio
import time

from . import config, sandbox
from .agent import Tools, build_task, run_loop
from .gemini import Meter, get_model


def _summary(r):
    return f"{r['passed']}/{r['total']} passing"


def _turn_reporter(emit, mode, nid, max_turns, meter):
    async def on_turn(turn, action, arg, usage):
        emit({"mode": mode, "kind": "turn", "id": nid, "turn": turn, "max_turns": max_turns,
              "action": action, "arg": arg[:80], "prompt_tokens": usage.prompt,
              "cached_tokens": usage.cached, "output_tokens": usage.output})
        emit({"mode": mode, "kind": "usage", **meter.snapshot()})
    return on_turn


def _loop_detail(res, extra=""):
    bits = [f"{res.turns} turn(s)", res.stop]
    if extra:
        bits.append(extra)
    return " · ".join(b for b in bits if b)


# --------------------------------------------------------------------------
# Mode 1: one agent, one conversation, the whole project and every failure
# --------------------------------------------------------------------------
async def single_agent(emit, model=None):
    mode = "single"
    model = model or get_model()
    meter = Meter()
    t0 = time.monotonic()
    ws = sandbox.new_workspace("demo-single-")
    try:
        first = await sandbox.run_pytest(ws)
        emit({"mode": mode, "kind": "node", "id": "root", "parent": None, "state": "red",
              "label": f"pytest: {first['failed']} failing", "detail": _summary(first)})
        max_turns = config.SINGLE_MAX_TURNS
        label = f"agent · all files · {first['failed']} failures"
        emit({"mode": mode, "kind": "node", "id": "agent", "parent": "root", "state": "work",
              "label": label, "detail": f"turn 0/{max_turns}"})
        tools = Tools(ws, sandbox.source_files(ws), output_chars=config.TOOL_OUTPUT_CHARS)
        files = None
        if config.PRELOAD_FILES:
            files = {rel: sandbox.read(ws, rel) for rel in sandbox.source_files(ws) + sandbox.test_files(ws)}
        task = build_task(first["failures"], editable=None, scoped=False, files=files)
        res = await run_loop(model, task, tools, meter, max_turns, config.MODE_MAX_USD,
                             _turn_reporter(emit, mode, "agent", max_turns, meter))
        result = await sandbox.run_pytest(ws)
        green = result["failed"] == 0
        emit({"mode": mode, "kind": "node", "id": "agent", "parent": "root",
              "state": "green" if green else "fail", "label": label,
              "detail": _loop_detail(res, f"edited {', '.join(sorted(tools.changed)) or 'nothing'}")})
        emit({"mode": mode, "kind": "node", "id": "root", "parent": None,
              "state": "green" if green else "red",
              "label": f"pytest: {first['failed']} failing", "detail": f"final: {_summary(result)}"})
        return _done(emit, mode, meter, t0, result, res.stop)
    finally:
        sandbox.drop_workspace(ws)


# --------------------------------------------------------------------------
# Mode 2: group failures by the source file their traceback bottoms out in,
# run one short agent loop per group in parallel, verify, retry once.
# --------------------------------------------------------------------------
async def split_verify(emit, model=None):
    mode = "split"
    model = model or get_model()
    meter = Meter()
    t0 = time.monotonic()
    ws = sandbox.new_workspace("demo-split-")
    pieces = []
    stops = []

    async def branch(nid, owner, group, max_turns, retry):
        failures = group["failures"]
        pws = sandbox.clone_workspace(ws)
        pieces.append(pws)
        writable = [owner] if owner else sandbox.source_files(pws)
        scope = [f["nodeid"] for f in failures if sandbox.NODEID_RE.match(f["nodeid"])]
        label = f"{'retry · ' if retry else ''}{owner or 'any source file'} · {len(failures)} test(s)"
        emit({"mode": mode, "kind": "node", "id": nid, "parent": "root", "state": "work",
              "label": label, "detail": f"grouped by {group['how']} · turn 0/{max_turns}"})
        tools = Tools(pws, writable, test_scope=scope or None, output_chars=config.TOOL_OUTPUT_CHARS)
        files = None
        if config.PRELOAD_FILES:
            tests = sorted({n.split("::")[0] for n in scope})
            files = {rel: sandbox.read(pws, rel) for rel in [*writable, *tests] if (pws / rel).is_file()}
        task = build_task(failures, editable=writable if owner else None, scoped=True, retry=retry,
                          files=files)
        res = await run_loop(model, task, tools, meter, max_turns, config.MODE_MAX_USD,
                             _turn_reporter(emit, mode, nid, max_turns, meter))
        stops.append(res.stop)
        # The harness checks the branch itself; the model's "finish" is not trusted.
        check = await sandbox.run_pytest(pws, scope or None)
        ok = check["failed"] == 0 and check["total"] > 0
        emit({"mode": mode, "kind": "node", "id": nid, "parent": "root",
              "state": "green" if ok else "fail", "label": label,
              "detail": _loop_detail(res, f"its tests: {_summary(check)}")})
        return {"owner": owner, "ws": pws, "ok": ok, "changed": tools.changed}

    def merge(outcomes):
        merged = []
        for o in outcomes:
            if not o["ok"]:
                continue
            for rel in sorted(o["changed"]):
                (ws / rel).write_text(sandbox.read(o["ws"], rel))
                merged.append(rel)
        return merged

    try:
        first = await sandbox.run_pytest(ws)
        groups = sandbox.group_failures(first["failures"], ws)
        emit({"mode": mode, "kind": "node", "id": "root", "parent": None, "state": "red",
              "label": f"pytest: {first['failed']} failing",
              "detail": f"{_summary(first)} · split into {len(groups)} group(s) by owning file"})

        outcomes = await asyncio.gather(*[
            branch(f"g{i}", owner, g, config.SPLIT_MAX_TURNS, False)
            for i, (owner, g) in enumerate(groups.items(), 1)])
        merged = merge(outcomes)

        emit({"mode": mode, "kind": "node", "id": "verify", "parent": "root", "state": "work",
              "label": "verify: full suite", "detail": f"merged {len(merged)} file(s)"})
        result = await sandbox.run_pytest(ws)
        emit({"mode": mode, "kind": "node", "id": "verify", "parent": "root",
              "state": "green" if result["failed"] == 0 else "red", "label": "verify: full suite",
              "detail": f"merged {len(merged)} file(s) · {_summary(result)}"})

        if result["failed"] and meter.cost_usd < config.MODE_MAX_USD:
            # One retry for whatever is still red, regrouped, each with a fresh short loop.
            regroups = sandbox.group_failures(result["failures"], ws)
            for p in pieces:
                sandbox.drop_workspace(p)
            pieces.clear()
            outcomes = await asyncio.gather(*[
                branch(f"r{i}", owner, g, config.SPLIT_RETRY_TURNS, True)
                for i, (owner, g) in enumerate(regroups.items(), 1)])
            merged = merge(outcomes)
            emit({"mode": mode, "kind": "node", "id": "final", "parent": "root", "state": "work",
                  "label": "verify again: full suite", "detail": f"merged {len(merged)} file(s)"})
            result = await sandbox.run_pytest(ws)
            emit({"mode": mode, "kind": "node", "id": "final", "parent": "root",
                  "state": "green" if result["failed"] == 0 else "red",
                  "label": "verify again: full suite",
                  "detail": f"merged {len(merged)} file(s) · {_summary(result)}"})

        green = result["failed"] == 0
        emit({"mode": mode, "kind": "node", "id": "root", "parent": None,
              "state": "green" if green else "red",
              "label": f"pytest: {first['failed']} failing",
              "detail": f"{len(groups)} group(s) · final: {_summary(result)}"})
        stop = "budget cap" if "budget cap" in stops else ""
        return _done(emit, mode, meter, t0, result, stop)
    finally:
        for p in pieces:
            sandbox.drop_workspace(p)
        sandbox.drop_workspace(ws)


def _done(emit, mode, meter, t0, result, stop=""):
    summary = {"mode": mode, "kind": "done", "green": result["failed"] == 0,
               "passed": result["passed"], "total": result["total"], "stop": stop,
               "budget_usd": config.MODE_MAX_USD,
               "wall_seconds": round(time.monotonic() - t0, 2), **meter.snapshot()}
    emit(summary)
    return summary
