"""A scripted stand-in for Gemini, for local testing only (DEMO_FAKE_MODEL=1).

It reads the task in the conversation, plays a plausible sequence of tool actions
(look around, read the test and the source, apply the known reference fix, run
the tests, finish) and replies with the same JSON the real model would send, so
the whole loop, the tool layer, the tree events and the meters are exercised.

Token counts are estimates (about 4 characters per token): prompt = everything
sent this call, output = the reply plus a fixed thinking allowance. Not real
Gemini numbers. Set DEMO_FAKE_CACHE=1 to pretend Gemini's implicit cache served
the previous turn's prefix (the best case for a long conversation).

Knobs: DEMO_FAKE_LATENCY (seconds per call, default 0.4), DEMO_FAKE_CACHE,
DEMO_FAKE_FAIL_ONCE (comma-separated source files whose first attempt skips the fix).
"""
import asyncio
import json
import os
import re

from app.gemini import Usage

from .reference_fixes import FIXES

THINKING_TOKENS = 120
MIN_CACHE_TOKENS = 1024


def _tokens(text):
    return max(1, len(text) // 4)


def _test_file(src):
    stem = src.rsplit("/", 1)[-1].removesuffix(".py")
    return f"tests/test_{stem}.py"


class FakeModel:
    name = "fake"

    def __init__(self, latency=0.4, cache=False, fail_once=()):
        self.latency = latency
        self.cache = cache
        self.fail_once = set(fail_once)

    @classmethod
    def from_env(cls):
        fail = [f.strip() for f in os.environ.get("DEMO_FAKE_FAIL_ONCE", "").split(",") if f.strip()]
        return cls(latency=float(os.environ.get("DEMO_FAKE_LATENCY", "0.4")),
                   cache=os.environ.get("DEMO_FAKE_CACHE") == "1", fail_once=fail)

    # ------------------------------------------------------------ the script
    def _plan(self, task):
        retry = "earlier attempt" in task
        m = re.search(r"You may edit: only (.+)\.\n", task)
        if m:
            targets = [p.strip() for p in m.group(1).split(",")]
        else:
            seen = []
            for tid in re.findall(r"^- (tests/test_\w+\.py)", task, re.M):
                src = "invoicer/" + tid.split("/")[-1][5:]
                if src in FIXES and src not in seen:
                    seen.append(src)
            targets = seen
        scoped = "only these failing tests" in task
        preloaded = set(re.findall(r"^--- (\S+) ---$", task, re.M))
        steps = [] if scoped else [{"thought": "See every failure.", "action": "run_tests"}]
        if not scoped and not preloaded:
            steps.insert(0, {"thought": "Look at the layout first.", "action": "list_files"})
        for i, src in enumerate(targets):
            test = _test_file(src)
            if (scoped or i % 2 == 0) and test not in preloaded:
                steps.append({"thought": f"What do the tests in {test} expect?",
                              "action": "read_file", "path": test})
            if src not in preloaded:
                steps.append({"thought": f"Read {src}.", "action": "read_file", "path": src})
            elif not scoped:
                steps.append({"thought": f"Check the failure details for {test}.", "action": "run_tests",
                              "tests": [test]})
            if src in self.fail_once and not retry:
                steps.append({"thought": "Not sure yet; check the tests again.", "action": "run_tests",
                              **({} if scoped else {"tests": [test]})})
                continue
            for old, new in FIXES.get(src, []):
                steps.append({"thought": f"Fix the bug in {src}.", "action": "replace",
                              "path": src, "old": old, "new": new})
            steps.append({"thought": "Re-run those tests.", "action": "run_tests",
                          **({} if scoped else {"tests": [test]})})
        if not scoped:
            steps.append({"thought": "Run the whole suite before finishing.", "action": "run_tests"})
        steps.append({"thought": "Done.", "action": "finish", "summary": f"fixed {', '.join(targets)}"})
        return steps

    async def generate(self, contents, system):
        plan = self._plan(contents[0]["text"])
        k = sum(1 for c in contents if c["role"] == "model")
        action = plan[k] if k < len(plan) else {"action": "finish", "summary": "out of ideas"}
        text = json.dumps(action)
        prompt = _tokens(system) + sum(_tokens(c["text"]) for c in contents)
        cached = 0
        if self.cache and len(contents) > 1:
            prefix = _tokens(system) + sum(_tokens(c["text"]) for c in contents[:-1])
            cached = prefix if prefix >= MIN_CACHE_TOKENS else 0
        if self.latency:
            await asyncio.sleep(self.latency * (1 + prompt / 20000))
        return text, Usage(prompt=prompt, cached=cached, output=_tokens(text) + THINKING_TOKENS)
