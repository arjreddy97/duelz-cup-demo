#!/usr/bin/env bash
# Run the app locally on http://localhost:${PORT:-8080}.
# GEMINI_API_KEY comes from your environment, or from the .env file named by
# DEMO_ENV_FILE (read at startup, never copied into this repo).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8080}"
