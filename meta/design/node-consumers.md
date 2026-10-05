# Design: Node.js consumers — a JavaScript implementation on npm (A34)

> **Status: decided in [ADR 0020](../decisions/0020-node-consumers-js-implementation.md)**
> (D01–D07). This document keeps the analysis behind it and the implementation plan (§6). Closes
> the "Non-Python consumers" open point of the [packaging design](packaging/README.md#open-points)
> (`meta/design/packaging/README.md:324`).

## 1. Essence

A Node.js project attaches akmon the way a Python project does: it pins akmon in its own manifest
(`package.json` `devDependencies`), runs `npx akmon init`, and gets the same model. That model is
generated Claude/Codex hook wiring, the always-on guardrails, `sync --check` / `verify --strict`
in CI, and `akmon check` running **the project's own** linters and analyzers, with an
akmon-provided ruleset offered only when the project has none. **It needs Node and no Python.**

akmon therefore keeps two permanent implementations of everything a consumer executes: Python
for Python consumers and the mounted modes, JavaScript for Node package mode. A language-neutral
conformance corpus is the normative spec both must pass. The Python implementation is the
reference where the corpus is silent.

## 2. As-is

What is already language-neutral and needs no port: the guardrails, profiles, pipelines, roles
and skills (documents), the vendor pointers, the data files (`tools/model_routing/registry.json`),
and the root and record *contracts*. Every executable piece is Python:

| Area | Files | Lines (2026-09-26) |
|---|---|---|
| `src/akmon` (CLI: init, update, dispatch, tree) | 5 | 2 203 |
| `bin` (sync, verify, check) | 3 | 2 597 |
| `common` (record, versions, root, runtime, check runner, …) | 9 | 1 454 |
| `hooks` (8 entry points, core, 2 adapters) | 11 | 1 981 |
| `tools` (model_routing ×6, release_check, tasks archive) | 8 | 3 893 |
| **total** | **36** | **12 128** |

The 1 562 tests in `meta/tests` are Python unit tests and do not carry over. Stdlib surfaces with
no identical Node counterpart: `tomllib` (`bin/sync.py::_read_manifest`, `bin/sync.py::ruff_extends`,
and `common/record.py`), `shlex`, `fnmatch`, `json.dumps` formatting, Python `re` syntax, code-point
sorting, `subprocess`, and `urllib` (`tools/model_routing/stats.py::fetch_usage`).

Python coupling outside the code itself:

| Surface | Where | Coupling |
|---|---|---|
| Pin inspection | `bin/sync.py::package_pin_status` | `pyproject.toml` only |
| Hook launcher | `bin/sync.py::launcher_relative`, `bin/sync.json` `default_launcher_rel` | `.venv/bin/akmon` console script |
| Update | `src/akmon/_update.py::_update_package` | `uv add` only |
| Check detection | `src/akmon/_init.py::_TOOLS`, `src/akmon/_init.py::_run_prefix` (`src/akmon/init.json` `run_prefix`) | ruff/flake8/pylint/mypy; `uv run`/`poetry run` |
| Default check patterns | `common/check_runner.json` `default_files` (read by `common/check_runner.py::default_files`) | `*.py` |
| Ruleset offer | `src/akmon/_init.py::_extend_with_akmon_rules` | ruff `extend` only |
| CI template | `src/akmon/_init.py::_ci_workflow` (`src/akmon/init.json` `ci_workflow`) | `uv run akmon …` |
| Runtime contract | `common/runtime.py:6` | `python3` on PATH for every consumer |
| Profiles | `profiles/` | `python`, `python-stdlib`, `quant`, `ruff.toml`; `ARCHETYPES.md:102` reserves `js` |
| Messages | SessionStart and others | print `python3 $(akmon path)/tools/…` |

## 3. Analysis (owner discussion 2026-09-26)

### F1 — Execution: port, not wrap

A JS launcher running the host `python3` was proposed first. The probe (Python 3.12 / Node 24.21)
showed a copy of the tree at `node_modules/akmon/` runs the CLI unchanged. **The owner rejected
it: Node consumers must run without Python.** Also rejected: a `uvx` wrapper (needs Python via
uv), a bundled interpreter (Python in substance), and one JS implementation for everyone (forces
Node onto Python consumers). The accepted shape is two permanent implementations (ADR 0020 D01),
with the port limited to Node package mode (D02).

### F2 — Opportunities of the port

- Node projects without Python: `node:*-slim` images, frontend teams, CI with one runtime.
- The conformance corpus fixes akmon's behavior at the process boundary, independently of either
  implementation. It catches Python regressions too, even if the port stalls.
- Porting forces data-first design. Logic moved into shared data is written once.
- JS tools become a base for JS projects' own dev-layer tools (ADR 0020 D06).

### F3 — Problems and how the decisions answer them

| # | Problem | Answer |
|---|---|---|
| P1 | Every executable change costs two languages, permanently | Accepted cost (D01). Data-first stage C102 shrinks it; the pairing gate and one-change rule (D03) make an omission fail CI |
| P2 | Which side wins a disagreement | Corpus normative; Python reference where silent; each resolution becomes a scenario (D01) |
| P3 | Proving compatibility | Process-level corpus, normalization rules as spec, coverage gate, pairing gate, differential payload fuzzing (D03) |
| P4 | Stdlib semantic gaps | TOML: vendored smol-toml + `toml-test` (D04). The rest (§5) are corpus-covered JS modules in `js/common/`, each with a table of cases shared with Python |
| P5 | Hook latency (Node start ~90 ms in one run) | Budget: JS p50 ≤ Python package-mode p50, same host, recorded (D05). Levers: few-module entry points, lazy imports, Node's module compile cache |
| P6 | Harness contracts measured on Python hooks | Live probe on Claude and Codex in a Python-less container before any parity claim (N10) |
| P7 | Messages and skills print `python3 …/tools/…` | `akmon tool <path>`; messages name the executing implementation's command (D06) |
| P8 | Mounted modes in Node repos | Stay Python (D02) |
| P9 | akmon's repo gains a Node toolchain | Accepted (D04 consequences); `AGENTS.md` verification set grows (C103) |
| P10 | Docs duplicate per ecosystem | C112: one Node path in BOOTSTRAP, commands via `akmon …`, not interpreter paths |

### F4 — Integration record format: TOML stays

The owner asked whether to move the record to YAML. It would make things worse on both sides:

- Python has no stdlib YAML, so the Python implementation would lose its zero-dependency
  contract.
- The YAML spec is far larger, and its implicit typing (`no` → `false`) is a known defect class.
- Python consumers' `pyproject.toml` stays TOML regardless.

TOML stays, read in JS by vendored smol-toml (ADR 0020 D04).

### F5 — Checks, linters and analyzers (extends ADR 0014 D01 §4–5; ADR 0020 D07)

`init` (JS implementation, Node ecosystem) detects the project's own tools and records commands
through the project's package manager:

| Tool | Config it detects | Recorded command | `files` patterns |
|---|---|---|---|
| ESLint | `eslint.config.{js,mjs,cjs,ts,mts,cts}`, `.eslintrc*`, `package.json#eslintConfig` | `<run> eslint {files}` | `*.js *.mjs *.cjs *.jsx *.ts *.mts *.cts *.tsx` |
| Biome | `biome.json`, `biome.jsonc` | `<run> biome check {files}` | same plus `*.json` |
| oxlint | `.oxlintrc.json` | `<run> oxlint {files}` | JS/TS set |
| Prettier | `.prettierrc*`, `prettier.config.*`, `package.json#prettier` | `<run> prettier --check {files}` | JS/TS + `*.json *.css *.md` |
| TypeScript | `tsconfig.json` | `<run> tsc --noEmit -p .`, **no `{files}`**: `tsc` given files ignores `tsconfig.json` | — (whole project) |

- **`<run>`** comes from the `packageManager` field first, then the lockfile: `package-lock.json`
  → `npx --no-install`, `pnpm-lock.yaml` → `pnpm exec`, `yarn.lock` → `yarn`,
  `bun.lock`/`bun.lockb` → `bunx`. `--no-install` makes a missing tool a failed check, not a
  silent download.
- **Patterns.** Node checks always record explicit `files` patterns (the implicit default is
  `*.py`).
- **Scripts.** `package.json` `lint`/`typecheck` scripts are named in the report for the owner's
  `own` choice, never auto-recorded.
- **Ruleset offer.** The akmon offer ships inside the package and is reached by `extends` by
  package name (`"extends": ["akmon/biome"]` or `import akmon from "akmon/eslint"`), so nothing is
  materialized. **Tool and rules: A35**, after a baseline on a real Node repository. Until then a
  Node project chooses between `own` and `none`.

**Landscape probe, 2026-09-26** ([MEASUREMENTS.md M100–M101](../MEASUREMENTS.md)): on npm
`eslint` is at 10.11.0 (v10 latest), `@biomejs/biome` at 2.5.14 (the unscoped `biome` name is an
unrelated package), `oxlint` 1.85.0, `prettier` 3.9.9, `typescript` 7.0.2 — the native line is
`latest`, and its `tsc --checkJs --noEmit --allowJs` caught a planted JSDoc argument-type error,
so ADR 0020 D04's checkJs verification holds on `latest` without a pin. The A35 baseline
candidate tvassistant runs ESLint 9 flat config + `@eslint/js` + `eslint-plugin-vue` and nothing
else of this table — the `akmon/eslint` form is the one with a measured home. The tool and rules
decision stays with A35.

### F6 — Owner-decided and agent-proposed points in ADR 0020 (all confirmed)

**Decided by the owner (2026-09-26):**

- Python-free only in `package` mode;
- the corpus is normative and Python is the reference;
- two implementations permanently, with a single JS implementation not considered;
- TOML with smol-toml;
- JS + JSDoc;
- all tools ported, as a base for JS projects;
- the hook latency budget.

**Proposed by the agent, written into ADR 0020, and confirmed by the owner on 2026-09-26
(all five points and the carried-over row):**

| Point | Block | Why proposed |
|---|---|---|
| Node floor 22 | D04 | oldest maintained LTS on 2026-09-26 (Node 20 ended April 2026) |
| `akmon tool <path>` as one subcommand in both implementations | D06 | tools need a Python-free entry; it reverses the "no command groups" stance recorded in the `update` design, with a single level only |
| Mirrored `js/` layout + pairing gate | D03 | makes "every Python file has its JS counterpart" mechanically checkable |
| One file list for both carriers (the wheel carries `js/`, npm carries `.py`) | D05 | a single test proves "same artifact"; costs unused files in each package |
| JS tool modules as a public API under release versioning | D06 | follows from "a base for JS projects"; makes a tool refactor a potential breaking release |
| Carried over from the first draft: exact pin, PnP unsupported, guardrails copied, checks detection, update per manager, owner-run publish | D05, D07 | presented in the first draft and not questioned in the discussion |

## 4. Target shape

### Repository layout

`js/` mirrors every consumer-executable Python file at the same relative path. The pairing gate
(D03) keys on this layout.

```
src/akmon/cli.py            → js/akmon/cli.mjs         (npm "bin": {"akmon": "js/akmon/cli.mjs"})
bin/sync.py                 → js/bin/sync.mjs
common/record.py            → js/common/record.mjs
hooks/role-on-code.py       → js/hooks/role-on-code.mjs
tools/model_routing/init.py → js/tools/model_routing/init.mjs   (+ "exports")
js/vendor/smol-toml/        (pinned, LICENSE kept, updated only by a task)
meta/conformance/           (the corpus: scenarios, fixtures, normalization rules, runner)
package.json                (root; no dependencies, no `scripts` key, exact-pinned
                             devDependencies, engines node >=22)
```

Akmon's own dev linter is ESLint 10 (`@eslint/js` recommended) — owner decision 2026-09-27. It
is akmon-internal: it lints this repository's `js/` and does not pre-decide A35's consumer ruleset.

Both carriers ship one file list (D05). The wheel carries `js/` and the npm package carries the
Python files, which are unused there. This keeps "same artifact, two entry points" provable by a
single test.

Shared data (C102) stays where it is: a JSON file beside its Python reader (`bin/sync.json`,
`hooks/hook_core.json`, …), which the paired `.mjs` reads at that path with `JSON.parse`. Stored
text marks a runtime value as `{{name}}` — filled by `common/jsondata.py::fill`, and by its JS
twin — and the code formats every value before filling it. These `{{…}}` placeholders are
unrelated to the corpus's normalization tokens (§5), which only share the spelling. A process
reads a data file once at its entry point and passes it down. A crash handler reads none: its
text stays in code, because a missing data file is one of the failures it reports.

### Consumer experience

```bash
npm install -D -E akmon            # pnpm add -D -E / yarn add -D -E / bun add -d --exact
npx akmon init --mode package      # records ecosystem = "node", wires hooks, detects eslint/tsc…
npx akmon check --changed          # the project's own tools through its manager
npx akmon sync --check && npx akmon verify --strict   # CI: Node only
npx akmon tool model_routing/init --orchestrator …    # tools, same command in both ecosystems
```

Generated Claude wiring:
`node "$CLAUDE_PROJECT_DIR/node_modules/akmon/js/hooks/role-on-code.mjs"`.

The dev layer is **not** the project's source, and JS tooling does not know that on its own:
`node --test` and `eslint` skip `node_modules/` by default and scan every other directory, so a
mounted tree inside the project root is scanned as if it were the project's code (measured —
M116: a vendored consumer's own `node --test` ran akmon's suites and reported 4 failures). Two
rules follow, and each has a single owner:

