"""Tiny pytest plugin: writes each test's outcome and traceback file list to JSON.

Loaded with `-p demo_report`; the output path comes from DEMO_REPORT_PATH.
"""
import json
import os

import pytest

_results = []


def _frames(excinfo, rootdir):
    out = []
    if excinfo is None:
        return out
    try:
        for entry in excinfo.traceback:
            path = str(entry.path)
            if path.startswith(rootdir):
                out.append(os.path.relpath(path, rootdir))
    except Exception:
        pass
    exc = excinfo.value
    if isinstance(exc, SyntaxError) and exc.filename:
        path = str(exc.filename)
        if path.startswith(rootdir):
            out.append(os.path.relpath(path, rootdir))
    return out


def _text(report, limit=1500):
    text = str(report.longrepr) if report.longrepr else ""
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"



@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    rootdir = str(item.config.rootpath)
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _results.append({
            "nodeid": report.nodeid,
            "outcome": report.outcome,
            "frames": _frames(call.excinfo, rootdir) if report.failed else [],
            "text": _text(report) if report.failed else "",
        })


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        rootdir = str(collector.config.rootpath)
        frames = []
        text = _text(report)
        # Collection errors: name any project file mentioned in the error text.
        for line in text.splitlines():
            for token in line.replace('"', " ").replace(":", " ").split():
                if token.endswith(".py"):
                    path = token if os.path.isabs(token) else os.path.join(rootdir, token)
                    if os.path.exists(path) and path.startswith(rootdir):
                        frames.append(os.path.relpath(path, rootdir))
        _results.append({"nodeid": report.nodeid, "outcome": "failed",
                         "frames": frames, "text": text})


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("DEMO_REPORT_PATH")
    if path:
        with open(path, "w") as fh:
            json.dump(_results, fh)
