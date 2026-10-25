# C106 evidence — the npm smoke with no Python on PATH

Task: [C106](../TASKS.md). Plan row: [design §6](../../docs/design/node-consumers.md#6-implementation-plan) — the npm smoke in
self-CI: pack, install, attach and run every hook with Python hidden. Follow-ups of the review live in
[C124](../TASKS.md) (npm smoke hardening).

## What the leg does

`selfci.npm-smoke` in [`meta/self_ci.py`](../self_ci.py) (`_installed_npm_smoke`), after the installed-wheel smoke:

1. **Prerequisites up front** (`_check_npm_smoke_prerequisites`): `node`, `npm` and `git` resolve on `PATH`, and
   `node --version` is at least the floor (22, `engines.node` in `package.json`).
2. **Pack:** `npm pack` of the working tree into a temp `dist/`; no `akmon-*.tgz` there is reported as
   `npm pack produced no akmon-*.tgz tarball in <dist>` (it used to escape as a bare `StopIteration`).
3. **Install offline into a fresh fixture:** a temp directory made a git repository (`git init` — the Codex wiring
   anchors on `git rev-parse --show-toplevel`) with a minimal `package.json`, then
   `npm install --save-dev --save-exact --offline --no-audit --no-fund <tarball>`. The pin is then rewritten to the
   exact version, which is what `npm install -D -E akmon` leaves after a publish.
4. **With `python3` and `python` hidden from `PATH`** (`_python_free_env`, one shadow set per binary, raising
   `could not hide <binary> from PATH` if one still resolves): `node_modules/.bin/akmon init --yes`, `sync --check`,
   `verify --strict --quiet`, then every generated hook command run verbatim through a shell, the way the harness
   runs it (`_run_generated_hook_commands`, Codex from a nested directory).

## What it asserts

- every step exits 0, and no hook writes to stderr;
- the record holds `ecosystem = "node"`;
- the only materialized file is `_aitna/.akmon/guardrails/_common.md` (the lint rules are extended in place from
  `node_modules/akmon/profiles/oxlint.json`, C109);
- every wired hook command runs from `node_modules/akmon/js/hooks/`;
- both always-speaking SessionStart hooks speak, and the Codex brief keeps its role brief and delegation rule.

## Offline by design — the only prerequisites

The leg touches no registry: the tarball is local, the install is `--offline`, and the Node `init` does no network
lookup. So its only prerequisites are **node >= 22, npm and git**, and `_npm_smoke_report` names exactly those.

## Prerequisite classification

`_npm_smoke_report` reports a prerequisite (`npm smoke could not run: … :: prerequisite of this leg, not a packaging
defect — it needs node >= 22, npm and git on PATH`, fix `Install node >= 22 (npm ships with it) and git, and re-run
python3 meta/self_ci.py.`) when the detail shows:

| How it surfaces | Text matched |
|---|---|
| The up-front check | ``the `node` / `npm` / `git` binary is not on PATH``; `node vX.Y.Z is older than 22` |
| Python spawning a missing binary | `No such file or directory: 'node' / 'npm' / 'git'` |
| node missing behind the `#!/usr/bin/env node` shebang of npm or the akmon bin | `env: <quote>node<quote>: ` — the quotes and the reason text follow the locale, so neither is matched |

Measured on this host (GNU coreutils `env` 9.4, `npm` resolving through a `PATH` with `node` removed), exit status 127:

- C locale: `/usr/bin/env: 'node': No such file or directory`
- `en_US.UTF-8`: `/usr/bin/env: ‘node’: No such file or directory`

Anything else is `npm smoke failed: <detail>` with the akmon-defect fix (`Run python3 meta/self_ci.py and fix the
Python-free Node install failure it reports.`).

## Tests

[`meta/tests/test_self_ci.py`](../tests/test_self_ci.py):

- every prerequisite branch of `_npm_smoke_report` — Python's text for node, npm and git; the env shebang text in the
  C and UTF-8 spellings and a translated reason; the up-front check's missing binary and old node — and the
  akmon-defect branch (a failed `verify`, the missing tarball, a lost `ecosystem`). Each is built into a `Finding`, so
  these fix texts, which the leg-fix sweep (`test_every_leg_fix_text_is_a_valid_finding_fix`, `ok_fix=`/`error_fix=`
  only) cannot see, meet the validator while the leg is green;
- `_check_npm_smoke_prerequisites` against stub binaries: a missing `git`, a node `v20.11.0`, a node `v22.0.0` at the
  floor;
- `_python_free_env`: every Python hidden while the rest of `PATH` and the environment stay, the real directory left
  alone, and the `could not hide python3 from PATH` error when the shadow leaves one resolvable.

## Result of a real run

The leg alone (a scratchpad driver calling `_installed_npm_smoke` with the same environment `_run` builds), node v24,
about 35 s:

```text
OK selfci.npm-smoke: npm smoke passes with python3 hidden (pack, install, init, sync, verify, hook) → Keep the Python-free Node install green before every release.
```

The same driver with `node` removed from `PATH`, and with a stub node printing `v20.11.0` first on `PATH`:

```text
ERROR selfci.npm-smoke: npm smoke could not run: the `node` binary is not on PATH :: prerequisite of this leg, not a packaging defect — it needs node >= 22, npm and git on PATH → Install node >= 22 (npm ships with it) and git, and re-run python3 meta/self_ci.py.
ERROR selfci.npm-smoke: npm smoke could not run: node v20.11.0 is older than 22 :: prerequisite of this leg, not a packaging defect — it needs node >= 22, npm and git on PATH → Install node >= 22 (npm ships with it) and git, and re-run python3 meta/self_ci.py.
```

## Not covered here

- The up-front check reads the `PATH` the leg's hidden environment derives from; `git init` and `npm pack` inherit the
  process environment, whose `PATH` is the same apart from the hidden Codex binary.
- Hiding every `python3.*`, a fail-loud Python shim, per-step timeouts, the fixture lockfile matching the exact pin, and
  running `update`, `tool` and `check` from the tarball: [C124](../TASKS.md).