- the mount carries no development-only files: `_init._COPY_IGNORE` filters `*.test.mjs` (the
  same rule the member allowlist already applies to `src/` and `tests/`), so the mount holds
  runnable material and a consumer's test command stays its own — while both carriers keep the
  tests, since a wheel's `site-packages` and a package inside `node_modules` are outside any
  scan path;
- the consumer's own configuration excludes `_aitna/**` from lint and typecheck, exactly as
  `_aitna/.venv/` is already a git ignore. `init` detects `eslint`/`tsc` today and can check the
  exclusion; making it *write* one is C105's (§7).

## 5. Conformance corpus (D03) — the spec

- **Scenario kinds.** Each one gives an input and its expected output:
  - hook: payload + env + project fixture → stdout/stderr/exit;
  - CLI: fixture + argv → written files (byte-exact), stdout/stderr/exit, findings;
  - tool: argv + fixture → output;
  - unit tables for the functions a JS port cannot inherit: the stdlib gaps (`shlex`-split, glob
    matching, JSON writer and its number spelling, code-point sorting, record parsing) and the
    shared data-driven answers (version ordering, the runtime's commands, the `[check]` table and
    the argv it builds). What a table cannot carry — an answer that needs a filesystem, a git
    repository or a child process — stays a scenario or a `node:test` instead.
