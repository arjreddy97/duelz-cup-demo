# Duelz for Gemini: split, fix, verify

**Same Gemini. 3x cheaper. 3x faster.**

A demo for the Google Cloud AI Builder Cup 2026. It shows that a smarter harness around the
same Gemini model fixes multi-bug coding tasks for less money and in less time than one big
agent working through everything in a single conversation.

The site has three pages:

- **Results** (`/`): benchmark charts and tables. Duelz vs Google's Gemini CLI on the same model,
  Duelz vs Claude Code, and a whole-library build.
- **Real runs** (`/replay`): replays of recorded benchmark runs of Duelz vs Gemini CLI (both on
  gemini-3.8-flash, real SWE-bench Verified bugs) with their real timings and costs. Nothing is executed.
- **Live demo** (`/demo`): both approaches run side by side as live Gemini coding agents on a
  small bundled Python project with six bugs in six files (22 failing tests, 21 passing).

## How it works

1. **Failures.** Run the test suite and collect every failure with its traceback.
2. **Split by cause.** Group failures by the source file their traceback bottoms out in. 22
   failing tests are often six bugs.
3. **Parallel fixes.** Each group gets its own short agent loop, with only its source file and its
   failing tests, so every prompt stays small and they all run at once.
4. **Verify.** Re-run each group's tests, merge, run the whole suite, and retry a still-red group
   once with a fresh loop before declaring victory.

The single-agent baseline in the live demo is the same agent loop pointed at the whole project
and every failure in one conversation, re-sending its growing context every turn.

The live demo is deliberately simple and generic. It is written fresh for this hackathon and
does not contain Duelz's engine.

## Benchmark results (provisional)

These numbers come from **Duelz's private engine**, not from this repository. This repo is a
fresh demo of the idea; it only displays aggregate per-task cost, time and solved status.

| Comparison | Model | Tasks | Cost | Time | Solved |
|---|---|---|---|---|---|
| Duelz vs Gemini CLI | gemini-3.8-flash, both | 11 | **0.34x the cost** ($0.36 vs $1.06 per task) | **0.34x the time** (3.4 vs 9.9 min) | 11/11 vs 11/11 |
| Duelz vs Claude Code (low effort) | Claude Haiku 5.5, both | 25 | 0.55-0.64x model cost | 0.95x | 100% vs 92% |
| Whole-library build (babel, 5,663 tests) | | 1 | $0.46 vs $0.86 | | all passing vs 2 failing |

The Gemini comparison covers 11 multi-bug tasks, one run per task per side. One task where the Duelz run crashed after 1 second (infrastructure, never started) is
excluded and footnoted on the page. Gemini CLI times exclude its rate-limit retry waits.
`app/static/bench-results.json` and `app/static/replays.json` hold these aggregate numbers; they are
exported from the private benchmark records, which are not part of this repo.

## Benchmark data

[`benchmark/`](benchmark/) has the 11 Gemini tasks (SWE-bench Verified and SWE-smith instance IDs, the patch that
stacks their bugs, the hidden tests and grading lists) and per-task results for both sides, so the 0.34x figures can
be checked by hand. See [`benchmark/README.md`](benchmark/README.md).

## Run locally

Needs Python 3.11+.

```bash
export GEMINI_API_KEY=...             # or: export DEMO_ENV_FILE=/path/to/.env containing GEMINI_API_KEY=
./run-local.sh                        # creates .venv on first run; serves http://localhost:8080
PORT=8765 ./run-local.sh              # another port
```

The key is read from the environment at startup and never written anywhere. See
`.env.example` for the optional knobs (model, thinking level, turn caps, spend cap, rate limits).

### Test without Gemini (scripted fake model)

```bash
.venv/bin/python -m pytest -q tests      # loop/tool layer, both modes end to end, sample project check
DEMO_FAKE_MODEL=1 ./run-local.sh         # the page with a scripted fake model (no key, no API calls)
```

`DEMO_FAKE_MODEL=1` swaps Gemini for `devtools/fake_model.py`, which plays plausible tool actions
and applies the known fixes from `devtools/reference_fixes.py`. Its token counts are estimates
(about 4 characters per token); the page says so. `DEMO_FAKE_CACHE=1` pretends the implicit cache
served each previous prefix, `DEMO_FAKE_FAIL_ONCE=invoicer/paging.py` makes one branch fail its first
attempt (exercises the retry), `DEMO_FAKE_LATENCY=0.4` sets seconds per call. `devtools/` and
`tests/` are excluded from the container image and the Cloud Build upload.

