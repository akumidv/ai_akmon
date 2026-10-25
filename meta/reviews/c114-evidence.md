# C114 evidence — tool reports named by task id and ordinal

Task: [C114](../TASKS.md). Rule: [AGENTS.md § Project contract](../../AGENTS.md#project-contract) (no dates in
the tree). Decision: the owner chose option A, an optional `--task <id>` plus an ordinal. The carriers are
uncommitted until the owner lands them.

## Contract

- A tool report written into a shared directory is named `[<task>-]<base>-<n>.md`, never
  `<base>-%Y%m%d-%H%M%S.md`.
- `n` is 1 + the largest `n` among entries matching exactly `^<escaped prefix>-([0-9]+)\.md$` in that
  directory; 1 when there is none or the directory is missing. A neighbour such as `design-align-full-3.md`
  does not count for the prefix `design-align`, and neither does an untasked or a non-ordinal name.
- The file is created exclusively; on an existing name (a concurrent run took it) the next ordinal is tried,
  so no report is ever overwritten.
- `--out` wins over the default name. A dry run prints the next path and creates nothing.
- The task id is sanitized like a gate name (every character but a letter, a digit, `-` or `_` becomes `-`,
  outer `-` stripped), case kept.
- A `--task` that sanitizes to nothing (`""`, `"///"`, `"..."`) is a usage error (owner decision), checked
  before any file is read or written: exit 2 and `--task '<value>' has no usable characters (letters,
  digits, '_' or '-')`. `report_prefix`/`reportPrefix` raise on such a task, so no caller gets a silent
  fallback.

| tool | `--task` | base | default directory |
|---|---|---|---|
| `gate_pack` | optional | `<gate>-<kind>` | `<AITNA_ROOT>/artifacts/gates/` |
| `second_opinion` | optional | `<gate>` | the route's `report_dir` |
| `coverage_map` | optional | `coverage` | `<AITNA_ROOT>/artifacts/gates/` |
| `stats` | optional | `stats` | `--report-dir`, default `.claude/stats/` |

## What landed

- **One owner of the name**: `common/report_path.py` (`safe_name`, `task_error`, `report_prefix`,
  `next_report_path`, `create_report`) and its twin `js/common/report_path.mjs` (`safeName`, `taskError`,
  `reportPrefix`, `nextReportPath`, `createReport`). Both are stdlib/Node-only. `task_error`/`taskError` is
  the one source of the empty-task sentence; each tool turns it into its own usage error.
- **The four tools**, in `tools/model_routing/*.py` and `js/tools/model_routing/*.mjs`, take `--task` and name
  their report through it. `gate_pack` and `second_opinion` keep the `gate` fallback for a gate name that
  sanitizes to nothing.
- **Export changes** (`tools/README.md` table, `CHANGELOG.md` Unreleased / Changed):
  - `akmon/tools/model_routing/gate_pack`: `reportDir`, `reportPrefix` instead of `stamp`, `reportPath`;
  - `akmon/tools/model_routing/second_opinion`: `reportPrefix` instead of `reportPath`.
- **Shipped-file lists**: `common/report_path.py` was added to the corpus snapshot (`meta/conformance/corpus.py`
  `SNAPSHOT_FILES`) and to the self-CI fixture (`meta/self_ci.py`). Without it the Python tools fail to import
  in package mode. The wheel already force-includes all of `common/`.
- **Tests**: `meta/tests/test_report_path.py` (7), `js/common/report_path.test.mjs` (6); the tool tests
  `test_gate_pack.py`, `test_coverage_map.py`, `test_stats.py`, `test_second_opinion_cli.py` and their JS
  twins assert the literal names. The empty task: both helper suites assert the sentence and the raise for
  `"///"`, `""` and `"..."`; `test_gate_pack.py` and `gate_pack.test.mjs` assert the CLI usage error (exit
  2, nothing written; the JS case uses a missing yardstick, so it also shows nothing was read first).
- **Corpus**: `gate-pack-full`, `second-opinion-dry-run`, `stats-digest` and `stats-degraded` assert the
  literal default names. The new `tools/gate-pack-task-ordinal` runs `--task C7` against a directory holding
  `C7-code-verify-plan-check-1.md`, the untasked `code-verify-plan-check-5.md` and the non-ordinal
  `C7-code-verify-plan-check-x.md`. It expects `-2`, `-1` unchanged and no `-6`. The new
  `tools/gate-pack-task-empty` runs `--task ///` and expects exit 2, the usage sentence on stderr, an empty
  stdout and no `code-verify-plan-check-1.md`.
- **Docs**: `skills/stats-digest/SKILL.md` (report name, `--task` flag), `docs/design/model-routing.md`
  (second-opinion report name).

## Evidence

- Conformance corpus, 177 scenarios:
  - python: 153 pass, 24 skip;
  - node: 159 pass, 18 skip;
  - coverage and pairing gates ok;
  - `tools/gate-pack-task-ordinal` and `tools/gate-pack-task-empty` pass on both.
- `node --test 'js/**/*.test.mjs'`: 551/551.
- `oxlint .`: exit 0. `oxfmt --check .`: 83 files, all formatted.
- `meta/self_ci.py`: exit 0, no non-OK line.
- `uv run pytest --ignore=akmon`: 2172 passed, 3 failed, all a22-only: `test_akmon_meets_every_size_limit_without_an_exception`
  and two in `test_a22_p3_quota_adapter_v3.py`. `--ignore=akmon` skips a stray root symlink `akmon -> .` that
  multiplies collection. `-k "link or doc or anchor or verify"`: 258 passed.
- `ruff check .`: 13 findings, all in `meta/experiments/a22-p3/` and `meta/tests/test_a22_p3_*` (a22-only).
- `tsc --checkJs --noEmit -p .`: clean.

## Limits

- `second_opinion --dry-run` prints the name that is next at the time of the scan. A concurrent run can take
  it before a real run, and the real run then reports the name it actually created.
- An ordinal is parsed as an integer in Python and as a `Number` in JS. They agree up to 2^53; nobody reaches
  such names in practice.
- `examples/gate-anatomy.md` still describes the session's hand-made gate folders as
  `_aitna/artifacts/gates/<stamp>-<slug>/`. That is an orchestrator's directory convention, not a tool's
  default name, so it was left out of C114.