- **Normalization rules** (versioned with the corpus): the project-root path, temp paths, and the
  interpreter spelling in wiring (`python3 "<…>.py"` ↔ `node "<…>.mjs"`). Anything not normalized
  must match exactly.
- **Ecosystem tag.** A scenario is `shared`, `python` or `node`. Shared scenarios run on both.
  Because the mounted modes stay Python-only (D02), a shared scenario attaches its consumer in
  the implementation's **native package mode**, and a mounted scenario is `python`-tagged. A
  finding code whose lines name one ecosystem's carrier (tree layout, manifest pin, launcher) is
  owned by that ecosystem; a shared scenario pins every other finding line (owner decision on
  the C101 review, 2026-09-27; mechanics in `meta/conformance/README.md`).
- **Gates** (self-CI):
  1. both implementations pass every scenario of their scope;
  2. the coverage gate: every command, hook, tool and finding code appears in a scenario;
  3. the pairing gate: every consumer-executable `.py` has its `.mjs` counterpart, or an exemption
     with a reason; the list must not lie in either direction — an exemption covering only files
     whose port has landed is stale, and a counterpart listed as a `[[stub]]` placeholder is not
     credited as a port, so an outstanding task cannot read as done;
  4. differential fuzzing: recorded real payloads plus mutations, compared on both
     implementations (bounded run in CI, longer run before a release).