## Live demo details

- Both modes run the same agent loop (`app/agent.py`): one JSON action per turn, from `list_files`,
  `read_file` (optional line range), `run_tests` (optional node ids), `replace`, `write_file` and
  `finish`. Each turn appends the model's action and the tool output to the conversation. Tool
  output is cut at 4,000 characters. Every agent starts with the files in its scope (whole project
  for the single agent, its own source and test file for a branch; `DEMO_PRELOAD_FILES=0` turns
  this off for both).
- Single agent: up to 30 turns. Split & verify: one loop per failure group, in parallel, up to 12
  turns each; a branch may only write its own file, sees only its group's failures, and its
  `run_tests` only runs its tests. Then merge, full suite, and one fresh 8-turn retry per still-red group.
- Hard spend cap: each mode stops calling the model once it has spent $0.25 in a run
  (`DEMO_MODE_MAX_USD`). Parallel branches can overshoot by at most one call each.
- Model `gemini-3.8-flash` via the `google-genai` SDK, thinking level `low`, JSON output.
- Tokens come from each response's `usageMetadata`; dollars use Google's published prices:
  $0.75 per M input tokens, $3.75 per M output tokens (thinking counted as output), $0.075 per M
  cached tokens. Implicit cache hits (`cachedContentTokenCount`) are charged at the cached price.
- Tests run with pytest in a throwaway temp copy of `sample_project/` per run, with a timeout,
  CPU/memory limits and an environment stripped of secrets. Only the bundled sample runs; the
  page accepts no user code or input. The tool layer only reads inside the workspace copy, never
  writes tests, and only writes the source files a loop is allowed; test selectors must be node ids
  under `tests/`. At most 3 pytest processes run at once.
- Rate limits: one live run per visitor per minute, at most 2 concurrent runs, 10 per hour and
  40 per day (all configurable). Limits are in memory, so the deploy pins one instance.

## Live-run history (Firestore)

Every finished live run is saved as one document in the Firestore collection `live_runs`
(default database, Native mode, us-central1): a server timestamp (`created`), the model name, and
for each mode (`single`, `split`) `green`, `passed`, `total`, `cost_usd`, `wall_seconds`,
`input_tokens`, `output_tokens`, `cached_tokens`, `turns`, `max_prompt_tokens` and `stop` (or
`{"error": true}` if that mode errored). Nothing about visitors is stored: no IP, no visitor id.
Writes run on a background thread with a 5 s timeout and never affect a run. `GET /api/runs`
returns the last 10 runs plus aggregates over the last 50 (median split/single cost ratio, how often
split was cheaper, how often both were green), cached for 20 s; the demo page shows them under
"Recent live runs". Firestore is used only on Cloud Run (or with `DEMO_FIRESTORE=1`), never with
`DEMO_FAKE_MODEL=1`; locally it is off and `/api/runs` returns an empty list. The Cloud Run
service account needs `roles/datastore.user`.

## Deploy (Cloud Run)

```bash
# once: store the key in Secret Manager
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=- --project duelz-play
./deploy.sh
```

`deploy.sh` runs `gcloud run deploy duelz-cup-demo --source . --region us-central1 --project duelz-play`
with `--allow-unauthenticated`, one max instance, and `GEMINI_API_KEY` mounted from the
`gemini-api-key` secret. `USE_ENV_KEY=1 ./deploy.sh` passes the key as a plain env var instead
(not recommended). The container listens on `$PORT`.

## Layout

```
app/main.py            FastAPI app: pages, /api/run (streams events), /api/runs, rate limits
app/runstore.py        live-run results in Firestore (background writes, cached reads, aggregates)
app/agent.py           the shared agent loop and its tools (path and write restrictions live here)
app/modes.py           the two demo modes: single agent, split & verify
app/gemini.py          google-genai wrapper with token/dollar metering (fake model when DEMO_FAKE_MODEL=1)
app/sandbox.py         temp-copy workspaces, pytest runner, traceback grouping
app/pytest_plugin/     tiny pytest plugin that reports outcomes + traceback files as JSON
app/static/            results, real-runs and demo pages, charts, bench-results.json, replays.json (replay data)
sample_project/        invoicer: 7 small modules, 43 tests, 6 deliberate bugs in 6 files (22 failing)
devtools/              dev-only: scripted fake model + reference fixes (not shipped)
tests/                 app tests (run with the fake model; no API calls)
Dockerfile, deploy.sh, run-local.sh
```
