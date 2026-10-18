# C107 evidence — the JS `update` for npm/pnpm/yarn/bun

Task: [C107](../TASKS.md). Plan row: [design §6](../design/node-consumers.md#6-implementation-plan) — each manager's
exact command covered; unknown manager → printed command; rollback announced. Decisions: ADR 0020 D07 ("`akmon update`
uses the detected manager's exact dev-install command; any other manager gets the command printed"), ADR-0018/D03.
ADR 0020 D08 applies: [`meta/conformance/DIVERGENCES.md`](../conformance/DIVERGENCES.md).

## What landed (ready for owner review)

| Python | JS twin | Tests |
|---|---|---|
| `src/akmon/_update.py` (package mode) | `js/akmon/_update.mjs` | `_update.test.mjs` (19 tests), `cli/update-node-*` (3 node scenarios), the shared `cli/update-missing-record` |

- **The JS `update` serves Node package mode only.** A record that is not a Node package attach is refused (exit 2,
  `node_refuses_record` of `src/akmon/update.json`, naming what the record holds); no record at all keeps the shared
  `missing_record` text.
- **The plan is the Python's**: the six notes, no move back without `--ref`, an explicit older `--ref` an announced
  rollback. A development version in the npm spelling (`0.5.0-dev.0`) is ordered as its PEP 440 twin (`0.5.0.dev0`), so
  it sorts before the release and its candidates, as on the Python side.
- **The target without `--ref`** is the newest final release `npm view akmon versions --json` lists, asked in the project
  so its `.npmrc` applies. A pre-release is never the newest. `--repo` is accepted and changes nothing (DV26).
- **The move** is the detected manager's exact dev install at the bare version (`v0.5.0` pins `akmon@0.5.0`), from the
  `add_dev_exact` of `init.json` — one table for `init`'s pin step and `update`'s move:
  - npm `npm install -D -E akmon@X`, pnpm `pnpm add -D -E akmon@X`, yarn `yarn add -D -E akmon@X`,
    bun `bun add -d --exact akmon@X`;
  - the manager is `package.json` `packageManager`, else the lockfile, else npm (`detectManager`, as in `init`);
  - a `packageManager` naming any other manager gets the command printed with the npm spelling, and a manager binary not
    on PATH gets its own command printed; both exit 2 and run nothing;
  - a pin outside `devDependencies` is refused before the move, as the Python refuses a pin outside a dev group.
- **After the move** the project's own installed CLI (`node_modules/akmon/js/akmon/cli.mjs`, under the running node) runs
  `init --yes`, `sync --check` and `verify --strict` — the release the project now pins, whichever CLI started the
  update. A missing installed CLI is refused naming the manager's install command.
- **Closing steps** are the Python's; what to stage is `package.json` and its lockfile.
- **Python refusal:** `update` refuses a record naming another ecosystem before the plan (`python_refuses_ecosystem`,
  pointing at `npx akmon update`), as `sync`, `verify` and `init` already do. Scenario `cli/update-ecosystem-node-refused`.
- **The dispatcher's `not_ported` text is gone** with its last user (`src/akmon/cli.json`, the owner's pass-1 decision 3).
- **Pairing:** `_update.py` is paired; `python3 meta/conformance/pairing.py` reports 41 consumer-executable `.py`
  files, 39 paired with their `.mjs`, 2 exempt (the two package inits), 0 covered by a stub only.
- **The real-process test pins the exit status hermetically:** "the real process realigns a Node project through its
  installed CLI" hides `codex` from the child's PATH (the JS twin of `meta/conformance/runner.py`'s
  `_hide_binary_from_path`) and asserts exit status 0. Without the PATH change, on a host with `codex` installed, the
  fixture's `verify --strict` fails on WARN `codex.host-trust` and the process exits 1.

## Python behavior changed

- `src/akmon/_update.py`: the refusal of a record with `ecosystem` other than `python`. Nothing else.

## Divergences registered

- DV26: the target source (the npm registry, not `git ls-remote`) and `--repo` as a no-op.
- DV12 now also names `update`.

## Evidence

- **Unit tests** (`_update.test.mjs`, stand-ins for the manager, the registry and PATH): every manager's exact command,
  chosen by lockfile and by `packageManager`; the registry newest, a lone version, an unreachable registry, a registry
  with no release; the unknown and the missing manager (nothing runs); a failed move (init never runs); the pin outside
  `devDependencies`; the refusals; a failed init and a failed check as the exit code; the closing steps with and without a
  move; one real process realigning through the installed CLI.
- **A real npm move against a local registry** (scratchpad probe): two releases repacked from `npm pack` of
  the working tree (`0.4.1`, `0.4.2`) served by a local HTTP registry (`npm_config_registry`), PATH holding only `node`,
  `npm`, `npx`, `git`, `sh` (no `python3`, no `python`). Install `0.4.1` and `init`, then:
  1. `akmon update` → registry newest `0.4.2`, "0.4.1 → 0.4.2", `npm install -D -E akmon@0.4.2`, init/sync/verify, exit 0;
  2. `akmon update --ref v0.4.1` → "rolling back 0.4.2 → v0.4.1, as --ref asks", exit 0;
  3. `akmon update` → forward to `0.4.2` again; 4. `akmon update` → "already at 0.4.2 — realigning only", no move.
  After each step the `package.json` pin, the installed version, the `package-lock.json` entry, `akmon_version` and
  `last_realign` agree.
- **Corpus:** `update-node-realigned` (the full init/sync/verify output through the installed CLI),
  `update-node-mounted-refused`, `update-node-manager-unknown`, the shared `update-missing-record` (now `warmup = false`:
  the refusal comes before anything is read, and the node warmup cannot sync a project with no record) and the Python
  `update-ecosystem-node-refused`.

## Found on the way

- `meta/self_ci.py`: the fix texts of the `tsc` and `eslint` legs (`… -p . and fix …`, `… eslint . and fix …`) read as two
  sentences to the `Finding` validator, so a failing type check crashed `selfci` with a `ValueError` instead of
  reporting `selfci.js-typecheck`. Reworded ("at the repository root"); `test_every_leg_fix_text_is_a_valid_finding_fix`
  checks every literal leg fix while the legs are green (it fails on the old `eslint` text).

## Not run

- Real pnpm, Yarn (classic or Berry) and Bun moves: none is installed on this host; their commands are covered by the unit
  tests only. pnpm in a workspace root needs `-w`, which `add_dev_exact` does not carry (hoisted layouts are unsupported).
- The real npm registry (V5) and a private registry with authentication.
- Windows (`npm.cmd` is not spawned through a shell).
