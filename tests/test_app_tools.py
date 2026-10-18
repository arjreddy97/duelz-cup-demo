"""The tool layer and the shared agent loop."""
import asyncio
import json

import pytest

from app import sandbox
from app.agent import Tools, build_task, parse_action, run_loop, truncate
from app.gemini import Meter


def run(coro):
    return asyncio.run(coro)


def act(tools, **action):
    return run(tools.execute(action))[0]


# ---------------------------------------------------------------- parsing
def test_parse_action_variants():
    assert parse_action('{"action": "list_files"}')["action"] == "list_files"
    assert parse_action('```json\n{"action": "run_tests"}\n```')["action"] == "run_tests"
    assert parse_action('Sure! {"action": "finish", "summary": "x"} done')["action"] == "finish"
    assert parse_action('[{"action": "read_file", "path": "a"}, {"action": "finish"}]')["path"] == "a"
    for bad in ("", "hello", '{"path": "x"}', "[1, 2]", "{broken"):
        with pytest.raises(ValueError):
            parse_action(bad)


def test_truncate():
    assert truncate("abc", 10) == "abc"
    out = truncate("x" * 50, 10)
    assert out.startswith("x" * 10) and "truncated 40 chars" in out


# ---------------------------------------------------------------- paths
def test_read_file_numbers_lines_and_ranges(ws):
    t = Tools(ws, sandbox.source_files(ws))
    out = act(t, action="read_file", path="./invoicer/paging.py", start_line=2, end_line=3)
    assert out.startswith("invoicer/paging.py (lines 2-3 of")
    assert "   2| from dataclasses import dataclass" in out
    assert "   1|" not in out and "   4|" not in out


@pytest.mark.parametrize("path", ["../secret.txt", "/etc/passwd", "~/.ssh/id_rsa", "invoicer/../../x.py",
                                  "tests/../../report.json", ""])
def test_paths_outside_the_project_are_refused(ws, path):
    (ws.parent / "secret.txt").write_text("nope")
    t = Tools(ws, sandbox.source_files(ws))
    for action in ("read_file", "write_file", "replace"):
        out = act(t, action=action, path=path, content="x", old="a", new="b")
        assert out.startswith("Error:"), (action, path, out)
    assert (ws.parent / "secret.txt").read_text() == "nope"


def test_tests_and_config_are_read_only(ws):
    t = Tools(ws, sandbox.source_files(ws))
    before = sandbox.read(ws, "tests/test_money.py")
    out = act(t, action="write_file", path="tests/test_money.py", content="def test_x(): pass\n")
    assert "read-only" in out
    out = act(t, action="replace", path="tests/test_money.py", old="import", new="#")
    assert "read-only" in out
    assert sandbox.read(ws, "tests/test_money.py") == before
    assert act(t, action="write_file", path="pytest.ini", content="").startswith("Error: you may only edit")
    assert act(t, action="write_file", path="invoicer/new_module.py", content="").startswith("Error:")
    assert not (ws / "invoicer/new_module.py").exists()
    assert t.changed == set()


def test_branch_may_write_only_its_own_file(ws):
    t = Tools(ws, ["invoicer/paging.py"])
    before = sandbox.read(ws, "invoicer/money.py")
    out = act(t, action="write_file", path="invoicer/money.py", content="x = 1\n")
    assert out == "Error: you may only edit: invoicer/paging.py"
    assert sandbox.read(ws, "invoicer/money.py") == before
    out = act(t, action="replace", path="invoicer/paging.py",
              old="return total // per_page + 1", new="return -(-total // per_page)")
    assert out == "edited invoicer/paging.py"
    assert t.changed == {"invoicer/paging.py"}
    # Reading other files is fine.
    assert "def to_money" in act(t, action="read_file", path="invoicer/money.py")


def test_replace_needs_a_unique_exact_match(ws):
    t = Tools(ws, sandbox.source_files(ws))
    assert "not found" in act(t, action="replace", path="invoicer/paging.py", old="   1| x", new="y")
    assert "occurs" in act(t, action="replace", path="invoicer/paging.py", old="per_page", new="n")
    assert "required" in act(t, action="replace", path="invoicer/paging.py", old="", new="n")
    assert act(t, action="nonsense").startswith("Error: unknown action")


def test_list_files_marks_editable(ws):
    t = Tools(ws, ["invoicer/money.py"])
    out = act(t, action="list_files")
    assert "invoicer/money.py  (editable)" in out
    assert "invoicer/dates.py\n" in out + "\n"
    assert "tests/test_money.py" in out and "__pycache__" not in out


# ---------------------------------------------------------------- run_tests
@pytest.mark.parametrize("bad", ["--version", "-p evil", "tests/../x.py", "/tmp/test_x.py", "tests/test_a.py;rm"])
def test_run_tests_rejects_non_test_selectors(ws, bad):
    t = Tools(ws, sandbox.source_files(ws))
    assert act(t, action="run_tests", tests=[bad]).startswith("Error: not a test id")


