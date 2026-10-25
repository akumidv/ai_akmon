# C110 evidence — akmon's JS ruleset and `--checks akmon` for Node

Task: [C110](../TASKS.md), with the A35 deliverables. Plan row: [design §6](../../docs/design/node-consumers.md#6-implementation-plan):
`extends` written into the project's own config, never over one it chose; a scenario per config format.
Decision: [ADR-0020/D09](../../docs/adr/0020-node-consumers-js-implementation.md#d09--the-javascripttypescript-ruleset-oxlint-and-akmons-own-tooling)
(owner), on the [A35 baseline](a35-js-rule-baseline.md). Divergence: DV25 (rewritten).

Owner review: the owner accepted every C110 decision, including the five implementation points
recorded in D09. The carriers are uncommitted until the owner lands them.

## What landed

- **The ruleset**: `profiles/oxlint.json`, a standard oxlint configuration (JSONC, annotated with the Google section of
  each rule):
  - ESLint's `recommended` as oxlint names it, `no-undef` and `no-useless-assignment` included;
  - the 29 Google/floor rules, with `camelcase` as `id-match` (declarations only, properties never);
  - for `.ts/.tsx/.mts/.cts`, the rules `tsc` checks turned off (typescript-eslint's `eslint-recommended` set);
  - no `env`: where the code runs is the project's.

  Extends semantics, probed on oxlint 1.88 (M132): comments are accepted in an extended file, and `rules`,
  `categories` and `overrides` arrive through `extends`; `env` does not — the extended file's `env` applies only when
  it is the config itself (`-c`), so a project that extends it states its own `env`. The ECMAScript globals are on
  without any `env`.
- **The profile**: `profiles/js.md` holds only the Google rules no linter checks:
  - §5.9 in JavaScript;
  - §3.4.2.1–§3.4.3 exports and cycles, §5.1.3, §5.4.4–§5.4.11;
  - §7 JSDoc, §8.2.3 suppressions;
  - TypeScript `strict`, globals in config.

  `ARCHETYPES.md` maps JavaScript/TS to it.
- **`init` (JS, Node)**, `js/akmon/_init.mjs`:
  - **Default.** `own` when a linter (ESLint, Biome, oxlint) is detected, otherwise `akmon`. At the prompt a no goes to
    `akmon` or `none`, or for a project with no linter to `own`/`none`.
  - **Writing.** `akmon` writes `.oxlintrc.json` when absent:
    `{"extends": ["./node_modules/akmon/profiles/oxlint.json"], "env": {"browser": true, "node": true}}`.
    A step says to narrow `env`.
  - **An existing `.oxlintrc.json`** is never edited. If it lacks the line, a step names it and the `env` the project
    states itself, since `extends` does not carry `env` (M132, C116).
  - **Recording.** It records `oxlint {files}` through the manager's `check_run`, then the detected Prettier and `tsc`.
  - **Install step.** It names `<add_dev_exact> oxlint` when `package.json` does not declare oxlint.
  - **Refusal removed.** The `--checks akmon` refusal and `node_checks_pending` are gone.
- **AGENTS block**: the profile example is `{{language_profile}}`: `python.md` from Python (bytes unchanged), `js.md`
  from JS. The JS `sync` materializes an imported `profiles/js.md` (`js/bin/sync.test.mjs`).
- **Corpus**:
  - `cli/init-node-checks-akmon-refused` was deleted.
  - Three scenarios were added:
    - `cli/init-node-checks-akmon-bare` (nothing detected → `akmon`, file and record bytes);
    - `cli/init-node-checks-akmon-own-oxlintrc` (an existing `.oxlintrc.json` stays byte-identical, with the step);
    - `cli/init-node-checks-akmon-tsc` (only `tsconfig.json` → oxlint + tsc).
  - Updated for the new default: `init-node-attach`, `init-node-bare`, `init-node-checks-scripts-akmon` (named `init-node-checks-scripts-none` until the C109 review fix),
    `init-node-checks-prettier-bun`, `update-node-realigned` (the last also gains the `check.config` OK line its new
    `[check]` causes).
- **akmon's own JS**:
  - **Tools.** ESLint 10 and `@eslint/js` were removed; oxlint 1.88.0 and oxfmt 0.73.0 were added as exact
    devDependencies.
  - **Lint config.** `.oxlintrc.json` extends `./profiles/oxlint.json` with `env.node`, the ignores, and the size
    family's per-file exceptions.
  - **Formatter.** `.oxfmtrc.json` is at width 120, limited to `.mjs/.js/.ts` (by default oxfmt would also rewrite
    JSON, Markdown and TOML). 57 files were reformatted (M131).
  - **Code fixes.** Outside the size family:
    - four literal U+2028 characters written as ` `;
    - camelCase renames (`problemsData`, `gitRepo`, `assistantLine`, and the constructor parameters in `probe.mjs`);
    - one `one-var`, one `curly`, two `prefer-const`.
  - **Self-CI.** The leg `selfci.js-lint` runs oxlint; the new `selfci.js-format` runs `oxfmt --check`. `AGENTS.md`
    and the corpus README name both.
  - **Ratchet.** `meta/tests/test_oxlint_profile.py` checks it. The exception lists may only shrink against a frozen
    table, a listed file that no longer offends fails with "remove it", and no inline disable of a size rule is allowed.

  Exceptions at the start (M131):

  | rule | findings | files |
  |---|---|---|
  | `complexity` | 66 | 26 |
  | `max-params` | 10 | 4 |
  | `max-statements` | 3 | 3 |
  | `max-depth` | 5 | 2 |

## Python behavior changed

Only the data placeholder in the AGENTS block; the bytes Python writes are unchanged. `init` on Python projects is
untouched.

## Evidence

- `npx --no-install oxlint .`: 0 problems.
- `oxfmt --check .`: 81 files.
- `tsc -p .`: clean.
- `node --test 'js/**/*.test.mjs'`: 545/545.
- Conformance corpus:
  - node: 175 scenarios, 157 pass, 18 skip;
  - python: 175 scenarios, 151 pass, 24 skip;
  - coverage and pairing gates ok.
- `uv run pytest`: 2114 passed, 1 deselected (`test_akmon_meets_every_size_limit_without_an_exception`, a22-only).
- `meta/self_ci.py`: exit 0, with `selfci.js-lint` and `selfci.js-format` OK.
- `ruff check .`: the only findings are 12 in `meta/experiments/a22-p3/` (a22-only).

## Limits

- The ruleset was run on two corpora, tvassistant and akmon. TypeScript is a parse probe plus the extends test.
  There is still no TypeScript corpus.
- The written `env` is browser + node, so `no-undef` is permissive until the project narrows it.
- The new scenario expectations were recorded from the JS output and checked line by line against the contract
  above. They are spec for the owner to review.