- **Seeding.** C101 builds the corpus against Python alone, from today's behavior, before any JS
  exists. The corpus is then a regression net for Python and the acceptance test for the port.

## 6. Implementation plan

Ids were free on 2026-09-26 across HEAD, the main checkout and all worktrees. Order is dependency
order. Stages: **0** spec · **1** data-first · **2** minimum Python-free slice · **3** full port ·
**4** checks and rules · **5** proof and publish.

| Id | Stage | Title | Depends on | Done when |
|---|---|---|---|---|
| C101 | 0 | Conformance corpus + runner, seeded against Python | — | scenario kinds and normalization of §5 in `meta/conformance/`; the coverage gate lists every command, hook, tool and finding code covered; `self_ci` leg `selfci.conformance` green on Python |
| C102 | 1 | Data-first reduction | C101 | inventory of logic that can be data (policy tables, message templates, matcher and tool-name tables) and its move into shared data files; corpus unchanged and green |
| C103 | 2 | JS foundation | C101 | root `package.json` (no deps, `engines` node ≥22, `bin`, one file list with the wheel, tested); `tsc --checkJs` + `node:test` + JS lint in the verification set (`AGENTS.md`); vendored smol-toml passing `toml-test`; `js/common/` for record, versions (incl. PEP 440 → SemVer), project root, runtime, check runner, shlex, glob, JSON writer, each on the shared unit tables; pairing gate live with the exemption list; the orphan `package-lock.json` replaced by the committed dev lock (exact-pinned devDependencies; `npm ci --ignore-scripts`, `npx --no-install`); `release_check` checks the `package.json` version carrier |
| C104 | 2 | JS hooks + Node wiring | C103 | all hook entry points, core and adapters in `js/hooks/` pass the hook corpus; Node wiring spelling and marker in both implementations' `sync`; latency budget met and recorded in `MEASUREMENTS.md` (JS vs Python p50, same host). Two passes, see below |
| C105 | 2 | JS CLI for Node package mode | C103, C104 | `init` (package/node), `sync`, `verify`, `check`, `path`, `hook`, `version` pass the corpus; `package.json` pin reader; `ecosystem` in the record; PnP, runtime-class pin and missing `node_modules/akmon` each a named finding; per-ecosystem runtime declaration (`meta/checks/runtime.py` extended); Node CI template without Python |
| C106 | 2 | npm smoke leg without Python | C105 | `selfci.npm-smoke`: `npm pack` → install into a fixture Node project → init/sync/verify/hook with `python3` hidden from PATH; the npm/network prerequisite named in its failure |
| C107 | 3 | JS `update` for npm/pnpm/yarn/bun | C105 | each manager's exact command covered; unknown manager → printed command; rollback announced |
| C108 | 3 | Tools port + `akmon tool` in both implementations | C103, C105 | every `tools/` module in `js/tools/` passes the tool corpus; `akmon tool <path>` in Python and JS; messages name the executing implementation's command; `exports` map with a documented module API |
| C109 | 4 | `init` detects JS/TS linters and analyzers | C105 | §3 F5 table in node-tagged scenarios per tool and per manager; explicit patterns; `tsc` without `{files}`; scripts named, not recorded |
| A35 | 4 | `js` profile + akmon JS ruleset (tool choice) | C109 | baseline over a real Node repository (tvassistant candidate); owner accepts tool and rules as a block extending ADR 0014/0020 |
| C110 | 4 | Ship the A35 ruleset + `--checks akmon` for Node | A35 | `extends` written into the project's own config, never over one it chose; a scenario per config format |
| N10 | 5 | Live harness probe on a Python-less Node consumer | C105, C108 | Claude and Codex observed running every wired hook from `node_modules/akmon/js` in a container without Python; `MEASUREMENTS.md` rows with harness versions |
| C111 | 5 | Differential fuzzing at release depth | C104 | recorded-payload + mutation run wired into the release gate; divergences become scenarios |
| C112 | 5 | Docs | C105, C108, C109 | README, BOOTSTRAP (Node path), MODEL, ARCHETYPES, packaging open point closed, skills naming `akmon tool`; citation check green |
| V5 | 5 | First npm publish (owner) | C101–C106, N10, V1 sequencing as V4 | `npm view akmon version` == the released tag |

