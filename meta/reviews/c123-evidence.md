# C123 evidence — a realign keeps the owner's `--checks none` and `own` with nothing found

Task: [C123](../TASKS.md). Decision: ADR 0014 D01 §5 ("`init` decides once … a realign never changes a recorded
`[check]`"); the owner's fix: `none` records an empty `[check]` table, so the existing "`[check]` already names this
project's checks — left untouched" guard keeps it. ADR 0020 D01/D03: both implementations, identical behaviour.

## What changed (ready for owner review)

- **`none` is recorded.** `src/akmon/_init.py::_setup_checks` and `js/akmon/_init.mjs::_setupChecks` append, on
  `none` (from `--checks none` or the prompt), the same table header and comment line `own` and `akmon` write, with no
  entries. One writer per implementation now carries all three choices: `_record_checks(commands, record)` (Python) and
  `_recordChecks(lines, record)` (JS). The bytes appended are identical on both:
  `\n[check]\n# What \`akmon check\` runs: the project's own commands, \`{files}\` becoming the files a run covers.\n`
  after the record's trailing whitespace is stripped.
- **`own` with nothing found is recorded the same way** (owner decision, extending C123): `--checks own` when no tool
  is detected appends the same empty table through the same writer, the same bytes as `none`, in both implementations.
  No prompt path ends there — with nothing detected the Python prompt offers `akmon` or `none`, and the JS
  `_chooseChecks` returns `own` only when a tool was detected — so the explicit flag is the only route. Its next step
  ("no linter configuration was found: name the project's checks under `[check]` in .akmon.toml") stays, and it still
  logs no "no checks recorded" line.
- **The log and the next step for `none` are unchanged** ("akmon check: no checks recorded"; "name the project's checks
  under `[check]` in .akmon.toml when it has any") — both still true.
- **`verify` reads an empty table as no table** (`bin/verify.py::check_check_config`, `js/bin/verify.mjs::checkCheckConfig`):
  the OK finding is given only when the table declares at least one check. See the measurement below.
- **Docstrings:** `_setup_checks` and the `_setupChecks` JSDoc say that nothing — `none`, or `own` when no tool is
  found — is recorded as an empty table so a realign keeps it, and that a record written before has no table and is decided again.
- **Design:** `meta/design/code-rules-and-profiles.md` §7 said "Nothing is written on `own` or `none`"; it now says
  nothing is written into the project's configuration, and `none` and `own` with nothing found are recorded as an
  empty table.
- **No migration:** a record without a `[check]` table is decided again on its next realign, as before.

## Measured — `akmon check` and `verify` on an absent and on an empty `[check]`

Scratch project: `AGENTS.md`, a git repository, `_aitna/.akmon.toml` with `mount = "package"`, `akmon_version`, and
(for the Node implementation) `ecosystem = "node"`; "empty" appends `[check]` with a comment line only.

| reader | absent table | empty table, before | empty table, after |
|---|---|---|---|
| `akmon check`, Python | WARN `check.config` "declares no checks, so nothing ran", exit 0 | same | same |
| `akmon check`, JS | WARN `check.config` "declares no checks, so nothing ran", exit 0 | same | same |
| `verify` `check.config`, Python | no finding | **OK** "[check] declares 0 check(s), …" | no finding |
| `verify` `check.config`, JS | no finding | **OK** "[check] declares 0 check(s), …" | no finding |

`akmon check` already treated the two alike (`read_checks` / `readChecks` return no checks and no problems for either).
`verify` did not, so it was changed; an absent table's behaviour is unchanged. The record readers need nothing:
`tomllib` and the JS strict reader return `{}` for an empty table, the lenient fallback returns `{}` too, and nothing
outside `check` and `verify` reads `check`.

## Tests

- `meta/tests/test_init_checks.py`: `test_choosing_none_records_an_empty_table_and_says_where_checks_go` (the exact
  record bytes); `test_a_realign_keeps_none` (a second `_setup_checks` with no choice and nobody asked, on a project with
  no linter, leaves the record byte-identical and writes no `ruff.toml` and no `[tool.ruff]`);
  `test_choosing_own_with_nothing_found_records_an_empty_table_and_a_realign_keeps_it` (the same record bytes as `none`,
  the "no linter configuration was found" next step, and the same realign assertions).
- `meta/tests/test_check_runner.py::test_verify_validates_the_check_table_and_runs_nothing`: no table and an empty table
  both give no finding.
- `js/akmon/_init.test.mjs`: `--checks none` records the empty table and writes no `.oxlintrc.json`; a realign
  (`init --yes`) after it logs "left untouched", leaves the record unchanged and writes no `.oxlintrc.json`; the prompt
  answers that decline into `none` record the empty table; `--checks own` with nothing found records the empty table,
  names the next step, and a realign logs "left untouched", keeps the record byte-identical and writes no
  `.oxlintrc.json`; the choice-flow, scripts-step and hand-written-record tests
  now expect the table.
- `js/bin/verify.test.mjs`: an empty table gives no `check.config` finding.
- `js/akmon/_update.test.mjs`: the real-process realign starts from a record with the empty table and asserts that
  `update` (through the installed CLI's `init --yes`) logs "left untouched", keeps the table and writes no
  `.oxlintrc.json`. This carrier pins the update path end to end; that `none` writes the table is pinned by the init
  tests. Python's `test_update.py` stubs `init`, so it is not a faithful carrier; the Python realign is the same
  `_setup_checks` call that `test_a_realign_keeps_none` pins.
- Corpus: `cli/init-vendored` (Python, `--checks none`) re-recorded from the Python reference — only the record bytes
  changed. New `cli/init-node-checks-none` (node): the full output and record of `--checks none`, and
  `.oxlintrc.json` absent; its expectation is hand-written (`--record` runs on Python only) and passes on the JS
  implementation.

## Gates

- `uv run pytest -q`: 10 failed, 2392 passed — the 9 known `test_a22_p3_*` reds and
  `test_ruff_profile.py::test_akmon_meets_every_size_limit_without_an_exception` (its offenders are `test_a22_p3_*`
  files only).
- `uv run ruff check .`: 1 error, the known I001 in `meta/tests/test_a22_p3_dispatch_v3.py`.
- `uv run ruff format --check` on the touched Python files: the touched files already formatted.
- `node --test "js/**/*.test.mjs"`: 601 tests, 601 pass.
- `npx --no-install tsc --checkJs --noEmit -p .`: exit 0. `npx --no-install oxlint .`: exit 0.
  `npx --no-install oxfmt --check .`: all matched files use the correct format.
- `uv run python meta/conformance/runner.py --tree .`: 188 scenarios, 162 pass, 26 skip; coverage and pairing gates ok.
- `uv run python meta/conformance/runner.py --tree . --impl node`: 188 scenarios, 168 pass, 20 skip; gates ok.

## Not run

- `meta/self_ci.py`, `uv build`, `npm ci` — not part of this task's gate list.
