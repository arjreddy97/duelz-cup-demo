"""A small tool-using agent loop, shared by both demo modes.

Each turn the model answers with ONE JSON action. The harness runs it and appends
the model's reply and the tool output to the conversation, so the context the
model is sent grows turn by turn, as in real coding agents.

All safety lives in `Tools`: paths must stay inside the throwaway workspace,
tests are read-only, and a branch may only write the files it was given.
"""
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import sandbox

SYSTEM = """You are a coding agent fixing bugs in a small Python project so that its pytest tests pass.
Reply each turn with exactly ONE JSON object: {"thought": "<one short sentence>", "action": "<name>", ...args}.
Actions:
- list_files: {} - list project files.
- read_file: {"path", "start_line"?, "end_line"?} - file contents with line numbers (numbers are not part of the file).
- run_tests: {"tests"?: [node ids or test files]} - run pytest; no tests = everything you are allowed to run.
- replace: {"path", "old", "new"} - replace text that occurs exactly once in the file (copy it exactly, without line numbers).
- write_file: {"path", "content"} - overwrite a whole file.
- finish: {"summary"} - stop when the failing tests pass.
Tests are read-only: fix the source code, never the tests. Prefer small replace edits. Run the tests before you finish."""

READ_LIMIT_BYTES = 200_000
WRITE_LIMIT_CHARS = 100_000


class ToolError(Exception):
    pass