def test_run_tests_in_a_branch_only_runs_its_scope(ws):
    scope = ["tests/test_paging.py::test_page_counts", "tests/test_paging.py::test_report_footer"]
    t = Tools(ws, ["invoicer/paging.py"], test_scope=scope)
    out = act(t, action="run_tests")
    assert out.startswith("0 passed, 2 failed")
    out = act(t, action="run_tests", tests=["tests/test_money.py"])
    assert "outside this task" in out and "0 passed, 2 failed" in out
    out = act(t, action="run_tests", tests="tests/test_paging.py::test_page_counts")
    assert out.startswith("0 passed, 1 failed")


def test_run_tests_whole_suite_lists_every_failure(ws):
    t = Tools(ws, sandbox.source_files(ws))
    out = act(t, action="run_tests")
    assert out.startswith("21 passed, 22 failed")
    assert out.count("FAILED tests/") == 22


# ---------------------------------------------------------------- loop
def test_loop_context_grows_and_output_is_truncated(ws, scripted):
    model = scripted(['{"action": "run_tests"}', '{"action": "read_file", "path": "invoicer/money.py"}',
                      '{"action": "finish", "summary": "ok"}'])
    t = Tools(ws, sandbox.source_files(ws), output_chars=300)
    turns = []

    async def on_turn(turn, name, arg, usage):
        turns.append((turn, name, usage.prompt))

    res = run(run_loop(model, "task", t, Meter(), 10, 1.0, on_turn))
    assert (res.finished, res.stop, res.turns) == (True, "finish", 3)
    assert [n for _, n, _ in turns] == ["run_tests", "read_file", "finish"]
    sizes = [len(c) for c in model.sent]
    assert sizes == [1, 3, 5]  # task, then +model reply +tool output each turn
    prompts = [p for _, _, p in turns]
    assert prompts[0] < prompts[1] < prompts[2]
    tool_out = model.sent[1][2]["text"]
    assert "truncated" in tool_out and len(tool_out) < 300 + 120
    assert "turn(s) left" in tool_out


def test_loop_stops_at_turn_cap(ws, scripted):
    model = scripted(['{"action": "list_files"}'] * 10)
    res = run(run_loop(model, "task", Tools(ws, []), Meter(), 4, 1.0))
    assert (res.finished, res.stop, res.turns) == (False, "turn cap", 4)


def test_loop_stops_at_budget_cap(ws, scripted):
    # Each call: ~1M prompt tokens = $0.75, so a $1 cap allows two calls.
    model = scripted(['{"action": "list_files"}'] * 10, prompt=1_000_000)
    meter = Meter()
    res = run(run_loop(model, "task", Tools(ws, []), meter, 10, 1.0))
    assert (res.stop, res.turns, meter.calls) == ("budget cap", 2, 2)


def test_loop_survives_bad_json_and_reports_model_errors(ws, scripted):
    model = scripted(["not json", RuntimeError("402 credits depleted")])
    res = run(run_loop(model, "task", Tools(ws, []), Meter(), 10, 1.0))
    assert "reply was not JSON" in model.sent[1][2]["text"]
    assert res.stop.startswith("model error: RuntimeError: 402")
    assert res.turns == 1


def test_build_task_scopes():
    failures = [{"nodeid": "tests/test_paging.py::test_page_counts", "text": "x\nE   assert 1 == 2\n"}]
    single = build_task(failures, None, scoped=False, files={"invoicer/paging.py": "code\n"})
    assert "You may edit: any file in invoicer/." in single
    assert "- tests/test_paging.py::test_page_counts: assert 1 == 2" in single
    assert "--- invoicer/paging.py ---\ncode" in single
    branch = build_task(failures, ["invoicer/paging.py"], scoped=True, retry=True)
    assert "You may edit: only invoicer/paging.py." in branch
    assert "only these failing tests" in branch and "earlier attempt" in branch
    json.dumps(branch)


def test_gemini_wrapper_meters_implicit_cache_hits():
    """The real-model path, with the network call replaced: usage parsing and cost."""
    from types import SimpleNamespace

    from google.genai import types

    from app.gemini import GeminiModel

    seen = {}

    async def generate_content(model, contents, config):
        seen.update(model=model, n=len(contents), schema=config.response_json_schema)
        usage = SimpleNamespace(prompt_token_count=10_000, cached_content_token_count=8_000,
                                candidates_token_count=50, thoughts_token_count=150)
        return SimpleNamespace(text='{"action": "list_files"}', usage_metadata=usage)

    m = object.__new__(GeminiModel)
    m._types = types
    m._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    text, usage = run(m.generate([{"role": "user", "text": "t"}, {"role": "model", "text": "{}"}], "sys"))
    assert parse_action(text)["action"] == "list_files"
    assert (usage.prompt, usage.cached, usage.output) == (10_000, 8_000, 200)
    assert seen["n"] == 2 and seen["schema"]["required"] == ["action"]
    meter = Meter()
    meter.add(usage, 1.0)
    assert (meter.input_tokens, meter.cached_tokens, meter.output_tokens) == (2_000, 8_000, 200)
    assert meter.cost_usd == pytest.approx((2_000 * 0.75 + 8_000 * 0.075 + 200 * 3.75) / 1e6)