C104 runs in two passes (owner decision 2026-10-04), each ending at a master-control review.

- **Pass 1 — what the hooks stand on.** `common/markers`, `common/materialization` and
  `tools/model_routing/routing` ported to `js/common/` and `js/tools/model_routing/`, each with
  a unit table in `meta/conformance/units/` and the shared JSON they read; the pairing entries
  for these three leave the exemption list (the rest of `tools/*` stays exempt for C108).
- **Pass 2 — the hooks.** `hook_core`, `claude_adapter`, `codex_adapter` and the nine entry
  points in `js/hooks/`; the node layer of the hook corpus (`runner.py --impl node` on all 36
  scenarios); Node wiring and marker in `bin/sync.py` / `bin/sync.json` and the matching part of
  the JS `sync`; the `hooks/*` exemption removed; the JS latency measured against the Python
  baseline (M122) with the P5 levers if it loses.

`routing.py` belongs to C104 and not to C108 because `gate-audit`, `delegation-log` and
`model-routing` import it: measured on 2026-10-04, 87 of its 91 definitions and 1317 of its 1688
lines are reachable from those three hooks. The four definitions outside that reach
(`second_opinion_command`, `second_opinion_unavailability`, `context_fill_ratio`,
`UnpinnableModelError`) travel with the file, so the pair stays whole. C108 keeps the other
`tools/` modules (`init`, `stats`, `gate_pack`, `coverage_map`, `second_opinion`).