def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def parse_action(text):
    """Model reply -> action dict. Raises ValueError with a message for the model."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except ValueError:
        # Tolerate prose around a single JSON object.
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("reply was not JSON")
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            raise ValueError("reply was not valid JSON")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]  # one action per turn
    if not isinstance(data, dict) or not isinstance(data.get("action"), str):
        raise ValueError('reply had no "action" field')
    return data


def failure_line(f):
    """Short one-line reason for a failure (last 'E ' line of its traceback)."""
    lines = [ln.strip() for ln in f.get("text", "").splitlines()]
    errs = [ln[1:].strip() for ln in lines if ln.startswith("E ")]
    line = errs[-1] if errs else (lines[-1] if lines else "")
    return line[:160]


class Tools:
    """The agent's tools over one workspace.

    writable:   relative paths the agent may change (existing source files only).
    test_scope: if given, run_tests only ever runs these node ids.
    """

    def __init__(self, ws, writable, test_scope=None, output_chars=4000):
        self.ws = Path(ws)
        self.root = self.ws.resolve()
        self.writable = set(writable)
        self.test_scope = list(test_scope) if test_scope else None
        self.output_chars = output_chars
        self.changed = set()
        self.last_result = None

    # ---------------------------------------------------------------- paths
    def _resolve(self, path):
        if not isinstance(path, str) or not path.strip():
            raise ToolError("a path is required")
        p = path.strip().replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        if p.startswith("/") or p.startswith("~"):
            raise ToolError("use a path relative to the project root, e.g. invoicer/money.py")
        target = (self.ws / p).resolve()
        if target != self.root and self.root not in target.parents:
            raise ToolError("that path is outside the project")
        return target, target.relative_to(self.root).as_posix()

    def _check_writable(self, rel):
        if rel in self.writable:
            return
        name = rel.rsplit("/", 1)[-1]
        if rel.startswith("tests/") or name.startswith("test_") or name == "conftest.py":
            raise ToolError("tests are read-only; fix the source code instead")
        raise ToolError(f"you may only edit: {', '.join(sorted(self.writable))}")

    # ---------------------------------------------------------------- tools
    def list_files(self):
        out = []
        for p in sorted(self.ws.rglob("*")):
            rel = p.relative_to(self.ws).as_posix()
            if p.is_dir() or "__pycache__" in rel or any(part.startswith(".") for part in rel.split("/")):
                continue
            mark = "  (editable)" if rel in self.writable else ""
            out.append(f"{rel}{mark}")
        return "\n".join(out)

    def read_file(self, path, start_line=None, end_line=None):
        target, rel = self._resolve(path)
        if not target.is_file():
            raise ToolError(f"no such file: {rel}")
        if target.stat().st_size > READ_LIMIT_BYTES:
            raise ToolError("file too large")
        lines = target.read_text(errors="replace").splitlines()
        lo = max(int(start_line or 1), 1)
        hi = min(int(end_line or len(lines)), len(lines))
        body = "\n".join(f"{i:>4}| {lines[i - 1]}" for i in range(lo, hi + 1))
        return f"{rel} (lines {lo}-{hi} of {len(lines)})\n{body}"

    def _write(self, target, rel, content):
        if len(content) > WRITE_LIMIT_CHARS:
            raise ToolError("content too large")
        target.write_text(content)
        self.changed.add(rel)

    def replace(self, path, old, new):
        target, rel = self._resolve(path)
        self._check_writable(rel)
        if not isinstance(old, str) or not old:
            raise ToolError('"old" text is required')
        if not isinstance(new, str):
            raise ToolError('"new" text is required')
        text = target.read_text()
        n = text.count(old)
        if n == 0:
            raise ToolError(f"old text not found in {rel}; copy it exactly, without line numbers")
        if n > 1:
            raise ToolError(f"old text occurs {n} times in {rel}; include more surrounding lines")
        self._write(target, rel, text.replace(old, new, 1))
        return f"edited {rel}"

    def write_file(self, path, content):
        target, rel = self._resolve(path)
        self._check_writable(rel)
        if not isinstance(content, str):
            raise ToolError('"content" is required')
        self._write(target, rel, content)
        return f"wrote {rel} ({len(content.splitlines())} lines)"

    def _select_tests(self, tests):
        tests = [t.strip() for t in (tests or []) if isinstance(t, str) and t.strip()]
        bad = [t for t in tests if not sandbox.NODEID_RE.match(t)]
        if bad:
            raise ToolError(f"not a test id under tests/: {', '.join(bad[:3])}")
        if self.test_scope is None:
            return tests, ""
        if not tests:
            return self.test_scope, ""
        picked = [s for s in self.test_scope if any(s == t or s.startswith(t + "::") for t in tests)]
        if not picked:
            return self.test_scope, "(those are outside this task; ran this task's tests instead)\n"
        return picked, ""

    async def run_tests(self, tests=None):
        ids, note = self._select_tests(tests)
        result = await sandbox.run_pytest(self.ws, ids or None)
        self.last_result = result
        head = f"{result['passed']} passed, {result['failed']} failed"
        if result.get("timeout"):
            head += " (timed out)"
        listing = "".join(f"FAILED {f['nodeid']}\n" for f in result["failures"])
        details = "".join(f"\n__ {f['nodeid']} __\n{f['text'].rstrip()}\n" for f in result["failures"])
        return note + head + "\n" + listing + details

    async def execute(self, action):
        """Run one action. Returns (observation text, short argument label)."""
        name = action.get("action")
        try:
            if name == "list_files":
                return self.list_files(), ""
            if name == "read_file":
                path = action.get("path")
                rng = ""
                if action.get("start_line") or action.get("end_line"):
                    rng = f":{action.get('start_line') or 1}-{action.get('end_line') or ''}"
                return self.read_file(path, action.get("start_line"), action.get("end_line")), f"{path}{rng}"
            if name == "run_tests":
                tests = action.get("tests")
                if isinstance(tests, str):
                    tests = [tests]
                label = ", ".join(tests[:2]) + ("…" if len(tests or []) > 2 else "") if tests else ""
                return await self.run_tests(tests), label
            if name == "replace":
                return self.replace(action.get("path"), action.get("old"), action.get("new")), str(action.get("path"))
            if name == "write_file":
                return self.write_file(action.get("path"), action.get("content")), str(action.get("path"))
            return f"Error: unknown action {name!r}", ""
        except ToolError as exc:
            return f"Error: {exc}", str(action.get("path") or "")
        except (TypeError, ValueError) as exc:
            return f"Error: bad arguments ({exc})", ""


@dataclass
class LoopResult:
    turns: int = 0
    finished: bool = False
    stop: str = ""           # "finish", "turn cap", "budget cap", "model error: ..."
    summary: str = ""
    actions: list = field(default_factory=list)


async def run_loop(model, task, tools, meter, max_turns, budget_usd, on_turn=None):
    """Drive one agent conversation until it finishes, hits the turn cap or the budget cap.

    on_turn(turn, action_name, arg_label, usage) is awaited after every model call.
    """
    contents = [{"role": "user", "text": task}]
    res = LoopResult()
    for turn in range(1, max_turns + 1):
        if meter.cost_usd >= budget_usd:
            res.stop = "budget cap"
            return res
        t0 = time.monotonic()
        try:
            text, usage = await model.generate(contents, SYSTEM)
        except Exception as exc:
            res.stop = f"model error: {type(exc).__name__}: {str(exc)[:160]}"
            return res
        meter.add(usage, time.monotonic() - t0)
        res.turns = turn
        contents.append({"role": "model", "text": text.strip() or "{}"})
        try:
            action = parse_action(text)
        except ValueError as exc:
            name, arg = "invalid", ""
            obs = f"Error: {exc}. Reply with exactly one JSON action."
        else:
            name = action["action"]
            if name == "finish":
                res.actions.append(name)
                res.finished, res.stop = True, "finish"
                res.summary = str(action.get("summary") or "")[:300]
                if on_turn:
                    await on_turn(turn, name, "", usage)
                return res
            obs, arg = await tools.execute(action)
        res.actions.append(name)
        obs = truncate(obs, tools.output_chars)
        left = max_turns - turn
        contents.append({"role": "user", "text": f"[{name} result]\n{obs}\n[{left} turn(s) left]"})
        if on_turn:
            await on_turn(turn, name, arg, usage)
    res.stop = "turn cap"
    return res


PRELOAD_LIMIT_CHARS = 40_000


def build_task(failures, editable, scoped, retry=False, files=None):
    """The opening user message. Same wording for both modes; only the scope differs.

    files: optional {relative path: content} handed to the agent up front.
    """
    if editable is None:
        edit = f"any file in {sandbox.SOURCE_PKG}/"
    else:
        edit = "only " + ", ".join(editable)
    run = ("only these failing tests (this is your part of a larger job)" if scoped
           else "the whole suite, or the test ids you pass")
    lines = [f"- {f['nodeid']}: {failure_line(f)}" for f in failures]
    parts = [
        "Make the failing pytest tests below pass by fixing the source code.",
        f"Project: {sandbox.SOURCE_PKG}/ (the package) and tests/ (pytest tests, read-only).",
        f"You may edit: {edit}.",
        f"run_tests runs {run}.",
    ]
    if retry:
        parts.append("An earlier attempt did not make these pass. Start fresh: read the code before editing.")
    parts.append(f"Failing tests ({len(failures)}):")
    text = "\n".join(parts + lines)
    if files:
        blocks = "".join(f"\n--- {rel} ---\n{body.rstrip()}\n" for rel, body in files.items())
        text += "\n\nFiles in your scope (exact contents):" + truncate(blocks, PRELOAD_LIMIT_CHARS)
    return text
