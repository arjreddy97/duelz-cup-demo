"""Run pytest on a throwaway copy of the bundled sample project.

Only the bundled sample project is ever executed. Each run gets its own temp
copy, a stripped environment (no API keys), CPU/memory limits and a timeout.
"""
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "sample_project"
PLUGIN_DIR = Path(__file__).resolve().parent / "pytest_plugin"
SOURCE_PKG = "invoicer"
PYTEST_TIMEOUT = int(os.environ.get("DEMO_PYTEST_TIMEOUT", "30"))
# Keep CPU light: at most this many pytest processes at once (per event loop).
PYTEST_CONCURRENCY = int(os.environ.get("DEMO_PYTEST_CONCURRENCY", "3"))
# What a test selector from the model may look like: a test file or node id under tests/.
NODEID_RE = re.compile(r"^tests/[A-Za-z0-9_/]+\.py(::[A-Za-z0-9_\[\]\-.]+)*$")
_sems = {}


def _pytest_slot():
    loop = asyncio.get_running_loop()
    sem = _sems.get(loop)
    if sem is None:
        _sems.clear()  # old loops (tests) are gone
        sem = _sems[loop] = asyncio.Semaphore(PYTEST_CONCURRENCY)
    return sem


def new_workspace(prefix="demo-"):
    """Fresh temp copy of the sample project. Returns its path."""
    base = Path(tempfile.mkdtemp(prefix=prefix))
    dest = base / "project"
    shutil.copytree(SAMPLE, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dest


def clone_workspace(src):
    base = Path(tempfile.mkdtemp(prefix="demo-piece-"))
    dest = base / "project"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dest


def drop_workspace(path):
    shutil.rmtree(Path(path).parent, ignore_errors=True)


def source_files(ws):
    """Relative paths of the editable source files (never tests)."""
    return sorted(str(p.relative_to(ws)) for p in (ws / SOURCE_PKG).glob("*.py"))


def test_files(ws):
    return sorted(str(p.relative_to(ws)) for p in (ws / "tests").glob("test_*.py"))


def read(ws, rel):
    return (ws / rel).read_text()


def write_source(ws, rel, content, allowed):
    """Write a model-proposed file, but only if it is in the allowed set."""
    if rel not in allowed:
        return False
    target = (ws / rel).resolve()
    if not str(target).startswith(str(ws.resolve()) + os.sep):
        return False
    target.write_text(content)
    return True


def _limits():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (PYTEST_TIMEOUT, PYTEST_TIMEOUT))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except Exception:
        pass


async def run_pytest(ws, nodeids=None):
    """Run pytest in ws. Returns {passed, failed, total, failures:[...], timeout}."""
    nodeids = [n for n in (nodeids or []) if NODEID_RE.match(n)]
    async with _pytest_slot():
        return await _run_pytest(ws, nodeids)


async def _run_pytest(ws, nodeids):
    report = ws.parent / "report.json"
    if report.exists():
        report.unlink()
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(ws.parent),
        "PYTHONPATH": str(PLUGIN_DIR),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DEMO_REPORT_PATH": str(report),
    }
    args = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-p", "demo_report", "--", *nodeids]
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=str(ws), env=env, preexec_fn=_limits,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=PYTEST_TIMEOUT + 5)
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        await proc.wait()
    results = []
    if report.exists():
        try:
            results = json.loads(report.read_text())
        except ValueError:
            results = []
    failures = [r for r in results if r["outcome"] == "failed"]
    passed = sum(1 for r in results if r["outcome"] == "passed")
    if timed_out or (not results and proc.returncode not in (0, None)):
        failures = failures or [{"nodeid": "<session>", "outcome": "failed", "frames": [],
                                 "text": "pytest timed out" if timed_out else "pytest crashed"}]
    return {"passed": passed, "failed": len(failures), "total": passed + len(failures),
            "failures": failures, "timeout": timed_out}


def owner_file(failure, ws):
    """The source file a failure's traceback bottoms out in.

    Deepest frame inside the source package wins. If the traceback never leaves
    the test file (a plain wrong-value assert), fall back to the module the test
    file is named after: tests/test_slug.py -> minishop/slug.py.
    """
    src = [f for f in failure.get("frames", []) if f.startswith(SOURCE_PKG + os.sep)]
    if src:
        return src[-1], "traceback"
    test_path = failure["nodeid"].split("::")[0]
    stem = Path(test_path).stem
    if stem.startswith("test_"):
        guess = f"{SOURCE_PKG}/{stem[5:]}.py"
        if (ws / guess).exists():
            return guess, "test name"
    return None, "unknown"


def group_failures(failures, ws):
    """{owner file or None: {"failures": [...], "how": "traceback"|"test name"|"unknown"}}, in order."""
    groups = {}
    for f in failures:
        owner, how = owner_file(f, ws)
        groups.setdefault(owner, {"failures": [], "how": how})["failures"].append(f)
    return groups
