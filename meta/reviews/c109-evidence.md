# C109 evidence — `init` detects JS/TS linters and analyzers

Task: [C109](../TASKS.md). Plan row: [design §6](../../docs/design/node-consumers.md#6-implementation-plan) — the §3 F5 table in
node-tagged scenarios per tool and per manager; explicit patterns; `tsc` without `{files}`; scripts named, not recorded.
Decision: ADR 0020 D07, design §3 F5. Divergence: DV25 (rewritten).

## What landed (ready for owner review)

- **Detection** (`js/akmon/_init.mjs` `detectNodeTools`, read-only, table order = record order):

  | Name | Config | Command | `files` |
  |---|---|---|---|
  | `eslint` | `eslint.config.{js,mjs,cjs,ts,mts,cts}`, `.eslintrc`/`.eslintrc.*`, `package.json#eslintConfig` | `<run>eslint {files}` | JS/TS set |
  | `biome` | `biome.json`, `biome.jsonc` | `<run>biome check {files}` | JS/TS + `*.json` |
  | `oxlint` | `.oxlintrc.json` | `<run>oxlint {files}` | JS/TS set |
  | `prettier` | `.prettierrc`/`.prettierrc.*`, `prettier.config.*`, `package.json#prettier` | `<run>prettier --check {files}` | JS/TS + `*.json *.css *.md` |
  | `tsc` | `tsconfig.json` | `<run>tsc --noEmit -p .` (plain string, no `{files}`) | — |

  JS/TS set: `*.js *.mjs *.cjs *.jsx *.ts *.mts *.cts *.tsx`.
- **`<run>`**: `check_run` of the detected manager (`init.json` `node_managers`; `packageManager` first, then the
  lockfile, else npm): `npx --no-install `, `pnpm exec `, `yarn `, `bunx --no-install ` (owner decision after M126). `exec` is unchanged.
- **Flow** (Python's `_setup_checks`, Node variant): a record with `[check]` is left untouched; detected tools → `own`
  (asked unless `--yes`; a no → `none`); nothing detected → `none` with Python's log line and next step; `--checks own`
  with nothing found → Python's next step; `--checks akmon` refused before anything is touched (exit 2, until A35).
- **Scripts**: `package.json` `lint`/`typecheck` scripts are named in one next step in the manager's run spelling
  (`node_scripts_step`, `run_script`), never recorded.
- **Corpus**: seven node-tagged scenarios `cli/init-node-checks-{eslint-npm,biome-pnpm,oxlint-yarn,prettier-bun,
  tsc-manager-field,scripts-none,akmon-refused}` (every tool, every manager, the `packageManager` field over a lockfile;
  the recorded `.akmon.toml` bytes asserted); `cli/init-node-attach`, `cli/init-node-bare`, `cli/update-node-realigned`
  follow the `none` default (one log line, one next step).
- **Tests**: `_init.test.mjs` (every config spelling, prefixes, record bytes, branches, left-untouched, scripts per
  manager); `test_init.py` key pin.

## Superseded by C110

[C110](c110-evidence.md) changed the default with nothing detected from `none` to `akmon` (oxlint with akmon's
rules), so the `none`-default lines of the flow and corpus above no longer hold, and it removed the
`cli/init-node-checks-akmon-refused` scenario. The C109 review fix renamed `cli/init-node-checks-scripts-none` to
`cli/init-node-checks-scripts-akmon`, the default it now records, and added tests of the interactive decline branches
(DV25).

## Python behavior changed

None. Python `init` refuses a Node project, as before.

## Evidence

`node --test` 538/538; tsc, eslint clean; corpus node 155 pass / 18 skip, python 151 pass / 22 skip, coverage and pairing
gates ok; pytest 2090 passed (the a22 size-limit test deselected); selfci exit 0, no ERROR/WARN; ruff clean outside a22.

## Not run

- The recorded commands against real ESLint/Biome/oxlint/Prettier/tsc installs: the corpus asserts the record, not a
  `akmon check` run of it.
