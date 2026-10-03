# The conformance corpus (C101)

The language-neutral behavioral spec both permanent implementations of akmon must pass
(ADR 0020 D01/D03; design [node-consumers.md §5](../design/node-consumers.md#5-conformance-corpus-d03--the-spec)).
The corpus lives at the **process boundary**: it invokes a hook, CLI command, tool or probe
exactly the way a harness or an owner would, and compares the normalized observable
(stdout, stderr, exit code, written files) with the recorded expectation. Where the corpus
is silent, the Python implementation is the reference, and the resolution becomes a scenario.

## Layout

| Path | Role |
|---|---|
| `scenarios/<area>/*.toml` | one scenario per file; areas: `hooks`, `cli`, `tools`, `units` |
| `fixtures/<name>/` | static consumer-project files a scenario's project is copied from (`base`) |
| `fixtures/attach/<layer>/` | the files a `native` attach lays over the base: `package` (both package modes), `python` (the Python carrier), `node` (C105) |
| `fixtures/tree/` | corpus-owned stand-ins for the standard tree's prose documents (see the snapshot) |
| `units/<name>.toml` | shared unit tables (inputs + expected answers) for the stdlib-gap functions |
| `coverage.toml` | the coverage gate's **exceptions**: ecosystem ownership, exemptions, reviewed dynamic sites |
| `pairing.toml` | the pairing gate's two lists: `[[exempt]]` — a `.py` whose port is outstanding, with reason and owning task — and `[[stub]]` — a `js/` counterpart that only announces it |
| `normalize.py` | normalization v2 — the other half of the spec (tokens and rules) |
| `corpus.py` | scenario loading, the snapshot, fixture materialization |
| `runner.py` | executes scenarios against one implementation; `--record` reseeds expectations |
| `coverage.py` | the coverage gate: derives the population from the source and checks it |
| `pairing.py` | the pairing gate: every consumer-executable `.py` paired under `js/` or exempted, with no exemption outliving its port or crediting a stub |
| `probe.py` | the Python implementation's mouth for unit tables |
| `probe.mjs` | the JS implementation's mouth for unit tables (same contract: the `{"ok","failed"}` document, exit 1 on a miss) |

## Ecosystems and attaches

ADR 0020 D02: the mounted modes (`submodule`, `vendored`, `subtree`) run the Python
implementation only; the JavaScript implementation covers Node **package** mode. A scenario
says both what it is spec for and how its consumer is connected:

- `ecosystem = "shared"` — spec for both implementations; `"python"` / `"node"` — one only.
- `[fixture] attach = "native"` (default) — the implementation's own package mode: the base
  fixture plus the `package` layer (a package-mode `AGENTS.md` block) and the ecosystem's carrier
  layer (Python: the record with `mount = "package"`, the `pyproject.toml` dev pin (written by `corpus.py`, as the launcher is), CI calling
  `uv run akmon`, and the `.venv/bin/akmon` launcher the runner writes). Hooks run through the
  launcher (`akmon hook <name>`), the way package wiring calls them.
- `attach = "mount"` — `<AITNA_ROOT>/akmon` links the snapshot. **Python only**: the loader
  refuses it on a `shared` or `node` scenario. Hooks run as `python3 <tree>/hooks/<name>.py`.
- `attach = "none"` — nothing connected (usage errors, `init` onto a bare project).

A shared scenario whose output carries lines of a code an ecosystem owns (the standard-tree
layout, the carrier's pin, the launcher — `coverage.toml [ecosystem]` whole-code entries)
cannot pin that output whole, so it records `findings` instead of `stdout`: every finding line
except those codes'. Those lines are pinned by the owning ecosystem's scenarios, recorded with
their exact `stdout` (e.g. `cli/verify-package-healthy` is the Python carrier's full report).

## Scenario schema

```toml
id = "area/name"          # must equal the file path under scenarios/
ecosystem = "shared"      # shared | python | node — runs on the impl whose scope includes it
kind = "hook"             # hook | cli | tool | unit
covers = ["hook:role-on-code", "code:agents.block-anchors"]   # claims; each must name a derived item

[fixture]                 # omit for the defaults (base, native, synced)
name = "base"             # fixtures/<name>/
attach = "native"         # native | mount | none (above)
files = { "rel/path" = "content" }   # written over base + attach layers ({{version}} materializes)
remove = ["rel/path"]               # base/layer files deleted before the run
branch = "main"                     # the fixture is a fresh git repo on this branch
warmup = "after"                    # the impl's own sync: "after" the files (a synced project; native
                                    # default), "before" them (synced, then the files break it), "none"
git = true                          # false: no repo at all (the not-a-work-tree scenario)
repo = false                        # build a local standard-tree git repo tagged v<version> (for --repo)
tmp_files = { "name" = "content" }  # seeded into the run tempdir (hook markers and counters)
tree_files = { "rel/path" = "…" }   # scenario-local override of the snapshot (tree-side breaks)
tree_remove = ["rel/path"]          # snapshot paths deleted from that scenario-local copy
tags = ["v1.1.0"]                   # git tags on the fixture's baseline commit (release checks)

[env]                     # environment overrides for the process under test
AITNA_ROOT = "_aitna"

[run]
script = "role-on-code"   # hook: the hook name (python: hooks/<script>.py | node: js/hooks/<script>.mjs)
args = []                 # hook: extra argv
payload = { ... }         # hook: the stdin JSON document (tokens materialized)
argv = ["sync", "--check"]# cli: console argv; tool: argv after the tool path
tool = "model_routing/init"  # tool: tools/<tool>.py (C108: `akmon tool <tool>` in both)
probe = "versions"        # unit: probe subcommand
table = "versions.toml"   # unit: units/<table>

[expected]
exit = 0
stdout = "…"             # exact, normalized — or stdout_json (hooks) — or findings (above)
findings = ["OK …", …]    # the shared finding lines, in output order
stderr = "…"             # exact, normalized — or stderr_contains
stderr_contains = ["…"]   # only for text an argument parser owns (usage banners); hand-written
[expected.files]         # rel path -> exact normalized content, or ref:tree:<path>
"rel/path" = "content"
file_absent = ["rel/path"]
[expected.stdout_json]   # hook: parsed-JSON equality with normalized string leaves
```

A scenario that asserts nothing beyond its exit code is refused. An unseeded scenario (no
`[expected]`) is a red state the loader names loudly. A `code:` claim must appear as a finding
line of the actual stdout (a line match, not a substring). A marker a scenario seeds in
`tmp_files` names the implementation's marker file, so the marker naming (`common/markers.py`)
is part of the spec a port mirrors.

## Normalization v2

A scenario file is written normalized already: it contains the tokens. The runner maps every
observable into the same form before comparing; **anything a rule does not normalize must
match exactly**. Rules, in normative order (see `normalize.py`):

1. **Hook commands** keep their anchor and the hook, however the ecosystem spells the call:
   `python3 "<anchor>/…/hooks/<name>.py"`, `node "<anchor>/…/hooks/<name>.mjs"` and the launcher
   `"<anchor>/<rel>" hook <name>` all become `{{hook <anchor> <name>}}` (raw and JSON-escaped),
   anchor `$CLAUDE_PROJECT_DIR` or `$(git rev-parse --show-toplevel)`. A command hanging from
   anything else is not collapsed, so an absolute path in shared wiring shows as a mismatch.
   The launcher's relative path is the Python carrier's fact, pinned by `hooks.launcher`.
2. **Tool calls** in package-mode spelling, `python3 $(akmon path)/tools/<tool>.py`, become
   `{{tool <tool>}}`; the Node spelling joins the rule with `akmon tool` (C108). The mounted
   spelling names the mount and stays as written, so a package-mode message that names the
   mount (the C77 class) is caught.
3. **Parser details** after `invalid JSON:` / `cannot be read as TOML:` up to the finding's
   ` → ` become `{{parse-error}}`: that a file failed to parse, and which, is spec; the
   parser's words are the implementation's.
4. **Paths**: mount → `{{mount}}`, tree → `{{tree}}`, project root → `{{root}}` (longest first;
   the mount path contains the root), run tempdir → `{{tmp}}`, the local standard repo → `{{repo}}`.
5. **Point-in-time**: the running version → `{{version}}`; datetimes and `YYYYMMDD-HHMMSS`
   stamps → `{{ts}}` and bare dates → `{{date}}` **only for the run's own day(s)**. A date from
   any other day came from a fixture and is compared literally.

Changing a rule, or adding one, is a corpus version change: bump `NORM_VERSION` in
`normalize.py` and say what changed here. v2 (C101 review): rule 1 keeps the anchor and covers
the launcher (v1 erased the whole path and kept the launcher's relative path); rules 2 and 3
are new; rule 5 is limited to the run day.

## Fixture model

- The **snapshot** (`corpus.SNAPSHOT_FILES` + the wired hooks + the `js/` tree carried whole via
  its derived list, `corpus.py::snapshot_js`) is the corpus-controlled standard tree: code, data
  and configuration are copied from the repository under test (including `src/akmon`, so a
  native consumer runs the snapshot's own CLI and it resolves the snapshot as its embedded
  tree); the **prose documents** come from `fixtures/tree/` stand-ins. The corpus
  pins behavior, not prose: with the real documents every guardrail edit (the always-loaded cap
  measures the imported guardrail) and every release (the healthy changelog check reads
  `## Unreleased`) would move the spec. A stand-in the snapshot does not list, or a listed path
  the repository no longer has, is refused.
- Every scenario run gets a fresh copy of the fixture, a fresh private tempdir (markers and
  counters land there, isolated from host state and each other), and a fresh git repo on the
  scenario's branch, committed once after the warmup — a synced consumer's sync output is its
  baseline, not a change.
- The `codex` binary is hidden from the process under test's PATH (self-CI's technique):
  `codex.host-trust` takes its absent-install skip, so the corpus never runs a live harness
  RPC. Its warn side is exempt in `coverage.toml`; live harness probes are N10's job.

## Gates

1. **Scope gate** — every scenario in the impl's scope (`shared` + its own tag) passes.
2. **Coverage gate** (`coverage.py`) — the population is **derived from the source** of the tree
   under test, never listed: commands from `src/akmon/cli.py` `_COMMANDS`, hooks and tools from
   their `__main__` blocks, unit tables from `units/`, and `code:<code>:<severity>` from every
   literal emission site (`self.ok|warn|error("code", …)`, `Finding("severity", "code", …)`).
   Evidence comes from each scenario's run and its recorded expectation lines, not from its
   claims. An item is covered only by a `shared` scenario unless `coverage.toml [ecosystem]`
   gives it to one ecosystem. `[exempt]` lists what no hermetic scenario can reach, `[dynamic]`
   the reviewed non-literal emission sites; an unlisted dynamic site, or an entry naming nothing
   derived, fails the gate. The runner runs it last.
3. **Pairing gate** (`pairing.py`) — every consumer-executable `.py` has its `.mjs` counterpart
   under `js/` at the mirrored path (design §4: `X/Y.py` → `js/X/Y.mjs`, the package mapping to
   the package — `src/akmon/cli.py` is `js/akmon/cli.mjs`), or an exemption in
   `meta/conformance/pairing.toml` with a reason and the owning task. The population is the five
   `CODE_ROOTS` (`coverage.py` owns the roots). The gate runs on a full corpus run, after the
   coverage gate, and fails like it does: a gap (`pairing.gap`) is an error, and so is an
   exemption that no longer says anything true (`pairing.stale`) — one covering no file, or one
   covering only files whose port has landed. A counterpart that is a placeholder rather than a
   port is named by a `[[stub]]` entry (its exact `js/` path, plus the task that replaces it) and
   is **not** credited as a port: the `.py` behind it stays exempt and still needs its own
   exemption, so an outstanding task cannot read as done. The exemption list shrinks as the port
   lands (C104 hooks, C105 CLI, C107 update, C108 tools), and the `[[stub]]` entry goes with it.
4. **Differential fuzzing** — recorded payloads plus mutations through both implementations
   (C111 wires the release-depth run).

## Seed protocol

Seeding is a two-step act, and the split is load-bearing:

1. `runner.py --record --scenario <id>` runs the implementation and writes the `[expected]`
   section from the live behavior (`stdout`, or `findings` where the output carries an
   ecosystem-owned code; `stderr_contains` is hand-written and kept). Unit scenarios are never
   recorded — the table is the expectation.
2. A human reviews that the recorded behavior **is** what the standard means — the recorded
   text is read as a spec, token by token; host facts, absolute paths and accidental drift
   are bugs in the scenario (or the normalization), not expected values.

Only after step 2 does the record become spec. A scenario that passes by recording is not a
scenario that covers.

## Self-CI

The `selfci.conformance` leg of `meta/self_ci.py` runs `runner.py --tree <repo>` (Python
implementation + coverage gate). The corpus is green when the leg is green. The machinery is
pinned by `meta/tests/test_conformance_coverage.py` and `meta/tests/test_conformance_corpus.py`.

From C103 the corpus also runs on the node implementation: `selfci.corpus-node` runs
`runner.py --tree <repo> --impl node --area units` — the same unit tables through
`probe.mjs`, fixture-free, with the gates off (they run on a full run only). The node
toolchain's own checks are independent self-CI legs on the same prerequisite-naming stance as
the wheel smoke: `selfci.js-deps` (`npm ci --ignore-scripts`), `selfci.js-typecheck`
(`npx --no-install tsc --checkJs --noEmit -p .`), `selfci.js-unit` (`node --test js/`) and
`selfci.js-lint` (`npx --no-install eslint .`).
