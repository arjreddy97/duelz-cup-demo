"""Settings. The API key only ever comes from the environment (or a local .env
file named by DEMO_ENV_FILE); it is never written anywhere."""
import os
from pathlib import Path

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL", "low")

# Google's published gemini-3.8-flash prices, USD per 1M tokens.
PRICE_INPUT = 0.75
PRICE_OUTPUT = 3.75
PRICE_CACHED = 0.075

# Agent loop (same loop, tools and model settings for both modes).
SINGLE_MAX_TURNS = int(os.environ.get("DEMO_SINGLE_MAX_TURNS", "30"))
SPLIT_MAX_TURNS = int(os.environ.get("DEMO_SPLIT_MAX_TURNS", "12"))    # per branch
SPLIT_RETRY_TURNS = int(os.environ.get("DEMO_SPLIT_RETRY_TURNS", "8"))  # per still-red group, once
# Hand each agent the files in its scope up front (whole project for the single agent,
# its own source file + test file for a split branch). Same rule for both modes.
PRELOAD_FILES = os.environ.get("DEMO_PRELOAD_FILES", "1") == "1"
TOOL_OUTPUT_CHARS = int(os.environ.get("DEMO_TOOL_OUTPUT_CHARS", "4000"))
MAX_OUTPUT_TOKENS = int(os.environ.get("DEMO_MAX_OUTPUT_TOKENS", "4096"))
CALL_TIMEOUT_SECONDS = float(os.environ.get("DEMO_CALL_TIMEOUT", "90"))
# Hard spend cap per mode per run: a mode stops calling the model once it has spent this.
MODE_MAX_USD = float(os.environ.get("DEMO_MODE_MAX_USD", "0.25"))

# Test-only: a scripted stand-in model from devtools/ (not shipped in the image).
FAKE_MODEL = os.environ.get("DEMO_FAKE_MODEL") == "1"

LIVE_ENABLED = os.environ.get("DEMO_LIVE_ENABLED", "1") == "1"
PER_VISITOR_SECONDS = int(os.environ.get("DEMO_PER_VISITOR_SECONDS", "60"))
MAX_CONCURRENT_RUNS = int(os.environ.get("DEMO_MAX_CONCURRENT", "2"))
MAX_RUNS_PER_HOUR = int(os.environ.get("DEMO_MAX_RUNS_PER_HOUR", "10"))
MAX_RUNS_PER_DAY = int(os.environ.get("DEMO_MAX_RUNS_PER_DAY", "40"))


def _load_env_file():
    path = os.environ.get("DEMO_ENV_FILE")
    if not path or os.environ.get("GEMINI_API_KEY"):
        return
    p = Path(path).expanduser()
    if not p.is_file():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return


_load_env_file()


def api_key():
    return os.environ.get("GEMINI_API_KEY", "")
