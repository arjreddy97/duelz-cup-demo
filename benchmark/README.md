# Benchmark: Duelz vs Gemini CLI on gemini-3.8-flash

The 11 multi-bug tasks behind the results page, with every number needed to check them by hand.

| | Gemini CLI | Duelz |
|---|---|---|
| Total model cost, 11 tasks | $11.64 | $3.93 (**0.34x**) |
| Total wall time, 11 tasks | 1:49:20 | 37:38 (**0.34x**) |
| Solved | 11/11 | 11/11 |

Per-task numbers are in [`results.csv`](results.csv).

## Where the tasks come from

- **10 tasks from [SWE-bench Verified](https://www.swebench.com/):** real GitHub issues from widely used Python
  projects (django, sympy, scikit-learn, pytest), each checked by human reviewers. It is the benchmark AI labs
  report for coding agents.
- **1 task from [SWE-smith](https://swesmith.com/)** (cantools): bugs generated in a real project, with tests.
- **Several bugs per task.** Each task puts 2 to 4 real bugs from the same project into one copy of it, like a real
  backlog. [`tasks.json`](tasks.json) lists, for each task, the original instance IDs, their issue titles, the
  starting image and commit, and the test command.

## How each task is built

1. Start from the original instance's published Docker image (`start_image`) at `start_commit`.
2. Apply `tasks/<task>/bugs.patch`. It removes the upstream fixes for every stacked instance, so all their bugs are
   present at once. Commit that as the only commit; that checkout is what both agents get.
3. Give the agent `tasks/<task>/problem.md` (every original issue, under its own heading) and the `check`
   command from `tasks.json` as the acceptance test.

## How each run is graded

After the agent finishes, its diff is taken against the starting commit, `tasks/<task>/tests.patch` (the original
instances' hidden tests) is applied, and the `check` command is run. A task counts as solved only when every test in
`tasks/<task>/grading.json` passes: the original FAIL_TO_PASS tests (the bugs are fixed) and PASS_TO_PASS tests
(nothing else broke). Neither agent ever sees or edits the hidden tests.

## Settings

- **Both sides:** `gemini-3.8-flash` through the Gemini API, the same sandboxes (one Linux sandbox per run), the same
  grader, one run per task per side, run on 18 Oct 2026.
- **Gemini CLI:** version 0.62.0 at its default settings, run non-interactively:
  `gemini -p "<problem.md>\n\nAcceptance: this command must pass before you are done:\n  <check>" -m gemini-3.8-flash --yolo --skip-trust --output-format json`.
  Cost is priced from the session's token stats at Google's published gemini-3.8-flash prices
  ($0.75 per million input, $3.75 per million output, $0.075 per million cached input tokens).
- **Duelz:** the private engine, on the same model. Only its aggregate cost, time and result are published.

## Caching

Duelz ran almost uncached: only 0.4% of its 4.8M input tokens were cache hits. Gemini CLI got 94–96% cache hits on the
same model, and its costs above are already priced at the cached rate ($0.075 instead of $0.75 per million input
tokens). Duelz's calls average about 9K tokens, above Gemini's caching minimum, so they are cacheable. With caching at
Gemini CLI's level, we estimate Duelz at about 0.07–0.18x Gemini CLI's cost instead of 0.34x
(50% hits: about $2.14; 70%: about $1.49; 90%: about $0.85, against $11.64). This is an estimate, not a measured run.

## What is excluded or adjusted

- **Gemini CLI rate-limit waits are removed from its time.** It hit Google's per-minute input-token quota and waited
  through retries (`gemini_cli_rate_limit_wait_seconds`; the raw time is `gemini_cli_seconds_raw`). Duelz logged no
  rate-limit waits. Cost is unaffected, because rejected calls are not billed.
- **One task is excluded:** `sympy-24539-24213-19637-20590`. The Duelz run crashed after 1 second (infrastructure,
  never started), so there is no fair pair. Its task files are included anyway.

## Reproducing

The Gemini CLI side can be rerun by anyone with the steps above and a Gemini API key. The Duelz engine is not open
source; the [live demo](https://duelz-cup-demo-712955077168.us-central1.run.app/demo) runs a simplified,
open version of the same idea (split the failures, fix in parallel, verify) on a small bundled project.