C101–C106 give the minimum usable Python-free slice. Everything after that extends it.
Master-control review per task: the `AGENTS.md` verification set, plus the corpus result on both
implementations and, from C103 on, `npm pack --dry-run` against the wheel's file list.

## 7. Open points

- **Hoisted monorepo layouts** (akmon only at a workspace root above the project root): the
  wiring would need a locator. Deferred, with the same trigger as the Python "venv outside the
  project root" point.
- **Where Python behavior is ambiguous** (found while seeding C101), each case is resolved once
  and becomes a scenario. The resolutions are listed in the C101 evidence, not decided here.
- **Scoped fallback name** (`@akmon/cli`) if `akmon` on npm is taken before V5 (free on
  2026-09-26).
- **`init` writing the dev-layer exclusion.** The consumer's eslint/tsconfig must ignore
  `_aitna/**` (§4, M116); today `init` detects those tools but leaves the exclusion to the
  project. Whether it should *edit* a project's config, only report the gap as a finding, or
  ship a shareable config the project spreads from is C105's call — the mount is already clean of
  development-only files, so the residue is lint and typecheck noise over runnable sources, not a
  broken test command.

## 8. Starting the implementation

Each task runs in its own session with the owner reviewing at the task boundary (master control).
Start prompt:

```
🧭 agent: engineer — Node.js implementation of akmon, starting with C101.

Read AGENTS.md, ADR meta/decisions/0020-node-consumers-js-implementation.md and
meta/design/node-consumers.md (§5 corpus, §6 plan). The decisions are accepted: do not
reopen them; raise any conflict with the ADR to the owner instead of resolving it yourself.

Take the tasks strictly in plan order, starting with C101 (the conformance corpus and runner,
seeded against Python; self_ci leg selfci.conformance). Stop for review after each task: report
what was done, each "Done when" criterion from §6 with its evidence, and the full AGENTS.md
verification set (pytest, ruff, meta/self_ci.py, uv build; from C103 also tsc --checkJs,
node:test, npm pack --dry-run). Do not commit — the owner commits.
```

Known before this work: `meta/tests/test_adapters.py::test_the_claude_shell_diagnostic_leaves_the_guard_decision_intact`
failed on the pre-A34 tree (1 failed, 1562 passed). **Stale as of the A22 tree:** the A22
commit updated that test, and the full suite is green including it (1669 passed on 2026-09-26,
C101 evidence resolution 3). The corpus pins the current first-Bash-call diagnostic behavior.
